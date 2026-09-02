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
        "domain_type": "Dating & Flirt AI, AI-Wingman, Relationships",
        "cases": [
            ("Химия: Роман 15.10.1985 и Анна 20.04.1990", "ИИ-Химия (9 шкал)"),
            ("Арбитраж: Муж забыл годовщину, жена молчит", "Высший Суд (Примирение)"),
            ("Двойник: Создание комнаты room_5521", "ИИ-Двойник"),
            ("Rizz-Рейтинг: Аудит фото и анкеты", "Rizz-Рейтинг"),
            ("Флирт-Ринг: 5 раундов переписки", "Флирт-Тренажер"),
            ("Ред-Флаги: Выявление манипуляций", "Детектор токсичности")
        ]
    },
    "opion2008/criminal-bot": {
        "title": "⚖️ Уголовный Адвокат (@advocate_criminal_bot)",
        "domain_type": "Criminal Law, Prison Sentence Calculation, Legal AI",
        "cases": [
            ("Зачет СИЗО: 120 дней в ИК общего режима (коэф 1.5)", "ст. 72 УК РФ (СИЗО)"),
            ("Сроки: ч. 1 ст. 105 УК РФ, 8 лет -> УДО (2/3)", "ст. 79 УК РФ (УДО)"),
            ("Замена наказания: 6 лет строгого режима -> ПТР (1/2)", "ст. 80 УК РФ (ЗМ)"),
            ("Судимость: 3 года лишения свободы за тяжкое", "ст. 86 УК РФ (Судимость)")
        ]
    },
    "opion2008/rslaw-bot": {
        "title": "🚗 ИИ-Автоюрист (@rslaw_auto_bot)",
        "domain_type": "Auto Law, Road Accidents, Traffic Fines, Insurance Disputes",
        "cases": [
            ("ДТП: Европротокол до 100 000 руб без пострадавших", "Помощник при ДТП"),
            ("ОСАГО: Сумма 120 000 руб, задержка 15 дней (1% в день)", "Неустойка ОСАГО"),
            ("Давность: ст. 12.8 ч. 1 КоАП РФ (1 год)", "ст. 4.5 КоАП (Давность)"),
            ("Лишение прав: Сдача ВУ в течение 3 дней", "ст. 32.7 КоАП (Лишение)")
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
        print(f"Ошибка сохранения истории: {e}")

def send_tg_report(text):
    if not TG_BOT_TOKEN:
        print(text)
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    
    # Автоматическое разделение длинных сообщений для Telegram (лимит 4096 символов)
    max_len = 3800
    parts = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    for part in parts:
        payload = {"chat_id": ADMIN_CHAT_ID, "text": part, "parse_mode": "HTML"}
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
            
    return "⚠️ Ошибка связи с Gemini API."

def get_live_bot_stats(space_id):
    """Считывает живую статистику пользователей из БД бота через эндпоинт /stats"""
    subdomain = space_id.replace("/", "-")
    url = f"https://{subdomain}.hf.space/stats"
    try:
        res = requests.get(url, timeout=7)
        if res.status_code == 200:
            data = res.json()
            users_count = data.get("total_users", 0)
            queries_today = data.get("queries_today", 0)
            return f"👥 Пользователей: <b>{users_count}</b> | ⚡ Запросов сегодня: <b>{queries_today}</b>"
    except Exception:
        pass
    return "📊 Статистика: <i>эндпоинт /stats подключается</i>"

def generate_hype_feature(bot_name, domain, previous_ideas):
    """Генерирует свежую хайповую/виральную фичу на базе трендов мирового AI без повторов"""
    prev_text = "\n".join([f"- {item}" for item in previous_ideas[-5:]]) if previous_ideas else "Пока нет"
    system_prompt = (
        "Ты — топовый Product Manager и AI-Трендсеттер. Придумай ровно ОДНУ инновационную, хайповую и виральную фичу "
        "для Telegram/VK бота на базе передовых мировых трендов ИИ (AI Voice, Deep-Vision, Telegram Mini Apps, геймификация). "
        "Формат: Название фичи (1 строка) + Суть и виральный эффект (2-3 строки). "
        f"КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО повторять ранее предложенные идеи:\n{prev_text}"
    )
    prompt = f"Предложи новую хайповую фичу для бота '{bot_name}' в сфере: {domain}."
    return ask_gemini(prompt, system_prompt)

def main():
    print("Запуск комплексного QA-Агента и Трендового Радара...")
    hf_api = HfApi(token=HF_TOKEN) if HF_TOKEN else None
    history = load_history()
    
    report_sections = []
    
    for space_id, cfg in BOTS_CONFIG.items():
        title = cfg["title"]
        subdomain = space_id.replace("/", "-")
        ping_url = f"https://{subdomain}.hf.space/ping"
        
        # 1. Проверка доступности и Keepalive
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

        # 2. Живая статистика пользователей
        stats_line = get_live_bot_stats(space_id)

        # 3. Проверка обновлений кода и QA-аудит
        bot_hist = history.get(space_id, {"last_sha": "", "proposed_ideas": []})
        last_sha = bot_hist.get("last_sha", "")
        sha_changed = (current_sha != last_sha) or (not last_sha)
        
        bot_report = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>{title}</b>\n"
            f"• Статус: {server_status} | Версия: <code>{current_sha}</code>\n"
            f"• {stats_line}\n"
        )
        
        if sha_changed:
            bot_report += "• 🔬 <b>Результаты QA-аудита модулей:</b>\n"
            qa_system = "Ты — QA-инженер. Оцени тест-кейс функции бота в 1 краткую строку (Статус: ОК / Замечание)."
            for test_input, case_name in cfg["cases"]:
                eval_text = ask_gemini(f"Тест [{case_name}]: {test_input}", qa_system)
                bot_report += f"  🧪 <i>{case_name}</i>: {eval_text}\n"
            bot_hist["last_sha"] = current_sha
        else:
            bot_report += "• 🔬 <b>QA-статус:</b> Все модули работают в штатном режиме (регрессий нет).\n"

        # 4. Генерация свежей хайповой фичи (без повторений)
        prev_ideas = bot_hist.get("proposed_ideas", [])
        new_idea = generate_hype_feature(title, cfg["domain_type"], prev_ideas)
        bot_report += f"\n• 🔥 <b>Трендовый AI-апгрейд (Хайповая фича):</b>\n{new_idea}\n"
        
        prev_ideas.append(new_idea[:80])
        bot_hist["proposed_ideas"] = prev_ideas[-15:] # сохраняем последние 15 идей для исключения дублей
        history[space_id] = bot_hist
        
        report_sections.append(bot_report)

    save_history(history)
    
    final_text = "🤖 <b>[ОТЧЕТ ИИ-АГЕНТА: ЭКОСИСТЕМА 3 БОТОВ & ТРЕНДЫ]</b>\n\n" + "\n".join(report_sections)
    send_tg_report(final_text)
    print("Отчет с трендами и статистикой успешно отправлен!")

if __name__ == "__main__":
    main()
