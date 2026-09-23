import os
import requests
import sqlite3
import logging
import vk_api
from llm import ask
from notifier import notify
import vkrate

log = logging.getLogger("promo")

def get_channel_stats():
    """Сбор живой статистики подписчиков по TG и VK."""
    stats = []
    
    # 1. Telegram
    tg_token = os.getenv("ADMIN_BOT_TOKEN", os.getenv("TG_BOT_TOKEN", ""))
    if tg_token:
        try:
            r = requests.post(f"https://api.telegram.org/bot{tg_token}/getChatMemberCount", json={"chat_id": "@qpd_n"}, timeout=10).json()
            if r.get("ok"):
                stats.append(f"• <b>Telegram @qpd_n:</b> <code>{r.get('result')}</code> подписчиков")
        except Exception as e:
            stats.append(f"• <b>Telegram @qpd_n:</b> сбой запроса ({e})")

    # 2. ВКонтакте
    vk_token = os.getenv("VK_GROUP_TOKEN", os.getenv("VK_TOKEN", ""))
    if vk_token:
        try:
            sess = vkrate.get_vk_session(vk_token)
            res = vkrate.vk_call(sess, "groups.getById", group_id="239533580", fields="members_count")
            count = res[0].get("members_count", 0)
            stats.append(f"• <b>ВК vk.com/qp_on:</b> <code>{count}</code> участников")
        except Exception as e:
            stats.append(f"• <b>ВК qp_on:</b> сбой запроса ({e})")
            
    return stats

def run_marketing_audit():
    """Глубокий маркетинговый аудит каналов с практическими шагами взрывного роста."""
    stats = get_channel_stats()
    stats_text = "\n".join(stats) if stats else "Каналы: Telegram @qpd_n и VK vk.com/qp_on (стадия запуска, до 50 подписчиков)"

    prompt = (
        f"Текущие показатели каналов проекта знакомств 'ИИ-Купидон':\n{stats_text}\n\n"
        "Дай жесткий, практичный маркетинговый разбор:\n"
        "1. Топ-3 ошибки позиционирования на старте.\n"
        "2. 5 БЕСПЛАТНЫХ партизанских механик привлечения первых 1000 подписчиков (включая вирусные кружочки, TikTok/Reels/Клипы, комментинг в дейтинг-пабликах).\n"
        "3. 1 нестандартную хайповую акцию (вирусный инфоповод для СМИ и пабликов)."
    )
    audit = ask(prompt, system="Ты — топ-маркетолог вирусных дейтинг-стартапов и Telegram Mini Apps. Пиши строго по делу, без воды.", max_tokens=1200)
    
    msg = (
        "📊 <b>[МАРКЕТИНГОВЫЙ АУДИТ И СТРАТЕГИЯ РОСТА]</b>\n\n"
        f"📈 <b>Текущие показатели:</b>\n{stats_text}\n\n"
        f"🎯 <b>План действий от ИИ-Маркетолога:</b>\n\n{audit}"
    )
    notify(msg, html=True)

def generate_7day_content_plan():
    """Генерация контент-плана на 7 дней с чередованием хайпа, юмора и разборов."""
    prompt = (
        "Составь контент-план на 7 дней для Telegram-канала и группы ВК проекта знакомств 'ИИ-Купидон'.\n"
        "Чередуй рубрики: 1) Мемный разбор кринж-свиданий, 2) Анализ анкет подписчиков, 3) Горячий тренд из соцсетей, "
        "4) Интерактивный опрос-битва полов, 5) Точечный лайфхак флирта, 6) Жизненная история, 7) Анонс фичи бота.\n"
        "Стиль: 'НА ПРИКОЛЕ', молодежный сленг. Формат вывода:\n"
        "День 1: [Рубрика] — Краткая суть поста и провокационный вопрос\n..."
    )
    plan = ask(prompt, system="Ты креативный продюсер контента для миллениалов и зумеров.", max_tokens=900)
    msg = f"🗓 <b>[КОНТЕНТ-ПЛАН НА 7 ДНЕЙ 'НА ПРИКОЛЕ']</b>\n\n{plan}"
    notify(msg, html=True)
