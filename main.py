import logging
import os
import sys
import sqlite3
import requests
import re

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

cursor.execute("""
CREATE TABLE IF NOT EXISTS requests(
movie TEXT UNIQUE
)
""")

cursor.execute(
    "CREATE INDEX IF NOT EXISTS idx_search ON movies(search_name)"
)

conn.commit()

# ---------------- CLEAN SEARCH ----------------
def clean_name(name):

    name = name.lower()
    name = re.sub(r"[._-]", " ", name)
    name = re.sub(r"\s+", " ", name)

    return name.strip()


class MovieBot:

    def __init__(self, application):
        self.application = application

    # ---------------- AUTO DELETE ----------------
    async def auto_delete(self, context):

        job = context.job

        try:
            await context.bot.delete_message(
                chat_id=job.data["chat_id"],
                message_id=job.data["message_id"]
            )
        except:
            pass

    # ---------------- POSTER ----------------
    async def send_movie_poster(self, update, movie):

        if not TMDB_API_KEY:
            return

        try:

            url = "https://api.themoviedb.org/3/search/movie"

            params = {
                "api_key": TMDB_API_KEY,
                "query": movie
            }

            r = requests.get(url, params=params, timeout=10).json()

            if not r.get("results"):
                return

            poster = r["results"][0].get("poster_path")

            if not poster:
                return

            poster_url = f"https://image.tmdb.org/t/p/w500{poster}"

            await update.message.reply_photo(
                photo=poster_url,
                caption=f"🎬 {movie.title()}"
            )

        except Exception as e:
            logger.error(e)

    # ---------------- START ----------------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        msg = await update.message.reply_text(
            "🎬 Movie Search Bot\n\nSend a movie name."
        )

        context.job_queue.run_once(
            self.auto_delete,
            18000,
            data={"chat_id": msg.chat_id, "message_id": msg.message_id}
        )

    # ---------------- SEARCH ----------------
    async def search_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        movie = clean_name(update.message.text)

        await self.send_movie_poster(update, movie)

        words = movie.split()

        query = " AND ".join(["search_name LIKE ?"] * len(words))
        params = [f"%{w}%" for w in words]

        sql = f"""
        SELECT file_name
        FROM movies
        WHERE {query}
        LIMIT 50
        """

        cursor.execute(sql, params)

        results = cursor.fetchall()

        if not results:

            msg = await update.message.reply_text(
                "❌ Movie not found.\n\n📩 Request sent to admin."
            )

            context.job_queue.run_once(
                self.auto_delete,
                18000,
                data={"chat_id": msg.chat_id, "message_id": msg.message_id}
            )

            cursor.execute(
                "SELECT movie FROM requests WHERE movie=?",
                (movie,)
            )

            if not cursor.fetchone() and REQUEST_CHANNEL_ID:

                cursor.execute(
                    "INSERT INTO requests VALUES (?)",
                    (movie,)
                )

                conn.commit()

                await context.bot.send_message(
                    chat_id=REQUEST_CHANNEL_ID,
                    text=movie
                )

            return

        languages = set()

        for (name,) in results:

            name = name.lower()

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

        msg = await update.message.reply_text(
            "🌐 Select Language:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

        context.job_queue.run_once(
            self.auto_delete,
            18000,
            data={"chat_id": msg.chat_id, "message_id": msg.message_id}
        )

    # ---------------- BUTTON HANDLER ----------------
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        query = update.callback_query
        await query.answer()

        data = query.data.split("|")

        # -------- LANGUAGE --------
        if data[0] == "lang":

            movie = data[1]
            language = data[2]

            cursor.execute(
                """
                SELECT file_name
                FROM movies
                WHERE search_name LIKE ?
                AND file_name LIKE ?
                """,
                (f"%{movie}%", f"%{language}%")
            )

            results = cursor.fetchall()

            qualities = set()

            for (name,) in results:

                name = name.lower()

                if "2160" in name or "4k" in name:
                    qualities.add("4K")
                if "1080" in name:
                    qualities.add("1080p")
                if "720" in name:
                    qualities.add("720p")
                if "480" in name:
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

        # -------- QUALITY --------
        elif data[0] == "quality":

            movie = data[1]
            language = data[2]
            quality = data[3]

            cursor.execute(
                """
                SELECT message_id,chat_id
                FROM movies
                WHERE search_name LIKE ?
                AND file_name LIKE ?
                AND file_name LIKE ?
                """,
                (f"%{movie}%", f"%{language}%", f"%{quality.lower()}%")
            )

            results = cursor.fetchall()

            if not results:
                await query.edit_message_text("❌ File not found.")
                return

            for message_id, chat_id in results[:5]:

                await context.bot.copy_message(
                    chat_id=query.from_user.id,
                    from_chat_id=chat_id,
                    message_id=message_id
                )

            await query.edit_message_text("✅ File sent!")

    # ---------------- INDEX ----------------
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

    application.run_polling(
        drop_pending_updates=True,
        close_loop=False
    )


if __name__ == "__main__":
    main()