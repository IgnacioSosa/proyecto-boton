import sqlite3
import pandas as pd
import bcrypt
from datetime import datetime, timedelta

# Crear la base de datos y tablas
def init_db():
    conn = sqlite3.connect('trabajo.db')
    c = conn.cursor()
    
    # Tabla de usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            nombre TEXT,
            apellido TEXT,
            email TEXT,
            is_admin BOOLEAN NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            rol_id INTEGER DEFAULT NULL
        )
    ''')
    
    # Tabla de roles
    c.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id_rol INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL UNIQUE,
            descripcion TEXT
        )
    ''')
    
    # Tabla de técnicos
    c.execute('''
        CREATE TABLE IF NOT EXISTS tecnicos (
            id_tecnico INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL UNIQUE
        )
    ''')
    
    # Tabla de clientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id_cliente INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL UNIQUE
        )
    ''')
    
    # Tabla de tipos de tarea
    c.execute('''
        CREATE TABLE IF NOT EXISTS tipos_tarea (
            id_tipo INTEGER PRIMARY KEY,
            descripcion TEXT NOT NULL UNIQUE
        )
    ''')
    
    # Tabla de modalidades de tarea
    c.execute('''
        CREATE TABLE IF NOT EXISTS modalidades_tarea (
            id_modalidad INTEGER PRIMARY KEY,
            modalidad TEXT NOT NULL UNIQUE
        )
    ''')
    
    # Tabla de registros de trabajo
    c.execute('''CREATE TABLE IF NOT EXISTS registros (
        id INTEGER PRIMARY KEY,
        fecha TEXT NOT NULL,
        id_tecnico INTEGER NOT NULL,
        id_cliente INTEGER NOT NULL,
        id_tipo INTEGER NOT NULL,
        id_modalidad INTEGER NOT NULL,
        tarea_realizada TEXT NOT NULL,
        numero_ticket TEXT NOT NULL,
        tiempo INTEGER NOT NULL,
        descripcion TEXT,
        mes TEXT NOT NULL,
        usuario_id INTEGER,
        FOREIGN KEY (id_tecnico) REFERENCES tecnicos (id_tecnico),
        FOREIGN KEY (id_cliente) REFERENCES clientes (id_cliente),
        FOREIGN KEY (id_tipo) REFERENCES tipos_tarea (id_tipo),
        FOREIGN KEY (id_modalidad) REFERENCES modalidades_tarea (id_modalidad),
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
    )''')
    
    # Verificar si el usuario admin existe, si no, crearlo
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    admin_user = c.fetchone()
    if not admin_user:
        c.execute('INSERT INTO usuarios (username, password, is_admin, is_active, rol_id) VALUES (?, ?, ?, ?, (SELECT id_rol FROM roles WHERE nombre = "admin"))',
                  ('admin', bcrypt.hashpw('admin'.encode('utf-8'), bcrypt.gensalt()), 1, 1))
    else:
        # Asegurarse de que el usuario admin tenga el rol correcto
        c.execute('UPDATE usuarios SET rol_id = (SELECT id_rol FROM roles WHERE nombre = "admin") WHERE username = "admin" AND (rol_id IS NULL OR rol_id != (SELECT id_rol FROM roles WHERE nombre = "admin"))')
    
    # Asegurarse de que todos los usuarios tengan un rol asignado
    c.execute('''
        UPDATE usuarios 
        SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'admin') 
        WHERE is_admin = 1 AND rol_id IS NULL
    ''')
    
    c.execute('''
        UPDATE usuarios 
        SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico') 
        WHERE is_admin = 0 AND rol_id IS NULL
    ''')
    
    # Insertar roles predeterminados si no existen
    c.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'admin'")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('admin', 'Administrador con acceso completo'))

    c.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'tecnico'")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('tecnico', 'Técnico con acceso a registros'))

    c.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'sin_rol'")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('sin_rol', 'Usuario sin acceso'))
    
    conn.commit()
    conn.close()

# Funciones de autenticación
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

def validate_password(password):
    """Valida que la contraseña cumpla con los requisitos de seguridad y devuelve una lista de mensajes."""
    requisitos_faltantes = []
    
    if len(password) < 8:
        requisitos_faltantes.append("La contraseña debe tener al menos 8 caracteres.")
    
    if not any(c.isupper() for c in password):
        requisitos_faltantes.append("La contraseña debe tener al menos una letra mayúscula.")
    
    if not any(c.islower() for c in password):
        requisitos_faltantes.append("La contraseña debe tener al menos una letra minúscula.")
    
    if not any(c.isdigit() for c in password):
        requisitos_faltantes.append("La contraseña debe tener al menos un número.")
    
    if not any(c in "!@#$%^&*()-_=+[]{}|;:'\",.<>/?`~" for c in password):
        requisitos_faltantes.append("La contraseña debe tener al menos un carácter especial.")
    
    if requisitos_faltantes:
        return False, requisitos_faltantes
    
    return True, ["Contraseña válida"]

def create_user(username, password, nombre=None, apellido=None, email=None, is_admin=False):
    # Validar la contraseña
    is_valid, messages = validate_password(password)
    if not is_valid:
        return False, messages
    
    conn = sqlite3.connect('trabajo.db')
    c = conn.cursor()
    
    # Convertir el username a minúsculas
    username = username.lower()
    
    # Capitalizar nombre y apellido si existen
    if nombre:
        nombre = nombre.strip().capitalize()
    if apellido:
        apellido = apellido.strip().capitalize()
    
    # Verificar si el usuario ya existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', (username,))
    if c.fetchone():
        conn.close()
        return False, ["El nombre de usuario ya existe."]
    
    # Crear el nuevo usuario (deshabilitado por defecto)
    hashed_password = hash_password(password)
    c.execute('INSERT INTO usuarios (username, password, nombre, apellido, email, is_admin, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)',
              (username, hashed_password, nombre, apellido, email, is_admin, False))
    
    conn.commit()
    conn.close()
    return True, ["Usuario creado exitosamente! Por favor contacte al administrador para que active su cuenta."]

def login_user(username, password):
    conn = sqlite3.connect('trabajo.db')
    c = conn.cursor()
    # Convertir el username a minúsculas antes de buscar
    username = username.lower()
    c.execute('SELECT id, password, is_admin, is_active FROM usuarios WHERE username = ?', (username,))
    user = c.fetchone()
    
    if user and verify_password(password, user[1]):
        if user[3]: # is_active
            # Obtener el nombre y apellido del usuario
            c.execute('SELECT nombre, apellido FROM usuarios WHERE id = ?', (user[0],))
            user_info = c.fetchone()
            
            # Si el usuario tiene nombre y apellido, verificar si existe como técnico
            if user_info and (user_info[0] or user_info[1]):
                nombre_completo = f"{user_info[0] or ''} {user_info[1] or ''}".strip()
                if nombre_completo:
                    # Verificar si el técnico ya existe
                    c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = ?', (nombre_completo,))
                    tecnico = c.fetchone()
                    if not tecnico:
                        # Crear el técnico si no existe
                        c.execute('INSERT INTO tecnicos (nombre) VALUES (?)', (nombre_completo,))
                        conn.commit()
            
            conn.close()
            return user[0], user[2] # user_id, is_admin
    conn.close()
    return None, None

# Funciones para actualizar perfil de usuario
def update_user_profile(user_id, nombre=None, apellido=None, email=None):
    conn = sqlite3.connect('trabajo.db')
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
    
    conn = sqlite3.connect('trabajo.db')
    c = conn.cursor()
    
    hashed_password = hash_password(nueva_password)
    c.execute('UPDATE usuarios SET password = ? WHERE id = ?',
                (hashed_password, user_id))
    
    conn.commit()
    conn.close()
    return True, ["Contraseña actualizada."]

# Funciones para obtener datos
def get_user_info(user_id):
    conn = sqlite3.connect('trabajo.db')
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
    conn = sqlite3.connect('trabajo.db')
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
init_db()