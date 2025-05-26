import logging
from emoji import emojize
import requests # Keep for now, though not directly used in this version after scraper changes
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update, ChatAction, ParseMode
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
ASK_DEPARTMENT, EDIT_FILTER_CHOICE, PROCESS_FILTER_VALUE = range(3) # Simplified state range for clarity


# --- Authentication ---
def is_authorized(update: Update) -> bool:
    user_id = str(update.effective_user.id)
    if user_id in AUTHORIZED_USER_IDS:
        return True
    logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
    if update.message:
        update.message.reply_text('Lo siento, no tienes permiso para usar este bot.')
    elif update.callback_query:
        update.callback_query.answer("No autorizado.", show_alert=True)
        update.callback_query.message.reply_text('Lo siento, no tienes permiso para usar este bot.')

    return False

# --- User Management (Basic) ---
def add_user_command(update: Update, context: CallbackContext):
    if str(update.effective_user.id) != AUTHORIZED_USER_IDS[0]: 
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

        driver = scraper.get_webdriver_instance()
        if not driver:
            logger.error("Scraper thread: Failed to get WebDriver instance. Exiting.")
            bot_state.search_thread_running = False
            if thread_db_conn: db.close_db_connection(thread_db_conn)
            return
        
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
                fotos = fotos_str.lower() == 'true' 

                logger.info(f"Scraper thread: Processing filter: palabra_clave='{palabra_clave}', departamento='{dep}'")
                
                scraper.buscar_anuncios(driver,
                                        db_conn=thread_db_conn,
                                        departamento=dep,
                                        palabra_clave=palabra_clave,
                                        precio_min=precio_min,
                                        precio_max=precio_max,
                                        provincia=provincia,
                                        municipio=municipio,
                                        fotos=fotos,
                                        max_pages=2) 

                logger.info("Scraper thread: Checking for unnotified ads...")
                unnotified_ads = db.obtener_anuncios_no_notificados(thread_db_conn)
                
                for ad_row in unnotified_ads:
                    if bot_state.stop_search_flag: break
                    ad_id, ad_url, titulo, precio, descripcion, fecha_anuncio, ubicacion, foto_info_db, _ = ad_row
                    
                    contacto_nombre, telefono, email = scraper.obtener_contacto_de_anuncio(driver, ad_url)

                    dt = datetime.now(pytz.timezone('Cuba')) 
                    hora_actual = dt.strftime('%Y-%m-%d a las %H:%M:%S')

                    mensaje = (
                        f"#{palabra_clave.replace(' ', '_')} #{dep}\n"
                        f"<b>{titulo}</b>\n\n"
                        f"Precio: {precio}\n"
                        f"Descripción: {descripcion[:200]}...\n" 
                        f"Fecha del Anuncio: {fecha_anuncio}\n" 
                        f"Ubicación: {ubicacion}\n"
                        f"Visto: {hora_actual}\n\n"
                        f"Contacto: {contacto_nombre}\n"
                        f"Teléfono: {telefono}\n"
                        f"Email: {email}\n"
                    )
                    
                    inline_button = InlineKeyboardButton("Ver Anuncio", url=ad_url)
                    markup = InlineKeyboardMarkup([[inline_button]])

                    try:
                        bot.send_message(chat_id=main_chat_id, text=mensaje, reply_markup=markup, parse_mode=ParseMode.HTML)
                        logger.info(f"Sent new ad notification for '{titulo}' to chat ID {main_chat_id}")
                        
                        if CHANNEL_ID and str(main_chat_id) != str(CHANNEL_ID): 
                           bot.send_message(chat_id=CHANNEL_ID, text=mensaje, reply_markup=markup, parse_mode=ParseMode.HTML)
                           logger.info(f"Sent new ad notification for '{titulo}' to channel ID {CHANNEL_ID}")

                        db.marcar_anuncio_como_notificado(thread_db_conn, ad_id)
                    except Exception as e_send:
                        logger.error(f"Error sending Telegram message for ad ID {ad_id}", exc_info=True)
                    
                    time.sleep(random.uniform(2, 5)) 

                if not unnotified_ads and active_filters : time.sleep(random.uniform(3,7)) # Shorter sleep if specific filter yielded no new ads
            
            logger.info(f"Scraper thread: Cycle finished. Sleeping for {60*5} seconds.")
            time.sleep(60 * 5) 

    except Exception as e:
        logger.error(f"Scraper thread: Unhandled exception: {e}", exc_info=True)
        try: # Attempt to notify the main user about the thread failure
            bot.send_message(chat_id=main_chat_id, text=f"⚠️ El hilo de búsqueda encontró un error crítico y se detuvo: {e}")
        except Exception as e_notify:
            logger.error(f"Scraper thread: Failed to notify user about critical error: {e_notify}")
    finally:
        if driver:
            scraper.close_webdriver() 
        if thread_db_conn:
            db.close_db_connection(thread_db_conn)
        bot_state.search_thread_running = False
        logger.info("Scraper thread stopped and cleaned up.")


# --- Telegram Command Handlers ---
def start_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    update.message.reply_text('¡Hola! 👋 Soy tu bot de Revolico. Estoy aquí para ayudarte a encontrar los anuncios que buscas.\n\n'
                              'Puedes usar /add para crear un nuevo filtro de búsqueda y luego /start_search para que comience a monitorear los anuncios por ti.\n\n'
                              'Usa /help para ver todos los comandos disponibles.')

def start_search_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    bot_state: BotState = context.bot_data['bot_state']

    if bot_state.search_thread_running:
        update.message.reply_text('⚙️ La búsqueda ya está en ejecución.')
        return

    bot_state.stop_search_flag = False
    bot_state.search_thread_running = True
    bot_state.search_thread = threading.Thread(target=buscar_thread_function, args=(bot_state, context.bot, update.message.chat_id), daemon=True)
    bot_state.search_thread.start()
    update.message.reply_text('🚀 Búsqueda iniciada. Te notificaré sobre nuevos anuncios.\nUsa /stop_search para detener.')
    logger.info(f"Search started by user {update.effective_user.id}")

def stop_search_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    bot_state: BotState = context.bot_data['bot_state']

    if not bot_state.search_thread_running:
        update.message.reply_text('ℹ️ La búsqueda no está en ejecución.')
        return

    bot_state.stop_search_flag = True
    # Thread join timeout is handled in main() during shutdown
    update.message.reply_text('🛑 Señal de detención enviada. El hilo de búsqueda se detendrá pronto.')
    logger.info(f"Search stop requested by user {update.effective_user.id}")


def status_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    bot_state: BotState = context.bot_data['bot_state']
    status_msg = "🟢 En ejecución" if bot_state.search_thread_running else "🔴 Detenido"
    update.message.reply_text(f'Estado de la búsqueda: {status_msg}')

# --- Add Filter Conversation ---
DEPARTAMENTOS_KEYBOARD = [
    [InlineKeyboardButton(emojize("🛍️ Compra-Venta"), callback_data='dep_compra-venta'), InlineKeyboardButton(emojize("🚗 Autos"), callback_data='dep_autos')],
    [InlineKeyboardButton(emojize("🏠 Vivienda"), callback_data='dep_vivienda'), InlineKeyboardButton(emojize("💼 Empleos"), callback_data='dep_empleos')],
    [InlineKeyboardButton(emojize("🛠️ Servicios"), callback_data='dep_servicios'), InlineKeyboardButton(emojize("💻 Computadoras"), callback_data='dep_computadoras')],
    [InlineKeyboardButton(emojize("❌ Cancelar"), callback_data='addfilter_cancel')],
]
MARKUP_DEPARTAMENTOS = InlineKeyboardMarkup(DEPARTAMENTOS_KEYBOARD)

EDIT_FILTER_KEYBOARD = [
    [InlineKeyboardButton(emojize("🔑 Palabra Clave"), callback_data='edit_palabra_clave')],
    [InlineKeyboardButton(emojize("💰 Precio Mín"), callback_data='edit_precio_min'), InlineKeyboardButton(emojize("💰 Precio Máx"), callback_data='edit_precio_max')],
    [InlineKeyboardButton(emojize("📍 Provincia"), callback_data='edit_provincia'), InlineKeyboardButton(emojize("📸 Fotos"), callback_data='edit_fotos')],
    [InlineKeyboardButton(emojize("💾 Guardar Filtro"), callback_data='addfilter_done'), InlineKeyboardButton(emojize("❌ Cancelar"), callback_data='addfilter_cancel')],
]
MARKUP_EDIT_FILTER = InlineKeyboardMarkup(EDIT_FILTER_KEYBOARD)


def add_filter_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    context.user_data['current_filter_parts'] = {} 
    update.message.reply_text('📋 Vamos a crear un nuevo filtro. Por favor, selecciona el departamento donde quieres buscar:', reply_markup=MARKUP_DEPARTAMENTOS)
    return ASK_DEPARTMENT

def ask_department_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    if not is_authorized(update): return ConversationHandler.END # double check auth on callback

    department_choice = query.data.split('dep_')[1]
    context.user_data['current_filter_parts']['departamento'] = department_choice
    query.edit_message_text(text=f"Departamento seleccionado: {department_choice.replace('-', ' ').capitalize()}.\n\nAhora puedes configurar los demás campos del filtro:", reply_markup=MARKUP_EDIT_FILTER)
    return EDIT_FILTER_CHOICE

def edit_filter_choice_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    if not is_authorized(update): return ConversationHandler.END

    choice = query.data.split('edit_')[1] 
    context.user_data['filter_field_to_edit'] = choice
    
    field_prompts = {
        "palabra_clave": "Por favor, envía la 🔑 palabra clave para la búsqueda.",
        "precio_min": "Envía el 💰 precio mínimo (solo números).",
        "precio_max": "Envía el 💰 precio máximo (solo números).",
        "provincia": "Envía la 📍 provincia (ej: La Habana). (Predeterminado: La Habana)",
        "fotos": "Busca anuncios con 📸 fotos? Envía 'Si' o 'No'. (Predeterminado: No)"
    }
    prompt = field_prompts.get(choice, "Opción desconocida. Por favor, cancela y reintenta.")
    query.edit_message_text(text=prompt)
    return PROCESS_FILTER_VALUE

def process_filter_value_message(update: Update, context: CallbackContext):
    if not is_authorized(update): return ConversationHandler.END
    user_text = update.message.text.strip()
    field_to_edit = context.user_data.get('filter_field_to_edit')
    
    if not field_to_edit:
        update.message.reply_text("⚠️ Error interno. Por favor, cancela (/cancel) y reintenta.", reply_markup=MARKUP_EDIT_FILTER)
        return EDIT_FILTER_CHOICE

    current_filter = context.user_data.get('current_filter_parts', {})

    if field_to_edit in ["precio_min", "precio_max"]:
        if not user_text.isdigit():
            update.message.reply_text("⚠️ El precio debe ser numérico. Intenta de nuevo o edita otro campo.", reply_markup=MARKUP_EDIT_FILTER)
            return EDIT_FILTER_CHOICE 
        current_filter[field_to_edit] = int(user_text)
    elif field_to_edit == "fotos":
        current_filter[field_to_edit] = user_text.lower() in ['si', 'sí', 's', 'true', 'yes', 'y']
    else: # palabra_clave, provincia
        current_filter[field_to_edit] = user_text
    
    context.user_data['current_filter_parts'] = current_filter
    
    summary_lines = []
    if 'departamento' in current_filter: summary_lines.append(f"**Departamento**: {current_filter['departamento'].replace('-', ' ').capitalize()}")
    if 'palabra_clave' in current_filter: summary_lines.append(f"**🔑 Palabra Clave**: {current_filter['palabra_clave']}")
    if 'precio_min' in current_filter: summary_lines.append(f"**💰 Precio Mín**: {current_filter['precio_min']}")
    if 'precio_max' in current_filter: summary_lines.append(f"**💰 Precio Máx**: {current_filter['precio_max']}")
    if 'provincia' in current_filter: summary_lines.append(f"**📍 Provincia**: {current_filter['provincia']}")
    if 'fotos' in current_filter: summary_lines.append(f"**📸 Fotos**: {'Sí' if current_filter['fotos'] else 'No'}")
    
    summary_text = "📝 Filtro actual:\n" + "\n".join(summary_lines) + "\n\nPuedes seguir editando o guardar."
    update.message.reply_text(summary_text, reply_markup=MARKUP_EDIT_FILTER, parse_mode=ParseMode.MARKDOWN)
    return EDIT_FILTER_CHOICE

def add_filter_done_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    if not is_authorized(update): return ConversationHandler.END

    db_conn = context.bot_data['db_conn']
    current_filter = context.user_data.get('current_filter_parts')

    if not current_filter or not current_filter.get('departamento') or not current_filter.get('palabra_clave'):
        query.edit_message_text("⚠️ Faltan campos obligatorios (departamento, palabra clave). Cancela o continúa editando.", reply_markup=MARKUP_EDIT_FILTER)
        return EDIT_FILTER_CHOICE

    dep = current_filter['departamento']
    p_clave = current_filter['palabra_clave']
    pr_min = current_filter.get('precio_min')
    pr_max = current_filter.get('precio_max')
    prov = current_filter.get('provincia', 'La Habana') 
    fotos = current_filter.get('fotos', False) 

    try:
        db.insertar_filtro(db_conn, dep, p_clave, pr_min, pr_max, prov, None, fotos) # Municipio not handled
        query.edit_message_text("✅ ¡Filtro guardado exitosamente!")
        logger.info(f"Filter saved by user {update.effective_user.id}: {current_filter}")
    except Exception as e:
        logger.error(f"Error saving filter for user {update.effective_user.id}: {e}", exc_info=True)
        query.edit_message_text("❌ Error al guardar el filtro.")
    
    context.user_data.pop('current_filter_parts', None)
    context.user_data.pop('filter_field_to_edit', None)
    return ConversationHandler.END

def add_filter_cancel_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    if not is_authorized(update): return ConversationHandler.END
    query.edit_message_text("❌ Creación de filtro cancelada.")
    context.user_data.pop('current_filter_parts', None)
    context.user_data.pop('filter_field_to_edit', None)
    return ConversationHandler.END

def cancel_command_in_conversation(update: Update, context: CallbackContext):
    if not is_authorized(update): return ConversationHandler.END
    update.message.reply_text("❌ Operación cancelada.")
    context.user_data.pop('current_filter_parts', None)
    context.user_data.pop('filter_field_to_edit', None)
    return ConversationHandler.END

# --- Other Commands ---
def show_filters_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    db_conn = context.bot_data['db_conn']
    filters_list = db.obtener_filtros(db_conn)
    if not filters_list:
        update.message.reply_text("ℹ️ No hay filtros activos.")
        return
    
    response = "📋 Filtros activos:\n\n"
    for f_id, dep, pk, pmin, pmax, prov, mun, fotos_str in filters_list:
        response += (f"🆔 *ID*: {f_id}\n"
                     f"🛍️ *Departamento*: {dep.replace('-', ' ').capitalize()}\n"
                     f"🔑 *Palabra Clave*: {pk}\n"
                     f"💰 *Precio Mín*: {pmin if pmin is not None else '-'}\n"
                     f"💰 *Precio Máx*: {pmax if pmax is not None else '-'}\n"
                     f"📍 *Provincia*: {prov if prov else '-'}\n"
                    #  f"🗺️ *Municipio*: {mun if mun else '-'}\n" # Municipio not currently editable via UI
                     f"📸 *Fotos*: {'Sí' if str(fotos_str).lower() == 'true' else 'No'}\n---\n")
    update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

def delete_filter_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    db_conn = context.bot_data['db_conn']
    filters_list = db.obtener_filtros(db_conn)
    if not filters_list:
        update.message.reply_text("ℹ️ No hay filtros para borrar.")
        return

    keyboard = []
    for f_id, _, pk, *rest in filters_list: # pk is palabra_clave
        keyboard.append([InlineKeyboardButton(f"🆔 {f_id} - \"{pk[:20]}...\"", callback_data=f"del_{f_id}")])
    keyboard.append([InlineKeyboardButton(emojize("🗑️ Borrar Todos los Filtros"), callback_data="del_ALL")])
    keyboard.append([InlineKeyboardButton(emojize("❌ Cancelar"), callback_data="del_cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("🗑️ Selecciona el filtro a borrar:", reply_markup=reply_markup)

def delete_filter_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    if not is_authorized(update): return

    action_data = query.data
    db_conn = context.bot_data['db_conn']

    if action_data == "del_ALL":
        db.eliminar_todos_los_filtros(db_conn)
        query.edit_message_text("🗑️ Todos los filtros han sido eliminados.")
        logger.info(f"All filters deleted by user {update.effective_user.id}")
    elif action_data == "del_cancel":
        query.edit_message_text("❌ Operación cancelada.")
    elif action_data.startswith("del_"):
        try:
            filter_id_to_delete = int(action_data.split('_')[1])
            db.eliminar_filtro(db_conn, filter_id_to_delete)
            query.edit_message_text(f"🗑️ Filtro ID {filter_id_to_delete} eliminado.")
            logger.info(f"Filter ID {filter_id_to_delete} deleted by user {update.effective_user.id}")
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing filter ID from callback data '{action_data}' for user {update.effective_user.id}: {e}", exc_info=True)
            query.edit_message_text("❌ Error al procesar la solicitud de borrado.")
            
def help_command(update: Update, context: CallbackContext):
    if not is_authorized(update): return
    help_text = (
        "ℹ️ *Comandos Disponibles* ℹ️\n\n"
        "/start - Inicia la interacción con el bot.\n"
        "/add - ➕ Añade un nuevo filtro de búsqueda.\n"
        "/show - 📋 Muestra los filtros activos.\n"
        "/delete - 🗑️ Elimina un filtro existente.\n"
        "/start_search - 🚀 Inicia la búsqueda de anuncios.\n"
        "/stop_search - 🛑 Detiene la búsqueda de anuncios.\n"
        "/status - 📊 Muestra el estado actual de la búsqueda.\n"
        "/help - ❓ Muestra este mensaje de ayuda.\n\n"
        "*Administración (Solo para el primer usuario autorizado):*\n"
        "/show_users - 👥 Muestra los IDs de usuarios autorizados.\n"
        "/add_user `<ID>` - 👤 Añade un nuevo usuario autorizado."
    )
    update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

def error_handler(update: object, context: CallbackContext) -> None:
    """Log Errors caused by Updates and notify user if possible."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            update.effective_message.reply_text("⚠️ Ocurrió un error procesando tu solicitud. Intenta de nuevo más tarde.")
        except Exception as e_reply:
            logger.error(f"Failed to send error message to user {update.effective_user.id if update.effective_user else 'unknown'}: {e_reply}", exc_info=True)

def main():
    """Start the bot."""
    if not TOKEN: 
        return

    bot_state = BotState()
    main_db_conn = db.get_db_connection()

    if not main_db_conn:
        logger.critical("Failed to establish main database connection. Bot cannot start.")
        return

    try:
        db.crear_tabla_filtros(main_db_conn)
    except Exception as e:
        logger.critical(f"Failed to create 'filtros' table: {e}. Bot cannot start.", exc_info=True)
        db.close_db_connection(main_db_conn)
        return

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.bot_data['bot_state'] = bot_state
    dp.bot_data['db_conn'] = main_db_conn
    
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
            CommandHandler('cancel', cancel_command_in_conversation) 
        ],
    )

    dp.add_handler(add_filter_conv_handler)
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("start_search", start_search_command))
    dp.add_handler(CommandHandler("stop_search", stop_search_command))
    dp.add_handler(CommandHandler("status", status_command))
    dp.add_handler(CommandHandler("show", show_filters_command))
    dp.add_handler(CommandHandler("delete", delete_filter_command))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("add_user", add_user_command))
    dp.add_handler(CommandHandler("show_users", show_users_command))
    dp.add_handler(CallbackQueryHandler(delete_filter_callback, pattern='^del_'))
    dp.add_error_handler(error_handler)

    updater.start_polling()
    logger.info("Bot started polling successfully.")
    updater.idle()

    logger.info("Bot shutting down...")
    bot_state.stop_search_flag = True 
    if bot_state.search_thread and bot_state.search_thread.is_alive():
        logger.info("Waiting for search thread to complete...")
        bot_state.search_thread.join(timeout=15) # Give thread time to finish current cycle
        if bot_state.search_thread.is_alive():
            logger.warning("Search thread did not terminate gracefully after timeout.")
    if main_db_conn:
        db.close_db_connection(main_db_conn)
    logger.info("Bot shutdown complete.")

if __name__ == '__main__':
    main()
```
