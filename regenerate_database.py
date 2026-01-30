import os
import sys
import argparse

# Verificar dependencias antes de importar módulos
try:
    # Intentar importar módulos necesarios
    import pandas as pd
    import psycopg2
    from modules.database import init_db, test_connection  
    import tqdm
    import bcrypt  
except ImportError as e:
    print(f"Error: Falta el módulo: {str(e)}")
    print("Instalando dependencias desde requirements.txt...")
    try:
        import subprocess
        # Verificar que requirements.txt existe
        if os.path.exists('requirements.txt'):
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            print("[OK] Dependencias instaladas correctamente")
            # Ahora que las dependencias están instaladas, importamos de nuevo
            import pandas as pd
            import psycopg2
            from modules.database import init_db, test_connection
            import tqdm
            import bcrypt
        else:
            print("[ERROR] No se encontró el archivo requirements.txt")
            print("Por favor, instala manualmente pandas, psycopg2-binary y tqdm")
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Error al instalar dependencias: {e}")
        print("Por favor, instala manualmente las dependencias con: pip install -r requirements.txt")
        sys.exit(1)

# Importar tqdm para la barra de progreso
from tqdm import tqdm
import time
from modules.config import POSTGRES_CONFIG

# Configuración de logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Eliminar configuración forzada de encoding para evitar errores en Windows con español
# os.environ['PGCLIENTENCODING'] = 'UTF8'

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def ensure_env_file():
    """Crea el archivo .env con valores por defecto si no existe."""
    if os.path.exists('.env'):
        return

    print("[INFO] Archivo .env no encontrado. Creando con valores por defecto...")
    
    default_content = """# Configuración de Base de Datos
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=sigo_db
POSTGRES_USER=sigo
POSTGRES_PASSWORD=sigo
"""
    try:
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(default_content)
        print("[OK] Archivo .env creado exitosamente.")
        
        # Recargar configuración para asegurar que se usen estos valores
        from modules.config import reload_env
        reload_env()
        
    except Exception as e:
        print(f"[WARN] No se pudo crear el archivo .env: {e}")

def _try_connect(host, port, user, password, database):
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )
        return conn
    except Exception:
        return None


def check_postgresql_connection(auto_mode=False):
    """Verifica conexión a PostgreSQL y configura la base de datos y usuario de aplicación.

    Flujo:
    1) Conectar como administrador (postgres)
    2) Crear/Verificar base de datos 'sigo_db'
    3) Crear/Verificar usuario 'sigo' y pedir contraseña
    4) Actualizar .env
    5) Verificar conexión con nuevas credenciales
    """
    print("[INFO] Iniciando configuración de base de datos...")

    # 1) Conectar como Administrador (postgres)
    host = POSTGRES_CONFIG.get("host", "localhost")
    port = POSTGRES_CONFIG.get("port", "5432")
    
    admin_conn = None
    connected_user = None
    
    # Intento 1: Credenciales del .env (si existen)
    env_user = POSTGRES_CONFIG.get("user")
    env_pass = POSTGRES_CONFIG.get("password")
    
    if env_user and env_pass:
        print(f"[INFO] Intentando conectar con credenciales del .env ({env_user})...")
        # Intentamos conectar a 'postgres' (db de mantenimiento) con las credenciales del .env
        admin_conn = _try_connect(host, port, env_user, env_pass, "postgres")
        if admin_conn:
            connected_user = env_user
            print(f"[OK] Conectado con credenciales del .env ({env_user})")

    # Intento 2: Default postgres/postgres
    if not admin_conn:
        print("[INFO] Intentando conectar con credenciales por defecto (postgres/postgres)...")
        admin_conn = _try_connect(host, port, "postgres", "postgres", "postgres")
        if admin_conn:
            connected_user = "postgres"
            print(f"[OK] Conectado con credenciales por defecto (postgres)")
            
    # Intento 3: Pedir usuario y contraseña
    if not admin_conn:
        # Verificar si estamos en un entorno interactivo antes de pedir input
        is_interactive = sys.stdin and sys.stdin.isatty()
        
        if not is_interactive:
             print("[ERROR] No se pudo conectar automáticamente y no hay terminal interactiva.")
             print("Por favor, verifique el usuario y contraseña de la base de datos en la configuración.")
             return False

        print("[WARN] No se pudo conectar automáticamente. Ingrese credenciales manuales.")
        try:
            admin_user_input = input("Usuario PostgreSQL (default: postgres): ").strip() or "postgres"
            admin_pass_input = input("Contraseña PostgreSQL: ").strip()
            
            admin_conn = _try_connect(host, port, admin_user_input, admin_pass_input, "postgres")
            if not admin_conn:
                print("[ERROR] No se pudo conectar a PostgreSQL. Verifique credenciales.")
                return False
            connected_user = admin_user_input
        except Exception as e:
            print(f"[ERROR] Error al leer credenciales: {e}")
            return False
    
    print(f"[OK] Conexión administrativa establecida como {connected_user}")

    # 2) Configurar Base de Datos y Usuario
    target_db = "sigo_db"
    target_user = "sigo"
    
    try:
        admin_conn.autocommit = True
        cursor = admin_conn.cursor()

        # a) Crear Base de Datos
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
        if not cursor.fetchone():
            print(f"[INFO] Creando base de datos '{target_db}'...")
            cursor.execute(f'CREATE DATABASE "{target_db}"')
            print(f"[OK] Base de datos '{target_db}' creada.")
        else:
            print(f"[INFO] La base de datos '{target_db}' ya existe.")

        # b) Crear/Configurar Usuario
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (target_user,))
        user_exists = cursor.fetchone()
        
        target_pass = "sigo" # Default fallback
        
        if not user_exists:
            print(f"[INFO] El usuario '{target_user}' no existe. Creando...")
            if auto_mode:
                pass_input = ""
                print(f"[INFO] Modo automático: Usando contraseña por defecto para '{target_user}'")
            else:
                pass_input = input(f"Ingrese la contraseña para el nuevo usuario '{target_user}' (Enter para default: 'sigo'): ").strip()
            target_pass = pass_input if pass_input else "sigo"
            
            try:
                cursor.execute(f'CREATE USER "{target_user}" WITH PASSWORD %s CREATEDB', (target_pass,))
                print(f"[OK] Usuario '{target_user}' creado.")
            except Exception as e:
                print(f"[ERROR] No se pudo crear el usuario: {e}")
                return False
        else:
            print(f"[INFO] El usuario '{target_user}' ya existe.")
            if auto_mode:
                change_pass = 'n'
            else:
                change_pass = input(f"¿Desea cambiar la contraseña del usuario '{target_user}'? (s/n): ").lower().strip()
            
            if change_pass == 's':
                target_pass = input(f"Ingrese nueva contraseña para '{target_user}': ").strip()
                while not target_pass:
                    target_pass = input(f"Ingrese nueva contraseña para '{target_user}': ").strip()
                
                try:
                    cursor.execute(f'ALTER USER "{target_user}" WITH PASSWORD %s', (target_pass,))
                    print(f"[OK] Contraseña de '{target_user}' actualizada.")
                except Exception as e:
                    print(f"[ERROR] No se pudo actualizar la contraseña: {e}")
                    return False
            else:
                # Si no cambiamos la contraseña, debemos validar que la que tenemos funciona
                candidate_pass = POSTGRES_CONFIG.get("password")
                
                # Lista de contraseñas candidatas para probar automáticamente
                candidates = []
                if candidate_pass: candidates.append(candidate_pass)
                if "sigo" not in candidates: candidates.append("sigo")
                
                found_valid = False
                for cand in candidates:
                    if _try_connect(host, port, target_user, cand, target_db):
                        target_pass = cand
                        found_valid = True
                        print(f"[OK] Credenciales validadas correctamente.")
                        break
                
                if not found_valid:
                     print(f"[WARN] No se pudo conectar con las contraseñas probadas (incluyendo 'sigo').")
                     
                     if auto_mode:
                         print("[INFO] Modo automático: Reseteando contraseña a 'sigo'...")
                         opt = '1'
                     else:
                         print(f"Opciones:")
                         print(f"1. Resetear contraseña a 'sigo' (Recomendado)")
                         print(f"2. Ingresar contraseña manual")
                         opt = input("Seleccione una opción (1/2): ").strip()
                     
                     if opt == '1' or opt == '':
                         try:
                             print(f"[INFO] Reseteando contraseña de '{target_user}' a 'sigo'...")
                             cursor.execute(f'ALTER USER "{target_user}" WITH PASSWORD %s', ('sigo',))
                             target_pass = 'sigo'
                             print(f"[OK] Contraseña reseteada exitosamente.")
                         except Exception as e:
                             print(f"[ERROR] No se pudo resetear la contraseña: {e}")
                             return False
                     else:
                         # Pedir la contraseña correcta hasta que funcione
                         while True:
                             if auto_mode:
                                 print("[ERROR] Modo automático: No se pudo verificar la contraseña.")
                                 return False
                                 
                             target_pass = input(f"Ingrese la contraseña actual VÁLIDA para '{target_user}': ").strip()
                             if not target_pass:
                                 continue
                                 
                             if _try_connect(host, port, target_user, target_pass, target_db):
                                 print(f"[OK] Contraseña verificada.")
                                 break
                             else:
                                 print("[ERROR] No se pudo conectar con esa contraseña.")
                                 if auto_mode:
                                     return False
                                 retry = input("¿Intentar de nuevo? (s/n): ").lower().strip()
                                 if retry != 's':
                                     return False

        # c) Asignar dueño a la base de datos
        try:
            cursor.execute(f'ALTER DATABASE "{target_db}" OWNER TO "{target_user}"')
        except Exception as e:
             print(f"[WARN] No se pudo asignar dueño de la BD: {e}")

        # d) Grant all privileges on schema public to target_user (in target_db)
        # Nota: Esto requiere reconectar a la target_db o hacerlo después.
        # Por ahora, ser dueño de la BD es suficiente para crear tablas.

        cursor.close()
        admin_conn.close()

        # 3) Actualizar .env
        print("[INFO] Actualizando archivo .env...")
        env_content = f"""# Configuración de Base de Datos
POSTGRES_HOST={host}
POSTGRES_PORT={port}
POSTGRES_DB={target_db}
POSTGRES_USER={target_user}
POSTGRES_PASSWORD={target_pass}
"""
        try:
            with open('.env', 'w', encoding='utf-8') as f:
                f.write(env_content)
            print("[OK] Archivo .env actualizado.")
            
            # Recargar configuración
            from modules.config import reload_env
            reload_env()
            
        except Exception as e:
            print(f"[ERROR] No se pudo escribir el archivo .env: {e}")
            return False

        # 4) Verificar conexión con nuevas credenciales
        print(f"[INFO] Verificando conexión con usuario '{target_user}'...")
        app_conn = _try_connect(host, port, target_user, target_pass, target_db)
        if app_conn:
            print(f"[OK] Conexión exitosa con usuario '{target_user}' a base de datos '{target_db}'.")
            app_conn.close()
            return True
        else:
            print(f"[ERROR] Falló la conexión con las nuevas credenciales.")
            return False

    except Exception as e:
        print(f"[ERROR] Error durante la configuración: {e}")
        return False


def drop_all_tables():
    """Elimina todas las tablas de la base de datos"""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_CONFIG['host'],
            port=POSTGRES_CONFIG['port'],
            database=POSTGRES_CONFIG['database'],
            user=POSTGRES_CONFIG['user'],
            password=POSTGRES_CONFIG['password']
        )
        cursor = conn.cursor()
        
        # Obtener todas las tablas
        cursor.execute("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
        """)
        tables = cursor.fetchall()
        
        # Eliminar cada tabla
        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table[0]} CASCADE")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("[INFO] Todas las tablas eliminadas")
        
    except Exception as e:
        print(f"[ERROR] Error eliminando tablas: {e}")
        raise

def fix_admin_hash():
    """Corrige el hash del usuario admin después de init_db()"""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_CONFIG['host'],
            port=POSTGRES_CONFIG['port'],
            database=POSTGRES_CONFIG['database'],
            user=POSTGRES_CONFIG['user'],
            password=POSTGRES_CONFIG['password']
        )
        conn.autocommit = True
        c = conn.cursor()
        
        print("[INFO] Corrigiendo hash del usuario admin...")
        
        # Generar un nuevo hash correcto
        password_hash = bcrypt.hashpw('admin'.encode('utf-8'), bcrypt.gensalt())
        
        # Actualizar el usuario admin con el hash correcto
        c.execute("""
            UPDATE usuarios 
            SET password_hash = %s 
            WHERE username = %s
        """, (password_hash.decode('utf-8'), 'admin'))
        
        # Verificar que se actualizó
        if c.rowcount > 0:
            print("[OK] Hash del usuario admin corregido")
        else:
            print("[WARN] No se encontró usuario admin para corregir")
        
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Error corrigiendo hash del admin: {e}")
        raise

def regenerate_database(backup_old=False, auto_mode=False):
    """Regenera completamente la base de datos PostgreSQL"""
    
    # Crear barra de progreso
    progress = tqdm(total=100, desc="Regenerando base de datos PostgreSQL", 
                   bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]", ncols=80)
    
    # Verificar conexión a PostgreSQL
    if not check_postgresql_connection(auto_mode=auto_mode):
        progress.close()
        return False
    progress.update(20)
    
    # Eliminar todas las tablas existentes
    print("[INFO] Eliminando tablas existentes...")
    try:
        drop_all_tables()
    except Exception as e:
        print(f"[ERROR] Error eliminando tablas: {e}")
        progress.close()
        return False
    progress.update(20)
    
    # Crear nueva estructura de base de datos
    print("[INFO] Creando nueva estructura de base de datos...")
    try:
        init_db()
        print("[OK] Estructura de base de datos creada")
    except Exception as e:
        print(f"[ERROR] Error creando estructura: {e}")
        progress.close()
        return False
    progress.update(30)
    
    # Corregir hash del usuario admin
    try:
        fix_admin_hash()
    except Exception as e:
        print(f"[ERROR] Error corrigiendo hash del admin: {e}")
        progress.close()
        return False
    progress.update(10)
    
    # Configurar datos iniciales
    print("[INFO] Configurando datos iniciales...")
    try:
        setup_initial_data()
    except Exception as e:
        print(f"[ERROR] Error configurando datos iniciales: {e}")
        progress.close()
        return False
    progress.update(15)
    
    # Verificar que todo funcione
    if test_connection():
        print("[OK] Verificación de conexión exitosa")
    else:
        print("[WARN] Problemas con la verificación de conexión")
    
    # Finalizar
    progress.update(5)
    progress.close()
    print("[OK] Base de datos PostgreSQL regenerada exitosamente")
    return True

def setup_initial_data():
    """Configura datos iniciales en la base de datos PostgreSQL"""
    conn = psycopg2.connect(
        host=POSTGRES_CONFIG['host'],
        port=POSTGRES_CONFIG['port'],
        database=POSTGRES_CONFIG['database'],
        user=POSTGRES_CONFIG['user'],
        password=POSTGRES_CONFIG['password']
    )
    cursor = conn.cursor()
    
    try:
        # Los roles del sistema ya se insertan en init_db()
        # Aquí podemos agregar datos adicionales si es necesario
        
        # Ejemplo: Crear algunos datos de prueba
        # Técnicos de ejemplo
        tecnicos_ejemplo = [
            ('Juan', 'Pérez', 'juan.perez@empresa.com', '123-456-7890'),
            ('María', 'González', 'maria.gonzalez@empresa.com', '123-456-7891'),
        ]
        
        for nombre, apellido, email, telefono in tecnicos_ejemplo:
            cursor.execute("""
                INSERT INTO tecnicos (nombre, apellido, email, telefono) 
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (nombre, apellido, email, telefono))
        
     
        conn.commit()
        print("[OK] Datos iniciales configurados")
        
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Error configurando datos iniciales: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def main():
    """Función principal del script"""
    print("=== REGENERADOR DE BASE DE DATOS POSTGRESQL ===")
    
    parser = argparse.ArgumentParser(description="Herramientas de mantenimiento y regeneración de la base de datos.")
    
    # Grupo de opciones principales
    parser.add_argument("--auto", action="store_true", help="Regeneración automática completa (Elimina y recrea todo)")
    parser.add_argument("--unlock", type=str, metavar="USERNAME", help="Desbloquear usuario (limpia lockout e intentos)")
    
    # Grupo de herramientas específicas
    utils_group = parser.add_argument_group('Herramientas de utilidad')
    utils_group.add_argument("--check-connection", action="store_true", help="Verificar conexión a PostgreSQL")
    utils_group.add_argument("--fix-hash", action="store_true", help="Corregir hash del usuario admin")
    utils_group.add_argument("--setup-data", action="store_true", help="Insertar datos iniciales (sin borrar tablas)")
    
    args = parser.parse_args()
    
    # Manejo de comandos específicos
    if args.unlock:
        from modules.auth import unlock_user
        username = args.unlock
        ok = unlock_user(username)
        if ok:
            print(f"Usuario '{username}' desbloqueado correctamente.")
        else:
            print(f"No se pudo desbloquear al usuario '{username}'. Verifica el nombre.")
        return

    if args.check_connection:
        if check_postgresql_connection(auto_mode=args.auto):
            print("[OK] Conexión a PostgreSQL verificada correctamente.")
        else:
            print("[ERROR] No se pudo conectar a PostgreSQL.")
        return

    if args.fix_hash:
        try:
            fix_admin_hash()
        except Exception as e:
            print(f"[ERROR] Falló la corrección del hash: {e}")
        return

    if args.setup_data:
        print("[INFO] Insertando datos iniciales...")
        try:
            setup_initial_data()
        except Exception as e:
            print(f"[ERROR] Error insertando datos: {e}")
        return

    # Si no hay argumentos específicos, ejecutar regeneración completa
    if args.auto:
        print("[INFO] Modo automático iniciado.")
        if regenerate_database(auto_mode=True):
            print("[SUCCESS] Base de datos regenerada correctamente.")
        else:
            print("[ERROR] Falló la regeneración de la base de datos.")
            sys.exit(1)
    else:
        # Modo interactivo por defecto
        confirm = input("¿Estás seguro de que quieres BORRAR y REGENERAR la base de datos? (s/n): ").lower().strip()
        if confirm == 's':
            if regenerate_database(auto_mode=False):
                print("[SUCCESS] Base de datos regenerada correctamente.")
            else:
                print("[ERROR] Falló la regeneración de la base de datos.")
                sys.exit(1)
        else:
            print("Operación cancelada.")

if __name__ == "__main__":
    main()
