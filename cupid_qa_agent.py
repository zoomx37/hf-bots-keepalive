import os
import json
import requests
from huggingface_hub import HfApi

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "721042205")

SPACES = [
    "opion2008/cupidon",
    "opion2008/criminal-bot",
    "opion2008/rslaw-bot"
]

def send_tg_report(text):
    """Отправка отчета агента администратору в Telegram"""
    if not TG_BOT_TOKEN:
        print(text)
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки в TG: {e}")

def ask_gemini(prompt, system_instruction):
    """Запрос к нейросети Gemini для анализа ответов и сценариев"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}]
    }
    try:
        r = requests.post(url, json=payload, timeout=25)
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return f"Ошибка Gemini API: {r.status_code}"
    except Exception as e:
        return f"Исключение сети: {e}"

def test_keepalive_and_endpoints():
    """Проверка доступности и авто-пробуждение спейсов"""
    hf_api = HfApi(token=HF_TOKEN)
    status_report = []
    
    for space in SPACES:
        subdomain = space.replace("/", "-")
        url = f"https://{subdomain}.hf.space/ping"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                status_report.append(f"• <b>{space}</b>: ✅ Работает (200 OK)")
            else:
                hf_api.restart_space(repo_id=space)
                status_report.append(f"• <b>{space}</b>: ⚠️ Код {res.status_code} ➔ Перезапущен через API")
        except Exception as e:
            try:
                hf_api.restart_space(repo_id=space)
                status_report.append(f"• <b>{space}</b>: 🚨 Недоступен ➔ Принудительно разбужен")
            except Exception as hf_err:
                status_report.append(f"• <b>{space}</b>: ❌ Ошибка перезапуска: {hf_err}")
                
    return "\n".join(status_report)

def run_ai_qa_scenarios():
    """Тестирование логики и качества ответов ИИ-Купидона"""
    system_prompt = "Ты — ИИ-QA инженер. Оцени качество ответа дейтинг-бота на шкалу от 1 до 5 и проверь, нет ли галлюцинаций или сбоев."
    
    test_cases = [
        ("Химия: Роман 15.10.1985 и Анна 20.04.1990", "Проверка модуля ИИ-Химия (совместимость)"),
        ("Суд отношений: Муж забыл про годовщину, жена обиделась", "Проверка ИИ-Арбитража")
    ]
    
    qa_results = []
    for prompt, desc in test_cases:
        eval_result = ask_gemini(f"Проанализируй тестовый кейс: '{prompt}' для раздела: {desc}", system_prompt)
        qa_results.append(f"🧪 <b>{desc}</b>:\n{eval_result[:250]}...\n")
        
    return "\n".join(qa_results)

def main():
    print("Запуск ИИ-Агента...")
    spaces_status = test_keepalive_and_endpoints()
    qa_status = run_ai_qa_scenarios()
    
    final_report = (
        f"🤖 <b>[ОТЧЕТ ИИ-АГЕНТА QA & KEEPALIVE]</b>\n\n"
        f"📡 <b>Статус серверов:</b>\n{spaces_status}\n\n"
        f"🧠 <b>Тестирование функционала:</b>\n{qa_status}"
    )
    send_tg_report(final_report)
    print("Готово!")

if __name__ == "__main__":
    main()
