import asyncio
import logging
import os
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PRIVATE_GROUP_ID = int(os.environ.get("PRIVATE_GROUP_ID", 0))
SEARCH_PREFIX = "🔍 Searching: "

print("DEBUG BOT_TOKEN:", BOT_TOKEN)
print("DEBUG PRIVATE_GROUP_ID:", PRIVATE_GROUP_ID)


class MovieBot:

    def __init__(self, application):
        self.application = application
        self.pending_searches = {}
        self.group_message_ids = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        await update.message.reply_text(
            "🎬 *Movie Search Bot*\n\n"
            "Send a movie name and I'll search it.\n"
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

        except Exception as e:

            logger.error(f"Group error: {e}")
            await update.message.reply_text("❌ Cannot access group.")

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

                    del self.pending_searches[user_id]
                    self.group_message_ids.pop(movie_name, None)

                except Exception as e:
                    logger.error(f"Forward error: {e}")

                break


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


def main():

    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN missing!")
        return

    if not PRIVATE_GROUP_ID:
        logger.error("❌ PRIVATE_GROUP_ID missing!")
        return

    logger.info("🚀 Starting Movie Bot")

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

    asyncio.get_event_loop().create_task(cleanup_old_searches(bot))

    logger.info("✅ Bot running")

    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()