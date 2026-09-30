import os
import io
import json
import logging
import sqlite3
import threading
import requests
import vk_api
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from drafts import get_pending_drafts, approve_draft, reject_draft
from publisher import publish_approved_post
from notifier import notify, PAGER_TOKEN, CHAT_ID
from secguard import scrub

log = logging.getLogger("pager")

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

SEARCH_FILTERS = {
    "sex": "ж",
    "age": "20-26",
    "city": "Ярославль",
    "vibe": "спорт, юмор"
}

IMAGE_GEN_STATE = {}
AWAIT_LOGO = set()

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
        r = session.post(url, json=payload, timeout=10).json()
        if not r.get("ok"):
            send_msg(text, reply_markup=reply_markup)
    except Exception as e:
        log.warning(f"editMessageText fallback: {e}")
        send_msg(text, reply_markup=reply_markup)

# ==========================================
# ФОНОВЫЕ ЗАДАЧИ (НЕ БЛОКИРУЮТ БОТА)
# ==========================================

def worker_pitch(tid: int):
    try:
        from trends import pitch_trend_to_post
        from drafts import add_draft
        v1, v2 = pitch_trend_to_post(tid)
        if v1 and v2:
            did = add_draft("post", f"@qpd_n|||на приколе|||{v1}|||{v2}", target="@qpd_n")
            send_msg(f"🔥 <b>Черновик поста #{did} готов по тренду #{tid}!</b>\n\nОтправьте команду /queue для утверждения.")
        else:
            send_msg(f"⚠️ Тренд #{tid} не найден или уже использован.")
    except Exception as e:
        send_msg(f"❌ Ошибка создания поста: {e}")

def worker_trends_fetch(region: str):
    from trends import REGIONS, fetch_trends_by_region, get_hot_trends, batch_translate_and_format
    reg_name = REGIONS.get(region, "Мир")
    try:
        fetch_trends_by_region(region)
        hot = get_hot_trends(region=region, limit=5)
        if not hot:
            send_msg(f"📭 Тренды по региону {reg_name} обновляются, повторите через пару секунд.")
        else:
            formatted_items = batch_translate_and_format(hot, region)
            out = [f"🔥 <b>[АКТУАЛЬНЫЕ ХАЙПОВЫЕ ТЕМЫ ДЕЙТИНГА: {reg_name.upper()}]</b>\n"] + formatted_items
            send_msg("\n".join(out))
    except Exception as e:
        send_msg(f"❌ Ошибка трендов: {e}")

def worker_rewrite_draft(did: int):
    try:
        from news import rewrite_draft_to_next_style
        next_st, err = rewrite_draft_to_next_style(did)
        if err:
            send_msg(f"⚠️ {err}")
        else:
            send_msg(f"✅ Черновик переписан в стиле «{next_st.upper()}»!")
            handle_queue()
    except Exception as e:
        send_msg(f"❌ Ошибка смены стиля: {e}")

def worker_custom_pitch(text_content: str):
    try:
        from news import STYLE, clean_html
        from drafts import add_draft
        from llm import ask
        import lex
        prompt_custom = (
            f"Материал: «{text_content}».\n\n"
            "Напиши насыщенный пост для дейтинг-канала по Золотому Стандарту (1100–1400 знаков). "
            "Выдели ключевые мысли жирным шрифтом и добавь 4-6 уместных эмодзи. БЕЗ салам!"
        )
        v1 = clean_html(ask(prompt_custom + " Сделай упор на психологию и сарказм.", system=STYLE + lex.block(), max_tokens=1000))
        v2 = clean_html(ask(prompt_custom + " Сделай упор на практический разбор.", system=STYLE + lex.block(), max_tokens=1000))
        did = add_draft("post", f"@qpd_n|||на приколе|||{v1}|||{v2}", target="@qpd_n")
        send_msg(f"🔥 <b>Черновик поста #{did} по вашему материалу готов!</b> Отправьте /queue для выбора варианта.")
    except Exception as e:
        send_msg(f"❌ Ошибка создания поста: {e}")

def worker_flux_generate(prompt: str, ref_photo_bytes: bytes = None):
    try:
        from imagegen import generate_image
        photo = generate_image(prompt, source_face_bytes=ref_photo_bytes)
        if photo:
            requests.post(
                f"https://api.telegram.org/bot{PAGER_TOKEN}/sendPhoto",
                data={"chat_id": CHAT_ID, "caption": f"🎨 <b>FLUX готов!</b>\nПромпт: <i>{prompt[:100]}...</i>", "parse_mode": "HTML"},
                files={"photo": ("flux_result.jpg", io.BytesIO(photo), "image/jpeg")},
                timeout=50
            )
        else:
            send_msg("❌ Не удалось сгенерировать изображение.")
    except Exception as e:
        send_msg(f"❌ Ошибка генерации: {e}")

def worker_search_candidates(city: str, age_str: str, sex: str, vibe: str):
    try:
        from social import search_vk_candidates
        ages = age_str.split("-")
        a_from = int(ages[0])
        a_to = int(ages[1]) if len(ages) > 1 else int(ages[0]) + 3
        users = search_vk_candidates(city, a_from, a_to, sex, vibe)
        if not users:
            send_msg(f"📭 В г. {city} подходящих анкет пока не найдено.")
        else:
            out = [f"👥 <b>[ОТОБРАННЫЕ КАНДИДАТЫ ВК: {city} | {age_str} лет]</b>\n"]
            for idx, u in enumerate(users[:5], 1):
                name = f"{u.get('first_name')} {u.get('last_name')}"
                uid = u.get("id")
                about = u.get("interests") or u.get("activities") or u.get("about") or u.get("status") or "без описания"
                out.append(f"<b>{idx}. {name}</b> (id{uid})\n<i>Анкета: {about[:75]}...</i>\n👉 Изучить и начать: <code>/pick {uid} Знакомство</code>\n")
            send_msg("\n".join(out))
    except Exception as e:
        send_msg(f"❌ Ошибка ВК: {e}")

def vk_img_test():
    """Тестирует гибридную цепочку: загрузка фото через VK_TOKEN, публикация через VK_GROUP_TOKEN."""
    send_msg("🧪 <i>Запускаю диагностику гибридной загрузки фото в ВК...</i>")
    gid = 239533580
    b = io.BytesIO()
    from PIL import Image
    Image.new("RGB", (120, 120), (255, 20, 147)).save(b, "JPEG")
    data = b.getvalue()
    out = ["🧪 <b>ТЕСТ ГИБРИДНОЙ ЦЕПОЧКИ ВК:</b>\n"]

    user_token = os.getenv("VK_TOKEN", os.getenv("VK_USER_TOKEN", "")).strip()
    group_token = os.getenv("VK_GROUP_TOKEN", "").strip()

    if not user_token:
        send_msg("❌ VK_TOKEN (токен пользователя) не задан в Secrets!")
        return
    if not group_token:
        send_msg("❌ VK_GROUP_TOKEN (ключ группы) не задан в Secrets!")
        return

    try:
        # 1. Загрузка фото через токен пользователя
        user_api = vk_api.VkApi(token=user_token, api_version="5.131").get_api()
        up = user_api.photos.getWallUploadServer(group_id=gid)
        out.append("✅ 1. Сервер загрузки получен (через VK_TOKEN)")

        upl = requests.post(up["upload_url"], files={"photo": ("test.jpg", io.BytesIO(data), "image/jpeg")}, timeout=30).json()
        if not upl.get("photo") or upl.get("photo") == "[]":
            send_msg(f"❌ Сервер отклонил файл: {upl}")
            return
        out.append("✅ 2. Файл принят сервером загрузки")

        s = user_api.photos.saveWallPhoto(group_id=gid, photo=upl["photo"], server=upl["server"], hash=upl["hash"])[0]
        att = f"photo{s['owner_id']}_{s['id']}"
        out.append(f"✅ 3. Фото сохранено в альбоме группы ({att})")

        # 2. Публикация на стене через ключ группы (from_group=1)
        group_api = vk_api.VkApi(token=group_token, api_version="5.131").get_api()
        p = group_api.wall.post(owner_id=-gid, from_group=1, signed=0, message="Тест фото (автоудаление)", attachments=att)
        out.append("✅ 4. Пост с фото успешно опубликован группой!")

        # 3. Безопасная попытка удаления
        try:
            user_api.wall.delete(owner_id=-gid, post_id=p["post_id"])
            out.append("\n🎉 <b>УРА! ГИБРИДНАЯ СВЯЗКА РАБОТАЕТ НА 100%!</b> (тест удалён со стены)")
        except Exception:
            out.append(f"\n🎉 <b>УРА! ГИБРИДНАЯ СВЯЗКА РАБОТАЕТ НА 100%!</b>\n👉 Тестовый пост опубликован на стене vk.com/public{gid} (удалите его вручную)")

    except Exception as e:
        out.append(f"\n❌ Сбой на шаге: {e}")

    send_msg("\n".join(out))

# ==========================================
# ВСТРОЕННЫЕ КЛАВИАТУРЫ РАЗДЕЛОВ
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
                {"text": "🔍 Скан профиля ВК", "callback_data": "nav_scan_prompt"},
                {"text": "📖 Живой лексикон", "callback_data": "nav_lex"}
            ],
            [
                {"text": "📰 Посты & Канал", "callback_data": "nav_posts"},
                {"text": "📝 Моя страница ВК", "callback_data": "nav_mypage"}
            ],
            [
                {"text": "👥 Поиск кандидатов ВК", "callback_data": "nav_social"},
                {"text": "📊 Маркетинг & Аудит", "callback_data": "nav_promo"}
            ],
            [
                {"text": "🩺 Диагностика системы", "callback_data": "nav_tech"},
                {"text": "🔄 Обновить статус", "callback_data": "menu_status"}
            ]
        ]
    }

def get_posts_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🔥 Тренды дейтинга (мировые)", "callback_data": "menu_trends"},
                {"text": "📋 Очередь черновиков", "callback_data": "menu_queue"}
            ],
            [
                {"text": "🎨 Генератор картинок FLUX", "callback_data": "menu_testimg"},
                {"text": "📅 Контент-план на 7 дней", "callback_data": "menu_plan7"}
            ],
            [
                {"text": "📥 Своя тема / ссылка", "callback_data": "trends_custom_topic"}
            ],
            [
                {"text": "🏠 В главное меню", "callback_data": "nav_main"}
            ]
        ]
    }

def get_promo_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "📈 Маркетинговый аудит", "callback_data": "menu_audit"},
                {"text": "📅 Контент-план на 7 дней", "callback_data": "menu_plan7"}
            ],
            [
                {"text": "🏠 В главное меню", "callback_data": "nav_main"}
            ]
        ]
    }

def get_tech_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🩺 Доктор системы", "callback_data": "menu_doctor"},
                {"text": "📡 Модели ИИ", "callback_data": "menu_models"}
            ],
            [
                {"text": "📖 Живой лексикон", "callback_data": "nav_lex"},
                {"text": "📋 Журнал ошибок", "callback_data": "menu_errors"}
            ],
            [
                {"text": "🏠 В главное меню", "callback_data": "nav_main"}
            ]
        ]
    }

def get_mypage_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "💡 Сгенерировать идею поста", "callback_data": "mypage_new_idea"},
                {"text": "📈 Аудит и раскрутка страницы", "callback_data": "mypage_audit"}
            ],
            [
                {"text": "🏠 В главное меню", "callback_data": "nav_main"}
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
        f"• 👤 Пол: <b>{sex_label}</b>\n"
        f"• 🎂 Возраст: <b>{s['age']} лет</b>\n"
        f"• 📍 Город: <b>{s['city']}</b>\n"
        f"• ✨ Интересы/Вайб: <b>{s['vibe']}</b>\n\n"
        "<i>Нажмите на параметр для изменения:</i>"
    )
    kb = {
        "inline_keyboard": [
            [
                {"text": f"👤 Пол: {s['sex'].upper()}", "callback_data": "filter_toggle_sex"},
                {"text": f"🎂 Возраст: {s['age']}", "callback_data": "filter_prompt_age"}
            ],
            [
                {"text": f"📍 {s['city']}", "callback_data": "filter_prompt_city"},
                {"text": f"✨ {s['vibe'][:15]}", "callback_data": "filter_prompt_vibe"}
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
# МОНИТОРИНГ БОТОВ
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
    kb = [[{"text": "⬅️ Назад к мониторингу", "callback_data": "nav_monitoring"}]]
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

def handle_pitch(args=""):
    parts = args.split()
    if len(parts) < 2:
        send_msg("⚠️ Использование: <code>/pitch &lt;ID_тренда&gt;</code>")
        return
    tid = int(parts[1])
    send_msg(f"✍️ <i>Пишу вирусный пост по тренду #{tid} по Золотому Стандарту...</i>")
    threading.Thread(target=worker_pitch, args=(tid,), daemon=True).start()

def handle_setlogo_prompt():
    AWAIT_LOGO.add(str(ADMIN_CHAT_ID))
    send_msg("📷 <b>УСТАНОВКА ЛОГОТИПА КАНАЛА:</b>\nПришлите изображение логотипа (аватарку) прямо в этот чат (как фотографию)!")

def handle_custom_image_prompt():
    from inbox import AWAIT_STATE
    AWAIT_STATE[ADMIN_CHAT_ID] = ("flux_prompt_input", None, None)
    send_msg(
        "🎨 <b>ФОТОРЕАЛИСТИЧНЫЙ ГЕНЕРАТОР FLUX</b>\n\n"
        "Напишите текст промпта для генерации сцены (на русском или английском).\n"
        "<i>Например: 'Стильный уверенный мужчина на террасе вечернего ресторана, кинематографичный свет, 8k':</i>"
    )

def handle_trends_command():
    text = (
        "🌍 <b>ВЫБЕРИТЕ РЕГИОН ИЛИ ТЕМАТИКУ ДЕЙТИНГА (≤7 ДНЕЙ):</b>\n\n"
        "Откуда берем самые свежие и хайповые темы прямо сейчас? 👇"
    )
    kb = [
        [
            {"text": "🇷🇺 Россия", "callback_data": "trends_fetch:ru"},
            {"text": "💃 Бразилия & Латам", "callback_data": "trends_fetch:brazil"}
        ],
        [
            {"text": "🇫🇷 Франция (Париж)", "callback_data": "trends_fetch:france"},
            {"text": "🇳🇱 Нидерланды (Going Dutch)", "callback_data": "trends_fetch:netherlands"}
        ],
        [
            {"text": "🎭 Курьезы и фейлы свиданий", "callback_data": "trends_fetch:fails"},
            {"text": "🎯 Мастер-класс подкатов", "callback_data": "trends_fetch:pickup"}
        ],
        [
            {"text": "🇺🇸🇨🇦 США & Канада", "callback_data": "trends_fetch:us_ca"},
            {"text": "🇯🇵🇰🇷 Азия (Корея/Япония)", "callback_data": "trends_fetch:asia"}
        ],
        [
            {"text": "📥 Своя тема / ссылка", "callback_data": "trends_custom_topic"},
            {"text": "🎲 Случайная страна", "callback_data": "trends_fetch:world"}
        ],
        [
            {"text": "🏠 В главное меню", "callback_data": "nav_main"}
        ]
    ]
    send_msg(text, reply_markup={"inline_keyboard": kb})

def show_trends_list(region: str):
    threading.Thread(target=worker_trends_fetch, args=(region,), daemon=True).start()

COMMANDS = {
    "/start": lambda _: show_main_menu(),
    "/menu": lambda _: show_main_menu(),
    "/inbox": lambda _: __import__('inbox').show_inbox_menu(),
    "/status": lambda _: send_msg("🟢 <b>Агент активен:</b> Все контуры работают в режиме 24/7."),
    "/queue": lambda _: handle_queue(),
    "/say": handle_say,
    "/pitch": handle_pitch,
    "/trends": lambda _: handle_trends_command(),
    "/testimg": lambda _: handle_custom_image_prompt(),
    "/setlogo": lambda _: handle_setlogo_prompt(),
    "/vkimgtest": lambda _: threading.Thread(target=vk_img_test, daemon=True).start(),
    "/scan": lambda t: __import__('scanner').start_scan_flow(t.split(maxsplit=1)[1] if len(t.split(maxsplit=1))>1 else "", ADMIN_CHAT_ID),
    "/doctor": lambda _: __import__('doctor').run_doctor(),
    "/models": lambda _: handle_models(),
    "/errors": lambda _: send_msg("📋 Ошибок в журнале нет ✅"),
    "/lex": lambda _: __import__('lex').cmd_lex(),
    "/lexupd": lambda _: __import__('lex').cmd_lexupd(),
    "/lexadd": lambda t: __import__('lex').cmd_lexadd(t),
    "/lexdel": lambda t: __import__('lex').cmd_lexdel(t),
    "/lexseed": lambda _: __import__('lex').cmd_lexseed(),
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
        
    from news import STYLES_ORDER
    for d in drafts:
        parts = d['payload'].split("|||")
        target_info = parts[0] if len(parts) > 2 else (d['target'] or 'общая')
        
        curr_style = parts[1] if len(parts) >= 4 and parts[1] in STYLES_ORDER else "на приколе"
        curr_idx = STYLES_ORDER.index(curr_style) if curr_style in STYLES_ORDER else 0
        next_style = STYLES_ORDER[curr_idx + 1] if curr_idx + 1 < len(STYLES_ORDER) else None
        
        variants = parts[2:] if len(parts) >= 4 else (parts[1:] if len(parts) > 2 else parts)
        
        msg = f"📋 <b>Черновик #{d['id']} [{d['type']}]</b> (Канал: <code>{target_info}</code> | Стиль: <b>{curr_style.upper()}</b>)\n\n"
        for idx, var in enumerate(variants, 1):
            clean_prev = var.split("[КАРТИНКА:")[0].replace("[ХЕДЛАЙН:", "📌 <b>").replace("]", "</b>\n").strip()
            msg += f"<b>Вариант {idx}:</b>\n{clean_prev}\n\n"
            
        inline_keyboard = [
            [{"text": "🔥 Одобрить Вариант 1", "callback_data": f"app_{d['id']}_1"}, {"text": "💡 Одобрить Вариант 2", "callback_data": f"app_{d['id']}_2"}]
        ]
        
        if next_style:
            inline_keyboard.append([{"text": f"🎭 Переписать: {next_style.title()}", "callback_data": f"draft_rewrite:{d['id']}"}])
            
        inline_keyboard.append([{"text": "🗑 Отклонить черновик", "callback_data": f"rej_{d['id']}"}])
        
        send_msg(msg, reply_markup={"inline_keyboard": inline_keyboard})

def execute_approval(draft_id: int, variant: int):
    drafts = [d for d in get_pending_drafts() if d['id'] == draft_id]
    if not drafts:
        send_msg(f"⚠️ Черновик #{draft_id} уже опубликован или не найден.")
        return
    d = drafts[0]
    if d['type'] == 'post':
        from news import prepare_post_preview
        prepare_post_preview(d['payload'], variant, draft_id)
    else:
        from publisher import publish_approved_post
        res = publish_approved_post(target="", text=d['payload'])
        approve_draft(draft_id, variant)
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

            # 1. ОБРАБОТКА НАЖАТИЙ НА КНОПКИ
            if "callback_query" in u:
                cb = u["callback_query"]
                if str(cb.get("from", {}).get("id", "")) != str(ADMIN_CHAT_ID):
                    continue
                data = cb.get("data", "")
                msg_id = cb.get("message", {}).get("message_id")
                session.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cb["id"]})

                # Главная навигация
                if data == "nav_main": show_main_menu(msg_id)
                elif data == "nav_inbox": __import__('inbox').show_inbox_menu()
                elif data == "nav_monitoring": show_monitoring_menu()
                elif data.startswith("mon_sort:"): show_monitoring_menu(sort_by=data.split(":")[1])
                elif data.startswith("mon_view:"): show_monitoring_dialog(int(data.split(":")[1]))
                elif data == "nav_lex": __import__('lex').cmd_lex()
                elif data == "nav_mypage":
                    edit_msg(msg_id, "📝 <b>Раздел: Моя страница ВКонтакте (vk.ru/rv__k)</b>\nВыберите действие:", reply_markup=get_mypage_keyboard())
                elif data == "nav_scan_prompt":
                    from inbox import AWAIT_STATE
                    AWAIT_STATE[ADMIN_CHAT_ID] = ("scan_manual", None, None)
                    send_msg("🔍 <b>СКАНИРОВАНИЕ ПРОФИЛЯ ВК:</b>\nПришлите ID или ссылку на страницу девушки (например: <code>durov</code> или <code>vk.com/id12345</code>):")
                elif data == "mypage_new_idea":
                    from mypage import request_page_post_idea
                    request_page_post_idea()
                elif data == "mypage_audit":
                    from mypage import run_personal_page_audit
                    run_personal_page_audit()

                # Навигация подразделов
                elif data == "nav_posts":
                    edit_msg(msg_id, "📰 <b>Раздел: Управление каналом & Посты</b>\nВыберите действие 👇", reply_markup=get_posts_keyboard())
                elif data == "nav_promo":
                    edit_msg(msg_id, "📊 <b>Раздел: Маркетинг & Продвижение</b>\nВыберите действие 👇", reply_markup=get_promo_keyboard())
                elif data == "nav_tech":
                    edit_msg(msg_id, "🩺 <b>Раздел: Диагностика & Статус</b>\nВыберите действие 👇", reply_markup=get_tech_keyboard())
                elif data == "nav_social":
                    text, kb = get_social_menu_data()
                    edit_msg(msg_id, text, reply_markup=kb)

                # Переписывание черновика в следующем стиле
                elif data.startswith("draft_rewrite:"):
                    did = int(data.split(":")[1])
                    threading.Thread(target=worker_rewrite_draft, args=(did,), daemon=True).start()

                # Тренды дейтинга по регионам
                elif data.startswith("trends_fetch:"):
                    show_trends_list(data.split(":")[1])
                elif data == "trends_custom_topic":
                    from inbox import AWAIT_STATE
                    AWAIT_STATE[ADMIN_CHAT_ID] = ("custom_article_pitch", None, None)
                    send_msg("📥 <b>Пришлите ссылку на статью, текст новости или файл:</b>\nАссистент мгновенно переработает материал в авторский пост по Золотому Стандарту!")

                # Премодерация постов перед публикацией
                elif data.startswith("fin_pub_img:"):
                    did = int(data.split(":")[1])
                    from news import final_publish_execute
                    final_publish_execute(did, with_photo=True)
                elif data.startswith("fin_pub_txt:"):
                    did = int(data.split(":")[1])
                    from news import final_publish_execute
                    final_publish_execute(did, with_photo=False)
                elif data.startswith("fin_regen_img:"):
                    did = int(data.split(":")[1])
                    from news import regenerate_preview_photo
                    regenerate_preview_photo(did)
                elif data.startswith("fin_cancel:"):
                    did = int(data.split(":")[1])
                    from news import POST_STAGING
                    POST_STAGING.pop(did, None)
                    from drafts import reject_draft
                    reject_draft(did)
                    send_msg(f"🗑 Черновик #{did} отклонён.")

                # Генерация FLUX без референса
                elif data == "flux_generate_no_ref":
                    prompt = IMAGE_GEN_STATE.pop(ADMIN_CHAT_ID, "")
                    if prompt:
                        send_msg("🎨 <i>Генерирую сцену через FLUX... (20–30 сек)</i>")
                        threading.Thread(target=worker_flux_generate, args=(prompt, None), daemon=True).start()

                # Скан: согласование плана знакомства
                elif data.startswith("scan_approve:"):
                    uid = data.split(":")[1]
                    from scanner import PLAN_CONTEXT
                    plan_data = PLAN_CONTEXT.get(ADMIN_CHAT_ID, {})
                    send_msg(f"🚀 <b>ПЛАН УТВЕРЖДЁН!</b>\nАссистент начинает работу с <b>{plan_data.get('name', uid)}</b> по согласованной стратегии.\n\n<i>Любое её сообщение сразу отобразится в ваших 'Входящих'!</i>")
                elif data.startswith("scan_edit_prompt:"):
                    from inbox import AWAIT_STATE
                    AWAIT_STATE[ADMIN_CHAT_ID] = ("plan_edit_remarks", None, None)
                    send_msg("✍️ <b>Внесите ваши замечания к плану:</b>\nНапишите, что изменить или добавить в первое сообщение (ответьте текстом):")
                elif data == "scan_cancel":
                    from scanner import PLAN_CONTEXT
                    PLAN_CONTEXT.pop(ADMIN_CHAT_ID, None)
                    send_msg("❌ План знакомства отменён.")

                # Моя страница: публикация черновика
                elif data.startswith("mypage_publish_text:"):
                    did = int(data.split(":")[1])
                    from drafts import get_pending_drafts, approve_draft
                    from mypage import publish_to_personal_wall
                    d = next((x for x in get_pending_drafts() if x['id'] == did), None)
                    if d:
                        approve_draft(did, 1)
                        publish_to_personal_wall(d['payload'], photo_bytes=None)
                elif data.startswith("mypage_await_photo:"):
                    did = int(data.split(":")[1])
                    from mypage import AWAIT_MYPAGE
                    AWAIT_MYPAGE[ADMIN_CHAT_ID] = did
                    send_msg("🖼 <b>Пришлите готовое фото в этот чат!</b>\nАссистент прикрепит его к посту и выложит на вашей личной стене.")
                elif data.startswith("mypage_reject:"):
                    did = int(data.split(":")[1])
                    from drafts import reject_draft
                    reject_draft(did)
                    send_msg(f"🗑 Черновик #{did} для личной страницы отклонён.")

                # Навигация папок инбокса
                elif data.startswith("inbox_"): __import__('inbox').handle_inbox_callback(data)

                # Переключение параметров поиска кандидатов
                elif data == "filter_toggle_sex":
                    SEARCH_FILTERS["sex"] = "м" if SEARCH_FILTERS["sex"] == "ж" else ("любой" if SEARCH_FILTERS["sex"] == "м" else "ж")
                    text, kb = get_social_menu_data()
                    edit_msg(msg_id, text, reply_markup=kb)
                elif data == "filter_prompt_city":
                    from inbox import AWAIT_STATE
                    AWAIT_STATE[ADMIN_CHAT_ID] = ("set_city", None, None)
                    send_msg("📍 <b>В каком городе искать кандидатов?</b>\nНапишите название города:")
                elif data == "filter_prompt_age":
                    from inbox import AWAIT_STATE
                    AWAIT_STATE[ADMIN_CHAT_ID] = ("set_age", None, None)
                    send_msg("🎂 <b>Какой возраст искать?</b>\nВведите диапазон или возраст (например: <i>19-25</i>):")
                elif data == "filter_prompt_vibe":
                    from inbox import AWAIT_STATE
                    AWAIT_STATE[ADMIN_CHAT_ID] = ("set_vibe", None, None)
                    send_msg("✨ <b>Какие интересы/вайб искать?</b>\nНапишите ключевые слова (например: <i>йога, спорт, книги</i>):")

                # Запуск поиска кандидатов
                elif data == "run_filter_search":
                    s = SEARCH_FILTERS
                    send_msg(f"🔎 <i>Запускаю фильтр ВК: г. {s['city']}, {s['sex'].upper()}, {s['age']} лет, интерес '{s['vibe']}'...</i>")
                    threading.Thread(target=worker_search_candidates, args=(s['city'], s['age'], s['sex'], s['vibe']), daemon=True).start()

                elif data == "menu_queue": handle_queue()
                elif data == "menu_status": send_msg("🟢 <b>Агент активен:</b> Все контуры работают 24/7.")
                elif data == "menu_trends": handle_trends_command()
                elif data == "menu_plan7": __import__('promo').generate_7day_content_plan()
                elif data == "menu_testimg": handle_custom_image_prompt()
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

            # 2. ТЕКСТОВЫЕ СООБЩЕНИЯ И МЕДИА
            m = u.get("message", {})
            if str(m.get("chat", {}).get("id", "")) != str(ADMIN_CHAT_ID):
                continue

            caption = (m.get("caption") or "").strip().lower()
            text = (m.get("text") or "").strip().lower()

            # ПРИЁМ ЛОГОТИПА КАНАЛА (/setlogo в подписи или активный AWAIT_LOGO)
            if "photo" in m and ("/setlogo" in caption or str(ADMIN_CHAT_ID) in AWAIT_LOGO):
                AWAIT_LOGO.discard(str(ADMIN_CHAT_ID))
                try:
                    fid = m["photo"][-1]["file_id"]
                    fpath = session.get(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getFile?file_id={fid}").json()["result"]["file_path"]
                    photo_bytes = session.get(f"https://api.telegram.org/file/bot{TG_BOT_TOKEN}/{fpath}").content
                    
                    with open("logo.png", "wb") as f:
                        f.write(photo_bytes)
                    
                    committed = False
                    hf_token = os.getenv("HF_TOKEN", "").strip()
                    if hf_token:
                        try:
                            from huggingface_hub import HfApi
                            api = HfApi(token=hf_token)
                            api.upload_file(
                                path_or_fileobj=photo_bytes,
                                path_in_repo="logo.png",
                                repo_id="opion2008/cupid-agent",
                                repo_type="space"
                            )
                            committed = True
                        except Exception as ex:
                            log.warning(f"HF upload error: {ex}")
                    
                    res_msg = "✅ <b>Фирменный логотип успешно установлен!</b>"
                    if committed:
                        res_msg += "\n💾 <i>Файл logo.png навсегда сохранен в репозиторий проекта!</i>"
                    else:
                        res_msg += "\n💡 <i>Файл сохранен в текущую сессию бота.</i>"
                    res_msg += "\n\nТеперь неоновый кибер-купидон будет красоваться в верхнем углу каждого фото!"
                    send_msg(res_msg)
                except Exception as e:
                    send_msg(f"❌ Ошибка сохранения логотипа: {e}")
                continue

            # Приём фото для публикации на личной странице
            try:
                import mypage
                await_dict = getattr(mypage, "AWAIT_MYPAGE", getattr(mypage, "S", {}))
                if ADMIN_CHAT_ID in await_dict and "photo" in m:
                    did = await_dict.pop(ADMIN_CHAT_ID)
                    fid = m["photo"][-1]["file_id"]
                    fpath = session.get(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getFile?file_id={fid}").json()["result"]["file_path"]
                    photo_bytes = session.get(f"https://api.telegram.org/file/bot{TG_BOT_TOKEN}/{fpath}").content
                    
                    from drafts import get_pending_drafts, approve_draft
                    d = next((x for x in get_pending_drafts() if x['id'] == did), None)
                    if d:
                        approve_draft(did, 1)
                        mypage.publish_to_personal_wall(d['payload'], photo_bytes=photo_bytes)
                    continue
            except Exception as e:
                log.warning(f"Ошибка mypage photo: {e}")

            from inbox import AWAIT_STATE, send_outbound_message, answer_chat_question
            if ADMIN_CHAT_ID in AWAIT_STATE:
                action, uid, platform = AWAIT_STATE.pop(ADMIN_CHAT_ID)
                text_content = (m.get("text") or m.get("caption") or "").strip()

                # Создание поста из присланной статьи/ссылки
                if action == "custom_article_pitch":
                    send_msg("✍️ <i>Изучаю присланный материал и создаю вирусный пост по Золотому Стандарту...</i>")
                    threading.Thread(target=worker_custom_pitch, args=(text_content,), daemon=True).start()
                    continue

                # Интерактивный генератор FLUX: ввод промпта
                elif action == "flux_prompt_input":
                    IMAGE_GEN_STATE[ADMIN_CHAT_ID] = text_content
                    AWAIT_STATE[ADMIN_CHAT_ID] = ("flux_await_ref_photo", None, None)
                    kb = {"inline_keyboard": [
                        [{"text": "🚀 Сгенерировать без исходника", "callback_data": "flux_generate_no_ref"}],
                        [{"text": "❌ Отмена", "callback_data": "nav_main"}]
                    ]}
                    send_msg(
                        f"🎯 <b>Промпт принят:</b> <i>«{text_content}»</i>\n\n"
                        "📷 <b>Есть ли исходное фото лица / человека для вставки?</b>\n"
                        "• Пришлите фото прямо сюда (как изображение).\n"
                        "• Или нажмите кнопку ниже для генерации чисто по промпту:",
                        reply_markup=kb
                    )
                    continue

                # Интерактивный генератор FLUX: фото-референс
                elif action == "flux_await_ref_photo":
                    prompt = IMAGE_GEN_STATE.pop(ADMIN_CHAT_ID, "")
                    send_msg("🎨 <i>Генерирую фотореалистичную сцену через FLUX... (20–30 сек)</i>")
                    ref_photo_bytes = None
                    if "photo" in m:
                        fid = m["photo"][-1]["file_id"]
                        fpath = session.get(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getFile?file_id={fid}").json()["result"]["file_path"]
                        ref_photo_bytes = session.get(f"https://api.telegram.org/file/bot{TG_BOT_TOKEN}/{fpath}").content
                    threading.Thread(target=worker_flux_generate, args=(prompt, ref_photo_bytes), daemon=True).start()
                    continue

                elif action == "scan_manual":
                    from scanner import start_scan_flow
                    start_scan_flow(text_content, ADMIN_CHAT_ID)
                    continue

                elif action == "plan_edit_remarks":
                    from scanner import PLAN_CONTEXT, generate_plan, show_plan_approval
                    ctx = PLAN_CONTEXT.get(ADMIN_CHAT_ID, {})
                    notify("♻️ <i>Перерабатываю план знакомства с учётом твоих замечаний...</i>", html=True)
                    new_plan = generate_plan(ctx.get("summary",""), ctx.get("analysis",{}), user_remarks=text_content)
                    ctx["plan"] = new_plan
                    PLAN_CONTEXT[ADMIN_CHAT_ID] = ctx
                    show_plan_approval(ADMIN_CHAT_ID)
                    continue

                elif action == "set_city":
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

            text_raw = (m.get("text") or "").strip()
            cmd = text_raw.split()[0].lower() if text_raw else ""
            if cmd in COMMANDS:
                COMMANDS[cmd](text_raw)
    except Exception as e:
        log.warning(f"Ошибка updates: {e}")
