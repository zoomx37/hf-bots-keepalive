import os
import io
import logging
import requests
from drafts import get_pending_drafts, approve_draft, reject_draft

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

# Память фильтров поиска кандидатов (пошаговый мастер)
SEARCH_FILTERS = {
    "sex": "ж",
    "age": "20-26",
    "city": "Москва",
    "vibe": "спорт, юмор"
}

ERR_BUF = io.StringIO()
_err_handler = logging.StreamHandler(ERR_BUF)
_err_handler.setLevel(logging.WARNING)
logging.getLogger().addHandler(_err_handler)

def send_msg(text: str, reply_markup=None):
    from notifier import notify
    notify(text, html=True)

# ==========================================
# КЛАВИАТУРЫ И ПОДРАЗДЕЛЫ МЕНЮ
# ==========================================

def get_main_menu_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "📰 Управление каналом & Посты", "callback_data": "nav_posts"},
                {"text": "👥 Поиск кандидатов ВК", "callback_data": "nav_social"}
            ],
            [
                {"text": "📊 Маркетинг & Продвижение", "callback_data": "nav_promo"},
                {"text": "🩺 Диагностика & Статус", "callback_data": "nav_tech"}
            ],
            [
                {"text": "📋 Очередь черновиков", "callback_data": "menu_queue"},
                {"text": "🔄 Обновить статус", "callback_data": "menu_status"}
            ]
        ]
    }

def get_posts_menu_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "📋 Очередь черновиков (/queue)", "callback_data": "menu_queue"},
                {"text": "🔥 Горячие тренды дейтинга", "callback_data": "menu_trends"}
            ],
            [
                {"text": "🗓 Контент-план на 7 дней", "callback_data": "menu_plan7"},
                {"text": "🎨 Тест генератора картинок", "callback_data": "menu_testimg"}
            ],
            [
                {"text": "🏠 В главное меню", "callback_data": "nav_main"}
            ]
        ]
    }

def get_social_menu_keyboard():
    s = SEARCH_FILTERS
    return {
        "inline_keyboard": [
            [
                {"text": f"👤 Пол: {s['sex'].upper()}", "callback_data": "filter_toggle_sex"},
                {"text": f"🎂 Возраст: {s['age']}", "callback_data": "filter_cycle_age"}
            ],
            [
                {"text": f"📍 Город: {s['city']}", "callback_data": "filter_cycle_city"},
                {"text": f"✨ Вайб: {s['vibe']}", "callback_data": "filter_cycle_vibe"}
            ],
            [
                {"text": "🚀 НАЙТИ КАНДИДАТОВ ПО ФИЛЬТРАМ", "callback_data": "run_filter_search"}
            ],
            [
                {"text": "🏠 В главное меню", "callback_data": "nav_main"}
            ]
        ]
    }

def get_promo_menu_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "📈 Экспертный аудит каналов", "callback_data": "menu_audit"},
                {"text": "🗓 Контент-план на 7 дней", "callback_data": "menu_plan7"}
            ],
            [
                {"text": "🏠 В главное меню", "callback_data": "nav_main"}
            ]
        ]
    }

def get_tech_menu_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🩺 Самодиагностика систем", "callback_data": "menu_doctor"},
                {"text": "📡 Каталог ИИ-моделей", "callback_data": "menu_models"}
            ],
            [
                {"text": "📋 Последние ошибки в логе", "callback_data": "menu_errors"},
                {"text": "🔄 Статус серверов", "callback_data": "menu_status"}
            ],
            [
                {"text": "🏠 В главное меню", "callback_data": "nav_main"}
            ]
        ]
    }

def show_main_menu():
    text = (
        "✨━━━━━━━━━━━━━━━━━━✨\n"
        "🎛 <b>ГЛАВНЫЙ ПУЛЬТ УПРАВЛЕНИЯ КУПИДОН</b>\n"
        "✨━━━━━━━━━━━━━━━━━━✨\n\n"
        "Выберите интересующий подраздел управления системой 👇"
    )
    from notifier import PAGER_TOKEN, CHAT_ID
    requests.post(
        f"https://api.telegram.org/bot{PAGER_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "reply_markup": get_main_menu_keyboard()},
        timeout=15
    )

# ==========================================
# ОБРАБОТЧИКИ ДЕЙСТВИЙ
# ==========================================

def handle_status(args=""):
    send_msg("🟢 <b>Агент активен:</b> Все контуры функционируют штатно.")

def handle_models(args=""):
    from modelcatalog import list_google, list_openrouter
    send_msg("📡 <i>Опрашиваю живой каталог API...</i>")
    g_key = os.getenv("GEMINI_API_KEY", "")
    out = ["📡 <b>[ЖИВОЙ КАТАЛОГ МОДЕЛЕЙ ИЗ API]</b>\n"]
    g_models = [m for m in list_google(g_key) if "flash" in m]
    out.append("🔹 <b>Google Gemini (flash):</b>")
    if g_models:
        for m in g_models[-6:]: out.append(f"  • <code>{m}</code>")
    else: out.append("  <i>Ключ не ответил</i>")
    
    or_models = list_openrouter()
    out.append("\n🔹 <b>OpenRouter (бесплатные :free):</b>")
    if or_models:
        for m in or_models[:6]: out.append(f"  • <code>{m}</code>")
    send_msg("\n".join(out))

def handle_trends(args=""):
    send_msg("🔥 <i>Сканирую тренды дейтинга и ленты новостей...</i>")
    try:
        from trends import fetch_rss_trends, get_hot_trends
        fetch_rss_trends()
        hot = get_hot_trends(5)
        if not hot:
            send_msg("📭 Новых трендов пока не обнаружено.")
            return
        out = ["🔥 <b>[ГОРЯЧИЕ ИНФОПОВОДЫ СЕЙЧАС]</b>\n"]
        for tid, src, title, heat, url in hot:
            out.append(f"🔹 <b>#{tid}</b> [{src.upper()}] <i>(Хайп: {heat:.1f})</i>\n«{title}»\n👉 Пост: <code>/pitch {tid}</code>\n")
        send_msg("\n".join(out))
    except Exception as e:
        send_msg(f"❌ Ошибка трендов: {e}")

def handle_pitch(args=""):
    parts = args.split()
    if len(parts) < 2:
        send_msg("⚠️ Использование: <code>/pitch &lt;ID_тренда&gt;</code>")
        return
    try:
        tid = int(parts[1])
        from trends import pitch_trend_to_post
        from drafts import add_draft
        v1, v2 = pitch_trend_to_post(tid)
        if v1 and v2:
            did = add_draft("post", f"@qpd_n|||{v1}|||{v2}", target="@qpd_n")
            send_msg(f"✅ На основе тренда создан <b>Черновик #{did}</b>! Откройте меню /queue для выбора.")
        else:
            send_msg(f"⚠️ Тренд #{tid} не найден.")
    except Exception as e:
        send_msg(f"❌ Сбой питча: {e}")

def handle_audit(args=""):
    send_msg("📊 <i>Собираю статистику каналов и формирую аудит...</i>")
    try:
        from promo import run_marketing_audit
        run_marketing_audit()
    except Exception as e:
        send_msg(f"❌ Ошибка аудита: {e}")

def handle_plan7(args=""):
    send_msg("🗓 <i>Генерирую контент-план на 7 дней в стиле 'НА ПРИКОЛЕ'...</i>")
    try:
        from promo import generate_7day_content_plan
        generate_7day_content_plan()
    except Exception as e:
        send_msg(f"❌ Ошибка плана: {e}")

def handle_testimg(args=""):
    send_msg("🎨 <i>Генерирую тестовую иллюстрацию БЕЗ людей и вотермарки...</i>")
    from imagegen import generate_image
    from notifier import PAGER_TOKEN, CHAT_ID
    photo = generate_image("уютный вечерний столик у окна кофейни, чашки горячего кофе, теплый кинематографичный свет, неоновая вывеска сердца")
    if photo:
        requests.post(
            f"https://api.telegram.org/bot{PAGER_TOKEN}/sendPhoto",
            data={"chat_id": CHAT_ID, "caption": "🎨 <b>Тест генератора картинок: без людей и без вотермарки!</b>", "parse_mode": "HTML"},
            files={"photo": ("test.jpg", io.BytesIO(photo), "image/jpeg")}, timeout=35
        )
    else:
        send_msg("❌ Не удалось сгенерировать изображение.")

def handle_errors(args=""):
    ERR_BUF.seek(0)
    lines = ERR_BUF.readlines()
    out = "".join(lines[-12:]) or "Ошибок в журнале нет ✅"
    send_msg(f"📋 <b>Последние записи журнала:</b>\n<pre>{out[-3000:]}</pre>")

def handle_doctor(args=""):
    from doctor import run_doctor
    run_doctor()

def handle_queue(args=""):
    drafts = get_pending_drafts()
    if not drafts:
        send_msg("📭 <b>Очередь пуста:</b> Нет действий, требующих решения.")
        return
    
    for d in drafts:
        parts = d['payload'].split("|||")
        target_info = parts[0] if len(parts) > 2 else (d['target'] or 'общая')
        variants = parts[1:] if len(parts) > 2 else parts
        
        msg = f"📋 <b>Черновик #{d['id']} [{d['type']}]</b> (Канал: <code>{target_info}</code>)\n\n"
        for idx, var in enumerate(variants, 1):
            clean_prev = var.split("[КАРТИНКА:")[0].replace("[ХЕДЛАЙН:", "📌 <b>").replace("]", "</b>\n").strip()
            msg += f"<b>Вариант {idx}:</b>\n{clean_prev}\n\n"

        inline_keyboard = [
            [
                {"text": "🔥 Одобрить Вариант 1", "callback_data": f"app_{d['id']}_1"},
                {"text": "💡 Одобрить Вариант 2", "callback_data": f"app_{d['id']}_2"}
            ],
            [
                {"text": "🗑 Отклонить черновик", "callback_data": f"rej_{d['id']}"}
            ]
        ]
        from notifier import PAGER_TOKEN, CHAT_ID
        requests.post(
            f"https://api.telegram.org/bot{PAGER_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML", "reply_markup": {"inline_keyboard": inline_keyboard}},
            timeout=15
        )

def execute_approval(draft_id: int, variant: int):
    from drafts import get_pending_drafts, approve_draft
    drafts = [d for d in get_pending_drafts() if d['id'] == draft_id]
    if not drafts:
        send_msg(f"⚠️ Черновик #{draft_id} уже опубликован или не найден.")
        return
        
    d = drafts[0]
    send_msg(f"🚀 <b>Черновик #{draft_id} (Вариант {variant}) утверждён!</b> Публикую...")
    approve_draft(draft_id, variant)
    if d['type'] == 'post':
        from news import publish_approved_news
        res = publish_approved_news(d['payload'], variant)
        send_msg(f"📢 <b>Результат публикации:</b>\n{res}")
    else:
        from publisher import publish_approved_post
        res = publish_approved_post(target="", text=d['payload'])
        send_msg(f"📢 <b>Результат:</b>\n{res}")

def execute_rejection(draft_id: int):
    if reject_draft(draft_id):
        send_msg(f"🗑 <b>Черновик #{draft_id} отклонён.</b>")
    else:
        send_msg(f"⚠️ Черновик #{draft_id} не найден.")

def handle_say(args=""):
    parts = args.split(maxsplit=2)
    if len(parts) < 3:
        send_msg("⚠️ Использование: <code>/say &lt;юзернейм/ID&gt; &lt;текст&gt;</code>")
        return
    send_msg(f"📨 Сообщение поставлено в очередь для <b>{parts[1]}</b>:\n«{parts[2]}»")

COMMANDS = {
    "/start": lambda _: show_main_menu(),
    "/menu": lambda _: show_main_menu(),
    "/status": handle_status,
    "/queue": handle_queue,
    "/say": handle_say,
    "/doctor": handle_doctor,
    "/models": handle_models,
    "/errors": handle_errors,
    "/testimg": handle_testimg,
    "/trends": handle_trends,
    "/pitch": handle_pitch,
    "/audit": handle_audit,
    "/plan7": handle_plan7
}

def process_pager_updates():
    if not TG_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates"
    try:
        res = requests.get(url, params={"timeout": 3, "allowed_updates": ["message", "callback_query"]}, timeout=6).json()
        for u in res.get("result", []):
            update_id = u["update_id"]
            requests.get(url, params={"offset": update_id + 1, "timeout": 0}, timeout=4)
            
            # Нажатие на кнопку
            if "callback_query" in u:
                cb = u["callback_query"]
                if str(cb.get("from", {}).get("id", "")) != str(ADMIN_CHAT_ID):
                    continue
                data = cb.get("data", "")
                requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cb["id"]})
                
                # Навигация меню
                if data == "nav_main":
                    show_main_menu()
                elif data == "nav_posts":
                    from notifier import PAGER_TOKEN, CHAT_ID
                    requests.post(f"https://api.telegram.org/bot{PAGER_TOKEN}/sendMessage", json={
                        "chat_id": CHAT_ID, "text": "📰 <b>Раздел: Управление каналом & Посты</b>\nВыберите действие:", "parse_mode": "HTML", "reply_markup": get_posts_menu_keyboard()
                    })
                elif data == "nav_social":
                    from notifier import PAGER_TOKEN, CHAT_ID
                    s = SEARCH_FILTERS
                    text = f"👥 <b>Поиск кандидатов ВК (Фильтры)</b>\n\nТекущие параметры:\n• Пол: <b>{s['sex'].upper()}</b>\n• Возраст: <b>{s['age']}</b>\n• Город: <b>{s['city']}</b>\n• Вайб: <b>{s['vibe']}</b>\n\nКликайте по кнопкам ниже для смены параметров или нажмите 'Найти':"
                    requests.post(f"https://api.telegram.org/bot{PAGER_TOKEN}/sendMessage", json={
                        "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "reply_markup": get_social_menu_keyboard()
                    })
                elif data == "nav_promo":
                    from notifier import PAGER_TOKEN, CHAT_ID
                    requests.post(f"https://api.telegram.org/bot{PAGER_TOKEN}/sendMessage", json={
                        "chat_id": CHAT_ID, "text": "📊 <b>Раздел: Маркетинг & Продвижение</b>\nВыберите действие:", "parse_mode": "HTML", "reply_markup": get_promo_menu_keyboard()
                    })
                elif data == "nav_tech":
                    from notifier import PAGER_TOKEN, CHAT_ID
                    requests.post(f"https://api.telegram.org/bot{PAGER_TOKEN}/sendMessage", json={
                        "chat_id": CHAT_ID, "text": "🩺 <b>Раздел: Диагностика & Серверы</b>\nВыберите действие:", "parse_mode": "HTML", "reply_markup": get_tech_menu_keyboard()
                    })
                
                # Переключение фильтров поиска в 1 клик
                elif data == "filter_toggle_sex":
                    SEARCH_FILTERS["sex"] = "м" if SEARCH_FILTERS["sex"] == "ж" else "ж"
                    send_msg(f"👤 Пол изменен на: <b>{SEARCH_FILTERS['sex'].upper()}</b>")
                elif data == "filter_cycle_age":
                    ages = ["18-22", "23-27", "28-35", "35-45"]
                    curr_idx = ages.index(SEARCH_FILTERS["age"]) if SEARCH_FILTERS["age"] in ages else 0
                    SEARCH_FILTERS["age"] = ages[(curr_idx + 1) % len(ages)]
                    send_msg(f"🎂 Возраст изменен на: <b>{SEARCH_FILTERS['age']}</b>")
                elif data == "filter_cycle_city":
                    cities = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Краснодар"]
                    curr_idx = cities.index(SEARCH_FILTERS["city"]) if SEARCH_FILTERS["city"] in cities else 0
                    SEARCH_FILTERS["city"] = cities[(curr_idx + 1) % len(cities)]
                    send_msg(f"📍 Город изменен на: <b>{SEARCH_FILTERS['city']}</b>")
                elif data == "filter_cycle_vibe":
                    vibes = ["спорт, юмор", "уют, книги, кофе", "вечеринки, музыка", "бизнес, карьера"]
                    curr_idx = vibes.index(SEARCH_FILTERS["vibe"]) if SEARCH_FILTERS["vibe"] in vibes else 0
                    SEARCH_FILTERS["vibe"] = vibes[(curr_idx + 1) % len(vibes)]
                    send_msg(f"✨ Вайб изменен на: <b>{SEARCH_FILTERS['vibe']}</b>")
                elif data == "run_filter_search":
                    s = SEARCH_FILTERS
                    a_from, a_to = map(int, s["age"].split("-"))
                    send_msg(f"🔎 <i>Ищу анкеты: {s['city']}, {s['sex'].upper()}, {s['age']} лет, вайб '{s['vibe']}'...</i>")
                    try:
                        from social import search_vk_candidates
                        users = search_vk_candidates(s["city"], a_from, a_to, s["sex"], s["vibe"])
                        if not users:
                            send_msg("📭 Кандидатов с открытой личкой по этим параметрам не найдено.")
                        else:
                            out = [f"👥 <b>[КАНДИДАТЫ ВК: {s['city']} | {s['age']} лет]</b>\n"]
                            for idx, u in enumerate(users[:5], 1):
                                name = f"{u.get('first_name')} {u.get('last_name')}"
                                uid = u.get("id")
                                about = u.get("interests") or u.get("about") or "без описания"
                                out.append(f"<b>{idx}. {name}</b> (id{uid})\n<i>О себе: {about[:60]}...</i>\n👉 Взять: <code>/pick {uid} Познакомиться легко, позвать на кофе</code>\n")
                            send_msg("\n".join(out))
                    except Exception as e:
                        send_msg(f"❌ Ошибка поиска: {e}")

                # Кнопки быстрых действий
                elif data == "menu_queue": handle_queue()
                elif data == "menu_status": handle_status()
                elif data == "menu_trends": handle_trends()
                elif data == "menu_plan7": handle_plan7()
                elif data == "menu_testimg": handle_testimg()
                elif data == "menu_audit": handle_audit()
                elif data == "menu_doctor": handle_doctor()
                elif data == "menu_models": handle_models()
                elif data == "menu_errors": handle_errors()

                # Одобрение / отклонение черновиков
                elif data.startswith("app_"):
                    _, d_id, v_idx = data.split("_")
                    execute_approval(int(d_id), int(v_idx))
                elif data.startswith("rej_"):
                    _, d_id = data.split("_")
                    execute_rejection(int(d_id))
                continue

            # Команды текстом
            m = u.get("message", {})
            if str(m.get("chat", {}).get("id", "")) != str(ADMIN_CHAT_ID):
                continue
            text = m.get("text", "").strip()
            cmd = text.split()[0] if text else ""
            if cmd == "/approve":
                p = text.split()
                if len(p) >= 2: execute_approval(int(p[1]), int(p[2]) if len(p) > 2 else 1)
            elif cmd == "/reject":
                p = text.split()
                if len(p) >= 2: execute_rejection(int(p[1]))
            elif cmd in COMMANDS:
                COMMANDS[cmd](text)
    except Exception as e:
        print(f"Ошибка updates: {e}")
