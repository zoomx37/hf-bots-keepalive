import os
import time
import threading
import logging
from flask import Flask

from db import init_db
from drafts import add_draft, get_pending_drafts
from pager import process_pager_updates
from moderator import start as start_moderation, ban_user, unban_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("main")

app = Flask(__name__)

@app.route("/")
@app.route("/ping")
@app.route("/health")
def health():
    return "Купидон-Агент 24/7 активен!", 200

def pager_background_loop():
    """Фоновый опрос команд пульта (/queue, /approve, /say, /status) каждые 2 секунды."""
    log.info("📡 Пульт управления запущен в режиме реального времени.")
    while True:
        try:
            process_pager_updates()
            time.sleep(2)
        except Exception as e:
            log.error(f"Ошибка в цикле пульта: {e}")
            time.sleep(5)

def scheduler_daily_digest():
    """Ежедневное создание черновика утреннего поста для канала."""
    while True:
        try:
            # Если очередь пуста — генерируем свежий пост
            if not get_pending_drafts():
                add_draft(
                    draft_type="post",
                    target="@qpd_n",
                    payload="🔥 Главный закон притяжения: люди тянутся к тем, кто уверен в себе и умеет слушать. Улыбка и открытый взгляд делают 80% успеха!|||💡 Вопрос дня: что для вас важнее на первом свидании — идеальное совпадение интересов или химия в общении?"
                )
                log.info("📝 Сгенерирован новый черновик утреннего поста.")
            time.sleep(3600 * 4) # Проверка каждые 4 часа
        except Exception as e:
            log.error(f"Ошибка планировщика: {e}")
            time.sleep(60)

if __name__ == "__main__":
    init_db()
    
    # 1. Запуск мгновенного пульта управления
    threading.Thread(target=pager_background_loop, daemon=True).start()
    
    # 2. Запуск автомодерации ТГ-чата и комментариев ВК из moderator.py
    try:
        start_moderation()
        log.info("🛡️ Автомодерация ТГ и ВК успешно запущена.")
    except Exception as e:
        log.error(f"Ошибка запуска автомодерации: {e}")

    # 3. Запуск генератора постов
    threading.Thread(target=scheduler_daily_digest, daemon=True).start()

    # 4. Веб-сервер Flask (порт 7860 для Hugging Face / 10000 для Render)
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port)
