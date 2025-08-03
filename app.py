# app.py (Logging Robusto e Integración Final con daloRADIUS en la tabla userinfo)

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
    Opcional: firstname, lastname, email, simultaneous_use, session_timeout.
    """
    app.logger.info("Recibida petición POST en /usuarios")
    data = request.get_json()
    if not data or not 'username' in data or not 'password' in data:
        app.logger.warning("Petición POST inválida: faltan username o password.")
        return jsonify({'error': 'Se requieren nombre de usuario y contraseña'}), 400

    # Datos para FreeRADIUS
    username = data['username']
    password = data['password']
    simultaneous_use = data.get('simultaneous_use')
    session_timeout = data.get('session_timeout')

    # Datos opcionales para daloRADIUS (userinfo)
    firstname = data.get('firstname', '')
    lastname = data.get('lastname', '')
    email = data.get('email', '')

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
    
    try:
        with conn.cursor() as cursor:
            app.logger.info(f"Insertando usuario {username} en la base de datos.")
            
            # --- INSERCIÓN PARA DALORADIUS (en la tabla userinfo) ---
            sql_user_dalo = "INSERT INTO `userinfo` (`username`, `firstname`, `lastname`, `email`, `creationdate`, `creationby`) VALUES (%s, %s, %s, %s, %s, %s)"
            cursor.execute(sql_user_dalo, (username, firstname, lastname, email, datetime.now(), 'api'))
            
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

@app.route('/usuarios', methods=['GET'])
def get_all_users():
    """Obtiene una lista de todos los usuarios de la tabla userinfo."""
    app.logger.info("Recibida petición GET para /usuarios (todos)")
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
        
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT username, firstname, lastname, email, creationdate FROM userinfo")
            users = cursor.fetchall()
            return jsonify(users)
    except pymysql.MySQLError as e:
        app.logger.error(f"Error de base de datos al obtener todos los usuarios: {e}")
        return jsonify({'error': f'Error de base de datos: {e}'}), 500
    finally:
        if conn:
            conn.close()

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

@app.route('/usuarios/<username>', methods=['PATCH'])
def update_user(username):
    """
    Actualiza los datos de un usuario existente.
    Permite cambiar la contraseña, datos de contacto y atributos de RADIUS.
    """
    app.logger.info(f"Recibida petición PATCH para /usuarios/{username}")
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No se proporcionaron datos para actualizar'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500

    try:
        with conn.cursor() as cursor:
            # Actualizar datos en userinfo
            if 'firstname' in data:
                cursor.execute("UPDATE userinfo SET firstname = %s WHERE username = %s", (data['firstname'], username))
            if 'lastname' in data:
                cursor.execute("UPDATE userinfo SET lastname = %s WHERE username = %s", (data['lastname'], username))
            if 'email' in data:
                cursor.execute("UPDATE userinfo SET email = %s WHERE username = %s", (data['email'], username))

            # Actualizar contraseña en radcheck
            if 'password' in data:
                cursor.execute("UPDATE radcheck SET value = %s WHERE username = %s AND attribute = 'Cleartext-Password'", (data['password'], username))
            
            # Actualizar otros atributos de radcheck
            if 'simultaneous_use' in data:
                cursor.execute("UPDATE radcheck SET value = %s WHERE username = %s AND attribute = 'Simultaneous-Use'", (str(data['simultaneous_use']), username))

            # Actualizar atributos de radreply
            if 'session_timeout' in data:
                cursor.execute("UPDATE radreply SET value = %s WHERE username = %s AND attribute = 'Session-Timeout'", (str(data['session_timeout']), username))
        
        conn.commit()
        app.logger.info(f"Usuario {username} actualizado exitosamente.")
        return jsonify({'success': f'Usuario {username} actualizado correctamente'})
    except pymysql.MySQLError as e:
        app.logger.error(f"Error de base de datos al actualizar usuario {username}: {e}")
        conn.rollback()
        return jsonify({'error': f'Error de base de datos: {e}'}), 500
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
            cursor.execute("DELETE FROM userinfo WHERE username = %s", (username,))
            cursor.execute("DELETE FROM radcheck WHERE username = %s", (username,))
            cursor.execute("DELETE FROM radreply WHERE username = %s", (username,))
            cursor.execute("DELETE FROM radusergroup WHERE username = %s", (username,))
            cursor.execute("DELETE FROM radacct WHERE username = %s", (username,))
        
        conn.commit()
        if cursor.rowcount > 0:
            return jsonify({'success': f'Usuario {username} eliminado permanentemente'})
        else:
            return jsonify({'error': 'Usuario no encontrado o ya eliminado'}), 404
    except pymysql.MySQLError as e:
        app.logger.error(f"Error de base de datos al eliminar usuario {username}: {e}")
        conn.rollback()
        return jsonify({'error': f'Error de base de datos: {e}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/usuarios/<username>/desactivar', methods=['POST'])
def deactivate_user(username):
    """Desactiva una cuenta de usuario añadiendo Auth-Type := Reject."""
    app.logger.info(f"Recibida petición para DESACTIVAR al usuario {username}")
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
    
    try:
        with conn.cursor() as cursor:
            # Primero, eliminar cualquier regla 'Auth-Type' existente para evitar duplicados
            cursor.execute("DELETE FROM radcheck WHERE username = %s AND attribute = 'Auth-Type'", (username,))
            
            # Insertar la regla para rechazar la autenticación
            sql = "INSERT INTO `radcheck` (`username`, `attribute`, `op`, `value`) VALUES (%s, 'Auth-Type', ':=', 'Reject')"
            cursor.execute(sql, (username,))
        
        conn.commit()
        app.logger.info(f"Usuario {username} desactivado exitosamente.")
        return jsonify({'success': f'Usuario {username} desactivado correctamente'})
    except pymysql.MySQLError as e:
        app.logger.error(f"Error de base de datos al desactivar usuario {username}: {e}")
        conn.rollback()
        return jsonify({'error': f'Error de base de datos: {e}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/usuarios/<username>/activar', methods=['POST'])
def activate_user(username):
    """Reactiva una cuenta de usuario eliminando la regla Auth-Type := Reject."""
    app.logger.info(f"Recibida petición para ACTIVAR al usuario {username}")
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'No se pudo conectar a la base de datos'}), 500
    
    try:
        with conn.cursor() as cursor:
            # Simplemente eliminar la regla que rechaza la autenticación
            sql = "DELETE FROM radcheck WHERE username = %s AND attribute = 'Auth-Type'"
            cursor.execute(sql, (username,))
        
        conn.commit()
        app.logger.info(f"Usuario {username} activado exitosamente.")
        return jsonify({'success': f'Usuario {username} activado correctamente'})
    except pymysql.MySQLError as e:
        app.logger.error(f"Error de base de datos al activar usuario {username}: {e}")
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
