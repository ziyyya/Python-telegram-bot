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

# Environment variables - STRICT validation
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PRIVATE_GROUP_ID = os.environ.get("PRIVATE_GROUP_ID")

print("🔍 DEBUG - Raw BOT_TOKEN length:", len(BOT_TOKEN) if BOT_TOKEN else "MISSING")
print("🔍 DEBUG - Raw PRIVATE_GROUP_ID:", PRIVATE_GROUP_ID)

if not BOT_TOKEN:
    print("❌ CRITICAL: BOT_TOKEN is missing!")
    sys.exit(1)

if len(BOT_TOKEN) != 46 or not BOT_TOKEN.startswith(('1', '2', '3', '4')):
    print(f"❌ CRITICAL: Invalid BOT_TOKEN (len={len(BOT_TOKEN)}, starts with '{BOT_TOKEN[:10] if BOT_TOKEN else 'None'}')!")
    sys.exit(1)

try:
    PRIVATE_GROUP_ID = int(PRIVATE_GROUP_ID)
    if PRIVATE_GROUP_ID >= 0:
        print(f"❌ CRITICAL: PRIVATE_GROUP_ID must be negative (got {PRIVATE_GROUP_ID})!")
        sys.exit(1)
    print(f"✅ PRIVATE_GROUP_ID validated: {PRIVATE_GROUP_ID}")
except:
    print("❌ CRITICAL: Invalid PRIVATE_GROUP_ID!")
    sys.exit(1)

SEARCH_PREFIX = "🔍 Searching: "
print("✅ Env vars validated - starting bot...")

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
            print(f"✅ Search posted to group: {movie_name}")
        except Exception as e:
            logger.error(f"Group post failed: {e}")
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
        if update.effective_chat.id != PRIVATE_GROUP_ID or not update.message.reply_to_message:
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
                    print(f"✅ File forwarded to user {user_id}")
                    del self.pending_searches[user_id]
                    self.group_message_ids.pop(movie_name, None)
                except Exception as e:
                    logger.error(f"Forward failed: {e}")
                break

async def cleanup_old_searches(bot_instance):
    """Cleanup expired searches every 5 minutes"""
    while True:
        await asyncio.sleep(300)
        expired = [uid for uid in bot_instance.pending_searches]
        for uid in expired:
            try:
                await bot_instance.application.bot.send_message(uid, "⏰ Search expired. Try again.")
            except:
                pass
            bot_instance.pending_searches.pop(uid, None)

def main():
    print("🚀 Building Application...")
    
    # This is where it was failing - now fully validated above
    application = Application.builder().token(BOT_TOKEN).build()
    
    bot_instance = MovieBot(application)

    # Handlers
    application.add_handler(CommandHandler("start", bot_instance.start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_instance.handle_movie_search))
    application.add_handler(MessageHandler(filters.Chat(PRIVATE_GROUP_ID) & filters.TEXT, bot_instance.handle_group_message))
    application.add_handler(MessageHandler(filters.Chat(PRIVATE_GROUP_ID) & filters.Document.ALL, bot_instance.handle_group_document))

    # Background cleanup
    asyncio.create_task(cleanup_old_searches(bot_instance))

    print("✅ Bot fully operational!")
    logger.info("Bot started - polling...")

    # Graceful shutdown for Railway
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()