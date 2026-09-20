import os
import requests
import logging
import asyncio
from drafts import get_pending_drafts, approve_draft, reject_draft

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

def send_msg(text: str):
    if not TG_BOT_TOKEN:
        print(f"[PAGER] {text}")
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Ошибка отправки pager: {e}")

def handle_status(args=""):
    send_msg("🟢 <b>Агент активен:</b> Все контуры (Антисон, Userbot TG, LLM-мозг) функционируют штатно.")

def handle_queue(args=""):
    drafts = get_pending_drafts()
    if not drafts:
        send_msg("📭 <b>Очередь пуста:</b> Нет действий, требующих вашего решения.")
        return
    
    msg = "📋 <b>Очередь черновиков на согласование:</b>\n\n"
    for d in drafts:
        msg += f"🔹 <b>#{d['id']} [{d['type']}]</b> (Цель: <code>{d['target'] or 'общая'}</code>)\n"
        variants = d['payload'].split("|||")
        for idx, var in enumerate(variants, 1):
            msg += f"  <i>Вариант {idx}:</i> {var.strip()[:180]}...\n"
        msg += f"👉 <code>/approve {d['id']} 1</code> | <code>/reject {d['id']}</code>\n\n"
    send_msg(msg)

def handle_approve(args=""):
    parts = args.split()
    if len(parts) < 2:
        send_msg("⚠️ Использование: <code>/approve &lt;ID_черновика&gt; &lt;номер_варианта&gt;</code>")
        return
    try:
        draft_id = int(parts[1])
        variant = int(parts[2]) if len(parts) > 2 else 1
        success, text = approve_draft(draft_id, variant)
        if success:
            send_msg(f"✅ <b>Черновик #{draft_id} утверждён!</b>\nВыбранный текст:\n«{text[:300]}...»")
        else:
            send_msg(f"❌ <b>Ошибка:</b> {text}")
    except ValueError:
        send_msg("⚠️ ID и номер варианта должны быть числами.")

def handle_reject(args=""):
    parts = args.split()
    if len(parts) < 2:
        send_msg("⚠️ Использование: <code>/reject &lt;ID_черновика&gt;</code>")
        return
    try:
        draft_id = int(parts[1])
        if reject_draft(draft_id):
            send_msg(f"🗑 <b>Черновик #{draft_id} отклонён.</b>")
        else:
            send_msg(f"⚠️ Черновик #{draft_id} не найден.")
    except ValueError:
        send_msg("⚠️ ID должен быть числом.")

def handle_say(args=""):
    parts = args.split(maxsplit=2)
    if len(parts) < 3:
        send_msg("⚠️ Использование: <code>/say &lt;юзернейм/ID&gt; &lt;текст_сообщения&gt;</code>\nПример: <code>/say @durov Привет!</code>")
        return
    target, text_to_send = parts[1], parts[2]
    send_msg(f"📨 Сообщение поставлено в очередь отправки для <b>{target}</b>:\n«{text_to_send}»")

COMMANDS = {
    "/status": handle_status,
    "/queue": handle_queue,
    "/approve": handle_approve,
    "/reject": handle_reject,
    "/say": handle_say,
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
