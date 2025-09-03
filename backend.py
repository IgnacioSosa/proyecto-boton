import pandas as pd
from modules.database import DB_PATH, get_connection, init_db as database_init_db, check_registro_duplicate
from modules.auth import hash_password, verify_password, validate_password, create_user as auth_create_user, login_user as auth_login_user

# Función wrapper para mantener compatibilidad con el código existente
def create_user(username, password, nombre=None, apellido=None, email=None, is_admin=False):
    # Determinar el rol_id basado en is_admin
    conn = get_connection()
    c = conn.cursor()
    
    if is_admin:
        c.execute('SELECT id_rol FROM roles WHERE nombre = ?', ('admin',))
    else:
        c.execute('SELECT id_rol FROM roles WHERE nombre = ?', ('tecnico',))
    
    rol_id = c.fetchone()[0] if c.fetchone() else None
    conn.close()
    
    # Llamar a la función de auth.py
    success = auth_create_user(username, password, nombre, apellido, email, rol_id)
    
    if success:
        return True, ["Usuario creado exitosamente! Por favor contacte al administrador para que active su cuenta."]
    else:
        return False, ["Error al crear el usuario. El nombre de usuario ya existe o la contraseña no cumple con los requisitos."]

def login_user(username, password):
    # Llamar a la función de auth.py pero adaptando el resultado al formato esperado
    user_id, is_admin = auth_login_user(username, password)
    return user_id, is_admin

# Funciones para actualizar perfil de usuario
def update_user_profile(user_id, nombre=None, apellido=None, email=None):
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('SELECT nombre, apellido FROM usuarios WHERE id = ?', (user_id,))
    old_user_info = c.fetchone()
    old_nombre = old_user_info[0] if old_user_info[0] else ''
    old_apellido = old_user_info[1] if old_user_info[1] else ''
    old_nombre_completo = f"{old_nombre} {old_apellido}".strip()
    
    # Capitalizar nombre y apellido
    nuevo_nombre_cap = nombre.strip().capitalize() if nombre else ''
    nuevo_apellido_cap = apellido.strip().capitalize() if apellido else ''
    
    c.execute('UPDATE usuarios SET nombre = ?, apellido = ?, email = ? WHERE id = ?',
                (nuevo_nombre_cap, nuevo_apellido_cap, email.strip() if email else None, user_id))
    
    nuevo_nombre_completo = f"{nuevo_nombre_cap} {nuevo_apellido_cap}".strip()
    
    if old_nombre_completo and nuevo_nombre_completo != old_nombre_completo:
        c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = ?', (old_nombre_completo,))
        old_tecnico = c.fetchone()
        if old_tecnico:
            c.execute('UPDATE tecnicos SET nombre = ? WHERE nombre = ?', 
                        (nuevo_nombre_completo, old_nombre_completo))
    
    if nuevo_nombre_completo:
        c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = ?', (nuevo_nombre_completo,))
        tecnico = c.fetchone()
        if not tecnico:
            c.execute('INSERT INTO tecnicos (nombre) VALUES (?)', (nuevo_nombre_completo,))
    
    conn.commit()
    conn.close()
    return True

def update_user_password(user_id, nueva_password):
    # Validar la contraseña
    is_valid, messages = validate_password(nueva_password)
    if not is_valid:
        return False, messages
    
    conn = get_connection()
    c = conn.cursor()
    
    hashed_password = hash_password(nueva_password)
    c.execute('UPDATE usuarios SET password = ? WHERE id = ?',
                (hashed_password, user_id))
    
    conn.commit()
    conn.close()
    return True, ["Contraseña actualizada."]

# Funciones para obtener datos
def get_user_info(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT nombre, apellido, username, email FROM usuarios WHERE id = ?', (user_id,))
    user_info = c.fetchone()
    conn.close()
    
    if user_info:
        return {
            'nombre': user_info[0] if user_info[0] else '',
            'apellido': user_info[1] if user_info[1] else '',
            'username': user_info[2],
            'email': user_info[3] if user_info[3] else ''
        }
    return None

def get_all_registros():
    conn = get_connection()
    query = '''
        SELECT r.id, r.fecha, t.nombre as tecnico, c.nombre as cliente, 
               tt.descripcion as tipo_tarea, mt.modalidad, r.tarea_realizada, 
               r.numero_ticket, r.tiempo, r.descripcion, r.mes
        FROM registros r
        JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
        JOIN clientes c ON r.id_cliente = c.id_cliente
        JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
        JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

# Inicializar la base de datos al importar el módulo
database_init_db()