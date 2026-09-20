import os
import re
import json
import logging
import vk_api
from llm import ask
from notifier import notify

log = logging.getLogger("moderator")

VK_TOKEN = os.getenv("VK_GROUP_TOKEN", os.getenv("VK_TOKEN", ""))
VK_GROUP_ID = 239533580  # ID сообщества qp_on

RULES = """Ты — строгий ИИ-модератор сообщества 'Купидон'. Оцени текст комментария.
Возможные вердикты:
- ok (обычный комментарий)
- spam (флуд, бессмыслица, ссылки)
- ad (реклама сторонних каналов/услуг)
- abuse (оскорбления, угрозы)
- scam (мошенничество, заработок)
- nsfw (18+, интим-услуги)

Ответь СТРОГО в формате JSON без лишних слов:
{"verdict": "ok", "reason": "причина на русском"}"""

def classify_text(text: str) -> dict:
    try:
        raw = ask(text[:800], system=RULES, max_tokens=150)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        log.error(f"Ошибка классификации: {e}")
    return {"verdict": "ok", "reason": "check_failed"}

def run_moderation_check() -> list[str]:
    """Проверяет последние комментарии в группе ВК и удаляет спам."""
    results = []
    if not VK_TOKEN:
        return ["⚠️ Модерация ВК пропущена: нет токена"]

    try:
        vk_session = vk_api.VkApi(token=VK_TOKEN, api_version="5.131")
        vk = vk_session.get_api()

        # Получаем последние 10 комментариев на стене группы
        comments = vk.wall.getComments(owner_id=-VK_GROUP_ID, count=10, sort="desc")
        items = comments.get("items", [])
        
        checked = 0
        deleted = 0
        for c in items:
            text = c.get("text", "").strip()
            cid = c.get("id")
            from_id = c.get("from_id")
            
            # Пропускаем комментарии самого сообщества
            if not text or from_id < 0:
                continue
                
            checked += 1
            verdict_data = classify_text(text)
            verdict = verdict_data.get("verdict", "ok")
            
            if verdict != "ok":
                # Удаляем спам-комментарий
                try:
                    vk.wall.deleteComment(owner_id=-VK_GROUP_ID, comment_id=cid)
                    deleted += 1
                    notify(f"🛡 [ВК Модерация] Удален комментарий ({verdict}):\n«{text[:150]}»\nПричина: {verdict_data.get('reason')}")
                except Exception as del_err:
                    log.error(f"Не удалось удалить комментарий: {del_err}")

        results.append(f"• <b>ВК qp_on:</b> Проверено {checked} коммент., удалено спама: {deleted}")
    except Exception as e:
        results.append(f"• <b>ВК qp_on:</b> Ошибка проверки ({e})")

    return results
