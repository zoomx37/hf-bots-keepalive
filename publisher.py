import os
import yaml
import requests
import vk_api

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
VK_GROUP_TOKEN = os.getenv("VK_GROUP_TOKEN", os.getenv("VK_TOKEN", ""))

def load_channels():
    if not os.path.exists("channels.yaml"):
        return []
    with open("channels.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data.get("channels", [])

def post_to_telegram(channel_target: str, text: str) -> bool:
    """Публикует пост в Telegram-канал."""
    if not TG_BOT_TOKEN:
        print("❌ TG_BOT_TOKEN не задан")
        return False
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": channel_target,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        return r.status_code == 200
    except Exception as e:
        print(f"Ошибка публикации в TG ({channel_target}): {e}")
        return False

def post_to_vk(owner_id: int, text: str) -> bool:
    """Публикует пост на стене группы ВКонтакте от имени сообщества."""
    if not VK_GROUP_TOKEN:
        print("❌ VK_GROUP_TOKEN не задан")
        return False
    try:
        vk_session = vk_api.VkApi(token=VK_GROUP_TOKEN)
        vk = vk_session.get_api()
        vk.wall.post(owner_id=owner_id, from_group=1, message=text)
        return True
    except Exception as e:
        print(f"Ошибка публикации в ВК ({owner_id}): {e}")
        return False

def publish_approved_post(target: str, text: str) -> str:
    """Определяет платформу и публикует пост."""
    channels = load_channels()
    results = []
    
    for ch in channels:
        plat = ch.get("platform")
        if plat == "tg":
            tg_target = ch.get("target")
            if post_to_telegram(tg_target, text):
                results.append(f"✅ TG: Опубликовано в {tg_target}")
            else:
                results.append(f"❌ TG: Сбой публикации в {tg_target}")
                
        elif plat == "vk":
            vk_owner = ch.get("owner_id")
            if post_to_vk(vk_owner, text):
                results.append(f"✅ VK: Опубликовано на стене группы {vk_owner}")
            else:
                results.append(f"❌ VK: Сбой публикации в ВК {vk_owner}")
                
    return "\n".join(results) if results else "⚠️ Нет настроенных каналов в channels.yaml"
