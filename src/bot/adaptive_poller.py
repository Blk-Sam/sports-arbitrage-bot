"""
adaptive_poller.py - Intelligent API polling with adaptive rate limiting
"""

import os
import logging
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import pandas as pd

logger = logging.getLogger(__name__)


class AdaptivePoller:
    """
    Manages adaptive polling intervals based on:
    - Time of day (peak vs off-peak)
    - Sleep mode (complete pause during configured hours)
    - API quota consumption
    - Market activity
    - Historical profitability from manual P&L
    """
    
    def __init__(
        self,
        api_key_manager,
        manual_pnl_analyzer=None,
        base_interval: int = 120,  # Base interval in seconds (2 minutes)
        peak_hours: Tuple[int, int] = (17, 23),  # 5 PM - 11 PM local time
        off_peak_multiplier: float = 3.0,  # 3x slower during off-peak
        quota_threshold_warning: float = 0.7,  # Slow down at 70% quota
        quota_threshold_critical: float = 0.9  # Drastically slow at 90% quota
    ):
        self.api_key_manager = api_key_manager
        self.manual_pnl_analyzer = manual_pnl_analyzer
        self.base_interval = base_interval
        self.peak_hours = peak_hours
        self.off_peak_multiplier = off_peak_multiplier
        self.quota_threshold_warning = quota_threshold_warning
        self.quota_threshold_critical = quota_threshold_critical
        
        # Sleep mode configuration
        self.sleep_mode_enabled = os.getenv("ENABLE_SLEEP_MODE", "0") == "1"
        self.sleep_hours = self._parse_sleep_hours()
        
        # Track activity
        self.last_arbitrage_found = {}  # {sport: timestamp}
        self.sport_priority = {}  # {sport: priority_score}
        self.market_priority = {}  # {market: priority_score}
        
        # Initialize priorities from manual P&L
        self._initialize_priorities()
        
        # Log sleep mode status
        if self.sleep_mode_enabled and self.sleep_hours:
            start, end = self.sleep_hours
            logger.info(f"💤 Sleep mode enabled: {start:02d}:00 - {end:02d}:00")
        else:
            logger.info("☀️ Sleep mode disabled - 24/7 operation")
    
    def _parse_sleep_hours(self) -> Optional[Tuple[int, int]]:
        """Parse SLEEP_HOURS from environment."""
        sleep_hours_str = os.getenv("SLEEP_HOURS", "")
        if not sleep_hours_str:
            return None
        
        try:
            parts = sleep_hours_str.split("-")
            if len(parts) != 2:
                logger.error(f"Invalid SLEEP_HOURS format: {sleep_hours_str}")
                return None
            
            start = int(parts[0])
            end = int(parts[1])
            
            if not (0 <= start <= 23 and 0 <= end <= 23):
                logger.error(f"Invalid sleep hours: {start}-{end}")
                return None
            
            return (start, end)
        
        except (ValueError, IndexError) as e:
            logger.error(f"Could not parse SLEEP_HOURS: {e}")
            return None
    
    def is_sleep_hours(self) -> bool:
        """Check if current time is within sleep hours."""
        if not self.sleep_mode_enabled or not self.sleep_hours:
            return False
        
        start, end = self.sleep_hours
        now = datetime.now().hour
        
        # Handle ranges that wrap midnight
        if start < end:
            return start <= now < end
        else:
            return now >= start or now < end
    
    def get_sleep_status(self) -> Dict[str, any]:
        """Get current sleep mode status."""
        if not self.sleep_mode_enabled or not self.sleep_hours:
            return {
                "enabled": False,
                "is_sleeping": False
            }
        
        start, end = self.sleep_hours
        now = datetime.now().hour
        is_sleeping = self.is_sleep_hours()
        
        # Calculate wake time
        if is_sleeping:
            if start < end:
                wake_hour = end
            else:
                if now >= start:
                    wake_hour = end
                else:
                    wake_hour = end
        else:
            wake_hour = None
        
        return {
            "enabled": True,
            "sleep_hours": f"{start:02d}:00-{end:02d}:00",
            "current_hour": now,
            "is_sleeping": is_sleeping,
            "wake_time": f"{wake_hour:02d}:00" if wake_hour is not None else None
        }
    
    def _initialize_priorities(self) -> None:
        """Initialize sport and market priorities from manual P&L data."""
        if not self.manual_pnl_analyzer or not self.manual_pnl_analyzer.data or self.manual_pnl_analyzer.data.empty:
            logger.info("No manual P&L data - using default priorities")
            return
        
        df = self.manual_pnl_analyzer.data
        
        # Sport priorities based on profitability and win rate
        if 'sport' in df.columns:
            sport_stats = df.groupby('sport').agg({
                'profit_loss': 'sum',
                'result': lambda x: (x == 'Win').sum() / len(x) if len(x) > 0 else 0
            })
            
            for sport, row in sport_stats.iterrows():
                profit = row['profit_loss']
                win_rate = row['result']
                # Priority score: profit * win_rate (higher = better)
                priority = profit * win_rate if profit > 0 else 0
                self.sport_priority[sport] = max(priority, 0.1)  # Minimum 0.1
        
        # Market priorities
        if 'market' in df.columns:
            market_stats = df.groupby('market').agg({
                'profit_loss': 'sum',
                'result': lambda x: (x == 'Win').sum() / len(x) if len(x) > 0 else 0
            })
            
            for market, row in market_stats.iterrows():
                profit = row['profit_loss']
                win_rate = row['result']
                priority = profit * win_rate if profit > 0 else 0
                self.market_priority[market] = max(priority, 0.1)
        
        logger.info(f"📊 Initialized priorities from manual P&L:")
        logger.info(f"   Sport priorities: {self.sport_priority}")
        logger.info(f"   Market priorities: {self.market_priority}")
    
    def is_peak_hours(self) -> bool:
        """Check if current time is within peak hours."""
        current_hour = datetime.now().hour
        start_hour, end_hour = self.peak_hours
        return start_hour <= current_hour <= end_hour
    
    def get_quota_usage_ratio(self) -> float:
        """Get current API quota usage ratio (0.0 to 1.0)."""
        if self.api_key_manager.demo_phase_enabled:
            max_calls = self.api_key_manager.demo_max_calls
        else:
            max_calls = self.api_key_manager.max_calls
        
        return self.api_key_manager.total_calls / max_calls if max_calls > 0 else 0
    
    def get_time_multiplier(self) -> float:
        """
        Get polling interval multiplier based on time of day.
        
        Returns:
            Multiplier (1.0 = normal, >1.0 = slower)
        """
        # Sleep mode overrides everything
        if self.is_sleep_hours():
            return float('inf')  # Infinite multiplier = don't poll
        
        if self.is_peak_hours():
            return 1.0  # Normal speed during peak
        else:
            return self.off_peak_multiplier  # Slower during off-peak
    
    def get_quota_multiplier(self) -> float:
        """
        Get polling interval multiplier based on quota consumption.
        
        Returns:
            Multiplier (1.0 = normal, >1.0 = slower)
        """
        usage = self.get_quota_usage_ratio()
        
        if usage >= self.quota_threshold_critical:
            logger.warning(f"⚠️ CRITICAL quota usage: {usage:.1%} - drastically reducing poll rate")
            return 10.0  # 10x slower
        elif usage >= self.quota_threshold_warning:
            logger.warning(f"⚠️ High quota usage: {usage:.1%} - reducing poll rate")
            return 3.0  # 3x slower
        else:
            return 1.0  # Normal speed
    
    def get_sport_multiplier(self, sport: str) -> float:
        """
        Get polling interval multiplier for a specific sport.
        Higher priority = lower multiplier (faster polling).
        
        Args:
            sport: Sport identifier
            
        Returns:
            Multiplier (lower = faster)
        """
        if not self.sport_priority:
            return 1.0  # No data, treat all equally
        
        priority = self.sport_priority.get(sport, 0.1)
        
        if priority > 10:
            return 0.5  # High priority: poll 2x faster
        elif priority > 5:
            return 0.75  # Medium-high priority
        elif priority > 1:
            return 1.0  # Normal priority
        else:
            return 2.0  # Low priority: poll 2x slower
    
    def get_adaptive_interval(self, sport: str) -> int:
        """
        Calculate adaptive polling interval for a sport.
        
        Args:
            sport: Sport identifier
            
        Returns:
            Polling interval in seconds (0 if should not poll due to sleep mode)
        """
        # Check sleep mode first
        if self.is_sleep_hours():
            return 0  # Don't poll during sleep
        
        # Base interval
        interval = self.base_interval
        
        # Apply multipliers
        time_mult = self.get_time_multiplier()
        quota_mult = self.get_quota_multiplier()
        sport_mult = self.get_sport_multiplier(sport)
        
        # Combined interval
        adaptive_interval = int(interval * time_mult * quota_mult * sport_mult)
        
        logger.debug(
            f"📊 Adaptive interval for {sport}: {adaptive_interval}s "
            f"(base={interval}, time={time_mult:.1f}x, quota={quota_mult:.1f}x, sport={sport_mult:.1f}x)"
        )
        
        return adaptive_interval
    
    def should_poll_sport(self, sport: str) -> bool:
        """
        Determine if a sport should be polled based on priority, quota, and sleep mode.
        
        Args:
            sport: Sport identifier
            
        Returns:
            True if should poll, False otherwise
        """
        # Never poll during sleep hours
        if self.is_sleep_hours():
            return False
        
        # Always poll if we have quota headroom
        usage = self.get_quota_usage_ratio()
        if usage < self.quota_threshold_warning:
            return True
        
        # If quota is tight, only poll high-priority sports
        priority = self.sport_priority.get(sport, 0.1)
        
        if usage >= self.quota_threshold_critical:
            # Only poll top-priority sports
            return priority > 10
        elif usage >= self.quota_threshold_warning:
            # Only poll medium+ priority sports
            return priority > 1
        
        return True
    
    def get_prioritized_sports(self, sports: List[str]) -> List[str]:
        """
        Sort sports by priority (highest first).
        
        Args:
            sports: List of sport identifiers
            
        Returns:
            Sorted list of sports
        """
        if not self.sport_priority:
            return sports
        
        def get_priority(sport: str) -> float:
            return self.sport_priority.get(sport, 0.1)
        
        sorted_sports = sorted(sports, key=get_priority, reverse=True)
        
        logger.info(f"📊 Prioritized sports order: {sorted_sports}")
        return sorted_sports
    
    def record_arbitrage_found(self, sport: str) -> None:
        """
        Record that an arbitrage was found for a sport.
        This can be used to temporarily increase polling frequency.
        
        Args:
            sport: Sport identifier
        """
        self.last_arbitrage_found[sport] = datetime.now()
        logger.debug(f"🔍 Arbitrage found for {sport} - recorded")
    
    def get_polling_summary(self) -> Dict[str, any]:
        """Get summary of current polling configuration."""
        sleep_status = self.get_sleep_status()
        
        return {
            'is_peak_hours': self.is_peak_hours(),
            'sleep_mode': sleep_status,
            'quota_usage': f"{self.get_quota_usage_ratio():.1%}",
            'time_multiplier': self.get_time_multiplier(),
            'quota_multiplier': self.get_quota_multiplier(),
            'base_interval': self.base_interval,
            'sport_priorities': self.sport_priority,
            'market_priorities': self.market_priority
        }


class RateLimiter:
    """
    Simple rate limiter to prevent API burst calls.
    """
    
    def __init__(self, max_calls_per_minute: int = 30):
        self.max_calls_per_minute = max_calls_per_minute
        self.call_timestamps = []
    
    def can_call(self) -> bool:
        """Check if a call can be made without exceeding rate limit."""
        now = datetime.now()
        
        # Remove timestamps older than 1 minute
        self.call_timestamps = [
            ts for ts in self.call_timestamps
            if (now - ts).total_seconds() < 60
        ]
        
        return len(self.call_timestamps) < self.max_calls_per_minute
    
    def record_call(self) -> None:
        """Record that an API call was made."""
        self.call_timestamps.append(datetime.now())
    
    async def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded."""
        import asyncio
        
        while not self.can_call():
            logger.warning("⏸️ Rate limit reached - waiting 5 seconds")
            await asyncio.sleep(5)
        
        self.record_call()
