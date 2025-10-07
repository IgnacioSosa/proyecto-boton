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
        print(f"[ERROR] No se puede conectar al servidor PostgreSQL: {e}")
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
        cursor = conn.cursor()
        
        # Verificar si la base de datos existe
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (POSTGRES_CONFIG['database'],))
        exists = cursor.fetchone()
        
        if not exists:
            # Crear la base de datos si no existe
            conn.autocommit = True
            cursor.execute(f"CREATE DATABASE {POSTGRES_CONFIG['database']}")
            print(f"[OK] Base de datos '{POSTGRES_CONFIG['database']}' creada")
        else:
            print(f"[OK] Base de datos '{POSTGRES_CONFIG['database']}' ya existe")
        
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
    
    parser = argparse.ArgumentParser(description="Herramientas de base de datos")
    parser.add_argument("--auto", action="store_true", help="Regeneración automática de la base de datos")
    parser.add_argument("--unlock", type=str, help="Desbloquear usuario (limpia lockout e intentos)")
    args = parser.parse_args()
    
    if args.unlock:
        from modules.auth import unlock_user
        username = args.unlock
        ok = unlock_user(username)
        if ok:
            print(f"Usuario '{username}' desbloqueado correctamente.")
        else:
            print(f"No se pudo desbloquear al usuario '{username}'. Verifica el nombre.")
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
    
    # Modo interactivo
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