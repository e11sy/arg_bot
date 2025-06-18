import logging
from io import BytesIO
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FONT_SHARP_PATH = "../assets/1.otf"
FONT_ARG_PATH = "../assets/2.ttf"

def fit_fonts(draw, image_width, image_height):
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

def draw_arg_on_image(image: Image.Image) -> BytesIO:
    draw = ImageDraw.Draw(image)
    font_sharp, font_arg = fit_fonts(draw, image.width, image.height)

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

async def process_arg(update: Update, context: ContextTypes.DEFAULT_TYPE, message):
    if not message.photo:
        await update.message.reply_text("Сообщение должно содержать фотографию.")
        return

    photo = message.photo[-1]
    telegram_file = await context.bot.get_file(photo.file_id)

    output = BytesIO()
    await telegram_file.download_to_memory(out=output)
    output.seek(0)
    image = Image.open(output).convert("RGB")

    result = draw_arg_on_image(image)
    await update.message.reply_photo(photo=InputFile(result, filename="result.jpg"))
    logger.info("Отправлено изображение с текстом")

async def arg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        await process_arg(update, context, update.message.reply_to_message)
    else:
        await update.message.reply_text("Ответь командой /arg на сообщение с фотографией.")

async def photo_with_arg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.caption and "/arg" in update.message.caption.lower():
        await process_arg(update, context, update.message)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришли фото с подписью /arg или ответь командой /arg на сообщение с фото — и я наложу надпись '#arg'."
    )

def main():
    TOKEN = "7254434247:AAGGxv8VmNxO5WCILgzqKpgzZp8EnaFfnq4"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("arg", arg_command))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"(?i)/arg"), photo_with_arg))

    app.run_polling()

if __name__ == "__main__":
    main()
