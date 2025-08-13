import sqlite3

def agregar_columna_fecha_nacimiento():
    conn = sqlite3.connect('trabajo.db')  # Cambiar de 'database.db' a 'trabajo.db'
    c = conn.cursor()
    
    try:
        c.execute('ALTER TABLE nomina ADD COLUMN fecha_nacimiento TEXT')
        conn.commit()
        print("Columna fecha_nacimiento agregada exitosamente")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("La columna fecha_nacimiento ya existe")
        else:
            print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    agregar_columna_fecha_nacimiento()