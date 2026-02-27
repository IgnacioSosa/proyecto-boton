
import os
import sys
import pandas as pd
from sqlalchemy import text

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.database import get_engine

def list_roles():
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id_rol, nombre FROM roles ORDER BY id_rol"))
        roles = result.fetchall()
        for role in roles:
            print(f"ID: {role[0]}, Name: '{role[1]}'")

if __name__ == "__main__":
    list_roles()
