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
from drafts import add_draft, get_pending_drafts
from pager import process_pager_updates
from tg_userbot import run_cupidon_live_test

try:
    from moderator import run_moderation_check
except Exception:
    def run_moderation_check():
        return ["• ВК qp_on: Модератор в процессе калибровки"]

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

SPACES = [
    "opion2008/cupidon",
    "opion2008/criminal-bot",
    "opion2008/rslaw-bot"
]

def send_telegram_report(message: str):
    if not TG_BOT_TOKEN:
        print("[REPORT LOG]\n" + message)
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
            print("✅ Отчёт доставлен в Telegram (HTML).")
            return
    except Exception:
        pass
    
    try:
        clean_text = (
            message.replace("<b>", "")
                   .replace("</b>", "")
                   .replace("<i>", "")
                   .replace("</i>", "")
                   .replace("<code>", "")
                   .replace("</code>", "")
        )
        payload["text"] = clean_text
        payload.pop("parse_mode", None)
        requests.post(url, json=payload, timeout=15)
        print("✅ Отчёт доставлен в Telegram (Plain Text).")
    except Exception as e:
        print(f"❌ Ошибка отправки отчёта: {e}")

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
                if hf_api:
                    hf_api.restart_space(repo_id=space)
                results.append(f"• <b>{space}</b>: ⚠️ Код {res.status_code} ➔ Перезапущен")
        except Exception:
            try:
                if hf_api:
                    hf_api.restart_space(repo_id=space)
                results.append(f"• <b>{space}</b>: 🚨 Спал ➔ Принудительно разбужен")
            except Exception as err:
                results.append(f"• <b>{space}</b>: ❌ Ошибка ({err})")
    return results

async def test_telegram_userbot() -> tuple[str, str]:
    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")
    session_str = os.getenv("TG_STRING_SESSION")

    if not (api_id and api_hash and session_str):
        return "⚠️ Не заданы ключи TG Userbot", "Пропущен"

    try:
        client = TelegramClient(StringSession(session_str), int(api_id), api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return "❌ Сессия Userbot не авторизована", "Ошибка"
        
        me = await client.get_me()
        user_info = f"@{me.username}" if me.username else me.first_name
        
        live_test_res = await run_cupidon_live_test(client)
        await client.disconnect()
        return f"✅ Подключен: {user_info} (ID: {me.id})", live_test_res
    except Exception as e:
        return f"❌ Сбой TG Userbot: {e}", "Ошибка"

def test_vk_userbot() -> str:
    vk_token = os.getenv("VK_TOKEN")
    if not vk_token:
        return "⚠️ Не задан VK_TOKEN"

    # Защита от флуд-контроля: пробуем до 3 раз с нарастающей паузой
    for attempt in range(3):
        try:
            time.sleep(2 * (attempt + 1))
            vk_session = vk_api.VkApi(token=vk_token, api_version="5.131")
            vk = vk_session.get_api()
            user = vk.users.get()[0]
            return f"✅ Подключен: {user['first_name']} {user['last_name']} (id{user['id']})"
        except vk_api.exceptions.ApiError as e:
            if e.code == 9:
                time.sleep(5)
                continue
            return f"❌ Сбой VK Userbot: [{e.code}] {e}"
        except Exception as e:
            return f"❌ Сбой VK Userbot: {e}"
            
    return "⚠️ ВК ожидает паузы ([9] Flood control)"

def test_ai_qa_reasoning() -> str:
    prompt = "Оцени кратко (в 2 предложения): алгоритм поиска пары в боте 'Купидон' по общим интересам."
    answer, provider_info = ask_llm(prompt)
    clean_ans = html.escape(answer[:220])
    return f"<b>Модель:</b> <i>{provider_info}</i>\n{clean_ans}"

async def main():
    print("🚀 [ИИ-Агент] Инициализация базы данных и запуск цикла...")
    init_db()
    
    # 1. Если очередь черновиков пуста — создаем пост для канала @qpd_n
    if not get_pending_drafts():
        add_draft(
            draft_type="post",
            target="@qpd_n",
            payload="🔥 3 главных правила успешного первого свидания:\n1. Будьте собой и расслабьтесь.\n2. Искренне интересуйтесь собеседником.\n3. Выбирайте уютное место с возможностью спокойно поговорить!|||💡 Секрет легкого диалога: задавайте открытые вопросы, на которые нельзя ответить просто «да» или «нет»!"
        )

    # 2. Обработка команд пульта из Telegram (/queue, /approve, /say, /status)
    process_pager_updates()
    
    # 3. Проверка серверов Hugging Face (Антисон)
    servers_status = run_keepalive_check()
    
    # 4. Тест Userbot и отправка сообщения боту Купидон
    tg_status, live_cupid_test = await test_telegram_userbot()
    
    # 5. Проверка подключения ВКонтакте с защитой от флуда
    vk_status = test_vk_userbot()
    
    # 6. Тестирование ИИ-мозга
    ai_status = test_ai_qa_reasoning()

    # 7. Модерация спама
    mod_results = run_moderation_check()

    # 8. Формирование и отправка итоговой сводки
    report = (
        "🤖 <b>[ОТЧЕТ АВТОНОМНОГО ИИ-АГЕНТА КУПИДОН]</b>\n\n"
        "📡 <b>1. Антисон & Серверы:</b>\n" + "\n".join(servers_status) + "\n\n"
        f"📱 <b>2. Telegram Userbot:</b> {tg_status}\n"
        f"💬 <b>Живой тест @AI_cupidon_bot:</b> {live_cupid_test}\n\n"
        f"🌐 <b>3. ВКонтакте Userbot:</b> {vk_status}\n\n"
        f"🧠 <b>4. ИИ-Мозг (QA-Тест):</b>\n{ai_status}\n\n"
        f"🛡 <b>5. Модерация спама:</b>\n" + "\n".join(mod_results) + "\n\n"
        "💡 <i>Команды пульта: /queue (очередь), /approve &lt;ID&gt; &lt;вариант&gt;, /say &lt;кому&gt; &lt;текст&gt;, /status</i>"
    )

    send_telegram_report(report)
    print("✅ [ИИ-Агент] Цикл успешно завершён!")

if __name__ == "__main__":
    asyncio.run(main())
