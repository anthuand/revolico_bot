"""
Authentication Module
--------------------
Efficient user authentication and admin authorization for the Telegram bot.
"""

from telegram import Update
from telegram.ext import ConversationHandler, CallbackContext
from typing import Set

ADMIN_ID = '1122914981'

class UserManager:
    """
    Manages user authorization and admin status.
    """
    def __init__(self) -> None:
        self.users: Set[str] = {ADMIN_ID}

    def is_admin(self, user_id: int) -> bool:
        """Returns True if the user is admin."""
        return str(user_id) == ADMIN_ID

    def is_authorized(self, user_id: int) -> bool:
        """Returns True if the user is authorized."""
        return str(user_id) in self.users

    def add_user(self, user_id: int) -> bool:
        """Adds a user to the authorized list if not present."""
        user_id_str = str(user_id)
        if user_id_str not in self.users:
            self.users.add(user_id_str)
            return True
        return False

    def get_users(self) -> Set[str]:
        """Returns the list of authorized users."""
        return self.users

user_manager = UserManager()

def authenticate(update: Update, context: CallbackContext) -> bool:
    """
    Checks if the user is authorized.
    """
    return user_manager.is_authorized(update.effective_user['id'])

def add_user_handler(update: Update, context: CallbackContext) -> int:
    """
    Handler to initiate adding a new user (admin only).
    """
    if user_manager.is_admin(update.message.chat_id):
        update.message.reply_text('Hello admin, please enter the user ID to add:')
        return 1  # add_users state
    else:
        update.message.reply_text('You do not have permission to add users!')
        return ConversationHandler.END

def user_received_handler(update: Update, context: CallbackContext) -> int:
    """
    Handler to receive and add a new user ID.
    """
    user = update.message.text
    if user_manager.add_user(user):
        update.message.reply_text('User added successfully. Here is the list:')
    else:
        update.message.reply_text('User already exists.')
    update.message.reply_text(str(user_manager.get_users()))
    return ConversationHandler.END

def show_user_handler(update: Update, context: CallbackContext) -> None:
    """
    Handler to show the list of authorized users.
    """
    update.message.reply_text(str(user_manager.get_users())) 