import asyncio
import logging
import os
import signal
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Railway Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PRIVATE_GROUP_ID = int(os.environ.get("PRIVATE_GROUP_ID", 0))
SEARCH_PREFIX = "🔍 Searching: "

# Debug prints (to check Railway variables)
print("DEBUG BOT_TOKEN:", BOT_TOKEN)
print("DEBUG PRIVATE_GROUP_ID:", PRIVATE_GROUP_ID)

@asynccontextmanager
async def lifespan(app: Application):
    """Graceful startup/shutdown"""
    await app.initialize()
    yield
    await app.shutdown()


class MovieBot:
    def __init__(self, application):
        self.application = application
        self.pending_searches = {}
        self.group_message_ids = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🎬 *Movie Search Bot*\n\n"
            "Send me a movie name and I'll find it for you!\n"
            "_Hosted on Railway 🚀_\n"
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

            logger.info(f"New search: {movie_name} by {user_id}")

        except Exception as e:
            logger.error(f"Group post failed: {e}")
            await update.message.reply_text("❌ Cannot access group.")

    async def handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        if update.effective_chat.id != PRIVATE_GROUP_ID:
            return

        message_text = update.message.text or ""

        if not message_text.startswith(SEARCH_PREFIX):
            return

        movie_name = message_text.replace(SEARCH_PREFIX, "").strip().lower()

        if update.message.reply_to_message:

            reply_msg_id = update.message.reply_to_message.message_id

            if reply_msg_id == self.group_message_ids.get(movie_name):

                await self._forward_file_to_user(movie_name, update.message)

    async def handle_group_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        if update.effective_chat.id != PRIVATE_GROUP_ID:
            return

        if not update.message.reply_to_message:
            return

        replied_text = update.message.reply_to_message.text or ""

        if not replied_text.startswith(SEARCH_PREFIX):
            return

        movie_name = replied_text.replace(SEARCH_PREFIX, "").strip().lower()

        await self._forward_file_to_user(movie_name, update.message)

    async def _forward_file_to_user(self, movie_name, group_message):

        for user_id, requested_movie in list(self.pending_searches.items()):

            if requested_movie.lower() == movie_name:

                try:

                    await self.application.bot.forward_message(
                        chat_id=user_id,
                        from_chat_id=group_message.chat_id,
                        message_id=group_message.message_id
                    )

                    del self.pending_searches[user_id]
                    self.group_message_ids.pop(movie_name, None)

                    logger.info(f"Sent {movie_name} to user {user_id}")

                except Exception as e:

                    logger.error(f"Forward failed: {e}")

                break


async def cleanup_old_searches(bot_instance):

    while True:

        try:

            await asyncio.sleep(300)

            expired_users = list(bot_instance.pending_searches.keys())

            for uid in expired_users:

                try:
                    await bot_instance.application.bot.send_message(
                        uid,
                        "⏰ Search expired. Try again."
                    )
                except:
                    pass

                bot_instance.pending_searches.pop(uid, None)

        except Exception as e:
            logger.error(f"Cleanup error: {e}")


async def main():

    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN missing! Check Railway variables.")

    if not PRIVATE_GROUP_ID:
        logger.error("❌ PRIVATE_GROUP_ID missing!")

    logger.info("🚀 Starting Movie Bot...")
    logger.info(f"Group ID: {PRIVATE_GROUP_ID}")

    application = Application.builder().token(BOT_TOKEN).build()

    bot_instance = MovieBot(application)

    application.add_handler(CommandHandler("start", bot_instance.start))

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND,
                       bot_instance.handle_movie_search)
    )

    application.add_handler(
        MessageHandler(filters.Chat(chat_id=PRIVATE_GROUP_ID) & filters.TEXT,
                       bot_instance.handle_group_message)
    )

    application.add_handler(
        MessageHandler(filters.Chat(chat_id=PRIVATE_GROUP_ID) & filters.Document.ALL,
                       bot_instance.handle_group_document)
    )

    asyncio.create_task(cleanup_old_searches(bot_instance))

    def signal_handler(signum, frame):
        logger.info("Shutdown signal received")
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("✅ Bot running")

    async with lifespan(application):
        await application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())