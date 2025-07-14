from telegram.ext import Application
from bots.manager_bot import ArgManagerBot
from redis_helper.helper import RedisHelper
import logging, os

TOKEN = os.getenv("TELEGRAM_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")

if __name__ == "__main__":
    logger = logging.getLogger("manager-bot")
    redis = RedisHelper(REDIS_URL)
    bot = ArgManagerBot(logger, redis)
    app = Application.builder().token(TOKEN).build()
    bot.register_handlers(app)
    app.run_polling()
