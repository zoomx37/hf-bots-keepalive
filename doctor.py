import os
import requests
from notifier import notify
from llm import ask_llm
from drafts import get_pending_drafts
import vkrate

SPACES = [
    "opion2008/cupidon",
    "opion2008/criminal-bot",
    "opion2008/rslaw-bot"
]

def run_doctor(args=""):
    rows = ["🩺 <b>[САМОДИАГНОСТИКА СИСТЕМЫ AGENT-DOCTOR]</b>\n"]
    
    # 1. Проверка LLM
    try:
        reply, provider = ask_llm("Ответь строго одним словом: ОК", system_prompt="Отвечай только словом ОК")
        rows.append(f"✅ <b>ИИ-Мозг:</b> {provider} (ответ: <i>{reply[:40]}</i>)")
    except Exception as e:
        rows.append(f"❌ <b>ИИ-Мозг:</b> Сбой ({str(e)[:80]})")

    # 2. Проверка Telegram Userbot
    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")
    session_str = os.getenv("TG_STRING_SESSION")
    if api_id and api_hash and session_str:
        rows.append("✅ <b>TG Userbot:</b> Ключи и сессия заданы")
    else:
        rows.append("❌ <b>TG Userbot:</b> Не все ключи TG_API заданы")

    # 3. Проверка VK Userbot
    vk_token = os.getenv("VK_TOKEN")
    if vk_token:
        try:
            sess = vkrate.get_vk_session(vk_token)
            me = vkrate.vk_call(sess, "users.get")[0]
            rows.append(f"✅ <b>VK Userbot:</b> Аккаунт {me['first_name']} {me['last_name']} (id{me['id']}) активен")
        except Exception as e:
            rows.append(f"⚠️ <b>VK Userbot:</b> {str(e)[:80]}")
    else:
        rows.append("❌ <b>VK Userbot:</b> VK_TOKEN не найден в Secrets")

    # 4. Проверка VK Group Token
    vk_group_token = os.getenv("VK_GROUP_TOKEN")
    if vk_group_token:
        try:
            sess_grp = vkrate.get_vk_session(vk_group_token)
            grp = vkrate.vk_call(sess_grp, "groups.getById", group_id="239533580")[0]
            rows.append(f"✅ <b>VK Сообщество:</b> «{grp.get('name')}» доступно для постов")
        except Exception as e:
            rows.append(f"⚠️ <b>VK Сообщество:</b> Ошибка ({str(e)[:80]})")
    else:
        rows.append("⚠️ <b>VK Сообщество:</b> VK_GROUP_TOKEN не задан")

    # 5. Проверка серверов Hugging Face
    active_spaces = 0
    for space in SPACES:
        subdomain = space.replace("/", "-")
        try:
            res = requests.get(f"https://{subdomain}.hf.space/ping", timeout=6)
            if res.status_code == 200:
                active_spaces += 1
        except Exception:
            pass
    rows.append(f"✅ <b>Серверы HF (Антисон):</b> {active_spaces}/{len(SPACES)} онлайн")

    # 6. Очередь черновиков
    drafts_count = len(get_pending_drafts())
    rows.append(f"📋 <b>Очередь черновиков:</b> {drafts_count} ожидают решения")

    notify("\n".join(rows))
