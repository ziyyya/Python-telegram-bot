import asyncio
import logging
import os
import sys
import sqlite3

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode


# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
PRIVATE_GROUP_ID = os.getenv("PRIVATE_GROUP_ID")

if not BOT_TOKEN:
    print("BOT_TOKEN missing")
    sys.exit(1)

if not PRIVATE_GROUP_ID:
    print("PRIVATE_GROUP_ID missing")
    sys.exit(1)

PRIVATE_GROUP_ID = int(PRIVATE_GROUP_ID)


# ---------------- DATABASE ----------------
conn = sqlite3.connect("movies.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS movies(
file_name TEXT,
message_id INTEGER
)
""")

conn.commit()


# ---------------- BOT CLASS ----------------
class MovieBot:

    def __init__(self, application):
        self.application = application

    # START
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        await update.message.reply_text(
            "🎬 Movie Search Bot\n\nSend a movie name."
        )

    # SEARCH MOVIE
    async def search_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        query = update.message.text.lower()

        cursor.execute(
            "SELECT message_id,file_name FROM movies WHERE file_name LIKE ?",
            ('%' + query + '%',)
        )

        results = cursor.fetchall()

        if not results:
            await update.message.reply_text("❌ Movie not found.")
            return

        await update.message.reply_text("🎬 Movie found! Sending file...")

        for message_id, name in results[:3]:

            await context.bot.forward_message(
                chat_id=update.effective_user.id,
                from_chat_id=PRIVATE_GROUP_ID,
                message_id=message_id
            )

    # INDEX FILES
    async def index_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        if update.effective_chat.id != PRIVATE_GROUP_ID:
            return

        if not update.message.document:
            return

        file_name = update.message.document.file_name.lower()
        message_id = update.message.message_id

        cursor.execute(
            "INSERT INTO movies VALUES (?,?)",
            (file_name, message_id)
        )

        conn.commit()

        logger.info(f"Indexed movie: {file_name}")


# ---------------- MAIN ----------------
def main():

    application = Application.builder().token(BOT_TOKEN).build()

    bot = MovieBot(application)

    application.add_handler(CommandHandler("start", bot.start))

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot.search_movie)
    )

    application.add_handler(
        MessageHandler(filters.Chat(PRIVATE_GROUP_ID) & filters.Document.ALL, bot.index_movie)
    )

    logger.info("Bot running...")

    application.run_polling()


if __name__ == "__main__":
    main()
