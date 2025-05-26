import sqlite3
import logging
from sqlite3 import Error

logger = logging.getLogger(__name__)

DATABASE_NAME = 'anuncios.db'

def get_db_connection():
    """
    Establishes a connection to the SQLite database.
    The database file will be created if it doesn't exist.
    Returns a connection object.
    """
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False) # check_same_thread=False for multi-thread access if needed by main thread and scraper thread differently.
        logger.info(f"Successfully connected to SQLite database: {DATABASE_NAME}")
    except Error as e:
        logger.error(f"Error connecting to SQLite database {DATABASE_NAME}: {e}", exc_info=True)
        raise
    return conn

def close_db_connection(conn):
    """Closes the database connection."""
    if conn:
        conn.close()
        logger.info(f"SQLite database connection to {DATABASE_NAME} closed.")

def execute_query(conn, query, params=None, commit=False, fetchone=False, fetchall=False):
    """
    Helper function to execute SQL queries.
    Manages cursor creation and closing.
    Returns the result of fetchone/fetchall if requested, or None.
    """
    if not conn:
        logger.error("Database connection is None. Cannot execute query.")
        return None
    
    cursor = None
    try:
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        if commit:
            conn.commit()
            logger.debug(f"Query executed and committed: {query[:100]}...")
        
        result = None
        if fetchone:
            result = cursor.fetchone()
        elif fetchall:
            result = cursor.fetchall()
        
        return result
    except Error as e:
        # For "database is locked" errors, more specific handling or retries might be needed.
        logger.error(f"Error executing query: {query[:100]}... Error: {e}", exc_info=True)
        return None 
    finally:
        if cursor:
            cursor.close()


def crear_tabla_filtros(conn):
    """Creates the 'filtros' table if it doesn't exist."""
    query = """
    CREATE TABLE IF NOT EXISTS filtros (
        id INTEGER PRIMARY KEY,
        departamento TEXT,
        palabra_clave TEXT,
        precio_min INTEGER,
        precio_max INTEGER,
        provincia TEXT,
        municipio TEXT,
        fotos TEXT 
    )
    """
    execute_query(conn, query, commit=True)
    logger.info("Table 'filtros' checked/created successfully.")


def insertar_filtro(conn, departamento, palabra_clave, precio_min=None, precio_max=None, provincia=None, municipio=None, fotos="False"):
    """Inserts a new filter into the 'filtros' table."""
    query = """
    INSERT INTO filtros (departamento, palabra_clave, precio_min, precio_max, provincia, municipio, fotos)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    fotos_text = str(fotos) 
    params = (departamento, palabra_clave, precio_min, precio_max, provincia, municipio, fotos_text)
    execute_query(conn, query, params, commit=True)
    logger.info(f"Filter inserted: '{palabra_clave}' in '{departamento}'")


def obtener_filtros(conn):
    """Retrieves all filters from the 'filtros' table."""
    query = "SELECT * FROM filtros"
    filtros = execute_query(conn, query, fetchall=True)
    if filtros is not None:
        logger.info(f"Retrieved {len(filtros)} filters from the database.")
    else:
        logger.warning("Failed to retrieve filters or table is empty.")
        return [] 
    return filtros


def actualizar_filtro(conn, filtro_id, param_name, param_value):
    """Updates a specific parameter of a filter by its ID."""
    valid_params = ["departamento", "palabra_clave", "precio_min", "precio_max", "provincia", "municipio", "fotos"]
    if param_name not in valid_params:
        logger.error(f"Invalid parameter name for updating filter: {param_name}")
        return

    if param_name == "fotos":
        param_value = str(param_value)

    query = f"UPDATE filtros SET {param_name} = ? WHERE id = ?"
    params = (param_value, filtro_id)
    execute_query(conn, query, params, commit=True)
    logger.info(f"Filter ID {filtro_id} updated. Set {param_name} to {param_value}.")


def eliminar_filtro(conn, filtro_id):
    """Deletes a filter from the 'filtros' table by its ID."""
    query = "DELETE FROM filtros WHERE id = ?"
    params = (filtro_id,)
    execute_query(conn, query, params, commit=True)
    logger.info(f"Filter with ID {filtro_id} deleted.")


def eliminar_todos_los_filtros(conn):
    """Drops and recreates the 'filtros' table."""
    execute_query(conn, "DROP TABLE IF EXISTS filtros", commit=True)
    logger.info("Table 'filtros' dropped.")
    crear_tabla_filtros(conn) 
    logger.info("All filters eliminated and table 'filtros' recreated.")


def crear_tabla_anuncio(conn):
    """
    Creates the 'anuncios' table.
    IMPORTANT: This function DROPS the 'anuncios' table if it already exists
    and then recreates it. This means all previously stored ads will be lost.
    This strategy is suitable if the table is meant to store only the results 
    of the most recent search operation. For accumulating ads, remove 'DROP TABLE'.
    """
    logger.warning("Dropping 'anuncios' table if it exists and recreating it. All previous ad data will be lost.")
    execute_query(conn, "DROP TABLE IF EXISTS anuncios", commit=True)
    
    query = """
    CREATE TABLE anuncios (
        id INTEGER PRIMARY KEY,
        url TEXT UNIQUE,
        titulo TEXT,
        precio TEXT,
        descripcion TEXT,
        fecha TEXT,
        ubicacion TEXT,
        foto TEXT,
        notified INTEGER DEFAULT 0 
    )
    """
    # Added 'notified' column to track if a notification has been sent for this ad.
    execute_query(conn, query, commit=True)
    logger.info("Table 'anuncios' created successfully (previous data dropped if any).")


def insertar_anuncio(conn, url, titulo, precio, descripcion, fecha, ubicacion, foto):
    """
    Inserts a new ad into the 'anuncios' table if it doesn't already exist based on URL.
    Returns the ID of the inserted row, or None if ignored or error.
    Sets 'notified' to 0 for new ads.
    """
    query = """
    INSERT OR IGNORE INTO anuncios (url, titulo, precio, descripcion, fecha, ubicacion, foto, notified)
    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
    """
    params = (url, titulo, precio, descripcion, fecha, ubicacion, foto)
    
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Ad inserted: {titulo[:50]}... (URL: {url})")
            return cursor.lastrowid # Return the id of the newly inserted ad
        else:
            logger.info(f"Ad with URL {url} already exists or was ignored, not inserted: {titulo[:50]}...")
            # If it already exists, we might want to fetch its ID if needed for 'notified' status check
            existing_id_cursor = conn.cursor()
            existing_id_cursor.execute("SELECT id FROM anuncios WHERE url = ?", (url,))
            row = existing_id_cursor.fetchone()
            existing_id_cursor.close()
            if row:
                return row[0] # Return ID of existing ad
            return None
    except Error as e:
        logger.error(f"Error inserting ad {titulo[:50]}... (URL: {url}): {e}", exc_info=True)
        return None
    finally:
        if cursor:
            cursor.close()

def marcar_anuncio_como_notificado(conn, ad_id):
    """Marks an ad as notified."""
    query = "UPDATE anuncios SET notified = 1 WHERE id = ?"
    execute_query(conn, query, (ad_id,), commit=True)
    logger.info(f"Ad with ID {ad_id} marked as notified.")

def obtener_anuncios_no_notificados(conn):
    """Retrieves all ads that have not yet been notified."""
    query = "SELECT * FROM anuncios WHERE notified = 0"
    anuncios = execute_query(conn, query, fetchall=True)
    if anuncios is not None:
        logger.info(f"Retrieved {len(anuncios)} unnotified ads from the database.")
    else:
        logger.warning("Failed to retrieve unnotified ads or table is empty.")
        return []
    return anuncios


def obtener_anuncios(conn): # Kept for general purpose if needed, but specific one is above
    """Retrieves all ads from the 'anuncios' table."""
    query = "SELECT * FROM anuncios"
    anuncios = execute_query(conn, query, fetchall=True)
    if anuncios is not None:
        logger.info(f"Retrieved {len(anuncios)} total ads from the database.")
    else:
        logger.warning("Failed to retrieve ads or table is empty.")
        return []
    return anuncios


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    db_connection = None 
    try:
        db_connection = get_db_connection()
        if db_connection:
            logger.info("--- Testing 'filtros' table ---")
            crear_tabla_filtros(db_connection)
            insertar_filtro(db_connection, "compra-venta", "laptop", precio_max=500, provincia="La Habana", fotos="True")
            
            logger.info("--- Testing 'anuncios' table ---")
            crear_tabla_anuncio(db_connection) 
            
            ad_id1 = insertar_anuncio(db_connection, "http://example.com/ad1", "Laptop Test", "300 USD", "Buena laptop", "Hoy", "Habana", "Sí")
            ad_id2 = insertar_anuncio(db_connection, "http://example.com/ad2", "PC Gamer", "1000 USD", "Super PC", "Ayer", "Vedado", "No")
            insertar_anuncio(db_connection, "http://example.com/ad1", "Laptop Test Duplicate", "350 USD", "Mejor laptop", "Hoy Mismo", "Playa", "Sí")

            logger.info(f"Ad ID1: {ad_id1}, Ad ID2: {ad_id2}")

            unnotified_ads = obtener_anuncios_no_notificados(db_connection)
            logger.info(f"Unnotified ads ({len(unnotified_ads)}):")
            for ad in unnotified_ads:
                logger.info(f"  {ad}")
                if ad_id1 and ad[0] == ad_id1 : # ad[0] is the id column
                    marcar_anuncio_como_notificado(db_connection, ad_id1)
            
            all_ads_after = obtener_anuncios(db_connection)
            logger.info(f"All ads after marking one as notified ({len(all_ads_after)}):")
            for ad in all_ads_after:
                logger.info(f"  {ad}")


    except Error as e_main:
        logger.error(f"An SQLite error occurred in the db.py main example: {e_main}", exc_info=True)
    except Exception as e_global:
        logger.error(f"A non-SQLite error occurred in db.py main example: {e_global}", exc_info=True)
    finally:
        if db_connection:
            close_db_connection(db_connection)

```
