"""臨時比價：輸入關鍵字，馬上把各網站最便宜的結果傳到 Telegram。

執行方式：python -m pricewatch.quick "關鍵字" --must "一定要有的字" --exclude "排除的字" --all
"""
from __future__ import annotations

import argparse
import re
import statistics
import sys
import time
from pathlib import Path

import yaml

from .filters import _VARIANTS, match_reason, site_blocked
from .notify import esc, send_telegram
from .sites import ALL_SITES, BACKED_UP, BlockedError

ROOT = Path(__file__).resolve().parent.parent
USED_WORDS = ["二手", "中古", "舊書", "書況", "無劃記", "九成新", "9成新", "95新", "蠻新", "已拆", "拆封", "近全新"]
USED_OK = ["未拆"]
# 個人賣家為主的平台（可能是二手）
C2C = {"蝦皮", "露天拍賣", "Yahoo拍賣", "iOPEN Mall", "旋轉拍賣"}
CHINA_SELLER = re.compile(r"^正版\s|壹")


def split_words(s: str | None) -> list[str]:
    return [w for w in re.split(r"[\s,，、]+", s or "") if w]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword")
    ap.add_argument("--must", default="", help="標題一定要有的字，用空白分開；不填就用關鍵字本身")
    ap.add_argument("--exclude", default="", help="要排除的字，用空白分開")
    ap.add_argument("--all", action="store_true", help="二手也要看")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "products.yaml").read_text(encoding="utf-8")) or {}
    keyword = a.keyword.strip()
    is_isbn = re.fullmatch(r"\d{10}|\d{13}", keyword) is not None
    must = split_words(a.must) or ([] if is_isbn else split_words(keyword))
    rule = {"must_include": must, "exclude": split_words(a.exclude)}
    if not a.all:
        rule.update(used_words=USED_WORDS, used_ok_words=USED_OK)

    # 關鍵字有異體字的話（例如「致」和「緻」），兩種寫法都搜
    keywords = [keyword]
    alt = keyword.translate(_VARIANTS)
    if alt != keyword:
        keywords.append(alt)

    raw, failed = [], []
    for name, fn in ALL_SITES.items():
        ok, reason = False, ""
        for kw in keywords:
            try:
                raw += fn(kw)
                ok = True
            except Exception as e:
                if name in BACKED_UP:
                    reason = f"直接連線被擋，已改從{BACKED_UP[name]}取得（筆數可能比較少）"
                elif isinstance(e, BlockedError):
                    reason = str(e)
                else:
                    reason = "連線失敗或網站改版"
                print(f"[{name}] 「{kw}」失敗：{e}")
            time.sleep(1)
        if not ok:
            failed.append(f"{name}：{reason}")

    seen, good = set(), []
    for x in sorted(raw, key=lambda x: x.price):
        if match_reason(x.title, rule, cfg.get("global_exclude") or []) is not None:
            continue
        if site_blocked(x.site, cfg.get("exclude_sites")):
            continue
        if CHINA_SELLER.search(x.title):  # 中國賣家常見寫法（多半是簡體書或代購）
            continue
        key = (x.site, x.title.strip(), x.price)
        if key not in seen:
            seen.add(key)
            good.append(x)

    # 價格特別低的（低於中位數 4 成），多半是賣場裡其他規格的價格或標錯價，另外列
    odd = []
    if len(good) >= 5:
        median = statistics.median(x.price for x in good)
        odd = [x for x in good if x.price < median * 0.4]
        good = [x for x in good if x.price >= median * 0.4]

    head = f"<b>【臨時比價】{esc(keyword)}</b>"
    cond = "含二手" if a.all else "標題寫二手的已排除"
    if not good:
        msg = f"{head}\n找不到標題符合「{esc(' '.join(must))}」的商品。"
        hints = []
        for x in raw:  # 各網站搜尋結果的前幾筆，通常最接近
            t = x.title[:45]
            if t not in hints:
                hints.append(t)
            if len(hints) >= 5:
                break
        if hints:
            msg += "\n\n網站上最接近的商品名稱，可以參考正確寫法：\n" + "\n".join(f"・{esc(t)}" for t in hints)
        msg += "\n\n也可以把「標題一定要有的字」只填最關鍵的一兩個字再查一次。"
    else:
        shops = [x for x in good if x.site not in C2C]
        c2c = [x for x in good if x.site in C2C]

        def block(items, n):
            out = []
            for i, x in enumerate(items[:n], 1):
                title = x.title if len(x.title) <= 38 else x.title[:38] + "…"
                out.append(f'{i}. <b>{x.price:,}</b> {esc(x.site)}\n   <a href="{esc(x.url)}">{esc(title)}</a>')
            return out or ["（沒有）"]

        lines = [head, f"共 {len(good)} 筆符合（{cond}）", "",
                 "<b>■ 商城、書店（全新）</b>"] + block(shops, 6)
        lines += ["", "<b>■ 拍賣、個人賣場（可能是二手，請點進去確認）</b>"] + block(c2c, 6)
        per_site = {}
        for x in good:
            per_site.setdefault(x.site, x.price)
        lines += ["", "各網站最低：" + "、".join(f"{esc(s)} {p:,}" for s, p in per_site.items())]
        if odd:
            lines += ["", f"<b>■ 價格異常（{len(odd)} 筆，可能是其他規格或標錯價）</b>"]
            for x in odd[:3]:
                title = x.title if len(x.title) <= 30 else x.title[:30] + "…"
                lines.append(f'・{x.price:,} {esc(x.site)} <a href="{esc(x.url)}">{esc(title)}</a>')
        msg = "\n".join(lines)
    if failed:
        msg += "\n\n這次沒抓到：\n" + "\n".join(f"・{esc(f)}" for f in failed)
        if any("BigGo" in f for f in failed):
            msg += "\n（BigGo 沒抓到時，iOPEN Mall、旋轉拍賣、博客來、讀冊會缺，蝦皮由飛比價格補上。過幾分鐘再查一次通常就會恢復）"
    send_telegram(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
