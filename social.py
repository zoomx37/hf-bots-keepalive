import os
import re
import sqlite3
import logging
from llm import ask
from notifier import notify
import vkrate

log = logging.getLogger("social")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")

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

def search_vk_candidates(city_name: str, age_from: int, age_to: int, sex: str = "all", count: int = 8) -> list:
    """Поиск подходящих открытых профилей в ВК по параметрам."""
    token = os.getenv("VK_TOKEN", "").strip()
    if not token:
        return []
    try:
        session = vkrate.get_vk_session(token)
        # 1. Поиск города
        cities = vkrate.vk_call(session, "database.getCities", q=city_name, country_id=1).get("items", [])
        city_id = cities[0]["id"] if cities else None

        # 2. Определение пола (1 — женский, 2 — мужской, 0 — любой)
        sex_code = 1 if sex.lower() in ["ж", "f", "жен"] else (2 if sex.lower() in ["м", "m", "муж"] else 0)

        params = {
            "count": count,
            "age_from": age_from,
            "age_to": age_to,
            "sex": sex_code,
            "has_photo": 1,
            "can_write_private_message": 1,
            "fields": "city,bdate,about,interests,activities"
        }
        if city_id:
            params["city"] = city_id

        res = vkrate.vk_call(session, "users.search", **params)
        return res.get("items", [])
    except Exception as e:
        log.error(f"Ошибка поиска кандидатов ВК: {e}")
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
    """
    Генератор ответов с ЖЕСТКИМ ПРАВИЛОМ: 
    Не называть себя ботом, но и не врать. При вопросах о боте — сигнал админу!
    """
    c = db()
    row = c.execute("SELECT stage, task, name FROM candidates WHERE uid=? AND platform=?", (str(sender_id), platform)).fetchone()
    c.close()

    task_context = f"Цель диалога: {row[1]}" if row else "Цель: лёгкое, интересное общение, подогрев симпатии, перевод к свиданию или боту."

    # ПРОВЕРКА НА ПРЯМОЙ ВОПРОС «ТЫ БОТ?»
    bot_triggers = ["ты бот", "ты робот", "ты человек", "ты реальный", "ты ии", "ты программа", "ты фейк"]
    if any(t in message_text.lower() for t in bot_triggers):
        # Эскалация админу в ту же секунду!
        notify(
            f"🚨 <b>[ВНИМАНИЕ: ВОПРОС О БОТЕ!]</b>\n"
            f"Собеседник ID <code>{sender_id}</code> ({platform}) спросил:\n«{message_text}»\n\n"
            f"👉 <i>Вы можете перехватить диалог и ответить лично:</i>\n<code>/say {sender_id} Ваш ответ</code>"
        )
        # Ответ-уклонение: с юмором переводим стрелки, не подтверждая и не отрицая
        prompt_evade = f"Собеседник спросил: '{message_text}'. Твоя задача: остроумно, с легким кокетством отшутиться и перевести разговор на него. " \
                       f"НЕ говори, что ты ИИ/робот, но и НЕ утверждай сухо 'я человек'. Сделай это стильно и с шармом!"
        reply = ask(prompt_evade, system="Ты остроумный собеседник с безупречным чувством юмора.", max_tokens=150)
        return reply

    # ПРОВЕРКА 18+ (Сигналы несовершеннолетия)
    minor_triggers = ["мне 14", "мне 15", "мне 16", "мне 17", "в школу", "уроки", "9 класс", "10 класс", "11 класс"]
    if any(m in message_text.lower() for m in minor_triggers):
        notify(f"⛔ <b>[СТОП 18+]</b> Собеседник {sender_id} упомянул несовершеннолетний возраст: «{message_text}». Диалог заморожен.")
        return "Приятно было пообщаться, но я общаюсь только со взрослой аудиторией 18+. Удачи тебе в учебе! 😉"

    # ПРОВЕРКА РОМАНТИЧЕСКОЙ ПРИВЯЗАННОСТИ К АГЕНТУ
    love_triggers = ["я тебя люблю", "выходи за меня", "хочу быть с тобой", "влюбился в тебя", "влюбилась в тебя", "ты мне нравишься безумно"]
    if any(l in message_text.lower() for l in love_triggers):
        notify(
            f"💘 <b>[СИЛЬНАЯ СИМПАТИЯ]</b> Собеседник {sender_id} признался в чувствах: «{message_text}».\n"
            f"Перехватите диалог: <code>/say {sender_id} Текст</code>"
        )
        return "Ого, какие признания! Ты умеешь удивить с порога 😌 Но давай не спешить с выводами, мы ведь только знакомимся. Расскажи лучше, что тебя обычно цепляет в людях?"

    # СТАНДАРТНЫЙ ДИАЛОГ «НА ПРИКОЛЕ»
    system_social = (
        f"Ты ведёшь личную переписку от имени стильного, обаятельного парня/девушки. {task_context} "
        "ПРАВИЛА:\n"
        "1. Пиши живо, тепло, с юмором и легким флиртом. Используй современный сленг в меру (без перегиба).\n"
        "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать 'Я бот', 'Я ИИ', 'Я программа'. Но и не выдумывай паспортные данные.\n"
        "3. Никаких просьб денег, паролей, согласий на реальные встречи или звонки прямо сейчас.\n"
        "4. Поддерживай интерес, задавай цепляющие встречные вопросы."
    )
    return ask(f"Сообщение от собеседника: '{message_text}'", system=system_social, max_tokens=250)
