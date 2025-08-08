import sqlite3
import pandas as pd

def get_connection():
    """Obtiene una conexión a la base de datos"""
    return sqlite3.connect('trabajo.db')

def init_db():
    """Inicializa la base de datos y tablas"""
    conn = get_connection()
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
            is_active BOOLEAN NOT NULL DEFAULT 1
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
    from .auth import hash_password
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        c.execute('INSERT INTO usuarios (username, password, is_admin, is_active) VALUES (?, ?, ?, ?)',
                  ('admin', hash_password('admin'), 1, 1))
    
    conn.commit()
    conn.close()

def get_users_dataframe():
    """Obtiene DataFrame de usuarios"""
    conn = get_connection()
    users_df = pd.read_sql_query(
        "SELECT id, username, nombre, apellido, email, is_admin, is_active FROM usuarios", conn)
    conn.close()
    
    # Reemplazar valores None con 'None' para mejor visualización
    users_df['email'] = users_df['email'].fillna('None')
    users_df['nombre'] = users_df['nombre'].fillna('None')
    users_df['apellido'] = users_df['apellido'].fillna('None')
    
    return users_df

def get_registros_dataframe():
    """Obtiene DataFrame de registros"""
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

def get_user_registros_dataframe(user_id):
    """Obtiene DataFrame de registros de un usuario específico"""
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
        WHERE r.usuario_id = ?
        ORDER BY r.fecha DESC
    '''
    df = pd.read_sql_query(query, conn, params=(user_id,))
    conn.close()
    return df

def get_tecnicos_dataframe():
    """Obtiene DataFrame de técnicos"""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM tecnicos", conn)
    conn.close()
    return df

def get_clientes_dataframe():
    """Obtiene DataFrame de clientes"""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM clientes", conn)
    conn.close()
    return df

def get_tipos_dataframe():
    """Obtiene DataFrame de tipos de tarea"""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM tipos_tarea", conn)
    conn.close()
    return df

def get_modalidades_dataframe():
    """Obtiene DataFrame de modalidades"""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM modalidades_tarea", conn)
    conn.close()
    return df


def add_task_type(descripcion):
    """Agrega un nuevo tipo de tarea a la base de datos"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO tipos_tarea (descripcion) VALUES (?)", (descripcion,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Ya existe un tipo de tarea con esa descripción
    finally:
        conn.close()

def add_client(nombre):
    """Agrega un nuevo cliente a la base de datos"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO clientes (nombre) VALUES (?)", (nombre,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Ya existe un cliente con ese nombre
    finally:
        conn.close()

def add_tecnico(nombre):
    """Agrega un nuevo técnico a la base de datos"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO tecnicos (nombre) VALUES (?)", (nombre,))
        conn.commit()
        return c.lastrowid  # Retorna el ID del técnico creado
    except sqlite3.IntegrityError:
        # Si ya existe, obtener su ID
        c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (nombre,))
        return c.fetchone()[0]
    finally:
        conn.close()

def add_modalidad(modalidad):
    """Agrega una nueva modalidad a la base de datos"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO modalidades_tarea (modalidad) VALUES (?)", (modalidad,))
        conn.commit()
        return c.lastrowid  # Retorna el ID de la modalidad creada
    except sqlite3.IntegrityError:
        # Si ya existe, obtener su ID
        c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (modalidad,))
        return c.fetchone()[0]
    finally:
        conn.close()

def get_or_create_tecnico(nombre, conn=None):
    """Obtiene el ID de un técnico o lo crea si no existe"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    
    # Buscar técnico existente
    c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (nombre,))
    result = c.fetchone()
    
    if result:
        if close_conn:
            conn.close()
        return result[0]
    else:
        # Crear nuevo técnico
        try:
            c.execute("INSERT INTO tecnicos (nombre) VALUES (?)", (nombre,))
            conn.commit()
            tecnico_id = c.lastrowid
            if close_conn:
                conn.close()
            return tecnico_id
        except Exception as e:
            if close_conn:
                conn.close()
            raise e

def get_or_create_cliente(nombre, conn=None):
    """Obtiene el ID de un cliente o lo crea si no existe"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    
    # Buscar cliente existente
    c.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (nombre,))
    result = c.fetchone()
    
    if result:
        if close_conn:
            conn.close()
        return result[0]
    else:
        # Crear nuevo cliente
        try:
            c.execute("INSERT INTO clientes (nombre) VALUES (?)", (nombre,))
            conn.commit()
            cliente_id = c.lastrowid
            if close_conn:
                conn.close()
            return cliente_id
        except Exception as e:
            if close_conn:
                conn.close()
            raise e

def get_or_create_tipo_tarea(descripcion, conn=None):
    """Obtiene el ID de un tipo de tarea o lo crea si no existe"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    
    # Buscar tipo de tarea existente
    c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (descripcion,))
    result = c.fetchone()
    
    if result:
        if close_conn:
            conn.close()
        return result[0]
    else:
        # Crear nuevo tipo de tarea
        try:
            c.execute("INSERT INTO tipos_tarea (descripcion) VALUES (?)", (descripcion,))
            conn.commit()
            tipo_id = c.lastrowid
            if close_conn:
                conn.close()
            return tipo_id
        except Exception as e:
            if close_conn:
                conn.close()
            raise e

def get_or_create_modalidad(modalidad, conn=None):
    """Obtiene el ID de una modalidad o la crea si no existe"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    
    # Buscar modalidad existente
    c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (modalidad,))
    result = c.fetchone()
    
    if result:
        if close_conn:
            conn.close()
        return result[0]
    else:
        # Crear nueva modalidad
        try:
            c.execute("INSERT INTO modalidades_tarea (modalidad) VALUES (?)", (modalidad,))
            conn.commit()
            modalidad_id = c.lastrowid
            if close_conn:
                conn.close()
            return modalidad_id
        except Exception as e:
            if close_conn:
                conn.close()
            raise e

def get_unassigned_records_for_user(user_id):
    """Obtiene registros sin asignar que podrían pertenecer a un usuario basándose en el nombre del técnico"""
    conn = get_connection()
    
    # Obtener el nombre completo del usuario
    c = conn.cursor()
    c.execute("SELECT nombre, apellido FROM usuarios WHERE id = ?", (user_id,))
    user_data = c.fetchone()
    
    if not user_data or not user_data[0] or not user_data[1]:
        conn.close()
        return pd.DataFrame()  # Usuario sin nombre completo
    
    nombre_completo = f"{user_data[0]} {user_data[1]}"
    
    query = '''
        SELECT r.id, r.fecha, t.nombre as tecnico, c.nombre as cliente, 
               tt.descripcion as tipo_tarea, mt.modalidad, r.tarea_realizada, 
               r.numero_ticket, r.tiempo, r.descripcion, r.mes
        FROM registros r
        JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
        JOIN clientes c ON r.id_cliente = c.id_cliente
        JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
        JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
        WHERE r.usuario_id IS NULL AND t.nombre = ?
        ORDER BY r.fecha DESC
    '''
    
    df = pd.read_sql_query(query, conn, params=(nombre_completo,))
    conn.close()
    return df