import psycopg2
import psycopg2.extras
import pandas as pd
import uuid
from .logging_utils import log_sql_error
from contextlib import contextmanager
from .config import POSTGRES_CONFIG, DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD, SYSTEM_ROLES
from .utils import month_name_es
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
_ENGINE = None

def get_engine():
    """Devuelve un engine de SQLAlchemy para PostgreSQL usando POSTGRES_CONFIG"""
    global _ENGINE
    if _ENGINE is None:
        db_url = URL.create(
            "postgresql+psycopg2",
            username=POSTGRES_CONFIG['user'],
            password=POSTGRES_CONFIG['password'],
            host=POSTGRES_CONFIG['host'],
            port=int(POSTGRES_CONFIG['port']),
            database=POSTGRES_CONFIG['database'],
        )
        _ENGINE = create_engine(db_url, pool_pre_ping=True)
    return _ENGINE

def get_connection():
    """Establece conexión con PostgreSQL"""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_CONFIG['host'],
            port=POSTGRES_CONFIG['port'],
            database=POSTGRES_CONFIG['database'],
            user=POSTGRES_CONFIG['user'],
            password=POSTGRES_CONFIG['password']
        )
        return conn
    except Exception as e:
        log_sql_error(f"Error conectando a PostgreSQL: {e}")
        raise

def test_connection():
    """Prueba la conexión a la base de datos"""
    try:
        conn = get_connection()
        conn.close()
        return True
    except Exception as e:
        log_sql_error(f"Error en test de conexión: {e}")
        return False

@contextmanager
def db_connection():
    """Context manager para conexiones a la base de datos"""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Inicializa la estructura de la base de datos"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        c.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                nombre VARCHAR(100),
                apellido VARCHAR(100),
                email VARCHAR(100),
                is_admin BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                is_2fa_enabled BOOLEAN DEFAULT FALSE,
                rol_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Asegurar columna para secreto TOTP (si no existe)
        c.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(255)")
        
        # Bloqueo por intentos fallidos (si no existen)
        c.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS failed_attempts INTEGER DEFAULT 0")
        c.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS lockout_until TIMESTAMP NULL")
        
        # Tabla de roles
        c.execute('''
            CREATE TABLE IF NOT EXISTS roles (
                id_rol SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL UNIQUE,
                descripcion TEXT,
                is_hidden BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de grupos
        c.execute('''
            CREATE TABLE IF NOT EXISTS grupos (
                id_grupo SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL UNIQUE,
                descripcion TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla grupos_roles
        c.execute('''
            CREATE TABLE IF NOT EXISTS grupos_roles (
                id SERIAL PRIMARY KEY,
                id_grupo INTEGER NOT NULL,
                id_rol INTEGER NOT NULL,
                FOREIGN KEY (id_grupo) REFERENCES grupos (id_grupo),
                FOREIGN KEY (id_rol) REFERENCES roles (id_rol),
                UNIQUE(id_grupo, id_rol)
            )
        ''')
        
        # Tabla de grupos_puntajes
        c.execute('''
            CREATE TABLE IF NOT EXISTS grupos_puntajes (
                id SERIAL PRIMARY KEY,
                id_grupo INTEGER NOT NULL,
                puntaje INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (id_grupo) REFERENCES grupos (id_grupo),
                UNIQUE(id_grupo)
            )
        ''')
        
        # Tabla de tipos_tarea_puntajes
        c.execute('''
            CREATE TABLE IF NOT EXISTS tipos_tarea_puntajes (
                id SERIAL PRIMARY KEY,
                id_tipo INTEGER NOT NULL,
                puntaje INTEGER NOT NULL DEFAULT 0,
                UNIQUE(id_tipo)
            )
        ''')
        
        # Tabla de técnicos
        c.execute('''
            CREATE TABLE IF NOT EXISTS tecnicos (
                id_tecnico SERIAL PRIMARY KEY,
                nombre VARCHAR(200) NOT NULL,
                apellido VARCHAR(100),
                email VARCHAR(100),
                telefono VARCHAR(20),
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de clientes
        c.execute('''CREATE TABLE IF NOT EXISTS clientes (
                id_cliente SERIAL PRIMARY KEY,
                nombre VARCHAR(200) NOT NULL UNIQUE,
                direccion VARCHAR(300),
                telefono VARCHAR(20),
                email VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de clientes_puntajes
        c.execute('''CREATE TABLE IF NOT EXISTS clientes_puntajes (
                id SERIAL PRIMARY KEY,
                id_cliente INTEGER NOT NULL,
                puntaje INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (id_cliente) REFERENCES clientes (id_cliente),
                UNIQUE(id_cliente)
            )
        ''')
        
        # Tabla de tipos de tarea
        c.execute('''
            CREATE TABLE IF NOT EXISTS tipos_tarea (
                id_tipo SERIAL PRIMARY KEY,
                descripcion VARCHAR(200) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de modalidades de tarea
        c.execute('''
            CREATE TABLE IF NOT EXISTS modalidades_tarea (
                id_modalidad SERIAL PRIMARY KEY,
                descripcion VARCHAR(200) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Sembrar modalidades requeridas (si no existen)
        required_modalidades = [
            "Cliente",
            "Presencial",
            "Remoto",
            "Feriado",
            "Base en Casa",
        ]
        for nombre in required_modalidades:
            c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE descripcion = %s", (nombre,))
            if not c.fetchone():
                c.execute("INSERT INTO modalidades_tarea (descripcion) VALUES (%s)", (nombre,))

        # Tabla tipos_tarea_roles
        c.execute('''
            CREATE TABLE IF NOT EXISTS tipos_tarea_roles (
                id SERIAL PRIMARY KEY,
                id_tipo INTEGER NOT NULL,
                id_rol INTEGER NOT NULL,
                FOREIGN KEY (id_tipo) REFERENCES tipos_tarea (id_tipo),
                FOREIGN KEY (id_rol) REFERENCES roles (id_rol),
                UNIQUE(id_tipo, id_rol)
            )
        ''')
        # Tabla de registros de trabajo
        c.execute('''CREATE TABLE IF NOT EXISTS registros (
            id SERIAL PRIMARY KEY,
            fecha VARCHAR(20) NOT NULL,
            id_tecnico INTEGER NOT NULL,
            id_cliente INTEGER NOT NULL,
            id_tipo INTEGER NOT NULL,
            id_modalidad INTEGER NOT NULL,
            tarea_realizada TEXT NOT NULL,
            numero_ticket VARCHAR(50) NOT NULL,
            tiempo INTEGER NOT NULL,
            descripcion TEXT,
            mes VARCHAR(20) NOT NULL,
            usuario_id INTEGER,
            grupo VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (id_tecnico) REFERENCES tecnicos (id_tecnico),
            FOREIGN KEY (id_cliente) REFERENCES clientes (id_cliente),
            FOREIGN KEY (id_tipo) REFERENCES tipos_tarea (id_tipo),
            FOREIGN KEY (id_modalidad) REFERENCES modalidades_tarea (id_modalidad),
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )''')
        
        # Asegurar tipo decimal para 'tiempo' en registros
        try:
            c.execute("""
                SELECT data_type 
                FROM information_schema.columns
                WHERE table_name = 'registros' AND column_name = 'tiempo'
            """)
            row = c.fetchone()
            if row and row[0] == 'integer':
                c.execute("""
                    ALTER TABLE registros
                    ALTER COLUMN tiempo TYPE NUMERIC(6,2)
                    USING tiempo::numeric
                """)
        except Exception:
            pass
        
        # Tabla de nómina
        c.execute('''
            CREATE TABLE IF NOT EXISTS nomina (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                apellido VARCHAR(100),
                email VARCHAR(100),
                documento VARCHAR(50),
                cargo VARCHAR(150),
                departamento VARCHAR(100),
                fecha_ingreso DATE,
                fecha_nacimiento DATE,
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de registro de actividades de usuarios
        c.execute('''
            CREATE TABLE IF NOT EXISTS actividades_usuarios (
                id SERIAL PRIMARY KEY,
                usuario_id INTEGER,
                username VARCHAR(50),
                tipo_actividad VARCHAR(50) NOT NULL,
                descripcion TEXT,
                fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
            )
        ''')
        
        # Tabla de códigos de recuperación
        c.execute('''
            CREATE TABLE IF NOT EXISTS recovery_codes (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                code VARCHAR(100),
                used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id)
            )
        ''')
        
        # Agregar foreign keys a usuarios después de crear las tablas
        try:
            c.execute('''
                ALTER TABLE usuarios 
                ADD CONSTRAINT fk_usuarios_rol 
                FOREIGN KEY (rol_id) REFERENCES roles (id_rol)
            ''')
        except Exception:
            pass  # La constraint ya existe
            
        try:
            c.execute('''
                ALTER TABLE tipos_tarea_puntajes 
                ADD CONSTRAINT fk_tipos_tarea_puntajes_tipo 
                FOREIGN KEY (id_tipo) REFERENCES tipos_tarea (id_tipo)
            ''')
        except Exception:
            pass  # La constraint ya existe
        
        # Insertar roles del sistema si no existen
        for role_name, role_desc in SYSTEM_ROLES.items():
            c.execute('SELECT * FROM roles WHERE nombre = %s', (role_desc,))
            if not c.fetchone():
                # SIN_ROL, VISOR e HIPERVISOR deben estar ocultos
                is_hidden = True if role_name in ['SIN_ROL', 'VISOR', 'HIPERVISOR'] else False
                c.execute('INSERT INTO roles (nombre, descripcion, is_hidden) VALUES (%s, %s, %s)',
                         (role_desc, f'Rol del sistema: {role_desc}', is_hidden))
        
        # Verificar si el usuario admin existe, si no, crearlo
        from .auth import hash_password
        c.execute('SELECT * FROM usuarios WHERE username = %s', (DEFAULT_ADMIN_USERNAME,))
        if not c.fetchone():
            # Obtener el ID del rol admin
            c.execute('SELECT id_rol FROM roles WHERE nombre = %s', (SYSTEM_ROLES['ADMIN'],))
            admin_role = c.fetchone()
            admin_rol_id = admin_role[0] if admin_role else None
            
            c.execute('INSERT INTO usuarios (username, password_hash, is_admin, is_active, rol_id) VALUES (%s, %s, %s, %s, %s)',
                      (DEFAULT_ADMIN_USERNAME, hash_password(DEFAULT_ADMIN_PASSWORD), True, True, admin_rol_id))
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error inicializando base de datos: {e}")
        raise
    finally:
        conn.close()

def create_default_admin():
    """Crea el usuario admin por defecto si no existe"""
    from .auth import hash_password
    
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Verificar si ya existe el admin
        c.execute("SELECT COUNT(*) FROM usuarios WHERE username = %s", (DEFAULT_ADMIN_USERNAME,))
        if c.fetchone()[0] == 0:
            # Obtener el rol de admin
            c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (SYSTEM_ROLES['ADMIN'],))
            admin_rol = c.fetchone()
            
            if admin_rol:
                # Crear hash de la contraseña
                password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
                
                c.execute('''
                    INSERT INTO usuarios (username, password_hash, is_admin, rol_id, is_active)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (DEFAULT_ADMIN_USERNAME, password_hash, True, admin_rol[0], True))
                
                conn.commit()
                
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error creando admin por defecto: {e}")
        raise
    finally:
        conn.close()

def get_users_dataframe():
    """Obtiene DataFrame de usuarios con información completa"""
    try:
        query = """SELECT u.id, u.username, u.nombre, u.apellido, u.email, u.is_admin, u.is_active, 
               u.rol_id, r.nombre as rol_nombre
               FROM usuarios u 
               LEFT JOIN roles r ON u.rol_id = r.id_rol
               ORDER BY u.is_admin DESC, u.apellido, u.nombre"""
        
        engine = get_engine()
        users_df = pd.read_sql_query(query, con=engine)
        
        # Reemplazar valores None con 'None' para mejor visualización
        users_df['email'] = users_df['email'].fillna('None')
        users_df['nombre'] = users_df['nombre'].fillna('None')
        users_df['apellido'] = users_df['apellido'].fillna('None')
        users_df['rol_nombre'] = users_df['rol_nombre'].fillna(SYSTEM_ROLES['SIN_ROL'])
        
        return users_df
        
    except Exception as e:
        log_sql_error(f"Error obteniendo usuarios: {e}")
        return pd.DataFrame()

def get_registros_dataframe():
    """Obtiene DataFrame de registros con información completa"""
    try:
        query = '''
            SELECT r.id, r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.descripcion as modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.descripcion, r.mes
            FROM registros r
            JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            JOIN clientes c ON r.id_cliente = c.id_cliente
            JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
            ORDER BY r.id DESC
        '''
        engine = get_engine()
        df = pd.read_sql_query(query, con=engine)
        
        if 'id' in df.columns:
            other_columns = [col for col in df.columns if col != 'id']
            df = df[['id'] + other_columns]
        
        if 'mes' in df.columns:
            df['mes'] = df['mes'].apply(month_name_es)
        
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo registros: {e}")
        return pd.DataFrame()

def get_registros_dataframe_with_date_filter(filter_type='current_month', custom_month=None, custom_year=None):
    """Obtiene DataFrame de registros filtrados por fecha
    
    Args:
        filter_type (str): 'current_month', 'custom_month', 'all_time'
        custom_month (int): Mes específico (1-12) para filtro personalizado
        custom_year (int): Año específico para filtro personalizado
    """
    try:
        # Construir filtro de fecha
        date_filter = ""
        params = {}
        
        if filter_type == 'current_month':
            from datetime import datetime
            current_month = datetime.now().month
            current_year = datetime.now().year
            year_2digit = str(current_year)[-2:]
            date_filter = "WHERE (substring(r.fecha, 4, 2) = :month AND substring(r.fecha, 7, 2) = :year2)"
            params.update({"month": f"{current_month:02d}", "year2": year_2digit})
        elif filter_type == 'custom_month' and custom_month and custom_year:
            year_2digit = str(custom_year)[-2:]
            date_filter = "WHERE (substring(r.fecha, 4, 2) = :month AND substring(r.fecha, 7, 2) = :year2)"
            params.update({"month": f"{custom_month:02d}", "year2": year_2digit})
        # Para 'all_time' no agregamos filtro de fecha
        
        query = f'''
            SELECT r.id, r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.descripcion as modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.descripcion, r.mes
            FROM registros r
            JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            JOIN clientes c ON r.id_cliente = c.id_cliente
            JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
            {date_filter}
            ORDER BY r.id DESC
        '''
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine, params=params if params else None)
        
        if 'mes' in df.columns:
            df['mes'] = df['mes'].apply(month_name_es)
        
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo registros con filtro de fecha: {e}")
        return pd.DataFrame()

def get_user_registros_dataframe(user_id):
    """Obtiene DataFrame de registros de un usuario específico"""
    try:
        query = '''
            SELECT r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.descripcion as modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.descripcion, r.mes, r.id
            FROM registros r
            JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            JOIN clientes c ON r.id_cliente = c.id_cliente
            JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
            WHERE r.usuario_id = :user_id
            ORDER BY r.fecha DESC
        '''
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine, params={"user_id": user_id})
        
        if 'mes' in df.columns:
            df['mes'] = df['mes'].apply(month_name_es)
        
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo registros de usuario: {e}")
        return pd.DataFrame()

def get_user_registros_dataframe_cached(user_id):
    """Obtiene DataFrame de registros de un usuario específico con caché en session_state"""
    import streamlit as st
    
    # Usar caché en session_state para evitar consultas repetidas
    cache_key = f"user_registros_{user_id}"
    
    if cache_key not in st.session_state:
        query = '''
            SELECT r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.descripcion as modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.descripcion, r.mes, r.id
            FROM registros r
            JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            JOIN clientes c ON r.id_cliente = c.id_cliente
            JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
            WHERE r.usuario_id = :user_id
            ORDER BY r.fecha DESC
        '''
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine, params={"user_id": user_id})
            
        # Procesar fechas una sola vez y guardar en caché
        if not df.empty:
            def convert_fecha_to_datetime(fecha_str):
                """Convierte fecha string a datetime con múltiples formatos"""
                try:
                    return pd.to_datetime(fecha_str, format='%d/%m/%y')
                except:
                    try:
                        return pd.to_datetime(fecha_str, format='%d/%m/%Y')
                    except:
                        try:
                            return pd.to_datetime(fecha_str, dayfirst=True)
                        except:
                            return pd.NaT
                
            df['fecha_dt'] = df['fecha'].apply(convert_fecha_to_datetime)
            
            if 'mes' in df.columns:
                df['mes'] = df['mes'].apply(month_name_es)
            
        st.session_state[cache_key] = df
    
    return st.session_state[cache_key]

def clear_user_registros_cache(user_id):
    """Limpia el caché de registros de un usuario específico"""
    import streamlit as st
    
    cache_key = f"user_registros_{user_id}"
    if cache_key in st.session_state:
        del st.session_state[cache_key]

def get_tecnicos_dataframe():
    """Obtiene DataFrame de técnicos"""
    engine = get_engine()
    df = pd.read_sql_query("SELECT * FROM tecnicos", con=engine)
    return df

def get_clientes_dataframe():
    """Obtiene DataFrame de clientes"""
    engine = get_engine()
    df = pd.read_sql_query("SELECT * FROM clientes", con=engine)
    return df

def get_tipos_dataframe(rol_id=None):
    """Obtiene DataFrame de tipos de tarea
    
    Args:
        rol_id (int, optional): Si se proporciona, filtra los tipos de tarea por rol
    """
    engine = get_engine()
    if rol_id is not None:
        query = """
        SELECT t.* 
        FROM tipos_tarea t
        JOIN tipos_tarea_roles tr ON t.id_tipo = tr.id_tipo
        WHERE tr.id_rol = :rol_id
        ORDER BY t.descripcion
        """
        df = pd.read_sql_query(text(query), con=engine, params={"rol_id": rol_id})
    else:
        df = pd.read_sql_query("SELECT * FROM tipos_tarea ORDER BY descripcion", con=engine)
    return df

def get_tipos_dataframe_with_roles():
    """Obtiene DataFrame de tipos de tarea con sus roles asociados"""
    try:
        query = """
        SELECT t.id_tipo, t.descripcion, 
               STRING_AGG(r.nombre, ', ') as roles_asociados
        FROM tipos_tarea t
        LEFT JOIN tipos_tarea_roles tr ON t.id_tipo = tr.id_tipo
        LEFT JOIN roles r ON tr.id_rol = r.id_rol
        GROUP BY t.id_tipo, t.descripcion
        ORDER BY t.descripcion
        """
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine)
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo tipos de tarea con roles: {e}")
        return pd.DataFrame()

def get_tipos_by_rol(rol_id):
    """Obtiene los tipos de tarea disponibles para un rol específico"""
    try:
        query = """
        SELECT t.id_tipo, t.descripcion
        FROM tipos_tarea t
        JOIN tipos_tarea_roles tr ON t.id_tipo = tr.id_tipo
        WHERE tr.id_rol = :rol_id
        ORDER BY t.descripcion
        """
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine, params={"rol_id": rol_id})
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo tipos por rol: {e}")
        return pd.DataFrame()

def get_modalidades_dataframe():
    """Obtiene DataFrame de modalidades"""
    engine = get_engine()
    df = pd.read_sql_query("SELECT * FROM modalidades_tarea ORDER BY descripcion", con=engine)
    return df


def ensure_user_modality_schedule_exists(conn=None):
    """Asegura que existe la tabla de programación de modalidades de usuario"""
    if conn is None:
        conn = get_connection()
        close_conn = True
    else:
        close_conn = False

    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_modalidad_schedule (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            rol_id INTEGER NOT NULL,
            fecha DATE NOT NULL,
            modalidad_id INTEGER NOT NULL,
            cliente_id INTEGER NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, fecha),
            FOREIGN KEY (user_id) REFERENCES usuarios (id),
            FOREIGN KEY (rol_id) REFERENCES roles (id_rol),
            FOREIGN KEY (modalidad_id) REFERENCES modalidades_tarea (id_modalidad)
        )
    ''')
    # Intentar agregar la columna si la tabla ya existía sin cliente_id (PostgreSQL)
    try:
        c.execute("ALTER TABLE user_modalidad_schedule ADD COLUMN IF NOT EXISTS cliente_id INTEGER NULL")
    except Exception:
        pass
    conn.commit()
    if close_conn:
        conn.close()


def get_users_by_rol(rol_id, exclude_hidden=True):
    """Obtiene usuarios por rol_id"""
    try:
        query = """
            SELECT u.id, u.nombre, u.apellido
            FROM usuarios u
            JOIN roles r ON u.rol_id = r.id_rol
            WHERE u.rol_id = :rol_id
            {extra}
            ORDER BY u.nombre, u.apellido
        """
        extra = "AND r.is_hidden = FALSE" if exclude_hidden else ""
        engine = get_engine()
        df = pd.read_sql_query(text(query.format(extra=extra)), con=engine, params={"rol_id": int(rol_id)})
        # Agregar columna nombre_completo
        df["nombre_completo"] = df.apply(lambda row: f"{row['nombre']} {row['apellido']}".strip(), axis=1)
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo usuarios por rol: {e}")
        return pd.DataFrame()


def sync_user_schedule_roles_for_range(start_date, end_date):
    """Sincroniza rol_id en user_modalidad_schedule con el rol actual del usuario
    para todas las filas entre start_date y end_date. Devuelve cantidad de filas actualizadas."""
    ensure_user_modality_schedule_exists()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            UPDATE user_modalidad_schedule s
            SET rol_id = u.rol_id,
                updated_at = CURRENT_TIMESTAMP
            FROM usuarios u
            WHERE s.user_id = u.id
              AND s.fecha BETWEEN %s AND %s
              AND s.rol_id <> u.rol_id
        """, (start_date, end_date))
        conn.commit()
        return c.rowcount
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error sincronizando roles en schedule: {e}")
        return 0
    finally:
        conn.close()

def get_user_weekly_modalities(user_id, start_date, end_date):
    """Obtiene las modalidades semanales de un usuario"""
    try:
        ensure_user_modality_schedule_exists()
        query = """
            SELECT fecha, modalidad_id, cliente_id
            FROM user_modalidad_schedule
            WHERE user_id = :user_id
              AND fecha BETWEEN :start_date AND :end_date
            ORDER BY fecha
        """
        engine = get_engine()
        df = pd.read_sql_query(
            text(query),
            con=engine,
            params={"user_id": int(user_id), "start_date": start_date, "end_date": end_date},
        )
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo modalidades semanales de usuario: {e}")
        return pd.DataFrame()


def get_weekly_modalities_by_rol(rol_id, start_date, end_date):
    """Obtiene las modalidades semanales de todos los usuarios de un rol"""
    try:
        ensure_user_modality_schedule_exists()
        query = """
            SELECT s.user_id, u.nombre, u.apellido, s.fecha, s.modalidad_id, m.descripcion AS modalidad,
                   s.cliente_id, c.nombre AS cliente_nombre
            FROM user_modalidad_schedule s
            JOIN usuarios u ON s.user_id = u.id
            JOIN modalidades_tarea m ON s.modalidad_id = m.id_modalidad
            LEFT JOIN clientes c ON s.cliente_id = c.id_cliente
            WHERE s.rol_id = :rol_id
              AND s.fecha BETWEEN :start_date AND :end_date
            ORDER BY u.nombre, u.apellido, s.fecha
        """
        engine = get_engine()
        df = pd.read_sql_query(
            text(query),
            con=engine,
            params={"rol_id": int(rol_id), "start_date": start_date, "end_date": end_date},
        )
        df["nombre_completo"] = df.apply(lambda row: f"{row['nombre']} {row['apellido']}".strip(), axis=1)
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo modalidades semanales por rol: {e}")
        return pd.DataFrame()


def sync_user_schedule_roles_for_range(start_date, end_date):
    """Sincroniza rol_id en user_modalidad_schedule con el rol actual del usuario
    para todas las filas entre start_date y end_date. Devuelve cantidad de filas actualizadas."""
    ensure_user_modality_schedule_exists()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            UPDATE user_modalidad_schedule s
            SET rol_id = u.rol_id,
                updated_at = CURRENT_TIMESTAMP
            FROM usuarios u
            WHERE s.user_id = u.id
              AND s.fecha BETWEEN %s AND %s
              AND s.rol_id <> u.rol_id
        """, (start_date, end_date))
        conn.commit()
        return c.rowcount
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error sincronizando roles en schedule: {e}")
        return 0
    finally:
        conn.close()


def upsert_user_modality_for_date(user_id, rol_id, fecha, modalidad_id, cliente_id=None):
    """Inserta o actualiza la modalidad de un usuario para una fecha específica, opcionalmente con cliente"""
    ensure_user_modality_schedule_exists()
    conn = get_connection()
    c = conn.cursor()
    try:
        # Intentar ON CONFLICT (PostgreSQL)
        c.execute("""
            INSERT INTO user_modalidad_schedule (user_id, rol_id, fecha, modalidad_id, cliente_id, updated_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, fecha)
            DO UPDATE SET modalidad_id = EXCLUDED.modalidad_id,
                          rol_id = EXCLUDED.rol_id,
                          cliente_id = EXCLUDED.cliente_id,
                          updated_at = CURRENT_TIMESTAMP
        """, (int(user_id), int(rol_id), fecha, int(modalidad_id), cliente_id))
        conn.commit()
    except Exception:
        # Fallback si la BD no soporta ON CONFLICT
        try:
            c.execute("SELECT id FROM user_modalidad_schedule WHERE user_id=%s AND fecha=%s", (int(user_id), fecha))
            row = c.fetchone()
            if row:
                c.execute("""
                    UPDATE user_modalidad_schedule
                    SET modalidad_id=%s, rol_id=%s, cliente_id=%s, updated_at=CURRENT_TIMESTAMP
                    WHERE user_id=%s AND fecha=%s
                """, (int(modalidad_id), int(rol_id), cliente_id, int(user_id), fecha))
            else:
                c.execute("""
                    INSERT INTO user_modalidad_schedule (user_id, rol_id, fecha, modalidad_id, cliente_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (int(user_id), int(rol_id), fecha, int(modalidad_id), cliente_id))
            conn.commit()
        except Exception as e2:
            conn.rollback()
            log_sql_error(f"Error upsert modalidad diaria: {e2}")
            raise
    finally:
        conn.close()

def ensure_user_default_schedule_exists(conn=None):
    """Crea la tabla de cronograma por defecto por usuario y día de semana si no existe"""
    if conn is None:
        conn = get_connection()
        close_conn = True
    else:
        close_conn = False

    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_default_schedule (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,  -- 0=Lunes ... 4=Viernes
            modalidad_id INTEGER NOT NULL,
            cliente_id INTEGER NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, day_of_week),
            FOREIGN KEY (user_id) REFERENCES usuarios (id),
            FOREIGN KEY (modalidad_id) REFERENCES modalidades_tarea (id_modalidad)
        )
    """)
    # Asegurar columna cliente_id si la tabla existía sin ella
    try:
        c.execute("ALTER TABLE user_default_schedule ADD COLUMN IF NOT EXISTS cliente_id INTEGER NULL")
    except Exception:
        pass

    conn.commit()
    if close_conn:
        conn.close()

def get_user_default_schedule(user_id):
    """Devuelve DataFrame con el cronograma por defecto para un usuario"""
    try:
        ensure_user_default_schedule_exists()
        engine = get_engine()
        df = pd.read_sql_query(
            text("SELECT day_of_week, modalidad_id, cliente_id FROM user_default_schedule WHERE user_id = :uid ORDER BY day_of_week"),
            con=engine,
            params={"uid": int(user_id)},
        )
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo cronograma por defecto de usuario: {e}")
        return pd.DataFrame()

def upsert_user_default_schedule(user_id, day_of_week, modalidad_id, cliente_id=None):
    """Inserta/actualiza el cronograma por defecto del usuario para un día de semana"""
    ensure_user_default_schedule_exists()
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO user_default_schedule (user_id, day_of_week, modalidad_id, cliente_id, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, day_of_week)
            DO UPDATE SET modalidad_id = EXCLUDED.modalidad_id,
                          cliente_id = EXCLUDED.cliente_id,
                          updated_at = CURRENT_TIMESTAMP
        """, (int(user_id), int(day_of_week), int(modalidad_id), cliente_id))
        conn.commit()
    except Exception:
        try:
            c.execute("SELECT id FROM user_default_schedule WHERE user_id=%s AND day_of_week=%s", (int(user_id), int(day_of_week)))
            row = c.fetchone()
            if row:
                c.execute("""
                    UPDATE user_default_schedule
                    SET modalidad_id=%s, cliente_id=%s, updated_at=CURRENT_TIMESTAMP
                    WHERE user_id=%s AND day_of_week=%s
                """, (int(modalidad_id), cliente_id, int(user_id), int(day_of_week)))
            else:
                c.execute("""
                    INSERT INTO user_default_schedule (user_id, day_of_week, modalidad_id, cliente_id)
                    VALUES (%s, %s, %s, %s)
                """, (int(user_id), int(day_of_week), int(modalidad_id), cliente_id))
            conn.commit()
        except Exception as e2:
            conn.rollback()
            log_sql_error(f"Error upsert cronograma por defecto: {e2}")
            raise
    finally:
        conn.close()

def upsert_user_default_schedule_bulk(user_id, schedule_dict):
    """Upsert en bloque: schedule_dict = {dow: (modalidad_id, cliente_id)}"""
    ensure_user_default_schedule_exists()
    for dow, pair in schedule_dict.items():
        modalidad_id, cliente_id = pair
        upsert_user_default_schedule(user_id, int(dow), int(modalidad_id), cliente_id)

def get_roles_dataframe(exclude_admin=False, exclude_sin_rol=False, exclude_hidden=True):
    """Obtiene DataFrame de roles
    
    Args:
        exclude_admin (bool): Si es True, excluye el rol de admin de los resultados
        exclude_sin_rol (bool): Si es True, excluye el rol sin_rol de los resultados
        exclude_hidden (bool): Si es True, excluye los roles marcados como ocultos
    """
    query = "SELECT id_rol, nombre, descripcion, is_hidden FROM roles"
    
    conditions = []
    if exclude_admin:
        conditions.append(f"nombre != '{SYSTEM_ROLES['ADMIN']}'")
    if exclude_sin_rol:
        conditions.append(f"nombre != '{SYSTEM_ROLES['SIN_ROL']}'")
    if exclude_hidden:
        conditions.append("is_hidden = FALSE")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY nombre"
    
    engine = get_engine()
    df = pd.read_sql_query(query, con=engine)
    return df

def add_task_type(descripcion):
    """Agrega un nuevo tipo de tarea a la base de datos con validación de duplicados"""
    # Normalizar la descripción: eliminar espacios extra y convertir a formato título
    descripcion_normalizada = ' '.join(descripcion.strip().split()).title()
    
    conn = get_connection()
    c = conn.cursor()
    try:
        # Verificar si ya existe un tipo similar (insensible a mayúsculas/minúsculas y espacios)
        c.execute("SELECT id_tipo FROM tipos_tarea WHERE LOWER(TRIM(descripcion)) = LOWER(TRIM(%s))", 
                 (descripcion_normalizada,))
        existing = c.fetchone()
        
        if existing:
            return False  # Ya existe un tipo similar
        
        c.execute("INSERT INTO tipos_tarea (descripcion) VALUES (%s)", (descripcion_normalizada,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def add_client(nombre):
    """Agrega un nuevo cliente a la base de datos"""
    try:
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO clientes (nombre) VALUES (%s)", (nombre,))
            conn.commit()
            return True
    except Exception:
        return False  # Ya existe un cliente con ese nombre

def add_tecnico(nombre):
    """Agrega un nuevo técnico a la base de datos"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO tecnicos (nombre) VALUES (%s) RETURNING id_tecnico", (nombre,))
        tecnico_id = c.fetchone()[0]
        conn.commit()
        return tecnico_id  # Retorna el ID del técnico creado
    except Exception:
        # Si ya existe, obtener su ID
        c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = %s", (nombre,))
        return c.fetchone()[0]
    finally:
        conn.close()

def add_modalidad(modalidad):
    """Agrega una nueva modalidad a la base de datos"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO modalidades_tarea (descripcion) VALUES (%s)", (modalidad,))
        conn.commit()
        return True
    except Exception:
        return False  # Ya existe una modalidad con ese nombre
    finally:
        conn.close()

def get_or_create_tecnico(nombre, conn=None):
    """Obtiene el ID de un técnico o lo crea si no existe"""
    from .utils import normalize_text  # Importar la función de normalización
    
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    
    # Normalizar el nombre para búsqueda
    nombre_normalizado = normalize_text(nombre)
    
    # Buscar técnico existente por nombre normalizado
    c.execute("SELECT id_tecnico, nombre FROM tecnicos")
    tecnicos = c.fetchall()
    
    for tecnico_id, tecnico_nombre in tecnicos:
        if normalize_text(tecnico_nombre) == nombre_normalizado:
            if close_conn:
                conn.close()
            return tecnico_id
    
    # Si no se encontró, crear nuevo técnico con el nombre original
    try:
        c.execute("INSERT INTO tecnicos (nombre) VALUES (%s) RETURNING id_tecnico", (nombre,))
        tecnico_id = c.fetchone()[0]
        conn.commit()
        if close_conn:
            conn.close()
        return tecnico_id
    except Exception as e:
        if close_conn:
            conn.close()
        raise e

def get_or_create_cliente(nombre, conn=None):
    """Obtiene el ID de un cliente o lo crea si no existe"""
    if conn is None:
        # Usar el contexto si no se proporciona una conexión externa
        with db_connection() as conn:
            c = conn.cursor()
            
            # Buscar cliente existente
            c.execute("SELECT id_cliente FROM clientes WHERE nombre = %s", (nombre,))
            result = c.fetchone()
            
            if result:
                return result[0]
            else:
                # Crear nuevo cliente
                c.execute("INSERT INTO clientes (nombre) VALUES (%s) RETURNING id_cliente", (nombre,))
                cliente_id = c.fetchone()[0]
                conn.commit()
                return cliente_id
    else:
        # Usar la conexión proporcionada
        c = conn.cursor()
        
        # Buscar cliente existente
        c.execute("SELECT id_cliente FROM clientes WHERE nombre = %s", (nombre,))
        result = c.fetchone()
        
        if result:
            return result[0]
        else:
            # Crear nuevo cliente
            c.execute("INSERT INTO clientes (nombre) VALUES (%s) RETURNING id_cliente", (nombre,))
            cliente_id = c.fetchone()[0]
            conn.commit()
            return cliente_id

def get_empleado_rol_id(nombre_empleado, conn=None):
    """Obtiene el rol_id de un empleado basándose en su nombre y la coincidencia con usuarios o nómina"""
    from .utils import normalize_text
    import re

    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    c = conn.cursor()

    try:
        empleado_normalizado = normalize_text(nombre_empleado)
        if not empleado_normalizado:
            if close_conn:
                conn.close()
            return None

        stopwords = {"de", "del", "la", "las", "los", "y", "e", "san", "santa", "da", "do", "das", "dos"}
        def tokens(s):
            return [t for t in re.split(r"\s+", normalize_text(s)) if t and t not in stopwords]

        emp_tokens = tokens(empleado_normalizado)
        if not emp_tokens:
            if close_conn:
                conn.close()
            return None

        # Heurística: últimos 2 tokens como apellidos, resto como nombres
        surname_tokens = emp_tokens[-2:] if len(emp_tokens) >= 2 else emp_tokens[-1:]
        name_tokens = emp_tokens[:-2] if len(emp_tokens) >= 3 else (emp_tokens[:-1] if len(emp_tokens) == 2 else [])

        c.execute("""
            SELECT u.id, u.nombre, u.apellido, u.rol_id
            FROM usuarios u
            WHERE u.nombre IS NOT NULL AND u.apellido IS NOT NULL
        """)
        usuarios = c.fetchall()

        best = None  # (score, rol_id)
        for _, nombre, apellido, rol_id in usuarios:
            user_name_tokens = tokens(nombre)
            user_surname_tokens = tokens(apellido)

            surname_match = sum(1 for t in surname_tokens if t in user_surname_tokens)
            name_match = sum(1 for t in name_tokens if t in user_name_tokens)
            global_intersection = len(set(emp_tokens) & (set(user_name_tokens) | set(user_surname_tokens)))

            # Ponderar apellidos + bonus por 3+ tokens en común
            score = (2 * surname_match) + name_match + (1 if global_intersection >= 3 else 0)

            # Umbral: al menos 1 apellido y 1 nombre, o 2 apellidos, o intersección global fuerte
            passes = (surname_match >= 2) or (surname_match >= 1 and name_match >= 1) or (global_intersection >= 3)
            if passes:
                if best is None or score > best[0]:
                    best = (score, rol_id)

        if best is not None:
            if close_conn:
                conn.close()
            return best[1]

        # Fallback: buscar en nómina con la misma heurística y mapear a rol por departamento/cargo
        c.execute("""
            SELECT nombre, apellido, departamento, cargo
            FROM nomina
            WHERE activo = true
        """)
        nomina_results = c.fetchall()

        best_nomina = None  # (score, departamento, cargo)
        for nombre, apellido, departamento, cargo in nomina_results:
            n_tokens = tokens(nombre)
            a_tokens = tokens(apellido)

            surname_match = sum(1 for t in surname_tokens if t in a_tokens)
            name_match = sum(1 for t in name_tokens if t in n_tokens)
            global_intersection = len(set(emp_tokens) & (set(n_tokens) | set(a_tokens)))
            score = (2 * surname_match) + name_match + (1 if global_intersection >= 3 else 0)

            passes = (surname_match >= 2) or (surname_match >= 1 and name_match >= 1) or (global_intersection >= 3)
            if passes:
                if best_nomina is None or score > best_nomina[0]:
                    best_nomina = (score, departamento, cargo)

        if best_nomina is not None:
            departamento, cargo = best_nomina[1], best_nomina[2]
            if departamento and departamento.strip() and departamento.lower() != "falta dato":
                c.execute("SELECT id_rol FROM roles WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(%s))", (departamento,))
                r = c.fetchone()
                if r:
                    if close_conn:
                        conn.close()
                    return r[0]
            if cargo and cargo.strip() and cargo.lower() != "falta dato":
                c.execute("SELECT id_rol FROM roles WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(%s))", (cargo,))
                r = c.fetchone()
                if r:
                    if close_conn:
                        conn.close()
                    return r[0]

        if close_conn:
            conn.close()
        return None
    except Exception:
        if close_conn:
            conn.close()
        return None

def get_tecnico_rol_id(tecnico_nombre, conn=None):
    """Obtiene el rol_id de un técnico basándose en su nombre y la coincidencia con usuarios"""
    # Mantener compatibilidad hacia atrás llamando a la nueva función
    return get_empleado_rol_id(tecnico_nombre, conn)

def get_or_create_tipo_tarea(descripcion, conn=None, empleado_nombre=None, tecnico_nombre=None):
    """Obtiene el ID de un tipo de tarea o lo crea si no existe (con validación de duplicados)
    Si se crea un nuevo tipo de tarea y se proporciona empleado_nombre o tecnico_nombre, lo asocia automáticamente al rol del empleado"""
    # Normalizar la descripción
    descripcion_normalizada = ' '.join(descripcion.strip().split()).title()
    
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    
    # Buscar tipo de tarea existente (insensible a mayúsculas/minúsculas)
    c.execute("SELECT id_tipo FROM tipos_tarea WHERE LOWER(TRIM(descripcion)) = LOWER(TRIM(%s))", 
             (descripcion_normalizada,))
    result = c.fetchone()
    
    if result:
        if close_conn:
            conn.close()
        return result[0]
    else:
        # Crear nuevo tipo de tarea
        try:
            c.execute("INSERT INTO tipos_tarea (descripcion) VALUES (%s) RETURNING id_tipo", (descripcion_normalizada,))
            tipo_id = c.fetchone()[0]
            
            # Determinar qué nombre usar (priorizar empleado_nombre sobre tecnico_nombre)
            nombre_a_usar = empleado_nombre or tecnico_nombre
            
            # Si se proporciona el nombre del empleado/técnico, asociar automáticamente al rol
            if nombre_a_usar:
                rol_id = get_empleado_rol_id(nombre_a_usar, conn)
                if rol_id:
                    # Verificar si ya existe la asociación
                    c.execute("SELECT COUNT(*) FROM tipos_tarea_roles WHERE id_tipo = %s AND id_rol = %s", 
                             (tipo_id, rol_id))
                    if c.fetchone()[0] == 0:
                        # Crear la asociación tipo_tarea -> rol
                        c.execute("INSERT INTO tipos_tarea_roles (id_tipo, id_rol) VALUES (%s, %s)", 
                                 (tipo_id, rol_id))
            
            conn.commit()
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
    c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE descripcion = %s", (modalidad,))
    result = c.fetchone()
    
    if result:
        if close_conn:
            conn.close()
        return result[0]
    else:
        # Crear nueva modalidad
        try:
            c.execute("INSERT INTO modalidades_tarea (descripcion) VALUES (%s) RETURNING id_modalidad", (modalidad,))
            modalidad_id = c.fetchone()[0]
            conn.commit()
            if close_conn:
                conn.close()
            return modalidad_id
        except Exception as e:
            if close_conn:
                conn.close()
            raise e

def get_unassigned_records_for_user(user_id):
    """Obtiene registros sin asignar que podrían pertenecer a un usuario basándose en el nombre del técnico"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT nombre, apellido FROM usuarios WHERE id = %s", (user_id,))
        user_data = c.fetchone()
        
        if not user_data or not user_data[0] or not user_data[1]:
            conn.close()
            return pd.DataFrame()  # Usuario sin nombre completo
        
        nombre_completo = f"{user_data[0]} {user_data[1]}"
        conn.close()
        
        query = '''
            SELECT r.id, r.fecha, t.nombre as tecnico, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.descripcion as modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.descripcion, r.mes
            FROM registros r
            JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            JOIN clientes c ON r.id_cliente = c.id_cliente
            JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
            WHERE r.usuario_id IS NULL AND t.nombre = :nombre
            ORDER BY r.fecha DESC
        '''
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine, params={"nombre": nombre_completo})
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo registros sin asignar para usuario: {e}")
        return pd.DataFrame()

def get_user_rol_id(user_id):
    """Obtiene el rol_id del usuario"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT rol_id FROM usuarios WHERE id = %s", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def check_record_duplicate(fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, tiempo, exclude_id=None):
    """
    Verifica si existe un registro duplicado
    
    Args:
        fecha: Fecha del registro
        id_tecnico: ID del técnico
        id_cliente: ID del cliente
        id_tipo: ID del tipo de tarea
        id_modalidad: ID de la modalidad
        tarea_realizada: Descripción de la tarea
        tiempo: Tiempo empleado
        exclude_id: ID del registro a excluir (para ediciones)
    
    Returns:
        bool: True si existe duplicado, False si no
    """
    with db_connection() as conn:
        c = conn.cursor()
        
        if exclude_id:
            # Para ediciones - excluir el registro actual
            c.execute('''
                SELECT COUNT(*) FROM registros 
                WHERE fecha = %s AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s 
                AND id_modalidad = %s AND tarea_realizada = %s AND tiempo = %s AND id != %s
            ''', (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, tiempo, exclude_id))
        else:
            # Para nuevos registros
            c.execute('''
                SELECT COUNT(*) FROM registros 
                WHERE fecha = %s AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s 
                AND id_modalidad = %s AND tarea_realizada = %s AND tiempo = %s
            ''', (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, tiempo))
        
        return c.fetchone()[0] > 0

def check_registro_duplicate(fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, tiempo, registro_id=None):
    """Verifica si existe un registro duplicado
    
    Args:
        registro_id: Si se proporciona, excluye este registro de la verificación (útil para actualizaciones)
    
    Returns:
        bool: True si existe un duplicado, False en caso contrario
    """
    # Llamar a la nueva función con los parámetros correctos
    return check_record_duplicate(fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, tiempo, registro_id)

def get_registros_by_rol_with_date_filter(rol_id, filter_type='all_time', custom_month=None, custom_year=None, start_date=None, end_date=None):
    """
    Obtiene registros filtrados por rol y fecha
    
    Args:
        rol_id: ID del rol
        filter_type: 'current_month', 'custom_month', 'custom_range', 'all_time'
        custom_month: Mes personalizado (1-12)
        custom_year: Año personalizado
        start_date: fecha inicio (date) para período de tiempo
        end_date: fecha fin (date) para período de tiempo
    
    Returns:
        DataFrame con los registros filtrados
    """
    try:
        conn = get_connection()
        
        # Obtener el nombre del rol actual
        c = conn.cursor()
        c.execute("SELECT nombre FROM roles WHERE id_rol = %s", (rol_id,))
        rol_result = c.fetchone()
        if not rol_result:
            conn.close()
            return pd.DataFrame()  # Retornar DataFrame vacío si el rol no existe
        
        rol_nombre = rol_result[0]
        conn.close()
        
        # Preparar parámetros y filtro de fecha (usando binds de SQLAlchemy)
        params = {}
        date_filter = ""
        
        if filter_type == 'current_month':
            # Filtro para el mes actual usando formato dd/mm/yy
            from datetime import datetime
            current_month = datetime.now().month
            current_year = datetime.now().year
            year_2digit = str(current_year)[-2:]  # Obtener últimos 2 dígitos del año
            date_filter = "AND (SUBSTRING(r.fecha, 4, 2) = :month AND SUBSTRING(r.fecha, 7, 2) = :year2)"
            params.update({"month": f"{current_month:02d}", "year2": year_2digit})
        elif filter_type == 'custom_month' and custom_month and custom_year:
            # Ajustar para formato dd/mm/yy usando SUBSTRING en PostgreSQL
            year_2digit = str(custom_year)[-2:]  # Obtener últimos 2 dígitos del año
            date_filter = "AND (SUBSTRING(r.fecha, 4, 2) = :month AND SUBSTRING(r.fecha, 7, 2) = :year2)"
            params.update({"month": f"{custom_month:02d}", "year2": year_2digit})
        elif filter_type == 'custom_range' and start_date and end_date:
            # Rango de fechas usando to_date con formato 'DD/MM/YY'
            date_filter = "AND to_date(r.fecha, 'DD/MM/YY') BETWEEN :start_date AND :end_date"
            params.update({"start_date": start_date, "end_date": end_date})
        # Para 'all_time' no agregamos filtro de fecha
        
        # Lógica de consulta según el rol
        engine = get_engine()
        
        if rol_nombre == SYSTEM_ROLES['ADMIN']:
            # Para admin, mostrar TODOS los registros (incluyendo sin asignar)
            query = f'''
                SELECT r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                       tt.descripcion as tipo_tarea, mt.descripcion as modalidad, r.tarea_realizada, 
                       r.numero_ticket, r.tiempo, r.descripcion, r.mes, r.id
                FROM registros r
                JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
                JOIN clientes c ON r.id_cliente = c.id_cliente
                JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
                JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
                WHERE 1=1
                {date_filter.replace("AND", "", 1) if date_filter else ""}
                ORDER BY r.id DESC
            '''
            df = pd.read_sql_query(text(query), con=engine, params=params if params else None)
        else:
            # Para cualquier otro rol, mostrar SOLO registros asignados específicamente a ese rol
            query = f'''
                SELECT r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                       tt.descripcion as tipo_tarea, mt.descripcion as modalidad, r.tarea_realizada, 
                       r.numero_ticket, r.tiempo, r.descripcion, r.mes, r.id
                FROM registros r
                JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
                JOIN clientes c ON r.id_cliente = c.id_cliente
                JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
                JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
                WHERE r.usuario_id IN (
                    SELECT id FROM usuarios 
                    WHERE rol_id = :rol_id
                )
                {date_filter}
                ORDER BY r.id DESC
            '''
            params_with_rol = {"rol_id": rol_id, **params}
            df = pd.read_sql_query(text(query), con=engine, params=params_with_rol if params_with_rol else None)
        
        if 'mes' in df.columns:
            df['mes'] = df['mes'].apply(month_name_es)
        
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo registros por rol con filtro de fecha: {e}")
        return pd.DataFrame()

def get_nomina_dataframe():
    """Obtiene un DataFrame con todos los registros de nómina"""
    query = """SELECT * FROM nomina ORDER BY nombre"""
    engine = get_engine()
    df = pd.read_sql_query(query, con=engine)
    return df

def get_nomina_dataframe_expanded():
    """Obtiene un DataFrame expandido con formato de vista completa para nómina"""
    query = """SELECT * FROM nomina"""
    engine = get_engine()
    df = pd.read_sql_query(query, con=engine)
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
    
    # CORREGIDO: Crear DataFrame expandido con campos intercambiados para mostrar correctamente
    # Campo 'nombre' de BD = apellido real → columna "APELLIDO"
    # Campo 'apellido' de BD = nombre real → columna "NOMBRE"
    expanded_df = pd.DataFrame({
        'APELLIDO': df['nombre'].apply(lambda x: str(x).capitalize() if pd.notna(x) and str(x).strip() != '' else 'falta dato'),
        'NOMBRE': df['apellido'].apply(lambda x: str(x).capitalize() if pd.notna(x) and str(x).strip() != '' else 'falta dato'),
        'MAIL': df['email'].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() != '' and str(x).strip().lower() != 'nan' else 'falta dato'),
        'Celular': df['documento'].apply(lambda x: str(x) if pd.notna(x) and str(x).strip() != '' and not str(x).startswith('AUTO_') else 'falta dato'),
        'Categoria': [cat for cat, func in categorias_funciones],
        'Funcion': [func for cat, func in categorias_funciones],
        'Sector': df['departamento'].apply(lambda x: 'falta dato' if pd.isna(x) or str(x).strip() == '' or str(x).lower() == 'falta dato' else str(x)),
        'Fecha ingreso': df['fecha_ingreso'].apply(lambda x: str(x) if pd.notna(x) and str(x).strip() != '' else 'falta dato'),
        'Fecha Nacimiento': df['fecha_nacimiento'].apply(lambda x: str(x) if pd.notna(x) and str(x).strip() != '' else 'falta dato') if 'fecha_nacimiento' in df.columns else 'falta dato',
        'Edad': df['fecha_nacimiento'].apply(calcular_edad) if 'fecha_nacimiento' in df.columns else 'falta dato',
        'Antigüedad': df['fecha_ingreso'].apply(calcular_antiguedad)
        # Removido 'ACTIVO' para que no se muestre en la vista
    })
    
    return expanded_df

def empleado_existe(nombre, apellido):
    """Verifica si un empleado ya existe en la nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        query = "SELECT COUNT(*) FROM nomina WHERE LOWER(nombre) = LOWER(%s) AND LOWER(apellido) = LOWER(%s)"
        c.execute(query, (nombre.strip(), apellido.strip()))
        count = c.fetchone()[0]
        return count > 0
    except Exception as e:
        log_sql_error(e, "empleado_existe")
        return False
    finally:
        conn.close()

def add_empleado_nomina(nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento=''):
    """Añade un nuevo empleado a la nómina solo si no existe"""
    
    # Verificar si el empleado ya existe
    if empleado_existe(nombre, apellido):
        print(f"⚠️  Empleado ya existe: {apellido}, {nombre} - Saltando inserción")
        return True  # Retornamos True porque no es un error, solo ya existe
    
    conn = get_connection()
    c = conn.cursor()
    try:
        # Crear rol basado en el departamento si es válido
        if departamento and departamento.strip() != '' and departamento.lower() != 'falta dato':
            get_or_create_role_from_sector(departamento)
        
        # Crear rol basado en el cargo si es válido
        if cargo and cargo.strip() != '' and cargo.lower() != 'falta dato':
            # Verificar si ya existe un rol con este cargo
            c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (cargo,))
            if not c.fetchone():
                c.execute("""
                    INSERT INTO roles (nombre, descripcion, is_hidden) 
                    VALUES (%s, %s, %s)
                """, (cargo, f'Rol generado automáticamente para el cargo: {cargo}', False))
        
        # Insertar el empleado
        query = """INSERT INTO nomina (nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento, activo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)"""
        params = (nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento)
        c.execute(query, params)
        conn.commit()
        
        return True
    except Exception as e:
        print(f"Error de integridad al insertar {apellido}, {nombre}: {str(e)}")
        log_sql_error(e, query="INSERT INTO nomina", params=(nombre, apellido, email, documento))
        return False
    except Exception as e:
        print(f"Error general al insertar {apellido}, {nombre}: {str(e)}")
        log_sql_error(e, query="INSERT INTO nomina", params=(nombre, apellido, email, documento))
        return False
    finally:
        conn.close()

def update_empleado_nomina(id_empleado, nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento='', activo=True):
    """Actualiza un empleado existente en la nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Convertir activo a booleano si es necesario
        if isinstance(activo, int):
            activo = bool(activo)
        
        c.execute("""
            UPDATE nomina 
            SET nombre = %s, apellido = %s, email = %s, documento = %s, cargo = %s, 
                departamento = %s, fecha_ingreso = %s, fecha_nacimiento = %s, activo = %s
            WHERE id = %s
        """, (nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento, activo, id_empleado))
        conn.commit()
        return True
    except Exception as e:
        # Error de integridad u otro error
        log_sql_error(e, "update_empleado_nomina")
        return False
    except Exception as e:
        log_sql_error(e, "update_empleado_nomina")
        raise e
    finally:
        conn.close()

def delete_empleado_nomina(id_empleado):
    """Elimina un empleado de la nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM nomina WHERE id = %s", (id_empleado,))
        conn.commit()
        return True
    except Exception as e:
        log_sql_error(e, "delete_empleado_nomina")
        raise e
    finally:
        conn.close()

def process_nomina_excel(excel_df):
    """Procesa un DataFrame de Excel y guarda los empleados en la nómina"""
    success_count = 0
    error_count = 0
    duplicate_count = 0
    error_details = []
    duplicate_details = []  # Lista de empleados duplicados
    success_details = []    # Lista de empleados creados exitosamente
    filtered_inactive_count = 0  # Contador para empleados inactivos filtrados
    
    # Hacer una copia del DataFrame para no modificar el original
    df = excel_df.copy()
    
    # Eliminar filas donde todas las columnas son NaN (por si no se hizo antes)
    df = df.dropna(how='all')
    
    # Eliminar columnas donde todas las filas son NaN (por si no se hizo antes)
    df = df.dropna(axis=1, how='all')
    
    # DETECCIÓN INTELIGENTE DE COLUMNAS
    def detect_column_mapping(df_columns):
        """Detecta automáticamente qué columnas corresponden a nombres y apellidos"""
        column_mapping = {}
        
        # Patrones para detectar columnas de nombres
        nombre_patterns = ['NOMBRE', 'NAME', 'FIRST_NAME', 'FIRSTNAME', 'NOMBRES']
        apellido_patterns = ['APELLIDO', 'APELLIDOS', 'LASTNAME', 'LAST_NAME', 'SURNAME']
        
        # Buscar columnas que contengan nombres
        for col in df_columns:
            col_upper = col.upper().strip()
            
            # Detectar columna de nombres
            for pattern in nombre_patterns:
                if pattern in col_upper:
                    column_mapping['NOMBRE'] = col
                    break
            
            # Detectar columna de apellidos
            for pattern in apellido_patterns:
                if pattern in col_upper:
                    column_mapping['APELLIDO'] = col
                    break
        
        return column_mapping
    
    # Detectar mapeo de columnas automáticamente
    auto_column_mapping = detect_column_mapping(df.columns)
    
    # Crear un diccionario para mapear columnas insensibles a mayúsculas
    column_map = {}
    for col in df.columns:
        col_upper = col.upper()
        column_map[col_upper] = col
    
    # Agregar mapeo automático detectado
    for key, value in auto_column_mapping.items():
        column_map[key] = value
    
    # Función auxiliar para obtener valor de columna insensible a mayúsculas
    def get_column_value(row, column_name):
        actual_column = column_map.get(column_name.upper())
        if actual_column and actual_column in df.columns:
            return row[actual_column]
        return None
    
    # Mostrar información de detección de columnas
    print("🔍 Detección automática de columnas:")
    for key, value in auto_column_mapping.items():
        print(f"   {key} → {value}")
    
    # VALIDACIÓN INTELIGENTE DE CONTENIDO
    def validate_name_content(df, nombre_col, apellido_col):
        """Valida si las columnas detectadas realmente contienen nombres/apellidos"""
        if not nombre_col or not apellido_col:
            return True  # Si no hay ambas columnas, usar lógica existente
        
        # Tomar una muestra de 5 filas para validar
        sample_size = min(5, len(df))
        sample_rows = df.head(sample_size)
        
        nombre_seems_correct = 0
        apellido_seems_correct = 0
        
        for _, row in sample_rows.iterrows():
            nombre_val = str(row[nombre_col]).strip() if pd.notna(row[nombre_col]) else ""
            apellido_val = str(row[apellido_col]).strip() if pd.notna(row[apellido_col]) else ""
            
            # Heurística simple: los nombres suelen ser más cortos que los apellidos
            # y no contienen comas
            if nombre_val and not ',' in nombre_val and len(nombre_val.split()) <= 2:
                nombre_seems_correct += 1
            
            if apellido_val and not ',' in apellido_val and len(apellido_val.split()) <= 2:
                apellido_seems_correct += 1
        
        # Si más del 60% de la muestra parece correcta, mantener el mapeo
        confidence_threshold = 0.6
        nombre_confidence = nombre_seems_correct / sample_size
        apellido_confidence = apellido_seems_correct / sample_size
        
        print(f"📊 Confianza en detección: NOMBRE={nombre_confidence:.1%}, APELLIDO={apellido_confidence:.1%}")
        
        # Si la confianza es baja, sugerir inversión
        if nombre_confidence < confidence_threshold and apellido_confidence < confidence_threshold:
            print("⚠️  Baja confianza en detección. Puede que las columnas estén invertidas.")
            return False
        
        return True
    
    # Validar contenido si se detectaron ambas columnas
    nombre_col = auto_column_mapping.get('NOMBRE')
    apellido_col = auto_column_mapping.get('APELLIDO')
    
    if nombre_col and apellido_col:
        content_valid = validate_name_content(df, nombre_col, apellido_col)
        if not content_valid:
            print("🔄 Intercambiando columnas detectadas debido a baja confianza...")
            # Intercambiar en el mapeo
            column_map['NOMBRE'] = apellido_col
            column_map['APELLIDO'] = nombre_col
            auto_column_mapping['NOMBRE'] = apellido_col
            auto_column_mapping['APELLIDO'] = nombre_col
    
    
    # CREAR ROLES Y GRUPOS BÁSICOS AL INICIO DEL PROCESAMIENTO
    with db_connection() as conn:
        c = conn.cursor()
        
        # 1. Crear rol "Sin Rol" si no existe
        c.execute("SELECT id_rol FROM roles WHERE nombre = %s", ('Sin Rol',))
        if not c.fetchone():
            c.execute("""
                INSERT INTO roles (nombre, descripcion, is_hidden) 
                VALUES (%s, %s, %s)
            """, ('Sin Rol', 'Rol por defecto para usuarios sin rol específico', True))
            print("✅ Rol 'Sin Rol' creado automáticamente")
        
        # 2. Crear grupo "General" si no existe
        c.execute("SELECT id_grupo FROM grupos WHERE nombre = %s", ('General',))
        if not c.fetchone():
            c.execute("""
                INSERT INTO grupos (nombre, descripcion) 
                VALUES (%s, %s)
            """, ('General', 'Grupo por defecto para usuarios'))
            print("✅ Grupo 'General' creado automáticamente")
        
        # 3. Pre-crear roles basados en departamentos únicos del Excel
        # Obtener departamentos únicos del Excel
        departamentos_unicos = set()
        cargos_unicos = set()
        
        for index, row in df.iterrows():
            # Obtener departamento
            sector_val = get_column_value(row, 'SECTOR')
            if sector_val and not pd.isna(sector_val):
                departamento = str(sector_val).strip()
                if departamento and departamento.lower() != 'falta dato':
                    departamentos_unicos.add(departamento)
            
            # Obtener cargo (combinación de categoría y función)
            categoria_val = get_column_value(row, 'CATEGORIA')
            funcion_val = get_column_value(row, 'FUNCION')
            
            categoria = str(categoria_val).strip() if categoria_val and not pd.isna(categoria_val) else ''
            funcion = str(funcion_val).strip() if funcion_val and not pd.isna(funcion_val) else ''
            
            if categoria and funcion:
                cargo = f"{categoria} - {funcion}"
            elif categoria:
                cargo = categoria
            elif funcion:
                cargo = funcion
            else:
                cargo = ''
            
            if cargo and cargo.lower() != 'falta dato':
                cargos_unicos.add(cargo)
        
        # Crear roles para departamentos únicos
        roles_departamentos_creados = 0
        for departamento in departamentos_unicos:
            c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (departamento,))
            if not c.fetchone():
                c.execute("""
                    INSERT INTO roles (nombre, descripcion, is_hidden) 
                    VALUES (%s, %s, %s)
                """, (departamento, f'Rol generado automáticamente para el departamento: {departamento}', False))
                roles_departamentos_creados += 1
        
        # Crear roles para cargos únicos
        roles_cargos_creados = 0
        for cargo in cargos_unicos:
            c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (cargo,))
            if not c.fetchone():
                c.execute("""
                    INSERT INTO roles (nombre, descripcion, is_hidden) 
                    VALUES (%s, %s, %s)
                """, (cargo, f'Rol generado automáticamente para el cargo: {cargo}', False))
                roles_cargos_creados += 1
        
        conn.commit()
        
        if roles_departamentos_creados > 0:
            print(f"✅ {roles_departamentos_creados} roles de departamentos creados automáticamente")
        if roles_cargos_creados > 0:
            print(f"✅ {roles_cargos_creados} roles de cargos creados automáticamente")
    
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
    
    # Verificar columnas requeridas
    required_columns = ['NOMBRE']  # Solo NOMBRE es obligatorio
    for col in required_columns:
        if not any(c.upper() == col for c in df.columns):
            raise ValueError(f"Columna requerida '{col}' no encontrada en el archivo")
    
    # Obtener conexión a la base de datos
    with db_connection() as conn:
        
        # Procesar cada fila del DataFrame
        for index, row in df.iterrows():
            try:
                # Verificar si el empleado está activo
                activo_val = get_column_value(row, 'ACTIVO')
                
                # Si ACTIVO es 0 o FALSE, ignorar este empleado
                if activo_val is not None and not pd.isna(activo_val):
                    activo_str = str(activo_val).strip().upper()
                    if activo_str == 'FALSE' or activo_str == 'NO' or activo_str == '0' or activo_str == 'F':
                        filtered_inactive_count += 1
                        continue
                
                # Obtener valores básicos
                nombre_val = get_column_value(row, 'NOMBRE')
                apellido_val = get_column_value(row, 'APELLIDO')
                celular_val = get_column_value(row, 'CELULAR')
                
                # Asegurarse de que al menos hay un nombre
                if pd.isna(nombre_val) or not nombre_val:
                    continue
                    
                # Rellenar valores faltantes
                nombre_str = str(nombre_val).strip() if not pd.isna(nombre_val) else "falta dato"
                apellido_str = str(apellido_val).strip() if not pd.isna(apellido_val) else "falta dato"
                celular_str = str(celular_val).strip() if not pd.isna(celular_val) else "falta dato"
                
        
                # Procesar celular - si no hay valor válido, usar "falta dato"
                if celular_str != "falta dato":
                    documento = celular_str  # Usar celular directamente
                else:
                    documento = "falta dato"  # En lugar de generar AUTO_
                
                # Procesar el campo NOMBRE que puede venir en formato "APELLIDO, NOMBRE"
                nombre_completo = str(nombre_val).strip()
                apellido_from_col = get_column_value(row, 'APELLIDO')
                apellido_from_col = str(apellido_from_col).strip() if apellido_from_col and not pd.isna(apellido_from_col) else ''
                
                # Extraer apellido y nombre
                nombre = ''
                apellido = ''
                
                if apellido_from_col:
                    apellido = format_name(apellido_from_col)  # Columna APELLIDO = apellidos
                    nombre = format_name(nombre_completo)     # Columna NOMBRE = nombres
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
                
                # CALCULAR EDAD DINÁMICAMENTE basándose en fecha_nacimiento
                def calcular_edad(fecha_nacimiento_str):
                    if not fecha_nacimiento_str or fecha_nacimiento_str == '':
                        return ''
                    try:
                        from datetime import datetime
                        fecha_nac = datetime.strptime(fecha_nacimiento_str, '%Y-%m-%d')
                        hoy = datetime.now()
                        edad = hoy.year - fecha_nac.year
                        if hoy.month < fecha_nac.month or (hoy.month == fecha_nac.month and hoy.day < fecha_nac.day):
                            edad -= 1
                        return str(edad)
                    except:
                        return ''
                
                # CALCULAR ANTIGÜEDAD DINÁMICAMENTE basándose en fecha_ingreso
                def calcular_antiguedad(fecha_ingreso_str):
                    if not fecha_ingreso_str or fecha_ingreso_str == '':
                        return ''
                    try:
                        from datetime import datetime
                        fecha_ing = datetime.strptime(fecha_ingreso_str, '%Y-%m-%d')
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
                
                edad = calcular_edad(fecha_nacimiento)
                antiguedad = calcular_antiguedad(fecha_ingreso)
                
                # Añadir fila al DataFrame de vista previa (SIN la columna ACTIVO)
                preview_row = {
                    'NOMBRE': nombre,
                    'Apellido': apellido,
                    'MAIL': email,
                    'Celular': celular_str,
                    'Categoria': categoria,
                    'Funcion': funcion,
                    'Sector': departamento,
                    'Fecha ingreso': fecha_ingreso,
                    'Fecha Nacimiento': fecha_nacimiento,
                    'Edad': edad,
                    'Antigüedad': antiguedad
                    # Removido 'ACTIVO': '1' para que no se muestre en la vista
                }
                # Asegurarse de que no haya valores None o NaN
                for key in preview_row:
                    if pd.isna(preview_row[key]) or preview_row[key] is None:
                        preview_row[key] = ''
                    elif not isinstance(preview_row[key], str):
                        preview_row[key] = str(preview_row[key])  # Convertir todos los valores a string
                        
                preview_rows.append(preview_row)
                
                # Verificar si el empleado ya existe (duplicado)
                if empleado_existe(nombre, apellido):
                    duplicate_count += 1
                    duplicate_details.append(f"{apellido}, {nombre}")
                    print(f"🔄 Empleado duplicado (no guardado): {apellido}, {nombre}")
                    continue
                
                # Añadir empleado a la base de datos
                print(f"Procesando empleado {index+1}: {apellido}, {nombre}")
                resultado = add_empleado_nomina(nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento)
                if resultado:
                    success_count += 1
                    success_details.append(f"{apellido}, {nombre}")
                    print(f"✅ Guardado exitoso: {apellido}, {nombre}")
                else:
                    error_count += 1
                    error_details.append(f"{apellido}, {nombre}")
                    print(f"❌ Error al guardar: {apellido}, {nombre}")
            
            except Exception as e:
                error_count += 1
                error_details.append(f"Error SQL en fila {index+1}: {str(e)}")
                print(f"❌ Error SQL en fila {index+1}: {str(e)}")
                log_sql_error(e, query="process_nomina_excel", params=f"fila {index+1}")
            
            except Exception as e:
                error_count += 1
                error_details.append(f"Error general en fila {index+1}: {str(e)}")
                print(f"❌ Error general en fila {index+1}: {str(e)}")
    
    # Crear DataFrame de vista previa
    preview_df = pd.DataFrame(preview_rows) if preview_rows else pd.DataFrame()
    
    # Estadísticas de procesamiento
    stats = {
        'success_count': success_count,
        'error_count': error_count,
        'duplicate_count': duplicate_count,
        'filtered_inactive_count': filtered_inactive_count,
        'total_processed': success_count + error_count + duplicate_count + filtered_inactive_count,
        'error_details': error_details,
        'duplicate_details': duplicate_details,
        'success_details': success_details,
        'preview_df': preview_df
    }
    
    return stats

def get_user_info(user_id):
    """Obtiene información completa del usuario por ID"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT nombre, apellido, username, email FROM usuarios WHERE id = %s', (user_id,))
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
        c.execute("INSERT INTO roles (nombre, descripcion) VALUES (%s, %s) RETURNING id_rol", 
                 (sector.strip(), f"Rol generado automáticamente desde el sector de nómina: {sector.strip()}"))
        new_role_id = c.fetchone()[0]
        conn.commit()
        
        conn.close()
        return new_role_id, True
        
    except Exception as e:
        conn.close()
        raise e

def migrate_nomina_remove_unique_constraint():
    """Migra la tabla nomina para remover la restricción UNIQUE del campo documento"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # En PostgreSQL, simplemente eliminar la restricción si existe
        c.execute("""
            ALTER TABLE nomina 
            DROP CONSTRAINT IF EXISTS nomina_documento_key
        """)
        
        conn.commit()
        conn.close()
        print("✅ Migración completada: restricción UNIQUE removida del campo documento")
        return True
        
    except Exception as e:
        print(f"❌ Error en migración: {str(e)}")
        conn.rollback()
        conn.close()
        return False



def clean_duplicate_task_types():
    """Limpia tipos de tarea duplicados, manteniendo solo uno de cada tipo"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Obtener todos los tipos de tarea con duplicados
        c.execute("""
            SELECT descripcion, COUNT(*) as count, MIN(id_tipo) as keep_id
            FROM tipos_tarea 
            GROUP BY LOWER(TRIM(descripcion))
            HAVING COUNT(*) > 1
        """)
        
        duplicates = c.fetchall()
        deleted_count = 0
        
        for descripcion, count, keep_id in duplicates:
            # Obtener todos los IDs de este tipo duplicado
            c.execute("SELECT id_tipo FROM tipos_tarea WHERE LOWER(TRIM(descripcion)) = LOWER(TRIM(%s))", (descripcion,))
            all_ids = [row[0] for row in c.fetchall()]
            
            # IDs a eliminar (todos excepto el que vamos a mantener)
            ids_to_delete = [id_tipo for id_tipo in all_ids if id_tipo != keep_id]
            
            for id_to_delete in ids_to_delete:
                # Actualizar registros que usan este tipo
                c.execute("UPDATE registros SET id_tipo = %s WHERE id_tipo = %s", (keep_id, id_to_delete))
                
                # Eliminar relaciones con roles
                c.execute("DELETE FROM tipos_tarea_roles WHERE id_tipo = %s", (id_to_delete,))
                
                # Eliminar puntajes asociados
                c.execute("DELETE FROM tipos_tarea_puntajes WHERE id_tipo = %s", (id_to_delete,))
                
                # Eliminar el tipo duplicado
                c.execute("DELETE FROM tipos_tarea WHERE id_tipo = %s", (id_to_delete,))
                
                deleted_count += 1
        
        conn.commit()
        return deleted_count, len(duplicates)
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def update_tecnico_from_user(old_nombre_completo, nuevo_nombre_completo):
    """Actualiza o crea un técnico basado en el cambio de nombre de usuario"""
    if not nuevo_nombre_completo:
        return
        
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Si cambió el nombre, actualizar el técnico existente
        if old_nombre_completo and nuevo_nombre_completo != old_nombre_completo:
            c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = %s', (old_nombre_completo,))
            old_tecnico = c.fetchone()
            if old_tecnico:
                c.execute('UPDATE tecnicos SET nombre = %s WHERE nombre = %s', 
                            (nuevo_nombre_completo, old_nombre_completo))
        
        # Verificar si el técnico ya existe con el nuevo nombre
        c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = %s', (nuevo_nombre_completo,))
        tecnico = c.fetchone()
        if not tecnico:
            # Crear el técnico si no existe
            c.execute('INSERT INTO tecnicos (nombre) VALUES (%s)', (nuevo_nombre_completo,))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        log_sql_error(e, "update_tecnico_from_user")
        return False
    finally:
        conn.close()

def update_user_profile_complete(user_id, nombre=None, apellido=None, email=None):
    """Actualiza el perfil de usuario y gestiona los técnicos asociados"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        c.execute('SELECT nombre, apellido FROM usuarios WHERE id = %s', (user_id,))
        old_user_info = c.fetchone()
        old_nombre = old_user_info[0] if old_user_info[0] else ''
        old_apellido = old_user_info[1] if old_user_info[1] else ''
        old_nombre_completo = f"{old_nombre} {old_apellido}".strip()
        
        # Capitalizar nombre y apellido
        nuevo_nombre_cap = nombre.strip().capitalize() if nombre else ''
        nuevo_apellido_cap = apellido.strip().capitalize() if apellido else ''
        
        c.execute('UPDATE usuarios SET nombre = %s, apellido = %s, email = %s WHERE id = %s',
                    (nuevo_nombre_cap, nuevo_apellido_cap, email.strip() if email else None, user_id))
        
        nuevo_nombre_completo = f"{nuevo_nombre_cap} {nuevo_apellido_cap}".strip()
        
        # Actualizar o crear técnico usando la función auxiliar
        update_tecnico_from_user(old_nombre_completo, nuevo_nombre_completo)
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        log_sql_error(e, "update_user_profile_complete")
        return False
    finally:
        conn.close()

def get_cliente_puntaje(id_cliente):
    """Obtiene el puntaje de un cliente específico"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT puntaje FROM clientes_puntajes WHERE id_cliente = %s", (id_cliente,))
    resultado = c.fetchone()
    conn.close()
    return resultado[0] if resultado else 0

def get_cliente_puntaje_by_nombre(nombre_cliente):
    """Obtiene el puntaje de un cliente por su nombre"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT cp.puntaje 
        FROM clientes_puntajes cp
        JOIN clientes c ON cp.id_cliente = c.id_cliente
        WHERE c.nombre = %s
    """, (nombre_cliente,))
    resultado = c.fetchone()
    conn.close()
    return resultado[0] if resultado else 0

def set_cliente_puntaje(id_cliente, puntaje):
    """Establece el puntaje para un cliente específico"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Intentar actualizar si ya existe
        c.execute("""
            INSERT INTO clientes_puntajes (id_cliente, puntaje) 
            VALUES (%s, %s)
            ON CONFLICT(id_cliente) 
            DO UPDATE SET puntaje = %s
        """, (id_cliente, puntaje, puntaje))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error al establecer puntaje: {e}")
        return False
    finally:
        conn.close()

def set_cliente_puntaje_by_nombre(nombre_cliente, puntaje):
    """Establece el puntaje para un cliente por su nombre"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Obtener el ID del cliente
        c.execute("SELECT id_cliente FROM clientes WHERE nombre = %s", (nombre_cliente,))
        resultado = c.fetchone()
        if not resultado:
            return False  # El cliente no existe
        
        id_cliente = resultado[0]
        return set_cliente_puntaje(id_cliente, puntaje)
    except Exception as e:
        print(f"Error al establecer puntaje por nombre: {e}")
        return False
    finally:
        conn.close()

def get_clientes_puntajes_dataframe():
    """Obtiene un DataFrame con todos los clientes y sus puntajes"""
    query = """
    SELECT c.id_cliente, c.nombre, 
           COALESCE(cp.puntaje, 0) as puntaje
    FROM clientes c
    LEFT JOIN clientes_puntajes cp ON c.id_cliente = cp.id_cliente
    ORDER BY c.nombre
    """
    
    engine = get_engine()
    df = pd.read_sql_query(query, con=engine)
    
    return df

def get_grupos_dataframe():
    """Obtiene DataFrame de grupos con sus roles asignados"""
    query = """
    SELECT g.id_grupo, g.nombre, 
           STRING_AGG(r.nombre, ', ') as roles_asignados,
           g.descripcion
    FROM grupos g
    LEFT JOIN grupos_roles gr ON g.id_grupo = gr.id_grupo
    LEFT JOIN roles r ON gr.id_rol = r.id_rol
    GROUP BY g.id_grupo, g.nombre, g.descripcion
    ORDER BY g.nombre
    """
    
    engine = get_engine()
    df = pd.read_sql_query(text(query), con=engine)
    
    # Reemplazar valores None con cadena vacía para mejor visualización
    df['roles_asignados'] = df['roles_asignados'].fillna('')
    df['descripcion'] = df['descripcion'].fillna('')
    
    return df

def get_grupo_puntaje(id_grupo):
    """Obtiene el puntaje de un grupo específico"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT puntaje FROM grupos_puntajes WHERE id_grupo = %s", (id_grupo,))
    resultado = c.fetchone()
    conn.close()
    return resultado[0] if resultado else 0

def get_grupo_puntaje_by_nombre(nombre_grupo):
    """Obtiene el puntaje de un grupo por su nombre"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT gp.puntaje 
        FROM grupos_puntajes gp
        JOIN grupos g ON gp.id_grupo = g.id_grupo
        WHERE g.nombre = %s
    """, (nombre_grupo,))
    resultado = c.fetchone()
    conn.close()
    return resultado[0] if resultado else 0

def set_grupo_puntaje(id_grupo, puntaje):
    """Establece el puntaje para un grupo específico"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Intentar actualizar si ya existe
        c.execute("""
            INSERT INTO grupos_puntajes (id_grupo, puntaje) 
            VALUES (%s, %s)
            ON CONFLICT(id_grupo) 
            DO UPDATE SET puntaje = %s
        """, (id_grupo, puntaje, puntaje))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error al establecer puntaje: {e}")
        return False
    finally:
        conn.close()

def set_grupo_puntaje_by_nombre(nombre_grupo, puntaje):
    """Establece el puntaje para un grupo por su nombre"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Obtener el ID del grupo
        c.execute("SELECT id_grupo FROM grupos WHERE nombre = %s", (nombre_grupo,))
        resultado = c.fetchone()
        if not resultado:
            return False  # El grupo no existe
        
        id_grupo = resultado[0]
        return set_grupo_puntaje(id_grupo, puntaje)
    except Exception as e:
        print(f"Error al establecer puntaje por nombre: {e}")
        return False
    finally:
        conn.close()

def get_grupos_puntajes_dataframe():
    """Obtiene un DataFrame con todos los grupos y sus puntajes"""
    query = """
    SELECT g.id_grupo, g.nombre, g.descripcion, 
           COALESCE(MAX(gp.puntaje), 0) as puntaje,
           STRING_AGG(r.nombre, ', ') as roles_asignados
    FROM grupos g
    LEFT JOIN grupos_puntajes gp ON g.id_grupo = gp.id_grupo
    LEFT JOIN grupos_roles gr ON g.id_grupo = gr.id_grupo
    LEFT JOIN roles r ON gr.id_rol = r.id_rol
    GROUP BY g.id_grupo, g.nombre, g.descripcion
    ORDER BY g.nombre
    """
    engine = get_engine()
    df = pd.read_sql_query(text(query), con=engine)
    
    # Reemplazar valores None con cadena vacía para mejor visualización
    df['roles_asignados'] = df['roles_asignados'].fillna('')
    df['descripcion'] = df['descripcion'].fillna('')
    
    return df

def registrar_actividad(usuario_id, username, tipo_actividad, descripcion):
    """Registra una actividad de usuario en la base de datos
    
    Args:
        usuario_id: ID del usuario (puede ser None para usuarios no autenticados)
        username: Nombre de usuario
        tipo_actividad: Tipo de actividad (login, creacion, edicion, eliminacion)
        descripcion: Descripción detallada de la actividad
    """
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO actividades_usuarios (usuario_id, username, tipo_actividad, descripcion)
            VALUES (%s, %s, %s, %s)
        ''', (usuario_id, username, tipo_actividad, descripcion))
        conn.commit()
        conn.close()
    except Exception as e:
        log_sql_error(e, "INSERT INTO actividades_usuarios", 
                     f"usuario_id: {usuario_id}, username: {username}, tipo: {tipo_actividad}")

def registrar_login(usuario_id, username):
    """Registra un inicio de sesión exitoso"""
    registrar_actividad(usuario_id, username, "login", "Inicio de sesión exitoso")

def registrar_creacion(usuario_id, username, entidad, detalles):
    """Registra la creación de un registro"""
    registrar_actividad(usuario_id, username, "creacion", f"Creación de {entidad}: {detalles}")

def registrar_edicion(usuario_id, username, entidad, detalles):
    """Registra la edición de un registro"""
    registrar_actividad(usuario_id, username, "edicion", f"Edición de {entidad}: {detalles}")

def registrar_eliminacion(usuario_id, username, entidad, detalles):
    """Registra la eliminación de un registro"""
    registrar_actividad(usuario_id, username, "eliminacion", f"Eliminación de {entidad}: {detalles}")

def get_actividades_dataframe(limit=1000):
    """Obtiene un DataFrame con las actividades de usuarios
    
    Args:
        limit: Número máximo de registros a devolver
    
    Returns:
        DataFrame con las actividades de usuarios
    """
    try:
        query = '''
            SELECT 
                a.id, 
                a.usuario_id, 
                a.username, 
                a.tipo_actividad, 
                a.descripcion, 
                a.fecha_hora,
                u.nombre,
                u.apellido
            FROM actividades_usuarios a
            LEFT JOIN usuarios u ON a.usuario_id = u.id
            ORDER BY a.fecha_hora DESC
            LIMIT :limit
        '''
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine, params={"limit": int(limit)})
        
        if not df.empty and 'fecha_hora' in df.columns:
            df['fecha_hora'] = pd.to_datetime(df['fecha_hora'])
            
        return df
    except Exception as e:
        log_sql_error(e, query, limit)
        return pd.DataFrame()

def get_tipo_puntaje(id_tipo):
    """Obtiene el puntaje de un tipo de tarea específico"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT puntaje FROM tipos_tarea_puntajes WHERE id_tipo = %s", (id_tipo,))
    resultado = c.fetchone()
    conn.close()
    return resultado[0] if resultado else 0


def get_tipo_puntaje_by_descripcion(descripcion_tipo):
    """Obtiene el puntaje de un tipo de tarea por su descripción"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT tp.puntaje 
        FROM tipos_tarea_puntajes tp
        JOIN tipos_tarea t ON tp.id_tipo = t.id_tipo
        WHERE t.descripcion = %s
    """, (descripcion_tipo,))
    resultado = c.fetchone()
    conn.close()
    return resultado[0] if resultado else 0


def set_tipo_puntaje(id_tipo, puntaje):
    """Establece el puntaje para un tipo de tarea específico"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Intentar actualizar si ya existe
        c.execute("""
            INSERT INTO tipos_tarea_puntajes (id_tipo, puntaje) 
            VALUES (%s, %s)
            ON CONFLICT(id_tipo) 
            DO UPDATE SET puntaje = %s
        """, (id_tipo, puntaje, puntaje))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error al establecer puntaje: {e}")
        return False
    finally:
        conn.close()


def set_tipo_puntaje_by_descripcion(descripcion_tipo, puntaje):
    """Establece el puntaje para un tipo de tarea por su descripción"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Obtener el ID del tipo de tarea
        c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = %s", (descripcion_tipo,))
        resultado = c.fetchone()
        if not resultado:
            return False  # El tipo de tarea no existe
        
        id_tipo = resultado[0]
        return set_tipo_puntaje(id_tipo, puntaje)
    except Exception as e:
        print(f"Error al establecer puntaje por descripción: {e}")
        return False
    finally:
        conn.close()


def get_tipos_puntajes_dataframe():
    """Obtiene un DataFrame con todos los tipos de tarea y sus puntajes"""
    query = """
    SELECT t.id_tipo, t.descripcion, 
           COALESCE(MAX(tp.puntaje), 0) as puntaje,
           STRING_AGG(r.nombre, ', ') as roles_asociados
    FROM tipos_tarea t
    LEFT JOIN tipos_tarea_puntajes tp ON t.id_tipo = tp.id_tipo
    LEFT JOIN tipos_tarea_roles tr ON t.id_tipo = tr.id_tipo
    LEFT JOIN roles r ON tr.id_rol = r.id_rol
    GROUP BY t.id_tipo, t.descripcion
    ORDER BY t.descripcion
    """
    engine = get_engine()
    df = pd.read_sql_query(text(query), con=engine)
    
    # Reemplazar valores None con cadena vacía para mejor visualización
    df['roles_asociados'] = df['roles_asociados'].fillna('')
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
        c.execute("INSERT INTO grupos (nombre, descripcion) VALUES (%s, %s) RETURNING id_grupo", 
                 (nombre, descripcion))
        nuevo_grupo_id = c.fetchone()[0]
        
        # Si es el grupo "General", asociarlo automáticamente a todos los roles existentes
        if nombre.lower() == 'general':
            c.execute("SELECT id_rol FROM roles WHERE nombre != 'admin'")
            roles_existentes = c.fetchall()
            
            roles_asociados = 0
            for rol_tuple in roles_existentes:
                rol_id = rol_tuple[0]
                try:
                    c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (%s, %s)", 
                             (nuevo_grupo_id, rol_id))
                    roles_asociados += 1
                except Exception:
                    # Ya existe esta relación, no es un error
                    pass
            
            if roles_asociados > 0:
                print(f"✅ Grupo 'General' asociado automáticamente a {roles_asociados} roles existentes")
        
        conn.commit()
        return True
    except Exception:
        return False  # Ya existe un grupo con ese nombre exacto
    finally:
        conn.close()

def get_grupo_by_id(grupo_id):
    """Obtiene un grupo por su ID"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM grupos WHERE id_grupo = %s", (grupo_id,))
        grupo = c.fetchone()
        return grupo
    except Exception as e:
        log_sql_error(e, "get_grupo_by_id")
        return None
    finally:
        conn.close()

def get_roles_by_grupo(grupo_id):
    """Obtiene los roles asociados a un grupo específico"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""SELECT r.id_rol, r.nombre 
                   FROM roles r
                   JOIN grupos_roles gr ON r.id_rol = gr.id_rol
                   WHERE gr.id_grupo = %s""", (grupo_id,))
        roles = c.fetchall()
        return roles
    except Exception as e:
        log_sql_error(e, "get_roles_by_grupo")
        return []
    finally:
        conn.close()

def get_grupos_by_rol(rol_id):
    """Obtiene los grupos asociados a un rol específico"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""SELECT g.id_grupo, g.nombre 
                   FROM grupos g
                   JOIN grupos_roles gr ON g.id_grupo = gr.id_grupo
                   WHERE gr.id_rol = %s""", (rol_id,))
        grupos = c.fetchall()
        return grupos
    except Exception as e:
        log_sql_error(e, "get_grupos_by_rol")
        return []
    finally:
        conn.close()

def assign_grupo_to_rol(grupo_id, rol_id):
    """Asigna un grupo a un rol específico"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (%s, %s)", (grupo_id, rol_id))
        conn.commit()
        return True
    except Exception:
        return False  # Ya existe esta relación
    except Exception as e:
        log_sql_error(e, "assign_grupo_to_rol")
        return False
    finally:
        conn.close()

def remove_grupo_from_rol(grupo_id, rol_id):
    """Elimina la asignación de un grupo a un rol"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM grupos_roles WHERE id_grupo = %s AND id_rol = %s", (grupo_id, rol_id))
        conn.commit()
        return True
    except Exception as e:
        log_sql_error(e, "remove_grupo_from_rol")
        return False
    finally:
        conn.close()

def update_grupo_roles(grupo_id, rol_ids):
    """Actualiza los roles asignados a un grupo"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Eliminar todas las asignaciones actuales
        c.execute("DELETE FROM grupos_roles WHERE id_grupo = %s", (grupo_id,))
        
        # Insertar las nuevas asignaciones
        for rol_id in rol_ids:
            c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (%s, %s)", (grupo_id, rol_id))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        log_sql_error(e, "update_grupo_roles")
        return False
    finally:
        conn.close()

def get_departamentos_list():
    """Obtiene lista única de departamentos desde nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT DISTINCT departamento FROM nomina WHERE departamento IS NOT NULL AND departamento != '' ORDER BY departamento")
        departamentos = [row[0] for row in c.fetchall()]
        return departamentos
    except Exception as e:
        log_sql_error(e, f"Error al obtener departamentos: {e}")
        return []
    finally:
        conn.close()

def generate_standard_password(apellido_completo):
    """Genera contraseña estándar basada en el primer apellido"""
    # Extraer solo el primer apellido (primera palabra)
    primer_apellido = apellido_completo.strip().split()[0]
    
    # Primer apellido con primera letra mayúscula + año actual + punto
    from datetime import datetime
    year = datetime.now().year
    apellido_formatted = primer_apellido.capitalize()
    return f"{apellido_formatted}{year}."

def generate_users_from_nomina(enable_users=False):
    """Genera usuarios desde los datos de nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Obtener TODOS los empleados activos de nómina (sin filtrar duplicados aquí)
        c.execute("""
            SELECT n.id, n.nombre, n.apellido, n.email, n.departamento, n.cargo
            FROM nomina n
            WHERE n.activo = true
            ORDER BY n.nombre, n.apellido
        """)
        
        empleados = c.fetchall()
        stats = {
            'total_empleados': len(empleados),
            'usuarios_creados': 0,
            'tecnicos_creados': 0,
            'roles_creados': 0,
            'usuarios_sin_email': 0,
            'empleados_sin_email': [],
            'usuarios_duplicados': 0,
            'empleados_duplicados': [],
            'usuarios_generados': [], 
            'errores': []
        }
        
        # Obtener rol "sin_rol" del sistema para asignar por defecto
        c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (SYSTEM_ROLES['SIN_ROL'],))
        sin_rol_result = c.fetchone()
        sin_rol_id = sin_rol_result[0] if sin_rol_result else None
        
        # Obtener grupo "General" para asignar por defecto (crear si no existe)
        c.execute("SELECT id_grupo FROM grupos WHERE nombre = %s", ('General',))
        general_grupo_result = c.fetchone()
        if not general_grupo_result:
            # Crear grupo "General" si no existe
            c.execute("""
                INSERT INTO grupos (nombre, descripcion) 
                VALUES (%s, %s) RETURNING id_grupo
            """, ('General', 'Grupo por defecto para usuarios'))
            general_grupo_id = c.fetchone()[0]
        else:
            general_grupo_id = general_grupo_result[0]
        
        # Verificar que tenemos los elementos necesarios
        if not sin_rol_id:
            stats['errores'].append("No se encontró el rol 'sin_rol' del sistema")
            return stats
        
        if not general_grupo_id:
            stats['errores'].append("No se pudo crear o encontrar el grupo 'General'")
            return stats
        
        for empleado in empleados:
            id_empleado, nombre_bd, apellido_bd, email, departamento, cargo = empleado
            
            # Usar los datos tal como vienen de la base de datos de nómina
            nombre = nombre_bd
            apellido = apellido_bd
            
            # Verificar si el email es válido
            if not email or email.strip() == '' or email.lower() == 'falta dato' or '@' not in email:
                stats['usuarios_sin_email'] += 1
                stats['empleados_sin_email'].append(f"{apellido}, {nombre}")
                continue  # Saltar este empleado y no crear usuario
            
            try:
                # Verificar si ya existe un usuario para este empleado (AQUÍ detectamos duplicados)
                c.execute("""
                    SELECT COUNT(*) FROM usuarios 
                    WHERE (nombre = %s AND apellido = %s)
                    OR email = %s
                """, (nombre, apellido, email))
                
                if c.fetchone()[0] > 0:
                    # Ya existe un usuario similar, registrar como duplicado
                    stats['usuarios_duplicados'] += 1
                    stats['empleados_duplicados'].append(f"{apellido}, {nombre}")
                    continue
                
                # Generar username basándose en el email
                base_username = email.split('@')[0].lower()
                
                username = base_username
                counter = 1
                
                while True:
                    c.execute("SELECT id FROM usuarios WHERE username = %s", (username,))
                    if not c.fetchone():
                        break
                    username = f"{base_username}{counter}"
                    counter += 1
                
                # Generar contraseña estándar
                password = generate_standard_password(apellido)
                
                # Hashear la contraseña antes de insertarla
                from .auth import hash_password
                password_hash = hash_password(password)
                
                # Convertir el hash a string si es bytes (CORRECCIÓN)
                if isinstance(password_hash, bytes):
                    password_hash = password_hash.decode('utf-8')
                
                # Determinar el rol basándose en el departamento o cargo
                rol_asignado = sin_rol_id  # Por defecto
                
                # Primero intentar buscar rol por departamento
                if departamento and departamento.strip() != '' and departamento.lower() != 'falta dato':
                    c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (departamento.strip(),))
                    rol_departamento = c.fetchone()
                    if rol_departamento:
                        rol_asignado = rol_departamento[0]
                
                # Si no se encontró por departamento, intentar por cargo
                if rol_asignado == sin_rol_id and cargo and cargo.strip() != '' and cargo.lower() != 'falta dato':
                    c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (cargo.strip(),))
                    rol_cargo = c.fetchone()
                    if rol_cargo:
                        rol_asignado = rol_cargo[0]
                
                # Crear usuario con el rol determinado
                c.execute("""
                    INSERT INTO usuarios (username, password_hash, nombre, apellido, email, 
                                        is_admin, is_active, rol_id) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (username, password_hash, nombre, apellido, email, False, enable_users, rol_asignado))
                
                # Agregar información del usuario generado
                stats['usuarios_generados'].append({
                    'nombre': nombre,
                    'apellido': apellido,
                    'username': username,
                    'password': password,  # Contraseña sin hashear para mostrar
                    'email': email,
                    'activo': 'Sí' if enable_users else 'No'
                })
                
                stats['usuarios_creados'] += 1
                
                # Crear técnico correspondiente con nombre completo
                nombre_completo_tecnico = f"{nombre} {apellido}"
                c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = %s", (nombre_completo_tecnico,))
                if not c.fetchone():
                    c.execute("INSERT INTO tecnicos (nombre) VALUES (%s)", (nombre_completo_tecnico,))
                    stats['tecnicos_creados'] += 1
                
                # Actualizar registros existentes para asociar al usuario
                c.execute("""
                    UPDATE registros SET usuario_id = (
                        SELECT id FROM usuarios WHERE username = %s
                    )
                    WHERE id_tecnico = (
                        SELECT id_tecnico FROM tecnicos WHERE nombre = %s
                    )
                """, (username, nombre_completo_tecnico))
                
            except Exception as e:
                error_msg = f"Error procesando {nombre} {apellido}: {str(e)}"
                stats['errores'].append(error_msg)
                log_sql_error(e, error_msg)
        
        conn.commit()
        return stats
        
    except Exception as e:
        log_sql_error(e, f"Error en generate_users_from_nomina: {e}")
        return {
            'total_empleados': 0,
            'usuarios_creados': 0,
            'tecnicos_creados': 0,
            'roles_creados': 0,
            'usuarios_sin_email': 0,
            'empleados_sin_email': [],
            'usuarios_generados': [],
            'errores': [str(e)]
        }
    finally:
        conn.close()

def get_user_departamento_from_nomina(user_id, conn=None):
    """Obtiene el departamento del usuario desde la tabla nomina basándose en nombre y apellido"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    try:
        # Obtener nombre y apellido del usuario
        c.execute("SELECT nombre, apellido FROM usuarios WHERE id = %s", (user_id,))
        user_data = c.fetchone()
        
        if not user_data or not user_data[0] or not user_data[1]:
            if close_conn:
                conn.close()
            return None
        
        nombre_completo = f"{user_data[0]} {user_data[1]}"
        
        # Buscar el departamento en la tabla nomina
        c.execute("""
            SELECT departamento 
            FROM nomina 
            WHERE LOWER(TRIM(CONCAT(nombre, ' ', apellido))) = LOWER(TRIM(%s))
            AND activo = true
            AND departamento IS NOT NULL 
            AND departamento != ''
            AND LOWER(departamento) != 'falta dato'
            LIMIT 1
        """, (nombre_completo,))
        
        result = c.fetchone()
        departamento = result[0] if result else None
        
        if close_conn:
            conn.close()
        return departamento
        
    except Exception as e:
        if close_conn:
            conn.close()
        log_sql_error(e, "get_user_departamento_from_nomina")
        return None

def get_or_create_grupo_with_department_association(nombre_grupo, user_id=None, conn=None):
    """Obtiene o crea un grupo por nombre y lo asocia automáticamente al departamento del usuario"""
    from .utils import normalize_text
    
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    try:
        # Buscar grupo existente por nombre normalizado
        c.execute("SELECT id_grupo, nombre FROM grupos")
        grupos = c.fetchall()
        
        nombre_normalizado = normalize_text(nombre_grupo)
        for grupo_id, grupo_nombre in grupos:
            if normalize_text(grupo_nombre) == nombre_normalizado:
                # Si el grupo existe y tenemos user_id, asociar al departamento del usuario
                if user_id:
                    asociar_grupo_a_departamento_usuario(grupo_id, user_id, conn)
                if close_conn:
                    conn.close()
                return grupo_id
        
        # Si no existe, crear nuevo grupo
        c.execute("""
            INSERT INTO grupos (nombre, descripcion) 
            VALUES (%s, %s) RETURNING id_grupo
        """, (nombre_grupo, f'Grupo creado automáticamente desde registros: {nombre_grupo}'))
        
        grupo_id = c.fetchone()[0]
        
        # Asociar automáticamente al departamento del usuario si se proporciona user_id
        if user_id:
            asociar_grupo_a_departamento_usuario(grupo_id, user_id, conn)
        
        conn.commit()
        
        if close_conn:
            conn.close()
        return grupo_id
        
    except Exception as e:
        if close_conn:
            conn.close()
        raise e

def asociar_grupo_a_departamento_usuario(grupo_id, user_id, conn=None):
    """Asocia un grupo al departamento del usuario que lo está creando/usando"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    try:
        # Obtener el rol (departamento) del usuario
        c.execute("SELECT rol_id FROM usuarios WHERE id = %s", (user_id,))
        user_rol = c.fetchone()
        
        if user_rol and user_rol[0]:
            rol_id = user_rol[0]
            
            # Verificar si la asociación ya existe
            c.execute("SELECT COUNT(*) FROM grupos_roles WHERE id_grupo = %s AND id_rol = %s", 
                     (grupo_id, rol_id))
            
            if c.fetchone()[0] == 0:  # Si no existe la asociación
                # Crear la asociación
                c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (%s, %s)", 
                         (grupo_id, rol_id))
                
                # Obtener nombres para logging
                c.execute("SELECT nombre FROM grupos WHERE id_grupo = %s", (grupo_id,))
                grupo_nombre = c.fetchone()[0]
                
                c.execute("SELECT nombre FROM roles WHERE id_rol = %s", (rol_id,))
                rol_nombre = c.fetchone()[0]
                
                print(f"✅ Grupo '{grupo_nombre}' asociado automáticamente al departamento '{rol_nombre}'")
        
        if close_conn:
            conn.commit()
            conn.close()
            
    except Exception as e:
        if close_conn:
            conn.close()
        print(f"⚠️ Error al asociar grupo a departamento: {e}")


def get_departamento_by_tecnico_name(tecnico_nombre, conn=None):
    """Obtiene el departamento de un técnico basándose en su nombre desde la tabla nomina
    Versión mejorada que maneja múltiples nombres y apellidos"""
    from .utils import normalize_text
    
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    try:
        # Normalizar el nombre del técnico
        tecnico_normalizado = normalize_text(tecnico_nombre)
        
        # Dividir el nombre en palabras para análisis
        palabras_tecnico = [palabra for palabra in tecnico_normalizado.split() if len(palabra) > 1]
        
        if not palabras_tecnico:
            if close_conn:
                conn.close()
            return None
        
        # Obtener todos los empleados activos con sus departamentos
        c.execute("""
            SELECT nombre, apellido, departamento 
            FROM nomina 
            WHERE activo = true
            AND departamento IS NOT NULL 
            AND departamento != ''
            AND LOWER(departamento) != 'falta dato'
        """)
        
        empleados = c.fetchall()
        
        # Buscar coincidencias usando estrategias múltiples
        for nombre, apellido, departamento in empleados:
            if not nombre or not apellido:
                continue
                
            nombre_normalizado = normalize_text(nombre)
            apellido_normalizado = normalize_text(apellido)
            nombre_completo_normalizado = f"{nombre_normalizado} {apellido_normalizado}".strip()
            
            # Dividir nombres y apellidos en palabras individuales
            palabras_nombre = [p for p in nombre_normalizado.split() if len(p) > 1]
            palabras_apellido = [p for p in apellido_normalizado.split() if len(p) > 1]
            todas_palabras_empleado = palabras_nombre + palabras_apellido
            
            # Estrategia 1: Coincidencia exacta completa
            if nombre_completo_normalizado == tecnico_normalizado:
                if close_conn:
                    conn.close()
                return departamento
            
            # Estrategia 2: Todas las palabras del técnico están en el empleado
            if all(palabra in todas_palabras_empleado for palabra in palabras_tecnico):
                if close_conn:
                    conn.close()
                return departamento
            
            # Estrategia 3: Coincidencia por componentes individuales
            # Verificar si cada palabra del técnico coincide con alguna palabra del empleado
            coincidencias_exactas = 0
            coincidencias_parciales = 0
            
            for palabra_tecnico in palabras_tecnico:
                # Coincidencia exacta con alguna palabra del empleado
                if palabra_tecnico in todas_palabras_empleado:
                    coincidencias_exactas += 1
                # Coincidencia parcial (la palabra del técnico está contenida en alguna palabra del empleado)
                elif any(palabra_tecnico in palabra_empleado or palabra_empleado in palabra_tecnico 
                        for palabra_empleado in todas_palabras_empleado if len(palabra_empleado) > 2):
                    coincidencias_parciales += 1
            
            # Calcular porcentaje de coincidencia
            total_palabras_tecnico = len(palabras_tecnico)
            porcentaje_exacto = coincidencias_exactas / total_palabras_tecnico if total_palabras_tecnico > 0 else 0
            porcentaje_total = (coincidencias_exactas + coincidencias_parciales) / total_palabras_tecnico if total_palabras_tecnico > 0 else 0
            
            # Criterios de validación más estrictos
            if porcentaje_exacto >= 0.8:  # 80% de coincidencias exactas
                if close_conn:
                    conn.close()
                return departamento
            elif porcentaje_total >= 0.9 and coincidencias_exactas >= 1:  # 90% total con al menos una exacta
                if close_conn:
                    conn.close()
                return departamento
            
            # Estrategia 4: Validación especial para casos complejos
            # Si el técnico tiene 2 palabras y el empleado tiene más de 2
            if len(palabras_tecnico) == 2 and len(todas_palabras_empleado) >= 2:
                # Verificar si las 2 palabras del técnico están en las primeras palabras del empleado
                if (palabras_tecnico[0] in palabras_nombre and 
                    palabras_tecnico[1] in (palabras_nombre + palabras_apellido[:2])):
                    if close_conn:
                        conn.close()
                    return departamento
                # O si están en nombre + primer apellido
                if (palabras_tecnico[0] in palabras_nombre and 
                    palabras_tecnico[1] in palabras_apellido):
                    if close_conn:
                        conn.close()
                    return departamento
        
        if close_conn:
            conn.close()
        return None
        
    except Exception as e:
        if close_conn:
            conn.close()
        log_sql_error(e, "get_departamento_by_tecnico_name")
        return None

def asociar_grupo_a_departamento_por_tecnico(grupo_id, tecnico_nombre, conn=None):
    """Asocia un grupo al departamento basándose en el técnico del registro"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    try:
        # Obtener el departamento del técnico desde la nómina
        departamento = get_departamento_by_tecnico_name(tecnico_nombre, conn)
        
        if not departamento:
            print(f"⚠️ No se encontró departamento para el técnico: {tecnico_nombre}")
            if close_conn:
                conn.close()
            return False
        
        # Buscar el rol_id correspondiente al departamento
        c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (departamento,))
        rol_result = c.fetchone()
        
        if not rol_result:
            print(f"⚠️ No se encontró rol para el departamento: {departamento}")
            if close_conn:
                conn.close()
            return False
        
        rol_id = rol_result[0]
        
        # Verificar si la asociación ya existe
        c.execute("SELECT COUNT(*) FROM grupos_roles WHERE id_grupo = %s AND id_rol = %s", 
                 (grupo_id, rol_id))
        
        if c.fetchone()[0] == 0:  # Si no existe la asociación
            # Crear la asociación
            c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (%s, %s)", 
                     (grupo_id, rol_id))
            
            # Obtener nombres para logging
            c.execute("SELECT nombre FROM grupos WHERE id_grupo = %s", (grupo_id,))
            grupo_nombre = c.fetchone()[0]
            
            print(f"✅ Grupo '{grupo_nombre}' asociado automáticamente al departamento '{departamento}' (basado en técnico: {tecnico_nombre})")
            
            if close_conn:
                conn.commit()
                conn.close()
            return True
        else:
            # La asociación ya existe, no hacer nada
            if close_conn:
                conn.close()
            return False
            
    except Exception as e:
        if close_conn:
            conn.close()
        print(f"⚠️ Error al asociar grupo a departamento por técnico: {e}")
        return False

def get_or_create_grupo_with_tecnico_department_association(nombre_grupo, tecnico_nombre, conn=None):
    """Obtiene o crea un grupo por nombre y lo asocia automáticamente al departamento del técnico
    
    Optimizado para:
    - Evitar duplicados usando normalización de texto
    - Solo procesar asociación si es necesario
    - Retornar rápidamente si el grupo ya existe y está asociado
    """
    from .utils import normalize_text
    
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    try:
        # Buscar grupo existente por nombre normalizado
        c.execute("SELECT id_grupo, nombre FROM grupos")
        grupos = c.fetchall()
        
        nombre_normalizado = normalize_text(nombre_grupo)
        grupo_existente_id = None
        
        # Verificar si ya existe un grupo con nombre normalizado similar
        for grupo_id, grupo_nombre in grupos:
            if normalize_text(grupo_nombre) == nombre_normalizado:
                grupo_existente_id = grupo_id
                break
        
        if grupo_existente_id:
            # El grupo ya existe, verificar si necesita asociación al departamento
            if tecnico_nombre:
                # Obtener departamento del técnico
                departamento = get_departamento_by_tecnico_name(tecnico_nombre, conn)
                if departamento:
                    # Verificar si ya está asociado
                    c.execute("""
                        SELECT COUNT(*) FROM grupos_roles gr
                        JOIN roles r ON gr.id_rol = r.id_rol
                        WHERE gr.id_grupo = %s AND r.nombre = %s
                    """, (grupo_existente_id, departamento))
                    
                    if c.fetchone()[0] == 0:
                        # No está asociado, hacer la asociación
                        asociar_grupo_a_departamento_por_tecnico(grupo_existente_id, tecnico_nombre, conn)
            
            if close_conn:
                conn.close()
            return grupo_existente_id
        
        # Si no existe, crear nuevo grupo
        c.execute("""
            INSERT INTO grupos (nombre, descripcion) 
            VALUES (%s, %s) RETURNING id_grupo
        """, (nombre_grupo, f'Grupo creado automáticamente desde registros: {nombre_grupo}'))
        
        grupo_id = c.fetchone()[0]
        
        # Asociar automáticamente al departamento del técnico
        if tecnico_nombre:
            asociar_grupo_a_departamento_por_tecnico(grupo_id, tecnico_nombre, conn)
        
        conn.commit()
        
        if close_conn:
            conn.close()
        return grupo_id
        
    except Exception as e:
        if close_conn:
            conn.close()
        raise e

def generate_roles_from_nomina():
    """Genera roles desde los cargos únicos en nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Obtener cargos únicos de nómina
        c.execute("SELECT DISTINCT cargo FROM nomina WHERE cargo IS NOT NULL AND cargo != ''")
        cargos = c.fetchall()
        
        # Solo estos roles deben estar ocultos por defecto
        roles_ocultos = ['hipervisor', 'visor']
        
        # Obtener o crear el grupo "General"
        c.execute("SELECT id_grupo FROM grupos WHERE nombre = %s", ('General',))
        general_grupo_result = c.fetchone()
        if not general_grupo_result:
            c.execute("INSERT INTO grupos (nombre, descripcion) VALUES (%s, %s) RETURNING id_grupo",
                     ('General', 'Grupo por defecto para usuarios'))
            general_grupo_id = c.fetchone()[0]
        else:
            general_grupo_id = general_grupo_result[0]
        
        stats = {
            'total_cargos': len(cargos),
            'roles_creados': 0,
            'nuevos_roles': [],
            'errores': []
        }
        
        for cargo_tuple in cargos:
            cargo = cargo_tuple[0]
            try:
                # Verificar si ya existe un rol con el mismo nombre normalizado (igual que en admin_departments.py)
                from .utils import normalize_text
                c.execute("SELECT id_rol, nombre FROM roles")
                roles_existentes = c.fetchall()

                cargo_normalizado = normalize_text(cargo)
                duplicado = False

                for _, rol_nombre in roles_existentes:
                    if normalize_text(rol_nombre) == cargo_normalizado:
                        duplicado = True
                        break

                if not duplicado:
                    # Determinar si el rol debe estar oculto
                    is_hidden = cargo in roles_ocultos
                    
                    # Crear el rol con el campo is_hidden
                    c.execute("INSERT INTO roles (nombre, descripcion, is_hidden) VALUES (%s, %s, %s) RETURNING id_rol",
                             (cargo, f"Rol generado automáticamente para el cargo: {cargo}", is_hidden))
                    new_role_id = c.fetchone()[0]
                    
                    # Asociar automáticamente el grupo "General" al nuevo rol
                    try:
                        c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (%s, %s)", 
                                 (general_grupo_id, new_role_id))
                    except:
                        pass  # Ignorar si ya existe la relación
                    
                    stats['roles_creados'] += 1
                    stats['nuevos_roles'].append(cargo)
                    
            except Exception as e:
                error_msg = f"Error creando rol para cargo {cargo}: {str(e)}"
                stats['errores'].append(error_msg)
                log_sql_error(e, error_msg)
        
        conn.commit()
        return stats
        
    except Exception as e:
        log_sql_error(e, f"Error en generate_roles_from_nomina: {e}")
        return {
            'total_cargos': 0,
            'roles_creados': 0,
            'nuevos_roles': [],
            'errores': [str(e)]
        }
    finally:
        conn.close()

def generate_grupos_from_nomina():
    """Genera grupos desde los equipos únicos en nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Obtener equipos únicos de nómina (usando el campo grupo que mapea tanto Sector como Equipo)
        c.execute("SELECT DISTINCT grupo FROM nomina WHERE grupo IS NOT NULL AND grupo != ''")
        equipos = c.fetchall()
        
        stats = {
            'total_equipos': len(equipos),
            'grupos_creados': 0,
            'nuevos_grupos': [],
            'errores': []
        }
        
        for equipo_tuple in equipos:
            equipo = equipo_tuple[0]
            try:
                # Verificar si el grupo ya existe
                c.execute("SELECT id_grupo FROM grupos WHERE nombre = %s", (equipo,))
                if not c.fetchone():
                    # Crear el grupo
                    c.execute("INSERT INTO grupos (nombre, descripcion) VALUES (%s, %s)",
                             (equipo, f"Grupo generado automáticamente para el equipo: {equipo}"))
                    stats['grupos_creados'] += 1
                    stats['nuevos_grupos'].append(equipo)
                    
            except Exception as e:
                error_msg = f"Error creando grupo para equipo {equipo}: {str(e)}"
                stats['errores'].append(error_msg)
                log_sql_error(e, error_msg)
        
        conn.commit()
        
        if stats['grupos_creados'] > 0:
            print(f"✅ {stats['grupos_creados']} grupos creados automáticamente desde equipos")
        
        return stats
        
    except Exception as e:
        log_sql_error(e, f"Error en generate_grupos_from_nomina: {e}")
        return {
            'total_equipos': 0,
            'grupos_creados': 0,
            'nuevos_grupos': [],
            'errores': [str(e)]
        }
    finally:
        conn.close()
