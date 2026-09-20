import os
import re
import json
import logging
from llm import ask
from notifier import notify
import vkrate

log = logging.getLogger("moderator")

VK_ENABLED = os.getenv("VK_ENABLED", "false").lower() == "true"
VK_USER_TOKEN = os.getenv("VK_TOKEN", "").strip()
VK_GROUP_TOKEN = os.getenv("VK_GROUP_TOKEN", "").strip()
VK_GROUP_ID = 239533580  # ID сообщества qp_on
MOD_DRY_RUN = os.getenv("MOD_DRY_RUN", "false").lower() == "true"

RULES = """Ты — строгий ИИ-модератор сообщества 'Купидон'. Оцени текст комментария.
Возможные вердикты:
- ok (нормальный комментарий)
- spam (флуд, бессмыслица, ссылки)
- ad (реклама сторонних каналов)
- abuse (оскорбления, мат, травля)
- scam (мошенничество, заработок)
- nsfw (18+, интим)

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
    if not VK_ENABLED:
        return ["• <b>ВК qp_on:</b> ⏸️ На карантине (VK_ENABLED=false)"]
        
    if not VK_USER_TOKEN:
        return ["• <b>ВК qp_on:</b> Требуется VK_TOKEN пользователя для чтения стены"]

    try:
        sess_user = vkrate.get_vk_session(VK_USER_TOKEN)
        comments = vkrate.vk_call(sess_user, "wall.getComments", owner_id=-VK_GROUP_ID, count=10, sort="desc")
        items = comments.get("items", [])
        
        checked = 0
        deleted = 0
        
        del_token = VK_GROUP_TOKEN or VK_USER_TOKEN
        sess_del = vkrate.get_vk_session(del_token)
        
        for c in items:
            text = c.get("text", "").strip()
            cid = c.get("id")
            from_id = c.get("from_id")
            
            if not text or from_id < 0:
                continue
                
            checked += 1
            verdict_data = classify_text(text)
            verdict = verdict_data.get("verdict", "ok")
            
            if verdict != "ok":
                if not MOD_DRY_RUN:
                    try:
                        vkrate.vk_call(sess_del, "wall.deleteComment", owner_id=-VK_GROUP_ID, comment_id=cid)
                        deleted += 1
                        notify(f"🛡 [ВК Удалено] ({verdict}):\n«{text[:150]}»\nПричина: {verdict_data.get('reason')}")
                    except Exception as e:
                        log.error(f"Не удалось удалить: {e}")
                else:
                    deleted += 1
                    notify(f"🛡 [ВК DRY-RUN] Обнаружен спам ({verdict}): «{text[:100]}»")

        results.append(f"• <b>ВК qp_on:</b> Проверено {checked} коммент., удалено спама: {deleted}")
    except Exception as e:
        err = str(e)
        if "[9]" in err or "Flood control" in err:
            results.append("• <b>ВК qp_on:</b> Ожидание окна лимитов ([9] Flood control)")
        else:
            results.append(f"• <b>ВК qp_on:</b> {err[:60]}")

    return results
