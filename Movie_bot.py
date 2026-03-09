import asyncio
import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import time

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Railway Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
PRIVATE_GROUP_ID = int(os.getenv("PRIVATE_GROUP_ID"))  # Must be integer
SEARCH_PREFIX = "🔍 Searching: "

class MovieBot:
    def __init__(self, application):
        self.application = application
        self.pending_searches = {}
        self.group_message_ids = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🎬 *Movie Search Bot*\n\n"
            "Send me a movie name and I'll find it for you!\n"
            "Example: `Inception 2010`",
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_movie_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        movie_name = update.message.text.strip()
        
        self.pending_searches[user_id] = movie_name
        
        group_msg = await context.bot.send_message(
            chat_id=PRIVATE_GROUP_ID,
            text=f"{SEARCH_PREFIX}{movie_name}"
        )
        
        self.group_message_ids[movie_name.lower()] = group_msg.message_id
        
        await update.message.reply_text(
            f"🔎 Searching for *{movie_name}*...\n⏳ Waiting for file...", 
            parse_mode=ParseMode.MARKDOWN
        )

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
            
        if not update.message.reply_to_message or not update.message.reply_to_message.text:
            return
            
        replied_text = update.message.reply_to_message.text
        if not replied_text.startswith(SEARCH_PREFIX):
            return
            
        movie_name = replied_text.replace(SEARCH_PREFIX, "").strip().lower()
        await self._forward_file_to_user(movie_name, update.message)

    async def _forward_file_to_user(self, movie_name: str, group_message):
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
                    logger.info(f"✅ Sent {movie_name} to user {user_id}")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to send to {user_id}: {e}")
                break

async def cleanup_old_searches(bot_instance):
    while True:
        await asyncio.sleep(300)  # 5 min
        expired_users = list(bot_instance.pending_searches.keys())
        for uid in expired_users:
            try:
                await bot_instance.application.bot.send_message(uid, "⏰ Search expired. Try again!")
            except:
                pass
            bot_instance.pending_searches.pop(uid, None)

async def main():
    if not BOT_TOKEN or not PRIVATE_GROUP_ID:
        logger.error("❌ BOT_TOKEN and PRIVATE_GROUP_ID required!")
        return
    
    application = Application.builder().token(BOT_TOKEN).build()
    bot_instance = MovieBot(application)
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot_instance.start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_instance.handle_movie_search))
    application.add_handler(MessageHandler(filters.Chat(chat_id=PRIVATE_GROUP_ID) & filters.TEXT, bot_instance.handle_group_message))
    application.add_handler(MessageHandler(filters.Chat(chat_id=PRIVATE_GROUP_ID) & filters.Document.ALL, bot_instance.handle_group_document))
    
    # Start cleanup
    asyncio.create_task(cleanup_old_searches(bot_instance))
    
    logger.info("🚀 Movie Bot deployed on Railway!")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
