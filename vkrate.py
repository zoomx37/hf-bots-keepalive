import os
import re
import time
import threading
import logging
import vk_api
import vk_api.exceptions

log = logging.getLogger("vkrate")

_lock = threading.Lock()
_last = [0.0]
MIN_GAP = float(os.getenv("VK_MIN_GAP", "2.0"))
KATE_USER_AGENT = "KateMobileAndroid/113.1 lite-arm64-v8a (Android 14; SDK 34; Google Pixel 7; ru)"

def get_vk_session(token: str, api_version: str = "5.131"):
    session = vk_api.VkApi(token=token.strip(), api_version=api_version)
    session.http.headers["User-Agent"] = KATE_USER_AGENT
    return session

def vk_call(session, method: str, **params):
    # Центральный выключатель: если карантин — не трогаем API вовсе
    if os.getenv("VK_ENABLED", "true").lower() == "false":
        raise RuntimeError("VK выключен (VK_ENABLED=false)")

    with _lock:
        wait = MIN_GAP - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()

    for attempt in range(3):
        try:
            return session.method(method, params)
        except vk_api.exceptions.ApiError as e:
            code = getattr(e, "code", None)
            if code is None:
                m = re.search(r"\[(\d+)\]", str(e))
                code = int(m.group(1)) if m else 0
                
            if code in (6, 9):
                wait_sec = min(30, 6 * (attempt + 1))
                log.warning(f"⚠️ [VK Throttling] Код {code} на {method}. Пауза {wait_sec}с...")
                time.sleep(wait_sec)
                continue
            raise
        except Exception as ex:
            if "Flood control" in str(ex):
                time.sleep(6 * (attempt + 1))
                continue
            raise
            
    raise RuntimeError(f"VK {method}: лимит [9] Flood control не отпустил после 3 попыток")
