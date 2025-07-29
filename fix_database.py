import sqlite3
import sys
import os

DB_NAME = 'trabajo.db'

def check_column_type():
    """Verifica el tipo de la columna 'tiempo' en la tabla 'registros'."""
    if not os.path.exists(DB_NAME):
        print(f"El archivo de base de datos '{DB_NAME}' no existe. No se necesita hacer nada.")
        return None

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(registros)")
        columns = cursor.fetchall()
        for col in columns:
            # col[1] is name, col[2] is type
            if col[1].lower() == 'tiempo':
                print(f"Tipo actual de la columna 'tiempo': {col[2]}")
                return col[2].upper()
    except sqlite3.OperationalError:
        print("La tabla 'registros' no existe. No se necesita migración.")
        return None
    finally:
        conn.close()
    return "UNKNOWN"

def migrate_tiempo_column():
    """Migra la columna 'tiempo' de INTEGER a REAL sin perder datos."""
    print("\nIniciando la reparación de la base de datos...")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    try:
        # 1. Renombrar la tabla original
        print("Paso 1: Renombrando tabla 'registros' a 'registros_old'...")
        cursor.execute("ALTER TABLE registros RENAME TO registros_old")

        # 2. Crear la nueva tabla con la estructura correcta (tiempo REAL)
        print("Paso 2: Creando nueva tabla 'registros' con el tipo de dato correcto...")
        cursor.execute('''
        CREATE TABLE registros (
            id INTEGER PRIMARY KEY,
            fecha TEXT NOT NULL,
            id_tecnico INTEGER NOT NULL,
            id_cliente INTEGER NOT NULL,
            id_tipo INTEGER NOT NULL,
            id_modalidad INTEGER NOT NULL,
            tarea_realizada TEXT NOT NULL,
            numero_ticket TEXT NOT NULL,
            tiempo REAL NOT NULL,
            descripcion TEXT,
            mes TEXT NOT NULL,
            usuario_id INTEGER,
            FOREIGN KEY (id_tecnico) REFERENCES tecnicos (id_tecnico),
            FOREIGN KEY (id_cliente) REFERENCES clientes (id_cliente),
            FOREIGN KEY (id_tipo) REFERENCES tipos_tarea (id_tipo),
            FOREIGN KEY (id_modalidad) REFERENCES modalidades_tarea (id_modalidad),
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
        ''')

        # 3. Copiar los datos de la tabla antigua a la nueva
        print("Paso 3: Copiando tus datos a la nueva tabla...")
        cursor.execute('INSERT INTO registros SELECT * FROM registros_old')
        print(f"{cursor.rowcount} registros copiados de forma segura.")

        # 4. Eliminar la tabla antigua
        print("Paso 4: Finalizando la limpieza...")
        cursor.execute("DROP TABLE registros_old")

        conn.commit()
        print("\n¡Reparación completada! La base de datos ha sido corregida.")

    except sqlite3.Error as e:
        print(f"\nOcurrió un error durante la reparación: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    if check_column_type() == 'INTEGER':
        migrate_tiempo_column()
    else:
        print("La base de datos ya está correcta o no necesita reparación.")