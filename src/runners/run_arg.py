from telegram.ext import Application
from bots.arg_bot import ArgBot
from redis_helper.helper import RedisHelper
import logging, os, sys

TOKEN = os.getenv("ARG_BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")

if __name__ == "__main__":
    logging.basicConfig(
      level=logging.INFO,
      format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
      handlers=[logging.StreamHandler(sys.stdout)]
    )
    logger = logging.getLogger("arg-bot")
    redis = RedisHelper(REDIS_URL)
    bot = ArgBot(logger, redis)
    app = Application.builder().token(TOKEN).build()
    bot.register_handlers(app)
    app.run_polling()
