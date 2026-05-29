from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.ai_generator import AIGenerator
from app.instagram_publisher import publish_carousel
from app.renderer import CarouselRenderer
from app.schemas import GenerationRequest
from app.utils import save_caption_file

DEFAULT_NICHE = "thyroid health / endocrinology"
DEFAULT_LANGUAGE = "Russian"
DEFAULT_SLIDES_COUNT = 7
DEFAULT_TONE = "calm, expert, simple, no fearmongering"
DEFAULT_INTERVAL_SECONDS = 30 * 60

PROJECT_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_DIR = PROJECT_ROOT / "data" / "sessions"

RUNNERS: dict[int, asyncio.Task] = {}


def _session_path(chat_id: int) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"{chat_id}.json"


def _load_session(chat_id: int) -> dict[str, Any]:
    path = _session_path(chat_id)
    if not path.exists():
        return {
            "chat_id": chat_id,
            "status": "idle",
            "topics": [],
            "current_index": 0,
            "interval_seconds": DEFAULT_INTERVAL_SECONDS,
            "next_due": 0,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _save_session(session: dict[str, Any]) -> None:
    _session_path(int(session["chat_id"])).write_text(
        json.dumps(session, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _reset_session(chat_id: int) -> None:
    path = _session_path(chat_id)
    if path.exists():
        path.unlink()


def _parse_topics(text: str) -> list[str]:
    cleaned = text.strip()
    if cleaned.startswith("/queue"):
        cleaned = cleaned.replace("/queue", "", 1).strip()

    topics: list[str] = []
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]+\s*", "", line)
        line = re.sub(r"^\d+[\.)\-:]\s*", "", line)
        line = line.strip()
        if line:
            topics.append(line)

    if not topics and cleaned:
        topics = [cleaned]

    return topics


def _build_request(topic: str) -> GenerationRequest:
    return GenerationRequest(
        topic=topic,
        niche=DEFAULT_NICHE,
        language=DEFAULT_LANGUAGE,
        slides_count=DEFAULT_SLIDES_COUNT,
        tone_of_voice=DEFAULT_TONE,
    )


def _generate_carousel(topic: str) -> tuple[list[Path], Path, Path]:
    request = _build_request(topic)
    generator = AIGenerator()
    carousel = generator.generate(request)

    renderer = CarouselRenderer(templates_dir=TEMPLATES_DIR, output_dir=OUTPUT_DIR)
    image_paths = renderer.render_slides(carousel)
    caption_path = save_caption_file(carousel, renderer.last_output_dir)
    return image_paths, caption_path, renderer.last_output_dir


def _control_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Approve", callback_data="approve"),
                InlineKeyboardButton("Reject", callback_data="reject"),
                InlineKeyboardButton("Regenerate", callback_data="regenerate"),
            ],
            [
                InlineKeyboardButton("Pause", callback_data="pause"),
                InlineKeyboardButton("Resume", callback_data="resume"),
                InlineKeyboardButton("Reset", callback_data="reset"),
            ],
        ]
    )


def _approved_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Publish to Instagram", callback_data="publish")],
            [
                InlineKeyboardButton("Pause", callback_data="pause"),
                InlineKeyboardButton("Resume", callback_data="resume"),
                InlineKeyboardButton("Reset", callback_data="reset"),
            ],
        ]
    )


async def _send_generated_result(context: ContextTypes.DEFAULT_TYPE, chat_id: int, topic: str, index: int, total: int) -> tuple[str, int | None]:
    await context.bot.send_message(chat_id, f"Generating {index}/{total}: {topic}")
    image_paths, caption_path, run_dir = await asyncio.to_thread(_generate_carousel, topic)

    media_group = []
    opened_files = []
    try:
        for image_index, image_path in enumerate(image_paths[:10]):
            file_handle = image_path.open("rb")
            opened_files.append(file_handle)
            if image_index == 0:
                media_group.append(InputMediaPhoto(file_handle, caption=f"Generated {index}/{total}"))
            else:
                media_group.append(InputMediaPhoto(file_handle))

        if media_group:
            await context.bot.send_media_group(chat_id, media_group)

        caption_text = caption_path.read_text(encoding="utf-8")[:3300]
        control = await context.bot.send_message(
            chat_id,
            f"Topic {index}/{total}\n\n{caption_text}\n\nRun folder: {run_dir}\n\nChoose what to do next:",
            reply_markup=_control_keyboard(),
        )
        return str(run_dir), control.message_id
    finally:
        for file_handle in opened_files:
            file_handle.close()


async def _queue_runner(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    while True:
        session = _load_session(chat_id)
        status = session.get("status", "idle")

        if status in {"idle", "completed"}:
            RUNNERS.pop(chat_id, None)
            return

        if status in {"paused", "waiting_approval", "generating"}:
            await asyncio.sleep(5)
            continue

        topics = session.get("topics", [])
        current_index = int(session.get("current_index", 0))
        if current_index >= len(topics):
            session["status"] = "completed"
            _save_session(session)
            await context.bot.send_message(chat_id, "Queue completed.")
            RUNNERS.pop(chat_id, None)
            return

        next_due = float(session.get("next_due", 0))
        now = time.time()
        if next_due > now:
            await asyncio.sleep(min(10, next_due - now))
            continue

        topic_item = topics[current_index]
        topic = topic_item["topic"]
        topic_item["status"] = "generating"
        topic_item["attempt"] = int(topic_item.get("attempt", 0)) + 1
        session["status"] = "generating"
        _save_session(session)

        try:
            run_dir, control_message_id = await _send_generated_result(
                context,
                chat_id,
                topic,
                current_index + 1,
                len(topics),
            )
            session = _load_session(chat_id)
            session["status"] = "waiting_approval"
            session["current_run_folder"] = run_dir
            session["control_message_id"] = control_message_id
            session["topics"][current_index]["status"] = "waiting_approval"
            session["topics"][current_index]["run_dir"] = run_dir
            _save_session(session)
        except Exception as exc:
            session = _load_session(chat_id)
            session["status"] = "waiting_approval"
            session["topics"][current_index]["status"] = "failed"
            session["topics"][current_index]["error"] = str(exc)
            _save_session(session)
            await context.bot.send_message(
                chat_id,
                f"Generation failed for topic {current_index + 1}: {exc}\nUse Regenerate, Reject, Pause, or Reset.",
                reply_markup=_control_keyboard(),
            )


def _ensure_runner(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    task = RUNNERS.get(chat_id)
    if task and not task.done():
        return
    RUNNERS[chat_id] = asyncio.create_task(_queue_runner(context, chat_id))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "Send a list of topics and I will generate them one by one.\n\n"
        "Commands:\n"
        "/queue - send topics after this command or just send a numbered list\n"
        "/interval 30 - set interval in minutes\n"
        "/status - show queue status\n"
        "/pause - pause queue\n"
        "/resume - resume queue\n"
        "/reset - clear everything\n\n"
        "After each carousel I will show buttons: Approve, Reject, Regenerate, Pause, Resume, Reset.\n"
        "Approve only marks a post as approved. Use Publish to Instagram after approval."
    )
    await update.message.reply_text(message)


async def set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /interval 30")
        return

    minutes = max(1, min(1440, int(context.args[0])))
    session = _load_session(chat_id)
    session["interval_seconds"] = minutes * 60
    _save_session(session)
    await update.message.reply_text(f"Interval set to {minutes} minutes.")


async def queue_topics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text or ""
    topics = _parse_topics(text)
    if not topics:
        await update.message.reply_text("Send topics after /queue, one topic per line.")
        return

    session = _load_session(chat_id)
    session["topics"] = [
        {"id": index + 1, "topic": topic, "status": "pending", "attempt": 0}
        for index, topic in enumerate(topics)
    ]
    session["current_index"] = 0
    session["status"] = "queued"
    session["next_due"] = time.time()
    _save_session(session)
    _ensure_runner(context, chat_id)

    await update.message.reply_text(
        f"Queue saved: {len(topics)} topics. First generation will start now."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    session = _load_session(chat_id)
    topics = session.get("topics", [])
    current_index = int(session.get("current_index", 0))
    interval_minutes = int(session.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)) // 60

    if not topics:
        await update.message.reply_text("No active queue.")
        return

    current_topic = topics[current_index]["topic"] if current_index < len(topics) else "Done"
    await update.message.reply_text(
        f"Status: {session.get('status')}\n"
        f"Progress: {min(current_index + 1, len(topics))}/{len(topics)}\n"
        f"Interval: {interval_minutes} minutes\n"
        f"Current topic: {current_topic}"
    )


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    session = _load_session(chat_id)
    session["status"] = "paused"
    _save_session(session)
    await update.message.reply_text("Paused.")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    session = _load_session(chat_id)
    if not session.get("topics"):
        await update.message.reply_text("No queue to resume.")
        return
    session["status"] = "queued"
    session["next_due"] = time.time()
    _save_session(session)
    _ensure_runner(context, chat_id)
    await update.message.reply_text("Resumed.")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    _reset_session(chat_id)
    task = RUNNERS.pop(chat_id, None)
    if task:
        task.cancel()
    await update.message.reply_text("Queue reset.")


def _run_paths_from_session(session: dict[str, Any], topic_item: dict[str, Any]) -> tuple[list[Path], Path, Path]:
    run_dir = Path(topic_item.get("run_dir") or session.get("current_run_folder") or "")
    if not run_dir.exists():
        raise RuntimeError("Run folder not found. Regenerate this topic first.")
    image_paths = sorted(run_dir.glob("slide_*.png"), key=lambda path: int(path.stem.split("_")[-1]))
    caption_path = run_dir / "caption.txt"
    if not image_paths:
        raise RuntimeError("No slide images found in run folder.")
    if not caption_path.exists():
        raise RuntimeError("caption.txt not found in run folder.")
    return image_paths, caption_path, run_dir


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    action = query.data
    session = _load_session(chat_id)

    if action == "reset":
        _reset_session(chat_id)
        task = RUNNERS.pop(chat_id, None)
        if task:
            task.cancel()
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id, "Queue reset.")
        return

    if action == "pause":
        session["status"] = "paused"
        _save_session(session)
        await context.bot.send_message(chat_id, "Paused.")
        return

    if action == "resume":
        if session.get("topics"):
            session["status"] = "queued"
            session["next_due"] = time.time()
            _save_session(session)
            _ensure_runner(context, chat_id)
            await context.bot.send_message(chat_id, "Resumed.")
        return

    topics = session.get("topics", [])
    current_index = int(session.get("current_index", 0))
    if current_index >= len(topics):
        await context.bot.send_message(chat_id, "No active topic.")
        return

    if action == "publish":
        topic_item = topics[current_index]
        try:
            image_paths, caption_path, run_dir = _run_paths_from_session(session, topic_item)
            await context.bot.send_message(chat_id, "Publishing to Instagram...")
            result = await asyncio.to_thread(publish_carousel, image_paths, caption_path, run_dir)
            topic_item["instagram_status"] = "published"
            topic_item["instagram_media_id"] = result.get("instagram_media_id")
            topic_item["public_image_urls"] = result.get("image_urls", [])
            _save_session(session)
            await context.bot.send_message(
                chat_id,
                f"Published to Instagram. Media ID: {result.get('instagram_media_id')}",
            )
        except Exception as exc:
            await context.bot.send_message(chat_id, f"Instagram publish failed: {exc}")
        return

    if action == "approve":
        topics[current_index]["status"] = "approved"
        await query.edit_message_reply_markup(reply_markup=None)
        _save_session(session)
        await context.bot.send_message(
            chat_id,
            "Approved. Publish now or reject later. Next topic will start only after Reject or after you manually continue with /resume.",
            reply_markup=_approved_keyboard(),
        )
        return

    if action == "reject":
        topics[current_index]["status"] = "rejected"
        session["current_index"] = current_index + 1
        await query.edit_message_reply_markup(reply_markup=None)
        if session["current_index"] >= len(topics):
            session["status"] = "completed"
            _save_session(session)
            await context.bot.send_message(chat_id, "Rejected. Queue completed.")
        else:
            session["status"] = "queued"
            session["next_due"] = time.time() + int(session.get("interval_seconds", DEFAULT_INTERVAL_SECONDS))
            _save_session(session)
            _ensure_runner(context, chat_id)
            await context.bot.send_message(chat_id, "Rejected. Next topic will start after the interval.")
        return

    if action == "regenerate":
        topics[current_index]["status"] = "pending"
        session["status"] = "queued"
        session["next_due"] = time.time()
        _save_session(session)
        await query.edit_message_reply_markup(reply_markup=None)
        _ensure_runner(context, chat_id)
        await context.bot.send_message(chat_id, "Regenerating the same topic.")


def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing. Add it to your .env file.")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("interval", set_interval))
    app.add_handler(CommandHandler("queue", queue_topics))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, queue_topics))

    print("Queue Telegram bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
