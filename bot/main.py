"""
Bot Main Module
---------------
Entry point for the Revolico Telegram bot. Sets up the bot, loads handlers, and starts polling.
All code is documented and follows PEP8 and best practices.
"""

import os
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, Filters
from utils.logger import setup_logger
from .handlers import (
    start, help_command, add_user_handler, user_received_handler, show_user_handler,
    search_handler, startsearch_command, stopsearch_command, question_handler, llm_message_handler
)
from dotenv import load_dotenv

def main() -> None:
    """
    Starts the Telegram bot, loads handlers, and begins polling.
    """
    # Load environment variables from .env if present
    load_dotenv()
    logger = setup_logger('revolico_bot', log_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'log.txt'))
    token = os.getenv('TOKEN')
    if not token:
        logger.error('TOKEN not found in environment variables.')
        return
    updater = Updater(token, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('help', help_command))
    dp.add_handler(CommandHandler('adduser', add_user_handler))
    dp.add_handler(CommandHandler('showusers', show_user_handler))
    dp.add_handler(search_handler)
    dp.add_handler(CommandHandler('startsearch', startsearch_command))
    dp.add_handler(CommandHandler('stopsearch', stopsearch_command))
    dp.add_handler(question_handler)
    dp.add_handler(llm_message_handler)
    # Add other handlers and ConversationHandlers as needed

    updater.start_polling()
    logger.info('Bot started')
    updater.idle()

if __name__ == '__main__':
    main() 