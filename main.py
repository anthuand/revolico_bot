import logging
from emoji import emojize
# import requests # Not directly used in main.py after scraper changes
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update # ChatAction not used
from telegram.ext import (
    Application, CommandHandler, MessageHandler, Filters, 
    ConversationHandler, CallbackQueryHandler, CallbackContext
)
from db import (
    insertar_filtro, obtener_filtros, eliminar_filtro, eliminar_todos_los_filtros,
    crear_tabla_filtros,
    crear_tabla_sent_ads, add_sent_ad, is_ad_sent
)
import scraper
import os
import time
import io
import threading
import asyncio # Added asyncio
from datetime import datetime
import pytz

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TOKEN')
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
NOTIFICATION_CHANNEL_ID = os.getenv('NOTIFICATION_CHANNEL_ID')
ALLOWED_USER_IDS = os.getenv('ALLOWED_USER_IDS', '')

# --- Global states for ConversationHandler (remains as is) ---
INTRODUCIR_DATOS_FILTRO, END_CONVERSATION = range(2) # Renamed 'end'
ANADIR_USUARIOS_STATE = 1 # Renamed 'anadir_usuarios' for clarity

# --- User ID Management (remains mostly global for now, loaded at start) ---
Users_id = [uid.strip() for uid in ALLOWED_USER_IDS.split(',') if uid.strip()]
if ADMIN_USER_ID and ADMIN_USER_ID not in Users_id:
    Users_id.append(ADMIN_USER_ID)
elif not Users_id and ADMIN_USER_ID: 
    Users_id.append(ADMIN_USER_ID)

# --- Boton class (can be removed if ConversationHandler uses dicts in user_data) ---
# For now, keeping it if it's simple, but user_data dicts are preferred.
# Let's try to remove it by storing simple dicts {'id': ..., 'valor': ...} in user_data.

# --- Global status for the search thread ---
hilo_status = ['detenido'] # String: 'detenido' or 'funcionando'
stop_threads_event = threading.Event() # Using threading.Event for safer stop signaling

# --- Authentication ---
def is_user_authenticated(update: Update, context: CallbackContext) -> bool: # Renamed & type hinted
    # Ensure update and update.effective_user exist
    if not update or not update.effective_user:
        return False
    user_id_to_check = str(update.effective_user.id)
    return user_id_to_check in Users_id

# --- User Management Commands (Async) ---
async def add_user_command(update: Update, context: CallbackContext) -> int: # Renamed, async
    if str(update.message.chat_id) == ADMIN_USER_ID:
        await update.message.reply_text('Hola admin, envía el ID del nuevo usuario a añadir.')
        return ANADIR_USUARIOS_STATE
    else:
        await update.message.reply_text('No tienes permiso para agregar usuarios.')
        return ConversationHandler.END

async def receive_user_id_for_addition(update: Update, context: CallbackContext) -> int: # Renamed, async
    user_to_add = update.message.text.strip()
    if user_to_add.isdigit():
        if user_to_add not in Users_id: 
            Users_id.append(user_to_add) # Still modifying global Users_id; consider persistent storage
            logger.info(f"Admin {ADMIN_USER_ID} added user {user_to_add}. Current Users_id: {Users_id}")
            await update.message.reply_text(f'Usuario {user_to_add} añadido a la lista activa.')
            # Could save ALLOWED_USER_IDS back to a file or DB if needed here
        else:
            await update.message.reply_text('Este usuario ya está en la lista activa.')
    else:
        await update.message.reply_text('ID de usuario inválido. Debe ser numérico.')
    return ConversationHandler.END

async def show_users_command(update: Update, context: CallbackContext) -> None: # Renamed, async
    if str(update.effective_chat.id) == ADMIN_USER_ID:
        await update.message.reply_text(f"Usuarios activos actualmente: {Users_id}")
    else:
         await update.message.reply_text("No tienes permiso para esta acción.")

# --- Synchronous Search Logic (runs in a separate thread) ---
def buscar_sync(initial_update_message, bot_instance, application_loop, stop_event: threading.Event):
    CHATID = initial_update_message.chat_id # User's chat ID who initiated the search
    
    while not stop_event.is_set():
        logger.info("Iniciando ciclo de búsqueda de anuncios...")
        try:
            filtros_activos = obtener_filtros() # DB access is synchronous
            if not filtros_activos:
                logger.info("No hay filtros activos. Esperando...")
                time.sleep(30) # Adjusted sleep time
                continue

            for filtro_item in filtros_activos:
                if stop_event.is_set(): break

                (id_filtro, dep, palabra_clave_filtro, precio_min, 
                 precio_max, provincia, municipio, fotos_filtro_setting) = filtro_item
                
                logger.info(f"Procesando filtro ID {id_filtro}: '{palabra_clave_filtro}' en '{dep}'")
                
                list_of_ad_data = scraper.get_main_anuncios(
                    dep, palabra_clave_filtro, precio_min, precio_max, provincia, municipio, fotos_filtro_setting
                ) # scraper.get_main_anuncios is synchronous

                if not list_of_ad_data:
                    # logger.info(f"No se encontraron anuncios para el filtro ID {id_filtro}.") # Can be noisy
                    time.sleep(3) 
                    continue

                for ad_data in list_of_ad_data:
                    if stop_event.is_set(): break

                    ad_url = ad_data['url']
                    if is_ad_sent(ad_url): # DB access is synchronous
                        # logger.info(f"Anuncio ya enviado: {ad_url}") # Can be noisy
                        continue

                    logger.info(f"Nuevo anuncio encontrado: {ad_data['titulo']} ({ad_url})")
                    
                    contacto_nombre, contacto_telefono, contacto_email = ad_data['contacto']
                    dt_cuba = datetime.now(pytz.timezone('Cuba'))
                    hora_actual = dt_cuba.strftime('%Y-%m-%d a las %H:%M:%S')

                    info = (
                        f"#{palabra_clave_filtro.replace(' ', '_') if palabra_clave_filtro else 'Revolico'}\n"
                        f"<b>{ad_data['titulo']}</b>\n\n"
                        f"Precio: {ad_data['precio']}\n\n"
                        f"Descripción:\n{ad_data['descripcion']}\n\n"
                        f"Fecha de publicación (scraping): {ad_data['fecha']}\n"
                        f"Fecha de envío (bot): {hora_actual}\n"
                        f"Ubicación: {ad_data['ubicacion']}\n"
                    )
                    if contacto_nombre != "no tiene": info += f"Contacto: {contacto_nombre}\n"
                    if contacto_email != "no tiene": info += f"Email: {contacto_email}\n"
                    if contacto_telefono != "no tiene": info += f"Teléfono: #{contacto_telefono.replace(' ', '')}\n\n"

                    message_button = InlineKeyboardButton("Ver Anuncio Original", url=ad_url)
                    message_markup = InlineKeyboardMarkup([[message_button]])
                    image_bytes, _ = ad_data['imagen']

                    try:
                        # Use asyncio.run_coroutine_threadsafe for bot calls from this thread
                        if image_bytes:
                            logger.debug(f"Preparando envío CON foto para {ad_url}")
                            photo_to_send = io.BytesIO(image_bytes)
                            coro = bot_instance.send_photo(chat_id=CHATID, photo=photo_to_send, caption=info, reply_markup=message_markup, parse_mode="HTML")
                            future = asyncio.run_coroutine_threadsafe(coro, application_loop)
                            future.result(timeout=30) # Wait for result with timeout

                            if NOTIFICATION_CHANNEL_ID:
                                photo_to_send.seek(0)
                                coro_channel = bot_instance.send_photo(chat_id=NOTIFICATION_CHANNEL_ID, photo=photo_to_send, caption=info, reply_markup=message_markup, parse_mode="HTML")
                                future_channel = asyncio.run_coroutine_threadsafe(coro_channel, application_loop)
                                future_channel.result(timeout=30)
                        else:
                            logger.debug(f"Preparando envío SIN foto para {ad_url}")
                            coro = bot_instance.send_message(chat_id=CHATID, text=info, reply_markup=message_markup, parse_mode="HTML")
                            future = asyncio.run_coroutine_threadsafe(coro, application_loop)
                            future.result(timeout=30)

                            if NOTIFICATION_CHANNEL_ID:
                                coro_channel = bot_instance.send_message(chat_id=NOTIFICATION_CHANNEL_ID, text=info, reply_markup=message_markup, parse_mode="HTML")
                                future_channel = asyncio.run_coroutine_threadsafe(coro_channel, application_loop)
                                future_channel.result(timeout=30)
                        
                        add_sent_ad(ad_url) # Synchronous DB call
                        logger.info(f"Anuncio marcado como enviado y notificado: {ad_url}")

                    except Exception as e_send:
                        logger.error(f"Error enviando anuncio {ad_url} a Telegram via threadsafe call: {e_send}")
                    
                    time.sleep(1) # Short sleep between ads

            # logger.info("Ciclo de filtros completado.") # Can be noisy
            time.sleep(15) # Sleep after processing all filters

        except Exception as e_outer:
            logger.error(f"Error mayor en el hilo de búsqueda: {e_outer}", exc_info=True)
            time.sleep(45)
    logger.info("Función buscar_sync terminada.")


# --- Filter Creation Conversation Handler (Async, uses context.user_data) ---
# States for the conversation
DEPARTAMENTO_STATE, PALABRA_CLAVE_STATE, PRECIO_MIN_STATE, PRECIO_MAX_STATE, RECEIVED_INFO_STATE = range(5)

async def add_filter_command(update: Update, context: CallbackContext) -> int:
    if not is_user_authenticated(update, context):
        await update.message.reply_text('Lo siento, no tienes permiso para añadir filtros.')
        return ConversationHandler.END
    
    context.user_data['current_filter_parts'] = {} # Initialize dict to store filter parts
    await update.message.reply_text('Selecciona el departamento donde buscar:', reply_markup=markup_departamentos)
    return DEPARTAMENTO_STATE # Entry point state changed

async def select_departamento_callback(update: Update, context: CallbackContext) -> int: # Renamed
    query = update.callback_query
    await query.answer()
    context.user_data['current_filter_parts']['departamento'] = query.data
    await query.edit_message_text(text=f"Departamento: {query.data}. Ahora elige una opción o introduce detalles:", reply_markup=markup_filtro)
    return INTRODUCIR_DATOS_FILTRO # State for choosing next field

async def ask_for_palabra_clave_callback(update: Update, context: CallbackContext) -> int: # Renamed
    query = update.callback_query
    await query.answer()
    context.user_data['current_filter_field_id'] = 'palabra_clave'
    await query.edit_message_text(text="Ejemplos de búsquedas por palabra clave:\n"
                                 "<b>casa grande:</b> todas las palabras.\n"
                                 "<b>\"casa grande\":</b> la frase exacta.\n"
                                 "<b>casa | grande:</b> una palabra o la otra.\n"
                                 "<b>casa !grande:</b> una palabra pero no la otra.\n"
                                 "<b>casa (grande | pequeña):</b> la primera y una de las otras dos.\n"
                                 "Por favor, envía tu palabra clave.",
                                 parse_mode="HTML")
    return RECEIVED_INFO_STATE # State to receive text input

async def ask_for_precio_min_callback(update: Update, context: CallbackContext) -> int: # Renamed
    query = update.callback_query
    await query.answer()
    context.user_data['current_filter_field_id'] = 'precio_min'
    await query.edit_message_text(text="Dime el precio mínimo que quieres buscar (ej. 500).")
    return RECEIVED_INFO_STATE

async def ask_for_precio_max_callback(update: Update, context: CallbackContext) -> int: # Renamed
    query = update.callback_query
    await query.answer()
    context.user_data['current_filter_field_id'] = 'precio_max'
    await query.edit_message_text(text="Dime el precio máximo que quieres buscar (ej. 1500).")
    return RECEIVED_INFO_STATE

async def received_filter_information_text(update: Update, context: CallbackContext) -> int: # Renamed
    text = update.message.text.strip()
    field_id = context.user_data.get('current_filter_field_id')

    if not field_id:
        await update.message.reply_text('Por favor, primero selecciona una opción (ej. "palabra_clave") antes de escribir.', reply_markup=markup_filtro)
        return INTRODUCIR_DATOS_FILTRO # Stay in current state or guide user

    context.user_data['current_filter_parts'][field_id] = text
    await update.message.reply_text(f"{field_id.replace('_',' ').capitalize()}: '{text}' guardado. Puedes seguir editando o /done_filter.", reply_markup=markup_filtro)
    context.user_data['current_filter_field_id'] = None # Clear field_id
    return INTRODUCIR_DATOS_FILTRO

async def done_filter_creation_callback(update: Update, context: CallbackContext) -> int: # Renamed
    query = update.callback_query
    await query.answer()
    
    filter_data = context.user_data.get('current_filter_parts', {})
    dep_valor = filter_data.get('departamento')
    p_clave_valor = filter_data.get('palabra_clave')

    if not dep_valor or not p_clave_valor:
        await query.edit_message_text("Error: Departamento y Palabra Clave son requeridos. /cancel_filter e inténtalo de nuevo.", reply_markup=markup_filtro)
        # context.user_data.pop('current_filter_parts', None) # Clean up
        # context.user_data.pop('current_filter_field_id', None)
        return INTRODUCIR_DATOS_FILTRO # Or end and ask to start over

    pr_min_valor = filter_data.get('precio_min')
    pr_max_valor = filter_data.get('precio_max')
    prov_valor, mun_valor, fot_valor = "La Habana", None, None # Defaults

    insertar_filtro(dep_valor, p_clave_valor, pr_min_valor, pr_max_valor, prov_valor, mun_valor, fot_valor) # Sync DB call
    
    await query.edit_message_text("¡Filtro guardado exitosamente!")
    
    userName = update.effective_user.first_name
    logger.info(f"Filtro guardado por [{userName}]: {p_clave_valor} en {dep_valor}")
    with open("log.txt", "a", encoding="utf-8") as log_file:
        log_file.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] User: {userName}, Filtro: {p_clave_valor} en {dep_valor}\n")
        
    context.user_data.pop('current_filter_parts', None)
    context.user_data.pop('current_filter_field_id', None)
    return ConversationHandler.END

async def cancel_filter_creation_callback(update: Update, context: CallbackContext) -> int: # Renamed
    context.user_data.pop('current_filter_parts', None)
    context.user_data.pop('current_filter_field_id', None)
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Creación de filtro cancelada.")
    else: # If called by /cancel_filter command
        await update.message.reply_text("Creación de filtro cancelada.")
    return ConversationHandler.END


# --- Other Commands (Async) ---
async def delete_all_filters_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    eliminar_todos_los_filtros() # Sync DB call
    await query.edit_message_text("Todos los filtros han sido eliminados.")
    # botones_filtro_borrar.clear() # This list is global, needs careful handling or removal

async def delete_single_filter_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    filter_id_to_delete_str = query.data 
    await query.answer()
    try:
        filter_id_to_delete = int(filter_id_to_delete_str)
        eliminar_filtro(filter_id_to_delete) # Sync DB call
        await query.edit_message_text(f"Filtro con ID {filter_id_to_delete} eliminado.")
    except ValueError:
        await query.edit_message_text(f"Error: ID de filtro inválido '{filter_id_to_delete_str}'.")
        logger.error(f"Intento de eliminar filtro con ID inválido: {filter_id_to_delete_str}")
    except Exception as e:
        await query.edit_message_text("Error al eliminar el filtro.")
        logger.error(f"Error eliminando filtro ID {filter_id_to_delete_str}: {e}")
    # botones_filtro_borrar.clear()

async def start_search_thread_command(update: Update, context: CallbackContext) -> None: # Renamed
    if not is_user_authenticated(update, context):
        await update.message.reply_text('Lo siento, no tienes permiso para iniciar la búsqueda.')
        return

    if hilo_status[0] == 'funcionando':
        await update.message.reply_text('La búsqueda automática ya está en ejecución. Usa /stop_search para detenerla primero.')
        return

    stop_threads_event.clear() # Reset event for new thread
    await update.message.reply_text('Iniciando búsqueda automática... Para detenerla, teclee /stop_search')
    
    # Store thread in application context to manage it if needed (e.g. for shutdown)
    # Ensure application context is used consistently if you need to access thread from other places
    search_thread = threading.Thread(
        target=buscar_sync, 
        args=(update.message, context.bot, asyncio.get_event_loop(), stop_threads_event), 
        daemon=True
    )
    context.application.search_thread_instance = search_thread # Store the thread
    search_thread.start()
    hilo_status[0] = 'funcionando'

async def stop_search_thread_command(update: Update, context: CallbackContext) -> None: # Renamed
    if not is_user_authenticated(update, context):
        await update.message.reply_text('Lo siento, no tienes permiso para detener la búsqueda.')
        return

    if hilo_status[0] == 'detenido':
        await update.message.reply_text('La búsqueda automática ya está detenida.')
        return

    stop_threads_event.set() # Signal the thread to stop
    
    search_thread_instance = getattr(context.application, 'search_thread_instance', None)
    if search_thread_instance and search_thread_instance.is_alive():
        logger.info("Esperando que el hilo de búsqueda termine...")
        search_thread_instance.join(timeout=10) # Wait for thread to finish
        if search_thread_instance.is_alive():
            logger.warning("El hilo de búsqueda no terminó a tiempo.")
        else:
            logger.info("Hilo de búsqueda terminado exitosamente.")
            
    hilo_status[0] = 'detenido'
    await update.message.reply_text('¡Búsqueda automática detenida!')


async def start_command(update: Update, context: CallbackContext) -> None:
    if is_user_authenticated(update, context):
        await update.message.reply_text('Hola bienvenido al bot revolico! Usa /help para ver los comandos.')
    else:
        await update.message.reply_text('Lo siento, no tienes permiso para acceder a este bot.')

async def status_command(update: Update, context: CallbackContext) -> None:
    if is_user_authenticated(update, context):
        await update.message.reply_text(f"Estado del hilo de búsqueda: {hilo_status[0]}")
    else:
        await update.message.reply_text('Lo siento, no tienes permiso para ver el estado.')

async def delete_filter_options_command(update: Update, context: CallbackContext) -> None: # Renamed
    if not is_user_authenticated(update, context):
        await update.message.reply_text('Lo siento, no tienes permiso para borrar filtros.')
        return

    filtros_existentes = obtener_filtros() # Sync DB call
    local_botones_borrar = [] # Use local list for buttons
    if not filtros_existentes:
        await update.message.reply_text('No hay filtros guardados para borrar.')
        return

    for filtro_item in filtros_existentes:
        btn_text = f"ID:{filtro_item[0]} - {filtro_item[2][:20]} ({filtro_item[1]})" # Truncate long names
        local_botones_borrar.append([InlineKeyboardButton(btn_text, callback_data=str(filtro_item[0]))])
    
    local_botones_borrar.append([InlineKeyboardButton(text="Borrar Todos los Filtros", callback_data='delete_all_filters_option')])
    local_botones_borrar.append([InlineKeyboardButton("Cancelar", callback_data='cancel_delete_op')]) # Specific cancel
    markup = InlineKeyboardMarkup(local_botones_borrar)
    await update.message.reply_text('Seleccione el filtro a borrar o la opción de borrar todos:', reply_markup=markup)

async def cancel_delete_operation_callback(update: Update, context: CallbackContext) -> None: # Specific cancel
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Operación de borrado cancelada.")


async def test_command(update: Update, context: CallbackContext) -> None:
    if is_user_authenticated(update, context):
        await update.message.reply_text('Tranquilo, sigo vivo y respondiendo en async! :)')
        if NOTIFICATION_CHANNEL_ID:
            await context.bot.send_message(chat_id=NOTIFICATION_CHANNEL_ID, text='El bot de Revolico (async) está funcionando correctamente.')
    else:
        await update.message.reply_text('No autenticado.')

async def show_filters_command(update: Update, context: CallbackContext) -> None:
    if not is_user_authenticated(update, context):
        await update.message.reply_text('Lo siento, no tienes permiso para ver los filtros.')
        return
        
    filtros_existentes = obtener_filtros() # Sync DB call
    if not filtros_existentes:
        await update.message.reply_text("No hay filtros activos guardados.")
        return

    response_message = "Filtros Activos:\n\n"
    for filtro_item in filtros_existentes:
        (id_f, dep_f, pk_f, pmin_f, pmax_f, prov_f, mun_f, fotos_f) = filtro_item
        response_message += (
            f"<b>ID: {id_f}</b>\n  Departamento: {dep_f}\n  Palabra Clave: {pk_f}\n"
            f"  Precio Min: {pmin_f if pmin_f else 'N/A'}\n  Precio Max: {pmax_f if pmax_f else 'N/A'}\n"
            # f"  Provincia: {prov_f if prov_f else 'N/A'}\n  Municipio: {mun_f if mun_f else 'N/A'}\n"
            # f"  Con Fotos: {fotos_f if fotos_f else 'N/A'}\n\n"
        )
    await update.message.reply_text(response_message, parse_mode="HTML")


async def help_command(update: Update, context: CallbackContext) -> None:
    if is_user_authenticated(update, context):
        help_text = (
            "Comandos disponibles:\n"
            "/start - Inicia el bot.\n"
            "/start_search - Inicia la búsqueda automática.\n"
            "/stop_search - Detiene la búsqueda automática.\n"
            "/status - Estado de la búsqueda.\n"
            "/add_filter - Añadir nuevo filtro.\n"
            "/show_filters - Mostrar filtros activos.\n"
            "/delete_filter - Borrar filtros.\n"
            "/test - Comprobar si el bot responde.\n"
            "/help - Muestra esta ayuda.\n\n"
            "Comandos de Admin:\n"
            "/add_user_cmd - Añadir ID de usuario autorizado.\n"
            "/show_users_cmd - Mostrar IDs autorizados.\n"
            "/ads_admin_cmd - Enviar archivo de log."
        )
        await update.message.reply_text(help_text)
    else:
        await update.message.reply_text('Lo siento, no tienes permiso para acceder a la ayuda.')

async def ads_admin_command(update: Update, context: CallbackContext) -> None:
    if str(update.effective_chat.id) == ADMIN_USER_ID:
        try:
            with open('log.txt', 'rb') as doc:
                await context.bot.send_document(ADMIN_USER_ID, document=doc, filename='revolico_bot_log.txt')
        except FileNotFoundError:
            await update.message.reply_text("log.txt no encontrado.")
        except Exception as e:
            await update.message.reply_text(f"Error al enviar log: {e}")
            logger.error(f"Error en ads_admin_command: {e}")

async def general_text_listener(update: Update, context: CallbackContext) -> None:
    if update.message and update.message.text and not update.message.text.startswith('/'):
        # This is a fallback for text not caught by conversations or other handlers
        logger.info(f"Texto no procesado de [{update.effective_user.id}][{update.effective_user.first_name}]: {update.message.text[:50]}")
        # await update.message.reply_text("No he entendido eso. Usa /help para ver los comandos.")

async def error_handler(update: object, context: CallbackContext) -> None:
    logger.error(f'Update "{update}" causó error "{context.error}"', exc_info=context.error)
    log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error: {context.error} from update: {update}\n"
    with open("log.txt", "a", encoding="utf-8") as log_file:
        log_file.write(log_entry)
    # Consider sending a message to ADMIN_USER_ID on critical errors
    # if ADMIN_USER_ID:
    #     try:
    #         error_message_for_admin = f"Error en el bot: {context.error}\nUpdate: {update}"
    #         await context.bot.send_message(chat_id=ADMIN_USER_ID, text=error_message_for_admin[:4000])
    #     except Exception as e_admin:
    #         logger.error(f"No se pudo notificar al admin sobre el error: {e_admin}")


# --- Markups (defined globally as they are static) ---
markup_departamentos = InlineKeyboardMarkup([
    [InlineKeyboardButton(emojize(":shopping_bags: Compra-Venta"), callback_data='compra-venta'),
     InlineKeyboardButton(emojize(":car: Autos"), callback_data='autos')],
    [InlineKeyboardButton(emojize(":house_with_garden: Vivienda"), callback_data='vivienda'),
     InlineKeyboardButton(emojize(":briefcase: Empleos"), callback_data='empleos')],
    [InlineKeyboardButton(emojize(":wrench: Servicios"), callback_data='servicios'),
     InlineKeyboardButton(emojize(":computer: Computadoras"), callback_data='computadoras')],
    [InlineKeyboardButton(emojize(":x: Cancelar"), callback_data='cancel_filter_creation')]
])

markup_filtro = InlineKeyboardMarkup([
    [InlineKeyboardButton("Palabra Clave", callback_data='ask_palabra_clave'),
     InlineKeyboardButton("Precio Mínimo", callback_data='ask_precio_min'),
     InlineKeyboardButton("Precio Máximo", callback_data='ask_precio_max')],
    [InlineKeyboardButton(emojize(":white_check_mark: Terminar Filtro"), callback_data='done_filter_creation'),
     InlineKeyboardButton(emojize(":x: Cancelar"), callback_data='cancel_filter_creation')]
])


def main() -> None:
    if not TOKEN:
        logger.critical("CRITICAL: TOKEN environment variable not set!")
        return
    if not ADMIN_USER_ID:
        logger.warning("ADMIN_USER_ID environment variable not set! Some admin functionalities might not work.")
    
    crear_tabla_filtros()
    crear_tabla_sent_ads()

    application = Application.builder().token(TOKEN).build()
    
    # Conversation handler for adding filters (using user_data)
    add_filter_conv = ConversationHandler(
        entry_points=[CommandHandler('add_filter', add_filter_command)],
        states={
            DEPARTAMENTO_STATE: [CallbackQueryHandler(select_departamento_callback, pattern='^(compra-venta|autos|vivienda|empleos|servicios|computadoras)$')],
            INTRODUCIR_DATOS_FILTRO: [
                CallbackQueryHandler(ask_for_palabra_clave_callback, pattern='ask_palabra_clave'),
                CallbackQueryHandler(ask_for_precio_min_callback, pattern='ask_precio_min'),
                CallbackQueryHandler(ask_for_precio_max_callback, pattern='ask_precio_max'),
                CallbackQueryHandler(done_filter_creation_callback, pattern='done_filter_creation'),
            ],
            RECEIVED_INFO_STATE: [MessageHandler(Filters.TEXT & (~Filters.COMMAND), received_filter_information_text)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_filter_creation_callback, pattern='cancel_filter_creation'),
            CommandHandler('cancel_filter', cancel_filter_creation_callback) # Command to cancel
        ],
        map_to_parent={ # If this conv is nested, otherwise not needed or END state returns to base level
            ConversationHandler.END: ConversationHandler.END
        }
    )

    add_user_conv = ConversationHandler(
        entry_points=[CommandHandler("add_user_cmd", add_user_command)], # Renamed command
        states={
            ANADIR_USUARIOS_STATE: [MessageHandler(Filters.TEXT & (~Filters.COMMAND), receive_user_id_for_addition)],
        },
        fallbacks=[CommandHandler('cancel_user_add', cancel_filter_creation_callback)], # Generic cancel for now
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("start_search", start_search_thread_command))
    application.add_handler(CommandHandler("stop_search", stop_search_thread_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(add_filter_conv)
    application.add_handler(CommandHandler("show_filters", show_filters_command))
    application.add_handler(CommandHandler("delete_filter", delete_filter_options_command))
    application.add_handler(add_user_conv)
    application.add_handler(CommandHandler("show_users_cmd", show_users_command)) # Renamed command
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ads_admin_cmd", ads_admin_command)) # Renamed command
    
    application.add_handler(CallbackQueryHandler(delete_all_filters_callback, pattern='delete_all_filters_option'))
    application.add_handler(CallbackQueryHandler(delete_single_filter_callback, pattern=r"^\d+$")) # For deleting specific filter by ID
    application.add_handler(CallbackQueryHandler(cancel_delete_operation_callback, pattern='cancel_delete_op'))

    application.add_handler(MessageHandler(Filters.TEXT & (~Filters.COMMAND) & (~Filters.Update.EDITED_MESSAGE), general_text_listener))
    application.add_error_handler(error_handler)

    logger.info("Bot iniciando polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES) # Specify allowed updates
    
    logger.info("Bot detenido.")

if __name__ == '__main__':
    main()
