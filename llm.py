import os
import re
import logging
import requests
from openai import OpenAI
from modelcatalog import get_active_models

log = logging.getLogger("llm")

def _has_garbage(text: str) -> bool:
    """Отсекает мусорные токены и иероглифы (сбой Llama)"""
    if not text:
        return True
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    if cjk >= 2 or (len(text) > 80 and (cjk / len(text)) > 0.015):
        return True
    return False

def ask_gemini_direct(prompt: str, system_prompt: str, model_id: str) -> tuple[str, str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY отсутствует")
    if not model_id:
        raise ValueError("Модель Gemini не найдена")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}]
    }
    
    r = requests.post(url, json=payload, timeout=25)
    if r.status_code == 200:
        data = r.json()
        if "candidates" in data and len(data["candidates"]) > 0:
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if not _has_garbage(text):
                return text, f"Gemini ({model_id})"
            else:
                raise ValueError(f"Gemini {model_id} вернул мусорные токены")
    raise RuntimeError(f"Gemini {model_id} статус {r.status_code}: {r.text[:120]}")

def ask_openrouter(prompt: str, system_prompt: str, model_id: str) -> tuple[str, str]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY отсутствует")
    if not model_id:
        raise ValueError("Модель OpenRouter не указана")
        
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key, timeout=25)
    r = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1000
    )
    content = r.choices[0].message.content.strip()
    if _has_garbage(content):
        raise ValueError(f"OpenRouter {model_id} вернул мусорные токены")
    return content, f"OpenRouter ({model_id})"

def ask_llm(prompt: str, system_prompt: str = "Ты — ИИ-QA инженер и аналитик.") -> tuple[str, str]:
    """Автоматическая цепочка: Gemini 3.8 -> OpenRouter GLM-5.2 -> OpenRouter Резерв."""
    active = get_active_models()
    
    # 1. Основной мозг: Gemini 3.8 Flash
    if active.get("gemini"):
        try:
            return ask_gemini_direct(prompt, system_prompt, active["gemini"])
        except Exception as e:
            log.warning(f"⚠️ [Fallback] Gemini {active['gemini']} сбой ({e}), переход на OpenRouter...")

    # 2. Резерв: OpenRouter Primary (z-ai/glm-5.2:free)
    primary_or = active.get("openrouter_primary")
    if primary_or:
        try:
            return ask_openrouter(prompt, system_prompt, primary_or)
        except Exception as e:
            log.warning(f"⚠️ [Fallback] OpenRouter {primary_or} сбой ({e}), перебор бэкапов...")

    # 3. Аварийный резерв: OpenRouter Backups
    for backup_model in active.get("openrouter_backups", []):
        try:
            return ask_openrouter(prompt, system_prompt, backup_model)
        except Exception as e:
            log.warning(f"⚠️ [Fallback] OpenRouter {backup_model} сбой ({e})...")
            continue

    return "❌ Все провайдеры ИИ временно недоступны.", "None"

def ask(prompt: str, system: str = "Ты — модератор сообщества.", max_tokens: int = 500) -> str:
    content, _ = ask_llm(prompt, system_prompt=system)
    return content
