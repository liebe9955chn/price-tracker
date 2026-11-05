"""主程式：抓價格 → 存歷史 → 判斷要不要通知 → 更新走勢圖資料。

執行方式：python -m pricewatch.main
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .filters import match_reason, merge_category, price_ok
from .notify import esc, send_telegram
from .sites import ALL_SITES, Listing, lego_list_price

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "products.yaml"
DATA = ROOT / "data"
HISTORY = DATA / "history.csv"
STATE = DATA / "state.json"
TW = timezone(timedelta(hours=8))
TFMT = "%Y-%m-%d %H:%M"
FAIL_ALERT_AFTER = 3  # 連續失敗幾次才提醒（一天跑 3 次，3 次約 1 天）


def pages_url() -> str:
    if os.environ.get("PAGES_URL"):
        return os.environ["PAGES_URL"].rstrip("/") + "/"
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return ""


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def load_history() -> dict[str, list[tuple[datetime, int]]]:
    """每個商品每次執行的「全部網站最低價」。"""
    per = defaultdict(dict)
    if HISTORY.exists():
        with HISTORY.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                t, p = r["time"], int(r["price"])
                if t not in per[r["product"]] or p < per[r["product"]][t]:
                    per[r["product"]][t] = p
    return {name: sorted((datetime.strptime(t, TFMT).replace(tzinfo=TW), p) for t, p in d.items())
            for name, d in per.items()}


def fetch_all(keywords: list[str], run_ok: dict) -> list[Listing]:
    seen, out = set(), []
    for site_name, fn in ALL_SITES.items():
        ok, err = False, ""
        for kw in keywords:
            try:
                for x in fn(kw):
                    key = (x.site, x.title.strip(), x.price)
                    if key not in seen:
                        seen.add(key)
                        out.append(x)
                ok = True
            except Exception as e:  # 單一網站失敗不影響其他網站
                err = f"{type(e).__name__}: {e}"
                print(f"  [{site_name}] 「{kw}」失敗：{err}")
            time.sleep(1)
        prev_ok, prev_err = run_ok.get(site_name, (False, ""))
        run_ok[site_name] = (prev_ok or ok, err or prev_err)
    return out


def fmt(n) -> str:
    return f"{n:,}"


def zhe(price: int, original: int) -> str:
    """把價格換算成幾折，例如 0.64 → 6.4 折。"""
    z = price / original * 10
    return f"{z:.1f}".rstrip("0").rstrip(".") + " 折"


def tier_level(price: int, original: int | None, tiers: list[dict]) -> int:
    """回傳達到第幾級（-1 代表都沒達到）。tiers 由淺到深排列。"""
    if not original:
        return -1
    level = -1
    for i, t in enumerate(tiers):
        limit = original * float(t["ratio"])
        if price < limit or (t.get("inclusive") and price <= limit):
            level = i
    return level


def build_message(kind: str, p: dict, best: Listing, per_site: dict, extra: list[str], anchor: str) -> str:
    lines = [f"<b>【{esc(kind)}】{esc(p['name'])}</b>",
             f"最低價 <b>{fmt(best.price)}</b> 元（{esc(best.site)}）"]
    lines += [esc(e) for e in extra]
    if best.url:
        lines.append(f'<a href="{esc(best.url)}">前往這個賣場</a>')
    lines.append("")
    lines.append("各網站最低價：")
    for site, x in sorted(per_site.items(), key=lambda kv: kv[1].price):
        lines.append(f'・{esc(site)} <a href="{esc(x.url)}">{fmt(x.price)}</a>')
    url = pages_url()
    if url:
        lines.append("")
        lines.append(f'<a href="{esc(url)}#{esc(anchor)}">查看價格走勢</a>')
    return "\n".join(lines)


def evaluate(p: dict, ps: dict, cur: int, now_dt: datetime, past: list[tuple[datetime, int]]):
    """判斷要不要通知。回傳 (通知標題, 說明文字清單)；不用通知就回傳 (None, [])。"""
    original = p.get("original_price")
    rule = p.get("rule")
    reasons, kind = [], None
    prev_low = ps.get("lowest")
    learning = False

    if rule == "discount":
        tiers = p.get("tiers") or []
        level = tier_level(cur, original, tiers)
        notified = ps.get("tier_notified", -1)
        if level > notified:
            label = tiers[level]["label"]
            kind = label
            t = tiers[level]
            rz = f"{float(t['ratio']) * 10:.1f}".rstrip("0").rstrip(".") + " 折"
            cond = f"{rz}以下" if t.get("inclusive") else f"低於 {rz}"
            reasons.append(f"原價 {fmt(original)} 元，現在 {zhe(cur, original)}（{label}：{cond}）")
        if level != notified:
            ps["tier_notified"] = level  # 價格回升會往回調，之後再降下來會重新通知
    else:
        learn_days = p.get("learn_days", 14)
        window = p.get("window_days", 30)
        drop_pct = float(p.get("drop_pct", 0.15))
        first = past[0][0] if past else now_dt
        learning = (now_dt - first) < timedelta(days=learn_days)
        if not learning:
            recent = [v for t, v in past if t >= now_dt - timedelta(days=window)]
            if recent:
                base = statistics.median(recent)
                ps["baseline"] = base
                hit = cur <= base * (1 - drop_pct)
                if hit and not ps.get("deal_active"):
                    kind = "特價"
                    reasons.append(f"過去 {window} 天一般價格約 {fmt(int(base))} 元，現在便宜 "
                                   f"{round((1 - cur / base) * 100)}%（門檻 {round(drop_pct * 100)}%）")
                ps["deal_active"] = hit

    target = p.get("target_price")
    if target:
        hit_t = cur <= target
        if hit_t and not ps.get("target_hit"):
            kind = kind or "達到目標價"
            reasons.append(f"已達到目標價 {fmt(target)} 元")
        ps["target_hit"] = hit_t

    if prev_low is not None and cur < prev_low and not learning:
        reasons.append(f"追蹤以來最低價！之前最低 {fmt(prev_low)} 元（{ps.get('lowest_at', '')}）")
        if kind is None:
            kind = "歷史新低"
            if original:
                reasons.insert(0, f"原價 {fmt(original)} 元，現在 {zhe(cur, original)}")
    return kind, reasons


def fill_lego_prices(products: list[dict], state: dict) -> None:
    """樂高沒填原價的話，自動查必買站標的原價（查到後記住，不會每次都查）。"""
    cache = state.setdefault("lego_list_prices", {})
    for p in products:
        if p.get("category") != "樂高" or p.get("original_price"):
            continue
        model = str((p.get("must_include") or [""])[0])
        if not model.isdigit():
            continue
        if not cache.get(model):  # 查不到的下次會再查
            try:
                found = lego_list_price(model)
            except Exception as e:
                print(f"  查 {model} 原價失敗：{e}")
                continue
            if found:
                cache[model] = found
        if cache.get(model):
            p["original_price"] = cache[model]
            p["original_price_auto"] = True
            print(f"  {model} 原價自動帶入 {cache[model]} 元（必買站）")


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    categories = cfg.get("categories") or {}
    global_exclude = cfg.get("global_exclude") or []
    state = load_json(STATE, {"products": {}, "sites": {}})
    state.setdefault("products", {})
    state.setdefault("sites", {})
    raw_products = cfg.get("products") or []
    fill_lego_prices(raw_products, state)
    products = [merge_category(p, categories) for p in raw_products]
    now_dt = datetime.now(TW)
    now = now_dt.strftime(TFMT)
    DATA.mkdir(exist_ok=True)
    history = load_history()
    new_file = not HISTORY.exists()
    latest_snapshot = {}
    run_ok: dict[str, tuple[bool, str]] = {}

    with HISTORY.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(["time", "product", "site", "price", "title", "url"])

        for idx, p in enumerate(products):
            name = p["name"]
            kws = p.get("keywords") or name
            kws = [kws] if isinstance(kws, str) else list(kws)
            print(f"\n=== {name} ===")
            raw = fetch_all(kws, run_ok)
            good = [x for x in raw
                    if match_reason(x.title, p, global_exclude) is None and price_ok(x.price, p)]
            good.sort(key=lambda x: x.price)
            print(f"  抓到 {len(raw)} 筆，符合條件 {len(good)} 筆")

            per_site: dict[str, Listing] = {}
            for x in good:
                per_site.setdefault(x.site, x)
            for site, x in per_site.items():
                w.writerow([now, name, site, x.price, x.title, x.url])
            latest_snapshot[name] = [x.__dict__ for x in good[:30]]

            ps = state["products"].setdefault(name, {})
            anchor = f"p{idx}"
            if not good:
                ps["empty_runs"] = ps.get("empty_runs", 0) + 1
                if ps["empty_runs"] == FAIL_ALERT_AFTER:
                    send_telegram(f"<b>【提醒】{esc(name)}</b>\n已經連續 {FAIL_ALERT_AFTER} 次找不到符合條件的商品，"
                                  "可能是關鍵字或過濾條件太嚴，或商品下架了。")
                continue
            ps["empty_runs"] = 0

            best = good[0]
            cur = best.price
            original = p.get("original_price")

            if ps.get("lowest") is None:  # 第一次追蹤
                extra = []
                if p.get("rule") == "discount" and original:
                    src = "（自動查必買站的標示，如果不對請在 products.yaml 填正確原價）" if p.get("original_price_auto") else ""
                    extra.append(f"原價 {fmt(original)} 元{src}，現在 {zhe(cur, original)}")
                    lvl = tier_level(cur, original, p.get("tiers") or [])
                    if lvl >= 0:
                        extra.append(f"目前已經是「{p['tiers'][lvl]['label']}」")
                    ps["tier_notified"] = lvl
                elif p.get("rule") == "discount":
                    extra.append("查不到原價，請在 products.yaml 填上，填好之前只會通知歷史新低")
                else:
                    extra.append(f"前 {p.get('learn_days', 14)} 天只記錄價格、不通知，之後比一般價格便宜 "
                                 f"{round(float(p.get('drop_pct', 0.15)) * 100)}% 以上或創新低才通知")
                if p.get("target_price"):
                    ps["target_hit"] = cur <= p["target_price"]
                send_telegram(build_message("開始追蹤", p, best, per_site, extra, anchor))
                ps.update(lowest=cur, lowest_at=now, lowest_site=best.site)
            else:
                kind, reasons = evaluate(p, ps, cur, now_dt, history.get(name, []))
                if cur < ps["lowest"]:
                    ps.update(lowest=cur, lowest_at=now, lowest_site=best.site)
                if kind:
                    send_telegram(build_message(kind, p, best, per_site, reasons, anchor))
            ps["last_price"] = cur
            ps["last_checked"] = now

    # 網站連續失敗提醒（每次執行只算一次）
    for site, (ok, err) in run_ok.items():
        st = state["sites"].setdefault(site, {"fails": 0})
        if ok:
            st["fails"] = 0
            continue
        st["fails"] = st.get("fails", 0) + 1
        st["last_error"] = err[:200]
        if st["fails"] == FAIL_ALERT_AFTER:
            send_telegram(f"<b>【提醒】{esc(site)} 連續 {FAIL_ALERT_AFTER} 次抓取失敗</b>\n"
                          f"可能是網站改版或擋住了連線，需要修程式。\n錯誤：{esc(st.get('last_error', ''))}")

    state["last_run"] = now
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "latest.json").write_text(json.dumps({"time": now, "products": latest_snapshot},
                                                 ensure_ascii=False, indent=1), encoding="utf-8")

    from .report import build_report
    build_report(products, ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
