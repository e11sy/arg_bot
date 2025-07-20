from telegram import Update, Message
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from bots.base_bot import BaseBot
import os

class ArgManagerBot(BaseBot):
    def __init__(self, logger, redis_helper):
        super().__init__(logger, redis_helper)
        self.waiting_for_message = set()
        self.broadcast_password = os.getenv("MANAGER_PASSWORD")
        if not self.broadcast_password:
            raise RuntimeError("MANAGER_PASSWORD is not set in environment variables")

    def register_handlers(self, app: Application) -> None:
        app.add_handler(CommandHandler("start", self.handle_start))
        app.add_handler(CommandHandler("auth", self.handle_auth))
        app.add_handler(CommandHandler("send", self.handle_send))
        app.add_handler(MessageHandler(filters.ALL, self.handle_message))

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "Привет! Это менеджер бот.\n"
            "/auth <password> — авторизация\n"
            "/send — отправить сообщение всем пользователям"
        )

    async def handle_auth(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Использование: /auth <password>")
            return

        password = context.args[0]
        if password == self.broadcast_password:
            chat_id = update.effective_chat.id
            self.redis.authorize_chat(chat_id)
            await update.message.reply_text("Успешная авторизация.")
        else:
            await update.message.reply_text("Неверный пароль.")

    async def handle_send(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        if not self.redis.is_authorized(chat_id):
            await update.message.reply_text("Вы не авторизованы. Используйте /auth.")
            return

        self.waiting_for_message.add(chat_id)
        await update.message.reply_text("Жду ваше сообщение для рассылки (текст, фото, аудио и т.д.).")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        message: Message = update.message

        if chat_id not in self.waiting_for_message:
            return

        self.waiting_for_message.remove(chat_id)

        try:
            copied = await context.bot.copy_message(
                chat_id=chat_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id
            )
            self.redis.publish_raw_message(copied)
        except Exception as e:
            self.logger.error(f"Failed to copy and broadcast message: {e}")