"""Runs every POC check against the datasets and scores them against the brief's pass bars."""
import csv
import json
import statistics
from datetime import datetime
from pathlib import Path

from .llm import clean_transcript, llm_configured
from .nutritionix import NutritionixClient, NutritionixError

DATA_DIR = Path(__file__).parent / "data"
RESULTS_DIR = Path(__file__).parent / "results"
LATEST = RESULTS_DIR / "latest.json"

PASS_BARS = {
    "nl_parsing": 90.0,
    "calorie_accuracy": 85.0,
    "search_relevance": 90.0,
    "barcode_hit_rate": 80.0,
    "latency_p95_ms": 1500.0,
}


def load(name):
    return json.loads((DATA_DIR / name).read_text())


def matches(alternatives, text):
    text = (text or "").lower()
    return any(a.strip().lower() in text for a in alternatives.split("|"))


def items_captured(expected_items, foods):
    names = [f.get("food_name", "") for f in foods]
    missing = [e for e in expected_items if not any(matches(e, n) for n in names)]
    return missing


def summarize_food(f):
    return {
        "name": f.get("food_name"),
        "brand": f.get("brand_name"),
        "qty": f.get("serving_qty"),
        "unit": f.get("serving_unit"),
        "grams": f.get("serving_weight_grams"),
        "kcal": f.get("nf_calories"),
        "protein": f.get("nf_protein"),
        "carbs": f.get("nf_total_carbohydrate"),
        "fat": f.get("nf_total_fat"),
    }


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def p95(values):
    if not values:
        return None
    if len(values) < 2:
        return values[0]
    return round(statistics.quantiles(values, n=20, method="inclusive")[18], 1)


def run_nl(client, out):
    micros = {}
    for meal in load("meals.json")["meals"]:
        try:
            foods, ms = client.natural_nutrients(meal["text"])
        except NutritionixError as e:
            out["errors"].append(f"{meal['id']}: {e}")
            foods, ms = [], None
        missing = items_captured(meal["expected_items"], foods)
        out["nl"].append({
            "id": meal["id"], "text": meal["text"], "ms": ms and round(ms),
            "parsed_all": not missing, "missing": missing,
            "foods": [summarize_food(f) for f in foods],
        })
        for ref in meal["reference"]:
            hit = next((f for f in foods if matches(ref["match"], f.get("food_name"))), None)
            kcal = hit.get("nf_calories") if hit else None
            diff = round(100.0 * (kcal - ref["kcal"]) / ref["kcal"], 1) if kcal is not None else None
            out["calories"].append({
                "id": meal["id"], "item": ref["match"], "nutritionix_kcal": kcal and round(kcal),
                "reference_kcal": ref["kcal"], "source": ref["source"],
                "portion": hit and f"{hit.get('serving_qty')} {hit.get('serving_unit')} ({hit.get('serving_weight_grams')} g)",
                "diff_pct": diff, "within_10": diff is not None and abs(diff) <= 10,
            })
        for f in foods:
            for n in f.get("full_nutrients", []):
                micros[n["attr_id"]] = micros.get(n["attr_id"], 0) + 1
    return micros


def run_search(client, out):
    for q in load("search_queries.json")["queries"]:
        try:
            common, branded, ms = client.search_instant(q["query"])
        except NutritionixError as e:
            out["errors"].append(f"search '{q['query']}': {e}")
            common, branded, ms = [], [], None
        top_c = [c.get("food_name") for c in common[:5]]
        top_b = [f"{b.get('brand_name')} — {b.get('food_name')}" for b in branded[:5]]
        out["search"].append({
            "query": q["query"], "kind": q["kind"], "expected": q["expected"], "ms": ms and round(ms),
            "top_common": top_c, "top_branded": top_b,
            "hit": any(matches(q["expected"], n) for n in top_c + top_b),
        })


def run_upc(client, out):
    for row in load("upcs.json")["upcs"]:
        if not row.get("upc"):
            continue
        try:
            food, ms = client.search_upc(row["upc"])
        except NutritionixError as e:
            out["errors"].append(f"upc {row['upc']}: {e}")
            food, ms = None, None
        kcal = food.get("nf_calories") if food else None
        label = row.get("label_kcal")
        out["upc"].append({
            "name": row["name"], "upc": row["upc"], "ms": ms and round(ms), "found": food is not None,
            "returned": food and f"{food.get('brand_name')} — {food.get('food_name')}",
            "nutritionix_kcal": kcal, "label_kcal": label,
            "label_match": (kcal is not None and label) and abs(kcal - label) <= max(5, 0.05 * label),
        })


def run_voice(client, out):
    use_llm = llm_configured()
    for t in load("voice_transcripts.json")["transcripts"]:
        row = {"id": t["id"], "raw": t["text"]}
        try:
            foods, _ = client.natural_nutrients(t["text"])
        except NutritionixError as e:
            out["errors"].append(f"{t['id']} raw: {e}")
            foods = []
        row["raw_missing"] = items_captured(t["expected_items"], foods)
        row["raw_foods"] = [f.get("food_name") for f in foods]
        row["cleaned"] = row["clean_missing"] = row["clean_foods"] = None
        if use_llm:
            try:
                row["cleaned"] = clean_transcript(t["text"])
                foods, _ = client.natural_nutrients(row["cleaned"])
                row["clean_missing"] = items_captured(t["expected_items"], foods)
                row["clean_foods"] = [f.get("food_name") for f in foods]
            except Exception as e:  # noqa: BLE001 — surface any LLM/API failure in the sheet
                out["errors"].append(f"{t['id']} cleanup: {e}")
        out["voice"].append(row)


def run_all():
    client = NutritionixClient()
    out = {"run_at": datetime.now().isoformat(timespec="seconds"), "errors": [],
           "nl": [], "calories": [], "search": [], "upc": [], "voice": []}

    micros = run_nl(client, out)
    run_search(client, out)
    run_upc(client, out)
    run_voice(client, out)

    try:
        catalog = client.nutrient_catalog()
    except NutritionixError as e:
        out["errors"].append(f"nutrient catalog: {e}")
        catalog = {}
    out["micronutrients"] = sorted(
        [{"attr_id": a, "name": catalog.get(a, {}).get("name", "?"), "unit": catalog.get(a, {}).get("unit", ""),
          "foods_with_value": c} for a, c in micros.items()],
        key=lambda r: r["attr_id"],
    )

    by_endpoint = {}
    for c in client.calls:
        by_endpoint.setdefault(c["endpoint"], []).append(c["ms"])
    out["latency"] = [
        {"endpoint": ep, "calls": len(v), "p50_ms": round(statistics.median(v), 1), "p95_ms": p95(v), "max_ms": max(v)}
        for ep, v in by_endpoint.items()
    ]
    out["rate_limit_headers"] = client.rate_limit_headers

    all_ms = [c["ms"] for c in client.calls]
    nl_rate = pct(sum(r["parsed_all"] for r in out["nl"]), len(out["nl"]))
    cal_rate = pct(sum(r["within_10"] for r in out["calories"]), len(out["calories"]))
    search_rate = pct(sum(r["hit"] for r in out["search"]), len(out["search"]))
    upc_rate = pct(sum(r["found"] for r in out["upc"]), len(out["upc"]))
    lat = p95(all_ms)
    voice_raw = sum(not r["raw_missing"] for r in out["voice"])
    voice_clean = sum(r["clean_missing"] == [] for r in out["voice"])

    def row(check, value, bar, passed, unit="%"):
        return {"check": check, "value": value, "unit": unit, "bar": bar,
                "status": "N/A" if value is None or passed is None else ("PASS" if passed else "FAIL")}

    out["summary"] = [
        row("NL parsing (all items captured)", nl_rate, "≥ 90%", nl_rate is not None and nl_rate >= PASS_BARS["nl_parsing"]),
        row("Calorie accuracy (±10% of reference)", cal_rate, "≥ 85%", cal_rate is not None and cal_rate >= PASS_BARS["calorie_accuracy"]),
        row("Search relevance (intended food in top-5)", search_rate, "≥ 90%", search_rate is not None and search_rate >= PASS_BARS["search_relevance"]),
        row("Barcode hit rate", upc_rate, "≥ 80%", upc_rate is not None and upc_rate >= PASS_BARS["barcode_hit_rate"]),
        row("Latency p95 (all calls)", lat, "< 1500 ms", lat is not None and lat < PASS_BARS["latency_p95_ms"], unit="ms"),
        row("Voice: parsed raw → after LLM cleanup", f"{voice_raw}/{len(out['voice'])} → "
            + (f"{voice_clean}/{len(out['voice'])}" if use_llm_ran(out) else "LLM not configured"),
            "cleanup improves parsing", None, unit=""),
        row("Micronutrients returned (distinct attr_ids)", len(out["micronutrients"]), "confirm vs clinical list", None, unit=""),
    ]

    RESULTS_DIR.mkdir(exist_ok=True)
    LATEST.write_text(json.dumps(out, indent=2))
    write_csv(out)
    return out


def use_llm_ran(out):
    return any(r["cleaned"] is not None for r in out["voice"])


def write_csv(out):
    path = RESULTS_DIR / "results_sheet.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Nutritionix POC results", out["run_at"]])
        w.writerow([])
        w.writerow(["Check", "Value", "Unit", "Pass bar", "Status"])
        for r in out["summary"]:
            w.writerow([r["check"], r["value"], r["unit"], r["bar"], r["status"]])
        w.writerow([])
        w.writerow(["Calorie accuracy detail"])
        w.writerow(["Meal", "Item", "Nutritionix kcal", "Reference kcal", "Diff %", "Portion", "Source"])
        for r in out["calories"]:
            w.writerow([r["id"], r["item"], r["nutritionix_kcal"], r["reference_kcal"], r["diff_pct"], r["portion"], r["source"]])
        w.writerow([])
        w.writerow(["Latency"])
        w.writerow(["Endpoint", "Calls", "p50 ms", "p95 ms", "max ms"])
        for r in out["latency"]:
            w.writerow([r["endpoint"], r["calls"], r["p50_ms"], r["p95_ms"], r["max_ms"]])


def load_latest():
    return json.loads(LATEST.read_text()) if LATEST.exists() else None
