import os
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InputFile, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from bots.base_bot import BaseBot

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_SHARP_PATH = os.path.join(BASE_DIR, "..", "assets", "1.otf")
FONT_ARG_PATH = os.path.join(BASE_DIR, "..", "assets", "2.ttf")

# Fail fast if fonts missing
for font_path in [FONT_SHARP_PATH, FONT_ARG_PATH]:
    if not os.path.exists(font_path):
        raise FileNotFoundError(f"Missing font file: {font_path}")

class ArgBot(BaseBot):
    def __init__(self, logger, redis_helper):
        super().__init__(logger, redis_helper)
        self._bg_task = None

    def register_handlers(self, app: Application):
        app.add_handler(CommandHandler("start", self.handle_start))
        app.add_handler(CommandHandler("arg", self.arg_command))
        app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"(?i)/arg"), self.photo_with_arg))

        app.post_init = self.on_startup

    async def on_startup(self, app: Application):
        self._bg_task = asyncio.create_task(self._broadcast_loop(app.bot))
        self.logger.info("Broadcast loop started.")

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        self.redis.add_chat_id(chat_id)
        await update.message.reply_text(
            "Пришли фото с подписью /arg или ответь командой /arg на сообщение с фото — и я наложу надпись '#arg'."
        )

    async def arg_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.reply_to_message:
            await self.process_arg(update, context, update.message.reply_to_message)
        else:
            await update.message.reply_text("Ответь командой /arg на сообщение с фотографией.")

    async def photo_with_arg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.caption and "/arg" in update.message.caption.lower():
            await self.process_arg(update, context, update.message)

    async def process_arg(self, update: Update, context: ContextTypes.DEFAULT_TYPE, message):
        if not message.photo:
            await update.message.reply_text("Сообщение должно содержать фотографию.")
            return

        photo = message.photo[-1]
        telegram_file = await context.bot.get_file(photo.file_id)

        output = BytesIO()
        await telegram_file.download_to_memory(out=output)
        output.seek(0)
        image = Image.open(output).convert("RGB")

        result = self.draw_arg_on_image(image)
        await update.message.reply_photo(photo=InputFile(result, filename="result.jpg"))
        self.logger.info("Отправлено изображение с текстом")

    def draw_arg_on_image(self, image: Image.Image) -> BytesIO:
        draw = ImageDraw.Draw(image)
        font_sharp, font_arg = self.fit_fonts(draw, image.width, image.height)

        text_sharp = "#"
        text_arg = "arg"
        spacing = 10

        width_sharp = draw.textlength(text_sharp, font=font_sharp)
        width_arg = draw.textlength(text_arg, font=font_arg)
        height = max(font_sharp.getbbox(text_sharp)[3], font_arg.getbbox(text_arg)[3])

        total_width = width_sharp + width_arg + spacing
        x = (image.width - total_width) // 2
        y = image.height - height - 20

        def draw_with_shadow(draw_fn, pos, font, text, fill="white"):
            for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
                draw_fn((pos[0] + dx, pos[1] + dy), text, font=font, fill="black")
            draw_fn(pos, text, font=font, fill=fill)

        draw_with_shadow(draw.text, (x, y), font_sharp, text_sharp)
        draw_with_shadow(draw.text, (x + width_sharp + spacing, y), font_arg, text_arg)

        result = BytesIO()
        result.name = "result.jpg"
        image.save(result, "JPEG")
        result.seek(0)
        return result

    def fit_fonts(self, draw, image_width, image_height):
        base_size = int(image_height * 0.05)
        for size in range(base_size, 10, -1):
            font_sharp = ImageFont.truetype(str(FONT_SHARP_PATH), size)
            font_arg = ImageFont.truetype(str(FONT_ARG_PATH), size)
            width_sharp = draw.textlength("#", font=font_sharp)
            width_arg = draw.textlength("arg", font=font_arg)
            total_width = width_sharp + width_arg + 10
            if total_width <= image_width * 0.95:
                return font_sharp, font_arg
        return ImageFont.truetype(str(FONT_SHARP_PATH), 12), ImageFont.truetype(str(FONT_ARG_PATH), 12)

    async def _broadcast_loop(self, bot: Bot):
        async for message in self.redis.subscribe_to_broadcasts():
            try:
                chat_ids = self.redis.get_all_chat_ids()
                content_type = message.get("content_type")

                if content_type == "raw_message":
                    origin_chat = message.get("chat_id")
                    message_id = message.get("message_id")
                    for chat_id in chat_ids:
                        try:
                            await bot.copy_message(chat_id=chat_id, from_chat_id=origin_chat, message_id=message_id)
                        except Exception as e:
                            self.logger.warning(f"Failed to copy message to {chat_id}: {e}")
                else:
                    raise RuntimeError("Unsupported content_type.")

            except Exception as e:
                self.logger.error(f"Broadcast loop error: {e}")
