import unittest
import sqlite3
from unittest.mock import patch
import sys
import os

# Add the parent directory to sys.path to allow db module import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import db # Now db.py should be importable

class TestDatabaseOperations(unittest.TestCase):

    def setUp(self):
        # Create an in-memory SQLite database for testing
        self.mock_conn = sqlite3.connect(':memory:')
        
        # Patch 'db.sql_connection' to return our in-memory connection
        # This ensures that all db_module functions use this connection
        self.patcher = patch('db.sql_connection', return_value=self.mock_conn)
        self.mock_sql_connection = self.patcher.start()

        # Create tables using the db_module functions (which now use the mocked connection)
        db.crear_tabla_filtros()
        db.crear_tabla_sent_ads()

    def tearDown(self):
        # Stop the patcher
        self.patcher.stop()
        # Close the in-memory connection
        self.mock_conn.close()

    # --- Test Cases for Filter Operations ---

    def test_insert_and_get_filter(self):
        db.insertar_filtro("compra-venta", "test_keyword", 10, 100, "La Habana", "Plaza", True)
        filtros = db.obtener_filtros()
        self.assertEqual(len(filtros), 1)
        filtro = filtros[0]
        # ID (auto-increment), dep, pk, pmin, pmax, prov, mun, fotos
        self.assertEqual(filtro[1], "compra-venta")
        self.assertEqual(filtro[2], "test_keyword")
        self.assertEqual(filtro[3], 10)
        self.assertEqual(filtro[4], 100)
        self.assertEqual(filtro[5], "La Habana")
        self.assertEqual(filtro[6], "Plaza")
        self.assertEqual(filtro[7], True) # Stored as 1 (True) or 0 (False) if TEXT, or boolean if type affinity works

    def test_get_multiple_filters(self):
        db.insertar_filtro("autos", "carro", 500, 5000, "Matanzas", "Cardenas", False)
        db.insertar_filtro("vivienda", "casa playa", 20000, 100000, "Pinar del Rio", "Viñales", True)
        filtros = db.obtener_filtros()
        self.assertEqual(len(filtros), 2)
        # Optionally, check contents more thoroughly
        self.assertEqual(filtros[0][2], "carro")
        self.assertEqual(filtros[1][2], "casa playa")


    def test_get_empty_filters(self):
        filtros = db.obtener_filtros()
        self.assertEqual(len(filtros), 0)

    def test_delete_filter(self):
        db.insertar_filtro("servicios", "electricista", None, None, "Habana", None, False)
        filtros_before = db.obtener_filtros()
        self.assertEqual(len(filtros_before), 1)
        filter_id_to_delete = filtros_before[0][0] # Get the ID of the inserted filter
        
        db.eliminar_filtro(filter_id_to_delete)
        
        filtros_after = db.obtener_filtros()
        self.assertEqual(len(filtros_after), 0)

    def test_delete_all_filters(self):
        db.insertar_filtro("compra-venta", "ganga1", 1, 2, "Habana", None, False)
        db.insertar_filtro("compra-venta", "ganga2", 3, 4, "Habana", None, True)
        self.assertEqual(len(db.obtener_filtros()), 2)
        
        db.eliminar_todos_los_filtros() # This also recreates the table
        
        filtros_after = db.obtener_filtros()
        self.assertEqual(len(filtros_after), 0)
        # Check table exists after delete all (it should be recreated)
        cursor = self.mock_conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='filtros';")
        self.assertIsNotNone(cursor.fetchone())


    def test_insert_filter_with_defaults(self):
        # Only departamento and palabra_clave are strictly required by some interpretations
        # The DB schema allows NULLs for others, and Python function provides defaults
        db.insertar_filtro("computadoras", "laptop i7")
        filtros = db.obtener_filtros()
        self.assertEqual(len(filtros), 1)
        filtro = filtros[0]
        self.assertEqual(filtro[1], "computadoras")
        self.assertEqual(filtro[2], "laptop i7")
        self.assertIsNone(filtro[3])  # precio_min
        self.assertIsNone(filtro[4])  # precio_max
        self.assertIsNone(filtro[5])  # provincia (None in func default)
        self.assertIsNone(filtro[6])  # municipio
        self.assertEqual(filtro[7], False) # fotos (False in func default)

    def test_eliminar_non_existent_filter(self):
        # Attempt to delete a filter that doesn't exist
        # The db.eliminar_filtro function should not raise an error.
        try:
            db.eliminar_filtro(999) # Assuming 999 does not exist
        except Exception as e:
            self.fail(f"eliminar_filtro raised an exception for non-existent ID: {e}")
        
        # Ensure no filters were accidentally deleted or created
        filtros = db.obtener_filtros()
        self.assertEqual(len(filtros), 0)

    # --- Test Cases for Sent Ad Operations ---

    def test_add_and_is_ad_sent(self):
        test_url = "https://www.revolico.com/test-ad-123.html"
        self.assertFalse(db.is_ad_sent(test_url), "Ad should not be marked as sent initially.")
        
        db.add_sent_ad(test_url)
        self.assertTrue(db.is_ad_sent(test_url), "Ad should be marked as sent after adding.")

    def test_is_ad_not_sent(self):
        test_url = "https://www.revolico.com/another-ad-456.html"
        self.assertFalse(db.is_ad_sent(test_url), "Ad not added should not be marked as sent.")

    def test_add_duplicate_ad_url(self):
        test_url = "https://www.revolico.com/duplicate-ad-789.html"
        db.add_sent_ad(test_url) # First add
        db.add_sent_ad(test_url) # Second add (should be ignored by INSERT OR IGNORE)
        
        # Verify it's marked as sent
        self.assertTrue(db.is_ad_sent(test_url))
        
        # Verify only one entry in the database
        cursor = self.mock_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sent_ads WHERE url = ?", (test_url,))
        count = cursor.fetchone()[0]
        self.assertEqual(count, 1, "Duplicate URL should result in only one entry in sent_ads table.")

    def test_is_ad_sent_after_recreating_table(self):
        # This tests if is_ad_sent correctly handles table creation if it was missing
        # (though setUp already creates it, this checks the internal robustness if called standalone)
        test_url = "https://www.revolico.com/ad-after-recreate.html"
        
        # Simulate table not existing by dropping it (then is_ad_sent should recreate it)
        # Note: This is a bit of a hacky way to test the internal resilience.
        # The db.py's is_ad_sent has a clause to try creating the table if it's missing.
        
        # We need to stop the main patcher to do this, then restart it, or use a different connection for this
        self.patcher.stop() # Stop main patch
        
        # Use a fresh in-memory for this specific check, or drop from self.mock_conn
        # For simplicity, let's assume db.is_ad_sent will use a new connection if sql_connection is called
        # and our patcher is stopped. So, we need to re-patch it to a connection where table doesn't exist.
        
        temp_conn = sqlite3.connect(':memory:') # A connection where sent_ads definitely doesn't exist
        
        with patch('db.sql_connection', return_value=temp_conn) as temp_mock_sql_connection:
            # At this point, if is_ad_sent is called, it uses temp_conn
            # The table 'sent_ads' does not exist in temp_conn
            self.assertFalse(db.is_ad_sent(test_url), "Ad should not be sent in a fresh DB where table might not exist yet.")
            # is_ad_sent should have created the table if it was missing
            cursor = temp_conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sent_ads';")
            self.assertIsNotNone(cursor.fetchone(), "sent_ads table should have been created by is_ad_sent.")

            # Now add and check
            db.add_sent_ad(test_url) # This will use temp_conn (via the temp_mock_sql_connection)
            self.assertTrue(db.is_ad_sent(test_url), "Ad should be sent after adding, even if table was initially missing.")
        
        temp_conn.close()
        self.patcher.start() # Restart main patcher for other tests

if __name__ == '__main__':
    unittest.main()
