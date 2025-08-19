import sqlite3
import pandas as pd
import uuid  # Agregar esta importación

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
            is_active BOOLEAN NOT NULL DEFAULT 1,
            rol_id INTEGER DEFAULT NULL,
            grupo_id INTEGER DEFAULT NULL,
            FOREIGN KEY (rol_id) REFERENCES roles (id_rol),
            FOREIGN KEY (grupo_id) REFERENCES grupos (id_grupo)
        )
    ''')
    
    # Tabla de roles - AÑADIR ESTA SECCIÓN
    c.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id_rol INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL UNIQUE,
            descripcion TEXT,
            is_hidden BOOLEAN NOT NULL DEFAULT 0
        )
    ''')
    
    # Tabla de grupos (nueva)
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos (
            id_grupo INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL UNIQUE,
            descripcion TEXT
        )
    ''')
    
    # Añadir esta sección para crear la tabla grupos_roles
    c.execute('''
        CREATE TABLE IF NOT EXISTS grupos_roles (
            id INTEGER PRIMARY KEY,
            id_grupo INTEGER NOT NULL,
            id_rol INTEGER NOT NULL,
            FOREIGN KEY (id_grupo) REFERENCES grupos (id_grupo),
            FOREIGN KEY (id_rol) REFERENCES roles (id_rol),
            UNIQUE(id_grupo, id_rol)
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
    
    # Añadir esta sección para crear la tabla tipos_tarea_roles
    c.execute('''
        CREATE TABLE IF NOT EXISTS tipos_tarea_roles (
            id INTEGER PRIMARY KEY,
            id_tipo INTEGER NOT NULL,
            id_rol INTEGER NOT NULL,
            FOREIGN KEY (id_tipo) REFERENCES tipos_tarea (id_tipo),
            FOREIGN KEY (id_rol) REFERENCES roles (id_rol),
            UNIQUE(id_tipo, id_rol)
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
        grupo TEXT,
        FOREIGN KEY (id_tecnico) REFERENCES tecnicos (id_tecnico),
        FOREIGN KEY (id_cliente) REFERENCES clientes (id_cliente),
        FOREIGN KEY (id_tipo) REFERENCES tipos_tarea (id_tipo),
        FOREIGN KEY (id_modalidad) REFERENCES modalidades_tarea (id_modalidad),
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
    )''')
    
    # Tabla de nómina
    c.execute('''
        CREATE TABLE IF NOT EXISTS nomina (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            apellido TEXT,
            email TEXT,
            documento TEXT UNIQUE,
            cargo TEXT,
            departamento TEXT,
            fecha_ingreso TEXT,
            activo BOOLEAN NOT NULL DEFAULT 1
        )
    ''')
    
    # Agregar la columna fecha_nacimiento si no existe
    try:
        c.execute('ALTER TABLE nomina ADD COLUMN fecha_nacimiento TEXT')
        conn.commit()
    except sqlite3.OperationalError:
        # La columna ya existe, no hacer nada
        pass
        
    # Agregar la columna grupo si no existe
    try:
        c.execute('ALTER TABLE registros ADD COLUMN grupo TEXT')
        conn.commit()
    except sqlite3.OperationalError:
        # La columna ya existe, no hacer nada
        pass
        
    # Agregar la columna is_hidden si no existe
    try:
        c.execute('ALTER TABLE roles ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT 0')
        conn.commit()
    except sqlite3.OperationalError:
        # La columna ya existe, no hacer nada
        pass
    
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
        """SELECT u.id, u.username, u.nombre, u.apellido, u.email, u.is_admin, u.is_active, 
           u.rol_id, r.nombre as rol_nombre 
           FROM usuarios u 
           LEFT JOIN roles r ON u.rol_id = r.id_rol""", conn)
    conn.close()
    
    # Reemplazar valores None con 'None' para mejor visualización
    users_df['email'] = users_df['email'].fillna('None')
    users_df['nombre'] = users_df['nombre'].fillna('None')
    users_df['apellido'] = users_df['apellido'].fillna('None')
    users_df['rol_nombre'] = users_df['rol_nombre'].fillna('sin_rol')
    
    return users_df

def get_registros_dataframe():
    """Obtiene DataFrame de registros"""
    conn = get_connection()
    query = '''
        SELECT r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
               tt.descripcion as tipo_tarea, mt.modalidad, r.tarea_realizada, 
               r.numero_ticket, r.tiempo, r.descripcion, r.mes, r.id
        FROM registros r
        JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
        JOIN clientes c ON r.id_cliente = c.id_cliente
        JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
        JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
    '''
    df = pd.read_sql_query(query, conn)
    
    # Eliminar la columna ID antes de devolver el DataFrame
    if 'id' in df.columns:
        df = df.drop(columns=['id'])
    
    conn.close()
    return df

def get_user_registros_dataframe(user_id):
    """Obtiene DataFrame de registros de un usuario específico"""
    conn = get_connection()
    query = '''
        SELECT r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
               tt.descripcion as tipo_tarea, mt.modalidad, r.tarea_realizada, 
               r.numero_ticket, r.tiempo, r.descripcion, r.mes, r.id
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
    
    # Reorganizar columnas para ocultar ID (lo mantenemos para operaciones internas)
    if 'id' in df.columns:
        df = df.drop(columns=['id'])
    
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

def get_tipos_dataframe(rol_id=None):
    """Obtiene DataFrame de tipos de tarea
    
    Args:
        rol_id (int, optional): Si se proporciona, filtra los tipos de tarea por rol
    """
    conn = get_connection()
    
    if rol_id is not None:
        # Consulta para obtener tipos de tarea asociados a un rol específico
        query = """
        SELECT t.* 
        FROM tipos_tarea t
        JOIN tipos_tarea_roles tr ON t.id_tipo = tr.id_tipo
        WHERE tr.id_rol = ?
        ORDER BY t.descripcion
        """
        df = pd.read_sql_query(query, conn, params=(rol_id,))
    else:
        # Obtener todos los tipos de tarea
        df = pd.read_sql_query("SELECT * FROM tipos_tarea", conn)
    
    conn.close()
    return df

def get_tipos_dataframe_with_roles():
    """Obtiene DataFrame de tipos de tarea con sus roles asociados"""
    conn = get_connection()
    
    # Consulta para obtener tipos de tarea con sus roles asociados
    query = """
    SELECT t.id_tipo, t.descripcion, 
           GROUP_CONCAT(r.nombre, ', ') as roles_asociados
    FROM tipos_tarea t
    LEFT JOIN tipos_tarea_roles tr ON t.id_tipo = tr.id_tipo
    LEFT JOIN roles r ON tr.id_rol = r.id_rol
    GROUP BY t.id_tipo
    ORDER BY t.descripcion
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_tipos_by_rol(rol_id):
    """Obtiene los tipos de tarea disponibles para un rol específico"""
    conn = get_connection()
    
    # Consulta para obtener tipos de tarea asociados a un rol
    query = """
    SELECT t.id_tipo, t.descripcion
    FROM tipos_tarea t
    JOIN tipos_tarea_roles tr ON t.id_tipo = tr.id_tipo
    WHERE tr.id_rol = ?
    ORDER BY t.descripcion
    """
    
    df = pd.read_sql_query(query, conn, params=(rol_id,))
    conn.close()
    return df

def get_modalidades_dataframe():
    """Obtiene DataFrame de modalidades"""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM modalidades_tarea", conn)
    conn.close()
    return df

def get_roles_dataframe(exclude_admin=False, exclude_sin_rol=False, exclude_hidden=True):
    """Obtiene DataFrame de roles
    
    Args:
        exclude_admin (bool): Si es True, excluye el rol de admin de los resultados
        exclude_sin_rol (bool): Si es True, excluye el rol sin_rol de los resultados
        exclude_hidden (bool): Si es True, excluye los roles marcados como ocultos
    """
    conn = get_connection()
    query = "SELECT id_rol, nombre, descripcion, is_hidden FROM roles"
    
    conditions = []
    if exclude_admin:
        conditions.append("nombre != 'admin'")
    if exclude_sin_rol:
        conditions.append("nombre != 'sin_rol'")
    if exclude_hidden:
        conditions.append("is_hidden = 0")
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY nombre"
    
    df = pd.read_sql_query(query, conn)
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

def get_user_rol_id(user_id):
    """Obtiene el rol_id del usuario"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT rol_id FROM usuarios WHERE id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def get_registros_by_rol(rol_id):
    """Obtiene DataFrame de registros filtrados por rol
    
    Args:
        rol_id (int): ID del rol para filtrar los registros
    """
    conn = get_connection()
    
    # Obtener el nombre del rol actual
    c = conn.cursor()
    c.execute("SELECT nombre FROM roles WHERE id_rol = ?", (rol_id,))
    rol_nombre = c.fetchone()[0]
    
    # Enfoque completamente nuevo para separar los registros por rol
    if rol_nombre == 'admin':
        # Para administradores, mostrar SOLO registros que:
        # 1. Están asignados a un usuario administrador Y
        # 2. El técnico NO coincide con ningún usuario técnico
        query = '''
            SELECT r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.descripcion, r.mes, r.id
            FROM registros r
            JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            JOIN clientes c ON r.id_cliente = c.id_cliente
            JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
            WHERE (
                -- Solo registros explícitamente asignados a usuarios admin
                r.usuario_id IN (SELECT id FROM usuarios WHERE rol_id = ?)
            )
            AND t.nombre NOT IN (
                -- Excluir cualquier registro donde el técnico coincida con un usuario técnico
                SELECT (nombre || ' ' || apellido) 
                FROM usuarios 
                WHERE rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico')
            )
        '''
        df = pd.read_sql_query(query, conn, params=(rol_id,))
    elif rol_nombre == 'tecnico':
        # Para técnicos, mostrar registros donde:
        # 1. El técnico coincide con un usuario técnico O
        # 2. Están asignados a un usuario técnico
        query = '''
            SELECT r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.descripcion, r.mes, r.id
            FROM registros r
            JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            JOIN clientes c ON r.id_cliente = c.id_cliente
            JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
            WHERE (
                -- Registros donde el técnico coincide con un usuario técnico
                t.nombre IN (
                    SELECT (nombre || ' ' || apellido) 
                    FROM usuarios 
                    WHERE rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico')
                )
                OR
                -- Registros asignados directamente a usuarios técnicos
                r.usuario_id IN (SELECT id FROM usuarios WHERE rol_id = ?)
            )
        '''
        df = pd.read_sql_query(query, conn, params=(rol_id,))
    else:
        # Para otros roles, mantener la lógica original
        query = '''
            SELECT r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.descripcion, r.mes, r.id
            FROM registros r
            JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            JOIN clientes c ON r.id_cliente = c.id_cliente
            JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
            WHERE (
                r.usuario_id IN (SELECT id FROM usuarios WHERE rol_id = ?)
                OR
                t.nombre IN (
                    SELECT (nombre || ' ' || apellido) 
                    FROM usuarios 
                    WHERE rol_id = ?
                )
            )
        '''
        df = pd.read_sql_query(query, conn, params=(rol_id, rol_id))
    
    conn.close()
    return df

def get_nomina_dataframe():
    """Obtiene un DataFrame con todos los registros de nómina"""
    conn = get_connection()
    query = """SELECT * FROM nomina"""
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_nomina_dataframe_expanded():
    """Obtiene un DataFrame expandido con formato de vista completa para nómina"""
    conn = get_connection()
    query = """SELECT * FROM nomina"""
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        return df
    
    from datetime import datetime
    
    def calcular_edad(fecha_nacimiento):
        if not fecha_nacimiento or pd.isna(fecha_nacimiento):
            return ''
        try:
            fecha_nac = datetime.strptime(str(fecha_nacimiento), '%Y-%m-%d')
            hoy = datetime.now()
            edad = hoy.year - fecha_nac.year
            if hoy.month < fecha_nac.month or (hoy.month == fecha_nac.month and hoy.day < fecha_nac.day):
                edad -= 1
            return str(edad)
        except:
            return ''
    
    def calcular_antiguedad(fecha_ingreso):
        if not fecha_ingreso or pd.isna(fecha_ingreso):
            return ''
        try:
            fecha_ing = datetime.strptime(str(fecha_ingreso), '%Y-%m-%d')
            hoy = datetime.now()
            años = hoy.year - fecha_ing.year
            meses = hoy.month - fecha_ing.month
            
            if meses < 0:
                años -= 1
                meses += 12
            
            if años > 0:
                return f"{años} años, {meses} meses"
            else:
                return f"{meses} meses"
        except:
            return ''
    
    # Función para separar categoria y funcion del campo cargo
    def separar_cargo(cargo_str):
        if not cargo_str or pd.isna(cargo_str) or cargo_str == '':
            return 'falta dato', 'falta dato'
        
        cargo_str = str(cargo_str).strip()
        
        # Si contiene " - ", separar
        if ' - ' in cargo_str:
            partes = cargo_str.split(' - ', 1)
            categoria = partes[0].strip()
            funcion = partes[1].strip()
            
            # Si alguna parte es 'falta dato' o está vacía, mostrar 'falta dato'
            if categoria.lower() == 'falta dato' or categoria == '':
                categoria = 'falta dato'
            if funcion.lower() == 'falta dato' or funcion == '':
                funcion = 'falta dato'
                
            return categoria, funcion
        else:
            # Si no contiene " - ", es solo una categoría
            if cargo_str.lower() == 'falta dato':
                return 'falta dato', 'falta dato'
            return cargo_str, 'falta dato'
    
    # Aplicar la separación
    categorias_funciones = df['cargo'].apply(separar_cargo)
    
    # Crear DataFrame expandido con cálculos dinámicos
    expanded_df = pd.DataFrame({
        'NOMBRE': df['nombre'].apply(lambda x: str(x).capitalize() if pd.notna(x) and str(x).strip() != '' else 'falta dato'),
        'Apellido': df['apellido'].apply(lambda x: str(x).capitalize() if pd.notna(x) and str(x).strip() != '' else 'falta dato'),
        'MAIL': df['email'].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() != '' and str(x).strip().lower() != 'nan' else 'falta dato'),
        'Celular': df['documento'].apply(lambda x: str(x) if pd.notna(x) and str(x).strip() != '' else 'falta dato'),
        'Categoria': [cat for cat, func in categorias_funciones],
        'Funcion': [func for cat, func in categorias_funciones],
        'Sector': df['departamento'].apply(lambda x: 'falta dato' if pd.isna(x) or str(x).strip() == '' or str(x).lower() == 'falta dato' else str(x)),
        'Fecha ingreso': df['fecha_ingreso'].apply(lambda x: str(x) if pd.notna(x) and str(x).strip() != '' else 'falta dato'),
        'Fecha Nacimiento': df['fecha_nacimiento'].apply(lambda x: str(x) if pd.notna(x) and str(x).strip() != '' else 'falta dato') if 'fecha_nacimiento' in df.columns else 'falta dato',
        'Edad': df['fecha_nacimiento'].apply(calcular_edad) if 'fecha_nacimiento' in df.columns else 'falta dato',
        'Antigüedad': df['fecha_ingreso'].apply(calcular_antiguedad)
    })
    
    return expanded_df

def add_empleado_nomina(nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento=''):
    """Añade un nuevo empleado a la nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO nomina (nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento, activo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento))
        conn.commit()
        conn.close()
        
        # Generar rol automáticamente si hay un departamento válido
        if departamento and departamento.strip() != '' and departamento.lower() != 'falta dato':
            get_or_create_role_from_sector(departamento)
            
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False
    except Exception as e:
        conn.close()
        raise e

def update_empleado_nomina(id_empleado, nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento='', activo=1):
    """Actualiza un empleado existente en la nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE nomina 
            SET nombre = ?, apellido = ?, email = ?, documento = ?, cargo = ?, 
                departamento = ?, fecha_ingreso = ?, fecha_nacimiento = ?, activo = ?
            WHERE id = ?
        """, (nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento, activo, id_empleado))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # El documento ya existe para otro empleado
        conn.close()
        return False
    except Exception as e:
        conn.close()
        raise e

def delete_empleado_nomina(id_empleado):
    """Elimina un empleado de la nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM nomina WHERE id = ?", (id_empleado,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        raise e

def process_nomina_excel(excel_df):
    """Procesa un DataFrame de Excel y guarda los empleados en la nómina"""
    success_count = 0
    error_count = 0
    duplicate_count = 0
    error_details = []
    
    # Hacer una copia del DataFrame para no modificar el original
    df = excel_df.copy()
    
    # Eliminar filas donde todas las columnas son NaN (por si no se hizo antes)
    df = df.dropna(how='all')
    
    # Eliminar columnas donde todas las filas son NaN (por si no se hizo antes)
    df = df.dropna(axis=1, how='all')
    
    # Crear un diccionario para mapear columnas insensibles a mayúsculas
    column_map = {}
    for col in df.columns:
        col_upper = col.upper()
        column_map[col_upper] = col
    
    # Función auxiliar para obtener valor de columna insensible a mayúsculas
    def get_column_value(row, column_name):
        actual_column = column_map.get(column_name.upper())
        if actual_column and actual_column in df.columns:
            return row[actual_column]
        return None
    
    # Función para formatear nombres y apellidos
    def format_name(name):
        if not name or pd.isna(name):
            return ''
        name_str = str(name).strip()
        if not name_str:
            return ''
        # Primera letra en mayúscula, resto en minúscula
        return name_str.capitalize()
    
    # Crear lista para almacenar filas de vista previa
    preview_rows = []
    
    # Verificar columnas requeridas (insensible a mayúsculas)
    required_columns = ['NOMBRE', 'CELULAR']
    missing_columns = []
    for req_col in required_columns:
        if req_col not in column_map:
            missing_columns.append(req_col)
    
    if missing_columns:
        raise ValueError(f"El archivo no contiene las columnas requeridas: {', '.join(missing_columns)}")
    
    # Obtener documentos existentes para verificar duplicados
    conn = get_connection()
    existing_docs = pd.read_sql_query("SELECT documento FROM nomina", conn)
    existing_docs_list = existing_docs['documento'].tolist() if not existing_docs.empty else []
    
    # Procesar cada fila
    for index, row in df.iterrows():
        try:
            # Omitir filas donde los campos requeridos están vacíos
            nombre_val = get_column_value(row, 'NOMBRE')
            celular_val = get_column_value(row, 'CELULAR')
            
            if pd.isna(nombre_val) or pd.isna(celular_val):
                continue
                
            # Usar Celular como documento único
            documento = str(celular_val).strip() if celular_val else f"AUTO_{uuid.uuid4().hex[:8]}"
            celular = documento  # Guardar el valor original para la vista previa
            
            # Si el documento está vacío después de limpiar, omitir esta fila
            if not documento:
                continue
                
            # Verificar si ya existe
            if documento in existing_docs_list:
                duplicate_count += 1
                continue
            
            # Procesar el campo NOMBRE que puede venir en formato "APELLIDO, NOMBRE"
            nombre_completo = str(nombre_val).strip()
            apellido_from_col = get_column_value(row, 'APELLIDO')
            apellido_from_col = str(apellido_from_col).strip() if apellido_from_col and not pd.isna(apellido_from_col) else ''
            
            # Extraer apellido y nombre
            nombre = ''
            apellido = ''
            
            if apellido_from_col:
                apellido = format_name(apellido_from_col)
                nombre = format_name(nombre_completo)
            elif ',' in nombre_completo:
                # Formato "APELLIDO, NOMBRE"
                partes = nombre_completo.split(',', 1)
                apellido = format_name(partes[0].strip())
                nombre = format_name(partes[1].strip())
            else:
                # No tiene formato con coma, usar la última palabra como apellido
                partes = nombre_completo.rsplit(' ', 1)
                if len(partes) == 2:
                    nombre = format_name(partes[0].strip())
                    apellido = format_name(partes[1].strip())
                else:
                    nombre = format_name(nombre_completo)
            
            # Guardar el email en una variable separada
            email_val = get_column_value(row, 'MAIL')
            email = str(email_val).strip() if email_val and not pd.isna(email_val) else ''
            
            # Si no se pudo extraer un apellido del nombre, usar parte del email como apellido
            if not apellido and email:
                # Intentar extraer apellido del email (parte antes del @)
                if '@' in email:
                    apellido = format_name(email.split('@')[0])
                else:
                    apellido = format_name(email)
            
            # Determinar categoria y funcion por separado para la vista previa
            categoria_val = get_column_value(row, 'CATEGORIA')
            categoria = str(categoria_val).strip() if categoria_val and not pd.isna(categoria_val) else ''
            
            funcion_val = get_column_value(row, 'FUNCION')
            funcion = str(funcion_val).strip() if funcion_val and not pd.isna(funcion_val) else ''
            
            # Para la base de datos, combinar categoria y funcion en cargo
            if categoria and funcion:
                cargo = f"{categoria} - {funcion}"
            elif categoria:
                cargo = categoria
            elif funcion:
                cargo = funcion
            else:
                cargo = ''
            
            sector_val = get_column_value(row, 'SECTOR')
            departamento = str(sector_val).strip() if sector_val and not pd.isna(sector_val) else ''
            
            # Procesar fecha de ingreso sin la hora
            fecha_ingreso_val = get_column_value(row, 'FECHA INGRESO')
            if not fecha_ingreso_val or pd.isna(fecha_ingreso_val):
                fecha_ingreso_val = get_column_value(row, 'FECHA_INGRESO')
            
            fecha_ingreso_completa = str(fecha_ingreso_val).strip() if fecha_ingreso_val and not pd.isna(fecha_ingreso_val) else ''
            fecha_ingreso = fecha_ingreso_completa.split(' ')[0] if ' ' in fecha_ingreso_completa else fecha_ingreso_completa
            
            # Procesar campos adicionales para la vista previa
            fecha_nacimiento_val = get_column_value(row, 'FECHA NACIMIENTO')
            if not fecha_nacimiento_val or pd.isna(fecha_nacimiento_val):
                fecha_nacimiento_val = get_column_value(row, 'FECHA_NACIMIENTO')
            
            fecha_nacimiento_completa = str(fecha_nacimiento_val).strip() if fecha_nacimiento_val and not pd.isna(fecha_nacimiento_val) else ''
            fecha_nacimiento = fecha_nacimiento_completa.split(' ')[0] if ' ' in fecha_nacimiento_completa else fecha_nacimiento_completa
            
            edad_val = get_column_value(row, 'EDAD')
            edad = str(edad_val).strip() if edad_val and not pd.isna(edad_val) else ''
            
            antiguedad_val = get_column_value(row, 'ANTIGÜEDAD')
            if not antiguedad_val or pd.isna(antiguedad_val):
                antiguedad_val = get_column_value(row, 'ANTIGUEDAD')
            antiguedad = str(antiguedad_val).strip() if antiguedad_val and not pd.isna(antiguedad_val) else ''
            
            # Añadir fila al DataFrame de vista previa
            preview_row = {
                'NOMBRE': nombre,
                'Apellido': apellido,
                'MAIL': email,
                'Celular': celular,
                'Categoria': categoria,
                'Funcion': funcion,
                'Sector': departamento,
                'Fecha ingreso': fecha_ingreso,
                'Fecha Nacimiento': fecha_nacimiento,
                'Edad': edad,
                'Antigüedad': antiguedad
            }
            # Asegurarse de que no haya valores None o NaN
            for key in preview_row:
                if pd.isna(preview_row[key]) or preview_row[key] is None:
                    preview_row[key] = ''
                    
            preview_rows.append(preview_row)
            
            # Salario eliminado - ya no se procesa
            
            # En la función process_nomina_excel, modificar la llamada a add_empleado_nomina:
            if add_empleado_nomina(nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento):
                success_count += 1
                existing_docs_list.append(documento)
            else:
                duplicate_count += 1
                
        except Exception as e:
            error_count += 1
            error_details.append(f"Fila {index + 1}: {str(e)}")
            continue
    
    # Crear DataFrame de vista previa desde la lista
    preview_df = pd.DataFrame(preview_rows)
    
    # Asegurar que el DataFrame de vista previa tenga todas las columnas necesarias
    if not preview_df.empty:
        # Reordenar columnas para mejor visualización
        column_order = ['NOMBRE', 'Apellido', 'MAIL', 'Celular', 'Categoria', 'Funcion', 'Sector', 'Fecha ingreso', 'Fecha Nacimiento', 'Edad', 'Antigüedad']
        # Solo incluir columnas que existen en el DataFrame
        available_columns = [col for col in column_order if col in preview_df.columns]
        preview_df = preview_df[available_columns]
    
    conn.close()
    
    # Si hay errores, mostrar detalles en la consola para debugging
    if error_details:
        print("Detalles de errores:")
        for detail in error_details[:10]:  # Mostrar solo los primeros 10 errores
            print(f"  - {detail}")
        if len(error_details) > 10:
            print(f"  ... y {len(error_details) - 10} errores más")
    
    return preview_df, success_count, error_count, duplicate_count


def get_or_create_role_from_sector(sector):
    """Obtiene o crea un rol basado en el sector de nómina
    
    Args:
        sector (str): Nombre del sector
        
    Returns:
        int: ID del rol creado o existente
        bool: True si el rol fue creado, False si ya existía
    """
    from .utils import normalize_sector_name
    
    if not sector or pd.isna(sector) or sector.strip() == '' or sector.lower() == 'falta dato':
        return None, False
    
    conn = get_connection()
    c = conn.cursor()
    
    # Normalizar el nombre del sector para comparación
    normalized_sector = normalize_sector_name(sector)
    
    try:
        # Buscar si ya existe un rol con este nombre normalizado
        c.execute("""SELECT id_rol, nombre FROM roles WHERE nombre != 'admin' AND nombre != 'sin_rol'""")
        existing_roles = c.fetchall()
        
        # Comparar con nombres normalizados
        for role_id, role_name in existing_roles:
            if normalize_sector_name(role_name) == normalized_sector:
                conn.close()
                return role_id, False
        
        # Si no existe, crear el nuevo rol
        # Usar el nombre original (no normalizado) para mantener mayúsculas/minúsculas y tildes
        c.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                 (sector.strip(), f"Rol generado automáticamente desde el sector de nómina: {sector.strip()}"))
        conn.commit()
        
        # Obtener el ID del rol recién creado
        c.execute("SELECT last_insert_rowid()")
        new_role_id = c.fetchone()[0]
        
        conn.close()
        return new_role_id, True
        
    except Exception as e:
        conn.close()
        raise e

def generate_users_from_nomina():
    """Genera usuarios automáticamente a partir de los empleados en la nómina
    
    Returns:
        dict: Diccionario con estadísticas de la generación de usuarios
    """
    from .auth import create_user
    import datetime
    from .utils import normalize_text
    
    conn = get_connection()
    
    # Obtener empleados de nómina que no tienen usuario asociado
    query = """
    SELECT n.id, n.nombre, n.apellido, n.email, n.documento, n.departamento 
    FROM nomina n 
    LEFT JOIN usuarios u ON (LOWER(n.nombre) = LOWER(u.nombre) AND LOWER(n.apellido) = LOWER(u.apellido)) 
    WHERE u.id IS NULL AND n.nombre IS NOT NULL AND n.apellido IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        return {"total": 0, "creados": 0, "errores": 0, "usuarios": []}
    
    # Estadísticas
    stats = {"total": len(df), "creados": 0, "errores": 0, "usuarios": []}
    
    # Obtener el año actual
    current_year = datetime.datetime.now().year
    
    # Procesar cada empleado
    for _, row in df.iterrows():
        nombre = str(row['nombre']).strip().capitalize()
        apellido_completo = str(row['apellido']).strip()
        
        # Extraer solo el primer apellido para la contraseña
        primer_apellido = apellido_completo.split()[0].capitalize()
        
        # Extraer el último apellido para el nombre de usuario
        apellidos = apellido_completo.split()
        ultimo_apellido = apellidos[-1] if apellidos else ""
        
        email = str(row['email']) if pd.notna(row['email']) and str(row['email']).strip() != '' else None
        departamento = str(row['departamento']) if pd.notna(row['departamento']) and str(row['departamento']).strip() != '' else None
        
        # Generar nombre de usuario (primera letra del nombre + último apellido, todo en minúsculas)
        username = (nombre[0] + ultimo_apellido).lower()
        username = ''.join(c for c in username if c.isalnum())  # Eliminar caracteres especiales
        
        # Generar contraseña con el formato Primer_Apellido+año actual seguido de un punto
        password = f"{primer_apellido}{current_year}."  # Ejemplo: Noel2025.
        
        # Obtener rol_id basado en el departamento
        rol_id = None
        if departamento and departamento.strip() != '' and departamento.lower() != 'falta dato':
            conn = get_connection()
            c = conn.cursor()
            
            # Normalizar el nombre del departamento para la búsqueda
            departamento_normalizado = normalize_text(departamento.strip())
            
            # Obtener todos los roles
            c.execute('SELECT id_rol, nombre FROM roles')
            roles = c.fetchall()
            conn.close()
            
            # Buscar coincidencia normalizada
            for role_id, role_name in roles:
                if normalize_text(role_name) == departamento_normalizado:
                    rol_id = role_id
                    break
        
        # Crear usuario
        try:
            if create_user(username, password, nombre, apellido_completo, email, rol_id):
                stats["creados"] += 1
                stats["usuarios"].append({
                    "username": username,
                    "nombre": nombre,
                    "apellido": apellido_completo,
                    "password": password,  # Incluir la contraseña generada para mostrarla al usuario
                    "rol": departamento if departamento else "sin_rol"
                })
        except Exception:
            stats["errores"] += 1
    
    return stats

def generate_roles_from_nomina():
    """Genera roles automáticamente a partir de los sectores en la nómina
    
    Returns:
        dict: Diccionario con estadísticas de la generación de roles
    """
    conn = get_connection()
    
    # Obtener todos los sectores únicos de la nómina
    query = """SELECT DISTINCT departamento FROM nomina WHERE departamento IS NOT NULL AND departamento != ''"""
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        return {"total": 0, "nuevos": 0, "nuevos_roles": []}
    
    # Estadísticas
    stats = {"total": 0, "nuevos": 0, "nuevos_roles": []}
    
    # Procesar cada sector
    for _, row in df.iterrows():
        sector = row['departamento']
        if sector and not pd.isna(sector) and sector.strip() != '':
            stats["total"] += 1
            role_id, is_new = get_or_create_role_from_sector(sector)
            
            if is_new and role_id:
                stats["nuevos"] += 1
                stats["nuevos_roles"].append(sector.strip())
    
    return stats

def get_grupos_dataframe():
    """Obtiene DataFrame de grupos con sus roles asignados"""
    conn = get_connection()
    
    # Consulta para obtener grupos con sus roles asociados
    query = """
    SELECT g.id_grupo, g.nombre, 
           GROUP_CONCAT(r.nombre, ', ') as roles_asignados,
           g.descripcion
    FROM grupos g
    LEFT JOIN grupos_roles gr ON g.id_grupo = gr.id_grupo
    LEFT JOIN roles r ON gr.id_rol = r.id_rol
    GROUP BY g.id_grupo
    ORDER BY g.nombre
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Reemplazar valores None con cadena vacía para mejor visualización
    df['roles_asignados'] = df['roles_asignados'].fillna('')
    df['descripcion'] = df['descripcion'].fillna('')
    
    return df

def add_grupo(nombre, descripcion=None):
    """Agrega un nuevo grupo a la base de datos"""
    from .utils import normalize_text
    
    conn = get_connection()
    c = conn.cursor()
    try:
        # Verificar si ya existe un grupo con el mismo nombre normalizado
        c.execute("SELECT id_grupo FROM grupos")
        grupos = c.fetchall()
        
        nombre_normalizado = normalize_text(nombre)
        for grupo_id in grupos:
            grupo = get_grupo_by_id(grupo_id[0])
            if normalize_text(grupo[1]) == nombre_normalizado:
                return False  # Ya existe un grupo con ese nombre normalizado
        
        # Si no existe, insertar el nuevo grupo con el nombre original
        c.execute("INSERT INTO grupos (nombre, descripcion) VALUES (?, ?)", (nombre, descripcion))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Ya existe un grupo con ese nombre exacto
    finally:
        conn.close()

def get_grupo_by_id(grupo_id):
    """Obtiene un grupo por su ID"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM grupos WHERE id_grupo = ?", (grupo_id,))
    grupo = c.fetchone()
    conn.close()
    return grupo

def get_roles_by_grupo(grupo_id):
    """Obtiene los roles asociados a un grupo específico"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT r.id_rol, r.nombre 
               FROM roles r
               JOIN grupos_roles gr ON r.id_rol = gr.id_rol
               WHERE gr.id_grupo = ?""", (grupo_id,))
    roles = c.fetchall()
    conn.close()
    return roles

def get_grupos_by_rol(rol_id):
    """Obtiene los grupos asociados a un rol específico"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT g.id_grupo, g.nombre 
               FROM grupos g
               JOIN grupos_roles gr ON g.id_grupo = gr.id_grupo
               WHERE gr.id_rol = ?""", (rol_id,))
    grupos = c.fetchall()
    conn.close()
    return grupos

def assign_grupo_to_rol(grupo_id, rol_id):
    """Asigna un grupo a un rol específico"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (?, ?)", (grupo_id, rol_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Ya existe esta relación
    finally:
        conn.close()

def remove_grupo_from_rol(grupo_id, rol_id):
    """Elimina la asignación de un grupo a un rol"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM grupos_roles WHERE id_grupo = ? AND id_rol = ?", (grupo_id, rol_id))
    conn.commit()
    conn.close()
    return True

def update_grupo_roles(grupo_id, rol_ids):
    """Actualiza los roles asignados a un grupo"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Eliminar todas las asignaciones actuales
        c.execute("DELETE FROM grupos_roles WHERE id_grupo = ?", (grupo_id,))
        
        # Insertar las nuevas asignaciones
        for rol_id in rol_ids:
            c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (?, ?)", (grupo_id, rol_id))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_departamentos_list():
    """Obtiene una lista de roles existentes para usar como departamentos (excluyendo ocultos)"""
    conn = get_connection()
    query = """SELECT DISTINCT nombre FROM roles 
               WHERE is_hidden = 0
               AND nombre IS NOT NULL AND nombre != '' 
               ORDER BY nombre"""
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        return []
    
    return df['nombre'].tolist()

def generate_users_from_nomina():
    """Genera usuarios automáticamente a partir de los empleados en la nómina
    
    Returns:
        dict: Diccionario con estadísticas de la generación de usuarios
    """
    from .auth import create_user
    import datetime
    import unicodedata
    
    def remove_accents(text):
        """Elimina acentos y caracteres especiales del texto"""
        # Normalizar el texto para separar caracteres base de acentos
        normalized = unicodedata.normalize('NFD', text)
        # Filtrar solo caracteres ASCII (sin acentos)
        ascii_text = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        return ascii_text
    
    conn = get_connection()
    
    # Obtener empleados de nómina que no tienen usuario asociado
    query = """
    SELECT n.id, n.nombre, n.apellido, n.email, n.documento, n.departamento 
    FROM nomina n 
    LEFT JOIN usuarios u ON (LOWER(n.nombre) = LOWER(u.nombre) AND LOWER(n.apellido) = LOWER(u.apellido)) 
    WHERE u.id IS NULL AND n.nombre IS NOT NULL AND n.apellido IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    
    # Obtener todos los usernames existentes para verificar duplicados
    usernames_query = "SELECT username FROM usuarios"
    existing_usernames = pd.read_sql_query(usernames_query, conn).username.str.lower().tolist()
    
    conn.close()
    
    if df.empty:
        return {"total": 0, "creados": 0, "errores": 0, "usuarios": []}
    
    # Estadísticas
    stats = {"total": len(df), "creados": 0, "errores": 0, "usuarios": [], "duplicados": 0}
    
    # Obtener el año actual
    current_year = datetime.datetime.now().year
    
    # Procesar cada empleado
    for _, row in df.iterrows():
        nombre = str(row['nombre']).strip().capitalize()
        apellido_completo = str(row['apellido']).strip()
        
        # Extraer solo el primer apellido para la contraseña
        primer_apellido = apellido_completo.split()[0].capitalize()
        
        # Usar el primer apellido para el nombre de usuario en lugar del último
        apellidos = apellido_completo.split()
        primer_apellido_username = apellidos[0] if apellidos else ""
        
        email = str(row['email']) if pd.notna(row['email']) and str(row['email']).strip() != '' else None
        departamento = str(row['departamento']) if pd.notna(row['departamento']) and str(row['departamento']).strip() != '' else None
        
        # Generar nombre de usuario (primera letra del nombre + primer apellido, todo en minúsculas)
        # Eliminar acentos antes de generar el username
        nombre_sin_acentos = remove_accents(nombre)
        primer_apellido_sin_acentos = remove_accents(primer_apellido_username)
        
        username = (nombre_sin_acentos[0] + primer_apellido_sin_acentos).lower()
        username = ''.join(c for c in username if c.isalnum())  # Eliminar caracteres especiales
        
        # Verificar si el username ya existe
        if username.lower() in existing_usernames:
            stats["duplicados"] += 1
            continue
        
        # Generar contraseña con el formato Primer_Apellido+año actual seguido de un punto
        password = f"{primer_apellido}{current_year}."  # Ejemplo: Noel2025.
        
        # Obtener rol_id basado en el departamento
        rol_id = None
        if departamento and departamento.strip() != '' and departamento.lower() != 'falta dato':
            conn = get_connection()
            c = conn.cursor()
            
            # Normalizar el nombre del departamento para la búsqueda
            from .utils import normalize_text
            departamento_normalizado = normalize_text(departamento.strip())
            
            # Obtener todos los roles
            c.execute('SELECT id_rol, nombre FROM roles')
            roles = c.fetchall()
            conn.close()
            
            # Buscar coincidencia normalizada
            for role_id, role_name in roles:
                if normalize_text(role_name) == departamento_normalizado:
                    rol_id = role_id
                    break
        
        # Crear usuario
        try:
            if create_user(username, password, nombre, apellido_completo, email, rol_id):
                stats["creados"] += 1
                existing_usernames.append(username.lower())  # Agregar a la lista de usernames existentes
                stats["usuarios"].append({
                    "username": username,
                    "nombre": nombre,
                    "apellido": apellido_completo,
                    "password": password,  # Incluir la contraseña generada para mostrarla al usuario
                    "rol": departamento if departamento else "sin_rol"
                })
        except Exception:
            stats["errores"] += 1
    
    return stats

def generate_roles_from_nomina():
    """Genera roles automáticamente a partir de los sectores en la nómina
    
    Returns:
        dict: Diccionario con estadísticas de la generación de roles
    """
    conn = get_connection()
    
    # Obtener todos los sectores únicos de la nómina
    query = """SELECT DISTINCT departamento FROM nomina WHERE departamento IS NOT NULL AND departamento != ''"""
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        return {"total": 0, "nuevos": 0, "nuevos_roles": []}
    
    # Estadísticas
    stats = {"total": 0, "nuevos": 0, "nuevos_roles": []}
    
    # Procesar cada sector
    for _, row in df.iterrows():
        sector = row['departamento']
        if sector and not pd.isna(sector) and sector.strip() != '':
            stats["total"] += 1
            role_id, is_new = get_or_create_role_from_sector(sector)
            
            if is_new and role_id:
                stats["nuevos"] += 1
                stats["nuevos_roles"].append(sector.strip())
    
    return stats