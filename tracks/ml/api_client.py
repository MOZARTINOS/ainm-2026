"""
Astar Island API Client
NM i AI 2026 — Norse World Prediction
"""
import requests
import time
from typing import Optional


class AstarClient:
    """Client for Astar Island competition API."""

    BASE_URL = "https://api.ainm.no/astar-island"

    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        })
        self._last_request_time = 0
        self._min_interval = 0.25  # 4 req/sec max (safe margin)

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def get_rounds(self) -> list:
        """GET /rounds — list all rounds with status."""
        self._throttle()
        r = self.session.get(f"{self.BASE_URL}/rounds")
        r.raise_for_status()
        return r.json()

    def get_round(self, round_id: str) -> dict:
        """GET /rounds/{round_id} — round details with initial map states."""
        self._throttle()
        r = self.session.get(f"{self.BASE_URL}/rounds/{round_id}")
        r.raise_for_status()
        return r.json()

    def get_budget(self) -> dict:
        """GET /budget — remaining query allocation."""
        self._throttle()
        r = self.session.get(f"{self.BASE_URL}/budget")
        r.raise_for_status()
        return r.json()

    def simulate(self, round_id: str, seed_index: int,
                 viewport_x: int, viewport_y: int,
                 viewport_w: int = 15, viewport_h: int = 15) -> dict:
        """POST /simulate — observe a viewport. Costs 1 query."""
        self._throttle()
        payload = {
            "round_id": round_id,
            "seed_index": seed_index,
            "viewport_x": viewport_x,
            "viewport_y": viewport_y,
            "viewport_w": min(viewport_w, 15),
            "viewport_h": min(viewport_h, 15)
        }
        r = self.session.post(f"{self.BASE_URL}/simulate", json=payload)
        r.raise_for_status()
        return r.json()

    def submit(self, round_id: str, seed_index: int,
               prediction: list) -> dict:
        """POST /submit — submit prediction tensor [y][x][6]."""
        self._throttle()
        payload = {
            "round_id": round_id,
            "seed_index": seed_index,
            "prediction": prediction
        }
        r = self.session.post(f"{self.BASE_URL}/submit", json=payload)
        r.raise_for_status()
        return r.json()

    def get_my_rounds(self) -> list:
        """GET /my-rounds — team rounds with scores."""
        self._throttle()
        r = self.session.get(f"{self.BASE_URL}/my-rounds")
        r.raise_for_status()
        return r.json()

    def get_analysis(self, round_id: str, seed_index: int) -> dict:
        """GET /analysis/{round_id}/{seed_index} — post-round comparison."""
        self._throttle()
        r = self.session.get(
            f"{self.BASE_URL}/analysis/{round_id}/{seed_index}")
        r.raise_for_status()
        return r.json()

    def get_leaderboard(self) -> list:
        """GET /leaderboard — public standings."""
        self._throttle()
        r = self.session.get(f"{self.BASE_URL}/leaderboard")
        r.raise_for_status()
        return r.json()
