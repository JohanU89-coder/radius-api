# app.py (Logging Robusto e Integración con daloRADIUS)

import os
import pymysql
import logging
from flask import Flask, jsonify, request
from datetime import datetime

# --- Configuración de Logging ---
# Esto asegura que los logs se muestren en la consola de Azure
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# --- Configuración de la Base de Datos ---
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')

def get_db_connection():
    """Crea una conexión a la base de datos."""
    try:
        app.logger.info("Intentando conectar a la base de datos...")
        connection = pymysql.connect(host=DB_HOST,
                                     user=DB_USER,
                                     password=DB_PASSWORD,
                                     database=DB_NAME,
                                     cursorclass=pymysql.cursors.DictCursor,
                                     connect_timeout=10)
        app.logger.info("¡Conexión a la base de datos exitosa!")
        return connection
    except pymysql.MySQLError as e:
        # Usamos app.logger.error para un registro más robusto
        app.logger.error(f"ERROR al conectar a la base de datos: {e}")
        return None

# --- Endpoints de la API ---

@app.route('/usuarios', methods=['POST'])
def create_user():
    """
    Crea un nuevo usuario con sus atributos, asegurando la visibilidad en daloRADIUS.
    Requiere: username, password.
    Opcional: simultaneous_use, session_timeout, company, owner.
    """
    app.logger.info("Recibida petición POST en /usuarios")
    data = request.get_json()
    if not data or not 'username' in data or not 'password' in data:
        app.logger.warning("Petición POST inválida: faltan username o password.")
        return jsonify({'error': 'Se requieren nombre de usuario y contraseña'}), 400

    username = data['username']
    password = data['password']
    simultaneous_use = data.get('simultaneous_use')
    session_timeout = data.get('session_timeout')
    company = data.get('company', 'Default Company') # Opcional, con valor por defecto
    owner = data.get('owner', 'api') # Opcional, para saber quién creó el usuario

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
    
    try:
        with conn.cursor() as cursor:
            app.logger.info(f"Insertando usuario {username} en la base de datos.")
            
            # --- INSERCIÓN PARA DALORADIUS ---
            # daloRADIUS usa la tabla 'users' para listar los usuarios en su interfaz.
            sql_user_dalo = "INSERT INTO `users` (`username`, `company`, `owner`, `creationdate`, `creationby`) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(sql_user_dalo, (username, company, owner, datetime.now(), 'api'))
            
            # --- Inserciones para FreeRADIUS ---
            sql_pass = "INSERT INTO `radcheck` (`username`, `attribute`, `op`, `value`) VALUES (%s, 'Cleartext-Password', ':=', %s)"
            cursor.execute(sql_pass, (username, password))

            if simultaneous_use is not None:
                sql_simul = "INSERT INTO `radcheck` (`username`, `attribute`, `op`, `value`) VALUES (%s, 'Simultaneous-Use', ':=', %s)"
                cursor.execute(sql_simul, (username, str(simultaneous_use)))

            if session_timeout is not None:
                sql_timeout = "INSERT INTO `radreply` (`username`, `attribute`, `op`, `value`) VALUES (%s, 'Session-Timeout', ':=', %s)"
                cursor.execute(sql_timeout, (username, str(session_timeout)))

        conn.commit()
        app.logger.info(f"Usuario {username} creado exitosamente.")
        return jsonify({'success': f'Usuario {username} creado correctamente'}), 201
    except pymysql.MySQLError as e:
        app.logger.error(f"Error de base de datos al crear usuario {username}: {e}")
        conn.rollback()
        return jsonify({'error': f'Error de base de datos: {e}'}), 500
    finally:
        if conn:
            conn.close()
            app.logger.info("Conexión a la base de datos cerrada.")

@app.route('/usuarios/<username>', methods=['GET'])
def get_user(username):
    """Verifica un usuario y devuelve sus atributos."""
    app.logger.info(f"Recibida petición GET para /usuarios/{username}")
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
        
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT attribute, op, value FROM radcheck WHERE username = %s", (username,))
            check_attrs = cursor.fetchall()
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
        if conn:
            conn.close()

@app.route('/usuarios/<username>', methods=['DELETE'])
def delete_user(username):
    """Elimina un usuario de todas las tablas relevantes, incluyendo la de daloRADIUS."""
    app.logger.info(f"Recibida petición DELETE para /usuarios/{username}")
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
        
    try:
        with conn.cursor() as cursor:
            # Eliminar de las tablas de FreeRADIUS y daloRADIUS para una limpieza completa
            cursor.execute("DELETE FROM users WHERE username = %s", (username,))
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
        app.logger.error(f"Error de base de datos al eliminar usuario {username}: {e}")
        conn.rollback()
        return jsonify({'error': f'Error de base de datos: {e}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/', methods=['GET'])
def bienvenida():
    """Endpoint de bienvenida para confirmar que la API está funcionando."""
    app.logger.info("Recibida petición GET en /")
    return jsonify({"mensaje": "¡Bienvenido a la API de Radius!"})