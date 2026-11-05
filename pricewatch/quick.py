"""臨時比價：輸入關鍵字，馬上把各網站最便宜的結果傳到 Telegram。

執行方式：python -m pricewatch.quick "關鍵字" --must "一定要有的字" --exclude "排除的字" --all
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import yaml

from .filters import match_reason
from .notify import esc, send_telegram
from .sites import ALL_SITES

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

    raw, failed = [], []
    for name, fn in ALL_SITES.items():
        try:
            raw += fn(keyword)
        except Exception as e:
            failed.append(name)
            print(f"[{name}] 失敗：{e}")
        time.sleep(1)

    seen, good = set(), []
    for x in sorted(raw, key=lambda x: x.price):
        if match_reason(x.title, rule, cfg.get("global_exclude") or []) is not None:
            continue
        if CHINA_SELLER.search(x.title):  # 中國賣家常見寫法（多半是簡體書或代購）
            continue
        key = (x.site, x.url or x.title)
        if key not in seen:
            seen.add(key)
            good.append(x)

    head = f"<b>【臨時比價】{esc(keyword)}</b>"
    cond = "含二手" if a.all else "標題寫二手的已排除"
    if not good:
        msg = f"{head}\n找不到符合的商品。可以換個關鍵字，或把「一定要有的字」放寬。"
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
        msg = "\n".join(lines)
    if failed:
        msg += f"\n\n這次沒抓到：{esc('、'.join(failed))}"
    send_telegram(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
