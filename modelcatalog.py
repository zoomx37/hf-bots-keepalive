import os
import logging
import requests

log = logging.getLogger("modelcatalog")

def list_google(key: str) -> list[str]:
    """Запрашивает у Google список всех моделей, поддерживающих генерацию текста."""
    if not key:
        return []
    try:
        r = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": key},
            timeout=20
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

def list_groq(key: str) -> list[str]:
    """Запрашивает список доступных моделей у Groq."""
    if not key:
        return []
    try:
        r = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=20
        ).json()
        return sorted(m["id"] for m in r.get("data", []))
    except Exception as e:
        log.warning(f"Ошибка получения моделей Groq: {e}")
        return []

def list_openrouter() -> list[str]:
    """Запрашивает список доступных моделей у OpenRouter."""
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", timeout=20).json()
        return sorted(m["id"] for m in r.get("data", []))
    except Exception as e:
        log.warning(f"Ошибка получения моделей OpenRouter: {e}")
        return []

def resolve_model(env_name: str, prefer_fn, lister_fn, key: str) -> str:
    """env-переопределение > самая свежая модель из живого API."""
    custom = os.getenv(env_name)
    if custom:
        return custom.strip()
    try:
        models = lister_fn(key)
        hits = [m for m in models if prefer_fn(m)]
        if hits:
            return hits[-1]  # Последняя по алфавиту/версии = самая новая
    except Exception as e:
        log.warning(f"{env_name}: автодетект не удался ({e})")
    return None

def get_active_models():
    """Определяет актуальную цепочку моделей на основе ответа API."""
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()

    g = resolve_model(
        "MODEL_GEMINI",
        lambda m: "flash" in m and "lite" not in m and "thinking" not in m,
        list_google,
        gemini_key
    )
    q = resolve_model(
        "MODEL_GROQ",
        lambda m: "70b" in m or "llama-3" in m,
        list_groq,
        groq_key
    )
    o = resolve_model(
        "MODEL_OPENROUTER",
        lambda m: "llama-3.3-70b" in m or "free" in m,
        lambda _: list_openrouter(),
        openrouter_key
    )

    log.info(f"Активные модели: Gemini={g}, Groq={q}, OpenRouter={o}")
    return {"gemini": g, "groq": q, "openrouter": o}
