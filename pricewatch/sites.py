"""各購物網站的搜尋爬蟲。每個函式都回傳 Listing 清單。"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from urllib.parse import quote

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
TIMEOUT = 30


@dataclass
class Listing:
    site: str
    title: str
    price: int
    url: str


def _get(url: str) -> requests.Response:
    last = None
    for attempt in range(3):
        try:
            r = requests.get(
                url,
                headers={"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise last


def _to_int(v) -> int | None:
    try:
        return int(float(str(v).replace(",", "").replace("$", "").strip()))
    except (TypeError, ValueError):
        return None


def _next_flight_text(html: str) -> str:
    """把 Next.js 頁面裡 self.__next_f.push(...) 的資料串接成一段文字。"""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S)
    return "".join(json.loads('"' + c + '"') for c in chunks)


def _decode_after(text: str, marker: str):
    i = text.find(marker)
    if i < 0:
        return None
    obj, _ = json.JSONDecoder().raw_decode(text[i + len(marker):])
    return obj


# ---------------- PChome 24h ----------------
def pchome(keyword: str) -> list[Listing]:
    out = []
    for page in (1, 2):
        url = (
            "https://ecshweb.pchome.com.tw/search/v4.3/all/results"
            f"?q={quote(keyword)}&page={page}&sort=prc/ac"
        )
        d = _get(url).json()
        for p in d.get("Prods") or []:
            price = _to_int(p.get("Price"))
            if price:
                out.append(Listing("PChome 24h", p["Name"], price,
                                   f"https://24h.pchome.com.tw/prod/{p['Id']}"))
        if page >= (d.get("TotalPage") or 1):
            break
    return out


# ---------------- momo ----------------
def momo(keyword: str) -> list[Listing]:
    html = _get(f"https://www.momoshop.com.tw/search/{quote(keyword)}").text
    goods = _decode_after(_next_flight_text(html), '"goodsInfoList":') or []
    out = []
    for g in goods:
        price = _to_int(((g.get("goodsPriceModel") or {}).get("basePrice") or {}).get("price"))
        if price is None:
            price = _to_int(g.get("goodsPrice"))
        if price:
            url = g.get("goodsUrl") or (
                "https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code=" + g["goodsCode"])
            out.append(Listing("momo", g.get("goodsName", ""), price, url.split("&Area=")[0].strip()))
    return out


# ---------------- Yahoo 購物中心 / 拍賣 ----------------
def _yahoo(url: str, site: str, base: str) -> list[Listing]:
    html = _get(url).text
    m = re.search(r'id="isoredux-data"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("找不到 Yahoo 頁面資料（網站可能改版）")
    hits = json.loads(m.group(1))["search"]["ecsearch"]["hits"]
    out = []
    for h in hits:
        price = _to_int(h.get("ec_price"))
        link = h.get("ec_item_url") or ""
        if link.startswith("/"):
            link = base + link
        if price:
            out.append(Listing(site, h.get("ec_title", ""), price, link))
    return out


def yahoo_buy(keyword: str) -> list[Listing]:
    return _yahoo(f"https://tw.buy.yahoo.com/search/product?p={quote(keyword)}&sort=price",
                  "Yahoo購物中心", "https://tw.buy.yahoo.com")


def yahoo_bid(keyword: str) -> list[Listing]:
    return _yahoo(f"https://tw.bid.yahoo.com/search/auction/product?p={quote(keyword)}",
                  "Yahoo拍賣", "https://tw.bid.yahoo.com")


# ---------------- 露天拍賣 ----------------
def ruten(keyword: str) -> list[Listing]:
    url = ("https://rtapi.ruten.com.tw/api/search/v3/index.php/core/prod"
           f"?q={quote(keyword)}&type=direct&sort=rnk%2Fdc&offset=1&limit=80")
    ids = [r["Id"] for r in (_get(url).json().get("Rows") or [])]
    out = []
    for i in range(0, len(ids), 40):
        batch = ",".join(ids[i:i + 40])
        for x in _get(f"https://rtapi.ruten.com.tw/api/prod/v2/index.php/prod?id={batch}").json():
            pr = x.get("PriceRange") or []
            price = _to_int(pr[0]) if pr else None
            if price and str(x.get("StockStatus", "1")) != "0":
                out.append(Listing("露天拍賣", x.get("ProdName", ""), price,
                                   f"https://www.ruten.com.tw/item/show?{x['ProdId']}"))
        time.sleep(1)
    return out


# ---------------- BigGo（含蝦皮、iOPEN Mall、旋轉拍賣等） ----------------
# BigGo 的商店代碼對應到統一的網站名稱，跟直接抓的網站合併計算
BIGGO_STORE = {
    "tw_mall_shopeemall": "蝦皮",
    "tw_bid_shopee": "蝦皮",
    "tw_mall_iopenmall": "iOPEN Mall",
    "tw_bid_ybid": "Yahoo拍賣",
    "tw_ec_pchome24h": "PChome 24h",
    "tw_pec_momoshop": "momo",
    "tw_ec_yahoobuy": "Yahoo購物中心",
}


def _normalize_store(store: str) -> str:
    low = store.lower()
    if "蝦皮" in store or "shopee" in low:
        return "蝦皮"
    if "momo" in low:
        return "momo"
    if "pchome" in low:
        return "PChome 24h"
    if "iopen" in low:
        return "iOPEN Mall"
    if "露天" in store or "ruten" in low:
        return "露天拍賣"
    if "旋轉" in store or "carousell" in low:
        return "旋轉拍賣"
    if "yahoo" in low and "拍賣" in store:
        return "Yahoo拍賣"
    if "yahoo" in low:
        return "Yahoo購物中心"
    return store


def biggo(keyword: str) -> list[Listing]:
    out = []
    for page in (1, 2, 3):
        url = f"https://biggo.com.tw/s/{quote(keyword)}/?p={page}"
        txt = _next_flight_text(_get(url).text)
        data = _decode_after(txt, '"ssrData":') or {}
        items = data.get("list") or []
        for x in items:
            price = _to_int(x.get("price"))
            if not price or x.get("is_offline") or x.get("is_expired") or x.get("is_notfound"):
                continue
            nindex = x.get("nindex", "")
            store = (x.get("store") or {}).get("name") or nindex
            site = BIGGO_STORE.get(nindex) or _normalize_store(store)
            out.append(Listing(site, x.get("title", ""), price, (x.get("purl") or "").strip()))
        if page >= (data.get("total_page") or 1) or not items:
            break
        time.sleep(1)
    return out


def lego_list_price(model: str) -> int | None:
    """從必買站的蝦皮賣場（透過 BigGo）推算樂高台灣定價：售價 + 標示的折扣金額。"""
    txt = _next_flight_text(_get(f"https://biggo.com.tw/s/{quote('必買站 ' + model)}/").text)
    data = _decode_after(txt, '"ssrData":') or {}
    for x in data.get("list") or []:
        title = x.get("title", "")
        if "必買站" in title and re.search(rf"(?<!\d){model}(?!\d)", title) and "shopee" in x.get("nindex", ""):
            price = _to_int(x.get("price"))
            diff = _to_int(x.get("price_diff_real")) or 0
            if price:
                return price - diff if diff < 0 else price
    return None


ALL_SITES = {
    "PChome 24h": pchome,
    "momo": momo,
    "Yahoo購物中心": yahoo_buy,
    "Yahoo拍賣": yahoo_bid,
    "露天拍賣": ruten,
    "BigGo（含蝦皮、iOPEN Mall、旋轉拍賣）": biggo,
}
