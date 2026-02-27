import sys
import os
import pandas as pd
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.database import get_registros_by_rol_with_date_filter, get_engine

def test_get_registros_created_at():
    print("--- Testing get_registros_by_rol_with_date_filter(6, 'current_month', use_created_at=True) ---")
    try:
        df = get_registros_by_rol_with_date_filter(6, 'current_month', use_created_at=True)
        print(f"Result DataFrame shape: {df.shape}")
        if not df.empty:
            print("First 5 rows:")
            print(df.head()[['fecha', 'Fecha Creación']])
        else:
            print("DataFrame is empty!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_get_registros_created_at()
