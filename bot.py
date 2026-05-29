from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import InputMediaPhoto, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.ai_generator import AIGenerator
from app.renderer import CarouselRenderer
from app.schemas import GenerationRequest
from app.utils import save_caption_file

DEFAULT_NICHE = "thyroid health / endocrinology"
DEFAULT_LANGUAGE = "Russian"
DEFAULT_SLIDES_COUNT = 7
DEFAULT_TONE = "спокойный, экспертный, простой, без запугивания"

PROJECT_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "output"


def _parse_message(text: str) -> GenerationRequest:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    values: dict[str, str] = {}

    for line in lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip().lower()] = value.strip()

    topic = values.get("topic") or values.get("тема") or text.strip()
    niche = values.get("niche") or values.get("ниша") or DEFAULT_NICHE
    language = values.get("language") or values.get("язык") or DEFAULT_LANGUAGE
    tone = values.get("tone") or values.get("tone of voice") or values.get("тон") or DEFAULT_TONE

    raw_slides = values.get("slides") or values.get("slides count") or values.get("слайды") or ""
    slides_count = DEFAULT_SLIDES_COUNT
    if raw_slides.isdigit():
        slides_count = max(1, min(20, int(raw_slides)))

    return GenerationRequest(
        topic=topic,
        niche=niche,
        language=language,
        slides_count=slides_count,
        tone_of_voice=tone,
    )


def _generate_carousel(request: GenerationRequest) -> tuple[list[Path], Path, Path]:
    generator = AIGenerator()
    carousel = generator.generate(request)

    renderer = CarouselRenderer(templates_dir=TEMPLATES_DIR, output_dir=OUTPUT_DIR)
    image_paths = renderer.render_slides(carousel)
    caption_path = save_caption_file(carousel, renderer.last_output_dir)
    return image_paths, caption_path, renderer.last_output_dir


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "Привет. Отправьте тему одним сообщением, и я создам карусель.\n\n"
        "Можно просто так:\n"
        "Почему ТТГ в норме, а я всё равно чувствую усталость\n\n"
        "Или расширенно:\n"
        "Topic: Почему ТТГ в норме, а я всё равно чувствую усталость\n"
        "Niche: thyroid health / endocrinology\n"
        "Language: Russian\n"
        "Slides: 7\n"
        "Tone: спокойный, экспертный, простой"
    )
    await update.message.reply_text(message)


async def generate_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    request = _parse_message(update.message.text)
    await update.message.reply_text("Генерирую карусель. Это может занять 1-2 минуты...")

    try:
        image_paths, caption_path, run_dir = await asyncio.to_thread(_generate_carousel, request)
    except Exception as exc:
        await update.message.reply_text(f"Ошибка: {exc}")
        return

    media_group = []
    opened_files = []
    try:
        for index, image_path in enumerate(image_paths[:10]):
            file_handle = image_path.open("rb")
            opened_files.append(file_handle)
            if index == 0:
                media_group.append(InputMediaPhoto(file_handle, caption="Готово. Карусель сгенерирована."))
            else:
                media_group.append(InputMediaPhoto(file_handle))

        if media_group:
            await update.message.reply_media_group(media_group)

        caption_text = caption_path.read_text(encoding="utf-8")
        await update.message.reply_text(caption_text[:3900])
        await update.message.reply_text(f"Run folder: {run_dir}")
    finally:
        for file_handle in opened_files:
            file_handle.close()


def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing. Add it to your .env file.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generate_from_message))

    print("Telegram bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
