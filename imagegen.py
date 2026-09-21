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

_mid = None
def get_kandinsky_model_id():
    global _mid
    if _mid: return _mid
    try:
        ms = requests.get(f"{BASE}/key/api/v1/models", headers=_h(), timeout=15).json()
        kd = sorted([m for m in ms if "kandinsky" in m.get("name", "").lower()],
                    key=lambda m: m.get("name", ""))
        _mid = kd[-1]["id"]
        return _mid
    except Exception:
        return 4

def generate_pollinations(prompt: str) -> bytes:
    """Бесплатный резерв: генерация без API-ключей в 1 запрос."""
    try:
        url = f"https://image.pollinations.ai/prompt/{quote(prompt)}?width=1024&height=1024&nologo=true"
        r = requests.get(url, timeout=40)
        if r.ok and r.headers.get("content-type", "").startswith("image"):
            return r.content
    except Exception as e:
        log.warning(f"Ошибка Pollinations: {e}")
    return None

def generate_image(prompt: str, width: int = 1024, height: int = 1024) -> bytes:
    """Возвращает байты изображения (JPEG/PNG) или None."""
    # 1. Если заданы ключи Kandinsky (FusionBrain)
    if KEY and SECRET:
        try:
            body = {
                "type": "GENERATE",
                "numImages": 1,
                "width": width,
                "height": height,
                "model": get_kandinsky_model_id(),
                "generateParams": {"query": prompt[:900]}
            }
            r = requests.post(f"{BASE}/key/api/v1/text2image/run", json=body, headers=_h(), timeout=20).json()
            uuid = r.get("uuid")
            if uuid:
                for _ in range(18):  # Ожидание генерации до 45 сек
                    time.sleep(2.5)
                    st = requests.get(f"{BASE}/key/api/v1/text2image/status/{uuid}", headers=_h(), timeout=15).json()
                    if st.get("status") == "DONE":
                        return base64.b64decode(st["images"][0])
                    if st.get("status") == "FAIL":
                        break
        except Exception as e:
            log.warning(f"Kandinsky сбой ({e}), переход на Pollinations...")

    # 2. Безотказный резерв Pollinations
    return generate_pollinations(prompt)
