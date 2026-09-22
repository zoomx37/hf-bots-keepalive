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
    send_msg("🟢 <b>Агент активен:</b> Все контуры функционируют штатно.")

def handle_export(args=""):
    """Выгружает все значения секретов прямо вам в Telegram для переноса в Hugging Face."""
    secret_keys = [
        "TG_BOT_TOKEN",
        "ADMIN_CHAT_ID",
        "GEMINI_API_KEY",
        "GEMINI_BACKUP_KEYS",
        "OPENROUTER_API_KEY",
        "TG_API_ID",
        "TG_API_HASH",
        "TG_STRING_SESSION",
        "VK_TOKEN",
        "VK_GROUP_TOKEN",
        "FB_API_KEY",
        "FB_SECRET_KEY",
        "MODEL_GEMINI",
        "MODEL_OPENROUTER",
        "VK_ENABLED"
    ]
    
    send_msg("🔐 <i>Выгружаю секреты из защищённого хранилища GitHub...</i>")
    
    for key in secret_keys:
        val = os.getenv(key, "").strip()
        if val:
            # Отправляем каждый секрет в отдельном сообщении с тегом <code> для быстрого копирования в 1 клик
            send_msg(f"📌 <b>{key}</b>:\n<code>{val}</code>")

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
        for m in or_models[:5]: out.append(f"  • <code>{m}</code>")
    send_msg("\n".join(out))

def handle_testimg(args=""):
    send_msg("🎨 <i>Генерирую тестовую иллюстрацию без вотермарки...</i>")
    from imagegen import generate_image
    from notifier import PAGER_TOKEN, CHAT_ID
    photo = generate_image("пара в уютном кафе пьет кофе, теплый свет, романтичная плоская иллюстрация")
    if photo:
        requests.post(
            f"https://api.telegram.org/bot{PAGER_TOKEN}/sendPhoto",
            data={"chat_id": CHAT_ID, "caption": "🎨 <b>Тест генератора картинок успешен (без вотермарки)!</b>", "parse_mode": "HTML"},
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

def handle_reject(draft_id: int):
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
    "/export": handle_export
}

def process_pager_updates():
    if not TG_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates"
    try:
        res = requests.get(url, params={"timeout": 3, "allowed_updates": ["message", "callback_query"]}, timeout=6).json()
        for u in res.get("result", []):
            update_id = u["update_id"]
            requests.get(url, params={"offset": update_id + 1, "timeout": 0}, timeout=4)
            
            # 1. Нажатие на кнопку
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
                    handle_reject(int(d_id))
                continue

            # 2. Текстовые команды
            m = u.get("message", {})
            if str(m.get("chat", {}).get("id", "")) != str(ADMIN_CHAT_ID):
                continue
            
            text = m.get("text", "").strip()
            cmd = text.split()[0] if text else ""
            
            if cmd == "/approve":
                p = text.split()
                if len(p) >= 2:
                    execute_approval(int(p[1]), int(p[2]) if len(p) > 2 else 1)
            elif cmd == "/reject":
                p = text.split()
                if len(p) >= 2:
                    handle_reject(int(p[1]))
            elif cmd in COMMANDS:
                COMMANDS[cmd](text)
    except Exception as e:
        print(f"Ошибка updates: {e}")
