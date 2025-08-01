import sqlite3

def add_email_column():
    print("Iniciando actualización de la base de datos...")
    conn = sqlite3.connect('trabajo.db')
    c = conn.cursor()
    
    # Verificar si la columna email ya existe
    c.execute("PRAGMA table_info(usuarios)")
    columns = c.fetchall()
    column_names = [column[1] for column in columns]
    
    if 'email' not in column_names:
        print("Agregando columna 'email' a la tabla 'usuarios'...")
        c.execute("ALTER TABLE usuarios ADD COLUMN email TEXT")
        conn.commit()
        print("Columna 'email' agregada exitosamente.")
    else:
        print("La columna 'email' ya existe en la tabla 'usuarios'.")
    
    conn.close()
    print("Actualización completada.")

if __name__ == "__main__":
    add_email_column()