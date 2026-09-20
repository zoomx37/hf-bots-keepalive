import os
import re
import logging
import requests
from openai import OpenAI
from modelcatalog import get_active_models

log = logging.getLogger("llm")

def _has_garbage(text: str) -> bool:
    """Проверяет наличие китайских/мусорных иероглифов (сбой Llama на OpenRouter)"""
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
        raise ValueError("Модель Gemini не найдена в API")

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
    raise RuntimeError(f"Gemini {model_id} вернул {r.status_code}: {r.text[:100]}")

def ask_groq(prompt: str, system_prompt: str, model_id: str) -> tuple[str, str]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GROQ_API_KEY отсутствует")
    if not model_id:
        raise ValueError("Модель Groq не найдена")
        
    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key, timeout=20)
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
        raise ValueError("Groq вернул мусорные токены")
    return content, f"Groq ({model_id})"

def ask_openrouter(prompt: str, system_prompt: str, model_id: str) -> tuple[str, str]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY отсутствует")
        
    model = model_id or "meta-llama/llama-3.3-70b-instruct"
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key, timeout=20)
    r = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1000
    )
    content = r.choices[0].message.content.strip()
    if _has_garbage(content):
        raise ValueError("OpenRouter вернул мусорные токены")
    return content, f"OpenRouter ({model})"

def ask_llm(prompt: str, system_prompt: str = "Ты — ИИ-QA инженер и аналитик.") -> tuple[str, str]:
    """Автоматическая цепочка с моделями из живого каталога API: Gemini ➔ Groq ➔ OpenRouter."""
    active = get_active_models()
    
    # 1. Сначала Gemini из каталога
    if active.get("gemini"):
        try:
            return ask_gemini_direct(prompt, system_prompt, active["gemini"])
        except Exception as e:
            log.warning(f"⚠️ [Fallback] Gemini сбой ({e}), переход на Groq...")

    # 2. Резерв Groq из каталога
    if active.get("groq"):
        try:
            return ask_groq(prompt, system_prompt, active["groq"])
        except Exception as e:
            log.warning(f"⚠️ [Fallback] Groq сбой ({e}), переход на OpenRouter...")

    # 3. Аварийный OpenRouter
    try:
        return ask_openrouter(prompt, system_prompt, active.get("openrouter"))
    except Exception as e:
        log.warning(f"⚠️ [Fallback] OpenRouter сбой ({e}).")

    return "❌ Все провайдеры ИИ временно недоступны.", "None"

def ask(prompt: str, system: str = "Ты — модератор сообщества.", max_tokens: int = 500) -> str:
    content, _ = ask_llm(prompt, system_prompt=system)
    return content
