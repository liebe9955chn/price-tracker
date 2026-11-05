"""把 data/history.csv 整理成走勢圖網頁要用的 docs/data.json。"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

# 走勢圖上固定顯示的網站順序（顏色跟著網站走，不會因為排名改變）
SITE_ORDER = ["PChome 24h", "momo", "Yahoo購物中心", "Yahoo拍賣", "蝦皮", "iOPEN Mall", "露天拍賣", "旋轉拍賣"]
OTHER = "其他"


def build_report(products: list[dict], root: Path) -> None:
    history = root / "data" / "history.csv"
    latest = json.loads((root / "data" / "latest.json").read_text(encoding="utf-8"))
    state = json.loads((root / "data" / "state.json").read_text(encoding="utf-8"))

    rows = defaultdict(lambda: defaultdict(dict))  # product -> time -> site -> price
    if history.exists():
        with history.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                site = r["site"] if r["site"] in SITE_ORDER else OTHER
                t, p = r["time"], int(r["price"])
                cur = rows[r["product"]][t].get(site)
                if cur is None or p < cur:
                    rows[r["product"]][t][site] = p

    out = {"updated": latest.get("time"), "sites": SITE_ORDER + [OTHER], "products": []}
    for idx, p in enumerate(products):
        name = p["name"]
        times = sorted(rows[name].keys())
        series = {}
        for site in SITE_ORDER + [OTHER]:
            vals = [rows[name][t].get(site) for t in times]
            if any(v is not None for v in vals):
                series[site] = vals
        overall = [min(rows[name][t].values()) if rows[name][t] else None for t in times]
        ps = state.get("products", {}).get(name, {})
        out["products"].append({
            "id": f"p{idx}",
            "name": name,
            "original_price": p.get("original_price"),
            "target_price": p.get("target_price"),
            "category": p.get("category"),
            "rule": p.get("rule"),
            "tiers": [{"price": int(p["original_price"] * float(t["ratio"])), "label": t["label"],
                       "ratio": t["ratio"]} for t in (p.get("tiers") or [])] if p.get("original_price") else [],
            "baseline": ps.get("baseline"),
            "lowest": ps.get("lowest"),
            "lowest_at": ps.get("lowest_at"),
            "lowest_site": ps.get("lowest_site"),
            "times": times,
            "overall": overall,
            "series": series,
            "listings": latest.get("products", {}).get(name, []),
        })

    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "data.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
