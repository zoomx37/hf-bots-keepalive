import os
import re
import sqlite3
import logging
from llm import ask
from notifier import notify
import vkrate

log = logging.getLogger("social")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")

CITIES_MAP = {
    "москва": 1,
    "санкт-петербург": 2,
    "спб": 2,
    "новосибирск": 99,
    "екатеринбург": 49,
    "казань": 60,
    "нижний новгород": 95,
    "краснодар": 72
}

def db():
    c = sqlite3.connect("agent.db")
    c.execute("""CREATE TABLE IF NOT EXISTS candidates(
        uid TEXT PRIMARY KEY,
        platform TEXT,
        name TEXT,
        city TEXT,
        age INT,
        stage INT DEFAULT 1,
        task TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    return c

def search_vk_candidates(city_name: str, age_from: int, age_to: int, sex: str = "ж", vibe: str = "", count: int = 15) -> list:
    """Поиск кандидатов в ВК с обработкой открытых профилей."""
    token = os.getenv("VK_TOKEN", "").strip()
    if not token:
        return []
    try:
        session = vkrate.get_vk_session(token)
        city_lower = city_name.strip().lower()
        city_id = CITIES_MAP.get(city_lower)

        if not city_id:
            try:
                res_cities = vkrate.vk_call(session, "database.getCities", q=city_name, country_id=1).get("items", [])
                if res_cities: city_id = res_cities[0]["id"]
            except Exception:
                city_id = 1  # По умолчанию Москва

        sex_code = 1 if sex.lower() in ["ж", "f", "жен", "девушка"] else (2 if sex.lower() in ["м", "m", "муж", "парень"] else 0)

        params = {
            "count": count,
            "city": city_id,
            "age_from": age_from,
            "age_to": age_to,
            "sex": sex_code,
            "has_photo": 1,
            "fields": "city,bdate,about,interests,activities,can_write_private_message"
        }
        if vibe:
            params["q"] = vibe

        res = vkrate.vk_call(session, "users.search", **params)
        raw_items = res.get("items", [])

        # Фильтруем закрытые профили на уровне Python
        valid_users = []
        for u in raw_items:
            # Если личка закрыта — пропускаем
            if u.get("can_write_private_message") == 0:
                continue
            valid_users.append(u)
            if len(valid_users) >= 6:
                break
                
        return valid_users or raw_items[:6]
    except Exception as e:
        log.error(f"Ошибка поиска ВК: {e}")
        return []

def pick_candidate_task(uid: str, platform: str, task: str, name: str = ""):
    c = db()
    c.execute(
        "INSERT OR REPLACE INTO candidates (uid, platform, name, stage, task) VALUES (?, ?, ?, 1, ?)",
        (str(uid), platform, name, task)
    )
    c.commit()
    c.close()

def generate_dating_reply(sender_id: str, platform: str, message_text: str) -> str:
    c = db()
    row = c.execute("SELECT stage, task, name FROM candidates WHERE uid=? AND platform=?", (str(sender_id), platform)).fetchone()
    c.close()

    task_context = f"Цель диалога: {row[1]}" if row else "Цель: лёгкое, интересное общение, подогрев симпатии, перевод к боту или встрече."

    # 1. ПРОВЕРКА НА ВОПРОС «ТЫ БОТ / ЧЕЛОВЕК?»
    bot_triggers = ["ты бот", "ты робот", "ты человек", "ты реальный", "ты ии", "ты программа", "ты фейк"]
    if any(t in message_text.lower() for t in bot_triggers):
        notify(
            f"🚨 <b>[ВНИМАНИЕ: ВОПРОС О БОТЕ!]</b>\n"
            f"Собеседник ID <code>{sender_id}</code> ({platform}) спросил:\n«{message_text}»\n\n"
            f"👉 <i>Ответить лично:</i>\n<code>/say {sender_id} Ваш ответ</code>"
        )
        prompt_evade = f"Собеседник спросил: '{message_text}'. Твоя задача: остроумно, с легким кокетством отшутиться и перевести разговор на собеседника. " \
                       f"НЕ говори, что ты ИИ/бот, но и НЕ утверждай сухо 'я человек'. Сделай это стильно и с шармом!"
        return ask(prompt_evade, system="Ты остроумный собеседник с безупречным чувством юмора.", max_tokens=150)

    # 2. ПРОВЕРКА 18+
    minor_triggers = ["мне 14", "мне 15", "мне 16", "мне 17", "в школу", "уроки", "9 класс", "10 класс", "11 класс"]
    if any(m in message_text.lower() for m in minor_triggers):
        notify(f"⛔ <b>[СТОП 18+]</b> Собеседник {sender_id} упомянул несовершеннолетний возраст: «{message_text}». Диалог заморожен.")
        return "Приятно было пообщаться, но я общаюсь только со взрослой аудиторией 18+. Успехов тебе! 😉"

    # 3. ПРОВЕРКА ВЛЮБЛЁННОСТИ / ПРИВЯЗАННОСТИ
    love_triggers = ["я тебя люблю", "выходи за меня", "хочу быть с тобой", "влюбился", "влюбилась", "ты мне нравишься безумно"]
    if any(l in message_text.lower() for l in love_triggers):
        notify(
            f"💘 <b>[СИЛЬНАЯ СИМПАТИЯ]</b> Собеседник {sender_id} признался в чувствах: «{message_text}».\n"
            f"Перехватите диалог: <code>/say {sender_id} Текст</code>"
        )
        return "Ого, какие признания с порога 😌 Но давай не спешить, мы ведь только знакомимся. Расскажи лучше, что тебя обычно по-настоящему вдохновляет?"

    # 4. ОБЫЧНЫЙ ДИАЛОГ «НА ПРИКОЛЕ»
    system_social = (
        f"Ты ведёшь переписку от имени обаятельного человека. {task_context} "
        "ПРАВИЛА:\n"
        "1. Пиши живо, тепло, с юмором и легким флиртом. Используй современный сленг к месту.\n"
        "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать 'Я бот', 'Я ИИ'. Не выдумывай паспортные данные.\n"
        "3. Никаких просьб денег, согласий на встречи прямо сейчас.\n"
        "4. Поддерживай интерес, задавай открытые вопросы."
    )
    return ask(f"Сообщение от собеседника: '{message_text}'", system=system_social, max_tokens=250)
