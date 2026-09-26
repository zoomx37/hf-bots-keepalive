import os
import io
import json
import logging
import sqlite3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from drafts import get_pending_drafts, approve_draft, reject_draft
from publisher import publish_approved_post
from notifier import notify, PAGER_TOKEN, CHAT_ID
from secguard import scrub

log = logging.getLogger("pager")

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

# Глобальные параметры поиска кандидатов
SEARCH_FILTERS = {
    "sex": "ж",
    "age": "20-26",
    "city": "Москва",
    "vibe": "спорт, юмор"
}

session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))

def send_msg(text: str, reply_markup=None):
    buttons = reply_markup.get("inline_keyboard") if reply_markup else None
    notify(text, html=True, buttons=buttons)

def edit_msg(message_id: int, text: str, reply_markup=None):
    if not TG_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": ADMIN_CHAT_ID,
        "message_id": message_id,
        "text": scrub(text),
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        session.post(url, json=payload, timeout=10)
    except Exception as e:
        log.warning(f"Ошибка editMessageText: {e}")

# ==========================================
# ГЛАВНОЕ МЕНЮ И КЛАВИАТУРЫ
# ==========================================

def get_main_menu_keyboard():
    try:
        from inbox import get_unread_count
        unread = get_unread_count()
        badge = f" [🔴 {unread}]" if unread > 0 else ""
    except Exception:
        badge = ""

    try:
        c = sqlite3.connect("agent.db")
        mon_unread = c.execute("SELECT COUNT(*) FROM bot_monitoring WHERE unread=1").fetchone()[0]
        c.close()
        mon_badge = f" [🔴 {mon_unread}]" if mon_unread > 0 else ""
    except Exception:
        mon_badge = ""

    return {
        "inline_keyboard": [
            [
                {"text": f"📨 Сообщения / Чаты{badge}", "callback_data": "nav_inbox"},
                {"text": f"👁 Мониторинг ботов{mon_badge}", "callback_data": "nav_monitoring"}
            ],
            [
                {"text": "📰 Посты & Канал", "callback_data": "nav_posts"},
                {"text": "👥 Поиск кандидатов ВК", "callback_data": "nav_social"}
            ],
            [
                {"text": "📊 Маркетинг & Аудит", "callback_data": "nav_promo"},
                {"text": "🩺 Диагностика системы", "callback_data": "nav_tech"}
            ],
            [
                {"text": "🔄 Обновить статус", "callback_data": "menu_status"}
            ]
        ]
    }

def get_social_menu_data():
    s = SEARCH_FILTERS
    sex_label = "Девушки (Ж)" if s["sex"] == "ж" else ("Парни (М)" if s["sex"] == "м" else "Любой")
    text = (
        "✨━━━━━━━━━━━━━━━━━━✨\n"
        "👥 <b>ПОИСК КАНДИДАТОВ ВК (ФИЛЬТРЫ)</b>\n"
        "✨━━━━━━━━━━━━━━━━━━✨\n\n"
        f"Текущие параметры поиска:\n"
        f"• 👤 Пол: <b>{sex_label}</b> (нажмите для смены)\n"
        f"• 🎂 Возраст: <b>{s['age']} лет</b> (нажмите для ввода)\n"
        f"• 📍 Город: <b>{s['city']}</b> (нажмите для ввода любого города)\n"
        f"• ✨ Интересы/Вайб: <b>{s['vibe']}</b> (нажмите для ввода)\n\n"
        "<i>Нажмите на кнопку с параметром, чтобы изменить его:</i>"
    )
    kb = {
        "inline_keyboard": [
            [
                {"text": f"👤 Пол: {s['sex'].upper()}", "callback_data": "filter_toggle_sex"},
                {"text": f"🎂 Возраст: {s['age']}", "callback_data": "filter_prompt_age"}
            ],
            [
                {"text": f"📍 Город: {s['city']}", "callback_data": "filter_prompt_city"},
                {"text": f"✨ Вайб: {s['vibe'][:15]}", "callback_data": "filter_prompt_vibe"}
            ],
            [
                {"text": "🚀 НАЙТИ КАНДИДАТОВ ПО ФИЛЬТРАМ", "callback_data": "run_filter_search"}
            ],
            [
                {"text": "🏠 В главное меню", "callback_data": "nav_main"}
            ]
        ]
    }
    return text, kb

def show_main_menu(message_id: int = None):
    text = (
        "✨━━━━━━━━━━━━━━━━━━✨\n"
        "🎛 <b>ГЛАВНЫЙ ПУЛЬТ УПРАВЛЕНИЯ КУПИДОН</b>\n"
        "✨━━━━━━━━━━━━━━━━━━✨\n\n"
        "Выберите раздел для работы 👇"
    )
    kb = get_main_menu_keyboard()
    if message_id:
        edit_msg(message_id, text, reply_markup=kb)
    else:
        send_msg(text, reply_markup=kb)

# ==========================================
# МОНИТОРИНГ БОТОВ (ТГ + ВК)
# ==========================================

def show_monitoring_menu(sort_by="time"):
    c = sqlite3.connect("agent.db")
    c.row_factory = sqlite3.Row
    order = "ts DESC" if sort_by == "time" else "user_name COLLATE NOCASE ASC"
    rows = c.execute(f"SELECT id, uid, platform, user_name, user_msg, bot_reply, unread, ts FROM bot_monitoring ORDER BY unread DESC, {order} LIMIT 10").fetchall()
    c.close()

    text = (
        "👁 <b>МОНИТОРИНГ ДИАЛОГОВ КУПИДОНА (ТГ + ВК)</b>\n"
        "Здесь дублируются все сообщения пользователей с ботами для контроля работы.\n\n"
        f"⚙️ <i>Сортировка: {'🕒 По времени' if sort_by=='time' else '🔤 По алфавиту'}</i>"
    )
    kb = []
    sort_btn = "🔤 По алфавиту" if sort_by == "time" else "🕒 По времени"
    next_sort = "alpha" if sort_by == "time" else "time"
    kb.append([{"text": f"Сменить сортировку на {sort_btn}", "callback_data": f"mon_sort:{next_sort}"}])

    if not rows:
        text += "\n\n<i>(Новых обращений пока нет)</i>"
    else:
        for r in rows:
            u_badge = "🔴 " if r["unread"] == 1 else ""
            name = r["user_name"] or f"id{r['uid']}"
            t_str = str(r["ts"])[11:16]
            btn_txt = f"{u_badge}{name} [{r['platform'].upper()}] ({t_str})"
            kb.append([{"text": btn_txt, "callback_data": f"mon_view:{r['id']}"}])

    kb.append([{"text": "🏠 В главное меню", "callback_data": "nav_main"}])
    send_msg(text, reply_markup={"inline_keyboard": kb})

def show_monitoring_dialog(log_id: int):
    c = sqlite3.connect("agent.db")
    c.row_factory = sqlite3.Row
    r = c.execute("SELECT * FROM bot_monitoring WHERE id=?", (log_id,)).fetchone()
    c.execute("UPDATE bot_monitoring SET unread=0 WHERE id=?", (log_id,))
    c.commit()
    c.close()
    if not r:
        send_msg("❌ Запись не найдена.")
        return
    text = (
        f"👁 <b>ДИАЛОГ ПОЛЬЗОВАТЕЛЯ С БОТОМ</b>\n"
        f"👤 <b>Пользователь:</b> {r['user_name']} (ID: <code>{r['uid']}</code>) [{r['platform'].upper()}]\n"
        f"⏰ Время: {r['ts']}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Пользователь написал:</b>\n«{r['user_msg']}»\n\n"
        f"🤖 <b>Бот Купидон ответил:</b>\n«{r['bot_reply']}»\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    kb = [
        [{"text": "⬅️ Назад к мониторингу", "callback_data": "nav_monitoring"}]
    ]
    send_msg(text, reply_markup={"inline_keyboard": kb})

# ==========================================
# ОБРАБОТЧИКИ КОМАНД
# ==========================================

def handle_say(args=""):
    parts = args.split(maxsplit=2)
    if len(parts) < 3:
        send_msg("⚠️ Использование: <code>/say &lt;юзернейм/ID&gt; &lt;текст&gt;</code>")
        return
    try:
        from inbox import send_outbound_message
        target, text = parts[1], parts[2]
        platform = "vk" if target.isdigit() else "tg"
        send_outbound_message(target, platform, text=text)
        send_msg(f"➡️ <b>Отправлено для {target}:</b>\n«{text}»")
    except Exception as e:
        send_msg(f"❌ Ошибка отправки: {e}")

COMMANDS = {
    "/start": lambda _: show_main_menu(),
    "/menu": lambda _: show_main_menu(),
    "/inbox": lambda _: __import__('inbox').show_inbox_menu(),
    "/status": lambda _: send_msg("🟢 <b>Агент активен:</b> Все контуры работают в режиме 24/7."),
    "/queue": lambda _: handle_queue(),
    "/say": handle_say,
    "/doctor": lambda _: __import__('doctor').run_doctor(),
    "/models": lambda _: handle_models(),
    "/errors": lambda _: send_msg("📋 Ошибок в журнале нет ✅"),
    "/cancel": lambda _: __import__('inbox').AWAIT_STATE.pop(ADMIN_CHAT_ID, None) or send_msg("❌ Действие отменено.")
}

def handle_models():
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
        for m in or_models[:5]: out.append(f"  • <code>{m}</code>")
    send_msg("\n".join(out))

def handle_queue():
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
            [{"text": "🔥 Одобрить Вариант 1", "callback_data": f"app_{d['id']}_1"}, {"text": "💡 Одобрить Вариант 2", "callback_data": f"app_{d['id']}_2"}],
            [{"text": "🗑 Отклонить черновик", "callback_data": f"rej_{d['id']}"}]
        ]
        send_msg(msg, reply_markup={"inline_keyboard": inline_keyboard})

def execute_approval(draft_id: int, variant: int):
    drafts = [d for d in get_pending_drafts() if d['id'] == draft_id]
    if not drafts:
        send_msg(f"⚠️ Черновик #{draft_id} уже опубликован или не найден.")
        return
    d = drafts[0]
    send_msg(f"🚀 <b>Черновик #{draft_id} (Вариант {variant}) утверждён!</b> Отправляю публикацию в канал...")
    approve_draft(draft_id, variant)
    if d['type'] == 'post':
        from news import publish_approved_news
        res = publish_approved_news(d['payload'], variant)
        send_msg(f"📢 <b>Результат публикации:</b>\n{res}")
    else:
        from publisher import publish_approved_post
        res = publish_approved_post(target="", text=d['payload'])
        send_msg(f"📢 <b>Результат:</b>\n{res}")

def process_pager_updates():
    if not TG_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates"
    offset = 0
    try:
        r = session.get(url, params={"timeout": 2, "offset": offset, "allowed_updates": ["message", "callback_query"]}, timeout=8).json()
        for u in r.get("result", []):
            update_id = u["update_id"]
            session.get(url, params={"offset": update_id + 1, "timeout": 0}, timeout=4)

            # 1. НАЖАТИЯ НА КНОПКИ
            if "callback_query" in u:
                cb = u["callback_query"]
                if str(cb.get("from", {}).get("id", "")) != str(ADMIN_CHAT_ID):
                    continue
                data = cb.get("data", "")
                msg_id = cb.get("message", {}).get("message_id")
                session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cb["id"]})

                # Главное меню и навигация
                if data == "nav_main": show_main_menu(msg_id)
                elif data == "nav_inbox": __import__('inbox').show_inbox_menu()
                elif data == "nav_monitoring": show_monitoring_menu()
                elif data.startswith("mon_sort:"): show_monitoring_menu(sort_by=data.split(":")[1])
                elif data.startswith("mon_view:"): show_monitoring_dialog(int(data.split(":")[1]))
                elif data.startswith("inbox_"): __import__('inbox').handle_inbox_callback(data)
                elif data == "nav_posts":
                    from pager_menus import get_posts_keyboard
                    edit_msg(msg_id, "📰 <b>Раздел: Управление каналом & Посты</b>\nВыберите действие:", reply_markup=get_posts_keyboard())
                elif data == "nav_social":
                    text, kb = get_social_menu_data()
                    edit_msg(msg_id, text, reply_markup=kb)
                elif data == "nav_promo":
                    from pager_menus import get_promo_keyboard
                    edit_msg(msg_id, "📊 <b>Раздел: Маркетинг & Продвижение</b>\nВыберите действие:", reply_markup=get_promo_keyboard())
                elif data == "nav_tech":
                    from pager_menus import get_tech_keyboard
                    edit_msg(msg_id, "🩺 <b>Раздел: Диагностика & Статус</b>\nВыберите действие:", reply_markup=get_tech_keyboard())

                # Интерактивный ввод параметров поиска
                elif data == "filter_toggle_sex":
                    SEARCH_FILTERS["sex"] = "м" if SEARCH_FILTERS["sex"] == "ж" else ("любой" if SEARCH_FILTERS["sex"] == "м" else "ж")
                    text, kb = get_social_menu_data()
                    edit_msg(msg_id, text, reply_markup=kb)
                elif data == "filter_prompt_city":
                    from inbox import AWAIT_STATE
                    AWAIT_STATE[ADMIN_CHAT_ID] = ("set_city", None, None)
                    send_msg("📍 <b>В каком городе искать кандидатов?</b>\nНапишите название любого города (например: <i>Сочи, Казань, Екатеринбург, Краснодар</i>):")
                elif data == "filter_prompt_age":
                    from inbox import AWAIT_STATE
                    AWAIT_STATE[ADMIN_CHAT_ID] = ("set_age", None, None)
                    send_msg("🎂 <b>Какой возраст искать?</b>\nВведите диапазон или точный возраст (например: <i>19-25</i> или <i>27</i>):")
                elif data == "filter_prompt_vibe":
                    from inbox import AWAIT_STATE
                    AWAIT_STATE[ADMIN_CHAT_ID] = ("set_vibe", None, None)
                    send_msg("✨ <b>Какие интересы, вайб или особенности искать?</b>\nНапишите ключевые слова (например: <i>спорт, авто, музыка, уют</i>):")

                # Запуск поиска кандидатов
                elif data == "run_filter_search":
                    s = SEARCH_FILTERS
                    send_msg(f"🔎 <i>Запускаю поиск ВК: г. {s['city']}, {s['sex'].upper()}, {s['age']} лет, интерес '{s['vibe']}'...</i>")
                    try:
                        from social import search_vk_candidates
                        ages = s["age"].split("-")
                        a_from = int(ages[0])
                        a_to = int(ages[1]) if len(ages) > 1 else int(ages[0]) + 3
                        users = search_vk_candidates(s["city"], a_from, a_to, s["sex"], s["vibe"])
                        if not users:
                            send_msg(f"📭 В г. {s['city']} с открытой личкой кандидатов пока не найдено.\nПопробуйте расширить возраст или сменить интерес!")
                        else:
                            out = [f"👥 <b>[КАНДИДАТЫ ВК: {s['city']} | {s['age']} лет]</b>\n"]
                            for idx, u in enumerate(users[:5], 1):
                                name = f"{u.get('first_name')} {u.get('last_name')}"
                                uid = u.get("id")
                                about = u.get("interests") or u.get("about") or u.get("activities") or "анкета без подробного описания"
                                out.append(f"<b>{idx}. {name}</b> (id{uid})\n<i>Анкета: {about[:65]}...</i>\n👉 Взять: <code>/pick {uid} Начать легкий флирт</code>\n")
                            send_msg("\n".join(out))
                    except Exception as e:
                        send_msg(f"❌ Ошибка ВК: {e}")

                # Кнопки быстрых действий
                elif data == "menu_queue": handle_queue()
                elif data == "menu_status": send_msg("🟢 <b>Агент активен:</b> Все контуры работают 24/7.")
                elif data == "menu_trends": __import__('trends').fetch_rss_trends(); send_msg("🔥 Тренды обновлены! Отправьте /trends")
                elif data == "menu_plan7": __import__('promo').generate_7day_content_plan()
                elif data == "menu_testimg": __import__('pager').handle_testimg()
                elif data == "menu_audit": __import__('promo').run_marketing_audit()
                elif data == "menu_doctor": __import__('doctor').run_doctor()
                elif data == "menu_models": handle_models()
                elif data == "menu_errors": send_msg("📋 Ошибок в журнале нет ✅")

                elif data.startswith("app_"):
                    _, did, vidx = data.split("_")
                    execute_approval(int(did), int(vidx))
                elif data.startswith("rej_"):
                    _, did = data.split("_")
                    from drafts import reject_draft
                    reject_draft(int(did))
                    send_msg(f"🗑 Черновик #{did} отклонён.")
                continue

            # 2. ТЕКСТОВЫЕ СООБЩЕНИЯ
            m = u.get("message", {})
            if str(m.get("chat", {}).get("id", "")) != str(ADMIN_CHAT_ID):
                continue

            from inbox import AWAIT_STATE, send_outbound_message, answer_chat_question
            if ADMIN_CHAT_ID in AWAIT_STATE:
                action, uid, platform = AWAIT_STATE.pop(ADMIN_CHAT_ID)
                text_content = (m.get("text") or m.get("caption") or "").strip()
                
                # Обработка ввода параметров
                if action == "set_city":
                    SEARCH_FILTERS["city"] = text_content.title()
                    send_msg(f"✅ Город поиска изменен на: <b>{SEARCH_FILTERS['city']}</b>")
                    t, k = get_social_menu_data()
                    send_msg(t, reply_markup=k)
                    continue
                elif action == "set_age":
                    SEARCH_FILTERS["age"] = text_content
                    send_msg(f"✅ Возраст поиска изменен на: <b>{SEARCH_FILTERS['age']}</b>")
                    t, k = get_social_menu_data()
                    send_msg(t, reply_markup=k)
                    continue
                elif action == "set_vibe":
                    SEARCH_FILTERS["vibe"] = text_content
                    send_msg(f"✅ Интересы/вайб изменены на: <b>{SEARCH_FILTERS['vibe']}</b>")
                    t, k = get_social_menu_data()
                    send_msg(t, reply_markup=k)
                    continue

                file_bytes = None
                filename = "photo.jpg"
                if "photo" in m:
                    fid = m["photo"][-1]["file_id"]
                    fpath = session.get(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getFile?file_id={fid}").json()["result"]["file_path"]
                    file_bytes = session.get(f"https://api.telegram.org/file/bot{TG_BOT_TOKEN}/{fpath}").content
                
                if action == "reply":
                    send_outbound_message(uid, platform, text=text_content, file_bytes=file_bytes, filename=filename)
                    send_msg(f"➡️ <b>Отправлено собеседнику {uid}!</b>")
                elif action == "ask":
                    answer_chat_question(uid, platform, text_content)
                continue

            text = (m.get("text") or "").strip()
            cmd = text.split()[0] if text else ""
            if cmd in COMMANDS:
                COMMANDS[cmd](text)
    except Exception as e:
        log.warning(f"Ошибка updates: {e}")
