import sqlite3
from sqlite3 import Error


def sql_connection():
    try:
        # Ensure the database file is created in a persistent location if needed,
        # for now, it's in the current working directory.
        conexion = sqlite3.connect('anuncios.db')
        # print("Conectado a la Db") # Can be noisy
        return conexion
    except Error as e:
        print(f"Error connecting to database: {e}")
        return None

# --- Funciones para la tabla de Filtros ---
def crear_tabla_filtros():
    try:
        conexion = sql_connection()
        if conexion is None: return

        cursor = conexion.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS filtros(id integer PRIMARY KEY, departamento text,palabra_clave text, precio_min integer, precio_max integer, provincia text, municipio text, fotos text)")
        conexion.commit()
        print("Tabla 'filtros' verificada/creada.")
    except Error as e:
        print(f"Error en crear_tabla_filtros: {e}")
    finally:
        if conexion:
            conexion.close()


def insertar_filtro(departamento,palabra_clave, precio_min=None, precio_max=None, provincia=None, municipio=None, fotos=False):
    try:
        conexion = sql_connection()
        if conexion is None: return

        cursor = conexion.cursor()
        cursor.execute(
            'INSERT INTO filtros( departamento,palabra_clave, precio_min, precio_max, provincia, municipio, fotos) VALUES( ?,?, ?, ?, ?, ?,?)',
            (departamento, palabra_clave, precio_min, precio_max, provincia, municipio, fotos))
        conexion.commit()
        print("Filtro insertado en la DB.")
    except Error as e:
        print(f"Error en insertar_filtro: {e}")
    finally:
        if conexion:
            conexion.close()


def obtener_filtros():
    filtros = []
    try:
        conexion = sql_connection()
        if conexion is None: return filtros

        cursor = conexion.cursor()
        cursor.execute("SELECT * from filtros")
        filtros = cursor.fetchall()
        # print("Obtuve los filtros de la DB") # Can be noisy
    except Error as e:
        print(f"Error en obtener_filtros: {e}")
    finally:
        if conexion:
            conexion.close()
        return filtros


def actualizar_filtro(id, param, value):
    try:
        conexion = sql_connection()
        if conexion is None: return
        
        cursor = conexion.cursor()
        # Using f-string for table/column names and placeholders for values is safer
        query = f'UPDATE filtros SET {param} = ? WHERE id = ?'
        cursor.execute(query, (value, id))
        conexion.commit()
        print("Filtro actualizado.")
    except Error as e:
        print(f"Error en actualizar_filtro: {e}")
    finally:
        if conexion:
            conexion.close()


def eliminar_filtro(id_filtro): # Renamed id to id_filtro for clarity
    try:
        conexion = sql_connection()
        if conexion is None: return

        cursor = conexion.cursor()
        cursor.execute("DELETE FROM filtros WHERE id = ?;", (id_filtro,)) # Use tuple for single parameter
        conexion.commit()
        print(f"Filtro con id {id_filtro} eliminado.")
    except Error as e:
        print(f"Error en eliminar_filtro: {e}")
    finally:
        if conexion:
            conexion.close()


def eliminar_todos_los_filtros():
    try:
        conexion = sql_connection()
        if conexion is None: return

        cursor = conexion.cursor()
        cursor.execute("DROP TABLE IF EXISTS filtros")
        print("Tabla 'filtros' eliminada.")
        conexion.commit() # Commit drop before creating new
        crear_tabla_filtros() # Recreate the table
    except Error as e:
        print(f"Error en eliminar_todos_los_filtros: {e}")
    finally:
        if conexion:
            conexion.close()

# --- Funciones para la tabla de Anuncios Enviados (sent_ads) ---

def crear_tabla_sent_ads():
    """
    Crea la tabla 'sent_ads' si no existe.
    Esta tabla almacena las URLs de los anuncios que ya han sido enviados.
    """
    try:
        conexion = sql_connection()
        if conexion is None: return

        cursor = conexion.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sent_ads (
                url TEXT PRIMARY KEY,
                sent_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conexion.commit()
        print("Tabla 'sent_ads' verificada/creada.")
    except Error as e:
        print(f"Error en crear_tabla_sent_ads: {e}")
    finally:
        if conexion:
            conexion.close()

def add_sent_ad(url):
    """
    Añade una URL a la tabla 'sent_ads'.
    Utiliza INSERT OR IGNORE para evitar errores si la URL ya existe.
    """
    try:
        conexion = sql_connection()
        if conexion is None: return

        cursor = conexion.cursor()
        cursor.execute("INSERT OR IGNORE INTO sent_ads (url) VALUES (?)", (url,))
        conexion.commit()
        # print(f"URL {url} añadida/ignorada en sent_ads.") # Can be noisy
    except Error as e:
        print(f"Error en add_sent_ad para URL {url}: {e}")
    finally:
        if conexion:
            conexion.close()

def is_ad_sent(url):
    """
    Verifica si una URL ya existe en la tabla 'sent_ads'.
    Retorna True si la URL existe, False en caso contrario o si hay error.
    """
    is_sent = False
    try:
        conexion = sql_connection()
        if conexion is None: return is_sent

        cursor = conexion.cursor()
        # It's good practice to call crear_tabla_sent_ads here to ensure table exists,
        # or ensure it's called at bot startup. For now, assuming it's called.
        # If not, an operational error might occur if the table doesn't exist.
        # A more robust way:
        # cursor.execute("CREATE TABLE IF NOT EXISTS sent_ads (url TEXT PRIMARY KEY, sent_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")

        cursor.execute("SELECT 1 FROM sent_ads WHERE url = ?", (url,))
        if cursor.fetchone():
            is_sent = True
    except Error as e:
        print(f"Error en is_ad_sent para URL {url}: {e}")
        # Optionally, try to create table if it doesn't exist
        if "no such table" in str(e).lower():
            print("Tabla sent_ads no encontrada, intentando crearla.")
            crear_tabla_sent_ads() # Attempt to create it
            # Could retry the select here, or just return False for this call
    finally:
        if conexion:
            conexion.close()
        return is_sent

# Note: The old ad table functions (crear_tabla_anuncio, insertar_anuncio, obtener_anuncios)
# have been removed as per the subtask instructions.
# It's recommended that main.py calls crear_tabla_filtros() and crear_tabla_sent_ads()
# once at startup to ensure tables are set up.
