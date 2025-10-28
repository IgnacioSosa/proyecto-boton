from datetime import date, timedelta
import os
import sys
import pandas as pd
from sqlalchemy import text

# Asegurar que la carpeta raíz del proyecto esté en sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from modules.database import get_engine, ensure_user_default_schedule_exists

def main():
    engine = get_engine()

    print("== Usuarios por rol ==")
    df_roles_users = pd.read_sql_query(
        text("""
            SELECT r.id_rol, r.nombre AS rol, COUNT(u.id) AS usuarios
            FROM roles r
            LEFT JOIN usuarios u ON u.rol_id = r.id_rol
            GROUP BY r.id_rol, r.nombre
            ORDER BY r.nombre
        """),
        con=engine
    )
    print(df_roles_users)

    # Cambia este nombre si tu rol se llama distinto
    ROL_NOMBRE = "Dpto Tecnico"
    rol_row = df_roles_users[df_roles_users["rol"].str.strip().str.lower() == ROL_NOMBRE.strip().lower()]
    if rol_row.empty:
        print(f"\n[!] Rol '{ROL_NOMBRE}' no existe o está oculto.")
        return

    rol_id = int(rol_row["id_rol"].iloc[0])
    print(f"\nRol '{ROL_NOMBRE}' => id_rol={rol_id}")

    print("\n== Usuarios del rol ==")
    df_users = pd.read_sql_query(
        text("""
            SELECT u.id, u.username, u.nombre, u.apellido, u.is_active
            FROM usuarios u
            WHERE u.rol_id = :rid
            ORDER BY u.nombre, u.apellido
        """),
        con=engine, params={"rid": rol_id}
    )
    print(df_users)

    # Semana actual (Lunes-Viernes)
    today = date.today()
    start_week = today - timedelta(days=today.weekday())
    end_week = start_week + timedelta(days=4)

    print("\n== Asignaciones semanales del rol ==")
    df_sched = pd.read_sql_query(
        text("""
            SELECT s.user_id, s.fecha, s.modalidad_id, m.descripcion AS modalidad, s.cliente_id
            FROM user_modalidad_schedule s
            JOIN modalidades_tarea m ON m.id_modalidad = s.modalidad_id
            WHERE s.rol_id = :rid
              AND s.fecha BETWEEN :start AND :end
            ORDER BY s.user_id, s.fecha
        """),
        con=engine, params={"rid": rol_id, "start": start_week, "end": end_week}
    )
    print(df_sched)

    print("\n== Defaults por usuario en el rol ==")
    from modules.database import ensure_user_default_schedule_exists
    ensure_user_default_schedule_exists()
    try:
        df_defaults = pd.read_sql_query(
            text("""
                SELECT
                    u.id AS user_id,
                    u.username,
                    u.nombre,
                    u.apellido,
                    uds.day_of_week,
                    uds.modalidad_id,
                    m.descripcion AS modalidad,
                    uds.cliente_id
                FROM user_default_schedule uds
                JOIN usuarios u ON u.id = uds.user_id
                JOIN modalidades_tarea m ON m.id_modalidad = uds.modalidad_id
                WHERE u.rol_id = :rid
                ORDER BY u.apellido, u.nombre, uds.day_of_week
            """),
            con=engine, params={"rid": rol_id}
        )
        if df_defaults.empty:
            print("No hay defaults configurados para usuarios de este rol.")
        else:
            print(df_defaults.to_string(index=False))
    except Exception as e:
        print(f"Tabla de defaults no disponible o error consultando: {e}")
        df_defaults = pd.DataFrame()

if __name__ == "__main__":
    main()