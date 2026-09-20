import os
import asyncio
import html
import requests
from huggingface_hub import HfApi
from telethon import TelegramClient
from telethon.sessions import StringSession
import vk_api

from llm import ask_llm
from db import init_db
from drafts import add_draft
from pager import process_pager_updates

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

SPACES = [
    "opion2008/cupidon",
    "opion2008/criminal-bot",
    "opion2008/rslaw-bot"
]

def send_telegram_report(message: str):
    """Гарантированная доставка отчета: сначала HTML, при сбое — чистый текст."""
    if not TG_BOT_TOKEN:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    
    # Попытка 1: Отправка с HTML
    payload = {
        "chat_id": ADMIN_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            print("✅ Отчёт успешно доставлен в Telegram (HTML).")
            return
    except Exception:
        pass
    
    # Попытка 2: Fallback на чистый текст без тегов
    try:
        clean_text = message.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
        payload["text"] = clean_text
        payload.pop("parse_mode", None)
        r2 = requests.post(url, json=payload, timeout=15)
        if r2.status_code == 200:
            print("✅ Отчёт доставлен в Telegram (Plain Text).")
        else:
            print(f"❌ Telegram API вернул ошибку: {r2.text}")
    except Exception as e:
        print(f"❌ Критическая ошибка отправки: {e}")

def run_keepalive_check() -> list[str]:
    hf_token = os.getenv("HF_TOKEN")
    hf_api = HfApi(token=hf_token) if hf_token else None
    results = []

    for space in SPACES:
        subdomain = space.replace("/", "-")
        ping_url = f"https://{subdomain}.hf.space/ping"
        try:
            res = requests.get(ping_url, timeout=10)
            if res.status_code == 200:
                results.append(f"• <b>{space}</b>: ✅ Работает (200 OK)")
            else:
                if hf_api: hf_api.restart_space(repo_id=space)
                results.append(f"• <b>{space}</b>: ⚠️ Код {res.status_code} ➔ Перезапущен")
        except Exception:
            try:
                if hf_api: hf_api.restart_space(repo_id=space)
                results.append(f"• <b>{space}</b>: 🚨 Спал ➔ Принудительно разбужен")
            except Exception as err:
                results.append(f"• <b>{space}</b>: ❌ Ошибка ({err})")
    return results

async def test_telegram_userbot() -> str:
    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")
    session_str = os.getenv("TG_STRING_SESSION")

    if not (api_id and api_hash and session_str):
        return "⚠️ Пропущен: не заданы ключи Telegram Userbot"

    try:
        client = TelegramClient(StringSession(session_str), int(api_id), api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return "❌ Ошибка авторизации Userbot"
        
        me = await client.get_me()
        user_info = f"@{me.username}" if me.username else me.first_name
        await client.disconnect()
        return f"✅ Подключен: {user_info} (ID: {me.id})"
    except Exception as e:
        return f"❌ Сбой TG Userbot: {e}"

def test_vk_userbot() -> str:
    vk_token = os.getenv("VK_TOKEN")
    if not vk_token:
        return "⚠️ Пропущен: не задан VK_TOKEN"

    try:
        vk_session = vk_api.VkApi(token=vk_token)
        vk = vk_session.get_api()
        user = vk.users.get()[0]
        return f"✅ Подключен: {user['first_name']} {user['last_name']} (id{user['id']})"
    except Exception as e:
        return f"❌ Сбой VK Userbot: {e}"

def test_ai_qa_reasoning() -> str:
    prompt = "Проверь работоспособность аналитического модуля Купидона (1-2 предложения)."
    answer, provider_info = ask_llm(prompt)
    clean_ans = html.escape(answer[:250])
    return f"<b>Модель:</b> <i>{provider_info}</i>\n{clean_ans}"

async def main():
    print("🚀 [ИИ-Агент] Инициализация баз и запуск...")
    init_db()
    
    # Читаем команды из пульта
    process_pager_updates()
    
    # Генерируем тестовый черновик для проверки пульта
    add_draft(
        draft_type="post",
        target="@cupidon_channel",
        payload="🔥 3 главных правила успешного первого свидания: 1. Будьте собой. 2. Слушайте партнера.|||💡 Секрет идеального диалога: задавайте открытые вопросы!"
    )
    
    servers_status = run_keepalive_check()
    tg_status = await test_telegram_userbot()
    vk_status = test_vk_userbot()
    ai_status = test_ai_qa_reasoning()

    report = (
        "🤖 <b>[ОТЧЕТ АВТОНОМНОГО ИИ-АГЕНТА КУПИДОН]</b>\n\n"
        "📡 <b>1. Антисон & Серверы:</b>\n" + "\n".join(servers_status) + "\n\n"
        f"📱 <b>2. Telegram Userbot:</b> {tg_status}\n"
        f"🌐 <b>3. ВКонтакте Userbot:</b> {vk_status}\n\n"
        f"🧠 <b>4. ИИ-Мозг (QA-Тест):</b>\n{ai_status}\n\n"
        "💡 <i>Отправьте в этот чат команду <b>/queue</b> для проверки очереди черновиков!</i>"
    )

    send_telegram_report(report)
    print("✅ [ИИ-Агент] Цикл завершён!")

if __name__ == "__main__":
    asyncio.run(main())
