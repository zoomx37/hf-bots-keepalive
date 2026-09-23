import os
import re
import yaml
import requests
import vk_api

TG_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", os.getenv("TG_BOT_TOKEN", ""))
# Строго токен сообщества! Личный токен пользователя исключен во избежание публикаций в личные истории
VK_GROUP_TOKEN = os.getenv("VK_GROUP_TOKEN", "").strip()

def clean_for_vk(text: str) -> str:
    """Полностью удаляет HTML-теги для стены ВКонтакте."""
    if not text: return ""
    clean = re.sub(r'<[^>]+>', '', text)
    return clean.strip()

def load_channels():
    if not os.path.exists("channels.yaml"): return []
    try:
        with open("channels.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("channels", [])
    except Exception as e:
        print(f"Ошибка channels.yaml: {e}")
        return []

def post_to_telegram(channel_target: str, text: str) -> tuple[bool, str]:
    if not TG_BOT_TOKEN: return False, "TG_BOT_TOKEN не задан"
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": channel_target, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15).json()
        if r.get("ok"): return True, "Успешно"
        return False, r.get("description", "Ошибка Telegram")
    except Exception as e:
        return False, str(e)

def post_to_vk(owner_id, text: str) -> tuple[bool, str]:
    if not VK_GROUP_TOKEN: 
        return False, "VK_GROUP_TOKEN не задан (публикация отменена для защиты личной страницы)"
    try:
        target_id = -239533580
        vk_session = vk_api.VkApi(token=VK_GROUP_TOKEN, api_version="5.131")
        vk = vk_session.get_api()
        clean_text = clean_for_vk(text)
        res = vk.wall.post(owner_id=target_id, from_group=1, message=clean_text)
        return True, f"post_id: {res.get('post_id')}"
    except Exception as e:
        return False, str(e)

def publish_approved_post(target: str, text: str) -> str:
    channels = load_channels()
    results = []
    for ch in channels:
        plat = ch.get("platform")
        if plat == "tg":
            tg_target = ch.get("target")
            ok, msg = post_to_telegram(tg_target, text)
            results.append(f"{'✅' if ok else '❌'} TG ({tg_target}): {msg}")
        elif plat == "vk":
            vk_owner = ch.get("owner_id")
            ok, msg = post_to_vk(vk_owner, text)
            results.append(f"{'✅' if ok else '❌'} VK (qp_on): {msg}")
    return "\n".join(results) if results else "⚠️ Нет каналов в channels.yaml"
