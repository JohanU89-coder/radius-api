# app.py (Versión de depuración para aislar el problema)

import os
# import pymysql # Comentado temporalmente
from flask import Flask, jsonify, request

app = Flask(__name__)

# --- Simulación de Endpoints sin Base de Datos ---
# Estos endpoints nos permitirán ver si la aplicación Flask puede iniciarse por sí sola.

@app.route('/usuarios', methods=['POST'])
def create_user():
    """
    Simula la creación de un usuario. No se conecta a la BD.
    Devuelve un mensaje de éxito para confirmar que la petición llegó.
    """
    data = request.get_json()
    username = data.get('username', 'desconocido')
    print(f"DEBUG: Recibida petición para crear usuario: {username}")
    return jsonify({'success': f'Simulación: Usuario {username} habría sido creado'}), 201

@app.route('/usuarios/<username>', methods=['GET'])
def get_user(username):
    """
    Simula la obtención de un usuario. Devuelve datos de prueba.
    """
    print(f"DEBUG: Recibida petición para obtener usuario: {username}")
    return jsonify({
        'username': username,
        'check_attributes': [{'attribute': 'Simulated-Attribute', 'value': 'true'}],
        'reply_attributes': []
    })

@app.route('/usuarios/<username>', methods=['DELETE'])
def delete_user(username):
    """
    Simula la eliminación de un usuario.
    """
    print(f"DEBUG: Recibida petición para eliminar usuario: {username}")
    return jsonify({'success': f'Simulación: Usuario {username} habría sido eliminado'})

@app.route('/', methods=['GET'])
def bienvenida():
    """
    Un endpoint raíz simple para verificar fácilmente si la app está viva desde un navegador.
    """
    print("DEBUG: El endpoint de bienvenida fue llamado.")
    return jsonify({"mensaje": "¡La API de depuración está funcionando! La conexión a la base de datos ha sido desactivada temporalmente."})

if __name__ == '__main__':
    # Esta parte se usa para desarrollo local, no en Azure.
    app.run(debug=True)