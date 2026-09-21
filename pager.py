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
    send_msg("🎨 <i>Генерирую тестовую иллюстрацию... (30-40 сек)</i>")
    from imagegen import generate_image
    from notifier import PAGER_TOKEN, CHAT_ID
    photo = generate_image("уютный вечер в кафе, пара пьет кофе, теплый свет, романтичная плоская иллюстрация")
    if photo:
        requests.post(
            f"https://api.telegram.org/bot{PAGER_TOKEN}/sendPhoto",
            data={"chat_id": CHAT_ID, "caption": "🎨 <b>Тест генератора картинок успешен!</b>", "parse_mode": "HTML"},
            files={"photo": ("test.jpg", io.BytesIO(photo), "image/jpeg")}, timeout=30
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
            clean_preview = var.split("[КАРТИНКА:")[0].strip()
            has_img = " 🖼 <i>(с иллюстрацией)</i>" if "[КАРТИНКА:" in var else ""
            msg += f"<b>Вариант {idx}{has_img}:</b>\n<i>«{clean_preview}»</i>\n\n"

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

def handle_approve(draft_id: int, variant: int):
    from drafts import get_pending_drafts, approve_draft
    drafts = [d for d in get_pending_drafts() if d['id'] == draft_id]
    if not drafts:
        send_msg(f"⚠️ Черновик #{draft_id} не найден.")
        return
        
    d = drafts[0]
    if d['type'] == 'post':
        from news import publish_approved_news
        approve_draft(draft_id, variant)
        publish_approved_news(d['payload'], variant)
    else:
        success, text = approve_draft(draft_id, variant)
        from publisher import publish_approved_post
        publish_approved_post(target="", text=text)
        send_msg(f"✅ Черновик #{draft_id} утверждён.")

def handle_reject(draft_id: int):
    if reject_draft(draft_id):
        send_msg(f"🗑 <b>Черновик #{draft_id} отклонён.</b>")
    else:
        send_msg(f"⚠️ Черновик #{draft_id} не найден.")

def process_pager_updates():
    if not TG_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates"
    try:
        res = requests.get(url, params={"timeout": 3}, timeout=6).json()
        for u in res.get("result", []):
            update_id = u["update_id"]
            requests.get(url, params={"offset": update_id + 1, "timeout": 0}, timeout=4)
            
            if "callback_query" in u:
                cb = u["callback_query"]
                data = cb.get("data", "")
                requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cb["id"], "text": "Действие принято!"})
                if data.startswith("app_"):
                    _, d_id, v_idx = data.split("_")
                    handle_approve(int(d_id), int(v_idx))
                elif data.startswith("rej_"):
                    _, d_id = data.split("_")
                    handle_reject(int(d_id))
                continue

            m = u.get("message", {})
            text = m.get("text", "").strip()
            cmd = text.split()[0] if text else ""
            if cmd == "/approve":
                p = text.split()
                if len(p) >= 2: handle_approve(int(p[1]), int(p[2]) if len(p) > 2 else 1)
            elif cmd == "/reject":
                p = text.split()
                if len(p) >= 2: handle_reject(int(p[1]))
            elif cmd == "/testimg": handle_testimg()
            elif cmd == "/models": handle_models()
            elif cmd == "/doctor": handle_doctor()
            elif cmd == "/errors": handle_errors()
            elif cmd == "/queue": handle_queue()
            elif cmd == "/status": handle_status()
    except Exception as e:
        print(f"Ошибка updates: {e}")
