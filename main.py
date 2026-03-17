import logging
import os
import sys
import sqlite3
import requests
import re
import asyncio  # ✅ NEW

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

PRIVATE_GROUP_ID = int(os.getenv("PRIVATE_GROUP_ID", "0"))

if not BOT_TOKEN:
    print("BOT_TOKEN missing")
    sys.exit(1)

# ---------------- DATABASE ----------------
conn = sqlite3.connect("movies.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS movies(
file_name TEXT,
search_name TEXT,
message_id INTEGER UNIQUE,
chat_id INTEGER
)
""")

cursor.execute("CREATE INDEX IF NOT EXISTS idx_search ON movies(search_name)")
conn.commit()

# ---------------- CLEAN ----------------
def clean_name(name):
    name = name.lower()
    name = re.sub(r"[._-]", " ", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()

# ---------------- LANG ----------------
LANG_MAP = {
    "malayalam": ["malayalam", "mal"],
    "tamil": ["tamil", "tam"],
    "hindi": ["hindi", "hin"],
    "kannada": ["kannada", "kan"],
    "english": ["english", "eng"]
}

# ---------------- BOT ----------------
class MovieBot:

    def __init__(self, app):
        self.app = app

    # ✅ AUTO DELETE FUNCTION
    async def auto_delete(self, context, chat_id, message_id, delay=10800):
        await asyncio.sleep(delay)
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.warning(f"Auto delete failed: {e}")

    # -------- START --------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🎬 Send movie name")

    # -------- SEARCH --------
    async def search_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔍 Searching... (feature simplified here)")

    # -------- BUTTON --------
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        query = update.callback_query
        await query.answer()

        data = query.data.split("|")

        # -------- QUALITY --------
        if data[0] == "quality":

            movie, language, quality = data[1], data[2], data[3]
            words = movie.split()

            cursor.execute(
                "SELECT message_id,chat_id,file_name FROM movies WHERE search_name LIKE ?",
                (f"%{movie}%",)
            )
            results = cursor.fetchall()

            files = []

            for msg_id, chat_id, name in results:
                name = name.lower()

                if not all(w in name for w in words):
                    continue

                if language == "multi audio":
                    if not any(x in name for x in ["multi", "dual", "+"]):
                        continue
                else:
                    if not any(x in name for x in LANG_MAP.get(language, [])):
                        continue

                if quality != "File" and quality.lower() not in name:
                    continue

                files.append((msg_id, chat_id))

            if not files:
                await query.edit_message_text(
                    "❌ File not found\n"
                    "Thanks for your request. We’ll try to include it next time 📌\n"
                    "Please check your spelling and try again 😊"
                )
                return

            sent_messages = []

            for i, (msg_id, chat_id) in enumerate(files[:5]):

                caption = None

                # ✅ ADD MESSAGE ONLY TO LAST FILE
                if i == len(files[:5]) - 1:
                    caption = "📌 This file will be auto-deleted in 3 hours ⏳"

                sent = await context.bot.copy_message(
                    chat_id=query.from_user.id,
                    from_chat_id=chat_id,
                    message_id=msg_id,
                    caption=caption
                )

                sent_messages.append(sent)

                # ✅ AUTO DELETE FILE
                context.application.create_task(
                    self.auto_delete(context, sent.chat_id, sent.message_id)
                )

            # ✅ SUCCESS MESSAGE (AUTO DELETE AFTER 5 MIN)
            msg = await query.edit_message_text("✅ File sent!")

            context.application.create_task(
                self.auto_delete(context, msg.chat_id, msg.message_id, delay=300)
            )

    # -------- INDEX --------
    async def index_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        if update.effective_chat.id != PRIVATE_GROUP_ID:
            return

        msg = update.message

        if msg.document:
            file_name = msg.document.file_name.lower()
        elif msg.video:
            file_name = (msg.video.file_name or "movie").lower()
        else:
            return

        search_name = clean_name(file_name)

        cursor.execute(
            "INSERT OR IGNORE INTO movies VALUES (?,?,?,?)",
            (file_name, search_name, msg.message_id, update.effective_chat.id)
        )

        conn.commit()
        logger.info(f"Indexed: {search_name}")

# ---------------- MAIN ----------------
def main():

    app = Application.builder().token(BOT_TOKEN).build()
    bot = MovieBot(app)

    app.add_handler(CallbackQueryHandler(bot.button_handler))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot.search_movie)
    )

    app.add_handler(
        MessageHandler(
            filters.Chat(PRIVATE_GROUP_ID) &
            (filters.Document.ALL | filters.VIDEO),
            bot.index_movie
        )
    )

    logger.info("Bot running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
