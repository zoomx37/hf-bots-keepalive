import os
import re
import logging
import requests
from openai import OpenAI

log = logging.getLogger("llm")

def _has_garbage(text: str) -> bool:
    """Проверяет наличие китайских/мусорных иероглифов в тексте (сбой Llama на OpenRouter)"""
    if not text:
        return True
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    if cjk >= 2 or (len(text) > 80 and (cjk / len(text)) > 0.015):
        return True
    return False

def ask_gemini_direct(prompt: str, system_prompt: str) -> tuple[str, str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY отсутствует")

    models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash"]
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}]
    }
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if "candidates" in data and len(data["candidates"]) > 0:
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if not _has_garbage(text):
                        return text, f"Gemini ({model})"
        except Exception:
            continue
    raise RuntimeError("Gemini API не ответил")

def ask_groq(prompt: str, system_prompt: str) -> tuple[str, str]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GROQ_API_KEY отсутствует")
        
    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key, timeout=20)
    r = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1000
    )
    content = r.choices[0].message.content.strip()
    if _has_garbage(content):
        raise ValueError("Groq вернул мусорные токены")
    return content, "Groq (llama-3.3)"

def ask_openrouter(prompt: str, system_prompt: str) -> tuple[str, str]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY отсутствует")
        
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key, timeout=20)
    r = client.chat.completions.create(
        model="meta-llama/llama-3.3-70b-instruct",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1000
    )
    content = r.choices[0].message.content.strip()
    if _has_garbage(content):
        raise ValueError("OpenRouter вернул мусорные токены")
    return content, "OpenRouter (llama-3.3)"

def ask_llm(prompt: str, system_prompt: str = "Ты — ИИ-QA инженер и аналитик.") -> tuple[str, str]:
    # 1. Пробуем Gemini
    try:
        return ask_gemini_direct(prompt, system_prompt)
    except Exception as e:
        log.warning(f"⚠️ [Fallback] Gemini сбой ({e}), переключаюсь на Groq...")

    # 2. Пробуем Groq
    try:
        return ask_groq(prompt, system_prompt)
    except Exception as e:
        log.warning(f"⚠️ [Fallback] Groq сбой ({e}), переключаюсь на OpenRouter...")

    # 3. Пробуем OpenRouter
    try:
        return ask_openrouter(prompt, system_prompt)
    except Exception as e:
        log.warning(f"⚠️ [Fallback] OpenRouter сбой ({e}).")

    return "❌ Все провайдеры ИИ временно недоступны.", "None"

def ask(prompt: str, system: str = "Ты — модератор сообщества.", max_tokens: int = 500) -> str:
    content, _ = ask_llm(prompt, system_prompt=system)
    return content
