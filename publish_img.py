import os
import io
import logging
import requests
import vk_api

log = logging.getLogger("publish_img")

def tg_post_photo(target: str, caption: str, photo_bytes: bytes) -> bool:
    token = os.getenv("ADMIN_BOT_TOKEN", os.getenv("TG_BOT_TOKEN", ""))
    if not token: return False
    
    # Лимит подписи к фото в Telegram — 1024 символа
    if len(caption) <= 1024:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data={"chat_id": target, "caption": caption, "parse_mode": "HTML"},
            files={"photo": ("post.jpg", io.BytesIO(photo_bytes), "image/jpeg")},
            timeout=30
        ).json()
        return bool(r.get("ok"))
    else:
        # Если текст длиннее 1024 символов — шлем фото + текст отдельным сообщением
        requests.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data={"chat_id": target},
            files={"photo": ("post.jpg", io.BytesIO(photo_bytes), "image/jpeg")},
            timeout=30
        )
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": target, "text": caption, "parse_mode": "HTML"},
            timeout=15
        ).json()
        return bool(r.get("ok"))

def vk_post_photo(owner_id: int, text: str, photo_bytes: bytes) -> bool:
    token = os.getenv("VK_GROUP_TOKEN", os.getenv("VK_TOKEN", ""))
    if not token: return False
    try:
        vk_session = vk_api.VkApi(token=token, api_version="5.131")
        vk = vk_session.get_api()
        gid = abs(int(owner_id))
        
        # 1. Получаем сервер загрузки обложки
        up = vk.photos.getWallUploadServer(group_id=gid)
        upl = requests.post(
            up["upload_url"],
            files={"photo": ("post.jpg", io.BytesIO(photo_bytes), "image/jpeg")},
            timeout=30
        ).json()
        
        # 2. Сохраняем фото
        saved = vk.photos.saveWallPhoto(
            group_id=gid, photo=upl["photo"], server=upl["server"], hash=upl["hash"]
        )[0]
        
        # 3. Публикуем пост с прикрепленным фото
        vk.wall.post(
            owner_id=owner_id,
            from_group=1,
            message=text[:15000],
            attachments=f"photo{saved['owner_id']}_{saved['id']}"
        )
        return True
    except Exception as e:
        log.error(f"Ошибка публикации фото в ВК: {e}")
        return False
