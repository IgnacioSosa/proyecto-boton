
import sys
import os
import pandas as pd
from sqlalchemy import text

# Add the project root to sys.path to allow imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.database import get_engine

def check_records_status():
    try:
        engine = get_engine()
        with engine.connect() as conn:
            print("\n--- Checking Records Assigned to Role 6 (Dpto Tecnico) ---")
            
            # Get users with Role 6
            query_users = text("SELECT id, username FROM usuarios WHERE rol_id = 6")
            users = conn.execute(query_users).fetchall()
            user_ids = [u[0] for u in users]
            print(f"Role 6 User IDs: {user_ids}")
            
            if not user_ids:
                print("No users found with Role 6!")
                return

            # Check records assigned to these users
            query_records = text(f"""
                SELECT COUNT(*) 
                FROM registros 
                WHERE usuario_id IN :user_ids
            """)
            result = conn.execute(query_records, {"user_ids": tuple(user_ids)}).fetchone()
            count = result[0]
            print(f"Total records assigned to Role 6 users: {count}")
            
            if count > 0:
                # Check dates
                print("\n--- Date Distribution for Role 6 Records ---")
                query_dates = text(f"""
                    SELECT fecha, COUNT(*) 
                    FROM registros 
                    WHERE usuario_id IN :user_ids
                    GROUP BY fecha
                    ORDER BY to_date(fecha, 'DD/MM/YY') DESC
                    LIMIT 20
                """)
                # Note: to_date might fail if format varies, but let's try assuming DD/MM/YY as per common format
                try:
                    dates = conn.execute(query_dates, {"user_ids": tuple(user_ids)}).fetchall()
                    for d in dates:
                        print(f"Date: '{d[0]}', Count: {d[1]}")
                except Exception as e:
                    print(f"Error querying dates (might be format issue): {e}")
                    # Fallback to string sort
                    query_dates_str = text(f"""
                        SELECT fecha, COUNT(*) 
                        FROM registros 
                        WHERE usuario_id IN :user_ids
                        GROUP BY fecha
                        ORDER BY fecha DESC
                        LIMIT 20
                    """)
                    dates = conn.execute(query_dates_str, {"user_ids": tuple(user_ids)}).fetchall()
                    for d in dates:
                        print(f"Date (string): '{d[0]}', Count: {d[1]}")

                # Check created_at distribution
                print("\n--- Created_at Distribution for Role 6 Records ---")
                query_created = text(f"""
                    SELECT created_at::date, COUNT(*) 
                    FROM registros 
                    WHERE usuario_id IN :user_ids
                    GROUP BY created_at::date
                    ORDER BY created_at::date DESC
                    LIMIT 10
                """)
                created = conn.execute(query_created, {"user_ids": tuple(user_ids)}).fetchall()
                for c in created:
                    print(f"Created At: {c[0]}, Count: {c[1]}")

            else:
                print("\n--- Troubleshooting: Where are the records? ---")
                # Check records that are NOT assigned to Role 6 but have 'id_tecnico' matching Role 6 users?
                # We need to map tecnicos to users.
                pass

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_records_status()
