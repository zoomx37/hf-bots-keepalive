import os
import re
import time
import logging
import requests
from openai import OpenAI
from modelcatalog import get_active_models

log = logging.getLogger("llm")
_cooldown = {}  # Кулдаун перегруженных моделей

def _has_garbage(text: str) -> bool:
    if not text:
        return True
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    if cjk >= 2 or (len(text) > 80 and (cjk / len(text)) > 0.015):
        return True
    return False

def get_all_gemini_keys() -> list[str]:
    keys = []
    main_k = os.getenv("GEMINI_API_KEY", "").strip()
    if main_k: keys.append(main_k)
    backup_str = os.getenv("GEMINI_BACKUP_KEYS", "")
    for k in backup_str.split(","):
        k = k.strip()
        if k and k not in keys:
            keys.append(k)
    return keys

def try_gemini_key_model(key: str, model: str, prompt: str, system_prompt: str, temperature: float = 0.7) -> str:
    cd_key = f"{key[-5:]}_{model}"
    if time.time() < _cooldown.get(cd_key, 0):
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature}
    }
    try:
        r = requests.post(url, json=payload, timeout=25)
        if r.status_code == 200:
            data = r.json()
            if "candidates" in data and len(data["candidates"]) > 0:
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if not _has_garbage(text):
                    _cooldown.pop(cd_key, None)
                    return text
        elif r.status_code in (429, 503):
            _cooldown[cd_key] = time.time() + 90
            log.warning(f"⚠️ Gemini {model} ({r.status_code}) — кулдаун 90с")
    except Exception as e:
        log.warning(f"⚠️ Gemini {model} сбой: {e}")
    return None

def ask_openrouter(prompt: str, system_prompt: str, model_id: str, temperature: float = 0.7) -> tuple[str, str]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY отсутствует")
        
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key, timeout=30)
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
        raise ValueError("OpenRouter вернул мусорные токены")
    return content, f"OpenRouter ({model_id})"

def ask_llm(prompt: str, system_prompt: str = "Ты — ИИ-QA инженер и аналитик.", temperature: float = 0.7) -> tuple[str, str]:
    """Быстрое чередование: Gemini #1 -> OpenRouter -> Gemini #2 (без зависаний)."""
    active = get_active_models()
    gemini_keys = get_all_gemini_keys()
    models = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.7-flash"]
    if active.get("gemini") and active["gemini"] not in models:
        models.insert(0, active["gemini"])

    # 1. Быстрая попытка на первом ключе Gemini
    if gemini_keys:
        for m in models:
            res = try_gemini_key_model(gemini_keys[0], m, prompt, system_prompt, temperature)
            if res:
                return res, f"Gemini ({m}) [Ключ #1]"

    # 2. Если на первом ключе 503 — сразу пробуем OpenRouter GLM-5.2 (не ждем 60 секунд)
    primary_or = active.get("openrouter_primary", "z-ai/glm-5.2:free")
    try:
        return ask_openrouter(prompt, system_prompt, primary_or, temperature=temperature)
    except Exception as e:
        log.warning(f"⚠️ [Fallback] OpenRouter сбой ({e}), пробую второй ключ Gemini...")

    # 3. Если есть второй ключ Gemini — пробуем его
    if len(gemini_keys) > 1:
        for m in models:
            res = try_gemini_key_model(gemini_keys[1], m, prompt, system_prompt, temperature)
            if res:
                return res, f"Gemini ({m}) [Ключ #2]"

    # 4. Резервные модели OpenRouter
    for backup_model in active.get("openrouter_backups", []):
        try:
            return ask_openrouter(prompt, system_prompt, backup_model, temperature=temperature)
        except Exception:
            continue

    return "❌ Все провайдеры ИИ временно недоступны.", "None"

def ask(prompt: str, system: str = "Ты — модератор сообщества.", max_tokens: int = 500, temperature: float = 0.7) -> str:
    content, _ = ask_llm(prompt, system_prompt=system, temperature=temperature)
    return content
