import sqlite3
import os
import sys

# Verificar dependencias antes de importar módulos
try:
    # Intentar importar módulos necesarios
    import pandas as pd
    from modules.database import init_db
    import tqdm
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
            from modules.database import init_db
            import tqdm
        else:
            print("[ERROR] No se encontró el archivo requirements.txt")
            print("Por favor, instala manualmente pandas y tqdm: pip install pandas tqdm")
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Error al instalar dependencias: {e}")
        print("Por favor, instala manualmente las dependencias con: pip install -r requirements.txt")
        sys.exit(1)

# Importar tqdm para la barra de progreso
from tqdm import tqdm
import time

def regenerate_database(backup_old=True):
    """Regenera completamente la base de datos"""
    
    db_path = 'trabajo.db'
    
    # Crear barra de progreso
    progress = tqdm(total=100, desc="Regenerando base de datos", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]", ncols=80)
    
    # Hacer backup de la base de datos existente si se solicita
    if backup_old and os.path.exists(db_path):
        import shutil
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f'trabajo_backup_{timestamp}.db'
        shutil.copy2(db_path, backup_path)
        print(f"[OK] Backup creado: {backup_path}")
        progress.update(10)
    else:
        progress.update(10)
    
    # Eliminar base de datos existente
    if os.path.exists(db_path):
        os.remove(db_path)
        print("[INFO] Base de datos anterior eliminada")
    progress.update(10)
    
    # Crear nueva base de datos
    print("[INFO] Creando nueva base de datos...")
    init_db()
    progress.update(40)
    
    # Configurar roles y datos iniciales
    print("[INFO] Configurando datos iniciales...")
    setup_initial_data()
    progress.update(30)
    
    # Finalizar
    progress.update(10)
    progress.close()
    print("[OK] Base de datos regenerada exitosamente")

def setup_initial_data():
    """Configura datos iniciales en la base de datos"""
    conn = sqlite3.connect('trabajo.db')
    cursor = conn.cursor()
    
    try:
        # Crear roles predeterminados con flag is_hidden
        roles_default = [
            ('admin', 'Administrador con acceso completo', 1),  # Oculto
            ('sin_rol', 'Usuario sin acceso', 1),                # Oculto
            ('hipervisor', 'Supervisor con acceso a visualización', 0)  # Visible
        ]
        
        for nombre_rol, descripcion, is_hidden in roles_default:
            cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = ?", (nombre_rol,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO roles (nombre, descripcion, is_hidden) VALUES (?, ?, ?)", 
                              (nombre_rol, descripcion, is_hidden))
                print(f"[+] Rol '{nombre_rol}' creado")
            else:
                # Actualizar el flag is_hidden para roles existentes
                cursor.execute("UPDATE roles SET is_hidden = ? WHERE nombre = ?", 
                              (is_hidden, nombre_rol))
        
        # Actualizar usuarios existentes con roles
        cursor.execute('''
            UPDATE usuarios 
            SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'usuario') 
            WHERE is_admin = 1 AND rol_id IS NULL
        ''')
        
        cursor.execute('''
            UPDATE usuarios 
            SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico') 
            WHERE is_admin = 0 AND rol_id IS NULL
        ''')
        
        conn.commit()
        print("[OK] Datos iniciales configurados")
        
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Error configurando datos iniciales: {e}")
        raise
    finally:
        conn.close()

def regenerate_with_data_migration():
    """Regenera la base de datos preservando datos existentes"""
    print("[INFO] Iniciando regeneración con migración de datos...")
    
    # Crear barra de progreso
    progress = tqdm(total=100, desc="Migrando datos", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]", ncols=80)
    
    # Exportar datos existentes
    print("[INFO] Exportando datos existentes...")
    exported_data = export_existing_data(progress)
    progress.update(30)
    
    # Regenerar base de datos
    print("[INFO] Regenerando base de datos...")
    regenerate_database(backup_old=True)
    progress.update(30)
    
    # Importar datos preservados
    if exported_data:
        print("[INFO] Importando datos preservados...")
        import_preserved_data(exported_data, progress)
    progress.update(10)
    
    # Finalizar
    progress.close()
    print("[OK] Regeneración con migración completada")

def export_existing_data(progress=None):
    """Exporta datos existentes antes de regenerar"""
    if not os.path.exists('trabajo.db'):
        return None
    
    try:
        conn = sqlite3.connect('trabajo.db')
        cursor = conn.cursor()
        
        data = {}
        
        # Exportar usuarios
        cursor.execute("SELECT * FROM usuarios")
        data['usuarios'] = cursor.fetchall()
        if progress:
            progress.update(5)
        
        # Exportar nómina
        cursor.execute("SELECT * FROM nomina")
        data['nomina'] = cursor.fetchall()
        if progress:
            progress.update(5)
        
        # Exportar registros
        cursor.execute("SELECT * FROM registros")
        data['registros'] = cursor.fetchall()
        if progress:
            progress.update(5)
        
        # Exportar roles
        try:
            cursor.execute("SELECT * FROM roles")
            data['roles'] = cursor.fetchall()
        except:
            data['roles'] = []
        if progress:
            progress.update(5)
        
        # Exportar otras tablas importantes
        for tabla in ['tecnicos', 'clientes', 'tipos_tarea', 'modalidades_tarea']:
            try:
                cursor.execute(f"SELECT * FROM {tabla}")
                data[tabla] = cursor.fetchall()
            except:
                data[tabla] = []
        
        conn.close()
        print("[INFO] Datos exportados exitosamente")
        return data
        
    except Exception as e:
        print(f"[WARN] Error exportando datos: {e}")
        return None

def import_preserved_data(data, progress=None):
    """Importa datos preservados a la nueva base de datos"""
    try:
        conn = sqlite3.connect('trabajo.db')
        cursor = conn.cursor()
        
        # Importar roles personalizados (excepto los predeterminados)
        for rol in data.get('roles', []):
            # Verificar que no sea uno de los roles predeterminados
            if rol[1] not in ['admin', 'tecnico', 'sin_rol', 'hipervisor']:
                try:
                    cursor.execute('''
                        INSERT INTO roles 
                        (nombre, descripcion, is_hidden)
                        VALUES (?, ?, ?)
                    ''', (rol[1], rol[2], rol[3] if len(rol) > 3 else 0))
                except Exception as e:
                    print(f"Error al importar rol {rol[1]}: {e}")
        if progress:
            progress.update(5)
        
        # Importar usuarios (excepto admin por defecto)
        for usuario in data.get('usuarios', []):
            if usuario[1] != 'admin':  # No duplicar admin
                try:
                    cursor.execute('''
                        INSERT INTO usuarios 
                        (username, password, nombre, apellido, email, is_admin, is_active, rol_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', usuario[1:])
                except:
                    pass  # Ignorar duplicados
        if progress:
            progress.update(5)
        
        # Importar otras tablas
        table_columns = {
            'nomina': '(nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento, activo)',
            'tecnicos': '(nombre, usuario_id)',
            'clientes': '(nombre,)',
            'tipos_tarea': '(descripcion,)',
            'modalidades_tarea': '(modalidad,)'
        }
        
        for tabla, columnas in table_columns.items():
            for row in data.get(tabla, []):
                try:
                    placeholders = ','.join(['?' for _ in row[1:]])  # Excluir ID
                    cursor.execute(f'INSERT INTO {tabla} {columnas} VALUES ({placeholders})', row[1:])
                except:
                    pass  # Ignorar duplicados
            if progress:
                progress.update(2)
        
        conn.commit()
        conn.close()
        print("[INFO] Datos importados exitosamente")
        
    except Exception as e:
        print(f"[ERROR] Error importando datos: {e}")

def main():
    """Función principal del script"""
    # Verificar si se ejecuta en modo automático
    if len(sys.argv) > 1 and sys.argv[1] == '--auto':
        print("Ejecutando regeneración automática...")
        regenerate_database(backup_old=True)
        return
    
    # Modo interactivo original
    print("=== REGENERADOR DE BASE DE DATOS ===")
    if len(sys.argv) > 1 and sys.argv[1] == '--with-migration':
        regenerate_with_data_migration()
    else:
        print("Opciones disponibles:")
        print("1. Regeneración completa (elimina todos los datos)")
        print("2. Regeneración con migración (preserva datos)")
        
        opcion = input("Selecciona una opción (1/2): ")
        
        if opcion == '1':
            confirm = input("[WARN] Esto eliminará TODOS los datos. ¿Continuar? (si/no): ")
            if confirm.lower() in ['si', 'sí', 's', 'yes', 'y']:
                regenerate_database()
            else:
                print("Operación cancelada")
        elif opcion == '2':
            regenerate_with_data_migration()
        else:
            print("Opción no válida")

if __name__ == "__main__":
    main()