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
            is_active BOOLEAN NOT NULL DEFAULT 1
        )
    ''')
    
    # Tabla de roles - AÑADIR ESTA SECCIÓN
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
            documento TEXT UNIQUE,
            cargo TEXT,
            departamento TEXT,
            fecha_ingreso TEXT,
            salario REAL,
            activo BOOLEAN NOT NULL DEFAULT 1
        )
    ''')
    
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

def get_roles_dataframe(exclude_admin=False):
    """Obtiene DataFrame de roles
    
    Args:
        exclude_admin (bool): Si es True, excluye el rol de admin de los resultados
    """
    conn = get_connection()
    query = "SELECT id_rol, nombre, descripcion FROM roles"
    
    if exclude_admin:
        query += " WHERE nombre != 'admin'"
        
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
    
    # Esta consulta asume que los técnicos están relacionados con usuarios
    # y los usuarios tienen un rol_id
    query = '''
        SELECT r.id, r.fecha, t.nombre as tecnico, c.nombre as cliente, 
               tt.descripcion as tipo_tarea, mt.modalidad, r.tarea_realizada, 
               r.numero_ticket, r.tiempo, r.descripcion, r.mes
        FROM registros r
        JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
        JOIN clientes c ON r.id_cliente = c.id_cliente
        JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
        JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
        JOIN usuarios u ON r.usuario_id = u.id
        WHERE u.rol_id = ?
    '''
    
    df = pd.read_sql_query(query, conn, params=(rol_id,))
    conn.close()
    return df

def get_nomina_dataframe():
    """Obtiene un DataFrame con todos los registros de nómina"""
    conn = get_connection()
    query = """SELECT * FROM nomina"""
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def add_empleado_nomina(nombre, apellido, documento, cargo, departamento, fecha_ingreso, salario):
    """Añade un nuevo empleado a la nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO nomina (nombre, apellido, documento, cargo, departamento, fecha_ingreso, salario, activo)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (nombre, apellido, documento, cargo, departamento, fecha_ingreso, salario))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # El documento ya existe
        conn.close()
        return False
    except Exception as e:
        conn.close()
        raise e

def update_empleado_nomina(id_empleado, nombre, apellido, documento, cargo, departamento, fecha_ingreso, salario, activo):
    """Actualiza un empleado existente en la nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            UPDATE nomina 
            SET nombre = ?, apellido = ?, documento = ?, cargo = ?, 
                departamento = ?, fecha_ingreso = ?, salario = ?, activo = ?
            WHERE id = ?
        """, (nombre, apellido, documento, cargo, departamento, fecha_ingreso, salario, activo, id_empleado))
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
    """Procesa un DataFrame de Excel para cargar datos de nómina"""
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
            
            # Salario (si existe, pero no lo mostramos en la vista previa)
            salario = 0.0
            
            if add_empleado_nomina(nombre, apellido, documento, cargo, departamento, fecha_ingreso, salario):
                success_count += 1
                existing_docs_list.append(documento)  # Actualizar lista para evitar duplicados en el mismo lote
            else:
                duplicate_count += 1
                
        except Exception as e:
            error_count += 1
            error_details.append(f"Fila {index + 1}: {str(e)}")
            continue
    
    # Crear DataFrame de vista previa desde la lista
    preview_df = pd.DataFrame(preview_rows)
    
    conn.close()
    
    # Si hay errores, mostrar detalles en la consola para debugging
    if error_details:
        print("Detalles de errores:")
        for detail in error_details[:10]:  # Mostrar solo los primeros 10 errores
            print(f"  - {detail}")
        if len(error_details) > 10:
            print(f"  ... y {len(error_details) - 10} errores más")
    
    return preview_df, success_count, error_count, duplicate_count