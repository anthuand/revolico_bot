import logging
from emoji import emojize
import requests
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update, ChatAction
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackQueryHandler, \
    CallbackContext, JobQueue
from db import insertar_filtro, obtener_filtros, obtener_anuncios, eliminar_filtro, eliminar_todos_los_filtros
from scraper import get_main_anuncios, obtener_imagenes, obtener_contacto
import os, time
import threading

# PORT = int(os.environ.get('PORT', 8443))

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)
TOKEN = os.getenv('TOKEN')


class boton:
    id = ""
    valor = ""


Hilo_status = ['detenido']
stop_threads = [False]
Filtros = []
borrar_filtro = 1
introducir_datos_filtro, end = range(2)


# ----->funciones independientes
def buscar(upd, context):
    CHATID = upd.message.chat_id
    bot = context.bot

    while True:
        if stop_threads[0]:
            break

        try:
            filtros = obtener_filtros()
            for filtro in filtros:

                id = filtro[0]
                dep = filtro[1]
                palabra_clave = filtro[2]
                precio_min = filtro[3]
                precio_max = filtro[4]
                provincia = filtro[5]
                municipio = filtro[6]
                fotos = filtro[7]

                get_main_anuncios(dep, palabra_clave, precio_min, precio_max, provincia, municipio, fotos)
                anuncios = obtener_anuncios()
                for anuncio in anuncios:
                    id = anuncio[0]
                    url = "https://www.revolico.com" + str(anuncio[1])
                    titulo = anuncio[2]
                    precio = anuncio[3]
                    descripcion = anuncio[4]
                    fecha = anuncio[5]
                    ubicacion = anuncio[6]
                    foto = anuncio[7]
                    Contacto, telefono, email = obtener_contacto(url)

                    info = (
                            "#" + str(palabra_clave) + "\n" + str(titulo) + "\n\n"
                            + "Precio: " + str(precio) + "\n\n\n"
                            + "descripcion: \n" + str(descripcion) + "\n\n\n"
                            + "fecha: " + str(fecha) + "\n"
                            + "ubicacion: " + str(ubicacion) + "\n"
                            + "Contacto: " + str(Contacto) + "\n"
                            + "Email: " + str(email) + "\n"
                            + "Telefono: " + str(telefono) + "\n\n"
                    )

                    boton = InlineKeyboardButton("Ver anuncio", url)
                    markup = InlineKeyboardMarkup([
                        [boton]
                    ])
                    if foto != 0 and foto != 'no tiene':
                        src_img = obtener_imagenes(url)
                        if src_img:
                            print("Voy a enviar una anuncio con imagen")
                            # ft = open("foto.jpg", "rb")
                            inf =str(info)+'<a href="'+ src_img +'">&#8205;</a>' 
                            chat = upd.message.chat
                            chat.send_action(action=ChatAction.UPLOAD_PHOTO)
                            upd.message.reply_text(text=inf, parse_mode="HTML", reply_markup=markup)
                            # upd.message.reply_photo(photo=ft, caption=info, reply_markup=markup)
                            print(info)
                    else:
                        # chat.send_action(action=ChatAction.TYPING)
                        print("Voy a enviar una anuncio sin imagen")
                        context.bot.send_message(CHATID, info, reply_markup=markup)
                        print(info)

                time.sleep(0.1)

            time.sleep(0.1)
        except Exception as e:
            print(e)


botones_filtro_borrar = []
opciones_filtro = [
    [InlineKeyboardButton("palabra_clave", callback_data='palabra_clave')],
    [InlineKeyboardButton("precio_min", callback_data='precio_min'),
     InlineKeyboardButton("precio_max", callback_data='precio_max')],
    # [InlineKeyboardButton("provincia", callback_data='provincia'),
    #  InlineKeyboardButton("municipio", callback_data='municipio'),
    #  InlineKeyboardButton("fotos", callback_data='fotos')],
    [InlineKeyboardButton(text=emojize("Cancelar :x:", use_aliases=True), callback_data='Cancelar'),
     InlineKeyboardButton(text=emojize("Aceptar :white_check_mark:", use_aliases=True), callback_data='Aceptar')],
]
markup_filtro = InlineKeyboardMarkup(opciones_filtro)
opciones_departamentos = [
    [InlineKeyboardButton(text=emojize("Compra-Venta :money_with_wings:", use_aliases=True),
                          callback_data='compra-venta'),
     InlineKeyboardButton(text=emojize("Autos :car:", use_aliases=True), callback_data='autos'),
     InlineKeyboardButton(text=emojize("Vivienda :house_with_garden:", use_aliases=True), callback_data='vivienda')],
    [InlineKeyboardButton(text=emojize("Empleos :briefcase:", use_aliases=True), callback_data='empleos'),
     InlineKeyboardButton(text=emojize("Servicios :wrench:", use_aliases=True), callback_data='servicios'),
     InlineKeyboardButton(text=emojize("Computadoras :computer:", use_aliases=True), callback_data='computadoras')],
    [InlineKeyboardButton(text=emojize("Cancelar :x:", use_aliases=True), callback_data='Cancelar')],
]

markup_departamentos = InlineKeyboardMarkup(opciones_departamentos)


# # ---->Seccion de editar los filtros

def departamento(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    global bt
    bt = boton()
    bt.id = "departamento"
    bt.valor = query.data
    if bt:
        Filtros.append(bt)
    query.answer()
    query.edit_message_text(text='Continua editando el filtro:', reply_markup=markup_filtro)

    return introducir_datos_filtro


def palabra_clave(update, context):
    print("estoy dentro de palabra clave")
    query = update.callback_query
    query.answer()
    query.edit_message_text(text= "Ejemplos de búsquedas por palabra clave:\n"
    "En los resultados aparecerán anuncios que contengan:\n\n"
    "<b>casa grande: </b>     todas las palabras de la búsqueda.\n"
    "<b>\"casa grande\":</b>   la frase exacta.\n"
    "<b>casa | grande:</b>   una palabra o la otra\n"
    "<b>casa !grande:</b>    una palabra pero no la otra.\n"
    "<b>casa (grande | pequeña):</b>   la primera palabra y cualquiera de las otras dos\n",
    parse_mode = "HTML")
    
    global bt
    bt = boton()
    bt.id = "palabra_clave"

    return introducir_datos_filtro


def precio_min(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "Dime el precio-minimo que quieres buscar"
    )
    global bt
    bt = boton()
    bt.id = "precio_min"

    return introducir_datos_filtro


def precio_max(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "Dime el precio-maximo que quieres buscar"
    )
    global bt
    bt = boton()
    bt.id = "precio_max"

    return introducir_datos_filtro


# def provincia(update, context):
#     query = update.callback_query
#     query.answer()
#     query.edit_message_text(
#         "Dime la provincia que quieres buscar"
#     )
#     global bt
#     bt = boton()
#     bt.id = "provincia"
#
#     return introducir_datos_filtro
#
#
# def municipio(update, context):
#     query = update.callback_query
#     query.answer()
#     query.edit_message_text(
#         "Dime el municipio en el que quieres buscar (para seleccionar municipio , tiene que haber establecido previamente la provincia"
#     )
#     global bt
#     bt = boton()
#     bt.id = "municipio"
#     return introducir_datos_filtro


# def fotos(update, context):
#     query = update.callback_query
#     query.answer()
#     query.edit_message_text(
#         "Si quieres que el anuncio tenga fotos escribe Si o No"
#     )
#     global bt
#     bt = boton()
#     bt.id = "fotos"
#
#     return introducir_datos_filtro


def received_information(update, context):
    print("estoy dentro de recived")
    text = update.message.text
    print(text)

    update.message.reply_text('ok.Puedes seguir editando el filtro  o terminar', reply_markup=markup_filtro)
    bt.valor = text
    if bt:
        Filtros.append(bt)

    return introducir_datos_filtro


def cancel(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "Se ha cancelado la accion"
    )
    if Filtros:
        Filtros.clear()

    return ConversationHandler.END


def done(update, context):
    if Filtros is not None:
        p_clave_valor = None
        pr_min_valor = None
        pr_max_valor = None
        prov_valor = "La Habana"
        mun_valor = None
        fot_valor = None
        dep = None
        for filtro in Filtros:
            id = filtro.id
            valor = filtro.valor
            print("filtro id: ", id)
            print("filtro valor: ", valor)

            if id == "palabra_clave":
                p_clave_valor = valor
            if id == "precio_min":
                pr_min_valor = valor
            if id == "precio_max":
                pr_max_valor = valor
            if id == "departamento":
                dep = valor
            # if id == "provincia":
            #     prov_valor = valor
            # if id == "municipio":
            #     mun_valor = valor
            # if id == "fotos":
            #     if valor == 'Si' or 'si':
            #         fot_valor = True
        insertar_filtro(dep, p_clave_valor, pr_min_valor, pr_max_valor, prov_valor, mun_valor, fot_valor)
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "Se ha completado la accion de manera exitosa"
    )
    Filtros.clear()

    return ConversationHandler.END


def delete_all(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    eliminar_todos_los_filtros()
    query.edit_message_text("Se han eliminado todos los filtros")


def delete_filter(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    eliminar_filtro(query.data)
    query.answer()
    botones_filtro_borrar.clear()
    query.edit_message_text("Se ha elimindao satisfactoriamente el filtro")


def iniciar_lista_de_trabajo(upd, context):
    stop_threads.clear()
    stop_threads.append(False)
    upd.message.reply_text('Se ha iniciado la busqueda automatica , para detenerlo teclee /stop')
    global hilo_busqueda
    hilo_busqueda = threading.Thread(target=buscar, args=(upd, context,))
    hilo_busqueda.start()


def parar(upd):
    print(Hilo_status)
    Hilo_status.clear()
    Hilo_status.append("detenido")
    stop_threads.clear()
    stop_threads.append(True)
    hilo_busqueda.join()
    print('thread killed')
    upd.message.reply_text('Stopped!')


# ---->lista de comandos del bot

def start(update, context):
    """Iniciar el bot"""
    update.message.reply_text('Hi!')


def start_search(update: Updater, context):
    """Iniciar  el bot"""
    if Hilo_status[0] == 'funcionando':
        parar(upd=update)
    Hilo_status.clear()
    Hilo_status.append('funcionando')
    iniciar_lista_de_trabajo(update, context)


def stoped(update: Updater, context):
    """Detener el bot"""
    parar(upd=update)


def status(update: Updater, context):
    update.message.reply_text(Hilo_status[0])


def add(update: Update, context: CallbackContext) -> None:
    """Anadir una nueva regla o filtro  ."""
    update.message.reply_text('Selecciona el departamento donde buscar:', reply_markup=markup_departamentos)
    return introducir_datos_filtro


def delete(update, context):
    """Eliminar una regla o filtro"""
    filtros = obtener_filtros()
    for filtro in filtros:
        id = filtro[0]
        palabra_clave = filtro[2]

        botones_filtro_borrar.append([InlineKeyboardButton(str(palabra_clave), callback_data=id)])
    botones_filtro_borrar.append([InlineKeyboardButton(text="Borrar todos", callback_data='borrar todos')])
    botones_filtro_borrar.append([InlineKeyboardButton("Cancelar", callback_data='Cancelar')])
    markup = InlineKeyboardMarkup(botones_filtro_borrar)
    update.message.reply_text('Seleccione el filtro a borrar', reply_markup=markup)


def test(update, context):
    """Testear el bot y enviar su informe de estado"""
    update.message.reply_text('Tranquilo sigo vivo')


def show(update, context):
    """Mostrar todas las reglas o filtros activos."""

    filtros = obtener_filtros()
    for filtro in filtros:
        id = filtro[0]
        dep = filtro[1]
        palabra_clave = filtro[2]
        precio_min = filtro[3]
        precio_max = filtro[4]
        provincia = filtro[5]
        municipio = filtro[6]
        fotos = filtro[7]
        mensaje = (
                "id: " + str(id) + "\n" +
                "departamento: " + str(dep) + "\n" +
                "palabra_clave: " + (palabra_clave) + "\n" +
                "precio_min: " + str(precio_min) + "\n" +
                "precio_max: " + str(precio_max) + "\n" +
                "provincia: " + str(provincia) + "\n" +
                "municipio: " + str(municipio) + "\n" +
                "fotos: " + str(fotos) + "\n"

        )
        update.message.reply_text(mensaje)


def help(update, context):
    """Mostrar la ayuda del bot"""
    update.message.reply_text('Help!')


def ads_admin(update, context):
    """admin del bot"""
    bot = context.bot
    mi_id = 1122914981
    if str(update.message.chat_id) == str(mi_id):
        # sendDocument
        doc = open('log.txt', 'rb')
        bot.send_document(mi_id, doc)


def Listener(update, context):
    bot = context.bot
    update_msg = getattr(update, "message", None)  # get info of message
    msg_id = update_msg.message_id  # get recently message id
    groupId = update.message.chat_id
    userName = update.effective_user['first_name']
    user_id = update.effective_user['id']  # get user id
    text = update.message.text  # get message sent to the bot
    logger.info(f"[{user_id}][{userName}]:{text}.")
    log_data = "[" + str(userName) + "]: " + str(text) + "\n"
    with open("log.txt", "a") as log_file:
        log_file.write(str(log_data))
        log_file.close()


def error(update, context):
    """Log Errors caused by Updates."""
    err = context.error
    logger.warning('Update "%s" caused error "%s"', update, err)
    time.sleep(5)
    with open("log.txt", "a") as log_file:
        log_file.write("Error:" + str(err))
        log_file.close()
    update.message.reply_text(err)


def not_comand(update, context):
    pass


def main():
    """Start the bot."""
    updater = Updater(TOKEN, use_context=True)

    # Get the dispatcher to register handlers

    dp = updater.dispatcher

    # Comandos
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("start_search", start_search, pass_chat_data=True))
    dp.add_handler(CommandHandler("stop", stoped))
    dp.add_handler(CommandHandler("delete", delete))
    dp.add_handler(CommandHandler("show", show))
    dp.add_handler(CommandHandler("test", test))
    dp.add_handler(CommandHandler("help", help))
    dp.add_handler(CommandHandler("ads_admin", ads_admin))
    dp.add_handler(CommandHandler("status", status))

    dp.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler('add', add)
        ],
        states={
            introducir_datos_filtro: [
                CallbackQueryHandler(palabra_clave, pattern='palabra_clave'),
                CallbackQueryHandler(precio_min, pattern='precio_min'),
                CallbackQueryHandler(precio_max, pattern='precio_max'),
                CallbackQueryHandler(departamento, pattern='compra-venta'),
                CallbackQueryHandler(departamento, pattern='autos'),
                CallbackQueryHandler(departamento, pattern='vivienda'),
                CallbackQueryHandler(departamento, pattern='empleos'),
                CallbackQueryHandler(departamento, pattern='servicios'),
                CallbackQueryHandler(departamento, pattern='computadoras'),
                # CallbackQueryHandler(provincia, pattern='provincia'),
                # CallbackQueryHandler(municipio, pattern='municipio'),
                # CallbackQueryHandler(fotos, pattern='fotos'),
                MessageHandler(Filters.text, received_information),
                CallbackQueryHandler(done, pattern='Aceptar'),
                CallbackQueryHandler(cancel, pattern='Cancelar'),
            ],

        },
        fallbacks=[],
    ))
    dp.add_handler(CallbackQueryHandler(cancel, pattern='Cancelar'))
    dp.add_handler(CallbackQueryHandler(delete_all, pattern='borrar todos'))
    dp.add_handler(CallbackQueryHandler(delete_filter))
    dp.add_handler(MessageHandler(Filters.text, Listener))
    dp.add_handler(MessageHandler(Filters.photo | Filters.audio | Filters.voice |
                                  Filters.video | Filters.sticker | Filters.document | Filters.location | Filters.contact,
                                  not_comand))

    # log all errors
    dp.add_error_handler(error)

    updater.start_polling()

    # PORT = int(os.environ.get("PORT", "8443"))
    # HEROKU_APP_NAME = os.environ.get("HEROKU_APP_NAME")
    # updater.start_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN)
    # updater.bot.set_webhook("https://{}.herokuapp.com/{}".format(HEROKU_APP_NAME, TOKEN))

    updater.idle()


if __name__ == '__main__':
    main()
