import os
import requests
from openai import OpenAI

def ask_gemini_direct(prompt: str, system_prompt: str) -> str:
    """Прямой вызов Google Gemini REST API (1-й приоритет)."""
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
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip(), f"Gemini ({model})"
        except Exception:
            continue
    raise RuntimeError("Gemini API не ответил")

def ask_groq(prompt: str, system_prompt: str) -> str:
    """Вызов Groq Cloud (2-й приоритет)."""
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
    return r.choices[0].message.content.strip(), "Groq (llama-3.3-70b)"

def ask_openrouter(prompt: str, system_prompt: str) -> str:
    """Вызов OpenRouter (3-й приоритет)."""
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
    return r.choices[0].message.content.strip(), "OpenRouter (llama-3.3)"

def ask_llm(prompt: str, system_prompt: str = "Ты — ИИ-QA инженер и аналитик.") -> tuple[str, str]:
    """Автоматическая отказоустойчивая цепочка: Gemini ➔ Groq ➔ OpenRouter."""
    # 1. Пробуем Gemini
    try:
        return ask_gemini_direct(prompt, system_prompt)
    except Exception as e:
        print(f"⚠️ [Fallback] Gemini сбой ({e}), переключаюсь на Groq...")

    # 2. Пробуем Groq
    try:
        return ask_groq(prompt, system_prompt)
    except Exception as e:
        print(f"⚠️ [Fallback] Groq сбой ({e}), переключаюсь на OpenRouter...")

    # 3. Пробуем OpenRouter

    def ask(prompt: str, system: str = "Ты — модератор сообщества.", max_tokens: int = 500) -> str:
    """Адаптер для вызова ИИ из moderator.py"""
    content, _ = ask_llm(prompt, system_prompt=system)
    return content
    try:
        return ask_openrouter(prompt, system_prompt)
    except Exception as e:
        print(f"⚠️ [Fallback] OpenRouter сбой ({e}).")

    return "❌ Все провайдеры ИИ временно недоступны.", "None"
