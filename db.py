import sqlite3
from sqlite3 import Error


def sql_connection():
    try:
        conexion = sqlite3.connect('anuncios.db')
        return conexion
    except Error:
        print(Error)


def crear_tabla_filtros():
    try:
        conexion = sql_connection()
        cursor = conexion.cursor()

        cursor.execute(
            "CREATE TABLE IF NOT EXISTS filtros(id integer PRIMARY KEY, departamento text,palabra_clave text, precio_min integer, precio_max integer, provincia text, municipio text, fotos text)")
        conexion.commit()
        conexion.close()
    except Exception as Error:
        print(Error)


def insertar_filtro(departamento,palabra_clave, precio_min=None, precio_max=None, provincia=None, municipio=None, fotos=False):
    try:
        conexion = sql_connection()
        cursor = conexion.cursor()
        cursor.execute(
            'INSERT INTO filtros( departamento,palabra_clave, precio_min, precio_max, provincia, municipio, fotos) VALUES( ?,?, ?, ?, ?, ?,?)',
            (departamento, palabra_clave, precio_min, precio_max, provincia, municipio, fotos))

        conexion.commit()
    except Exception as e:
        print(e)


def obtener_filtros():
    try:
        conexion = sql_connection()
        cursor = conexion.cursor()
        cursor = conexion.execute("SELECT * from filtros")
        filtros = cursor.fetchall()
        conexion.close()
        return filtros
    except Exception as e:
        print(e)


def actualizar_filtro(id, param, value):
    try:
        conexion = sql_connection()
        cursor = conexion.cursor()
        query = 'UPDATE filtros set ' + str(param) + ' = ' + str(value) + ' where id = ' + str(id)
        cursor = conexion.execute(query)
        conexion.commit()

        conexion.close()
    except Exception as e:
        print(e)


def eliminar_filtro(id):
    try:
        conexion = sql_connection()

        cursor = conexion.cursor()
        cursor = conexion.execute("DELETE from filtros where id = ?;", id)
        conexion.commit()

        conexion.close()

    except Exception as e:
        print(e)


def eliminar_todos_los_filtros():
    try:
        conexion = sql_connection()

        cursor = conexion.cursor()
        cursor.execute("DROP TABLE IF EXISTS filtros")
        crear_tabla_filtros()
        conexion.commit()

        conexion.close()

    except Exception as e:
        print(e)


def crear_tabla_anuncio():
    try:
        conexion = sql_connection()
        cursor = conexion.cursor()

        cursor.execute("DROP TABLE IF EXISTS anuncios")
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS anuncios(id integer PRIMARY KEY, url text, titulo text, precio text, descripcion text, fecha text, ubicacion text,foto text)")
        conexion.commit()
        conexion.close()
    except Exception as Error:
        print(Error)


def insertar_anuncio(url, titulo, precio, descripcion, fecha, ubicacion, foto):
    try:
        conexion = sql_connection()
        cursor = conexion.cursor()
        cursor.execute(
            'INSERT INTO anuncios( url, titulo, precio, descripcion, fecha, ubicacion, foto) VALUES( ?, ?, ?, ?, ?,?,?)',
            (url, titulo, precio, descripcion, fecha, ubicacion, foto))

        conexion.commit()
    except Exception as e:
        print(e)


def obtener_anuncios():
    try:
        conexion = sql_connection()
        cursor = conexion.cursor()
        cursor = conexion.execute("SELECT * from anuncios")
        anuncios = cursor.fetchall()
        conexion.close()
        return anuncios
    except Exception as e:
        print(e)



