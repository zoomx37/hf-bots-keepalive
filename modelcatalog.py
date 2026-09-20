import os
import re
import logging
import requests

log = logging.getLogger("modelcatalog")

BAD = re.compile(r"preview|exp|omni|tts|image|audio|embed|aqa|guard", re.I)

def _ver(m: str) -> float:
    nums = re.findall(r"\d+(?:\.\d+)?", m)
    return float(nums[0]) if nums else 0.0

def pick_gemini(models: list[str]) -> str:
    """Выбирает старшую Flash-модель по номеру версии (3.8 > 3.7), отсекая preview/omni."""
    ok = [
        m for m in models
        if "flash" in m.lower() and not BAD.search(m)
        and "lite" not in m.lower() and "thinking" not in m.lower()
    ]
    if not ok:
        ok = [m for m in models if "flash" in m.lower() and not BAD.search(m)]
    return max(ok, key=_ver) if ok else None

def list_google(key: str) -> list[str]:
    if not key:
        return []
    try:
        r = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": key},
            timeout=15
        ).json()
        models = [
            m["name"].replace("models/", "")
            for m in r.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        ]
        return sorted(models)
    except Exception as e:
        log.warning(f"Ошибка получения моделей Google: {e}")
        return []

def list_openrouter() -> list[str]:
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=15).json()
        return sorted(m["id"] for m in r.get("data", []) if ":free" in m.get("id", ""))
    except Exception as e:
        log.warning(f"Ошибка получения моделей OpenRouter: {e}")
        return []

def get_active_models():
    """Определяет актуальную цепочку моделей."""
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    # 1. Gemini: приоритет env-переменной > умный pick()
    custom_gemini = os.getenv("MODEL_GEMINI")
    if custom_gemini:
        g = custom_gemini.strip()
    else:
        g = pick_gemini(list_google(gemini_key)) or "gemini-3.8-flash"

    # 2. OpenRouter: подтвержденный glm-5.2:free + бэкапы
    custom_or = os.getenv("MODEL_OPENROUTER", "z-ai/glm-5.2:free").strip()
    backups_str = os.getenv("OPENROUTER_BACKUPS", "deepseek/deepseek-chat-v3:free,qwen/qwen-2.5-72b-instruct:free")
    backups = [m.strip() for m in backups_str.split(",") if m.strip()]

    log.info(f"Активные модели: Gemini={g}, OpenRouter={custom_or}, Backups={backups}")
    return {
        "gemini": g,
        "openrouter_primary": custom_or,
        "openrouter_backups": backups
    }
