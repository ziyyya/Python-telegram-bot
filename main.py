import logging
import os
import sys
import sqlite3

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
PRIVATE_GROUP_ID = os.getenv("PRIVATE_GROUP_ID")
REQUEST_CHANNEL_ID = os.getenv("REQUEST_CHANNEL_ID")

# FORCE JOIN USERNAMES
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL")   # example @mychannel
FORCE_GROUP = os.getenv("FORCE_GROUP")       # example @mygroup

if not BOT_TOKEN:
    print("BOT_TOKEN missing")
    sys.exit(1)

if not PRIVATE_GROUP_ID:
    print("PRIVATE_GROUP_ID missing")
    sys.exit(1)

if not REQUEST_CHANNEL_ID:
    print("REQUEST_CHANNEL_ID missing")
    sys.exit(1)

PRIVATE_GROUP_ID = int(PRIVATE_GROUP_ID)
REQUEST_CHANNEL_ID = int(REQUEST_CHANNEL_ID)

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

    # ---------------- CHECK JOIN ----------------
    async def check_membership(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        user_id = update.effective_user.id

        try:
            channel = await context.bot.get_chat_member(FORCE_CHANNEL, user_id)
            group = await context.bot.get_chat_member(FORCE_GROUP, user_id)

            if channel.status in ["left", "kicked"]:
                return False

            if group.status in ["left", "kicked"]:
                return False

            return True

        except:
            return False

    # ---------------- START ----------------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        joined = await self.check_membership(update, context)

        if not joined:
            await update.message.reply_text(
                "🚫 You must join our channel and group first!\n\n"
                f"📢 Channel: https://t.me/{FORCE_CHANNEL.replace('@','')}\n"
                f"💬 Group: https://t.me/{FORCE_GROUP.replace('@','')}\n\n"
                "After joining send /start again."
            )
            return

        await update.message.reply_text(
            "🎬 Movie Search Bot\n\nSend a movie name."
        )

    # ---------------- SEARCH MOVIE ----------------
    async def search_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        joined = await self.check_membership(update, context)

        if not joined:
            await update.message.reply_text(
                "🚫 Join our channel and group first!\n\n"
                f"📢 https://t.me/{FORCE_CHANNEL.replace('@','')}\n"
                f"💬 https://t.me/{FORCE_GROUP.replace('@','')}"
            )
            return

        query = update.message.text.lower()

        cursor.execute(
            "SELECT message_id,file_name FROM movies WHERE file_name LIKE ?",
            ('%' + query + '%',)
        )

        results = cursor.fetchall()

        # ---------- MOVIE FOUND ----------
        if results:

            await update.message.reply_text("🎬 Movie found! Sending file...")

            for message_id, name in results[:3]:

                await context.bot.forward_message(
                    chat_id=update.effective_user.id,
                    from_chat_id=PRIVATE_GROUP_ID,
                    message_id=message_id
                )

            return

        # ---------- MOVIE NOT FOUND ----------
        await update.message.reply_text(
            "❌ Movie not found. Request sent. We will add it soon 😔"
        )

        try:
            await context.bot.send_message(
                chat_id=REQUEST_CHANNEL_ID,
                text=f"🎬 Movie Request:\n{query}"
            )

        except Exception as e:
            logger.error(f"Request channel error: {e}")

    # ---------------- INDEX MOVIES ----------------
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
