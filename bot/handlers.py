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
        "👋 <b>Welcome to Revolico Bot!</b>\n\n"
        "Este bot te permite buscar y recibir anuncios de Revolico directamente en Telegram.\n\n"
        "<b>¿Qué puedes hacer?</b>\n"
        "• Buscar anuncios por palabra clave\n"
        "• Recibir anuncios nuevos automáticamente cada 45 segundos\n"
        "• Gestionar usuarios autorizados (solo admin)\n"
        "• Ver la lista de usuarios autorizados\n"
        "• Hacer preguntas a la IA\n\n"
        "<b>Comandos disponibles:</b>\n"
        "  /start - Muestra este mensaje de bienvenida\n"
        "  /search &lt;palabra_clave&gt; - Inicia o reinicia la búsqueda continua de anuncios\n"
        "  /stopsearch - Detiene la búsqueda continua\n"
        "  /adduser - Añade un usuario autorizado (solo admin)\n"
        "  /showusers - Muestra los usuarios autorizados\n"
        "  /question &lt;pregunta&gt; - Haz una pregunta a la IA\n"
        "  /help - Muestra los comandos disponibles\n\n"
        "<i>Ejemplo: /search bicicleta</i>",
        parse_mode="HTML"
    )

def help_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Available commands: /start, /adduser, /showusers, /search, /help')

def search_command(update: Update, context: CallbackContext) -> None:
    """
    Inicia una búsqueda continua cada 45 segundos para la palabra clave dada.
    Si ya hay una búsqueda activa, la reemplaza con la nueva palabra clave.
    """
    global search_active, search_thread, current_keyword
    if context.args:
        keyword = ' '.join(context.args).strip()
        current_keyword = keyword
        if search_active:
            search_active = False
            if search_thread and search_thread.is_alive():
                search_thread.join(timeout=2)
        search_active = True
        update.message.reply_text(f'🔍 Búsqueda continua iniciada para: "{keyword}". Usa /stopsearch para detenerla.')
        def loop():
            chat_id = update.effective_chat.id
            while search_active:
                try:
                    get_main_ads(None, keyword, chat_id=chat_id, context=context, on_new_ad=on_new_ad_telegram)
                except Exception:
                    pass
                for _ in range(45):
                    if not search_active:
                        break
                    time.sleep(1)
        search_thread = threading.Thread(target=loop, daemon=True)
        search_thread.start()
    else:
        update.message.reply_text('Por favor, usa el comando así: /search <palabra_clave>')

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

search_handler = CommandHandler('search', search_command)

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