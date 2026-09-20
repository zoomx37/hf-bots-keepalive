import os
import io
import logging
import requests
from drafts import get_pending_drafts, approve_draft, reject_draft
from publisher import publish_approved_post

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

ERR_BUF = io.StringIO()
_err_handler = logging.StreamHandler(ERR_BUF)
_err_handler.setLevel(logging.WARNING)
logging.getLogger().addHandler(_err_handler)

def send_msg(text: str, reply_markup=None):
    if not TG_BOT_TOKEN:
        print(f"[PAGER] {text}")
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": ADMIN_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Ошибка отправки pager: {e}")

def handle_status(args=""):
    send_msg("🟢 <b>Агент активен:</b> Все контуры функционируют штатно.")

def handle_models(args=""):
    """Опрашивает API напрямую и выдаёт реальный список моделей в чат."""
    from modelcatalog import list_google, list_groq
    send_msg("📡 <i>Опрашиваю API Google и Groq на доступные модели...</i>")
    
    g_key = os.getenv("GEMINI_API_KEY", "")
    q_key = os.getenv("GROQ_API_KEY", "")
    
    out = ["📡 <b>[ЖИВОЙ КАТАЛОГ МОДЕЛЕЙ ИЗ API]</b>\n"]
    
    g_models = [m for m in list_google(g_key) if "flash" in m]
    out.append("🔹 <b>Google Gemini (flash):</b>")
    if g_models:
        for m in g_models[-6:]:
            out.append(f"  • <code>{m}</code>")
    else:
        out.append("  <i>Нет ответа от API или неверный ключ</i>")

    q_models = [m for m in list_groq(q_key) if "llama" in m or "70b" in m]
    out.append("\n🔹 <b>Groq:</b>")
    if q_models:
        for m in q_models[:6]:
            out.append(f"  • <code>{m}</code>")
    else:
        out.append("  <i>Нет ответа от API</i>")
        
    out.append("\n💡 <i>Любую модель можно закрепить в Secrets через MODEL_GEMINI=...</i>")
    send_msg("\n".join(out))

def handle_errors(args=""):
    ERR_BUF.seek(0)
    lines = ERR_BUF.readlines()
    out = "".join(lines[-12:]) or "Ошибок в журнале нет ✅"
    send_msg(f"📋 <b>Последние записи журнала:</b>\n<pre>{out[-3000:]}</pre>")

def handle_doctor(args=""):
    send_msg("🩺 <i>Запускаю самодиагностику систем...</i>")
    try:
        from doctor import run_doctor
        run_doctor()
    except Exception as e:
        send_msg(f"❌ Ошибка доктора: {e}")

def handle_queue(args=""):
    drafts = get_pending_drafts()
    if not drafts:
        send_msg("📭 <b>Очередь пуста:</b> Нет действий, требующих решения.")
        return
    
    for d in drafts:
        variants = d['payload'].split("|||")
        msg = f"📋 <b>Черновик #{d['id']} [{d['type']}]</b> (Цель: <code>{d['target'] or 'общая'}</code>)\n\n"
        for idx, var in enumerate(variants, 1):
            msg += f"<b>Вариант {idx}:</b>\n<i>«{var.strip()}»</i>\n\n"

        inline_keyboard = [
            [
                {"text": "🔥 Одобрить Вариант 1", "callback_data": f"app_{d['id']}_1"},
                {"text": "💡 Одобрить Вариант 2", "callback_data": f"app_{d['id']}_2"}
            ],
            [
                {"text": "🗑 Отклонить черновик", "callback_data": f"rej_{d['id']}"}
            ]
        ]
        send_msg(msg, reply_markup={"inline_keyboard": inline_keyboard})

def handle_approve(draft_id: int, variant: int):
    success, text = approve_draft(draft_id, variant)
    if success:
        send_msg(f"🚀 <b>Черновик #{draft_id} (Вариант {variant}) утверждён!</b> Публикую...")
        publish_res = publish_approved_post(target="", text=text)
        send_msg(f"📢 <b>Результат публикации:</b>\n{publish_res}")
    else:
        send_msg(f"❌ <b>Ошибка:</b> {text}")

def handle_reject(draft_id: int):
    if reject_draft(draft_id):
        send_msg(f"🗑 <b>Черновик #{draft_id} отклонён.</b>")
    else:
        send_msg(f"⚠️ Черновик #{draft_id} не найден.")

def handle_say(args=""):
    parts = args.split(maxsplit=2)
    if len(parts) < 3:
        send_msg("⚠️ Использование: <code>/say &lt;юзернейм/ID&gt; &lt;текст_сообщения&gt;</code>")
        return
    target, text_to_send = parts[1], parts[2]
    send_msg(f"📨 Сообщение поставлено в очередь для <b>{target}</b>:\n«{text_to_send}»")

COMMANDS = {
    "/status": handle_status,
    "/queue": handle_queue,
    "/say": handle_say,
    "/doctor": handle_doctor,
    "/models": handle_models,
    "/errors": handle_errors,
}

def process_pager_updates():
    if not TG_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates"
    try:
        res = requests.get(url, params={"timeout": 3}, timeout=6).json()
        for u in res.get("result", []):
            update_id = u["update_id"]
            requests.get(url, params={"offset": update_id + 1, "timeout": 0}, timeout=4)
            
            # Клик по инлайн-кнопкам
            if "callback_query" in u:
                cb = u["callback_query"]
                sender_id = str(cb.get("from", {}).get("id", ""))
                if sender_id != str(ADMIN_CHAT_ID):
                    continue
                
                data = cb.get("data", "")
                requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cb["id"], "text": "Действие принято!"})
                
                if data.startswith("app_"):
                    _, d_id, v_idx = data.split("_")
                    handle_approve(int(d_id), int(v_idx))
                elif data.startswith("rej_"):
                    _, d_id = data.split("_")
                    handle_reject(int(d_id))
                continue

            # Текстовые команды
            m = u.get("message", {})
            sender_id = str(m.get("chat", {}).get("id", ""))
            if sender_id != str(ADMIN_CHAT_ID):
                continue
            
            text = m.get("text", "").strip()
            cmd = text.split()[0] if text else ""
            
            if cmd == "/approve":
                parts = text.split()
                if len(parts) >= 2:
                    handle_approve(int(parts[1]), int(parts[2]) if len(parts) > 2 else 1)
            elif cmd == "/reject":
                parts = text.split()
                if len(parts) >= 2:
                    handle_reject(int(parts[1]))
            elif cmd in COMMANDS:
                COMMANDS[cmd](text)
    except Exception as e:
        print(f"Ошибка проверки updates: {e}")
