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
from threading import Thread, Lock
from utils.logger import setup_logger
import datetime

search_states = {}
search_states_lock = Lock()
logger = setup_logger('revolico_bot')

# Tiempo máximo de inactividad para limpiar estados (en segundos)
STATE_CLEANUP_INTERVAL = 3600  # 1 hora

class SearchState:
    def __init__(self, keyword=None):
        self.active = False
        self.keyword = keyword
        self.thread = None
        self.last_activity = datetime.datetime.utcnow()

    def stop(self):
        self.active = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        self.thread = None
        self.last_activity = datetime.datetime.utcnow()

    def touch(self):
        self.last_activity = datetime.datetime.utcnow()


def get_or_create_state(chat_id):
    with search_states_lock:
        if chat_id not in search_states:
            search_states[chat_id] = SearchState()
        state = search_states[chat_id]
        state.touch()
        return state

def cleanup_old_states():
    now = datetime.datetime.utcnow()
    with search_states_lock:
        to_delete = [cid for cid, state in search_states.items()
                     if not state.active and (now - state.last_activity).total_seconds() > STATE_CLEANUP_INTERVAL]
        for cid in to_delete:
            del search_states[cid]
        if to_delete:
            logger.info(f"Cleaned up {len(to_delete)} inactive chat states.")

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
    cleanup_old_states()
    chat_id = update.effective_chat.id
    state = get_or_create_state(chat_id)
    if context.args:
        keyword = ' '.join(context.args).strip()
        # Detener búsqueda previa si existe
        state.stop()
        state.keyword = keyword
        state.active = True
        update.message.reply_text(f'🔍 Búsqueda continua iniciada para: "{keyword}". Usa /stopsearch para detenerla.')
        def loop():
            while state.active:
                try:
                    get_main_ads(None, keyword, chat_id=chat_id, context=context, on_new_ad=on_new_ad_telegram)
                except Exception as e:
                    logger.error(f"Error in search thread for chat {chat_id}: {e}", exc_info=True)
                for _ in range(45):
                    if not state.active:
                        break
                    time.sleep(1)
        state.thread = Thread(target=loop, daemon=True)
        state.thread.start()
    else:
        update.message.reply_text('Por favor, usa el comando así: /search <palabra_clave>')

def receive_keyword(update: Update, context: CallbackContext) -> int:
    cleanup_old_states()
    chat_id = update.effective_chat.id
    state = get_or_create_state(chat_id)
    state.keyword = update.message.text.strip()
    update.message.reply_text(f'Keyword saved: "{state.keyword}". Use /startsearch to begin searching.')
    return ConversationHandler.END

def startsearch_command(update: Update, context: CallbackContext) -> None:
    cleanup_old_states()
    chat_id = update.effective_chat.id
    state = get_or_create_state(chat_id)
    if not state.keyword:
        update.message.reply_text('You must first provide a keyword using /search.')
        return
    if state.active:
        update.message.reply_text('Search is already active.')
        return
    state.active = True
    update.message.reply_text(f'🔍 Starting continuous search for: "{state.keyword}". Use /stopsearch to stop.')
    def loop():
        while state.active:
            try:
                get_main_ads(None, state.keyword, chat_id=chat_id, context=context, on_new_ad=on_new_ad_telegram)
            except Exception as e:
                logger.error(f"Error in search thread for chat {chat_id}: {e}", exc_info=True)
            for _ in range(45):
                if not state.active:
                    break
                time.sleep(1)
    state.thread = Thread(target=loop, daemon=True)
    state.thread.start()

def stopsearch_command(update: Update, context: CallbackContext) -> None:
    cleanup_old_states()
    chat_id = update.effective_chat.id
    state = get_or_create_state(chat_id)
    if not state.active:
        update.message.reply_text('No active search to stop.')
        return
    state.stop()
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
    # Obsoleto: la lógica ahora está en los métodos por chat
    pass

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