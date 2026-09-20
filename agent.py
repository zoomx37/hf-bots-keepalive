import os
import asyncio
import html
import time
import requests
from huggingface_hub import HfApi
from telethon import TelegramClient
from telethon.sessions import StringSession
import vk_api

from llm import ask_llm
from db import init_db
from drafts import add_draft
from pager import process_pager_updates
from tg_userbot import run_cupidon_live_test

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

SPACES = [
    "opion2008/cupidon",
    "opion2008/criminal-bot",
    "opion2008/rslaw-bot"
]

def send_telegram_report(message: str):
    if not TG_BOT_TOKEN:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": ADMIN_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            return
    except Exception:
        pass
    
    # Fallback
    try:
        clean_text = message.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "").replace("<code>", "").replace("</code>", "")
        payload["text"] = clean_text
        payload.pop("parse_mode", None)
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

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
                results.append(f"• <b>{space}</b>: ⚠️ Перезапущен ({res.status_code})")
        except Exception:
            try:
                if hf_api: hf_api.restart_space(repo_id=space)
                results.append(f"• <b>{space}</b>: 🚨 Разбужен")
            except Exception as err:
                results.append(f"• <b>{space}</b>: ❌ Ошибка ({err})")
    return results

async def test_telegram_userbot() -> tuple[str, str]:
    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")
    session_str = os.getenv("TG_STRING_SESSION")

    if not (api_id and api_hash and session_str):
        return "⚠️ Не заданы ключи TG", "Пропущен"

    try:
        client = TelegramClient(StringSession(session_str), int(api_id), api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return "❌ Сессия не авторизована", "Ошибка"
        
        me = await client.get_me()
        user_info = f"@{me.username}" if me.username else me.first_name
        
        # Живой тест диалога с ботом Купидон
        live_test_res = await run_cupidon_live_test(client)
        
        await client.disconnect()
        return f"✅ Подключен: {user_info} (ID: {me.id})", live_test_res
    except Exception as e:
        return f"❌ Сбой TG Userbot: {e}", "Ошибка"

def test_vk_userbot() -> str:
    vk_token = os.getenv("VK_TOKEN")
    if not vk_token:
        return "⚠️ Не задан VK_TOKEN"

    try:
        time.sleep(1)
        vk_session = vk_api.VkApi(token=vk_token, api_version="5.131")
        vk = vk_session.get_api()
        user = vk.users.get()[0]
        return f"✅ Подключен: {user['first_name']} {user['last_name']} (id{user['id']})"
    except Exception as e:
        return f"⚠️ ВК ожидает паузы ({e})"

def test_ai_qa_reasoning() -> str:
    prompt = "Оцени кратко (в 2 предложения): алгоритм поиска пары в боте 'Купидон' по общим интересам."
    answer, provider_info = ask_llm(prompt)
    clean_ans = html.escape(answer[:220])
    return f"<b>Модель:</b> <i>{provider_info}</i>\n{clean_ans}"

async def main():
    print("🚀 [ИИ-Агент] Обработка пульта и запуск проверок...")
    init_db()
    
    # 1. Чтение ваших команд из Telegram (/queue, /approve, /say, /status)
    process_pager_updates()
    
    # 2. Проверка серверов
    servers_status = run_keepalive_check()
    
    # 3. Тест Userbot и отправка сообщения боту Купидон
    tg_status, live_cupid_test = await test_telegram_userbot()
    
    # 4. Проверка ВК
    vk_status = test_vk_userbot()
    
    # 5. Тест ИИ-мозга
    ai_status = test_ai_qa_reasoning()

    report = (
        "🤖 <b>[ОТЧЕТ АВТОНОМНОГО ИИ-АГЕНТА КУПИДОН]</b>\n\n"
        "📡 <b>1. Антисон & Серверы:</b>\n" + "\n".join(servers_status) + "\n\n"
        f"📱 <b>2. Telegram Userbot:</b> {tg_status}\n"
        f"💬 <b>Живой тест @AI_cupidon_bot:</b> {live_cupid_test}\n\n"
        f"🌐 <b>3. ВКонтакте Userbot:</b> {vk_status}\n\n"
        f"🧠 <b>4. ИИ-Мозг (QA-Тест):</b>\n{ai_status}\n\n"
        "💡 <i>Команды пульта: /queue (очередь), /say &lt;кому&gt; &lt;текст&gt;, /status</i>"
    )

    send_telegram_report(report)
    print("✅ [ИИ-Агент] Цикл успешно завершён!")

if __name__ == "__main__":
    asyncio.run(main())
