"""Thin Nutritionix v2 client that records latency and rate-limit headers per call."""
import os
import time

import requests

BASE_URL = "https://trackapi.nutritionix.com/v2"
TIMEOUT = 15


class NutritionixError(Exception):
    pass


class NutritionixClient:
    def __init__(self):
        self.app_id = os.getenv("NUTRITIONIX_APP_ID", "")
        self.app_key = os.getenv("NUTRITIONIX_APP_KEY", "")
        self.calls = []  # [{endpoint, ms, status}]
        self.rate_limit_headers = {}

    @property
    def configured(self):
        return bool(self.app_id and self.app_key)

    def _request(self, method, path, **kwargs):
        if not self.configured:
            raise NutritionixError("NUTRITIONIX_APP_ID / NUTRITIONIX_APP_KEY not set in .env")
        headers = {
            "x-app-id": self.app_id,
            "x-app-key": self.app_key,
            "x-remote-user-id": "0",
        }
        start = time.perf_counter()
        resp = requests.request(method, BASE_URL + path, headers=headers, timeout=TIMEOUT, **kwargs)
        ms = (time.perf_counter() - start) * 1000
        self.calls.append({"endpoint": path.split("?")[0], "ms": round(ms, 1), "status": resp.status_code})
        for k, v in resp.headers.items():
            if "limit" in k.lower() or "quota" in k.lower():
                self.rate_limit_headers[k] = v
        if resp.status_code == 404:
            return None, ms
        if resp.status_code >= 400:
            raise NutritionixError(f"{resp.status_code} on {path}: {resp.text[:300]}")
        return resp.json(), ms

    def natural_nutrients(self, query):
        data, ms = self._request("POST", "/natural/nutrients", json={"query": query})
        return (data or {}).get("foods", []), ms

    def search_instant(self, query):
        data, ms = self._request("GET", "/search/instant", params={"query": query, "detailed": "true"})
        data = data or {}
        return data.get("common", []), data.get("branded", []), ms

    def search_upc(self, upc):
        data, ms = self._request("GET", "/search/item", params={"upc": upc})
        foods = (data or {}).get("foods", [])
        return (foods[0] if foods else None), ms

    def nutrient_catalog(self):
        """attr_id -> {name, unit} from /utils/nutrients."""
        data, _ = self._request("GET", "/utils/nutrients")
        return {n["attr_id"]: {"name": n.get("usda_nutr_desc") or n.get("name"), "unit": n.get("unit")} for n in data or []}
