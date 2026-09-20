import os
import requests
import logging
from drafts import get_pending_drafts, approve_draft, reject_draft

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

def send_msg(text: str):
    """Безопасная отправка текстового сообщения администратору."""
    if not TG_BOT_TOKEN:
        print(f"[PAGER] {text}")
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": ADMIN_CHAT_ID, "text": text}
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Ошибка отправки pager: {e}")

def handle_status(args=""):
    send_msg("🟢 Агент на связи. Все системы работают в штатном режиме.")

def handle_queue(args=""):
    drafts = get_pending_drafts()
    if not drafts:
        send_msg("📭 Очередь пуста. Нет действий, требующих согласования.")
        return
    
    msg = "📋 <b>Очередь черновиков на согласование:</b>\n\n"
    for d in drafts:
        msg += f"🔹 <b>#{d['id']} [{d['type']}]</b> (Цель: {d['target'] or 'общая'})\n"
        variants = d['payload'].split("|||")
        for idx, var in enumerate(variants, 1):
            msg += f"  Вариант {idx}: {var.strip()[:150]}...\n"
        msg += f"👉 <i>Одобрить: /approve {d['id']} 1</i> | <i>Отклонить: /reject {d['id']}</i>\n\n"
    send_msg(msg)

def handle_approve(args=""):
    parts = args.split()
    if len(parts) < 2:
        send_msg("⚠️ Использование: /approve <ID_черновика> <номер_варианта>")
        return
    try:
        draft_id = int(parts[1])
        variant = int(parts[2]) if len(parts) > 2 else 1
        success, text = approve_draft(draft_id, variant)
        if success:
            send_msg(f"✅ Черновик #{draft_id} утверждён!\nВыбранный текст:\n«{text[:300]}...»\n(Готов к публикации/отправке)")
        else:
            send_msg(f"❌ Ошибка: {text}")
    except ValueError:
        send_msg("⚠️ ID и номер варианта должны быть числами.")

def handle_reject(args=""):
    parts = args.split()
    if len(parts) < 2:
        send_msg("⚠️ Использование: /reject <ID_черновика>")
        return
    try:
        draft_id = int(parts[1])
        if reject_draft(draft_id):
            send_msg(f"🗑 Черновик #{draft_id} отклонён.")
        else:
            send_msg(f"⚠️ Черновик #{draft_id} не найден.")
    except ValueError:
        send_msg("⚠️ ID должен быть числом.")

COMMANDS = {
    "/status": handle_status,
    "/queue": handle_queue,
    "/approve": handle_approve,
    "/reject": handle_reject,
}

def process_pager_updates():
    """Считывает входящие команды от администратора."""
    if not TG_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates"
    try:
        res = requests.get(url, params={"timeout": 5}, timeout=10).json()
        for u in res.get("result", []):
            update_id = u["update_id"]
            # Сдвигаем offset, подтверждая прочтение
            requests.get(url, params={"offset": update_id + 1, "timeout": 0}, timeout=5)
            
            m = u.get("message", {})
            sender_id = str(m.get("chat", {}).get("id", ""))
            if sender_id != str(ADMIN_CHAT_ID):
                continue
            
            text = m.get("text", "").strip()
            cmd = text.split()[0] if text else ""
            if cmd in COMMANDS:
                COMMANDS[cmd](text)
    except Exception as e:
        print(f"Ошибка проверки getUpdates: {e}")
