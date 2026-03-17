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

    # -------- POSTER --------
    async def send_poster_selection(self, update, user_input):

        if not TMDB_API_KEY:
            return False

        try:
            raw = clean_name(user_input)

            movie = re.sub(
                r"\b(malayalam|mal|tamil|tam|hindi|hin|kannada|kan|english|eng|movie)\b",
                "",
                raw
            ).strip()

            url = "https://api.themoviedb.org/3/search/movie"

            params = {
                "api_key": TMDB_API_KEY,
                "query": movie,
                "include_adult": False
            }

            res = requests.get(url, params=params, timeout=10).json()
            results = res.get("results", [])[:5]

            if not results:
                return False

            for r in results:
                poster = r.get("poster_path")
                if not poster:
                    continue

                poster_url = f"https://image.tmdb.org/t/p/w500{poster}"
                title = r.get("title", "Unknown")
                year = r.get("release_date", "----")[:4]
                movie_id = r.get("id")

                buttons = [[InlineKeyboardButton(
                    "✅ Select",
                    callback_data=f"select|{movie_id}|{user_input}"
                )]]

                await update.message.reply_photo(
                    photo=poster_url,
                    caption=f"🎬 {title} ({year})",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )

            return True

        except Exception as e:
            logger.error(f"Poster error: {e}")
            return False

    # -------- START --------
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🎬 Send movie name")

    # -------- SEARCH --------
    async def search_movie(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        user_input = update.message.text

        ok = await self.send_poster_selection(update, user_input)
        if ok:
            return

        await update.message.reply_text("❌ No poster found")

    # -------- BUTTON --------
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        query = update.callback_query
        await query.answer()

        data = query.data.split("|")

        # -------- SELECT --------
        if data[0] == "select":

            user_input = data[2]
            movie = clean_name(user_input)
            words = movie.split()

            # ✅ STRICT AND SEARCH
            sql = " AND ".join(["search_name LIKE ?"] * len(words))
            params = [f"%{w}%" for w in words]

            cursor.execute(f"SELECT file_name FROM movies WHERE {sql}", params)
            results = cursor.fetchall()

            if not results:
                await query.message.reply_text("❌ Movie not found in DB\nWe will receive your request📩.\n Next time, we will add it📌.\nMaybe, please check your spelling and try searching again😊")
                return

            languages = set()

            for (name,) in results:
                name = name.lower()

                # ✅ DOUBLE CHECK MATCH
                if not all(w in name for w in words):
                    continue

                for lang, keys in LANG_MAP.items():
                    if any(k in name for k in keys):
                        languages.add(lang.capitalize())

                if any(x in name for x in ["multi", "dual", "+"]):
                    languages.add("Multi Audio")

            if not languages:
                languages.add("Movie")

            buttons = [[InlineKeyboardButton(
                l, callback_data=f"lang|{movie}|{l.lower()}"
            )] for l in languages]

            await query.message.reply_text(
                "🌐 Select Language:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # -------- LANGUAGE --------
        elif data[0] == "lang":

            movie, language = data[1], data[2]
            words = movie.split()

            cursor.execute(
                "SELECT file_name FROM movies WHERE search_name LIKE ?",
                (f"%{movie}%",)
            )
            results = cursor.fetchall()

            qualities = set()

            for (name,) in results:
                name = name.lower()

                if not all(w in name for w in words):
                    continue

                if language == "multi audio":
                    if not any(x in name for x in ["multi", "dual", "+"]):
                        continue
                else:
                    if not any(x in name for x in LANG_MAP.get(language, [])):
                        continue

                if "2160" in name or "4k" in name:
                    qualities.add("4K")
                elif "1080" in name:
                    qualities.add("1080p")
                elif "720" in name:
                    qualities.add("720p")
                elif "480" in name:
                    qualities.add("480p")

            if not qualities:
                qualities.add("File")

            buttons = [[InlineKeyboardButton(
                q, callback_data=f"quality|{movie}|{language}|{q}"
            )] for q in qualities]

            await query.edit_message_text(
                "🎥 Select Quality:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # -------- QUALITY --------
        elif data[0] == "quality":

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
                await query.edit_message_text("❌ File not found")
                return

            for msg_id, chat_id in files[:5]:
                await context.bot.copy_message(
                    chat_id=query.from_user.id,
                    from_chat_id=chat_id,
                    message_id=msg_id
                )

            await query.edit_message_text("✅ File sent!")

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

    app.add_handler(CommandHandler("start", bot.start))
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
