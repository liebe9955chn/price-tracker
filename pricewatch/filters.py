"""判斷一筆商品標題是不是我們要追蹤的商品。"""
from __future__ import annotations

import re


def _contains(title: str, word: str) -> bool:
    word = str(word)
    if word.isdigit():
        # 純數字：前後不能緊接其他數字（40817 不會比對到 140817 或 408170）
        return re.search(rf"(?<!\d){re.escape(word)}(?!\d)", title) is not None
    return word.lower() in title.lower()


def match_reason(title: str, product: dict, global_exclude: list[str]) -> str | None:
    """符合就回傳 None，不符合就回傳原因（方便除錯）。"""
    for w in list(global_exclude) + list(product.get("exclude") or []):
        if _contains(title, w):
            return f"排除字：{w}"
    used = product.get("used_words") or []
    if used and any(_contains(title, w) for w in used):
        if not any(_contains(title, w) for w in product.get("used_ok_words") or []):
            return "二手且沒有註明狀況良好"
    for w in product.get("must_include") or []:
        if not _contains(title, w):
            return f"缺少：{w}"
    limit = product.get("max_other_models")
    if limit is not None:
        own = {str(w) for w in product.get("must_include") or []}
        others = {n for n in re.findall(r"(?<!\d)\d{5}(?!\d)", title) if n not in own}
        if len(others) > limit:
            return f"一個賣場有好幾款：{'/'.join(sorted(others))}"
    any_words = product.get("must_include_any") or []
    if any_words and not any(_contains(title, w) for w in any_words):
        return f"缺少其中之一：{'/'.join(map(str, any_words))}"
    return None


def price_ok(price: int, product: dict) -> bool:
    lo = product.get("min_price")
    hi = product.get("max_price")
    if lo is not None and price < lo:
        return False
    if hi is not None and price > hi:
        return False
    return True


def merge_category(product: dict, categories: dict) -> dict:
    """把類別的預設規則套到商品上；商品自己寫的欄位優先，排除字等清單會合併。"""
    cat = dict(categories.get(product.get("category") or "", {}) or {})
    merged = {**cat, **{k: v for k, v in product.items() if v is not None}}
    for key in ("exclude", "must_include_any", "used_words", "used_ok_words"):
        if key in cat and key in product and product[key] is not None:
            merged[key] = list(cat[key]) + [w for w in product[key] if w not in cat[key]]
    orig = merged.get("original_price")
    if orig:
        if merged.get("min_price") is None and merged.get("min_ratio"):
            merged["min_price"] = int(orig * merged["min_ratio"])
        if merged.get("max_price") is None and merged.get("max_ratio"):
            merged["max_price"] = int(orig * merged["max_ratio"])
    merged.setdefault("rule", "discount" if orig else "baseline")
    return merged
