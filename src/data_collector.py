import requests
import logging
import os
import time
from typing import List, Dict, Any

class OddsDataCollector:
    def __init__(self, api_key: str, max_calls: int = 500, base_url: str = None):
        self.api_key = api_key
        self.calls_made = 0
        self.max_calls = max_calls
        self.base_url = base_url or os.getenv("ODDS_API_BASE_URL", "https://api.the-odds-api.com/v4/sports")
        self.headers = {"Accept": "application/json"}

    def _request(self, url: str, params: Dict[str, Any], retries: int = 3, backoff: int = 8) -> List[Dict]:
        for attempt in range(retries):
            if self.calls_made >= self.max_calls:
                logging.warning(f"API call limit reached: {self.calls_made}/{self.max_calls}")
                return []
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=10)
                self.calls_made += 1
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as err:
                logging.error(f"API error (attempt {attempt+1}): {err}")
                if attempt < retries - 1:
                    time.sleep(backoff)
        return []

    def fetch_sports(self, retries: int = 3, backoff: int = 8) -> List[str]:
        """Retrieve active sports from the API (doesn't use quota)."""
        url = self.base_url  # No trailing slash for endpoint
        params = {"apiKey": self.api_key}
        sports_data = self._request(url, params, retries, backoff)
        if not isinstance(sports_data, list):
            logging.error("Malformed sports data returned by API.")
            return []
        # Only return active sports' keys for in-season coverage
        return [sport['key'] for sport in sports_data if sport.get('active')]

    def fetch_odds(self, sport: str, regions: str = "us", markets: str = "h2h", retries: int = 3, backoff: int = 8) -> List[Dict]:
        """Fetch odds data for a given sport, regions, and markets."""
        endpoint = f"{self.base_url.rstrip('/')}/{sport}/odds"
        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal"
        }
        data = self._request(endpoint, params, retries, backoff)
        if not isinstance(data, list):
            logging.error(f"Malformed odds data returned for sport {sport}.")
            return []
        logging.info(f"Fetched {len(data)} odds results for {sport} [{regions} | {markets}]")
        return data

    def parse_odds_response(self, raw_odds: List[Dict]) -> List[Dict]:
        """Parse the raw odds data into a list of games with schema validation."""
        games = []
        keys_required = {"id", "home_team", "away_team", "commence_time", "bookmakers"}
        try:
            for event in raw_odds:
                if not all(k in event for k in keys_required):
                    logging.warning(f"Skipped malformed event: {event}")
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
                        logging.warning(f"Malformed bookmaker block: {bookmaker}")
                        continue
                    bookmaker_entry = {
                        "key": bookmaker["key"],
                        "markets": []
                    }
                    for market in bookmaker.get("markets", []):
                        market_keys = {"key", "outcomes"}
                        if not all(mk in market for mk in market_keys):
                            logging.warning(f"Malformed market block: {market}")
                            continue
                        market_entry = {
                            "key": market["key"],
                            "outcomes": market.get("outcomes", [])
                        }
                        bookmaker_entry["markets"].append(market_entry)
                    game["bookmakers"].append(bookmaker_entry)
                games.append(game)
            logging.info(f"Parsed {len(games)} games from odds data.")
        except Exception as err:
            logging.error(f"Error parsing odds data: {err}")
        return games
