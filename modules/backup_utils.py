import pandas as pd
import io
import streamlit as st
from sqlalchemy import text
from .database import get_connection, get_engine, log_sql_error, ensure_clientes_schema, ensure_projects_schema, ensure_cliente_solicitudes_schema

pd.set_option('future.no_silent_downcasting', True)

SPANISH_MONTH_TO_NUMBER = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def _normalize_month_value(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw_lower = raw.lower()
    if raw_lower in SPANISH_MONTH_TO_NUMBER:
        return SPANISH_MONTH_TO_NUMBER[raw_lower]
    digits = "".join(ch for ch in raw_lower if ch.isdigit())
    if digits:
        try:
            month_i = int(digits)
            if 1 <= month_i <= 12:
                return month_i
        except Exception:
            pass
    return value


def _is_date_only_column(column_name):
    name = str(column_name or "").strip().lower()
    if not name:
        return False
    if name == "fecha":
        return True
    if name.startswith("fecha_"):
        return True
    if name in {"fecha cierre", "fecha_cierre", "fecha ref", "fecha_ref", "fecha prevista", "fecha_prevista"}:
        return True
    return False


def _is_datetime_column(column_name):
    name = str(column_name or "").strip().lower()
    if not name:
        return False
    if name.endswith("_at"):
        return True
    if any(token in name for token in ("created_at", "updated_at", "processed_at", "last_login", "timestamp")):
        return True
    return False


def _coerce_datetime_series(series, dayfirst=True):
    try:
        parsed = pd.to_datetime(series, dayfirst=dayfirst, errors="coerce", utc=False)
    except Exception:
        parsed = pd.to_datetime(series.astype(str), dayfirst=dayfirst, errors="coerce", utc=False)
    try:
        if pd.api.types.is_datetime64tz_dtype(parsed):
            parsed = parsed.dt.tz_convert(None)
    except Exception:
        pass
    return parsed


def _normalize_dataframe_for_backup(df):
    if df is None or df.empty:
        return df

    df = df.copy()

    for col in df.columns:
        col_lower = str(col or "").strip().lower()
        if col_lower == "mes":
            df[col] = df[col].apply(_normalize_month_value)
            continue

        if _is_date_only_column(col):
            parsed = _coerce_datetime_series(df[col], dayfirst=True)
            if parsed.notna().any():
                df[col] = parsed.dt.date
            continue

        if _is_datetime_column(col):
            parsed = _coerce_datetime_series(df[col], dayfirst=True)
            if parsed.notna().any():
                df[col] = parsed
            continue

    return df


def _apply_excel_formats(worksheet, df):
    try:
        from openpyxl.utils import get_column_letter
    except Exception:
        return

    if df is None or df.empty:
        return

    date_columns = []
    datetime_columns = []

    for idx, col in enumerate(df.columns, start=1):
        if _is_date_only_column(col):
            date_columns.append(idx)
        elif _is_datetime_column(col):
            datetime_columns.append(idx)

    max_row = worksheet.max_row
    for col_idx in date_columns:
        col_letter = get_column_letter(col_idx)
        for row_idx in range(2, max_row + 1):
            worksheet[f"{col_letter}{row_idx}"].number_format = "DD/MM/YYYY"

    for col_idx in datetime_columns:
        col_letter = get_column_letter(col_idx)
        for row_idx in range(2, max_row + 1):
            worksheet[f"{col_letter}{row_idx}"].number_format = "DD/MM/YYYY HH:MM:SS"


def create_full_backup_excel():
    """Genera un archivo Excel con todas las tablas de la base de datos"""
    conn = get_connection()
    output = io.BytesIO()
    
    try:
        # Obtener lista de tablas públicas
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tablename 
            FROM pg_catalog.pg_tables 
            WHERE schemaname = 'public'
        """)
        tables = [row[0] for row in cursor.fetchall()]
        tables.sort() # Orden alfabético para consistencia visual
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for table in tables:
                try:
                    # Leer tabla
                    engine = get_engine()
                    df = pd.read_sql_query(text(f'SELECT * FROM "{table}"'), con=engine)
                    df = _normalize_dataframe_for_backup(df)
                    
                    # Nombre de hoja (max 31 chars)
                    sheet_name = table[:31]
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    try:
                        ws = writer.sheets.get(sheet_name)
                        if ws is not None:
                            _apply_excel_formats(ws, df)
                    except Exception:
                        pass
                except Exception as e:
                    log_sql_error(f"Error exportando tabla {table}: {e}")
                    
        output.seek(0)
        return output
    except Exception as e:
        log_sql_error(f"Error generando backup: {e}")
        return None
    finally:
        conn.close()

def restore_full_backup_excel(uploaded_file):
    """Restaura la base de datos desde un archivo Excel"""
    # Asegurar que el esquema esté actualizado antes de restaurar (columnas nuevas, tablas, etc.)
    try:
        ensure_clientes_schema()
        ensure_projects_schema()
        ensure_cliente_solicitudes_schema()
    except Exception as e:
        log_sql_error(f"Warning updating schema before restore: {e}")

    conn = get_connection()
    conn.autocommit = False # Usar transacción explícita
    cursor = conn.cursor()
    
    # Orden de eliminación (Tablas hijas primero para evitar FK constraint errors)
    # IMPORTANTE: Mantener este orden sincronizado con las relaciones de la BD
    DELETE_ORDER = [
        'proyecto_documentos',
        'proyecto_compartidos',
        'activity_logs',
        'registros',      # Depende de: tecnicos, clientes, tipos_tarea, modalidades
        'nomina',         # Depende de: roles (departamento)
        'proyectos',      # Depende de: clientes, contactos (moved up to fix FK issue)
        'tecnicos',       # Tabla base para FK de registros (registros_id_tecnico_fkey)
        'contactos',      # Puede depender de clientes
        'clientes',       # Base para registros, proyectos, contactos
        'tipos_tarea',    # Base para registros (registros_id_tipo_fkey)
        'modalidades_tarea', # Base para registros (registros_id_modalidad_fkey) - Nombre correcto en BD
        'marcas',
        'usuarios',
        'roles',
        'grupos',
        'licencias'
    ]
    
    try:
        # Leer Excel (todas las hojas)
        # Usamos na_values=['NaT'] para que pandas interprete "NaT" como NaN desde el inicio
        xls = pd.read_excel(uploaded_file, sheet_name=None, na_values=['NaT'])
        
        # Obtener tablas existentes en BD
        cursor.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'")
        db_tables = [row[0] for row in cursor.fetchall()]
        
        processed_deletes = set()
        
        for table in DELETE_ORDER:
            if table in db_tables:
                # CASCADE borrará dependientes si existen, pero el orden ayuda a evitar bloqueos
                cursor.execute(f"TRUNCATE TABLE {table} CASCADE")
                processed_deletes.add(table)
        
        for table in db_tables:
            if table not in processed_deletes:
                cursor.execute(f"TRUNCATE TABLE {table} CASCADE")

        INSERT_ORDER = list(reversed(DELETE_ORDER))
        
        processed_inserts = set()
        
        def insert_table_data(table_name, df):
            if df.empty:
                return
            
            # Limpiar datos: Convertir a objeto, manejar "NaT" strings y NaNs
            df_clean = df.astype(object)
            
            # Reemplazar explícitamente cualquier string residual "NaT", "NaN" o "nan"
            # Esto es un fallback en caso de que na_values no haya capturado todo
            df_clean.replace(["NaT", "nan", "NaN"], None, inplace=True)
            
            # Reemplazar valores nulos de pandas (NaN, NaT object) por None de Python
            df_clean = df_clean.where(pd.notnull(df_clean), None)
            
            try:
                cursor.execute(f"""
                    SELECT column_name, is_nullable, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}'
                """)
                schema = {row[0]: {'nullable': row[1] == 'YES', 'type': row[2]} for row in cursor.fetchall()}
                
                allowed_columns = [c for c in df_clean.columns if c in schema]
                if not allowed_columns:
                    return
                if len(allowed_columns) != len(df_clean.columns):
                    df_clean = df_clean[allowed_columns]
                
                for col in df_clean.columns:
                    if col in schema:
                        props = schema[col]
                        if not props['nullable']:
                            if props['type'] in ('character varying', 'text', 'character', 'bpchar'):
                                df_clean[col] = df_clean[col].fillna('')
                            elif props['type'] in ('integer', 'bigint', 'smallint', 'numeric', 'double precision', 'real'):
                                df_clean[col] = df_clean[col].fillna(0)
                            elif props['type'] == 'boolean':
                                df_clean[col] = df_clean[col].fillna(False)
                
                # NO usar infer_objects aquí, ya que puede revertir None a pd.NaT en columnas de fecha
                # df_clean = df_clean.infer_objects(copy=False)
                
                # Asegurar nuevamente que no queden NaT/NaN después de cualquier manipulación
                df_clean = df_clean.where(pd.notnull(df_clean), None)
            except Exception as e:
                log_sql_error(f"Warning checking schema for {table_name}: {e}")

            columns = list(df_clean.columns)
            cols_str = ",".join([f'"{c}"' for c in columns])
            placeholders = ",".join(["%s"] * len(columns))
            
            query = f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({placeholders})'
            
            values = df_clean.values.tolist()
            
            cursor.executemany(query, values)
        
        for table in INSERT_ORDER:
            sheet_name = table[:31]
            if sheet_name in xls:
                insert_table_data(table, xls[sheet_name])
                processed_inserts.add(sheet_name)
        
        for sheet_name, df in xls.items():
            if sheet_name not in processed_inserts:
                target_table = None
                if sheet_name in db_tables:
                    target_table = sheet_name
                else:
                    for t in db_tables:
                        if t[:31] == sheet_name:
                            target_table = t
                            break
                
                if target_table:
                    insert_table_data(target_table, df)
        
        for table in db_tables:
            cursor.execute(f"""
                SELECT column_name, column_default 
                FROM information_schema.columns 
                WHERE table_name = '{table}' 
                AND column_default LIKE 'nextval%%'
            """)
            serial_cols = cursor.fetchall()
            
            for col_name, col_default in serial_cols:
                # Extraer nombre de secuencia: nextval('mi_secuencia'::regclass)
                # O simplemente usar pg_get_serial_sequence
                try:
                    cursor.execute(f"SELECT pg_get_serial_sequence('{table}', '{col_name}')")
                    seq_res = cursor.fetchone()
                    if seq_res and seq_res[0]:
                        seq_name = seq_res[0]
                        # Resetear al max(id) + 1
                        cursor.execute(f"""
                            SELECT setval('{seq_name}', (SELECT COALESCE(MAX("{col_name}"), 0) + 1 FROM "{table}"), false)
                        """)
                except Exception as e:
                    log_sql_error(f"Warning reset sequence {table}.{col_name}: {e}")

        conn.commit()
        return True, "Restauración completada exitosamente. Todas las tablas han sido recargadas."
        
    except Exception as e:
        conn.rollback()
        return False, f"Error crítico en restauración: {str(e)}"
    finally:
        conn.close()
