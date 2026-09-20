import os
import re
import time
import logging
import requests
from openai import OpenAI
from modelcatalog import get_active_models

log = logging.getLogger("llm")

def _has_garbage(text: str) -> bool:
    """Отсекает мусорные иероглифы и битые токены."""
    if not text:
        return True
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    if cjk >= 2 or (len(text) > 80 and (cjk / len(text)) > 0.015):
        return True
    return False

def ask_gemini_cascade(prompt: str, system_prompt: str, primary_model: str) -> tuple[str, str]:
    """
    Каскадный опрос линейки Gemini: пробует 3.8 -> при 503/429 переключается на 3.7 -> затем на 3.6.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY отсутствует")

    candidates = [primary_model] if primary_model else []
    for fallback in ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"]:
        if fallback not in candidates:
            candidates.append(fallback)

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}]
    }

    last_err = None
    for model in candidates:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if "candidates" in data and len(data["candidates"]) > 0:
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if not _has_garbage(text):
                        return text, f"Gemini ({model})"
                    else:
                        log.warning(f"Gemini {model} вернул мусорный текст")
            elif r.status_code in (503, 429):
                log.warning(f"⚠️ Gemini {model} пиковая нагрузка (код {r.status_code}). Пробую резервную версию Gemini...")
                time.sleep(1)
                continue
            else:
                log.warning(f"Gemini {model} статус {r.status_code}: {r.text[:100]}")
        except Exception as e:
            last_err = e
            log.warning(f"Gemini {model} сбой сети: {e}")
            continue

    raise RuntimeError(f"Все модели линейки Gemini (3.8/3.7/3.6) перегружены: {last_err}")

def ask_openrouter(prompt: str, system_prompt: str, model_id: str) -> tuple[str, str]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY отсутствует")
    if not model_id:
        raise ValueError("Модель OpenRouter не указана")
        
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key, timeout=25)
    for attempt in range(2):
        try:
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
        except Exception as e:
            if "429" in str(e) and attempt == 0:
                time.sleep(3)
                continue
            raise

def ask_llm(prompt: str, system_prompt: str = "Ты — ИИ-QA инженер и аналитик.") -> tuple[str, str]:
    """Автоматическая цепочка: Gemini (3.8->3.7->3.6) -> OpenRouter GLM-5.2 -> Живые бэкапы."""
    active = get_active_models()
    
    # 1. Основной мозг: Каскад Gemini 3.8/3.7/3.6
    if active.get("gemini"):
        try:
            return ask_gemini_cascade(prompt, system_prompt, active["gemini"])
        except Exception as e:
            log.warning(f"⚠️ [Fallback] Gemini сбой ({e}), переход на OpenRouter...")

    # 2. Резерв: OpenRouter Primary (z-ai/glm-5.2:free)
    primary_or = active.get("openrouter_primary")
    if primary_or:
        try:
            return ask_openrouter(prompt, system_prompt, primary_or)
        except Exception as e:
            log.warning(f"⚠️ [Fallback] OpenRouter {primary_or} сбой ({e}), перебор бэкапов...")

    # 3. Аварийный резерв: Живые бэкапы OpenRouter
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
