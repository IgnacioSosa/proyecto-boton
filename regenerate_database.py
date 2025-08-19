import sqlite3
import os
from modules.database import init_db

def regenerate_database(backup_old=True):
    """Regenera completamente la base de datos"""
    
    db_path = 'trabajo.db'
    
    # Hacer backup de la base de datos existente si se solicita
    if backup_old and os.path.exists(db_path):
        import shutil
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f'trabajo_backup_{timestamp}.db'
        shutil.copy2(db_path, backup_path)
        print(f"✅ Backup creado: {backup_path}")
    
    # Eliminar base de datos existente
    if os.path.exists(db_path):
        os.remove(db_path)
        print("🗑️ Base de datos anterior eliminada")
    
    # Crear nueva base de datos
    print("🔄 Creando nueva base de datos...")
    init_db()
    
    # Configurar roles y datos iniciales
    setup_initial_data()
    
    print("✅ Base de datos regenerada exitosamente")

def setup_initial_data():
    """Configura datos iniciales en la base de datos"""
    conn = sqlite3.connect('trabajo.db')
    cursor = conn.cursor()
    
    try:
        # Crear roles predeterminados con flag is_hidden
        roles_default = [
            ('admin', 'Administrador con acceso completo', 1),  # Oculto
            ('tecnico', 'Técnico con acceso a registros', 0),    # Visible
            ('sin_rol', 'Usuario sin acceso', 1)                 # Oculto
        ]
        
        for nombre_rol, descripcion, is_hidden in roles_default:
            cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = ?", (nombre_rol,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO roles (nombre, descripcion, is_hidden) VALUES (?, ?, ?)", 
                              (nombre_rol, descripcion, is_hidden))
                print(f"➕ Rol '{nombre_rol}' creado")
            else:
                # Actualizar el flag is_hidden para roles existentes
                cursor.execute("UPDATE roles SET is_hidden = ? WHERE nombre = ?", 
                              (is_hidden, nombre_rol))
        
        # Actualizar usuarios existentes con roles
        cursor.execute('''
            UPDATE usuarios 
            SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'admin') 
            WHERE is_admin = 1 AND rol_id IS NULL
        ''')
        
        cursor.execute('''
            UPDATE usuarios 
            SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico') 
            WHERE is_admin = 0 AND rol_id IS NULL
        ''')
        
        conn.commit()
        print("✅ Datos iniciales configurados")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error configurando datos iniciales: {e}")
        raise
    finally:
        conn.close()

def regenerate_with_data_migration():
    """Regenera la base de datos preservando datos existentes"""
    print("🔄 Iniciando regeneración con migración de datos...")
    
    # Exportar datos existentes
    exported_data = export_existing_data()
    
    # Regenerar base de datos
    regenerate_database(backup_old=True)
    
    # Importar datos preservados
    if exported_data:
        import_preserved_data(exported_data)
    
    print("✅ Regeneración con migración completada")

def export_existing_data():
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
        
        # Exportar nómina
        cursor.execute("SELECT * FROM nomina")
        data['nomina'] = cursor.fetchall()
        
        # Exportar registros
        cursor.execute("SELECT * FROM registros")
        data['registros'] = cursor.fetchall()
        
        # Exportar otras tablas importantes
        for tabla in ['tecnicos', 'clientes', 'tipos_tarea', 'modalidades_tarea']:
            try:
                cursor.execute(f"SELECT * FROM {tabla}")
                data[tabla] = cursor.fetchall()
            except:
                data[tabla] = []
        
        conn.close()
        print("📤 Datos exportados exitosamente")
        return data
        
    except Exception as e:
        print(f"⚠️ Error exportando datos: {e}")
        return None

def import_preserved_data(data):
    """Importa datos preservados a la nueva base de datos"""
    try:
        conn = sqlite3.connect('trabajo.db')
        cursor = conn.cursor()
        
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
        
        conn.commit()
        conn.close()
        print("📥 Datos importados exitosamente")
        
    except Exception as e:
        print(f"❌ Error importando datos: {e}")

def main():
    """Función principal del script"""
    # Verificar si se ejecuta en modo automático
    if len(sys.argv) > 1 and sys.argv[1] == '--auto':
        print("Ejecutando regeneración automática...")
        regenerate_database(backup=True)
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
            confirm = input("⚠️ Esto eliminará TODOS los datos. ¿Continuar? (si/no): ")
            if confirm.lower() in ['si', 'sí', 's', 'yes', 'y']:
                regenerate_database()
            else:
                print("Operación cancelada")
        elif opcion == '2':
            regenerate_with_data_migration()
        else:
            print("Opción no válida")