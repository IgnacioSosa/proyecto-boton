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

# Asegurar codificación UTF-8
os.environ['PGCLIENTENCODING'] = 'UTF8'
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def check_postgresql_connection():
    """Verifica que PostgreSQL esté disponible y la base de datos exista"""
    print("[INFO] Verificando conexión a PostgreSQL...")
    
    # Primero intentar conectar al servidor PostgreSQL (sin especificar base de datos)
    try:
        conn = psycopg2.connect(
            host=POSTGRES_CONFIG['host'],
            port=POSTGRES_CONFIG['port'],
            user=POSTGRES_CONFIG['user'],
            password=POSTGRES_CONFIG['password'],
            database='postgres'  # Base de datos por defecto
        )
        conn.close()
    except Exception as e:
        error_msg = str(e)
        if "codec can't decode" in error_msg:
             print(f"[ERROR] No se puede conectar al servidor PostgreSQL. Probable error de credenciales (Respuesta del servidor con codificación incompatible).")
        else:
            try:
                print(f"[ERROR] No se puede conectar al servidor PostgreSQL: {error_msg}")
            except UnicodeError:
                 print(f"[ERROR] No se puede conectar al servidor PostgreSQL (Error de codificación en mensaje)")
        return False
    
    # Ahora verificar si la base de datos específica existe
    try:
        conn = psycopg2.connect(
            host=POSTGRES_CONFIG['host'],
            port=POSTGRES_CONFIG['port'],
            user=POSTGRES_CONFIG['user'],
            password=POSTGRES_CONFIG['password'],
            database='postgres'
        )
        # Configurar autocommit ANTES de crear el cursor
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Asegurar usuario 'sigo'
        try:
            # Verificar si somos superusuario o tenemos permisos para crear roles
            cursor.execute("SELECT usesuper FROM pg_user WHERE usename = current_user")
            row = cursor.fetchone()
            is_superuser = row[0] if row else False
            
            if is_superuser:
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='sigo'")
                if not cursor.fetchone():
                    print("[INFO] Creando usuario PostgreSQL 'sigo'...")
                    cursor.execute("CREATE USER sigo WITH PASSWORD 'sigo' CREATEDB")
                    print("[OK] Usuario 'sigo' creado")
                else:
                    # Asegurar permisos y contraseña
                    cursor.execute("ALTER USER sigo WITH PASSWORD 'sigo' CREATEDB")
        except Exception as e:
            print(f"[WARN] No se pudo verificar/crear usuario 'sigo': {e}")
        
        # Verificar si la base de datos existe
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (POSTGRES_CONFIG['database'],))
        exists = cursor.fetchone()
        
        if not exists:
            # Crear la base de datos si no existe, asignando a 'sigo' si es posible
            owner_clause = ""
            try:
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='sigo'")
                if cursor.fetchone():
                    owner_clause = " OWNER sigo"
            except:
                pass
                
            cursor.execute(f'CREATE DATABASE "{POSTGRES_CONFIG["database"]}"{owner_clause}')
            print(f"[OK] Base de datos '{POSTGRES_CONFIG['database']}' creada")
        else:
            print(f"[OK] Base de datos '{POSTGRES_CONFIG['database']}' ya existe")
            # Intentar asignar owner si ya existe
            try:
                 cursor.execute(f'ALTER DATABASE "{POSTGRES_CONFIG["database"]}" OWNER TO sigo')
            except Exception:
                 pass
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"[ERROR] Error verificando/creando base de datos: {e}")
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

def regenerate_database(backup_old=False):
    """Regenera completamente la base de datos PostgreSQL"""
    
    # Crear barra de progreso
    progress = tqdm(total=100, desc="Regenerando base de datos PostgreSQL", 
                   bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]", ncols=80)
    
    # Verificar conexión a PostgreSQL
    if not check_postgresql_connection():
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
        if check_postgresql_connection():
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
            print(f"[ERROR] Falló la configuración de datos iniciales: {e}")
        return
    
    if args.auto:
        print("Ejecutando regeneración automática...")
        success = regenerate_database(backup_old=False)
        if success:
            print("\n[OK] Regeneración completada exitosamente")
        else:
            print("\n[ERROR] La regeneración falló")
            sys.exit(1)
        return
    
    # Modo interactivo (si no se pasan argumentos)
    print("\nEste script regenerará completamente la base de datos PostgreSQL.")
    print("ADVERTENCIA: Esto eliminará TODOS los datos existentes.")
    
    confirm = input("\n¿Deseas continuar? (si/no): ")
    if confirm.lower() in ['si', 'sí', 's', 'yes', 'y']:
        success = regenerate_database()
        if success:
            print("\n[OK] Regeneración completada exitosamente")
            print("\nCredenciales por defecto:")
            print("Usuario: admin")
            print("Contraseña: admin")
        else:
            print("\n[ERROR] La regeneración falló")
            sys.exit(1)
    else:
        print("Operación cancelada")

if __name__ == "__main__":
    main()