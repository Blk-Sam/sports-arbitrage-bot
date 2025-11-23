import requests
import logging
import os
import time
import asyncio
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    import jsonschema
except ImportError:
    jsonschema = None

from src.bot.api_key_manager import APIKeyManager


class OddsDataCollector:
    """
    Collects odds data from The Odds API with intelligent key rotation, quota management,
    and both sync/async support.
    
    Features:
    - Automatic API key rotation with quota enforcement
    - Demo phase cap enforcement
    - Sync and async request methods
    - JSON schema validation (optional)
    - Dashboard callback integration
    - Event window filtering
    - Comprehensive error handling and logging
    """
    
    def __init__(
        self,
        api_key_manager: APIKeyManager,
        base_url: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        dashboard_callback: Optional[Callable[[str], None]] = None,
        max_calls: Optional[int] = None
    ):
        """
        Initialize OddsDataCollector.
        
        Args:
            api_key_manager: APIKeyManager instance for key rotation
            base_url: Base URL for The Odds API (defaults to env or standard URL)
            logger: Optional custom logger instance
            dashboard_callback: Optional callback function for dashboard alerts
            max_calls: Maximum API calls per key (defaults to manager's limit)
        """
        self.api_key_manager = api_key_manager
        self.api_key = self.api_key_manager.get_most_available_key() if api_key_manager else None
        self.base_url = base_url or os.getenv("ODDS_API_BASE_URL", "https://api.the-odds-api.com/v4/sports")
        self.headers = {"Accept": "application/json"}
        self.logger = logger or logging.getLogger(__name__)
        self.dashboard_callback = dashboard_callback
        self.max_calls = max_calls or (self.api_key_manager.max_calls if api_key_manager else 500)
        self.calls_made = 0
        self.last_request_time = 0
        self.min_request_interval = float(os.getenv("MIN_API_INTERVAL", "2"))
        
        if not self.api_key:
            self.logger.error("No API key available for data collection!")
            raise ValueError("No API key available. Check APIKeyManager configuration.")
        
        self.logger.info(f"OddsDataCollector initialized with key: ...{self.api_key[-8:]}")

    def _can_make_api_call(self) -> bool:
        """
        Check if API call can be made based on quota limits.
        
        Returns:
            True if call can be made, False otherwise
        """
        # Enforce demo-phase API cap
        if self.api_key_manager:
            if self.api_key_manager.is_demo_cap_reached():
                msg = f"Demo API call limit reached: {self.api_key_manager.total_calls}/{self.api_key_manager.demo_max_calls}"
                self.logger.warning(msg)
                self._alert_dashboard("Demo API cap reached!")
                return False
        return True

    def _rate_limit_check(self) -> None:
        """Enforce minimum interval between API requests."""
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            self.logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    async def _rate_limit_check_async(self) -> None:
        """Async version of rate limit check."""
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            self.logger.debug(f"Rate limiting (async): sleeping {sleep_time:.2f}s")
            await asyncio.sleep(sleep_time)
        self.last_request_time = time.time()

    def _rotate_key_if_needed(self) -> None:
        """
        Rotate to next available API key if current is exhausted.
        """
        if self.api_key_manager:
            next_key = self.api_key_manager.get_most_available_key()
            if next_key and next_key != self.api_key:
                self.logger.info(f"API key rotated: ...{self.api_key[-8:]} -> ...{next_key[-8:]}")
                self.api_key = next_key
                self.calls_made = self.api_key_manager.calls_made.get(self.api_key, 0)
            if not next_key:
                self.logger.error("No available API keys with quota left!")
                self._alert_dashboard("No API keys available!")

    def _alert_dashboard(self, error_msg: str) -> None:
        """
        Send alert to dashboard if callback is configured.
        
        Args:
            error_msg: Error message to send
        """
        if self.dashboard_callback:
            try:
                self.dashboard_callback(error_msg)
            except Exception as e:
                self.logger.error(f"Dashboard callback error: {e}")

    def _request(self, url: str, params: Dict[str, Any], retries: int = 3, backoff: int = 8) -> List[Dict]:
        """
        Make synchronous HTTP request with retry logic and key rotation.
        
        Args:
            url: API endpoint URL
            params: Query parameters
            retries: Number of retry attempts
            backoff: Backoff time in seconds between retries
            
        Returns:
            List of dictionaries from API response
        """
        for attempt in range(retries):
            self._rotate_key_if_needed()
            if not self._can_make_api_call():
                return []
            
            if self.api_key_manager and self.api_key_manager.calls_made.get(self.api_key, 0) >= self.api_key_manager.max_calls:
                msg = f"API key ...{self.api_key[-8:]} quota reached: {self.api_key_manager.calls_made[self.api_key]}/{self.api_key_manager.max_calls}"
                self.logger.warning(msg)
                self._alert_dashboard(msg)
                continue
            
            self._rate_limit_check()
            
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=10)
                self.calls_made += 1
                if self.api_key_manager:
                    self.api_key_manager.record_usage(self.api_key)
                
                response.raise_for_status()
                self.logger.debug(f"API request successful: {url}")
                return response.json()
            
            except requests.exceptions.HTTPError as err:
                status_code = err.response.status_code if err.response else "N/A"
                msg = f"HTTP error (attempt {attempt+1}/{retries}) [{status_code}]: {err}"
                self.logger.error(msg)
                self._alert_dashboard(msg)
                
                if status_code == 429:  # Rate limit
                    self.logger.warning("Rate limit hit, extending backoff")
                    time.sleep(backoff * 2)
                elif status_code in [401, 403]:  # Auth errors
                    self.logger.error("Authentication error - check API key")
                    return []
                elif attempt < retries - 1:
                    time.sleep(backoff)
            
            except requests.exceptions.RequestException as err:
                msg = f"Request error (attempt {attempt+1}/{retries}): {err}"
                self.logger.error(msg)
                self._alert_dashboard(msg)
                if attempt < retries - 1:
                    time.sleep(backoff)
        
        self.logger.error(f"All retry attempts failed for {url}")
        return []

    async def _request_async(self, url: str, params: Dict[str, Any], retries: int = 3, backoff: int = 8) -> List[Dict]:
        """
        Make asynchronous HTTP request with retry logic and key rotation.
        
        Args:
            url: API endpoint URL
            params: Query parameters
            retries: Number of retry attempts
            backoff: Backoff time in seconds between retries
            
        Returns:
            List of dictionaries from API response
        """
        if aiohttp is None:
            msg = "aiohttp not installed -- async support unavailable."
            self.logger.error(msg)
            self._alert_dashboard(msg)
            return []
        
        timeout = aiohttp.ClientTimeout(total=10)
        
        for attempt in range(retries):
            self._rotate_key_if_needed()
            if not self._can_make_api_call():
                return []
            
            if self.api_key_manager and self.api_key_manager.calls_made.get(self.api_key, 0) >= self.api_key_manager.max_calls:
                msg = f"API key ...{self.api_key[-8:]} quota reached: {self.api_key_manager.calls_made[self.api_key]}/{self.api_key_manager.max_calls}"
                self.logger.warning(msg)
                self._alert_dashboard(msg)
                continue
            
            await self._rate_limit_check_async()
            
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=self.headers, params=params) as response:
                        self.calls_made += 1
                        if self.api_key_manager:
                            self.api_key_manager.record_usage(self.api_key)
                        
                        if response.status == 429:
                            self.logger.warning("Rate limit hit (async), extending backoff")
                            await asyncio.sleep(backoff * 2)
                            continue
                        
                        if response.status not in [200, 201]:
                            raise Exception(f"API error (status: {response.status})")
                        
                        result = await response.json()
                        self.logger.debug(f"API request successful (async): {url}")
                        return result
            
            except Exception as err:
                msg = f"[Async] Request error (attempt {attempt+1}/{retries}): {err}"
                self.logger.error(msg)
                self._alert_dashboard(msg)
                if attempt < retries - 1:
                    await asyncio.sleep(backoff)
        
        self.logger.error(f"All retry attempts failed (async) for {url}")
        return []

    def fetch_sports(self, retries: int = 3, backoff: int = 8, active_only: bool = True) -> List[str]:
        """
        Fetch list of available sports.
        
        Args:
            retries: Number of retry attempts
            backoff: Backoff time between retries
            active_only: Only return active sports
            
        Returns:
            List of sport keys
        """
        url = self.base_url
        params = {"apiKey": self.api_key}
        sports_data = self._request(url, params, retries, backoff)
        
        if not isinstance(sports_data, list):
            msg = "Malformed sports data returned by API."
            self.logger.error(msg)
            self._alert_dashboard(msg)
            return []
        
        result = []
        for sport in sports_data:
            if active_only and not sport.get('active'):
                continue
            result.append(sport['key'])
        
        self.logger.info(f"Fetched {len(result)} sports")
        return result

    async def fetch_sports_async(self, retries: int = 3, backoff: int = 8, active_only: bool = True) -> List[str]:
        """
        Asynchronously fetch list of available sports.
        
        Args:
            retries: Number of retry attempts
            backoff: Backoff time between retries
            active_only: Only return active sports
            
        Returns:
            List of sport keys
        """
        url = self.base_url
        params = {"apiKey": self.api_key}
        sports_data = await self._request_async(url, params, retries, backoff)
        
        if not isinstance(sports_data, list):
            msg = "Malformed sports data returned by API (async)."
            self.logger.error(msg)
            self._alert_dashboard(msg)
            return []
        
        result = []
        for sport in sports_data:
            if active_only and not sport.get('active'):
                continue
            result.append(sport['key'])
        
        self.logger.info(f"Fetched {len(result)} sports (async)")
        return result

    def fetch_odds(
        self, 
        sport: str, 
        regions: Optional[str] = None, 
        markets: Any = None, 
        bookmakers: Optional[str] = None,
        retries: int = 3, 
        backoff: int = 8, 
        event_window_hours: Optional[int] = None
    ) -> List[Dict]:
        """
        Fetch odds data for a specific sport.
        
        Args:
            sport: Sport key (e.g., 'basketball_nba')
            regions: Regions to fetch (e.g., 'us,uk')
            markets: Markets to fetch (e.g., 'h2h,spreads')
            bookmakers: Specific bookmakers to fetch
            retries: Number of retry attempts
            backoff: Backoff time between retries
            event_window_hours: Filter events within N hours
            
        Returns:
            List of game dictionaries with odds data
        """
        endpoint = f"{self.base_url.rstrip('/')}/{sport}/odds"
        markets_str = ",".join(markets) if isinstance(markets, list) else str(markets or "h2h")
        
        params = {
            "apiKey": self.api_key,
            "markets": markets_str,
            "oddsFormat": "decimal"
        }
        
        if bookmakers:
            params["bookmakers"] = bookmakers
            log_label = bookmakers
        elif regions:
            params["regions"] = regions
            log_label = regions
        else:
            params["regions"] = "us"
            log_label = "us"
        
        data = self._request(endpoint, params, retries, backoff)
        
        if not isinstance(data, list):
            msg = f"Malformed odds data returned for sport {sport}."
            self.logger.error(msg)
            self._alert_dashboard(msg)
            return []
        
        # Event window filtering
        event_window = event_window_hours or int(os.getenv("EVENT_WINDOW_HOURS", "6"))
        now = time.time()
        filtered = [
            game for game in data
            if (
                "commence_time" in game
                and self._parse_commence_time(game["commence_time"]) <= now + 3600 * event_window
            )
        ]
        
        self.logger.info(f"Fetched {len(filtered)}/{len(data)} odds results for {sport} [{log_label} | {markets_str}] in event_window_hours={event_window}")
        return filtered

    async def fetch_odds_async(
        self, 
        sport: str, 
        regions: Optional[str] = None, 
        markets: Any = None, 
        bookmakers: Optional[str] = None,
        retries: int = 3, 
        backoff: int = 8, 
        event_window_hours: Optional[int] = None
    ) -> List[Dict]:
        """
        Asynchronously fetch odds data for a specific sport.
        
        Args:
            sport: Sport key (e.g., 'basketball_nba')
            regions: Regions to fetch (e.g., 'us,uk')
            markets: Markets to fetch (e.g., 'h2h,spreads')
            bookmakers: Specific bookmakers to fetch
            retries: Number of retry attempts
            backoff: Backoff time between retries
            event_window_hours: Filter events within N hours
            
        Returns:
            List of game dictionaries with odds data
        """
        endpoint = f"{self.base_url.rstrip('/')}/{sport}/odds"
        markets_str = ",".join(markets) if isinstance(markets, list) else str(markets or "h2h")
        
        params = {
            "apiKey": self.api_key,
            "markets": markets_str,
            "oddsFormat": "decimal"
        }
        
        if bookmakers:
            params["bookmakers"] = bookmakers
            log_label = bookmakers
        elif regions:
            params["regions"] = regions
            log_label = regions
        else:
            params["regions"] = "us"
            log_label = "us"
        
        data = await self._request_async(endpoint, params, retries, backoff)
        
        if not isinstance(data, list):
            msg = f"[Async] Malformed odds data for {sport}."
            self.logger.error(msg)
            self._alert_dashboard(msg)
            return []
        
        # Event window filtering
        event_window = event_window_hours or int(os.getenv("EVENT_WINDOW_HOURS", "6"))
        now = time.time()
        filtered = [
            game for game in data
            if (
                "commence_time" in game
                and self._parse_commence_time(game["commence_time"]) <= now + 3600 * event_window
            )
        ]
        
        self.logger.info(f"[Async] Fetched {len(filtered)}/{len(data)} odds results for {sport} [{log_label} | {markets_str}] in event_window_hours={event_window}")
        return filtered

    def _parse_commence_time(self, commence_time: Any) -> float:
        """
        Parse commence_time field to timestamp.
        
        Args:
            commence_time: String or numeric timestamp
            
        Returns:
            Unix timestamp as float
        """
        try:
            if isinstance(commence_time, (int, float)):
                return float(commence_time)
            # Try parsing ISO format string
            dt = datetime.fromisoformat(commence_time.replace('Z', '+00:00'))
            return dt.timestamp()
        except Exception as e:
            self.logger.warning(f"Could not parse commence_time: {commence_time} - {e}")
            return 0.0

    def parse_odds_response(self, raw_odds: List[Dict]) -> List[Dict]:
        """
        Parse and validate raw odds data using jsonschema if available.
        
        Args:
            raw_odds: Raw odds data from API
            
        Returns:
            List of validated and parsed game dictionaries
        """
        games = []
        keys_required = {"id", "home_team", "away_team", "commence_time", "bookmakers"}
        game_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "home_team": {"type": "string"},
                "away_team": {"type": "string"},
                "commence_time": {"type": ["string", "number"]},
                "bookmakers": {"type": "array"},
            },
            "required": ["id", "home_team", "away_team", "commence_time", "bookmakers"]
        }
        
        try:
            for event in raw_odds:
                # Schema validation if jsonschema available
                if jsonschema is not None:
                    try:
                        jsonschema.validate(event, game_schema)
                    except Exception as ve:
                        self.logger.error(f"Odds schema validation error: {ve}")
                        continue
                else:
                    # Manual validation
                    if not all(k in event for k in keys_required):
                        self.logger.warning(f"Skipped malformed event: {event}")
                        continue
                
                game = {
                    "id": event["id"],
                    "home_team": event["home_team"],
                    "away_team": event["away_team"],
                    "commence_time": event["commence_time"],
                    "bookmakers": []
                }
                
                for bookmaker in event.get("bookmakers", []):
                    book_keys = {"key", "markets"}
                    if not all(bk in bookmaker for bk in book_keys):
                        self.logger.warning(f"Malformed bookmaker block: {bookmaker}")
                        continue
                    
                    bookmaker_entry = {
                        "key": bookmaker["key"],
                        "markets": []
                    }
                    
                    for market in bookmaker.get("markets", []):
                        market_keys = {"key", "outcomes"}
                        if not all(mk in market for mk in market_keys):
                            self.logger.warning(f"Malformed market block: {market}")
                            continue
                        
                        market_entry = {
                            "key": market["key"],
                            "outcomes": market.get("outcomes", [])
                        }
                        bookmaker_entry["markets"].append(market_entry)
                    
                    game["bookmakers"].append(bookmaker_entry)
                
                games.append(game)
            
            self.logger.info(f"Parsed {len(games)}/{len(raw_odds)} games from odds data")
        
        except Exception as err:
            self.logger.error(f"Error parsing odds data: {err}")
        
        return games

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about data collector usage.
        
        Returns:
            Dictionary with collector statistics
        """
        return {
            "calls_made": self.calls_made,
            "current_key": f"...{self.api_key[-8:]}",
            "manager_total_calls": self.api_key_manager.total_calls if self.api_key_manager else 0,
            "manager_demo_phase": self.api_key_manager.demo_phase_enabled if self.api_key_manager else False
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"OddsDataCollector(key=...{self.api_key[-8:]}, "
            f"calls={self.calls_made}, "
            f"base_url={self.base_url})"
        )
