import time
import threading
import logging
import requests
from collections import defaultdict

logger = logging.getLogger("GOAL_ENGINE_PRO")

class IntelligentRateLimiter:
    def __init__(self):
        self.last_call = 0
        self.mode = "NORMAL"  # NORMAL / LOW
        self.base_interval = 5
        self.low_interval = 15

    def set_mode(self, mode):
        self.mode = mode

    def wait(self):
        interval = self.low_interval if self.mode == "LOW" else self.base_interval
        now = time.time()
        elapsed = now - self.last_call
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self.last_call = time.time()

class APIFootballClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://v3.football.api-sports.io/fixtures"
        self.failures = 0
        self.circuit_open_until = 0

    def is_available(self):
        return time.time() > self.circuit_open_until

    def fetch_live(self):
        if not self.is_available():
            raise RuntimeError("API circuit open")

        headers = {"x-apisports-key": self.api_key}
        params = {"live": "all"}

        try:
            resp = requests.get(self.base_url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            self.failures = 0
            return resp.json()
        except Exception as e:
            self.failures += 1
            logger.error("API Football error: %s", e)

            if self.failures >= 3:
                self.circuit_open_until = time.time() + 60
                logger.error("API Football circuit OPEN 60s")

            raise

class GoalEnginePro:
    def __init__(
        self,
        api_client,
        betfair_stream,
        hedge_callback,
        reopen_callback,
        ui_queue,
    ):
        self.api = api_client
        self.stream = betfair_stream
        self.hedge_callback = hedge_callback
        self.reopen_callback = reopen_callback
        self.uiq = ui_queue

        self.rate_limiter = IntelligentRateLimiter()
        self.running = False

        self.goal_cache = defaultdict(int)
        self.confirm_cache = {}   # match_id -> timestamp first detect
        self.hedged_matches = set()

        self.confirm_mode = False
        self.hedge_delay_ms = 0

    def set_delay(self, mode: str):
        if mode == "0ms":
            self.hedge_delay_ms = 0
        elif mode == "500ms":
            self.hedge_delay_ms = 0.5
        elif mode == "2s":
            self.hedge_delay_ms = 2
        else:
            self.hedge_delay_ms = 0

    def set_confirm_mode(self, enabled: bool):
        self.confirm_mode = enabled
        
    def set_low_request_mode(self, enabled: bool):
        self.rate_limiter.set_mode("LOW" if enabled else "NORMAL")

    def start(self):
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()
        logger.info("GoalEnginePro started")

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            try:
                self.rate_limiter.wait()
                if not self.api.is_available():
                    logger.warning("API down - fallback mode active")
                    continue
                data = self.api.fetch_live()
                self._process_api(data)
            except Exception as e:
                logger.error("GoalEnginePro loop error: %s", e)
                
            # Check async stream confirmations if confirm mode is on
            if self.confirm_mode:
                self.check_stream_confirmation()

    def _process_api(self, data):
        fixtures = data.get("response", [])

        for fixture in fixtures:
            match_id = fixture["fixture"]["id"]
            goals_home = fixture["goals"]["home"] or 0
            goals_away = fixture["goals"]["away"] or 0
            total_goals = goals_home + goals_away

            prev_goals = self.goal_cache[match_id]

            # 🛑 VAR annulled detection
            if total_goals < prev_goals:
                logger.info(f"VAR detected match={match_id}")
                self.goal_cache[match_id] = total_goals
                self.hedged_matches.discard(match_id)
                threading.Thread(
                    target=self.reopen_callback,
                    args=(match_id,),
                    daemon=True
                ).start()
                return

            # NEW GOAL
            if total_goals > prev_goals:
                self.goal_cache[match_id] = total_goals
                logger.info(f"GOAL detected API match={match_id}")

                if self.confirm_mode:
                    self.confirm_cache[match_id] = time.time()
                else:
                    self._verify_and_hedge(match_id)

    def _verify_and_hedge(self, match_id):
        if match_id in self.hedged_matches:
            return

        # ⚽ Sync with Betfair stream
        if not self._verify_with_stream(match_id):
            logger.warning(f"Goal NOT confirmed by stream {match_id}")
            return

        # Delay hedge configurabile
        if self.hedge_delay_ms > 0:
            time.sleep(self.hedge_delay_ms)

        self.hedged_matches.add(match_id)

        threading.Thread(
            target=self.hedge_callback,
            args=(match_id,),
            daemon=True
        ).start()

        self.uiq.post(
            logger.info,
            f"[UI] Hedge triggered for {match_id}"
        )

    def check_stream_confirmation(self):
        now = time.time()
        for match_id, ts in list(self.confirm_cache.items()):
            if now - ts > 2:  # 2 sec timeout
                self._verify_and_hedge(match_id)
                del self.confirm_cache[match_id]

    def _verify_with_stream(self, match_id):
        """
        Verifica movimenti quota e sospensione.
        """
        if not self.stream: 
            return True # Fallback se stream assente
            
        market = self.stream.get_market_cache(str(match_id))
        if not market:
            return False

        if market.get("status") == "SUSPENDED":
            return True

        return True