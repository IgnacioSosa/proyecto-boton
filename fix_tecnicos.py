import sqlite3

def fix_tecnicos():
    print("Iniciando verificación de técnicos...")
    conn = sqlite3.connect('trabajo.db')
    c = conn.cursor()
    
    # Capitalizar nombres y apellidos existentes
    print("Capitalizando nombres y apellidos existentes...")
    c.execute("SELECT id, nombre, apellido FROM usuarios WHERE nombre IS NOT NULL OR apellido IS NOT NULL")
    usuarios = c.fetchall()
    
    for user_id, nombre, apellido in usuarios:
        # Manejo seguro de valores potencialmente nulos
        nombre_cap = nombre.strip().capitalize() if nombre else None
        apellido_cap = apellido.strip().capitalize() if apellido else None
        
        if nombre_cap != nombre or apellido_cap != apellido:
            print(f"Actualizando usuario ID {user_id}: {nombre} {apellido} -> {nombre_cap} {apellido_cap}")
            c.execute("UPDATE usuarios SET nombre = ?, apellido = ? WHERE id = ?", 
                     (nombre_cap, apellido_cap, user_id))
    
    # Obtener todos los usuarios con nombre y apellido (ya capitalizados)
    c.execute("SELECT id, nombre, apellido FROM usuarios WHERE nombre IS NOT NULL AND apellido IS NOT NULL")
    usuarios = c.fetchall()
    
    # Verificar si cada usuario tiene un técnico correspondiente
    for user_id, nombre, apellido in usuarios:
        nombre_completo = f"{nombre} {apellido}".strip()
        if nombre_completo:
            # Verificar si existe el técnico
            c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (nombre_completo,))
            tecnico = c.fetchone()
            if not tecnico:
                # Crear el técnico si no existe
                print(f"Creando técnico para: {nombre_completo}")
                c.execute("INSERT INTO tecnicos (nombre) VALUES (?)", (nombre_completo,))
    
    # Actualizar nombres de técnicos existentes para que coincidan con el formato capitalizado
    c.execute("SELECT id_tecnico, nombre FROM tecnicos")
    tecnicos = c.fetchall()
    
    for id_tecnico, nombre_tecnico in tecnicos:
        # Verificar que nombre_tecnico no sea None antes de procesarlo
        if nombre_tecnico:
            try:
                partes = nombre_tecnico.split()
                nombre_capitalizado = ' '.join(parte.capitalize() for parte in partes if parte)
                
                if nombre_capitalizado and nombre_capitalizado != nombre_tecnico:
                    print(f"Actualizando técnico ID {id_tecnico}: {nombre_tecnico} -> {nombre_capitalizado}")
                    c.execute("UPDATE tecnicos SET nombre = ? WHERE id_tecnico = ?", 
                            (nombre_capitalizado, id_tecnico))
            except Exception as e:
                print(f"Error al procesar técnico ID {id_tecnico}: {e}")
    
    # Listar todos los técnicos para verificación
    c.execute("SELECT id_tecnico, nombre FROM tecnicos ORDER BY nombre")
    tecnicos = c.fetchall()
    print("\nLista de técnicos en el sistema:")
    for id_tecnico, nombre in tecnicos:
        print(f"ID: {id_tecnico}, Nombre: {nombre}")
    
    conn.commit()
    conn.close()
    print("\nVerificación completada.")

if __name__ == "__main__":
    fix_tecnicos()