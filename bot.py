"""Telegram bot that collects photos and converts them into a single PDF."""

import asyncio
import io
import logging
import os
import shutil
import tempfile
import time

import img2pdf
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN", "")
ALBUM_FLUSH_SECONDS = 2.5

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Per-user ordered temp image paths
batches: dict[int, list[str]] = {}
# user_id -> set of file_unique_ids already added (dedupe)
added_ids: dict[int, set[str]] = {}
# media_group_id -> pending photo messages
album_buffer: dict[str, list[Update]] = {}
# media_group_id -> flush task
album_tasks: dict[str, asyncio.Task] = {}


def get_batch(user_id: int) -> list[str]:
    return batches.setdefault(user_id, [])


def get_added_ids(user_id: int) -> set[str]:
    return added_ids.setdefault(user_id, set())


async def download_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Download the largest size of a photo message to a temp file, return its path."""
    message = update.effective_message
    photo = message.photo[-1]  # largest size
    file = await photo.get_file()
    user_id = update.effective_user.id
    session_dir = os.path.join(tempfile.gettempdir(), f"imagetopdf_{user_id}")
    os.makedirs(session_dir, exist_ok=True)
    path = os.path.join(session_dir, f"{time.time()}_{photo.file_unique_id}.jpg")
    await file.download_to_drive(path)
    return path


def cleanup_user(user_id: int) -> None:
    """Delete a user's temp images and reset their state."""
    for path in batches.pop(user_id, []):
        try:
            os.remove(path)
        except OSError:
            logger.warning("Could not delete temp file %s", path)
    added_ids.pop(user_id, None)
    session_dir = os.path.join(tempfile.gettempdir(), f"imagetopdf_{user_id}")
    if os.path.isdir(session_dir):
        shutil.rmtree(session_dir, ignore_errors=True)


def build_convert_buttons() -> InlineKeyboardMarkup:
    """Inline Convert/Cancel buttons shown when a batch is ready."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Convert ✅", callback_data="convert"),
                InlineKeyboardButton("Cancel ❌", callback_data="cancel_batch"),
            ]
        ]
    )


async def do_convert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Convert the user's batch to a PDF and send it."""
    user_id = update.effective_user.id
    images = get_batch(user_id)
    if not images:
        await update.effective_message.reply_text(
            "No photos in your batch yet. Send me some photos, then /pdf."
        )
        return

    await update.effective_message.reply_text(
        f"Converting {len(images)} photo(s) to PDF..."
    )
    try:
        layout = img2pdf.get_layout_fun(
            pagesize=(A4[0], A4[1]),
            fit=img2pdf.FitMode.into,
        )
        pdf_bytes = img2pdf.convert(images, layout_fun=layout)
    except Exception as exc:
        logger.exception("PDF conversion failed for user %s", user_id)
        await update.effective_message.reply_text(
            f"Sorry, conversion failed: {exc}"
        )
        return
    finally:
        cleanup_user(user_id)

    filename = f"photos_{int(time.time())}.pdf"
    await update.effective_message.reply_document(
        document=io.BytesIO(pdf_bytes),
        filename=filename,
        caption=f"Done — {len(images)} page(s).",
    )


async def handle_convert_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle Convert / Cancel button presses."""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    if query.data == "convert":
        await do_convert(update, context)
    elif query.data == "cancel_batch":
        count = len(get_batch(user_id))
        cleanup_user(user_id)
        await query.edit_message_text(
            f"Cancelled — cleared {count} photo(s)."
            if count
            else "Nothing to cancel."
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Send me photos (one by one or as an album) and I'll combine them "
        "into a PDF.\n\n"
        "• After sending photos, tap Convert to make the PDF\n"
        "• Tap Cancel to clear your batch\n"
        "• Caption a photo with 'make pdf' to convert instantly"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    count = len(get_batch(user_id))
    cleanup_user(user_id)
    if count:
        await update.effective_message.reply_text(
            f"Cancelled — cleared {count} photo(s)."
        )
    else:
        await update.effective_message.reply_text("Nothing to cancel.")


async def prompt_convert(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int
) -> None:
    """Reply with Convert/Cancel buttons for the user's current batch."""
    total = len(get_batch(user_id))
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Batch has {total} photo(s). Convert to PDF?",
        reply_markup=build_convert_buttons(),
    )


async def flush_album(
    media_group_id: str,
    user_id: int,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Wait for an album to finish arriving, then add all its photos at once."""
    await asyncio.sleep(ALBUM_FLUSH_SECONDS)
    pending = album_buffer.pop(media_group_id, [])
    album_tasks.pop(media_group_id, None)

    if not pending:
        return

    added = 0
    for update in pending:
        photo = update.effective_message.photo[-1]
        if photo.file_unique_id in get_added_ids(user_id):
            continue
        try:
            path = await download_photo(update, context)
        except Exception:
            logger.exception("Could not download album photo for user %s", user_id)
            continue
        get_added_ids(user_id).add(photo.file_unique_id)
        get_batch(user_id).append(path)
        added += 1

    if added:
        await prompt_convert(context, chat_id, user_id)
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Received an album, but couldn't download any photos.",
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    message = update.effective_message
    media_group_id = message.media_group_id

    # Photo with a conversion caption -> convert immediately.
    if message.caption and _caption_triggers(message.caption):
        try:
            path = await download_photo(update, context)
        except Exception as exc:
            await message.reply_text(f"Couldn't download the photo: {exc}")
            return
        get_added_ids(user_id).add(message.photo[-1].file_unique_id)
        get_batch(user_id).append(path)
        await do_convert(update, context)
        return

    # Album -> buffer until the group finishes arriving.
    if media_group_id:
        album_buffer.setdefault(media_group_id, []).append(update)
        if media_group_id not in album_tasks:
            album_tasks[media_group_id] = asyncio.create_task(
                flush_album(media_group_id, user_id, message.chat_id, context)
            )
        return

    # Single photo -> add directly.
    photo = message.photo[-1]
    if photo.file_unique_id in get_added_ids(user_id):
        return
    try:
        path = await download_photo(update, context)
    except Exception as exc:
        await message.reply_text(f"Couldn't download the photo: {exc}")
        return
    get_added_ids(user_id).add(photo.file_unique_id)
    get_batch(user_id).append(path)
    await prompt_convert(context, message.chat_id, user_id)


def _caption_triggers(caption: str) -> bool:
    lowered = caption.lower().strip()
    return lowered in ("pdf", "make pdf") or "/pdf" in lowered


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text.strip().lower()
    if text in ("pdf", "make pdf"):
        user_id = update.effective_user.id
        if not get_batch(user_id):
            await update.effective_message.reply_text(
                "No photos in your batch yet. Send me some photos first."
            )
            return
        await prompt_convert(context, update.effective_message.chat_id, user_id)

def main() -> None:
    if not TOKEN:
        raise SystemExit(
            "BOT_TOKEN is not set. Copy .env.example to .env and add your token."
        )

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(handle_convert_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
