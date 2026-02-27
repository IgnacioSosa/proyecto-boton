
import os
import sys
import pandas as pd
from sqlalchemy import text
from datetime import datetime

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.database import get_engine, process_registros_df, get_registros_by_rol_with_date_filter

def check_dates():
    # 1. Test get_registros_by_rol_with_date_filter directly
    print("\n--- Testing get_registros_by_rol_with_date_filter(6, 'current_month') ---")
    df_filtered = get_registros_by_rol_with_date_filter(6, 'current_month')
    print(f"Result count: {len(df_filtered)}")
    if not df_filtered.empty:
        print("Sample dates:")
        print(df_filtered['fecha'].head())
    else:
        print("Result is EMPTY!")

    # 2. Test with custom_month/year explicitly for Feb 2026
    print("\n--- Testing get_registros_by_rol_with_date_filter(6, 'custom_month', 2, 2026) ---")
    df_custom = get_registros_by_rol_with_date_filter(6, 'custom_month', custom_month=2, custom_year=2026)
    print(f"Result count: {len(df_custom)}")
    
    # 3. Test with use_created_at=True
    print("\n--- Testing get_registros_by_rol_with_date_filter(6, 'current_month', use_created_at=True) ---")
    df_created = get_registros_by_rol_with_date_filter(6, 'current_month', use_created_at=True)
    print(f"Result count: {len(df_created)}")

if __name__ == "__main__":
    check_dates()
