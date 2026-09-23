import os
import io
import logging
import requests
from drafts import get_pending_drafts, approve_draft, reject_draft

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

ERR_BUF = io.StringIO()
_err_handler = logging.StreamHandler(ERR_BUF)
_err_handler.setLevel(logging.WARNING)
logging.getLogger().addHandler(_err_handler)

def send_msg(text: str, reply_markup=None):
    from notifier import notify
    notify(text, html=True)

def handle_status(args=""):
    send_msg("🟢 <b>Агент активен:</b> Все контуры (Пульт 24/7, Мониторинг, Тренды, Соц-модуль) в строю.")

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
    send_msg("🔥 <i>Сканирую тренды дейтинга, соцсети и новости глянца...</i>")
    try:
        from trends import fetch_rss_trends, get_hot_trends
        fetch_rss_trends()
        hot = get_hot_trends(6)
        if not hot:
            send_msg("📭 Новых трендов пока не обнаружено.")
            return
        out = ["🔥 <b>[ГОРЯЧИЕ ИНФОПОВОДЫ И ТРЕНДЫ СЕЙЧАС]</b>\n"]
        for tid, src, title, heat, url in hot:
            out.append(f"🔹 <b>#{tid}</b> [{src.upper()}] <i>(Хайп-балл: {heat:.1f})</i>\n«{title}»\n👉 Сделать пост: <code>/pitch {tid}</code>\n")
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
            send_msg(f"✅ На основе тренда #{tid} создан <b>Черновик поста #{did}</b>! Отправьте /queue для просмотра.")
        else:
            send_msg(f"⚠️ Тренд #{tid} не найден.")
    except Exception as e:
        send_msg(f"❌ Сбой питча: {e}")

def handle_find(args=""):
    # Пример: /find Москва 20-28 ж
    parts = args.split()
    if len(parts) < 4:
        send_msg("⚠️ Использование: <code>/find &lt;Город&gt; &lt;Возраст&gt; &lt;Пол: м/ж&gt;</code>\nПример: <code>/find Москва 20-27 ж</code>")
        return
    city, age_range, sex = parts[1], parts[2], parts[3]
    try:
        a_from, a_to = map(int, age_range.split("-"))
        send_msg(f"🔎 <i>Ищу открытые анкеты ВК в г. {city} ({a_from}–{a_to} лет)...</i>")
        from social import search_vk_candidates
        users = search_vk_candidates(city, a_from, a_to, sex)
        if not users:
            send_msg("📭 Кандидатов с открытой личкой не найдено.")
            return
        out = [f"👥 <b>[КАНДИДАТЫ ДЛЯ ЗНАКОМСТВА: {city}]</b>\n"]
        for idx, u in enumerate(users[:6], 1):
            name = f"{u.get('first_name')} {u.get('last_name')}"
            uid = u.get("id")
            about = u.get("interests") or u.get("about") or "без описания"
            out.append(f"<b>{idx}. {name}</b> (id{uid})\n<i>Интересы: {about[:70]}...</i>\n👉 Начать диалог: <code>/pick {uid} Познакомиться легко, позвать на кофе</code>\n")
        send_msg("\n".join(out))
    except Exception as e:
        send_msg(f"❌ Ошибка поиска: {e}")

def handle_pick(args=""):
    parts = args.split(maxsplit=2)
    if len(parts) < 3:
        send_msg("⚠️ Использование: <code>/pick &lt;VK_ID&gt; &lt;Цель/Задание&gt;</code>")
        return
    uid, task = parts[1], parts[2]
    try:
        from social import pick_candidate_task
        pick_candidate_task(uid, "vk", task)
        send_msg(f"💌 <b>Кандидат id{uid} взят в работу!</b>\nЗадача: «{task}».\n<i>Агент начнет общение с юмором и без самораскрытия бота. При вопросах о боте — сразу уведомит вас!</i>")
    except Exception as e:
        send_msg(f"❌ Ошибка: {e}")

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
            data={"chat_id": CHAT_ID, "caption": "🎨 <b>Тест генератора: без людей и без вотермарки!</b>", "parse_mode": "HTML"},
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
    send_msg(f"📨 Сообщение в очереди для <b>{parts[1]}</b>:\n«{parts[2]}»")

COMMANDS = {
    "/status": handle_status,
    "/queue": handle_queue,
    "/say": handle_say,
    "/doctor": handle_doctor,
    "/models": handle_models,
    "/errors": handle_errors,
    "/testimg": handle_testimg,
    "/trends": handle_trends,
    "/pitch": handle_pitch,
    "/find": handle_find,
    "/pick": handle_pick,
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
            
            if "callback_query" in u:
                cb = u["callback_query"]
                if str(cb.get("from", {}).get("id", "")) != str(ADMIN_CHAT_ID):
                    continue
                data = cb.get("data", "")
                requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery", json={
                    "callback_query_id": cb["id"],
                    "text": "🚀 Принято! Запускаю публикацию..."
                })
                if data.startswith("app_"):
                    _, d_id, v_idx = data.split("_")
                    execute_approval(int(d_id), int(v_idx))
                elif data.startswith("rej_"):
                    _, d_id = data.split("_")
                    execute_rejection(int(d_id))
                continue

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
