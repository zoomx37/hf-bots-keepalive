import os
import requests
import logging
from drafts import get_pending_drafts, approve_draft, reject_draft
from publisher import publish_approved_post

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

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

def handle_queue(args=""):
    drafts = get_pending_drafts()
    if not drafts:
        send_msg("📭 <b>Очередь пуста:</b> Нет действий, требующих вашего решения.")
        return
    
    for d in drafts:
        variants = d['payload'].split("|||")
        msg = f"📋 <b>Черновик #{d['id']} [{d['type']}]</b> (Цель: <code>{d['target'] or 'общая'}</code>)\n\n"
        for idx, var in enumerate(variants, 1):
            msg += f"<b>Вариант {idx}:</b>\n<i>«{var.strip()}»</i>\n\n"

        # Создаем удобные интерактивные кнопки
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
        send_msg(f"🚀 <b>Черновик #{draft_id} (Вариант {variant}) утверждён!</b> Отправляю на публикацию...")
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
}

def process_pager_updates():
    """Обработка текстовых команд и нажатий на кнопки."""
    if not TG_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates"
    try:
        res = requests.get(url, params={"timeout": 3}, timeout=6).json()
        for u in res.get("result", []):
            update_id = u["update_id"]
            requests.get(url, params={"offset": update_id + 1, "timeout": 0}, timeout=4)
            
            # 1. Если нажали кнопку под черновиком
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

            # 2. Если отправили команду текстом
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
