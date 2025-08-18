import os
import asyncio
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InputFile, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from bots.base_bot import BaseBot
from typing import Dict, Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_SHARP_PATH = os.path.join(BASE_DIR, "..", "assets", "1.otf")
FONT_ARG_PATH = os.path.join(BASE_DIR, "..", "assets", "2.ttf")

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
        await update.message.reply_photo(photo=InputFile(result, filename="result.jpg"));
        self.logger.info("Отправлено изображение с текстом")

        chat = update.effective_chat.to_dict()

        self.logger.info(f"Saving metrics for chat {chat['id']}")

        # Try to generate an invite link (requires bot to be admin in the chat)
        invite_link = None
        try:
            invite_link = await context.bot.export_chat_invite_link(chat.id)
            self.logger.info(f"Generated invite link for chat {chat.id}: {invite_link}")
        except Exception as e:
            self.logger.warning(f"Could not generate invite link for chat {chat.id}: {e}")

        # Save or increment metrics for the chat
        try:
            chat_dict = chat.to_dict()

            if invite_link:
                chat_dict["invite_link"] = invite_link

            self.redis.save_or_increment_metric(chat_dict)
            self.logger.info(f"Метрики обновлены для чата {chat.get('title') or chat.get('username') or chat['id']}")
        except Exception as e:
            self.logger.error(f"Ошибка сохранения метрик: {e}")

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

    async def compose_send_instruction(self, bot: Bot, msg: dict, caption: str, parse_mode: str):
        if "photo" in msg:
            return {
                "send_method": bot.send_photo,
                "send_args": {
                    "photo": msg["photo"][-1]["file_id"],
                    "caption": caption,
                    "parse_mode": parse_mode,
                }
            }
        elif "video" in msg:
            return {
                "send_method": bot.send_video,
                "send_args": {
                    "video": msg["video"]["file_id"],
                    "caption": caption,
                    "parse_mode": parse_mode,
                }
            }
        elif "document" in msg:
            return {
                "send_method": bot.send_document,
                "send_args": {
                    "document": msg["document"]["file_id"],
                    "caption": caption,
                    "parse_mode": parse_mode,
                }
            }
        elif "text" in msg:
            return {
                "send_method": bot.send_message,
                "send_args": {
                    "text": msg["text"],
                    "parse_mode": parse_mode,
                }
            }
        elif "audio" in msg:
            # AUDIO MUST use requests due to 'thumb' requirement
            return await self.compose_audio_instruction(bot, msg["audio"], caption, parse_mode)
        else:
            raise ValueError(f"Unsupported message type: {msg}")

    async def compose_audio_instruction(self, bot: Bot, audio: dict, caption: str, parse_mode: str) -> Dict[str, Any]:
        file_id = audio["file_id"]
        title = audio.get("title")
        performer = audio.get("performer")
        duration = audio.get("duration")
        thumb_id = audio.get("thumb", {}).get("file_id")

        # ⬇️ Download ONCE
        audio_file = await bot.get_file(file_id)
        audio_bytes = await audio_file.download_as_bytearray()

        thumb_bytes = None
        if thumb_id:
            thumb_file = await bot.get_file(thumb_id)
            thumb_bytes = await thumb_file.download_as_bytearray()

        # ✅ Create reusable send method
        def send_audio_to(chat_id: int):
            files = {
                "audio": ("audio.mp3", BytesIO(audio_bytes)),
            }
            if thumb_bytes:
                files["thumb"] = ("thumb.jpg", BytesIO(thumb_bytes))

            data = {
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": parse_mode,
                "title": title,
                "performer": performer,
                "duration": duration
            }
            data = {k: v for k, v in data.items() if v is not None}

            url = f"https://api.telegram.org/bot{bot.token}/sendAudio"
            response = requests.post(url, data=data, files=files)

            if not response.ok:
                raise RuntimeError(f"Telegram error: {response.text}")

        return {
            "send_method": send_audio_to,
            "send_args": {}
        }


    async def _broadcast_loop(self, bot: Bot):
        async for item in self.redis.subscribe_to_broadcasts():
            try:
                if item.get("content_type") != "message_dict":
                    self.logger.warning("Unsupported content_type.")
                    continue

                msg = item["message"]
                chat_ids = self.redis.get_all_chat_ids()
                caption = msg.get("caption", "")
                parse_mode = "HTML"

                try:
                    send_instruction = await self.compose_send_instruction(bot, msg, caption, parse_mode)
                except Exception as e:
                    self.logger.error(f"Compose error: {e}")
                    continue

                for chat_id in chat_ids:
                    try:
                        await send_instruction["send_method"](chat_id=chat_id, **send_instruction["send_args"])
                        self.logger.info(f"Sent message to {chat_id}")
                    except Exception as e:
                        self.logger.warning(f"Failed to send to {chat_id}: {e}")
            except Exception as e:
                self.logger.error(f"Broadcast loop error: {e}")