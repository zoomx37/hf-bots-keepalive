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

# 1. Стоп-слова коммерции, ботов, рекламы и услуг
SPAM_STOP_WORDS = [
    "автобус", "махачкал", "такси", "грузоперевозк", "перевозк",
    "взаимн", "подписк", "youtube", "ютуб", "заработок", "доход", "крипт",
    "маникюр", "ресниц", "брови", "шугаринг", "кератин", "наращиван",
    "шоурум", "одежд", "эскорт", "интим", "массаж", "таро", "нумеролог",
    "wildberries", "вайлдберриз", "ozon", "озон", "менеджер", "bot", "бот",
    "вацап", "whatsapp", "пишите на", "заказ", "доставка", "бронирован",
    "ставь лайк", "кидай заявку", "хочешь в друзья", "добавь в друзья", "в подписчик"
]

# 2. Стоп-слова детности
KIDS_STOP_WORDS = [
    "мама", "мамочка", "сынок", "сыночек", "дочка", "доченька", "дети", "ребенок", "деток", "мать"
]

# 3. Стоп-слова для имён (чтобы не попадали автобусы и организации)
FAKE_NAMES = [
    "автобус", "билет", "такси", "тур", "одежда", "ресницы", "маникюр",
    "брови", "шоп", "магазин", "доставка", "цветы", "работа", "аренда"
]

PHONE_PATTERN = re.compile(r"(\+?[78]\s?\(?\d{3}\)?\s?\d{3}[-\s]?\d{2}[-\s]?\d{2}|\b89\d{9}\b)")

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

def is_spam_or_bot(u: dict) -> bool:
    """Глубокий фильтр ботов, накруток, коммерческих аккаунтов и автобусов."""
    first = str(u.get("first_name", "")).strip().lower()
    last = str(u.get("last_name", "")).strip().lower()
    status = str(u.get("status", "")).lower()
    about = str(u.get("about", "")).lower()
    activities = str(u.get("activities", "")).lower()
    occupation = str(u.get("occupation", {}).get("name", "")).lower()
    followers = u.get("followers_count", 0)

    # 1. Проверка имени на коммерцию («Автобус Москва»)
    if any(fake in first or fake in last for fake in FAKE_NAMES):
        return True

    # 2. Блогеры, фермы накрутки и медийные боты (как Сабина с 10к подписчиков)
    if followers and int(followers) > 3500:
        return True

    combined_text = f"{first} {last} {status} {about} {activities} {occupation}"

    # 3. Поиск номеров телефонов и вацапа
    if PHONE_PATTERN.search(combined_text):
        return True

    # 4. Стоп-слова спама и коммерции
    if any(w in combined_text for w in SPAM_STOP_WORDS):
        return True

    return False

def has_kids(u: dict) -> bool:
    full_info = f"{u.get('status','')} {u.get('about','')} {u.get('interests','')}".lower()
    return any(w in full_info for w in KIDS_STOP_WORDS)

def is_relation_ok(u: dict) -> bool:
    """Исключаем замужних, помолвленных и тех, у кого есть пара."""
    rel = u.get("relation", 0)
    # 2: есть парень, 3: помолвлена, 4: замужем, 7: влюблена, 8: гражданский брак
    if rel in [2, 3, 4, 7, 8]:
        return False
    status_lower = u.get("status", "").lower()
    if any(w in status_lower for w in ["замужем", "люблю мужа", "есть парень", "занята", "влюблена"]):
        return False
    return True

def search_vk_candidates(city_name: str, age_from: int, age_to: int, sex: str = "ж", vibe: str = "") -> list:
    allowed, wait_min = vkrate.can_vk()
    if not allowed:
        raise RuntimeError(f"ВК на паузе предохранителем ещё {wait_min} мин.")

    token = os.getenv("VK_TOKEN", "").strip()
    if not token:
        raise ValueError("VK_TOKEN не задан")

    cache_key = f"{city_name.lower()}|{age_from}-{age_to}|{sex.lower()}|{vibe.lower()}"
    now = time.time()

    if cache_key in FIND_CACHE and now - FIND_CACHE[cache_key][0] < 1200:
        return FIND_CACHE[cache_key][1]

    session = vkrate.get_vk_session(token)
    cid = get_city_id(session, city_name)
    sex_code = 1 if sex.lower() in ["ж", "f", "жен", "девушка", "девушки (ж)"] else (2 if sex.lower() in ["м", "m", "муж", "парень", "парни (м)"] else 0)

    params = {
        "count": 80,  # Увеличена выборка для качественного отсева спама
        "city": cid,
        "country": 1,
        "age_from": age_from,
        "age_to": age_to,
        "has_photo": 1,
        "fields": "city,bdate,about,interests,activities,music,about,status,relation,occupation,followers_count,can_write_private_message"
    }
    if sex_code > 0:
        params["sex"] = sex_code

    res = vkrate.vk_call(session, "users.search", **params)
    items = res.get("items", [])

    clean_candidates = []
    vibe_clean = vibe.strip().lower()

    # Синонимы для точного попадания в интерес
    vibe_synonyms = [vibe_clean]
    if "спорт" in vibe_clean or "йог" in vibe_clean:
        vibe_synonyms = ["спорт", "фитнес", "зал", "тренировк", "бег", "растяжк", "стретч", "йог", "yoga", "пилатес"]
    elif "книг" in vibe_clean:
        vibe_synonyms = ["книг", "чтени", "литератур", "роман", "психолог"]
    elif "музык" in vibe_clean or "вечерин" in vibe_clean:
        vibe_synonyms = ["музык", "концерт", "рок", "техно", "dj", "клуб", "фестивал"]

    for u in items:
        if u.get("is_closed", False):
            continue
        if u.get("can_write_private_message") == 0:
            continue
        if not is_relation_ok(u):
            continue
        if is_spam_or_bot(u):
            continue
        if has_kids(u):
            continue

        bio_text = f"{u.get('about','')} {u.get('interests','')} {u.get('activities','')} {u.get('status','')}".lower()

        # Бонус за совпадение по вайбу
        score = 0
        matched_vibe = False
        for syn in vibe_synonyms:
            if syn and syn in bio_text:
                score += 20
                matched_vibe = True
                break

        # Если анкета заполнена — плюс, пустые («без описания») получают штраф
        if len(bio_text.strip()) > 15:
            score += 10
        else:
            score -= 15  # Пустышки отсекаются вниз списка

        if u.get("relation") in [1, 6]:
            score += 5

        u["_score"] = score
        u["_matched_vibe"] = matched_vibe
        clean_candidates.append(u)

    # Сортируем: сначала реальные девушки с совпадением по интересу и заполненным профилем
    clean_candidates.sort(key=lambda x: x["_score"], reverse=True)

    result = clean_candidates[:5]
    if result:
        FIND_CACHE[cache_key] = (now, result)
    return result

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
