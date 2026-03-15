import logging
import os
import sys
import sqlite3
import requests

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


class MovieBot:

    def __init__(self, application):
        self.application = application

    # ---------------- POSTER FUNCTION ----------------
    async def send_movie_poster(self, update, movie):

        if not TMDB_API_KEY:
            return

        try:

            url = "https://api.themoviedb.org/3/search/movie"

            params = {
                "api_key": TMDB_API_KEY,
                "query": movie
            }

            r = requests.get(url, params=params).json()

            if not r["results"]:
                return

            poster = r["results"][0]["poster_path"]

            if not poster:
                return

            poster_url = f"https://image.tmdb.org/t/p/w500{poster}"

            await update.message.reply_photo(
                photo=poster_url,
                caption=f"🎬 {movie.title()}"
            )

        except Exception as e:
            logger.error(e)

    # ---------------- JOIN BUTTONS ----------------
    def join_buttons(self):

        keyboard = []

        if FORCE_CHANNEL:
            keyboard.append([
                InlineKeyboardButton(
                    "📢 Join Channel",
                    url=f"https://t.me/{FORCE_CHANNEL.replace('@','')}"
                )
            ])

        if FORCE_GROUP:
            keyboard.append([
                InlineKeyboardButton(
                    "💬 Join Group",
                    url=f"https://t.me/{FORCE_GROUP.replace('@','')}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton("✅ I Joined", callback_data="check_join")
        ])

        return InlineKeyboardMarkup(keyboard)

    # ---------------- CHECK MEMBERSHIP ----------------
    async def check_membership(self, user_id, context):

        try:

            if FORCE_CHANNEL_ID:
                member = await context.bot.get_chat_member(
                    FORCE_CHANNEL_ID, user_id
                )

                if member.status in ["left", "kicked"]:
                    return False

            if FORCE_GROUP_ID:
                member = await context.bot.get_chat_member(
                    FORCE_GROUP_ID, user_id
                )

                if member.status in ["left", "kicked"]:
                    return False

            return True

        except Exception as e:
            logger.error(e)
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

    # ---------------- SEARCH MOVIE ----------------
    async def search_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        movie = update.message.text.lower()

        # send poster first
        await self.send_movie_poster(update, movie)

        cursor.execute(
            "SELECT file_name FROM movies WHERE file_name LIKE ?",
            ('%' + movie + '%',)
        )

        results = cursor.fetchall()

        if not results:
            await update.message.reply_text("❌ Movie not found.")
            return

        languages = set()

        for (name,) in results:

            if "malayalam" in name:
                languages.add("Malayalam")

            if "tamil" in name:
                languages.add("Tamil")

            if "hindi" in name:
                languages.add("Hindi")

            if "english" in name:
                languages.add("English")

        if not languages:
            languages.add("Movie")

        buttons = []

        for lang in languages:
            buttons.append([
                InlineKeyboardButton(
                    lang,
                    callback_data=f"lang|{movie}|{lang.lower()}"
                )
            ])

        await update.message.reply_text(
            "🌐 Select Language:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    # ---------------- BUTTON HANDLER ----------------
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        query = update.callback_query
        await query.answer()

        data = query.data.split("|")

        if data[0] == "lang":

            movie = data[1]
            language = data[2]

            cursor.execute(
                "SELECT file_name FROM movies WHERE file_name LIKE ? AND file_name LIKE ?",
                ('%' + movie + '%', '%' + language + '%')
            )

            results = cursor.fetchall()

            qualities = set()

            for (name,) in results:

                if "1080" in name:
                    qualities.add("1080p")

                elif "720" in name:
                    qualities.add("720p")

                elif "480" in name:
                    qualities.add("480p")

            if not qualities:
                qualities.add("File")

            buttons = []

            for q in qualities:
                buttons.append([
                    InlineKeyboardButton(
                        q,
                        callback_data=f"quality|{movie}|{language}|{q}"
                    )
                ])

            await query.edit_message_text(
                "🎥 Select Quality:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif data[0] == "quality":

            movie = data[1]
            language = data[2]
            quality = data[3]

            cursor.execute(
                """
                SELECT message_id,chat_id
                FROM movies
                WHERE file_name LIKE ?
                AND file_name LIKE ?
                AND file_name LIKE ?
                """,
                ('%' + movie + '%', '%' + language + '%', '%' + quality + '%')
            )

            results = cursor.fetchall()

            if not results:
                await query.edit_message_text("❌ File not found.")
                return

            for message_id, chat_id in results:

                await context.bot.copy_message(
                    chat_id=query.from_user.id,
                    from_chat_id=chat_id,
                    message_id=message_id
                )

            await query.edit_message_text("✅ File sent!")

    # ---------------- INDEX MOVIES ----------------
    async def index_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        if update.effective_chat.id != PRIVATE_GROUP_ID:
            return

        msg = update.message

        if msg.document:
            file_name = msg.document.file_name.lower()

        elif msg.video:
            file_name = msg.video.file_name or "movie"

        else:
            return

        cursor.execute(
            "INSERT INTO movies VALUES (?,?,?)",
            (file_name, msg.message_id, update.effective_chat.id)
        )

        conn.commit()

        logger.info(f"Indexed: {file_name}")


# ---------------- MAIN ----------------
def main():

    application = Application.builder().token(BOT_TOKEN).build()

    bot = MovieBot(application)

    application.add_handler(CommandHandler("start", bot.start))

    application.add_handler(
        CallbackQueryHandler(bot.button_handler)
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

    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()