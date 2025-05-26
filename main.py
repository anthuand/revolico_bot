import logging
from emoji import emojize
import requests # Keep for now, though not directly used in this version after scraper changes
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update, ChatAction
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackQueryHandler, \
    CallbackContext
import db # db.py is expected to be in the same directory
import scraper # scraper.py is expected to be in the same directory
import os
import time
import threading
from datetime import datetime
import pytz
import re # For parsing user IDs

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
TOKEN = os.getenv('TOKEN')
if not TOKEN:
    logger.error("Telegram Bot TOKEN not found in environment variables!")
    exit()

DEFAULT_AUTHORIZED_USER_IDS = ['1122914981'] # Default if env var is not set
AUTHORIZED_USER_IDS_STR = os.getenv('AUTHORIZED_USER_IDS', ",".join(DEFAULT_AUTHORIZED_USER_IDS))
AUTHORIZED_USER_IDS = [uid.strip() for uid in AUTHORIZED_USER_IDS_STR.split(',')]

CHANNEL_ID_STR = os.getenv('TELEGRAM_CHANNEL_ID') # e.g., "-1001598585439"
CHANNEL_ID = int(CHANNEL_ID_STR) if CHANNEL_ID_STR else None
if not CHANNEL_ID:
    logger.warning("TELEGRAM_CHANNEL_ID not set in environment. Will only send to user if not set.")


# --- Bot State Management ---
class BotState:
    def __init__(self):
        self.search_thread_running = False
        self.stop_search_flag = False
        self.search_thread = None

# Conversation states for adding a filter
ASK_DEPARTMENT, ASK_PALABRA_CLAVE, ASK_PRECIO_MIN, ASK_PRECIO_MAX, EDIT_FILTER_CHOICE, PROCESS_FILTER_VALUE = range(6)


# --- Authentication ---
def is_authorized(update: Update) -> bool:
    user_id = str(update.effective_user.id)
    if user_id in AUTHORIZED_USER_IDS:
        return True
    logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
    update.message.reply_text('Lo siento, no tienes permiso para usar este bot.')
    return False

# --- User Management (Basic) ---
def add_user_command(update: Update, context: CallbackContext):
    if str(update.effective_user.id) != AUTHORIZED_USER_IDS[0]: # Simple check: only first authorized user is admin
        update.message.reply_text('No tienes permiso para agregar usuarios.')
        return
    
    if not context.args:
        update.message.reply_text('Por favor, proporciona el ID del usuario a agregar. Ejemplo: /add_user 123456789')
        return

    new_user_id = context.args[0].strip()
    if not re.match(r"^\d+$", new_user_id):
        update.message.reply_text(f"ID de usuario '{new_user_id}' inválido. Debe ser numérico.")
        return

    if new_user_id not in AUTHORIZED_USER_IDS:
        AUTHORIZED_USER_IDS.append(new_user_id)
        # Note: This change is in-memory. For persistence, update the env var or a config file.
        update.message.reply_text(f'Usuario {new_user_id} añadido. Usuarios autorizados actuales: {", ".join(AUTHORIZED_USER_IDS)}')
        logger.info(f"User {new_user_id} added by {update.effective_user.id}. Current authorized users: {AUTHORIZED_USER_IDS}")
    else:
        update.message.reply_text(f'El usuario {new_user_id} ya está autorizado.')

def show_users_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    update.message.reply_text(f'Usuarios autorizados: {", ".join(AUTHORIZED_USER_IDS)}')

# --- Scraper Thread Function ---
def buscar_thread_function(bot_state: BotState, bot: CallbackContext.bot, main_chat_id: int):
    logger.info("Scraper thread started.")
    thread_db_conn = None
    driver = None

    try:
        thread_db_conn = db.get_db_connection()
        if not thread_db_conn:
            logger.error("Scraper thread: Failed to get DB connection. Exiting.")
            bot_state.search_thread_running = False
            return

        # Initialize WebDriver for this thread
        driver = scraper.get_webdriver_instance()
        if not driver:
            logger.error("Scraper thread: Failed to get WebDriver instance. Exiting.")
            bot_state.search_thread_running = False
            db.close_db_connection(thread_db_conn)
            return
        
        # Ensure anuncios table exists (it drops and recreates)
        # This means only ads from the current run will be processed for notification.
        db.crear_tabla_anuncio(thread_db_conn)


        while not bot_state.stop_search_flag:
            logger.info("Scraper thread: Starting new search cycle.")
            active_filters = db.obtener_filtros(thread_db_conn)
            if not active_filters:
                logger.info("Scraper thread: No active filters. Sleeping for 60 seconds.")
                time.sleep(60)
                continue

            for filtro_row in active_filters:
                if bot_state.stop_search_flag: break
                
                _, dep, palabra_clave, precio_min, precio_max, provincia, municipio, fotos_str = filtro_row
                fotos = fotos_str.lower() == 'true' # Convert string to boolean

                logger.info(f"Scraper thread: Processing filter: palabra_clave='{palabra_clave}', departamento='{dep}'")
                
                # scraper.buscar_anuncios now handles its own pagination and calls procesar_y_guardar_anuncios
                # procesar_y_guardar_anuncios in scraper.py calls db.insertar_anuncio
                # We pass the thread-specific db_conn to scraper functions that need it.
                
                # Modify scraper.py's procesar_y_guardar_anuncios to accept db_conn
                # For now, assuming scraper.buscar_anuncios is adapted to use a passed db_conn for its calls
                # to functions that eventually hit db.insertar_anuncio
                
                # This is a conceptual change: scraper.py's functions that interact with DB
                # (like procesar_y_guardar_anuncios) must now accept `thread_db_conn`.
                # The current scraper.py does not do this. This is a required modification in scraper.py.
                # For now, I will proceed as if scraper.procesar_y_guardar_anuncios is adapted.
                # A simplified call, assuming `buscar_anuncios` handles passing `thread_db_conn` down:
                scraper.buscar_anuncios(driver,
                                        db_conn=thread_db_conn, # This param needs to be added to scraper.py functions
                                        departamento=dep,
                                        palabra_clave=palabra_clave,
                                        precio_min=precio_min,
                                        precio_max=precio_max,
                                        provincia=provincia,
                                        municipio=municipio,
                                        fotos=fotos,
                                        max_pages=2) # Limit pages for testing/politeness

                logger.info("Scraper thread: Checking for unnotified ads...")
                unnotified_ads = db.obtener_anuncios_no_notificados(thread_db_conn)
                
                for ad_row in unnotified_ads:
                    if bot_state.stop_search_flag: break
                    ad_id, ad_url, titulo, precio, descripcion, fecha_anuncio, ubicacion, foto_info_db, _ = ad_row
                    
                    # Fetch contact details for the new ad
                    # This requires scraper.py to be adapted if it doesn't take `driver`
                    # `obtener_contacto` in original main.py was `obtener_contacto(url)`
                    # `scraper.obtener_contacto_de_anuncio(driver, ad_url)` is the new one
                    contacto_nombre, telefono, email = scraper.obtener_contacto_de_anuncio(driver, ad_url)

                    dt = datetime.now(pytz.timezone('Cuba')) # Consider if fecha_anuncio is more relevant
                    hora_actual = dt.strftime('%Y-%m-%d a las %H:%M:%S')

                    mensaje = (
                        f"#{palabra_clave.replace(' ', '_')} #{dep}\n"
                        f"<b>{titulo}</b>\n\n"
                        f"Precio: {precio}\n"
                        f"Descripción: {descripcion[:200]}...\n" # Truncate description
                        f"Fecha del Anuncio: {fecha_anuncio}\n" # This is from the ad itself
                        f"Ubicación: {ubicacion}\n"
                        f"Visto: {hora_actual}\n\n"
                        f"Contacto: {contacto_nombre}\n"
                        f"Teléfono: {telefono}\n"
                        f"Email: {email}\n"
                    )
                    
                    inline_button = InlineKeyboardButton("Ver Anuncio", url=ad_url)
                    markup = InlineKeyboardMarkup([[inline_button]])

                    try:
                        # Send to main user who initiated search (or a default admin/channel)
                        bot.send_message(chat_id=main_chat_id, text=mensaje, reply_markup=markup, parse_mode="HTML")
                        logger.info(f"Sent new ad notification for '{titulo}' to chat ID {main_chat_id}")
                        
                        # Optionally send to a channel if CHANNEL_ID is configured
                        if CHANNEL_ID and str(main_chat_id) != str(CHANNEL_ID): # Avoid double sending if main_chat_id is channel
                           bot.send_message(chat_id=CHANNEL_ID, text=mensaje, reply_markup=markup, parse_mode="HTML")
                           logger.info(f"Sent new ad notification for '{titulo}' to channel ID {CHANNEL_ID}")

                        db.marcar_anuncio_como_notificado(thread_db_conn, ad_id)
                    except Exception as e_send:
                        logger.error(f"Error sending Telegram message for ad ID {ad_id}", exc_info=True)
                    
                    time.sleep(random.uniform(2, 5)) # Delay between sending messages

                if not active_filters: time.sleep(random.uniform(5,10)) # Small delay if no ads from this filter
            
            logger.info(f"Scraper thread: Cycle finished. Sleeping for {60*5} seconds.")
            time.sleep(60 * 5) # Wait 5 minutes before next full cycle

    except Exception as e:
        logger.error(f"Scraper thread: Unhandled exception: {e}", exc_info=True)
        bot.send_message(chat_id=main_chat_id, text=f"El hilo de búsqueda encontró un error y se detuvo: {e}")
    finally:
        if driver:
            scraper.close_webdriver() # Ensure scraper's global driver instance is closed
        if thread_db_conn:
            db.close_db_connection(thread_db_conn)
        bot_state.search_thread_running = False
        logger.info("Scraper thread stopped and cleaned up.")


# --- Telegram Command Handlers ---
def start_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    update.message.reply_text('¡Hola! Soy tu bot de Revolico. Usa /add para añadir un filtro y /start_search para comenzar a buscar.')

def start_search_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    bot_state: BotState = context.bot_data['bot_state']

    if bot_state.search_thread_running:
        update.message.reply_text('La búsqueda ya está en ejecución.')
        return

    bot_state.stop_search_flag = False
    bot_state.search_thread_running = True
    # Pass context.bot for sending messages from thread, and user's chat_id for replies
    bot_state.search_thread = threading.Thread(target=buscar_thread_function, args=(bot_state, context.bot, update.message.chat_id))
    bot_state.search_thread.start()
    update.message.reply_text('Búsqueda iniciada. Usar /stop_search para detener.')
    logger.info(f"Search started by user {update.effective_user.id}")

def stop_search_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    bot_state: BotState = context.bot_data['bot_state']

    if not bot_state.search_thread_running:
        update.message.reply_text('La búsqueda no está en ejecución.')
        return

    bot_state.stop_search_flag = True
    if bot_state.search_thread:
        bot_state.search_thread.join(timeout=10) # Wait for thread to finish
    bot_state.search_thread_running = False # Ensure it's marked as not running
    update.message.reply_text('Señal de detención enviada. El hilo de búsqueda se detendrá pronto.')
    logger.info(f"Search stop requested by user {update.effective_user.id}")


def status_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    bot_state: BotState = context.bot_data['bot_state']
    status_msg = "En ejecución" if bot_state.search_thread_running else "Detenido"
    update.message.reply_text(f'Estado de la búsqueda: {status_msg}')

# --- Add Filter Conversation ---
# Predefined keyboard markups (can be module level)
DEPARTAMENTOS_KEYBOARD = [
    [InlineKeyboardButton("Compra-Venta", callback_data='dep_compra-venta'), InlineKeyboardButton("Autos", callback_data='dep_autos')],
    [InlineKeyboardButton("Vivienda", callback_data='dep_vivienda'), InlineKeyboardButton("Empleos", callback_data='dep_empleos')],
    [InlineKeyboardButton("Servicios", callback_data='dep_servicios'), InlineKeyboardButton("Computadoras", callback_data='dep_computadoras')],
    [InlineKeyboardButton("Cancelar", callback_data='addfilter_cancel')],
]
MARKUP_DEPARTAMENTOS = InlineKeyboardMarkup(DEPARTAMENTOS_KEYBOARD)

EDIT_FILTER_KEYBOARD = [
    [InlineKeyboardButton("Palabra Clave", callback_data='edit_palabra_clave')],
    [InlineKeyboardButton("Precio Mín", callback_data='edit_precio_min'), InlineKeyboardButton("Precio Máx", callback_data='edit_precio_max')],
    [InlineKeyboardButton("Provincia", callback_data='edit_provincia'), InlineKeyboardButton("Fotos (Sí/No)", callback_data='edit_fotos')],
    [InlineKeyboardButton("Guardar Filtro", callback_data='addfilter_done'), InlineKeyboardButton("Cancelar", callback_data='addfilter_cancel')],
]
MARKUP_EDIT_FILTER = InlineKeyboardMarkup(EDIT_FILTER_KEYBOARD)


def add_filter_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    context.user_data['current_filter_parts'] = {} # Initialize filter construction
    update.message.reply_text('Selecciona el departamento para tu nuevo filtro:', reply_markup=MARKUP_DEPARTAMENTOS)
    return ASK_DEPARTMENT

def ask_department_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    department_choice = query.data.split('_')[1]
    context.user_data['current_filter_parts']['departamento'] = department_choice
    query.edit_message_text(text=f"Departamento: {department_choice}. Ahora edita los demás campos:", reply_markup=MARKUP_EDIT_FILTER)
    return EDIT_FILTER_CHOICE

def edit_filter_choice_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    choice = query.data.split('_')[1] # e.g., "palabra_clave" from "edit_palabra_clave"
    context.user_data['filter_field_to_edit'] = choice
    
    field_prompts = {
        "palabra_clave": "Por favor, envía la palabra clave para la búsqueda.",
        "precio_min": "Envía el precio mínimo (solo números).",
        "precio_max": "Envía el precio máximo (solo números).",
        "provincia": "Envía la provincia (ej: La Habana). Por defecto es 'La Habana'.",
        "fotos": "Busca anuncios con fotos? Envía 'Si' o 'No'."
    }
    prompt = field_prompts.get(choice, "Valor desconocido. Cancela y reintenta.")
    query.edit_message_text(text=prompt)
    return PROCESS_FILTER_VALUE

def process_filter_value_message(update: Update, context: CallbackContext):
    user_text = update.message.text.strip()
    field_to_edit = context.user_data.get('filter_field_to_edit')
    
    if not field_to_edit:
        update.message.reply_text("Error interno. Por favor, cancela y reintenta.", reply_markup=MARKUP_EDIT_FILTER)
        return EDIT_FILTER_CHOICE

    current_filter = context.user_data.get('current_filter_parts', {})

    if field_to_edit in ["precio_min", "precio_max"]:
        if not user_text.isdigit():
            update.message.reply_text("El precio debe ser numérico. Intenta de nuevo o edita otro campo.", reply_markup=MARKUP_EDIT_FILTER)
            return EDIT_FILTER_CHOICE 
        current_filter[field_to_edit] = int(user_text)
    elif field_to_edit == "fotos":
        current_filter[field_to_edit] = user_text.lower() in ['si', 'sí', 'true', 'yes']
    else:
        current_filter[field_to_edit] = user_text
    
    context.user_data['current_filter_parts'] = current_filter
    # Build summary of current filter
    summary_lines = [f"{k.replace('_', ' ').capitalize()}: {v}" for k, v in current_filter.items()]
    summary_text = "Filtro actual:\n" + "\n".join(summary_lines) + "\n\nPuedes seguir editando o guardar."
    update.message.reply_text(summary_text, reply_markup=MARKUP_EDIT_FILTER)
    return EDIT_FILTER_CHOICE

def add_filter_done_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    db_conn = context.bot_data['db_conn']
    current_filter = context.user_data.get('current_filter_parts')

    if not current_filter or not current_filter.get('departamento') or not current_filter.get('palabra_clave'):
        query.edit_message_text("Faltan campos obligatorios (departamento, palabra clave). Cancela o continúa editando.", reply_markup=MARKUP_EDIT_FILTER)
        return EDIT_FILTER_CHOICE

    # Set defaults for optional fields if not provided
    dep = current_filter['departamento']
    p_clave = current_filter['palabra_clave']
    pr_min = current_filter.get('precio_min')
    pr_max = current_filter.get('precio_max')
    prov = current_filter.get('provincia', 'La Habana') # Default province
    fotos = current_filter.get('fotos', False) # Default fotos

    try:
        db.insertar_filtro(db_conn, dep, p_clave, pr_min, pr_max, prov, None, fotos) # Municipio not handled by this simplified UI
        query.edit_message_text("¡Filtro guardado exitosamente!")
        logger.info(f"Filter saved by user {update.effective_user.id}: {current_filter}")
    except Exception as e:
        logger.error(f"Error saving filter: {e}", exc_info=True)
        query.edit_message_text("Error al guardar el filtro.")
    
    context.user_data.pop('current_filter_parts', None)
    context.user_data.pop('filter_field_to_edit', None)
    return ConversationHandler.END

def add_filter_cancel_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    query.edit_message_text("Creación de filtro cancelada.")
    context.user_data.pop('current_filter_parts', None)
    context.user_data.pop('filter_field_to_edit', None)
    return ConversationHandler.END

# --- Other Commands ---
def show_filters_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    db_conn = context.bot_data['db_conn']
    filters_list = db.obtener_filtros(db_conn)
    if not filters_list:
        update.message.reply_text("No hay filtros activos.")
        return
    
    response = "Filtros activos:\n\n"
    for f_id, dep, pk, pmin, pmax, prov, mun, фото_str in filters_list:
        response += (f"ID: {f_id}\nDepartamento: {dep}\nPalabra Clave: {pk}\n"
                     f"Precio Mín: {pmin if pmin else '-'}\nPrecio Máx: {pmax if pmax else '-'}\n"
                     f"Provincia: {prov if prov else '-'}\nFotos: {'Sí' if фото_str.lower() == 'true' else 'No'}\n---\n")
    update.message.reply_text(response)

def delete_filter_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    db_conn = context.bot_data['db_conn']
    filters_list = db.obtener_filtros(db_conn)
    if not filters_list:
        update.message.reply_text("No hay filtros para borrar.")
        return

    keyboard = []
    for f_id, _, pk, *rest in filters_list:
        keyboard.append([InlineKeyboardButton(f"ID: {f_id} - \"{pk[:20]}\"", callback_data=f"del_{f_id}")])
    keyboard.append([InlineKeyboardButton("Borrar Todos los Filtros", callback_data="del_ALL")])
    keyboard.append([InlineKeyboardButton("Cancelar", callback_data="del_cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Selecciona el filtro a borrar:", reply_markup=reply_markup)

def delete_filter_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    action_data = query.data
    db_conn = context.bot_data['db_conn']

    if action_data == "del_ALL":
        db.eliminar_todos_los_filtros(db_conn)
        query.edit_message_text("Todos los filtros han sido eliminados.")
        logger.info(f"All filters deleted by user {update.effective_user.id}")
    elif action_data == "del_cancel":
        query.edit_message_text("Operación cancelada.")
    elif action_data.startswith("del_"):
        try:
            filter_id_to_delete = int(action_data.split('_')[1])
            db.eliminar_filtro(db_conn, filter_id_to_delete)
            query.edit_message_text(f"Filtro ID {filter_id_to_delete} eliminado.")
            logger.info(f"Filter ID {filter_id_to_delete} deleted by user {update.effective_user.id}")
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing filter ID from callback data '{action_data}': {e}")
            query.edit_message_text("Error al procesar la solicitud de borrado.")
            
def help_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    help_text = (
        "/start - Inicia la interacción con el bot.\n"
        "/add - Añade un nuevo filtro de búsqueda.\n"
        "/show - Muestra los filtros activos.\n"
        "/delete - Elimina un filtro existente.\n"
        "/start_search - Inicia la búsqueda de anuncios (en segundo plano).\n"
        "/stop_search - Detiene la búsqueda de anuncios.\n"
        "/status - Muestra el estado actual de la búsqueda.\n"
        "/show_users - Muestra los IDs de usuarios autorizados.\n"
        "/add_user <ID> - (Admin) Añade un nuevo usuario autorizado.\n"
        "/help - Muestra este mensaje de ayuda."
    )
    update.message.reply_text(help_text)

def error_handler(update: object, context: CallbackContext) -> None:
    """Log Errors caused by Updates."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        # Try to send a message back to the user if possible
        try:
            update.effective_message.reply_text("Ocurrió un error procesando tu solicitud. Intenta de nuevo más tarde.")
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")

def main():
    """Start the bot."""
    if not TOKEN: # Already checked, but good for safety
        return

    # Initialize bot state and DB connection
    bot_state = BotState()
    main_db_conn = db.get_db_connection()

    if not main_db_conn:
        logger.error("Failed to establish main database connection. Exiting.")
        return

    # Create tables if they don't exist using the main connection
    db.crear_tabla_filtros(main_db_conn)
    # db.crear_tabla_anuncio(main_db_conn) # The scraper thread will manage its anuncios table

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Store state and main DB connection in bot_data for access in handlers
    dp.bot_data['bot_state'] = bot_state
    dp.bot_data['db_conn'] = main_db_conn
    
    # Conversation handler for adding filters
    add_filter_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add', add_filter_command)],
        states={
            ASK_DEPARTMENT: [CallbackQueryHandler(ask_department_callback, pattern='^dep_')],
            EDIT_FILTER_CHOICE: [
                CallbackQueryHandler(edit_filter_choice_callback, pattern='^edit_'),
                CallbackQueryHandler(add_filter_done_callback, pattern='^addfilter_done$'),
            ],
            PROCESS_FILTER_VALUE: [MessageHandler(Filters.text & ~Filters.command, process_filter_value_message)],
        },
        fallbacks=[
            CallbackQueryHandler(add_filter_cancel_callback, pattern='^addfilter_cancel$'),
            CommandHandler('cancel', lambda u,c: u.message.reply_text("Operación cancelada.") or ConversationHandler.END) # Allow /cancel command
        ],
        map_to_parent={ # Allow returning to main interaction level if needed
            ConversationHandler.END: ConversationHandler.END
        }
    )

    dp.add_handler(add_filter_conv_handler)

    # Command Handlers
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("start_search", start_search_command))
    dp.add_handler(CommandHandler("stop_search", stop_search_command))
    dp.add_handler(CommandHandler("status", status_command))
    dp.add_handler(CommandHandler("show", show_filters_command))
    dp.add_handler(CommandHandler("delete", delete_filter_command))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("add_user", add_user_command))
    dp.add_handler(CommandHandler("show_users", show_users_command))

    # Callback Query Handlers (for filter deletion)
    dp.add_handler(CallbackQueryHandler(delete_filter_callback, pattern='^del_'))
    
    # Error Handler
    dp.add_error_handler(error_handler)

    # Start polling
    updater.start_polling()
    logger.info("Bot started polling.")
    updater.idle()

    # Cleanup on exit
    logger.info("Bot shutting down...")
    bot_state.stop_search_flag = True # Signal thread to stop
    if bot_state.search_thread and bot_state.search_thread.is_alive():
        logger.info("Waiting for search thread to complete...")
        bot_state.search_thread.join(timeout=15)
    if main_db_conn:
        db.close_db_connection(main_db_conn)
    logger.info("Bot shutdown complete.")


if __name__ == '__main__':
    main()
```
