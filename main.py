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

PRIVATE_GROUP_ID = int(os.getenv("PRIVATE_GROUP_ID", "0"))
REQUEST_CHANNEL_ID = int(os.getenv("REQUEST_CHANNEL_ID", "0"))

FORCE_CHANNEL_ID = int(os.getenv("FORCE_CHANNEL_ID", "0"))
FORCE_GROUP_ID = int(os.getenv("FORCE_GROUP_ID", "0"))

FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "")
FORCE_GROUP = os.getenv("FORCE_GROUP", "")

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
chat_id INTEGER
)
""")

conn.commit()

# ---------------- BOT CLASS ----------------
class MovieBot:

    def __init__(self, application):
        self.application = application

    # ---------------- JOIN BUTTONS ----------------
    def join_buttons(self):

        keyboard = []

        if FORCE_CHANNEL:
            keyboard.append(
                [InlineKeyboardButton(
                    "📢 Join Channel",
                    url=f"https://t.me/{FORCE_CHANNEL.replace('@','')}"
                )]
            )

        if FORCE_GROUP:
            keyboard.append(
                [InlineKeyboardButton(
                    "💬 Join Group",
                    url=f"https://t.me/{FORCE_GROUP.replace('@','')}"
                )]
            )

        keyboard.append(
            [InlineKeyboardButton("✅ I Joined", callback_data="check_join")]
        )

        return InlineKeyboardMarkup(keyboard)

    # ---------------- CHECK MEMBERSHIP ----------------
    async def check_membership(self, user_id, context):

        try:

            if FORCE_CHANNEL_ID:
                channel_member = await context.bot.get_chat_member(
                    FORCE_CHANNEL_ID, user_id
                )

                if channel_member.status in ["left", "kicked"]:
                    return False

            if FORCE_GROUP_ID:
                group_member = await context.bot.get_chat_member(
                    FORCE_GROUP_ID, user_id
                )

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
                "🚫 Please join our channel and group first.",
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
            "SELECT message_id,chat_id,file_name FROM movies WHERE file_name LIKE ?",
            ('%' + query + '%',)
        )

        results = cursor.fetchall()

        if results:

            await update.message.reply_text("🎬 Movie found! Sending file...")

            for message_id, chat_id, name in results[:5]:

                await context.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=chat_id,
                    message_id=message_id
                )

        else:

            await update.message.reply_text(
                "❌ Movie not found. Request sent."
            )

            if REQUEST_CHANNEL_ID:

                try:

                    await context.bot.send_message(
                        chat_id=REQUEST_CHANNEL_ID,
                        text=query
                    )

                except Exception as e:

                    logger.error(f"Request channel error: {e}")

    # ---------------- INDEX MOVIES ----------------
    async def index_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        if update.effective_chat.id != PRIVATE_GROUP_ID:
            return

        msg = update.message

        if msg.document:
            file_name = msg.document.file_name.lower()

        elif msg.video:
            file_name = msg.video.file_name or "video_movie"

        else:
            return

        message_id = msg.message_id
        chat_id = update.effective_chat.id

        cursor.execute(
            "INSERT INTO movies VALUES (?,?,?)",
            (file_name, message_id, chat_id)
        )

        conn.commit()

        logger.info(f"Indexed movie: {file_name}")

# ---------------- MAIN ----------------
def main():

    application = Application.builder().token(BOT_TOKEN).build()

    bot = MovieBot(application)

    application.add_handler(CommandHandler("start", bot.start))

    application.add_handler(
        CallbackQueryHandler(bot.check_join_button, pattern="check_join")
    )

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot.search_movie)
    )

    application.add_handler(
        MessageHandler(
            filters.Chat(PRIVATE_GROUP_ID) &
            (filters.Document.ALL | filters.VIDEO),
            bot.index_movie
        )
    )

    logger.info("Bot running...")

    application.run_polling()


if __name__ == "__main__":
    main()