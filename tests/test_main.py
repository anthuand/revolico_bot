import unittest
from unittest.mock import patch, AsyncMock, MagicMock, PropertyMock
import asyncio
import threading
import io
import sys
import os
from datetime import datetime

# Add the parent directory to sys.path to allow main and db module import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from telegram import Update, User, Message, Chat, CallbackQuery
from telegram.ext import CallbackContext, ConversationHandler, Application

# Import functions and constants from main.py
# Note: Some globals like Users_id, hilo_status, stop_threads_event might need careful patching
# or re-initialization for tests if their state affects test outcomes.
import main

# Mock the db and scraper modules that main.py depends on
# This is a common pattern if these modules are not being tested here
# and we want to control their behavior.
db_mock = MagicMock()
scraper_mock = MagicMock()

# Apply patches at the module level if main.py imports them directly like 'import db'
# If it's 'from db import ...', patching specific functions might be needed inside tests.
# For this test, we'll assume main.py does 'import db' and 'import scraper'.
# If not, these patches might not work as expected for all main.py functions.
# It's often better to patch specific functions where they are looked up.
# e.g., @patch('main.db.insertar_filtro')

# We will patch specific functions from 'main's perspective.

class TestMainModule(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Reset or mock global states from main.py for each test if necessary
        main.Users_id = ["123", main.ADMIN_USER_ID] # Example authorized user and admin
        main.hilo_status[0] = 'detenido'
        main.stop_threads_event.clear()

        # Mock application and bot for context
        self.mock_bot = AsyncMock()
        self.mock_application = MagicMock(spec=Application)
        self.mock_application.bot = self.mock_bot
        self.mock_application.loop = asyncio.get_event_loop() # For run_coroutine_threadsafe
        
        # Store the thread instance if created by a test
        self.search_thread_instance_for_test = None


    def tearDown(self):
        # Clean up any threads started during tests
        if self.search_thread_instance_for_test and self.search_thread_instance_for_test.is_alive():
            main.stop_threads_event.set()
            self.search_thread_instance_for_test.join(timeout=1)
        main.stop_threads_event.clear() # Ensure it's cleared for the next test


    async def _create_mock_update_context(self, user_id="123", chat_id="123", message_text="", callback_data=None):
        mock_update = MagicMock(spec=Update)
        mock_update.effective_chat = MagicMock(spec=Chat)
        mock_update.effective_chat.id = chat_id
        mock_update.effective_user = MagicMock(spec=User)
        mock_update.effective_user.id = user_id
        mock_update.effective_user.first_name = "TestUser"

        if callback_data:
            mock_update.callback_query = AsyncMock(spec=CallbackQuery)
            mock_update.callback_query.data = callback_data
            mock_update.callback_query.message = MagicMock(spec=Message) # for edit_message_text
            mock_update.callback_query.message.chat_id = chat_id
            mock_update.callback_query.message.message_id = 12345
        else:
            mock_update.message = AsyncMock(spec=Message)
            mock_update.message.text = message_text
            mock_update.message.chat_id = chat_id
            mock_update.message.from_user = mock_update.effective_user
        
        mock_context = MagicMock(spec=CallbackContext)
        mock_context.bot = self.mock_bot
        mock_context.application = self.mock_application
        mock_context.user_data = {} # Fresh user_data for each call usually
        mock_context.chat_data = {}
        return mock_update, mock_context

    # --- Test is_user_authenticated (Synchronous) ---
    def test_is_user_authenticated(self):
        mock_update, _ = self_sync._create_mock_update_context_sync(user_id="123") # Need sync helper or adapt
        self.assertTrue(main.is_user_authenticated(mock_update, None))

        mock_update_unauth, _ = self_sync._create_mock_update_context_sync(user_id="999")
        self.assertFalse(main.is_user_authenticated(mock_update_unauth, None))
        
        with patch('main.Users_id', []): # Test with empty Users_id
            self.assertFalse(main.is_user_authenticated(mock_update, None))

    # --- Test Filter Creation Conversation Handler ---
    @patch('main.markup_departamentos', MagicMock()) # Mock global markup
    async def test_add_filter_command_entry(self):
        mock_update, mock_context = await self._create_mock_update_context(user_id=main.ADMIN_USER_ID)
        
        # Patching Users_id for this specific test, assuming ADMIN_USER_ID is in it
        with patch('main.Users_id', [main.ADMIN_USER_ID]):
            self.assertTrue(main.is_user_authenticated(mock_update, mock_context))
            next_state = await main.add_filter_command(mock_update, mock_context)
        
        mock_update.message.reply_text.assert_called_once_with(
            'Selecciona el departamento donde buscar:', reply_markup=main.markup_departamentos
        )
        self.assertEqual(next_state, main.DEPARTAMENTO_STATE)
        self.assertEqual(mock_context.user_data, {'current_filter_parts': {}})

    @patch('main.markup_filtro', MagicMock())
    async def test_select_departamento_callback(self):
        mock_update, mock_context = await self._create_mock_update_context(callback_data="compra-venta")
        mock_context.user_data['current_filter_parts'] = {} # Initialized by entry point

        next_state = await main.select_departamento_callback(mock_update, mock_context)

        mock_update.callback_query.answer.assert_called_once()
        mock_update.callback_query.edit_message_text.assert_called_once_with(
            text="Departamento: compra-venta. Ahora elige una opción o introduce detalles:", 
            reply_markup=main.markup_filtro
        )
        self.assertEqual(mock_context.user_data['current_filter_parts']['departamento'], "compra-venta")
        self.assertEqual(next_state, main.INTRODUCIR_DATOS_FILTRO)

    async def test_ask_for_palabra_clave_callback(self):
        mock_update, mock_context = await self._create_mock_update_context(callback_data="ask_palabra_clave")
        
        next_state = await main.ask_for_palabra_clave_callback(mock_update, mock_context)
        
        mock_update.callback_query.answer.assert_called_once()
        mock_update.callback_query.edit_message_text.assert_called_once() # Check text content if vital
        self.assertEqual(mock_context.user_data['current_filter_field_id'], 'palabra_clave')
        self.assertEqual(next_state, main.RECEIVED_INFO_STATE)

    @patch('main.markup_filtro', MagicMock())
    async def test_received_filter_information_text(self):
        mock_update, mock_context = await self._create_mock_update_context(message_text="test keyword")
        mock_context.user_data['current_filter_field_id'] = 'palabra_clave'
        mock_context.user_data['current_filter_parts'] = {'departamento': 'autos'}

        next_state = await main.received_filter_information_text(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        self.assertEqual(mock_context.user_data['current_filter_parts']['palabra_clave'], 'test keyword')
        self.assertIsNone(mock_context.user_data.get('current_filter_field_id')) # Should be cleared
        self.assertEqual(next_state, main.INTRODUCIR_DATOS_FILTRO)

    @patch('main.db.insertar_filtro')
    @patch('main.logger.info') # To check logging
    async def test_done_filter_creation_callback_success(self, mock_logger_info, mock_insertar_filtro):
        mock_update, mock_context = await self._create_mock_update_context(callback_data="done_filter_creation", user_id="test_user_id")
        mock_update.effective_user.first_name = "TestUserDone"
        mock_context.user_data['current_filter_parts'] = {
            'departamento': 'vivienda',
            'palabra_clave': 'casa grande',
            'precio_min': '10000'
        }
        
        next_state = await main.done_filter_creation_callback(mock_update, mock_context)

        mock_update.callback_query.answer.assert_called_once()
        mock_insertar_filtro.assert_called_once_with(
            'vivienda', 'casa grande', '10000', None, "La Habana", None, None
        )
        mock_update.callback_query.edit_message_text.assert_called_once_with("¡Filtro guardado exitosamente!")
        self.assertNotIn('current_filter_parts', mock_context.user_data) # Should be cleared
        mock_logger_info.assert_called() # Check if logging happened
        self.assertEqual(next_state, ConversationHandler.END)

    async def test_done_filter_creation_callback_fail_missing_fields(self):
        mock_update, mock_context = await self._create_mock_update_context(callback_data="done_filter_creation")
        mock_context.user_data['current_filter_parts'] = {'departamento': 'vivienda'} # Missing palabra_clave
        
        next_state = await main.done_filter_creation_callback(mock_update, mock_context)
        
        mock_update.callback_query.answer.assert_called_once()
        mock_update.callback_query.edit_message_text.assert_called_with(
            "Error: Departamento y Palabra Clave son requeridos. /cancel_filter e inténtalo de nuevo.",
            reply_markup=unittest.mock.ANY # or the specific markup if important
        )
        self.assertIn('current_filter_parts', mock_context.user_data) # Should not be cleared on this path
        self.assertEqual(next_state, main.INTRODUCIR_DATOS_FILTRO) # Or whatever state it returns to

    async def test_cancel_filter_creation_callback(self):
        mock_update, mock_context = await self._create_mock_update_context(callback_data="cancel_filter_creation")
        mock_context.user_data['current_filter_parts'] = {'departamento': 'test'}
        mock_context.user_data['current_filter_field_id'] = 'palabra_clave'

        next_state = await main.cancel_filter_creation_callback(mock_update, mock_context)

        mock_update.callback_query.answer.assert_called_once()
        mock_update.callback_query.edit_message_text.assert_called_once_with("Creación de filtro cancelada.")
        self.assertNotIn('current_filter_parts', mock_context.user_data)
        self.assertNotIn('current_filter_field_id', mock_context.user_data)
        self.assertEqual(next_state, ConversationHandler.END)

    # --- Test buscar_sync Core Logic ---
    # This requires more setup for mocking the environment buscar_sync runs in.
    # We are testing the synchronous function `buscar_sync` here.
    @patch('main.scraper.get_main_anuncios')
    @patch('main.db.obtener_filtros')
    @patch('main.db.is_ad_sent')
    @patch('main.db.add_sent_ad')
    @patch('main.asyncio.run_coroutine_threadsafe') # Key mock for bot calls
    def test_buscar_sync_new_ad_with_image(self, mock_run_coro, mock_add_sent, mock_is_sent, mock_get_filtros, mock_get_ads):
        # Setup: One filter, one new ad with image
        mock_get_filtros.return_value = [
            (1, 'compra', 'test keyword', None, None, 'Habana', None, None)
        ]
        mock_ad_data = {
            'url': 'http://example.com/ad1', 'titulo': 'Test Ad 1', 'precio': '100',
            'descripcion': 'Desc with test keyword', 'fecha': 'hace 5 segundos', 
            'ubicacion': 'Habana',
            'contacto': ('John Doe', '5551234', 'john@example.com'),
            'imagen': (b'imagedata', 'http://example.com/img.jpg')
        }
        mock_get_ads.return_value = [mock_ad_data]
        mock_is_sent.return_value = False # Ad is new

        # Mock initial update and bot for buscar_sync
        mock_initial_update_msg = MagicMock(spec=Message)
        mock_initial_update_msg.chat_id = "user_chat_id"
        
        mock_bot_sync = MagicMock() # This is the 'bot_instance' passed to buscar_sync
        
        # Mock the future returned by run_coroutine_threadsafe
        mock_future = MagicMock()
        mock_run_coro.return_value = mock_future

        stop_event_for_test = threading.Event()
        
        # Run buscar_sync for one iteration (or a very short time)
        # To do this, we'd need to control the loop inside buscar_sync.
        # One way: make it run once by having stop_event set after first ad.
        def side_effect_add_sent_ad(*args):
            stop_event_for_test.set() # Stop after first ad processed
        mock_add_sent.side_effect = side_effect_add_sent_ad

        loop = asyncio.new_event_loop() # A loop for the threadsafe calls
        
        buscar_thread = threading.Thread(target=main.buscar_sync, 
                                         args=(mock_initial_update_msg, mock_bot_sync, loop, stop_event_for_test))
        buscar_thread.start()
        buscar_thread.join(timeout=5) # Wait for thread to complete or timeout

        self.assertTrue(stop_event_for_test.is_set()) # Check if it tried to stop
        mock_get_filtros.assert_called_once()
        mock_get_ads.assert_called_once_with('compra', 'test keyword', None, None, 'Habana', None, None)
        mock_is_sent.assert_called_once_with('http://example.com/ad1')
        
        # Check that send_photo was called via run_coroutine_threadsafe
        # mock_run_coro would have been called twice (user, channel) if NOTIFICATION_CHANNEL_ID was set
        # For simplicity, let's assume NOTIFICATION_CHANNEL_ID is None or check calls accordingly
        
        # Check the coroutine passed to run_coroutine_threadsafe
        # This is a bit complex due to nested calls. We check if bot_sync.send_photo was the target.
        # The actual call to bot_sync.send_photo is what we want to verify args for.
        # Since run_coroutine_threadsafe is mocked, the actual bot.send_photo isn't called unless we make the mock_future execute it.

        # Simpler: check if add_sent_ad was called, implying message was "sent"
        mock_add_sent.assert_called_once_with('http://example.com/ad1')
        
        # Check that mock_run_coro was called (at least for user)
        self.assertGreaterEqual(mock_run_coro.call_count, 1)
        
        # The actual coroutine object passed to run_coroutine_threadsafe
        first_call_args = mock_run_coro.call_args_list[0][0]
        actual_coro_sent = first_call_args[0]
        
        # Check properties of the coroutine (if possible, or check the mock_bot_sync directly
        # if run_coroutine_threadsafe was not mocked and we mocked bot.send_photo with AsyncMock)
        # This part of testing is tricky with run_coroutine_threadsafe.
        # A common pattern is to mock the bot methods (e.g. bot_sync.send_photo = AsyncMock())
        # and then check that AsyncMock.
        # For now, relying on add_sent_ad call as a proxy for successful processing.

    # --- Test Start/Stop Search Commands ---
    @patch('main.threading.Thread')
    async def test_start_search_thread_command_authed(self, MockThread):
        mock_update, mock_context = await self._create_mock_update_context(user_id=main.ADMIN_USER_ID)
        main.hilo_status[0] = 'detenido' # Ensure it's stopped

        await main.start_search_thread_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once_with('Iniciando búsqueda automática... Para detenerla, teclee /stop_search')
        MockThread.assert_called_once()
        self.assertEqual(main.hilo_status[0], 'funcionando')
        self.assertFalse(main.stop_threads_event.is_set())
        # Store thread for teardown if needed
        self.search_thread_instance_for_test = MockThread.return_value


    async def test_start_search_thread_command_already_running(self):
        mock_update, mock_context = await self._create_mock_update_context(user_id=main.ADMIN_USER_ID)
        main.hilo_status[0] = 'funcionando'

        await main.start_search_thread_command(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once_with('La búsqueda automática ya está en ejecución. Usa /stop_search para detenerla primero.')


    async def test_stop_search_thread_command_authed_running(self):
        mock_update, mock_context = await self._create_mock_update_context(user_id=main.ADMIN_USER_ID)
        main.hilo_status[0] = 'funcionando'
        
        # Mock the thread instance for join
        mock_thread_instance = MagicMock(spec=threading.Thread)
        mock_thread_instance.is_alive.return_value = True
        mock_context.application.search_thread_instance = mock_thread_instance

        await main.stop_search_thread_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once_with('¡Búsqueda automática detenida!')
        self.assertTrue(main.stop_threads_event.is_set())
        mock_thread_instance.join.assert_called_once_with(timeout=10)
        self.assertEqual(main.hilo_status[0], 'detenido')

    # Helper for synchronous creation of update/context for non-async tests
    # This is a bit of a workaround because IsolatedAsyncioTestCase runs setUp async.
    class SyncTestHelpers:
        def _create_mock_update_context_sync(self, user_id="123", chat_id="123", message_text=""):
            mock_update = MagicMock(spec=Update)
            mock_update.effective_chat = MagicMock(spec=Chat)
            mock_update.effective_chat.id = chat_id
            mock_update.effective_user = MagicMock(spec=User)
            mock_update.effective_user.id = str(user_id) # Ensure string for comparison
            # ... other fields as needed by is_user_authenticated ...
            return mock_update, None # Context not really used by is_user_authenticated

    self_sync = SyncTestHelpers()


if __name__ == '__main__':
    # Important: To run IsolatedAsyncioTestCase tests, you typically run with `python -m unittest discover`
    # or use a test runner that supports asyncio.
    # If running this file directly, it might not work as expected without `asyncio.run(unittest.main())`
    # but `unittest.main()` should handle it in modern Python.
    unittest.main()
