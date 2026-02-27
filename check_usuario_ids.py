
import sys
import os

# Add the project root to sys.path to allow imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from modules.database import get_engine

def check_usuario_ids():
    try:
        engine = get_engine()
        with engine.connect() as conn:
            print("\n--- Checking Records with NULL usuario_id ---")
            
            # Get records where usuario_id is NULL
            query_nulls = text("SELECT COUNT(*) FROM registros WHERE usuario_id IS NULL")
            result = conn.execute(query_nulls).fetchone()
            print(f"Total records with NULL usuario_id: {result[0]}")
            
            if result[0] > 0:
                # See which technicians these belong to
                query_techs = text("""
                    SELECT t.id_tecnico, t.nombre, COUNT(r.id) as count
                    FROM registros r
                    JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
                    WHERE r.usuario_id IS NULL
                    GROUP BY t.id_tecnico, t.nombre
                    ORDER BY count DESC
                """)
                techs = conn.execute(query_techs).fetchall()
                print("\nTechnicians with unassigned records:")
                for t in techs:
                    print(f"ID: {t[0]}, Name: '{t[1]}', Count: {t[2]}")
            
            # See available users with Role 6 (Dpto Tecnico)
            print("\n--- Available Users in Dpto Tecnico (Role 6) ---")
            query_users = text("SELECT id, nombre, apellido, username FROM usuarios WHERE rol_id = 6")
            users = conn.execute(query_users).fetchall()
            for u in users:
                print(f"ID: {u[0]}, Name: '{u[1]}', Surname: '{u[2]}', Username: '{u[3]}'")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_usuario_ids()
