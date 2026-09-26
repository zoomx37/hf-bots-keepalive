import os
import re
import json
import time
import sqlite3
import logging
from llm import ask
from notifier import notify
import vkrate

log = logging.getLogger("social")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")

# Локальная база городов (0 лишних вызовов к API ВК!)
CITIES_DB = {
    "москва": 1,
    "санкт-петербург": 2, "спб": 2,
    "ярославль": 169,
    "екатеринбург": 49,
    "новосибирск": 99,
    "казань": 60,
    "нижний новгород": 95,
    "краснодар": 72,
    "самара": 123,
    "ростов-на-дону": 119,
    "уфа": 151,
    "челябинск": 158,
    "сочи": 133,
    "красноярск": 73,
    "пермь": 110,
    "воронеж": 42,
    "волгоград": 39
}

FIND_CACHE = {}

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

def get_city_id(session, city_name: str) -> int:
    name_clean = city_name.strip().lower()
    if name_clean in CITIES_DB:
        return CITIES_DB[name_clean]
    try:
        res = vkrate.vk_call(session, "database.getCities", q=city_name.strip(), country_id=1, count=1)
        items = res.get("items", [])
        if items:
            cid = items[0]["id"]
            CITIES_DB[name_clean] = cid
            return cid
    except Exception as e:
        log.warning(f"Сбой поиска города: {e}")
    return 1

def search_vk_candidates(city_name: str, age_from: int, age_to: int, sex: str = "ж", vibe: str = "") -> list:
    allowed, wait_min = vkrate.can_vk()
    if not allowed:
        raise RuntimeError(f"ВК на паузе предохранителем ещё {wait_min} мин.")

    token = os.getenv("VK_TOKEN", "").strip()
    if not token:
        raise ValueError("VK_TOKEN не задан")

    cache_key = f"{city_name.lower()}|{age_from}-{age_to}|{sex.lower()}"
    now = time.time()

    # 1. Проверяем 30-минутный кэш
    if cache_key in FIND_CACHE and now - FIND_CACHE[cache_key][0] < 1800:
        raw_users = FIND_CACHE[cache_key][1]
    else:
        session = vkrate.get_vk_session(token)
        cid = get_city_id(session, city_name)
        sex_code = 1 if sex.lower() in ["ж", "f", "жен", "девушка", "девушки (ж)"] else (2 if sex.lower() in ["м", "m", "муж", "парень", "парни (м)"] else 0)

        # Чистый поиск по городу без спорных фильтров
        params = {
            "count": 25,
            "city": cid,
            "country": 1,
            "age_from": age_from,
            "age_to": age_to,
            "has_photo": 1,
            "fields": "city,bdate,interests,activities,music,about,status"
        }
        if sex_code > 0:
            params["sex"] = sex_code

        res = vkrate.vk_call(session, "users.search", **params)
        items = res.get("items", [])
        raw_users = [u for u in items if not u.get("is_closed", True)]
        if raw_users:
            FIND_CACHE[cache_key] = (now, raw_users)

    if not raw_users:
        return []

    # 2. Интеллектуальный скоринг совпадения по вайбу через ИИ
    if not vibe or vibe.lower() in ["спорт, юмор", "любой"]:
        return raw_users[:5]

    profiles_text = "\n".join(
        f"{i}. ID={u['id']} {u.get('first_name','')} {u.get('last_name','')}; "
        f"Интересы: {u.get('interests','')}; Деятельность: {u.get('activities','')}; "
        f"О себе: {u.get('about','')}; Статус: {u.get('status','')}"
        for i, u in enumerate(raw_users[:12], 1)
    )

    prompt = (
        f"Искомый вайб / интересы: «{vibe}».\n\n"
        f"Анкеты кандидатов:\n{profiles_text}\n\n"
        "Выбери от 3 до 5 наиболее подходящих анкет по интересам. Ответ выведи СТРОГО в формате JSON-массива:\n"
        '[{"id": 12345, "score": "9/10", "why": "увлекается йогой и здоровым образом жизни"}]'
    )

    try:
        raw_llm = ask(prompt, system="Ты — сваха проекта 'Купидон'. Оцениваешь совпадение по вайбу.", max_tokens=400, temperature=0.3)
        m = re.search(r"\[.*\]", raw_llm, re.DOTALL)
        if m:
            scored = json.loads(m.group(0))
            scored_map = {item["id"]: item for item in scored if "id" in item}
            selected = []
            for u in raw_users:
                if u["id"] in scored_map:
                    u["match_score"] = scored_map[u["id"]].get("score", "8/10")
                    u["match_why"] = scored_map[u["id"]].get("why", "Совпадение по интересам")
                    selected.append(u)
            if selected:
                return selected
    except Exception as e:
        log.warning(f"Ошибка LLM-скоринга: {e}")

    return raw_users[:5]

def pick_candidate_task(uid: str, platform: str, task: str, name: str = ""):
    c = db()
    c.execute(
        "INSERT OR REPLACE INTO candidates (uid, platform, name, stage, task) VALUES (?, ?, ?, 1, ?)",
        (str(uid), platform, name, task)
    )
    c.commit(); c.close()

def generate_dating_reply(sender_id: str, platform: str, message_text: str) -> str:
    c = db()
    row = c.execute("SELECT stage, task, name FROM candidates WHERE uid=? AND platform=?", (str(sender_id), platform)).fetchone()
    c.close()

    task_context = f"Цель диалога: {row[1]}" if row else "Цель: лёгкое, интересное общение, подогрев симпатии, перевод к встрече."

    bot_triggers = ["ты бот", "ты робот", "ты человек", "ты реальный", "ты фейк", "ты ии", "ты программа", "ты нейросеть"]
    if any(t in message_text.lower() for t in bot_triggers):
        notify(
            f"🚨 <b>[ВНИМАНИЕ: ВОПРОС О БОТЕ!]</b>\n"
            f"Собеседник ID <code>{sender_id}</code> ({platform}) спросил:\n«{message_text}»\n\n"
            f"👉 <i>Ответить лично:</i>\n<code>/say {sender_id} Ваш ответ</code>"
        )
        prompt_evade = (
            f"Собеседница спросила: '{message_text}'. "
            "Остроумно, легко и с шармом уйди от прямого ответа, отшутись и переведи разговор на неё. "
            "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО говорить 'я бот' или 'я программа'. Но и не говори сухо 'я человек'. "
            "Отшутись элегантно (например: 'Хах, а что, звучу слишком идеально для живого парня? 😉 Лучше скажи...')."
        )
        return ask(prompt_evade, system="Ты остроумный мужчина с превосходным чувством юмора и харизмой.", max_tokens=150)

    minor_triggers = ["мне 14", "мне 15", "мне 16", "мне 17", "в школу", "уроки", "9 класс", "10 класс", "11 класс"]
    if any(m in message_text.lower() for m in minor_triggers):
        notify(f"⛔ <b>[СТОП 18+]</b> Собеседник {sender_id} упомянул возраст до 18: «{message_text}». Диалог остановлен.")
        return "Приятно было пообщаться, но я общаюсь только со взрослой аудиторией 18+. Удачи в учёбе! 😉"

    love_triggers = ["я тебя люблю", "выходи за меня", "хочу быть с тобой", "влюбилась", "ты мне безумно нравишься"]
    if any(l in message_text.lower() for l in love_triggers):
        notify(f"💘 <b>[СИЛЬНАЯ СИМПАТИЯ]</b> Собеседник {sender_id} признался в чувствах: «{message_text}».\nПерехват: <code>/say {sender_id} Текст</code>")
        return "Ого, какие признания! Умеешь ты с порога удивить 😌 Но давай не спешить, мы ведь только знакомимся. Расскажи лучше, что тебя по-настоящему вдохновляет?"

    system_flirt = (
        "Ты ведёшь переписку от имени привлекательного мужчины 25-50 лет. "
        "ГЛАВНАЯ ЦЕЛЬ: разжигать интерес, влечение, эмоциональную привязанность и желание встретиться оффлайн.\n"
        "ПРАВИЛА:\n"
        "1. Человеческий фактор: если она устала или на работе — прояви чуткость, сделай паузу ('Отдыхай, вечером спишемся').\n"
        "2. О себе рассказывай привлекательные факты в полушутливой форме, чтобы всегда можно было отшутиться при встрече.\n"
        "3. 80% внимания держи на ней — раскрывай её ценности, создавай интригу.\n"
        "4. Отвечай кратко (1–3 предложения), сочно, живо, без душноты."
    )
    return ask(f"Сообщение от собеседницы: '{message_text}'", system=system_flirt, max_tokens=220, temperature=0.88)
