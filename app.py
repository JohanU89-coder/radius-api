# app.py (Código Original Restaurado)

import os
import pymysql
from flask import Flask, jsonify, request

app = Flask(__name__)

# --- Configuración de la Base de Datos ---
# Se leen desde las variables de entorno de tu Azure App Service
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')

def get_db_connection():
    """Crea una conexión a la base de datos."""
    try:
        connection = pymysql.connect(host=DB_HOST,
                                     user=DB_USER,
                                     password=DB_PASSWORD,
                                     database=DB_NAME,
                                     cursorclass=pymysql.cursors.DictCursor,
                                     connect_timeout=10) # Añadido timeout para fallar más rápido
        return connection
    except pymysql.MySQLError as e:
        print(f"ERROR: No se pudo conectar a la base de datos: {e}")
        return None

# --- Endpoints de la API ---

@app.route('/usuarios', methods=['POST'])
def create_user():
    """
    Crea un nuevo usuario con sus atributos.
    Requiere un JSON con: username, password.
    Opcional: simultaneous_use, session_timeout.
    """
    data = request.get_json()
    if not data or not 'username' in data or not 'password' in data:
        return jsonify({'error': 'Se requieren nombre de usuario y contraseña'}), 400

    username = data['username']
    password = data['password']
    simultaneous_use = data.get('simultaneous_use') # Opcional
    session_timeout = data.get('session_timeout') # Opcional

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
    
    try:
        with conn.cursor() as cursor:
            # Insertar la contraseña en radcheck
            sql_pass = "INSERT INTO `radcheck` (`username`, `attribute`, `op`, `value`) VALUES (%s, 'Cleartext-Password', ':=', %s)"
            cursor.execute(sql_pass, (username, password))

            # Insertar límite de sesiones si se proporcionó
            if simultaneous_use is not None:
                sql_simul = "INSERT INTO `radcheck` (`username`, `attribute`, `op`, `value`) VALUES (%s, 'Simultaneous-Use', ':=', %s)"
                cursor.execute(sql_simul, (username, str(simultaneous_use)))

            # Insertar tiempo límite de conexión si se proporcionó (esto va en radreply)
            if session_timeout is not None:
                sql_timeout = "INSERT INTO `radreply` (`username`, `attribute`, `op`, `value`) VALUES (%s, 'Session-Timeout', ':=', %s)"
                cursor.execute(sql_timeout, (username, str(session_timeout)))

        conn.commit()
        return jsonify({'success': f'Usuario {username} creado correctamente'}), 201
    except pymysql.MySQLError as e:
        conn.rollback()
        return jsonify({'error': f'Error de base de datos: {e}'}), 500
    finally:
        conn.close()


@app.route('/usuarios/<username>', methods=['GET'])
def get_user(username):
    """Verifica un usuario y devuelve sus atributos."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
        
    try:
        with conn.cursor() as cursor:
            # Obtener atributos de radcheck
            cursor.execute("SELECT attribute, op, value FROM radcheck WHERE username = %s", (username,))
            check_attrs = cursor.fetchall()

            # Obtener atributos de radreply
            cursor.execute("SELECT attribute, op, value FROM radreply WHERE username = %s", (username,))
            reply_attrs = cursor.fetchall()

            if not check_attrs and not reply_attrs:
                return jsonify({'error': 'Usuario no encontrado'}), 404

            return jsonify({
                'username': username,
                'check_attributes': check_attrs,
                'reply_attributes': reply_attrs
            })
    finally:
        conn.close()


@app.route('/usuarios/<username>', methods=['DELETE'])
def delete_user(username):
    """Elimina un usuario de todas las tablas relevantes."""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
        
    try:
        with conn.cursor() as cursor:
            # Eliminar de las 4 tablas principales para una limpieza completa
            cursor.execute("DELETE FROM radcheck WHERE username = %s", (username,))
            cursor.execute("DELETE FROM radreply WHERE username = %s", (username,))
            cursor.execute("DELETE FROM radusergroup WHERE username = %s", (username,))
            cursor.execute("DELETE FROM radacct WHERE username = %s", (username,))
        
        conn.commit()
        if cursor.rowcount > 0:
            return jsonify({'success': f'Usuario {username} eliminado correctamente'})
        else:
            return jsonify({'error': 'Usuario no encontrado o ya eliminado'}), 404
    except pymysql.MySQLError as e:
        conn.rollback()
        return jsonify({'error': f'Error de base de datos: {e}'}), 500
    finally:
        conn.close()

@app.route('/', methods=['GET'])
def bienvenida():
    """
    Endpoint de bienvenida para confirmar que la API está funcionando.
    """
    return jsonify({"mensaje": "¡Bienvenido a la API de Radius!"})

