import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple


class APIKeyManager:
    """
    Manages multiple API keys with intelligent rotation, quota tracking, and demo phase limits.
    
    Features:
    - Multi-key rotation with automatic failover
    - Per-key and global quota tracking
    - Demo phase enforcement with hard cap
    - Real-time usage monitoring and alerts
    - Legacy fallback support
    - **Persistent call tracking across bot restarts**
    """
    
    def __init__(
        self,
        max_calls: Optional[int] = None,
        demo_max_calls: Optional[int] = None,
        demo_phase_enabled: Optional[bool] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.logger = logger or logging.getLogger(__name__)
        
        # Load keys from comma-separated env variable
        raw_keys = os.getenv("ODDS_API_KEYS", "")
        self.keys: List[str] = [k.strip() for k in raw_keys.split(",") if k.strip()]

        # Fallback for legacy individual env vars
        if not self.keys:
            fallback_names = [
                "ODDS_API_KEY1", "ODDS_API_KEY2", "ODDS_API_KEY3", "ODDS_API_KEY4"
            ]
            self.keys = [os.getenv(name) for name in fallback_names if os.getenv(name)]
            if self.keys:
                self.logger.warning("Using legacy individual API key env vars. Consider migrating to ODDS_API_KEYS.")

        if not self.keys:
            self.logger.error("No API keys found in environment variables!")
            raise ValueError("No API keys configured. Set ODDS_API_KEYS in .env file.")

        # API call limits (per .env and demo settings)
        self.max_calls = max_calls if max_calls is not None else int(os.getenv("MAX_API_CALLS", "500"))
        self.demo_max_calls = demo_max_calls if demo_max_calls is not None else int(os.getenv("DEMO_MAX_API_CALLS", "2000"))
        self.demo_phase_enabled = demo_phase_enabled if demo_phase_enabled is not None else os.getenv("DEMO_PHASE_ENABLED", "0") == "1"
        
        # Initialize tracking
        self.calls_made: Dict[str, int] = {k: 0 for k in self.keys}
        self.total_calls: int = 0
        self.current_idx: int = 0
        self.exhausted_keys: set = set()
        
        # Persistence setup
        self.tracking_file = Path('data/api_usage_tracking.json')
        self.tracking_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load previous session's data
        self._load_tracking_data()
        
        self.logger.info(f"APIKeyManager initialized with {len(self.keys)} keys")
        self.logger.info(f"Per-key limit: {self.max_calls} calls")
        if self.demo_phase_enabled:
            self.logger.info(f"Demo phase active - Global cap: {self.demo_max_calls} calls")
        self.logger.info(f"Total calls from previous sessions: {self.total_calls}")

    def _load_tracking_data(self):
        """Load call tracking from previous session (same day only)"""
        if not self.tracking_file.exists():
            self.logger.info("No previous tracking data found - starting fresh")
            return
        
        try:
            with open(self.tracking_file, 'r') as f:
                data = json.load(f)
            
            # Check if data is from today (UTC)
            last_reset_str = data.get('last_reset')
            if not last_reset_str:
                self.logger.warning("Tracking file missing last_reset - starting fresh")
                return
            
            last_reset = datetime.fromisoformat(last_reset_str)
            now = datetime.now(timezone.utc)
            
            # Compare dates (ignoring time)
            if last_reset.date() == now.date():
                # Same day - restore call counts
                restored_count = 0
                for key in self.keys:
                    # Use last 16 chars as key identifier
                    key_id = key[-16:]
                    if key_id in data.get('call_counts', {}):
                        count = data['call_counts'][key_id]
                        self.calls_made[key] = count
                        restored_count += count
                        
                        # Mark as exhausted if at limit
                        if count >= self.max_calls:
                            self.exhausted_keys.add(key)
                
                self.total_calls = data.get('total_calls', restored_count)
                
                self.logger.info(f"✅ Restored API usage from previous session")
                self.logger.info(f"   Total calls restored: {self.total_calls}")
                for key in self.keys:
                    self.logger.info(f"   ...{key[-8:]}: {self.calls_made[key]}/{self.max_calls} calls")
            else:
                self.logger.info(f"New day detected - starting fresh tracking")
                self.logger.info(f"   Previous: {last_reset.date()}, Current: {now.date()}")
                # New day - data will be overwritten on first save
                
        except Exception as e:
            self.logger.warning(f"Could not load tracking data: {e}")
            self.logger.info("Starting with fresh tracking")

    def _save_tracking_data(self):
        """Save current call tracking to disk"""
        try:
            data = {
                'last_reset': datetime.now(timezone.utc).isoformat(),
                'total_calls': self.total_calls,
                'call_counts': {
                    key[-16:]: self.calls_made[key]  # Use last 16 chars as identifier
                    for key in self.keys
                }
            }
            
            with open(self.tracking_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            self.logger.warning(f"Could not save tracking data: {e}")

    def is_demo_cap_reached(self) -> bool:
        """Check if demo phase global cap has been reached."""
        if self.demo_phase_enabled and self.total_calls >= self.demo_max_calls:
            return True
        return False

    def get_next_key(self) -> Optional[str]:
        """
        Get next available API key using round-robin rotation.
        Skips exhausted keys and returns None if all keys are exhausted.
        """
        if self.is_demo_cap_reached():
            self.logger.error(f"Demo API cap reached: {self.total_calls}/{self.demo_max_calls}")
            return None
        
        start_idx = self.current_idx
        attempts = 0
        max_attempts = len(self.keys)
        
        while attempts < max_attempts:
            key = self.keys[self.current_idx]
            quota_left = self.max_calls - self.calls_made[key]
            
            if quota_left > 0:
                selected_key = key
                self.current_idx = (self.current_idx + 1) % len(self.keys)
                self.logger.debug(f"Selected API key: ...{key[-8:]} (Quota left: {quota_left})")
                return selected_key
            else:
                if key not in self.exhausted_keys:
                    self.exhausted_keys.add(key)
                    self.logger.warning(f"API key ...{key[-8:]} exhausted ({self.calls_made[key]}/{self.max_calls})")
            
            self.current_idx = (self.current_idx + 1) % len(self.keys)
            attempts += 1
        
        self.logger.error("All API keys exhausted! Bot should pause or alert admin.")
        return None

    def record_usage(self, api_key: str, calls: int = 1) -> None:
        """
        Record API usage for a specific key and persist to disk.
        
        Args:
            api_key: The API key that was used
            calls: Number of calls to record (default: 1)
        """
        if api_key not in self.calls_made:
            self.logger.warning(f"Unknown API key used: ...{api_key[-8:]}")
            return
        
        self.calls_made[api_key] += calls
        self.total_calls += calls
        
        # Persist after every call
        self._save_tracking_data()
        
        self.logger.debug(f"API usage recorded: ...{api_key[-8:]} (+{calls} calls, total: {self.calls_made[api_key]}/{self.max_calls})")
        
        # Demo phase cap check
        if self.demo_phase_enabled and self.total_calls >= self.demo_max_calls:
            self.logger.error(f"Demo API call cap reached ({self.total_calls}/{self.demo_max_calls}). Bot should halt.")

    def get_best_key(self) -> Optional[str]:
        """
        Returns key with most quota remaining (not exhausted).
        Alias for get_most_available_key for backward compatibility.
        """
        return self.get_most_available_key()

    def get_most_available_key(self) -> Optional[str]:
        """
        Returns the key with the most quota left (not exhausted).
        Includes quota check warnings.
        """
        if self.is_demo_cap_reached():
            self.logger.error(f"Demo API cap reached: {self.total_calls}/{self.demo_max_calls}")
            return None
        
        warnings = self.check_api_quota()
        available_keys = [k for k in self.calls_made if self.calls_made[k] < self.max_calls]
        
        if not available_keys:
            self.logger.error("No available API key with quota left.")
            return None
        
        best_key = max(available_keys, key=lambda k: self.max_calls - self.calls_made[k])
        quota_left = self.max_calls - self.calls_made[best_key]
        self.logger.info(f"Best available key: ...{best_key[-8:]} (Quota left: {quota_left})")
        return best_key

    def reset_counts(self) -> None:
        """Reset all usage counters. Use with caution - typically for new billing periods."""
        self.logger.info("Resetting all API usage counters")
        for key in self.calls_made:
            self.calls_made[key] = 0
        self.total_calls = 0
        self.exhausted_keys.clear()
        
        # Persist the reset
        self._save_tracking_data()

    def get_usage_report(self) -> Dict[str, int]:
        """
        Get detailed usage report for all keys.
        
        Returns:
            Dictionary mapping each key (last 8 chars) to usage count
        """
        return {f"...{k[-8:]}": self.calls_made[k] for k in self.keys}

    def get_detailed_stats(self) -> Dict[str, any]:
        """
        Get comprehensive statistics about API usage.
        
        Returns:
            Dictionary with detailed usage statistics
        """
        total_capacity = len(self.keys) * self.max_calls
        total_used = sum(self.calls_made.values())
        available_keys = [k for k in self.keys if self.calls_made[k] < self.max_calls]
        
        return {
            "total_keys": len(self.keys),
            "total_calls": self.total_calls,
            "total_capacity": total_capacity,
            "total_used": total_used,
            "capacity_used_pct": (total_used / total_capacity * 100) if total_capacity > 0 else 0,
            "available_keys": len(available_keys),
            "exhausted_keys": len(self.exhausted_keys),
            "demo_phase": self.demo_phase_enabled,
            "demo_cap": self.demo_max_calls if self.demo_phase_enabled else None,
            "demo_usage_pct": (self.total_calls / self.demo_max_calls * 100) if self.demo_phase_enabled else None,
            "per_key_usage": self.get_usage_report()
        }

    def check_api_quota(self) -> List[str]:
        """
        Check if any API key is above threshold usage and generate warnings.
        
        Returns:
            List of warning messages
        """
        warnings = []
        
        # Per-key quota warnings (95% threshold)
        for key, count in self.calls_made.items():
            usage_pct = (count / self.max_calls) * 100
            if usage_pct > 95:
                warning = f"API key ...{key[-8:]} has exceeded 95% of quota ({count}/{self.max_calls})."
                warnings.append(warning)
                self.logger.warning(warning)
            elif usage_pct > 80:
                self.logger.info(f"API key ...{key[-8:]} at {usage_pct:.1f}% usage ({count}/{self.max_calls})")
        
        # Demo phase cap warning
        if self.demo_phase_enabled:
            demo_usage_pct = (self.total_calls / self.demo_max_calls) * 100
            if self.total_calls >= self.demo_max_calls:
                demo_warn = f"Demo API cap reached ({self.total_calls}/{self.demo_max_calls}). Bot should halt."
                warnings.append(demo_warn)
                self.logger.error(demo_warn)
            elif demo_usage_pct > 90:
                demo_warn = f"Demo API usage above 90% ({self.total_calls}/{self.demo_max_calls})."
                warnings.append(demo_warn)
                self.logger.warning(demo_warn)
        
        return warnings

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"APIKeyManager(keys={len(self.keys)}, "
            f"total_calls={self.total_calls}, "
            f"max_calls={self.max_calls}, "
            f"demo_phase={self.demo_phase_enabled})"
        )
