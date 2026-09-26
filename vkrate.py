import os
import re
import time
import threading
import logging
import requests
import vk_api
import vk_api.exceptions

log = logging.getLogger("vkrate")

_lock = threading.Lock()
_last = [0.0]
_state = {"streak": 0, "until": 0.0}
MIN_GAP = float(os.getenv("VK_MIN_GAP", "2.0"))
KATE_USER_AGENT = "KateMobileAndroid/113.1 lite-arm64-v8a (Android 14; SDK 34; Google Pixel 7; ru)"

def can_vk() -> tuple[bool, int]:
    """Проверяет, не включен ли аварийный предохранитель."""
    rem = int(_state["until"] - time.time())
    if rem > 0:
        return False, (rem // 60) + 1
    return True, 0

def get_vk_session(token: str, api_version: str = "5.131"):
    session = requests.Session()
    proxy = os.getenv("VK_PROXY", "").strip()
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    
    vk_sess = vk_api.VkApi(token=token.strip(), api_version=api_version, session=session)
    vk_sess.http.headers["User-Agent"] = KATE_USER_AGENT
    return vk_sess

def vk_call(session, method: str, **params):
    if os.getenv("VK_ENABLED", "true").lower() == "false":
        raise RuntimeError("VK выключен в настройках (VK_ENABLED=false)")

    allowed, wait_min = can_vk()
    if not allowed:
        raise RuntimeError(f"Предохранитель ВК: пауза еще {wait_min} мин. Запросы временно остановлены.")

    with _lock:
        wait = MIN_GAP - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()

    for attempt in range(3):
        try:
            res = session.method(method, params)
            _state["streak"] = 0
            return res
        except vk_api.exceptions.ApiError as e:
            code = getattr(e, "code", None)
            if code is None:
                m = re.search(r"\[(\d+)\]", str(e))
                code = int(m.group(1)) if m else 0

            if code in (6, 9):  # Flood control
                _state["streak"] += 1
                if _state["streak"] >= 2:
                    # При повторных ошибках включаем паузу с защитой от продления бана
                    pause_sec = min(7200, 900 * _state["streak"])  # 15 мин, 30 мин...
                    _state["until"] = time.time() + pause_sec
                    log.warning(f"🔌 [VK Breaker] Аварийный стоп ВК на {pause_sec // 60} мин во избежание блокировки.")
                    raise RuntimeError(f"ВК включил защиту [9]. Агент взял паузу на {pause_sec // 60} мин.")

                time.sleep(5 * (attempt + 1))
                continue
            raise
        except Exception as ex:
            if "Flood control" in str(ex):
                time.sleep(5 * (attempt + 1))
                continue
            raise

    raise RuntimeError(f"VK {method}: лимит [9] Flood control не отпустил после 3 попыток")
