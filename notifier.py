import os
import requests

PAGER_TOKEN = os.getenv("TG_BOT_TOKEN", os.getenv("PAGER_BOT_TOKEN", ""))
CHAT_ID = os.getenv("ADMIN_CHAT_ID", os.getenv("MY_CHAT_ID", "721042205"))

def notify(text: str, html: bool = True):
    """Отправляет служебные уведомления с гарантированной доставкой HTML/Plain."""
    if not PAGER_TOKEN:
        print(f"[NOTIFY] {text}")
        return
    url = f"https://api.telegram.org/bot{PAGER_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text[:4000],
        "disable_web_page_preview": True
    }
    if html:
        payload["parse_mode"] = "HTML"
        
    try:
        r = requests.post(url, json=payload, timeout=20).json()
        if not r.get("ok") and html:
            # Если Telegram ругнулся на HTML — шлём чистый текст без тегов
            payload.pop("parse_mode")
            clean_text = (
                text.replace("<b>", "").replace("</b>", "")
                    .replace("<i>", "").replace("</i>", "")
                    .replace("<code>", "").replace("</code>", "")
            )
            payload["text"] = clean_text[:4000]
            requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Ошибка notify: {e}")
