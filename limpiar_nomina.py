import sqlite3

def limpiar_nomina():
    """Elimina todos los registros de la tabla nomina"""
    try:
        conn = sqlite3.connect('trabajo.db')
        c = conn.cursor()
        
        # Contar registros antes de eliminar
        c.execute("SELECT COUNT(*) FROM nomina")
        count_before = c.fetchone()[0]
        print(f"Registros antes de limpiar: {count_before}")
        
        # Eliminar todos los registros
        c.execute("DELETE FROM nomina")
        
        # Intentar reiniciar el contador de ID solo si la tabla sqlite_sequence existe
        try:
            c.execute("DELETE FROM sqlite_sequence WHERE name='nomina'")
            print("Contador de ID reiniciado")
        except sqlite3.OperationalError:
            # La tabla sqlite_sequence no existe, esto es normal
            print("No hay contador de ID que reiniciar (normal)")
        
        conn.commit()
        
        # Verificar que se eliminaron
        c.execute("SELECT COUNT(*) FROM nomina")
        count_after = c.fetchone()[0]
        print(f"Registros después de limpiar: {count_after}")
        
        conn.close()
        print("✅ Tabla nomina limpiada exitosamente")
        
    except Exception as e:
        print(f"❌ Error al limpiar la tabla: {str(e)}")

if __name__ == "__main__":
    respuesta = input("¿Estás seguro de que quieres eliminar TODOS los empleados de la nómina? (si/no): ")
    if respuesta.lower() in ['si', 'sí', 's', 'yes', 'y']:
        limpiar_nomina()
    else:
        print("Operación cancelada")