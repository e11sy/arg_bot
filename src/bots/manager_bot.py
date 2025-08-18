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
        app.add_handler(CommandHandler("top", self.handle_top))
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

        message_dict = message.to_dict()
        self.redis.publish_raw_dict(message_dict)

    async def handle_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        if not self.redis.is_authorized(chat_id):
            await update.message.reply_text("Вы не авторизованы. Используйте /auth.")
            return

        metrics = self.redis.get_all_metrics()
        if not metrics:
            await update.message.reply_text("Нет данных для отображения.")
            return

        top_list = sorted(metrics, key=lambda x: x.get("count", 0), reverse=True)

        response_lines = []
        for i, item in enumerate(top_list[:10], start=1):
            title = item.get("title", "Unknown")
            username = item.get("username", "")
            count = item.get("count", 0)
            inviteLink = item.get("invite_link", "")
            response_line = ''

            if inviteLink and title:
                response_line = f'{i}. <a href="{inviteLink}">{title}</a> — {count}'
            elif title:
                response_line = f'{i}. {title} — {count}'
            elif username:
                response_line = f'{i}. @{username}(private chat) — {count}'
            
            response_lines.append(response_line)

        response_text = "🏆 Топ участников по активности:\n" + "\n".join(response_lines)
        await update.message.reply_text(response_text, parse_mode="HTML")
