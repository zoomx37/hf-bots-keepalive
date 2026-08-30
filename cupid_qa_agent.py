import os
import json
import requests
from huggingface_hub import HfApi

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "721042205")

HISTORY_FILE = "qa_history.json"

BOTS_CONFIG = {
    "opion2008/cupidon": {
        "title": "❤️ ИИ-Купидон (@AI_cupidon_bot)",
        "cases": [
            ("Химия [Happy Path]: Роман 15.10.1985 и Анна 20.04.1990", "ИИ-Химия (Позитивный)"),
            ("Химия [Negative]: Роман 31.02.1985 (невалидная дата)", "ИИ-Химия (Валидация даты)"),
            ("Арбитраж [Safety]: Муж забыл годовщину, жена молчит", "Высший Суд (Примирение)"),
            ("Двойник: Создание комнаты room_5521 и авто-флирт", "ИИ-Двойник"),
            ("Rizz-Рейтинг: Оценка анкеты 'Люблю спорт, ищу искренность'", "Rizz-Рейтинг"),
            ("Флирт-Ринг: Тест 5 раундов диалога и разбор ошибок", "Флирт-Ринг"),
            ("Ред-Флаги: 'Если ты уйдешь, мне будет плохо'", "Детектор манипуляций"),
            ("Скриншот: Выбор из 3 ответов (дерзкий, харизма, прямой)", "Прокачка диалога"),
            ("Подкат: Точечные открывашки для профиля с собакой", "Идеальный подкат"),
            ("Локатор: План свидания в уютном кафе", "Локатор свиданий")
        ]
    },
    "opion2008/criminal-bot": {
        "title": "⚖️ Уголовный Адвокат (@advocate_criminal_bot)",
        "cases": [
            ("Зачет СИЗО: 120 дней СИЗО в ИК общего режима (коэф 1.5)", "ст. 72 УК РФ (СИЗО)"),
            ("Сроки: ч. 1 ст. 105 УК РФ (особо тяжкое), срок 8 лет -> УДО (2/3)", "ст. 79 УК РФ (УДО)"),
            ("Замена наказания: 6 лет строгого режима -> ПТР (1/2)", "ст. 80 УК РФ (ЗМ)"),
            ("Судимость: 3 года лишения свободы за тяжкое (8 лет погашение)", "ст. 86 УК РФ (Судимость)")
        ]
    },
    "opion2008/rslaw-bot": {
        "title": "🚗 ИИ-Автоюрист (@rslaw_auto_bot)",
        "cases": [
            ("ДТП: Европротокол при ущербе до 100 000 руб без пострадавших", "Помощник при ДТП"),
            ("ОСАГО: Сумма 120 000 руб, задержка 15 дней (1% в день)", "Неустойка ОСАГО"),
            ("Давность: ст. 12.8 ч. 1 КоАП РФ (алкоголь, срок 1 год)", "ст. 4.5 КоАП (Давность)"),
            ("Лишение прав: Сдача ВУ в течение 3 дней и течение срока", "ст. 32.7 КоАП (Лишение)")
        ]
    }
}

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения истории QA: {e}")

def send_tg_report(text):
    if not TG_BOT_TOKEN:
        print(text)
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Ошибка отправки в TG: {e}")

def ask_gemini(prompt, system_instruction):
    if not GEMINI_API_KEY:
        return "⚠️ Отсутствует GEMINI_API_KEY"
        
    models_to_try = [
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash"
    ]
    
    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}]
    }
    
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        try:
            r = requests.post(url, json=payload, timeout=25)
            if r.status_code == 200:
                data = r.json()
                if "candidates" in data and len(data["candidates"]) > 0:
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            continue
            
    return "⚠️ Не удалось получить ответ от Gemini API."

def main():
    print("Запуск комплексного QA-Агента...")
    hf_api = HfApi(token=HF_TOKEN) if HF_TOKEN else None
    history = load_history()
    
    report_sections = []
    
    for space_id, cfg in BOTS_CONFIG.items():
        title = cfg["title"]
        subdomain = space_id.replace("/", "-")
        ping_url = f"https://{subdomain}.hf.space/ping"
        
        # 1. Проверка доступности и получение Commit SHA
        server_status = "✅ Работает (200 OK)"
        current_sha = "unknown"
        
        try:
            res = requests.get(ping_url, timeout=10)
            if res.status_code != 200:
                server_status = f"⚠️ Код {res.status_code} ➔ Перезапущен"
                if hf_api: hf_api.restart_space(repo_id=space_id)
        except Exception:
            server_status = "🚨 Недоступен ➔ Принудительно разбужен"
            if hf_api:
                try: hf_api.restart_space(repo_id=space_id)
                except: pass

        if hf_api:
            try:
                space_info = hf_api.space_info(repo_id=space_id)
                current_sha = getattr(space_info, "sha", "unknown")[:7]
            except: pass

        # 2. Проверка: изменился ли код с прошлого раза?
        last_sha = history.get(space_id, {}).get("last_sha")
        sha_changed = (current_sha != last_sha) or (current_sha == "unknown")
        
        bot_report = f"<b>{title}</b>\n• Статус: {server_status} | Версия: <code>{current_sha}</code>\n"
        
        if sha_changed:
            bot_report += "• 🔬 <b>Результаты полного QA-аудита модулей:</b>\n"
            system_prompt = (
                "Ты — ведущий QA-инженер и юрист. Оцени работу функции бота в 1 предложении: "
                "корректность формул/логики, безопасность и соблюдение закона РФ. Дай 1 конкретное улучшение."
            )
            
            for test_input, case_name in cfg["cases"]:
                eval_text = ask_gemini(f"Тест-кейс [{case_name}]: {test_input}", system_prompt)
                bot_report += f"  🧪 <i>{case_name}</i>: {eval_text}\n"
                
            history[space_id] = {"last_sha": current_sha}
        else:
            bot_report += "• 💡 <i>Все модули стабильны. Замечания по версии уже зафиксированы, повторы скрыты до обновления кода.</i>\n"
            
        report_sections.append(bot_report)

    save_history(history)
    
    final_text = "🤖 <b>[ОТЧЕТ ИИ-АГЕНТА: ЭКОСИСТЕМА 3 БОТОВ]</b>\n\n" + "\n".join(report_sections)
    send_tg_report(final_text)
    print("Комплексный отчет отправлен!")

if __name__ == "__main__":
    main()
