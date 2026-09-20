import os
import requests

PAGER_TOKEN = os.getenv("TG_BOT_TOKEN", os.getenv("PAGER_BOT_TOKEN", ""))
CHAT_ID = os.getenv("ADMIN_CHAT_ID", os.getenv("MY_CHAT_ID", "721042205"))

def notify(text: str):
    """Отправляет уведомление о модерации в Telegram оператору."""
    if not PAGER_TOKEN:
        print(f"[NOTIFY] {text}")
        return
    url = f"https://api.telegram.org/bot{PAGER_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text[:4000],
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Ошибка notify: {e}")
