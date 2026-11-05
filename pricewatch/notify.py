"""Telegram 通知。"""
from __future__ import annotations

import html
import os

import requests


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("[通知] 沒有設定 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID，只印在畫面上：")
        print(text)
        return False
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    if not r.ok:
        print("[通知] Telegram 傳送失敗：", r.status_code, r.text)
    return r.ok


def esc(s) -> str:
    return html.escape(str(s), quote=False)
