import logging
import os
import sys
import sqlite3

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

PRIVATE_GROUP_ID = int(os.getenv("PRIVATE_GROUP_ID"))
REQUEST_CHANNEL_ID = int(os.getenv("REQUEST_CHANNEL_ID"))

FORCE_CHANNEL_ID = int(os.getenv("FORCE_CHANNEL_ID"))
FORCE_GROUP_ID = int(os.getenv("FORCE_GROUP_ID"))

FORCE_CHANNEL = os.getenv("FORCE_CHANNEL")
FORCE_GROUP = os.getenv("FORCE_GROUP")

if not BOT_TOKEN:
    print("BOT_TOKEN missing")
    sys.exit(1)

# ---------------- DATABASE ----------------
conn = sqlite3.connect("movies.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS movies(
file_name TEXT,
message_id INTEGER,
language TEXT
)
""")

conn.commit()


# ---------------- BOT CLASS ----------------
class MovieBot:

    def __init__(self, application):
        self.application = application

    # ---------------- DETECT LANGUAGE ----------------
    def detect_language(self, file_name):

        name = file_name.lower()

        if "malayalam" in name or "mal" in name:
            return "malayalam"

        elif "tamil" in name:
            return "tamil"

        elif "hindi" in name:
            return "hindi"

        elif "telugu" in name:
            return "telugu"

        elif "eng" in name or "english" in name:
            return "english"

        return "unknown"

    # ---------------- JOIN BUTTONS ----------------
    def join_buttons(self):

        keyboard = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_CHANNEL.replace('@','')}")],
            [InlineKeyboardButton("💬 Join Group", url=f"https://t.me/{FORCE_GROUP.replace('@','')}")],
            [InlineKeyboardButton("✅ I Joined", callback_data="check_join")]
        ]

        return InlineKeyboardMarkup(keyboard)

    # ---------------- CHECK MEMBERSHIP ----------------
    async def check_membership(self, user_id, context):

        try:

            channel_member = await context.bot.get_chat_member(FORCE_CHANNEL_ID, user_id)
            group_member = await context.bot.get_chat_member(FORCE_GROUP_ID, user_id)

            if channel_member.status in ["left", "kicked"]:
                return False

            if group_member.status in ["left", "kicked"]:
                return False

            return True

        except Exception as e:
            logger.error(f"Membership check error: {e}")
            return False

    # ---------------- START ----------------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        user_id = update.effective_user.id

        joined = await self.check_membership(user_id, context)

        if not joined:

            await update.message.reply_text(
                "🚫 You must join our channel and group to use this bot.",
                reply_markup=self.join_buttons()
            )
            return

        await update.message.reply_text(
            "🎬 Movie Search Bot\n\nSend a movie name."
        )

    # ---------------- BUTTON CHECK ----------------
    async def check_join_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        query = update.callback_query
        user_id = query.from_user.id

        await query.answer()

        joined = await self.check_membership(user_id, context)

        if joined:

            await query.edit_message_text(
                "✅ Verification successful!\n\nNow send the movie name."
            )

        else:

            await query.answer(
                "❌ You still haven't joined the channel or group!",
                show_alert=True
            )

    # ---------------- SEARCH MOVIE ----------------
    async def search_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        user_id = update.effective_user.id

        joined = await self.check_membership(user_id, context)

        if not joined:

            await update.message.reply_text(
                "🚫 Please join our channel and group first.",
                reply_markup=self.join_buttons()
            )
            return

        query = update.message.text.lower()

        cursor.execute(
            "SELECT language FROM movies WHERE file_name LIKE ?",
            ('%' + query + '%',)
        )

        rows = cursor.fetchall()

        if not rows:

            await update.message.reply_text(
                "❌ Movie not found. Request sent."
            )

            try:
                await context.bot.send_message(
                    chat_id=REQUEST_CHANNEL_ID,
                    text=query
                )
            except Exception as e:
                logger.error(f"Request channel error: {e}")

            return

        languages = list(set([row[0] for row in rows]))

        keyboard = []

        for lang in languages:

            keyboard.append([
                InlineKeyboardButton(
                    lang.capitalize(),
                    callback_data=f"lang|{query}|{lang}"
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🎬 Select Language",
            reply_markup=reply_markup
        )

    # ---------------- LANGUAGE FILTER ----------------
    async def language_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        query = update.callback_query
        await query.answer()

        data = query.data.split("|")

        movie = data[1]
        language = data[2]

        cursor.execute(
            "SELECT message_id FROM movies WHERE file_name LIKE ? AND language=?",
            ('%' + movie + '%', language)
        )

        results = cursor.fetchall()

        if not results:

            await query.message.reply_text("❌ File not found.")
            return

        await query.message.reply_text("🎬 Sending movie...")

        for msg in results[:3]:

            await context.bot.forward_message(
                chat_id=query.from_user.id,
                from_chat_id=PRIVATE_GROUP_ID,
                message_id=msg[0]
            )

    # ---------------- INDEX MOVIES ----------------
    async def index_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        if update.effective_chat.id != PRIVATE_GROUP_ID:
            return

        if not update.message.document:
            return

        file_name = update.message.document.file_name.lower()
        message_id = update.message.message_id

        language = self.detect_language(file_name)

        cursor.execute(
            "INSERT INTO movies VALUES (?,?,?)",
            (file_name, message_id, language)
        )

        conn.commit()

        logger.info(f"Indexed movie: {file_name} ({language})")


# ---------------- MAIN ----------------
def main():

    application = Application.builder().token(BOT_TOKEN).build()

    bot = MovieBot(application)

    application.add_handler(CommandHandler("start", bot.start))

    application.add_handler(
        CallbackQueryHandler(bot.check_join_button, pattern="check_join")
    )

    application.add_handler(
        CallbackQueryHandler(bot.language_filter, pattern="lang")
    )

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot.search_movie)
    )

    application.add_handler(
        MessageHandler(
            filters.Chat(PRIVATE_GROUP_ID) & filters.Document.ALL,
            bot.index_movie
        )
    )

    logger.info("Bot running...")

    application.run_polling()


if __name__ == "__main__":
    main()