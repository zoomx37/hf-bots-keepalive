import os
import base64
import time
import logging
import requests
from urllib.parse import quote

log = logging.getLogger("imagegen")
BASE = "https://api-key.fusionbrain.ai"
KEY = os.getenv("FB_API_KEY", "").strip()
SECRET = os.getenv("FB_SECRET_KEY", "").strip()

def _h():
    return {"X-Key": f"Key {KEY}", "X-Secret": f"Secret {SECRET}"}

def generate_pollinations(prompt: str) -> bytes:
    """Бесплатная генерация через Pollinations с браузерным заголовком."""
    try:
        clean_prompt = prompt.replace("[КАРТИНКА:", "").replace("]", "").strip()
        url = f"https://image.pollinations.ai/prompt/{quote(clean_prompt)}?width=1024&height=1024&nologo=true"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=60)
        if r.status_code == 200 and r.content and len(r.content) > 2000:
            return r.content
        log.warning(f"Pollinations статус: {r.status_code}")
    except Exception as e:
        log.warning(f"Ошибка Pollinations: {e}")
    return None

def generate_image(prompt: str, width: int = 1024, height: int = 1024) -> bytes:
    # 1. Если заданы ключи Kandinsky
    if KEY and SECRET:
        try:
            body = {
                "type": "GENERATE",
                "numImages": 1,
                "width": width,
                "height": height,
                "model": 4,
                "generateParams": {"query": prompt[:900]}
            }
            r = requests.post(f"{BASE}/key/api/v1/text2image/run", json=body, headers=_h(), timeout=20).json()
            uuid = r.get("uuid")
            if uuid:
                for _ in range(18):
                    time.sleep(2.5)
                    st = requests.get(f"{BASE}/key/api/v1/text2image/status/{uuid}", headers=_h(), timeout=15).json()
                    if st.get("status") == "DONE":
                        return base64.b64decode(st["images"][0])
                    if st.get("status") == "FAIL":
                        break
        except Exception as e:
            log.warning(f"Kandinsky сбой ({e})")

    # 2. Безотказный резерв Pollinations
    return generate_pollinations(prompt)
