import sqlite3

DB_PATH = "trabajo.db"

def ensure_columns():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Obtener lista de columnas actuales en 'usuarios'
    c.execute("PRAGMA table_info(usuarios);")
    existing_columns = [row[1] for row in c.fetchall()]

    # Columnas necesarias para 2FA
    required_columns = {
        "is_2fa_enabled": "INTEGER DEFAULT 0",
        "totp_secret": "TEXT"
    }

    # Agregar las columnas que falten
    for col, col_type in required_columns.items():
        if col not in existing_columns:
            print(f"➕ Agregando columna {col}...")
            c.execute(f"ALTER TABLE usuarios ADD COLUMN {col} {col_type};")
        else:
            print(f"✔ Columna {col} ya existe")

    conn.commit()
    conn.close()
    print("✅ Migración completada")

if __name__ == "__main__":
    ensure_columns()
