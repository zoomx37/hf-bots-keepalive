import os
import re
import time
import logging
import requests
from openai import OpenAI
from modelcatalog import get_active_models

log = logging.getLogger("llm")

def _has_garbage(text: str) -> bool:
    if not text:
        return True
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    if cjk >= 2 or (len(text) > 80 and (cjk / len(text)) > 0.015):
        return True
    return False

def get_all_gemini_keys() -> list[str]:
    """Собирает основной и все запасные ключи Gemini в единый пул."""
    keys = []
    main_k = os.getenv("GEMINI_API_KEY", "").strip()
    if main_k:
        keys.append(main_k)
    backup_str = os.getenv("GEMINI_BACKUP_KEYS", "") or os.getenv("GEMINI_API_KEYS", "")
    for k in backup_str.split(","):
        k = k.strip()
        if k and k not in keys:
            keys.append(k)
    return keys

def ask_gemini_cascade(prompt: str, system_prompt: str, primary_model: str, temperature: float = 0.7) -> tuple[str, str]:
    gemini_keys = get_all_gemini_keys()
    if not gemini_keys:
        raise ValueError("Нет доступных ключей GEMINI_API_KEY")

    candidates = [primary_model] if primary_model else []
    for fallback in ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"]:
        if fallback not in candidates:
            candidates.append(fallback)

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature}
    }

    # Перебор пула ключей и линейки моделей
    for key_idx, key in enumerate(gemini_keys, 1):
        for model in candidates:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            try:
                r = requests.post(url, json=payload, timeout=20)
                if r.status_code == 200:
                    data = r.json()
                    if "candidates" in data and len(data["candidates"]) > 0:
                        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        if not _has_garbage(text):
                            key_tag = f" [Ключ #{key_idx}]" if len(gemini_keys) > 1 else ""
                            return text, f"Gemini ({model}){key_tag}"
                elif r.status_code in (429, 503):
                    log.warning(f"⚠️ Gemini {model} на ключе #{key_idx} лимит/перегруз ({r.status_code}). Пробую дальше...")
                    time.sleep(1)
                    continue
            except Exception as e:
                log.warning(f"Gemini {model} ошибка: {e}")
                continue

    raise RuntimeError("Все ключи и модели Gemini временно исчерпаны")

def ask_openrouter(prompt: str, system_prompt: str, model_id: str, temperature: float = 0.7) -> tuple[str, str]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY отсутствует")
        
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key, timeout=25)
    for attempt in range(2):
        try:
            r = client.chat.completions.create(
                model=model_id or "z-ai/glm-5.2:free",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=temperature
            )
            content = r.choices[0].message.content.strip()
            if _has_garbage(content):
                raise ValueError(f"OpenRouter {model_id} вернул мусорные токены")
            return content, f"OpenRouter ({model_id})"
        except Exception as e:
            if "429" in str(e) and attempt == 0:
                time.sleep(3)
                continue
            raise

def ask_llm(prompt: str, system_prompt: str = "Ты — ИИ-QA инженер и аналитик.", temperature: float = 0.7) -> tuple[str, str]:
    active = get_active_models()
    
    # 1. Пул ключей Gemini (3.8 -> 3.7 -> 3.6)
    try:
        return ask_gemini_cascade(prompt, system_prompt, active.get("gemini"), temperature=temperature)
    except Exception as e:
        log.warning(f"⚠️ [Fallback] Пул Gemini сбой ({e}), переход на OpenRouter...")

    # 2. Резерв: OpenRouter
    primary_or = active.get("openrouter_primary", "z-ai/glm-5.2:free")
    try:
        return ask_openrouter(prompt, system_prompt, primary_or, temperature=temperature)
    except Exception as e:
        log.warning(f"⚠️ [Fallback] OpenRouter сбой ({e}), перебор бэкапов...")

    for backup_model in active.get("openrouter_backups", []):
        try:
            return ask_openrouter(prompt, system_prompt, backup_model, temperature=temperature)
        except Exception:
            continue

    return "❌ Все провайдеры ИИ временно недоступны.", "None"

def ask(prompt: str, system: str = "Ты — модератор сообщества.", max_tokens: int = 500, temperature: float = 0.7) -> str:
    content, _ = ask_llm(prompt, system_prompt=system, temperature=temperature)
    return content
