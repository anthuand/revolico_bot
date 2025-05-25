"""
Bot Handlers Module
------------------
Efficient Telegram bot command and message handlers for user interaction and ad searching.
"""

from telegram import Update, ChatAction
from telegram.ext import CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackContext
from scraper.revolico import get_main_ads
from .auth import add_user_handler, user_received_handler, show_user_handler
import threading
import time
from utils.groq_client import general_response_llm

WAITING_FOR_KEYWORD = 1
search_active = False
current_keyword = None
search_thread = None

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "👋 Welcome to *Revolico Bot*!\n\n"
        "This bot lets you search and receive Revolico ads directly in Telegram.\n\n"
        "🔹 *What can you do?*\n"
        "• Search ads by filters (coming soon)\n"
        "• Manage authorized users (admin only)\n"
        "• View the list of authorized users\n"
        "• Get help about commands\n\n"
        "🔸 *Available commands:*\n"
        "  /start - Show this welcome message\n"
        "  /help - Show help and available commands\n"
        "  /adduser - Add an authorized user (admin only)\n"
        "  /showusers - View authorized users\n",
        parse_mode="Markdown"
    )

def help_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Available commands: /start, /adduser, /showusers, /search, /help')

def search_command(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('Please enter the keyword or product you want to search for:')
    return WAITING_FOR_KEYWORD

def receive_keyword(update: Update, context: CallbackContext) -> int:
    global current_keyword
    current_keyword = update.message.text.strip()
    update.message.reply_text(f'Keyword saved: "{current_keyword}". Use /startsearch to begin searching.')
    return ConversationHandler.END

def startsearch_command(update: Update, context: CallbackContext) -> None:
    global search_active, search_thread, current_keyword
    if not current_keyword:
        update.message.reply_text('You must first provide a keyword using /search.')
        return
    if search_active:
        update.message.reply_text('Search is already active.')
        return
    search_active = True
    update.message.reply_text(f'🔍 Starting continuous search for: "{current_keyword}". Use /stopsearch to stop.')
    search_thread = threading.Thread(target=search_loop, args=(update, context), daemon=True)
    search_thread.start()

def stopsearch_command(update: Update, context: CallbackContext) -> None:
    global search_active
    if not search_active:
        update.message.reply_text('No active search to stop.')
        return
    search_active = False
    update.message.reply_text('⏹️ Search stopped.')

def on_new_ad_telegram(ad: dict, chat_id: int, context: CallbackContext) -> None:
    message = (
        f"<b>{ad['title']}</b>\n"
        f"<b>Price:</b> {ad['price']}\n"
        f"<b>Location:</b> {ad['location']}\n"
        f"<b>Date:</b> {ad['date']}\n"
        f"<b>Description:</b> {ad['description']}\n"
        f"<b>Link:</b> <a href='https://www.revolico.com{ad['url']}'>View ad</a>"
    )
    if ad['photo']:
        try:
            context.bot.send_photo(chat_id, ad['photo'], caption=message, parse_mode="HTML")
        except Exception:
            context.bot.send_message(chat_id, message, parse_mode="HTML")
    else:
        context.bot.send_message(chat_id, message, parse_mode="HTML")

def search_loop(update: Update, context: CallbackContext) -> None:
    global search_active, current_keyword
    chat_id = update.effective_chat.id
    while search_active:
        try:
            get_main_ads(None, current_keyword, chat_id=chat_id, context=context, on_new_ad=on_new_ad_telegram)
        except Exception:
            pass
        time.sleep(30)

search_handler = ConversationHandler(
    entry_points=[CommandHandler('search', search_command)],
    states={
        WAITING_FOR_KEYWORD: [MessageHandler(Filters.text & ~Filters.command, receive_keyword)]
    },
    fallbacks=[]
)

def question_command(update: Update, context: CallbackContext) -> None:
    question = ' '.join(context.args)
    if not question:
        update.message.reply_text('Please enter your question after the /question command.')
        return
    update.message.chat.send_action(action=ChatAction.TYPING)
    try:
        answer = general_response_llm(question)
        update.message.reply_text(answer)
    except Exception:
        update.message.reply_text('An error occurred while processing your question. Please try again later.')

question_handler = CommandHandler('question', question_command)

def llm_response(update: Update, context: CallbackContext) -> None:
    message = update.message.text
    if message.startswith('/'):
        return
    update.message.chat.send_action(action=ChatAction.TYPING)
    try:
        answer = general_response_llm(message)
        update.message.reply_text(answer)
    except Exception:
        update.message.reply_text('An error occurred while processing your message. Please try again later.')

llm_message_handler = MessageHandler(Filters.text & ~Filters.command, llm_response) 