import os
from openai import OpenAI

PROVIDERS = [
    ("Gemini", "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY", "gemini-2.0-flash"),
    ("Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
    ("OpenRouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "meta-llama/llama-3.3-70b-instruct:free"),
]

def ask_llm(prompt: str, system_prompt: str = "Ты — ИИ-QA инженер и аналитик.", max_tokens: int = 2000) -> tuple[str, str]:
    """Отправляет запрос к ИИ с автоматическим перебором резервных моделей при сбое."""
    last_error = None
    for name, base_url, key_env, model in PROVIDERS:
        api_key = os.getenv(key_env)
        if not api_key:
            continue
        try:
            client = OpenAI(base_url=base_url, api_key=api_key, timeout=30)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens
            )
            content = response.choices[0].message.content.strip()
            return content, f"{name} ({model})"
        except Exception as e:
            last_error = e
            print(f"⚠️ [LLM Fallback] Провайдер {name} недоступен ({e}), переключаюсь на резерв...")
            continue
            
    return f"❌ Ошибка: все провайдеры ИИ недоступны ({last_error})", "None"
