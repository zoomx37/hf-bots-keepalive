import os
import asyncio
import requests
from huggingface_hub import HfApi
from telethon import TelegramClient
from telethon.sessions import StringSession
import vk_api

from llm import ask_llm

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

SPACES = [
    "opion2008/cupidon",
    "opion2008/criminal-bot",
    "opion2008/rslaw-bot"
]

def send_telegram_report(message: str):
    """Отправляет итоговый отчет владельцу через пейджер-бота."""
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
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"❌ Ошибка отправки отчета в TG: {e}")

def run_keepalive_check() -> list[str]:
    """1. Проверка доступности Hugging Face серверов и авто-будильник."""
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
                if hf_api:
                    hf_api.restart_space(repo_id=space)
                results.append(f"• <b>{space}</b>: ⚠️ Код {res.status_code} ➔ Перезапущен через API")
        except Exception:
            try:
                if hf_api:
                    hf_api.restart_space(repo_id=space)
                results.append(f"• <b>{space}</b>: 🚨 Спал/Недоступен ➔ Принудительно разбужен")
            except Exception as err:
                results.append(f"• <b>{space}</b>: ❌ Ошибка перезапуска ({err})")
    return results

async def test_telegram_userbot() -> str:
    """2. Тестирование Userbot-аккаунта агента в Telegram."""
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
            return "❌ Ошибка авторизации Userbot (сессия недействительна)"
        
        me = await client.get_me()
        user_info = f"@{me.username}" if me.username else me.first_name
        await client.disconnect()
        return f"✅ Подключен: {user_info} (ID: {me.id})"
    except Exception as e:
        return f"❌ Сбой Telegram Userbot: {e}"

def test_vk_userbot() -> str:
    """3. Тестирование Userbot-аккаунта агента во ВКонтакте."""
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
    """4. Тестирование логики ИИ-моделей агента."""
    prompt = (
        "Сделай краткий экспертный QA-аудит (2-3 строки): "
        "Проверь логику расчета совместимости пары по Human Design и соционике для дейтинг-бота 'Купидон'."
    )
    answer, provider_info = ask_llm(prompt)
    return f"<b>Модель:</b> <i>{provider_info}</i>\n{answer[:350]}..."

async def main():
    print("🚀 [ИИ-Агент] Запуск комплексного цикла тестирования и мониторинга...")
    
    # 1. Проверка серверов
    servers_status = run_keepalive_check()
    
    # 2. Проверка Userbot TG
    tg_status = await test_telegram_userbot()
    
    # 3. Проверка Userbot VK
    vk_status = test_vk_userbot()
    
    # 4. Проверка ИИ-моделей
    ai_status = test_ai_qa_reasoning()

    # Сборка финального отчета
    report = (
        "🤖 <b>[ОТЧЕТ АВТОНОМНОГО ИИ-АГЕНТА КУПИДОН]</b>\n\n"
        "📡 <b>1. Антисон & Серверы:</b>\n" + "\n".join(servers_status) + "\n\n"
        f"📱 <b>2. Telegram Userbot:</b> {tg_status}\n"
        f"🌐 <b>3. ВКонтакте Userbot:</b> {vk_status}\n\n"
        f"🧠 <b>4. ИИ-Мозг (QA-Тест):</b>\n{ai_status}"
    )

    send_telegram_report(report)
    print("✅ [ИИ-Агент] Цикл успешно завершен, отчет отправлен в Telegram!")

if __name__ == "__main__":
    asyncio.run(main())
