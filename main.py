import asyncio
import logging
import os
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ---------------- ENV VARIABLES ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
PRIVATE_GROUP_ID = os.getenv("PRIVATE_GROUP_ID")

if not BOT_TOKEN:
    print("❌ BOT_TOKEN missing")
    sys.exit(1)

if not PRIVATE_GROUP_ID:
    print("❌ PRIVATE_GROUP_ID missing")
    sys.exit(1)

PRIVATE_GROUP_ID = int(PRIVATE_GROUP_ID)

SEARCH_PREFIX = "🔍 Searching: "

# ---------------- BOT CLASS ----------------
class MovieBot:

    def __init__(self, application):
        self.application = application
        self.pending_searches = {}
        self.group_message_ids = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        await update.message.reply_text(
            "🎬 *Movie Search Bot*\n\n"
            "Send a movie name and I'll search it.\n"
            "_Hosted on Railway 🚀_\n\n"
            "Example: `Inception 2010`",
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_movie_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        user_id = update.effective_user.id
        movie_name = update.message.text.strip()

        if len(movie_name) > 100:
            await update.message.reply_text("❌ Movie name too long!")
            return

        self.pending_searches[user_id] = movie_name

        try:

            group_msg = await context.bot.send_message(
                chat_id=PRIVATE_GROUP_ID,
                text=f"{SEARCH_PREFIX}{movie_name}"
            )

            self.group_message_ids[movie_name.lower()] = group_msg.message_id

            await update.message.reply_text(
                f"🔎 Searching for *{movie_name}*...\n⏳ Waiting for file...",
                parse_mode=ParseMode.MARKDOWN
            )

            logger.info(f"Search sent to group: {movie_name}")

        except Exception as e:

            logger.error(f"Group error: {e}")

            await update.message.reply_text(
                "❌ Cannot access private group."
            )

    async def handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        if update.effective_chat.id != PRIVATE_GROUP_ID:
            return

        text = update.message.text or ""

        if not text.startswith(SEARCH_PREFIX):
            return

        movie_name = text.replace(SEARCH_PREFIX, "").strip().lower()

        if update.message.reply_to_message:

            reply_id = update.message.reply_to_message.message_id

            if reply_id == self.group_message_ids.get(movie_name):

                await self.forward_file(movie_name, update.message)

    async def handle_group_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        if update.effective_chat.id != PRIVATE_GROUP_ID:
            return

        if not update.message.reply_to_message:
            return

        text = update.message.reply_to_message.text or ""

        if not text.startswith(SEARCH_PREFIX):
            return

        movie_name = text.replace(SEARCH_PREFIX, "").strip().lower()

        await self.forward_file(movie_name, update.message)

    async def forward_file(self, movie_name, group_message):

        for user_id, requested in list(self.pending_searches.items()):

            if requested.lower() == movie_name:

                try:

                    await self.application.bot.forward_message(
                        chat_id=user_id,
                        from_chat_id=group_message.chat_id,
                        message_id=group_message.message_id
                    )

                    logger.info(f"File sent to user {user_id}")

                    del self.pending_searches[user_id]
                    self.group_message_ids.pop(movie_name, None)

                except Exception as e:

                    logger.error(f"Forward error: {e}")

                break


# ---------------- CLEANUP TASK ----------------
async def cleanup_old_searches(bot):

    while True:

        await asyncio.sleep(300)

        expired = list(bot.pending_searches.keys())

        for uid in expired:

            try:
                await bot.application.bot.send_message(
                    uid,
                    "⏰ Search expired. Try again."
                )
            except:
                pass

            bot.pending_searches.pop(uid, None)


# ---------------- POST INIT ----------------
async def post_init(application: Application):

    bot = application.bot_data["movie_bot"]

    application.create_task(cleanup_old_searches(bot))

# ---------------- MAIN ----------------
def main():

    logger.info("Starting Movie Bot")

    application = Application.builder().token(BOT_TOKEN).build()

    bot = MovieBot(application)

    application.add_handler(CommandHandler("start", bot.start))

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_movie_search)
    )

    application.add_handler(
        MessageHandler(filters.Chat(PRIVATE_GROUP_ID) & filters.TEXT, bot.handle_group_message)
    )

    application.add_handler(
        MessageHandler(filters.Chat(PRIVATE_GROUP_ID) & filters.Document.ALL, bot.handle_group_document)
    )

    # Start cleanup task
    application.job_queue.run_repeating(
        lambda context: asyncio.create_task(cleanup_old_searches(bot)),
        interval=300,
        first=300,
    )

    logger.info("Bot running...")

    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

