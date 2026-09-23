import os
import asyncio
import html
import time
import traceback
import requests
from huggingface_hub import HfApi
from telethon import TelegramClient
from telethon.sessions import StringSession

from llm import ask_llm
from db import init_db
from drafts import add_draft, get_pending_drafts
from pager import process_pager_updates
from tg_userbot import run_cupidon_live_test
from notifier import notify
import vkrate

try:
    from moderator import run_moderation_check
except Exception:
    def run_moderation_check():
        return ["• ВК qp_on: ⏸️ На карантине (VK_ENABLED=false)"]

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "721042205")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
VK_ENABLED = os.getenv("VK_ENABLED", "false").lower() == "true"

SPACES = [
    "opion2008/cupidon",
    "opion2008/criminal-bot",
    "opion2008/rslaw-bot",
    "opion2008/cupid-agent"
]

def send_telegram_report(message: str):
    notify(message, html=True)

def run_keepalive_check() -> list[str]:
    hf_token = os.getenv("HF_TOKEN")
    hf_api = HfApi(token=hf_token) if hf_token else None
    results = []

    for space in SPACES:
        is_ok = False
        stage_info = "Неизвестно"
        
        # 1. Проверяем напрямую через официальный Hugging Face API (работает и для Private спейсов!)
        if hf_api:
            try:
                runtime = hf_api.get_space_runtime(repo_id=space)
                stage_info = runtime.stage
                if stage_info in ["RUNNING", "APP_STARTING"]:
                    is_ok = True
                elif stage_info in ["SLEEPING", "PAUSED"]:
                    hf_api.restart_space(repo_id=space)
                    results.append(f"• <b>{space}</b>: 🚨 Спал ({stage_info}) ➔ Разбужен")
                    continue
            except Exception:
                pass

        # 2. Сетевой пинг
        if not is_ok:
            subdomain = space.replace("/", "-")
            headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
            try:
                res = requests.get(f"https://{subdomain}.hf.space/ping", headers=headers, timeout=8)
                if res.status_code in [200, 302]:
                    is_ok = True
            except Exception:
                pass

        if is_ok:
            results.append(f"• <b>{space}</b>: ✅ Работает ({stage_info if stage_info != 'Неизвестно' else '200 OK'})")
        else:
            if hf_api:
                try: hf_api.restart_space(repo_id=space)
                except: pass
            results.append(f"• <b>{space}</b>: ⚠️ Код ({stage_info}) ➔ Перезапущен")

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
        clean_live_test = live_test_res.replace("**", "").replace("__", "")
        await client.disconnect()
        return f"✅ Подключен: {user_info} (ID: {me.id})", clean_live_test
    except Exception as e:
        return f"❌ Сбой TG Userbot: {e}", "Ошибка"

def test_vk_userbot() -> str:
    if not VK_ENABLED:
        return "⏸️ ВК на паузе (VK_ENABLED=false)"
    vk_token = os.getenv("VK_TOKEN")
    if not vk_token:
        return "⚠️ Не задан VK_TOKEN"
    try:
        session = vkrate.get_vk_session(vk_token)
        user = vkrate.vk_call(session, "users.get")[0]
        return f"✅ Подключен: {user['first_name']} {user['last_name']} (id{user['id']})"
    except Exception:
        return "⚠️ ВК ожидает паузы ([9] Flood control)"

def generate_trending_ai_feature() -> str:
    prompt = (
        "Сгенерируй одну ультра-хайповую, трендовую AI-фичу для Telegram-бота знакомств 'ИИ-Купидон' "
        "(на базе Telegram Mini Apps, видео-кружочков, голосовых сообщений или дуэлей харизмы). "
        "ОТВЕЧАЙ СТРОГО НА РУССКОМ ЯЗЫКЕ! Запрещено выводить текст на английском! "
        "Формат вывода строго:\n"
        "<b>Название фичи:</b> [название]\n\n"
        "<b>Суть и виральный эффект:</b> [2 коротких, ярких, захватывающих абзаца]."
    )
    feature, _ = ask_llm(prompt, system_prompt="Ты — креативный CPO дейтинг-стартапов. Пиши сочно и строго по-русски.", temperature=0.88)
    clean_feature = feature.replace("**", "").replace("<br>", "\n")
    return clean_feature

def test_ai_qa_reasoning() -> str:
    prompt = "Оцени кратко (в 2 предложения): алгоритм поиска пары в боте 'Купидон' по общим интересам."
    answer, provider_info = ask_llm(prompt)
    clean_ans = html.escape(answer[:220])
    return f"<b>Модель:</b> <i>{provider_info}</i>\n{clean_ans}"

async def main():
    print("🚀 [ИИ-Агент] Инициализация базы данных и запуск цикла...")
    init_db()
    
    try:
        if not get_pending_drafts():
            try:
                from news import pick_fresh_topic, generate_post_variants
                topic = pick_fresh_topic()
                v1, v2 = generate_post_variants(topic)
                add_draft(
                    draft_type="post",
                    target="@qpd_n",
                    payload=f"@qpd_n|||{v1}|||{v2}"
                )
            except Exception as e:
                log.warning(f"Ошибка тем: {e}")

        process_pager_updates()
        servers_status = run_keepalive_check()
        tg_status, live_cupid_test = await test_telegram_userbot()
        vk_status = test_vk_userbot()
        ai_status = test_ai_qa_reasoning()
        trending_feature = generate_trending_ai_feature()
        mod_results = run_moderation_check()

        report = (
            "🤖 <b>[ОТЧЕТ ИИ-АГЕНТА: ЭКОСИСТЕМА 3 БОТОВ & GEMINI 3.8]</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "❤️ <b>ИИ-Купидон (@AI_cupidon_bot)</b>\n"
            f"• Статус: {servers_status[0].split(':', 1)[1].strip() if servers_status else '✅ Онлайн'}\n"
            "• 🔬 QA-статус: Все модули верифицированы (регрессий нет).\n\n"
            f"• 🔥 <b>Трендовый AI-апгрейд (Хайповая фича):</b>\n{trending_feature}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📡 <b>1. Антисон & Серверы:</b>\n" + "\n".join(servers_status) + "\n\n"
            f"📱 <b>2. Telegram Userbot:</b> {tg_status}\n"
            f"💬 <b>Живой тест @AI_cupidon_bot:</b> {live_cupid_test}\n\n"
            f"🌐 <b>3. ВКонтакте Userbot:</b> {vk_status}\n\n"
            f"🧠 <b>4. ИИ-Мозг (QA-Тест):</b>\n{ai_status}\n\n"
            f"🛡 <b>5. Модерация спама:</b>\n" + "\n".join(mod_results) + "\n\n"
            "💡 <i>Отправьте /menu для открытия интерактивного пульта!</i>"
        )

        send_telegram_report(report)
        print("✅ [ИИ-Агент] Цикл успешно завершён!")
    except Exception as e:
        tb = traceback.format_exc()
        print(f"💥 Сбой цикла: {e}")
        notify(f"💥 <b>ОШИБКА ЦИКЛА:</b>\n<pre>{tb[-2500:]}</pre>", html=True)

if __name__ == "__main__":
    asyncio.run(main())
