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
    ok = [
        m for m in models
        if "flash" in m.lower() and not BAD.search(m)
        and "lite" not in m.lower() and "thinking" not in m.lower()
    ]
    if not ok:
        ok = [m for m in models if "flash" in m.lower() and not BAD.search(m)]
    return max(ok, key=_ver) if ok else "gemini-3.8-flash"

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
    """Возвращает список реально бесплатных (:free) моделей из API OpenRouter."""
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=15).json()
        return sorted(m["id"] for m in r.get("data", []) if ":free" in m.get("id", ""))
    except Exception as e:
        log.warning(f"Ошибка получения моделей OpenRouter: {e}")
        return []

def get_active_models():
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    custom_gemini = os.getenv("MODEL_GEMINI", "gemini-3.8-flash").strip()
    g = custom_gemini or pick_gemini(list_google(gemini_key))

    custom_or = os.getenv("MODEL_OPENROUTER", "z-ai/glm-5.2:free").strip()
    
    # Берём реальные живые бесплатные модели OpenRouter из API
    live_free = list_openrouter()
    backups = [m for m in live_free if m != custom_or][:3]

    return {
        "gemini": g,
        "openrouter_primary": custom_or,
        "openrouter_backups": backups
    }
