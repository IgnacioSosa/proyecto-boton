import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import time
import phonenumbers

def initialize_session_state():
    """Inicializa variables de estado de sesión por defecto"""
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'username' not in st.session_state:
        st.session_state.username = None
    if 'is_admin' not in st.session_state:
        st.session_state.is_admin = False
    if 'connection_success' not in st.session_state:
        st.session_state.connection_success = False
    if 'admin_not_found' not in st.session_state:
        st.session_state.admin_not_found = False
    if 'alerts_shown' not in st.session_state:
        st.session_state.alerts_shown = False

def apply_custom_css():
    st.markdown("""
    <style>
    .main .block-container {
        padding-top: 0rem !important;
        padding-bottom: 1rem !important;
    }
    div[data-testid="stImage"] button[title="Fullscreen"],
    div[data-testid="stImage"] button[aria-label="Fullscreen"],
    div[data-testid="stImage"] button[title="View fullscreen"],
    div[data-testid="stImage"] button[aria-label="View fullscreen"],
    div[data-testid="stImage"] button[title*="fullscreen" i],
    div[data-testid="stImage"] button[aria-label*="fullscreen" i],
    button[title*="fullscreen" i],
    button[aria-label*="fullscreen" i] {
        display: none !important;
    }

    /* Ocultar header y footer por defecto para ganar espacio */
    header[data-testid="stHeader"] {
        background-color: transparent !important;
        z-index: 999999 !important;
    }
    
    /* Asegurar que la barra de herramientas (donde están los 3 puntos) sea visible */
    div[data-testid="stToolbar"] {
        visibility: visible !important;
        display: flex !important;
        right: 1rem !important;
        top: 0.5rem !important;
        z-index: 999999 !important;
    }

    /* Ocultar la decoración superior (la línea de colores) si es posible, de forma segura */
    /* En muchas versiones, la decoración es un div vacío al inicio con altura fija */
    header[data-testid="stHeader"] > div[class*="stDecoration"] {
        display: none !important;
    }
    
    footer {
        display: none !important;
    }
    
    /* Ajuste específico para subir el contenido pero respetando el header transparente */
    div.block-container {
        padding-top: 0.75rem !important;
    }
    
    /* Hacer que los selectbox se vean como los campos de texto */
    .stSelectbox div[data-baseweb="select"] > div,
    .stTextInput div[data-baseweb="input"],
    .stNumberInput div[data-baseweb="input"] > div,
    .stDateInput div[data-baseweb="input"],
    .stTextArea div[data-baseweb="textarea"] > div,
    .stSelectbox > div > div,
    .stNumberInput > div > div,
    .stDateInput > div > div,
    .stTextArea > div > div {
        background-color: rgba(128, 128, 128, 0.2) !important;
        border: 1px solid rgba(128, 128, 128, 0.5) !important;
        color: var(--text-color) !important;
        box-shadow: none !important;
    }
    
    /* FIX: Hacer transparentes los hijos del input para que el campo de contraseña (con icono) y fecha se vean bien */
    .stTextInput div[data-baseweb="input"] > div,
    .stDateInput div[data-baseweb="input"] > div {
        background-color: transparent !important;
        border: none !important;
    }
    
    /* Estilos de foco para todos los inputs */
    .stTextInput > div > div > input:focus,
    .stNumberInput > div > div > input:focus,
    .stDateInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: var(--primary-color) !important;
        box-shadow: none !important;
    }

    /* Eliminar borde rojo/rosa de validación o foco */
    .stSelectbox div[data-baseweb="select"] > div:focus-within,
    .stTextInput div[data-baseweb="input"]:focus-within,
    .stNumberInput div[data-baseweb="input"] > div:focus-within,
    .stDateInput div[data-baseweb="input"]:focus-within,
    .stTextArea div[data-baseweb="textarea"] > div:focus-within,
    .stSelectbox > div > div:focus-within,
    .stTextInput > div > div:focus-within,
    .stNumberInput > div > div:focus-within,
    .stDateInput > div > div:focus-within,
    .stTextArea > div > div:focus-within {
        border-color: var(--primary-color) !important;
        box-shadow: none !important;
    }
    
    /* Texto del selectbox */
    .stSelectbox > div > div > div {
        color: var(--text-color) !important;
    }
    
    /* Flecha del dropdown */
    .stSelectbox > div > div svg {
        fill: var(--text-color) !important;
    }
    
    /* Opciones del dropdown con sombreado */
    .stSelectbox [data-baseweb="select"] [data-baseweb="popover"] {
        background-color: var(--background-color) !important;
        border: 1px solid rgba(128, 128, 128, 0.5) !important;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1) !important;
        border-radius: 6px !important;
    }
    
    /* Items individuales del dropdown */
    .stSelectbox [data-baseweb="select"] [data-baseweb="menu"] > ul > li {
        background-color: var(--background-color) !important;
        color: var(--text-color) !important;
        border-bottom: 1px solid var(--secondary-background-color) !important;
    }
    
    /* Hover en las opciones */
    .stSelectbox [data-baseweb="select"] [data-baseweb="menu"] > ul > li:hover {
        background-color: var(--secondary-background-color) !important;
        color: var(--text-color) !important;
    }
    
    /* Último item sin borde inferior */
    .stSelectbox [data-baseweb="select"] [data-baseweb="menu"] > ul > li:last-child {
        border-bottom: none !important;
    }
    
    /* Estilo de enlace para checkbox (link-like toggle) */
    .stCheckbox label {
        color: #60a5fa !important;
        text-decoration: underline !important;
        cursor: pointer !important;
    }
    
    /* Panel del formulario manual de cliente */
    /* contenedor retirado para evitar bloque extra */
    /* Botones estilo enlace dentro de acciones manuales */
    .manual-actions button {
        background: transparent !important;
        color: #60a5fa !important;
        text-decoration: underline !important;
        border: none !important;
        padding: 0 !important;
        box-shadow: none !important;
    }
    .overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(0, 0, 0, 0.5);
        z-index: 9999;
        display: none;
    }

    div[data-testid="stPopover"] button {
        white-space: nowrap;
    }
    .notif-trigger button {
        position: relative;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 4px;
        padding: 0.25rem 0.6rem;
    }
    .notif-trigger button::before {
        content: "";
    }
    .notif-trigger.no-alerts button {
        border-color: #4b5563;
        color: #6b7280;
        opacity: 0.7;
    }
    .notif-trigger.has-alerts button {
        border-color: #ef4444;
    }
    .notif-trigger.has-alerts button::after {
        content: "";
        position: absolute;
        width: 8px;
        height: 8px;
        border-radius: 999px;
        background: #ef4444;
        top: 4px;
        right: 4px;
        box-shadow: 0 0 0 1px #111827;
    }

    /* Estilos específicos para botones primarios en la barra lateral (Logout) - Más pequeño */
    aside[data-testid="stSidebar"] .stButton > button[kind="primary"], 
    aside[data-testid="stSidebar"] .stButton > button[data-testid="baseButton-primary"] {
        min_height: 42px !important;
        height: auto !important;
        font-size: 16px !important;
        padding-top: 8px !important;
        padding-bottom: 8px !important;
    }
    aside[data-testid="stSidebar"] .stButton > button[kind="primary"] p, 
    aside[data-testid="stSidebar"] .stButton > button[data-testid="baseButton-primary"] p {
        font-size: 16px !important;
    }
    </style>
    """, unsafe_allow_html=True)

def show_success_message(message, duration=3):
    """Muestra un mensaje de éxito temporal"""
    placeholder = st.empty()
    placeholder.success(message)
    time.sleep(duration)
    placeholder.empty()

def normalize_text(text):
    import unicodedata
    s = str(text or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = " ".join(s.split())
    return s

def clean_role_name(text):
    """
    Normaliza nombres de roles para comparación y limpieza.
    Maneja prefijos adm_ y dpto_, pero preserva la distinción entre rol base y admin.
    Ej: 'Comercial' -> 'comercial', 'Adm Comercial' -> 'adm_comercial'
    """
    import re
    if not text:
        return ""
    
    # 1. Normalización básica
    s = normalize_text(text)
    
    # 2. Caso especial: 'admin' (rol protegido)
    if s == 'admin':
        return 'admin'
        
    # 3. Separar por delimitadores comunes
    words = re.split(r'[\s_\.]+', s)
    
    is_admin_role = False
    has_dpto_prefix = False
    filtered_words = []
    
    for w in words:
        if w in ['dpto', 'departamento']: 
            has_dpto_prefix = True
            continue
        if w in ['adm', 'admin']:
            is_admin_role = True
            continue
        if w:
            filtered_words.append(w)
            
    base_name = "_".join(filtered_words)
    
    # Si quedó vacío (ej. entrada "Admin"), y era admin, devolvemos "admin"
    if not base_name and is_admin_role:
        return "admin"
        
    if not base_name:
        return ""
        
    # Reconstruir
    if is_admin_role:
        # Usar guion bajo para roles administrativos
        return f"adm_{base_name}"
    elif has_dpto_prefix:
        return f"dpto_{base_name}"
    else:
        return base_name

def format_role_display(name):
    """Formatea nombres de roles snake_case para visualización en UI (ej. 'dpto_tecnico' -> 'Dpto Tecnico')"""
    name = str(name or "")
    # Casos específicos
    if name == 'dpto_comercial': return 'Dpto Comercial'
    if name == 'dpto_tecnico': return 'Dpto Tecnico'
    
    # Lógica general
    if name.startswith('dpto_'):
        return name.replace('dpto_', 'Dpto ').replace('_', ' ').title()
    if name.startswith('adm_'):
        return name.replace('adm_', 'Adm ').replace('_', ' ').title()
    return name.replace('_', ' ').title()

def normalize_sector_name(text):
    return normalize_text(text)

def month_name_es(month_num):
    """Retorna el nombre del mes en español"""
    meses = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
    }
    return meses.get(month_num, "")


def parse_registro_datetime(value):
    """Parsea fechas de registros priorizando formatos explícitos y estables."""
    if value is None:
        return pd.NaT
    try:
        if pd.isna(value):
            return pd.NaT
    except Exception:
        pass

    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        try:
            return pd.to_datetime(value, errors="coerce")
        except Exception:
            return pd.NaT

    raw = str(value).strip()
    if not raw:
        return pd.NaT

    explicit_formats = (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%y %H:%M:%S",
    )
    for fmt in explicit_formats:
        try:
            return pd.to_datetime(raw, format=fmt, errors="raise")
        except Exception:
            pass

    try:
        return pd.to_datetime(raw, dayfirst=True, errors="coerce")
    except Exception:
        return pd.NaT


def format_registro_date_iso(value, empty_value=None):
    """Normaliza una fecha de registro a `YYYY-MM-DD`."""
    parsed = parse_registro_datetime(value)
    if pd.isna(parsed):
        return empty_value
    return parsed.strftime("%Y-%m-%d")


def format_registro_datetime_iso(value, empty_value=None):
    """Normaliza un timestamp a `YYYY-MM-DD HH:MM:SS`."""
    parsed = parse_registro_datetime(value)
    if pd.isna(parsed):
        return empty_value
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def format_registro_date_display(value, fmt="%d/%m/%Y", empty_value="Sin fecha"):
    """Formatea una fecha de registro para mostrar en UI."""
    parsed = parse_registro_datetime(value)
    if pd.isna(parsed):
        return empty_value
    return parsed.strftime(fmt)

def render_excel_uploader(key="excel_uploader", label="Cargar archivo Excel", expanded=False, enable_sheet_selection=True):
    """Renderiza un uploader de Excel y devuelve el DF"""
    uploaded_file = st.file_uploader(label, type=["xlsx", "xls"], key=key)
    if uploaded_file:
        try:
            excel_file = pd.ExcelFile(uploaded_file)
            sheet_names = excel_file.sheet_names
            
            selected_sheet = sheet_names[0]
            if enable_sheet_selection and len(sheet_names) > 1:
                selected_sheet = st.selectbox("Seleccionar hoja", sheet_names, key=f"{key}_sheet_selector")
                
            # Usar el objeto ExcelFile ya creado para parsear la hoja, evitando leer el stream dos veces
            df = excel_file.parse(selected_sheet)
            return uploaded_file, df, selected_sheet
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")
            return None, None, None
    return None, None, None

def log_app_error(e, module="unknown", function="unknown"):
    """Registra un error de la aplicación (placeholder)"""
    print(f"ERROR [{module}.{function}]: {e}")

def get_general_alerts():
    """Calcula alertas generales del sistema:
       - Proyectos vencidos o por vencer (agrupados por dueño)
       - Solicitudes de clientes pendientes
    """
    # Importar aquí para evitar dependencias circulares
    from .database import get_all_proyectos, get_users_dataframe, get_cliente_solicitudes_df
    
    alerts = {
        "owner_alerts": {},
        "pending_requests_count": 0
    }
    
    try:
        req_df = get_cliente_solicitudes_df(estado='pendiente')
        alerts["pending_requests_count"] = len(req_df)
    except Exception as e:
        log_app_error(e, module="utils", function="get_general_alerts")
        
    try:
        # --- Alertas de Proyectos ---
        all_alert_proyectos = get_all_proyectos()
        
        # Map Owner IDs to Names
        users_df_all = get_users_dataframe()
        _nombres = users_df_all['nombre'].fillna('').astype(str).str.strip()
        _apellidos = users_df_all['apellido'].fillna('').astype(str).str.strip()
        users_df_all["nombre_completo"] = (_nombres + ' ' + _apellidos).str.strip()
        owner_map = dict(zip(users_df_all['id'].astype(int), users_df_all['nombre_completo']))
        owner_alerts = {}
        today = pd.Timestamp.now().date()
        if not all_alert_proyectos.empty:
            # filtro 1: estados no cerrados
            _estado_series = all_alert_proyectos.get("estado", pd.Series(dtype=str)).fillna("").astype(str)
            mask_activos = ~_estado_series.isin(["Ganado", "Perdido"])
            _df = all_alert_proyectos.loc[mask_activos].copy()
            if not _df.empty:
                # filtro 2: fecha_cierre válida
                _fc_dt = pd.to_datetime(_df.get("fecha_cierre"), errors="coerce")
                mask_fc = _fc_dt.notna()
                _df = _df.loc[mask_fc]
                _fc_dt = _fc_dt.loc[mask_fc]
                if not _df.empty:
                    # cálculos vectorizados
                    _days_diff = (_fc_dt.dt.date - today).apply(lambda d: d.days)
                    _owner_ids = _df.get("owner_user_id", pd.Series(dtype=float))
                    _owner_name = _owner_ids.apply(
                        lambda x: owner_map.get(int(x), "Desconocido") if pd.notna(x) else "Sin asignar"
                    )
                    # loop solo sobre arrays numpy (menor overhead que iterrows)
                    for owner_name, days_diff in zip(_owner_name.tolist(), _days_diff.tolist()):
                        if owner_name not in owner_alerts:
                            owner_alerts[owner_name] = {"vencidos": 0, "hoy": 0, "pronto": 0}
                        if days_diff < 0:
                            owner_alerts[owner_name]["vencidos"] += 1
                        elif days_diff == 0:
                            owner_alerts[owner_name]["hoy"] += 1
                        elif days_diff <= 7:  # Notify for next 7 days
                            owner_alerts[owner_name]["pronto"] += 1
        
        alerts["owner_alerts"] = owner_alerts
        
    except Exception as e:
         print(f"Error checking project alerts: {e}")
         
    return alerts

def get_week_dates(week_offset=0):
    """Retorna las fechas de inicio (lunes) y fin (domingo) de la semana con offset"""
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week

def format_week_range(start_date, end_date):
    """Formatea el rango de fechas de la semana (ej. '01 Ene - 07 Ene')"""
    def format_date(d):
        return f"{d.day} {month_name_es(d.month)[:3]}"
    return f"{format_date(start_date)} - {format_date(end_date)}"

def prepare_weekly_chart_data(weekly_df, start_of_week):
    """Prepara los datos para el gráfico semanal asegurando que todos los días aparezcan"""
    # Crear DataFrame con todos los días de la semana
    days_data = []
    dias_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    
    for i in range(7):
        current_date = start_of_week + timedelta(days=i)
        dia_nombre = dias_semana[i]
        fecha_str = f"{dia_nombre} {current_date.day}"
        days_data.append({
            'fecha_dt': pd.to_datetime(current_date.date()), # Normalizar a fecha sin hora
            'dia_con_fecha': fecha_str,
            'dia_index': i
        })
    
    base_df = pd.DataFrame(days_data)
    
    # Agrupar datos existentes
    if not weekly_df.empty:
        # Trabajar sobre una copia para evitar SettingWithCopyWarning
        weekly_df = weekly_df.copy()
        
        # Asegurar que fecha_dt sea datetime y solo fecha
        if 'fecha_dt' not in weekly_df.columns:
             # Fallback si no existe (aunque debería haber sido creada en user_dashboard)
             weekly_df['fecha_dt'] = pd.to_datetime(weekly_df['fecha'], errors='coerce')
        
        # Normalizar a fecha sin hora para el merge
        weekly_df['fecha_merge'] = weekly_df['fecha_dt'].dt.normalize()
        base_df['fecha_merge'] = base_df['fecha_dt'].dt.normalize()
        
        grouped = weekly_df.groupby('fecha_merge')['tiempo'].sum().reset_index()
        
        # Merge con los días de la semana
        result_df = pd.merge(base_df, grouped, on='fecha_merge', how='left')
        result_df['tiempo'] = result_df['tiempo'].fillna(0)
    else:
        result_df = base_df
        result_df['tiempo'] = 0.0
        
    return result_df[['dia_con_fecha', 'tiempo']]

def validate_phone_number(phone_str, region="AR"):
    """
    Valida un número de teléfono usando la librería phonenumbers.
    Retorna (True, numero_formateado) si es válido, o (False, mensaje_error).
    """
    if not phone_str:
        return False, "El número de teléfono no puede estar vacío."
    raw_phone = str(phone_str).strip()
    if not raw_phone:
        return False, "El número de teléfono no puede estar vacío."

    import re
    if not re.match(r"^[\d\s\-\(\)\+./]+$", raw_phone):
        return False, "El teléfono contiene caracteres inválidos."

    digits = "".join(ch for ch in raw_phone if ch.isdigit())
    if len(digits) < 6:
        return False, "El teléfono debe tener al menos 6 dígitos."
    if len(digits) > 15:
        return False, "El teléfono no puede superar 15 dígitos."

    try:
        parsed_number = phonenumbers.parse(raw_phone, region)
        
        if phonenumbers.is_possible_number(parsed_number) and phonenumbers.is_valid_number(parsed_number):
            formatted_number = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            return True, formatted_number
    except phonenumbers.NumberParseException:
        pass

    normalized_phone = " ".join(raw_phone.split())
    return True, normalized_phone

def normalize_cuit(value):
    s = ''.join(filter(str.isdigit, str(value or "")))
    return s

def normalize_web(value):
    s = str(value or "").strip()
    if s and not (s.startswith("http://") or s.startswith("https://")):
        s = "https://" + s
    return s

def show_ordered_dataframe(df, base_order, exclude):
    for c in base_order:
        if c not in df.columns:
            df[c] = ""
    base_cols = [c for c in base_order if c in df.columns]
    other_cols = [c for c in df.columns if c not in set(exclude + base_cols)]
    ordered_cols = base_cols + other_cols
    st.dataframe(df[ordered_cols], use_container_width=True)

def show_ordered_dataframe_with_labels(df, base_order, exclude, rename_map=None):
    for c in base_order:
        if c not in df.columns:
            df[c] = ""
    base_cols = [c for c in base_order if c in df.columns]
    other_cols = [c for c in df.columns if c not in set(exclude + base_cols)]
    ordered_cols = base_cols + other_cols
    out = df[ordered_cols]
    if rename_map:
        out = out.rename(columns=rename_map)
    st.dataframe(out, use_container_width=True)

def normalize_name(name):
    import re
    return re.sub(r'[^A-Z0-9]', '', str(name).upper())

def excel_normalize_columns(df, column_map):
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    df.rename(columns=column_map, inplace=True)
    df = df.loc[:, ~df.columns.duplicated()]
    return df

def detect_feriados_columns(df):
    cols = list(df.columns)
    date_col = None
    name_col = None
    type_col = None
    lower_cols = [str(c).strip().lower() for c in cols]
    for idx, lc in enumerate(lower_cols):
        if date_col is None and ("fecha" in lc or "feriado" in lc):
            date_col = cols[idx]
        if name_col is None and "nombre" in lc:
            name_col = cols[idx]
        if type_col is None and "tipo" in lc:
            type_col = cols[idx]
    if date_col is None and cols:
        date_col = cols[0]
    return date_col, name_col, type_col

def safe_rerun():
    import streamlit as st
    st.rerun()

def tokenize(s):
    import re
    s = normalize_text(s)
    toks = [t for t in re.split(r"[\s\-/|,]+", s) if t and len(t) >= 2]
    return set(toks)

def fuzzy_lookup(norm_val, mapping, cutoff=0.7):
    import difflib
    keys = list(mapping.keys())
    matches = difflib.get_close_matches(norm_val, keys, n=1, cutoff=cutoff)
    return mapping[matches[0]] if matches else None

def build_user_lookup_maps(usuarios_df):
    _bn = usuarios_df['nombre'].fillna('').astype(str).str.strip()
    _ba = usuarios_df['apellido'].fillna('').astype(str).str.strip()
    usuarios_df["nombre_completo"] = (_bn + ' ' + _ba).str.strip()
    name_to_id = {normalize_text(n): int(uid) for uid, n in zip(usuarios_df["id"], usuarios_df["nombre_completo"])}
    username_to_id = {normalize_text(u): int(uid) for uid, u in zip(usuarios_df["id"], usuarios_df["username"])}
    _apell = usuarios_df['apellido'].fillna('').astype(str).str.strip()
    _nombr = usuarios_df['nombre'].fillna('').astype(str).str.strip()
    _apell_nombres = (_apell + ' ' + _nombr).apply(normalize_text)
    apell_nombre_to_id = dict(zip(_apell_nombres, usuarios_df['id'].astype(int)))
    return name_to_id, username_to_id, apell_nombre_to_id

def find_cliente_id(cliente, all_clients_data, normalized_client_map):
    cliente_upper = str(cliente or "").upper()
    cliente_norm = normalize_name(cliente)
    cid = None
    for _cid, cname in all_clients_data:
        if str(cname).upper() == cliente_upper:
            cid = _cid
            break
    if (cid is None) and (cliente_norm in normalized_client_map):
        cid = normalized_client_map[cliente_norm]
    if cid is None and len(cliente_norm) >= 3:
        for _cid, cname in all_clients_data:
            cname_norm = normalize_name(cname)
            if (cliente_norm in cname_norm) or (cname_norm in cliente_norm and len(cname_norm) >= 3):
                cid = _cid
                break
    return cid

def parse_planning_cell(cell_val, mod_map, all_clients_data, normalized_client_map, cliente_mod_id):
    import difflib
    import re
    s_raw = str(cell_val if cell_val is not None else "").strip()
    if not s_raw:
        return (None, None)
    key = normalize_text(s_raw)
    if key in mod_map:
        return (mod_map[key], None)
    parts = [p.strip() for p in re.split(r"[\-/|,()]+", s_raw) if p.strip()]
    mod_fallback = None
    for p in reversed(parts):
        pk = normalize_text(p)
        if pk in mod_map:
            mod_fallback = mod_map[pk]
        cid = find_cliente_id(p, all_clients_data, normalized_client_map)
        if cid is not None:
            return (cliente_mod_id, cid)
    if mod_fallback is not None:
        return (mod_fallback, None)
    cid = find_cliente_id(s_raw, all_clients_data, normalized_client_map)
    if cid is not None:
        return (cliente_mod_id, cid)
    best_mod = difflib.get_close_matches(key, list(mod_map.keys()), n=1, cutoff=0.85)
    if best_mod:
        return (mod_map[best_mod[0]], None)
    return (None, None)


def install_cache_guardian():
    """Inyecta un script JS que detecta y se recupera automáticamente del error
    'error loading dynamically imported module' (caché de navegador obsoleta
    tras reinicios de Streamlit).

    Seguridad por diseño:
      • El script NUNCA usa innerHTML / document.write / eval / new Function.
        Toda manipulación de DOM se hace con createElement + textContent.
      • La redirección de recarga usa una URL "blanqueada" (reconstruida desde
        location.origin + pathname + sanitized search) para prevenir open-redirect
        y XSS por datos hostiles en la query string.
      • Restricción de origen: solo se activa sobre el mismo origin de
        window.parent (si fuera cross-origin por alguna configuración rara, el
        acceso a parent.document ya es bloqueado por el browser, pero además
        validamos origin y protocol).
      • El botón 'Recargar ahora' tiene target=_self + rel=noreferrer y NO
        navega a un target _blank (sin riesgo de tab-nabbing).
      • Ningún dato de usuario ni token se envía por red; todo es local al DOM
        y storage del navegador, con saneo de storage preservando solo
        whitelist de keys.
    """
    import streamlit as st
    import streamlit.components.v1 as components

    components.html(
        r"""
<script>
(function(){
  'use strict';
  // ===== VARIABLES DE SEGURIDAD (whitelist) =================================
  var KEEP_KEYS = Object.freeze(['sigo_session_token','sigo_user_id','auth_cookie_present','sigo_cache_bust_count']);
  var ALLOWED_PROTOCOLS = Object.freeze(['https:','http:']);
  var EXPECTED_ERROR_PREFIXES = Object.freeze([
    'error loading dynamically imported module',
    'failed to fetch dynamically imported module',
    'typeerror: error loading dynamically imported module',
  ]);
  var MAX_HISTORY_LEN = 2;  // max 2 recargas en 60s, luego pide modo manual (anti-loop/DoS)
  var AUTO_TRIGGER_MS = 800;
  var AUTO_TRIGGER_MS_CSP = 700;

  try {
    // ===== (A) ORIGIN-SAFE: solo usar window.parent si es mismo origin =====
    var selfOrigin;
    try { selfOrigin = (location.origin || (location.protocol + '//' + location.host)).toLowerCase(); }
    catch(_) { selfOrigin = ''; }

    var useParent = false;
    try {
      if (window.parent && window.parent !== window) {
        var pLoc = window.parent.location;
        var pOrigin = (pLoc.origin || (pLoc.protocol + '//' + pLoc.host)).toLowerCase();
        useParent = (pOrigin === selfOrigin) && ALLOWED_PROTOCOLS.indexOf(pLoc.protocol.toLowerCase()) >= 0;
      }
    } catch(_) { useParent = false; }  // cross-origin (browser already blocks; we skip to self)

    var root = useParent ? window.parent : window;
    var rootDoc = root.document;

    if (ALLOWED_PROTOCOLS.indexOf(location.protocol.toLowerCase()) < 0) {
      return;  // file:/data: u otros: no tocamos nada
    }

    // ===== HELPER: buildSafeRedirectUrl (sin open redirect) ================
    function buildSafeRedirectUrl() {
      var now = String(Date.now());
      var proto = root.location.protocol;
      var host = root.location.host;
      var pathname = root.location.pathname || '/';
      var search = '';
      try {
        var old = root.location.search || '';
        // 1) remover viejo _cb; 2) quitar params potencialmente hostiles con javascript:/data:
        var cleanedPairs = [];
        if (old && old.length > 1) {
          var raw = old.slice(1).split('&');
          for (var i = 0; i < raw.length; i++) {
            if (!raw[i]) continue;
            var pair = raw[i].split('=');
            var k = decodeURIComponent(pair.shift() || '');
            if (!k || k === '_cb') continue;
            if (/[\x00-\x1f<>]/.test(k)) continue;
            var v = pair.length ? decodeURIComponent(pair.join('=')) : '';
            // paranoico: eliminar cualquier proto en valores
            var vl = String(v || '').toLowerCase();
            if (vl.indexOf('javascript:') === 0 || vl.indexOf('data:') === 0 || vl.indexOf('vbscript:') === 0) continue;
            cleanedPairs.push(encodeURIComponent(k) + (v ? '=' + encodeURIComponent(v) : ''));
          }
        }
        cleanedPairs.push('_cb=' + encodeURIComponent(now));
        search = '?' + cleanedPairs.join('&');
      } catch(_) {
        search = '?_cb=' + encodeURIComponent(now);
      }
      var hash = root.location.hash || '';
      // Sanear hash: remover scripts inline potenciales
      if (hash && /javascript:/i.test(hash)) { hash = ''; }
      return proto + '//' + host + pathname + search + hash;
    }

    // ===== HELPER: safeSetText / safeAttr (sin innerHTML) ==================
    function h(tag, attrs, text) {
      var el = rootDoc.createElement(tag);
      if (attrs) {
        for (var k in attrs) if (Object.prototype.hasOwnProperty.call(attrs, k)) {
          var v = attrs[k];
          if (k === 'class') el.className = v;
          else if (k === 'id') el.id = v;
          else if (k === 'for') el.setAttribute('for', v);
          else if (k === 'style') el.setAttribute('style', v);
          else el.setAttribute(k, v);
        }
      }
      if (text != null) el.appendChild(rootDoc.createTextNode(String(text)));
      return el;
    }

    // ===== (1) META-TAGS anti-cache via createElement ======================
    if (!rootDoc.querySelector('meta[name="sigo-cacheguard"]')) {
      [
        {httpEquiv:'Cache-Control', content:'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0'},
        {httpEquiv:'Pragma', content:'no-cache'},
        {httpEquiv:'Expires', content:'0'},
      ].forEach(function(m){
        var meta = rootDoc.createElement('meta');
        meta.httpEquiv = m.httpEquiv;
        meta.content = m.content;
        rootDoc.head.appendChild(meta);
      });
      var sentinel = rootDoc.createElement('meta');
      sentinel.name = 'sigo-cacheguard';
      sentinel.content = '1';
      rootDoc.head.appendChild(sentinel);
    }

    // ===== (2) INYECTAR CSS + OVERLAY (TODOS LOS NODOS via createElement) ==
    var overlay, progressBar, btnFix;
    if (!rootDoc.getElementById('sigo-cacheguard-style')) {
      var style = rootDoc.createElement('style');
      style.id = 'sigo-cacheguard-style';
      style.textContent = [
        '#sigo-cacheguard-overlay{',
        '  position:fixed;inset:0;z-index:2147483646;',
        '  display:none;align-items:center;justify-content:center;',
        '  background:rgba(14,17,23,0.9);backdrop-filter:blur(6px);',
        '  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;',
        '  cursor:default;',
        '}',
        '#sigo-cacheguard-card{',
        '  background:#1f2937;color:#f9fafb;border:1px solid #3b82f6;',
        '  border-radius:14px;padding:26px 28px;max-width:420px;width:90%;',
        '  box-shadow:0 20px 60px rgba(59,130,246,0.22), 0 8px 30px rgba(0,0,0,0.55);',
        '  text-align:center;',
        '}',
        '#sigo-cacheguard-icon{',
        '  width:48px;height:48px;margin:0 auto 12px;border-radius:50%;',
        '  background:linear-gradient(135deg,#3b82f6 0%,#60a5fa 100%);',
        '  display:flex;align-items:center;justify-content:center;font-size:22px;color:#fff;',
        '  animation:sigo-cg-spin 1.1s linear infinite;user-select:none;',
        '}',
        '@keyframes sigo-cg-spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}',
        '#sigo-cacheguard-card h2{margin:0 0 8px;font-size:18px;color:#93c5fd;font-weight:700;}',
        '#sigo-cacheguard-card p{margin:0 0 18px;line-height:1.5;color:#d1d5db;font-size:14px;}',
        '#sigo-cacheguard-card ul{margin:0 0 6px;text-align:left;}',
        '#sigo-cacheguard-card li{margin-bottom:4px;color:#e5e7eb;font-size:14px;line-height:1.5;}',
        '#sigo-cacheguard-card li code{background:#111827;color:#fbbf24;padding:2px 6px;border-radius:4px;font-size:12.5px;}',
        '#sigo-cacheguard-fix{',
        '  display:inline-flex;align-items:center;justify-content:center;gap:6px;',
        '  background:#2563eb;color:#fff;border:none;border-radius:8px;padding:10px 18px;',
        '  font-size:13.5px;font-weight:600;cursor:pointer;transition:transform .08s ease, background .2s ease;',
        '}',
        '#sigo-cacheguard-fix:hover{background:#1d4ed8;transform:translateY(-1px);}',
        '#sigo-cacheguard-fix:active{transform:translateY(0);}',
        '#sigo-cacheguard-fix:disabled{opacity:.55;cursor:not-allowed;transform:none;}',
        '#sigo-cacheguard-progress{',
        '  height:2px;margin-top:14px;background:#374151;border-radius:2px;overflow:hidden;display:none;',
        '}',
        '#sigo-cacheguard-progress > span{',
        '  display:block;height:100%;width:0%;background:linear-gradient(90deg,#3b82f6,#8b5cf6);',
        '  animation:sigo-cg-pulse 1s ease-in-out infinite;',
        '}',
        '@keyframes sigo-cg-pulse{0%{width:0%}50%{width:100%}100%{width:0%}}',
      ].join('');
      rootDoc.head.appendChild(style);

      overlay = h('div', {id:'sigo-cacheguard-overlay','aria-modal':'true','role':'alertdialog','aria-labelledby':'sigo-cg-title','aria-describedby':'sigo-cg-msg'});
      var card = h('div', {id:'sigo-cacheguard-card'});
      var icon = h('div', {id:'sigo-cacheguard-icon'});
      icon.appendChild(rootDoc.createTextNode('🔄'));
      card.appendChild(icon);
      var titleEl = h('h2', {id:'sigo-cg-title'}, 'Actualizando la página');
      card.appendChild(titleEl);
      var msgEl = h('p', {id:'sigo-cg-msg'}, 'Se detectó una versión desactualizada del sitio. La ventana se recargará automáticamente en unos instantes…');
      card.appendChild(msgEl);
      var btnWrap = h('div');
      btnFix = h('button', {id:'sigo-cacheguard-fix', type:'button'}, 'Recargar ahora');
      btnWrap.appendChild(btnFix);
      card.appendChild(btnWrap);
      var progWrap = h('div', {id:'sigo-cacheguard-progress'});
      var progInner = h('span');
      progWrap.appendChild(progInner);
      card.appendChild(progWrap);
      overlay.appendChild(card);
      rootDoc.body.appendChild(overlay);

      btnFix.addEventListener('click', function(){
        sigoForceHardReload('manual');
      });
    } else {
      overlay = rootDoc.getElementById('sigo-cacheguard-overlay');
      progressBar = rootDoc.getElementById('sigo-cacheguard-progress');
      btnFix = rootDoc.getElementById('sigo-cacheguard-fix');
    }

    // ===== (3) Limpieza de storage (whitelist-only) ========================
    function sigoClearCacheArtifacts(){
      try {
        if (root.caches && typeof root.caches.keys === 'function') {
          try {
            Promise.resolve(root.caches.keys()).then(function(keys){
              keys.forEach(function(k){ try { root.caches.delete(k); } catch(_){} });
            });
          } catch(_){}
        }
        try {
          var toKeep = {};
          KEEP_KEYS.forEach(function(k){
            try {
              var v = root.localStorage.getItem(k);
              if (v != null) toKeep[k] = v;
            } catch(_){}
          });
          root.localStorage.clear();
          for (var k in toKeep) if (Object.prototype.hasOwnProperty.call(toKeep, k)) {
            try { root.localStorage.setItem(k, toKeep[k]); } catch(_){}
          }
        } catch(_){}
      } catch(_){}
    }

    function replaceTo(url){
      try { root.location.replace(url); } catch(_){
        // Fallback sin bypass del historial (menos bueno, pero garantiza navegacion)
        try { root.location.assign(url); } catch(_){ root.location.href = url; }
      }
      try { root.location.reload(true); } catch(_){}
    }

    function sigoForceHardReload(reason){
      try {
        var o = overlay || rootDoc.getElementById('sigo-cacheguard-overlay');
        var prog = progressBar || rootDoc.getElementById('sigo-cacheguard-progress');
        if (o) {
          var t = o.querySelector('h2'); if (t) t.textContent = 'Recargando…';
          var p = o.querySelector('p'); if (p) p.textContent = 'En breve volverás a ver el sistema con la versión actualizada.';
          var b = o.querySelector('#sigo-cacheguard-fix'); if (b) { b.disabled = true; b.setAttribute('aria-disabled', 'true'); }
        }
        if (prog) prog.style.display = 'block';
      } catch(_){}

      sigoClearCacheArtifacts();

      var now = Date.now();
      var history;
      try { history = JSON.parse(root.sessionStorage.getItem('sigo_cg_history') || '[]'); } catch(_){ history = []; }
      history = history.filter(function(t){ return now - t < 60000; });
      history.push(now);
      // Límite anti-loop/DoS: no acumular interminables timestamps
      history = history.slice(-(MAX_HISTORY_LEN + 2));
      try { root.sessionStorage.setItem('sigo_cg_history', JSON.stringify(history)); } catch(_){}

      if (history.length > MAX_HISTORY_LEN) {
        try {
          var c = (overlay || rootDoc.getElementById('sigo-cacheguard-overlay'));
          var card2 = c ? c.querySelector('#sigo-cacheguard-card') : null;
          if (card2) {
            while (card2.firstChild) card2.removeChild(card2.firstChild);
            var t2 = h('h2', {}, '🛠️ Acción manual requerida');
            card2.appendChild(t2);
            var p2 = h('p', {}, 'La recarga automática no alcanzó. Por favor hacé manualmente:');
            card2.appendChild(p2);
            var ul = h('ul');
            var li1 = h('li');
            li1.appendChild(rootDoc.createTextNode('Presioná '));
            li1.appendChild(h('code', {}, 'Ctrl + Shift + Supr'));
            ul.appendChild(li1);
            var li2 = h('li');
            li2.appendChild(rootDoc.createTextNode('Marcá '));
            var bold2 = h('b', {}, 'Imágenes y archivos en caché');
            li2.appendChild(bold2);
            li2.appendChild(rootDoc.createTextNode(' (última hora)'));
            ul.appendChild(li2);
            var li3 = h('li');
            li3.appendChild(rootDoc.createTextNode('Aceptá y luego presioná '));
            li3.appendChild(h('code', {}, 'Ctrl + Shift + R'));
            ul.appendChild(li3);
            card2.appendChild(ul);
            var small = h('p', {style:'margin-top:16px'});
            var sm = h('small', {}, 'Si el problema persiste abrí una ventana de incógnito.');
            small.appendChild(sm);
            card2.appendChild(small);
          }
        } catch(_){}
        try {
          var pb = progressBar || rootDoc.getElementById('sigo-cacheguard-progress');
          if (pb) pb.style.display = 'none';
        } catch(_){}
        return;
      }

      var safeUrl = buildSafeRedirectUrl();
      setTimeout(function(){ replaceTo(safeUrl); }, 120);
    }

    // ===== (4) Detectores de error (paranoid signature match) =============
    function matchesSignature(msg, url, reason){
      var text = [String(msg||''), String(url||''), String(reason||'')].join(' ').toLowerCase();
      // Match estricto: debe CONTENER al menos uno de los prefijos oficiales +
      // también el substring distintivo para evitar falsos positivos.
      var hasSignature = false;
      for (var i = 0; i < EXPECTED_ERROR_PREFIXES.length; i++) {
        if (text.indexOf(EXPECTED_ERROR_PREFIXES[i]) >= 0) { hasSignature = true; break; }
      }
      if (!hasSignature) return false;
      // Además requiere un token distintivo (archivo de Streamlit) para
      // evitar que un atacante que imprima ese texto en un comentario/registro
      // dispare la recarga sin que exista el verdadero error de módulo.
      return /(dynamically imported module|static\/js\/(index|possibleconstructorreturn)\.[A-Za-z0-9_-]+\.js)/.test(text);
    }

    function triggerRecoveryIfNeeded(reason){
      var o = overlay || rootDoc.getElementById('sigo-cacheguard-overlay');
      if (!o) return;
      if (o.style.display === 'flex') return;
      o.style.display = 'flex';

      if (!root.__sigoCgAutoTriggered) {
        root.__sigoCgAutoTriggered = true;
        setTimeout(function(){
          var ov = overlay || rootDoc.getElementById('sigo-cacheguard-overlay');
          if (ov && ov.style.display === 'flex') {
            sigoForceHardReload(reason || 'auto');
          }
        }, AUTO_TRIGGER_MS);
      }
    }

    root.addEventListener('error', function(ev){
      try {
        if (matchesSignature(ev.message, ev.filename, '')) triggerRecoveryIfNeeded('onerror');
      } catch(_){}
    }, true);

    root.addEventListener('unhandledrejection', function(ev){
      try {
        var r = ev.reason;
        var msg = (r && r.message) ? r.message : String(r || '');
        var stack = (r && r.stack) ? r.stack : '';
        if (matchesSignature(msg, stack, '')) triggerRecoveryIfNeeded('unhandled');
      } catch(_){}
    }, true);

    // Fallback DOM scan: reducido de 60 a 40 últimos nodos + chequeo de
    // substring + textNode directo, para evitar scan excesivo y falsos +.
    setInterval(function(){
      try {
        var nodes = rootDoc.body.childNodes ? rootDoc.body.querySelectorAll('[data-testid="stAlert"], [role="alert"], .stException, .stError, div') : [];
        var fired = false;
        var start = Math.max(0, nodes.length - 40);
        for (var i = start; i < nodes.length && !fired; i++) {
          var el = nodes[i];
          if (!el || el.childElementCount !== 0) continue;
          var t = (el.textContent || '').slice(0, 500).toLowerCase();
          if ((t.indexOf('error loading dynamically imported module') >= 0 ||
               t.indexOf('failed to fetch dynamically imported module') >= 0) &&
              (t.indexOf('static/js/index.') >= 0 ||
               t.indexOf('dynamically imported module') >= 0)) {
            fired = true;
          }
        }
        if (fired) triggerRecoveryIfNeeded('dom-scan');
      } catch(_){}
    }, 1100);

  } catch (_) {
    // ===== MODO DEGRADADO: CSP/no-access-parent (mismos lineamientos seg) =
    try {
      if (ALLOWED_PROTOCOLS.indexOf(location.protocol.toLowerCase()) < 0) return;

      var cg = document.createElement('div');
      cg.setAttribute('role','alertdialog');
      cg.setAttribute('aria-modal','true');
      cg.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(14,17,23,0.94);display:flex;align-items:center;justify-content:center;font-family:sans-serif;color:#fff;text-align:center;';
      var inner = document.createElement('div');
      inner.style.maxWidth = '360px';
      var ic = document.createElement('div');
      ic.appendChild(document.createTextNode('🔄'));
      ic.style.cssText = 'font-size:28px;margin-bottom:10px;animation:sigoMiniSpin 1s linear infinite;';
      var miniStyle = document.createElement('style');
      miniStyle.textContent = '@keyframes sigoMiniSpin{from{transform:rotate(0)}to{transform:rotate(360deg)}}';
      document.head.appendChild(miniStyle);
      inner.appendChild(ic);
      var hh = document.createElement('h3');
      hh.style.cssText = 'margin:0 0 8px;color:#93c5fd;font-size:18px;';
      hh.appendChild(document.createTextNode('Actualizando'));
      inner.appendChild(hh);
      var pp = document.createElement('p');
      pp.style.cssText = 'margin:0 0 16px;opacity:0.85;line-height:1.5;font-size:14px;';
      pp.appendChild(document.createTextNode('Recargando la página para sincronizar la versión del sitio…'));
      inner.appendChild(pp);
      cg.appendChild(inner);
      document.body.appendChild(cg);

      // safe-url helper mini
      var miniNow = String(Date.now());
      var proto = location.protocol, host = location.host, pathn = location.pathname || '/';
      var oldSearch = location.search || '';
      var cleanedPairs = [];
      try {
        if (oldSearch.length > 1) {
          oldSearch.slice(1).split('&').forEach(function(raw){
            if (!raw) return;
            var pair = raw.split('=');
            var k = decodeURIComponent(pair.shift() || '');
            if (!k || k === '_cb' || /[\x00-\x1f<>]/.test(k)) return;
            var v = pair.length ? decodeURIComponent(pair.join('=')) : '';
            var vl = String(v || '').toLowerCase();
            if (vl.indexOf('javascript:') === 0 || vl.indexOf('data:') === 0) return;
            cleanedPairs.push(encodeURIComponent(k) + (v ? '=' + encodeURIComponent(v) : ''));
          });
        }
      } catch(_){ cleanedPairs = []; }
      cleanedPairs.push('_cb=' + encodeURIComponent(miniNow));
      var theHash = location.hash || '';
      if (/javascript:/i.test(theHash)) theHash = '';
      var finalUrl = proto + '//' + host + pathn + '?' + cleanedPairs.join('&') + theHash;

      setTimeout(function(){
        try { location.replace(finalUrl); } catch(_){ try { location.assign(finalUrl); } catch(_){ location.href = finalUrl; } }
        try { location.reload(true); } catch(_){}
      }, AUTO_TRIGGER_MS_CSP);
    } catch(_){}
  }
})();
</script>
        """,
        height=0,
        width=0,
    )


def render_cache_health_button():
    """Renderiza un botón discreto en el sidebar para que los usuarios
    puedan proactivamente forzar una limpieza de caché sin esperar el error."""
    import streamlit as st
    import streamlit.components.v1 as components

    st.markdown("---")
    if st.button("🧹 Limpiar caché del navegador", use_container_width=True, help="Si notás que la app se ve mal o tiene errores raros después de una actualización, usá este botón."):
        components.html(
            r"""
<script>
(function(){
  try {
    var root = (window.parent && window.parent !== window) ? window.parent : window;
    var now = Date.now();
    var cleaned = root.location.href.replace(/[?&]_cb=\d+/g, '');
    var sep = (cleaned.indexOf('?') >= 0 ? '&' : '?');
    root.location.replace(cleaned + sep + '_cb=' + now + (root.location.hash || ''));
    setTimeout(function(){ try { root.location.reload(true); } catch(_){} }, 50);
  } catch(_){
    var now2 = Date.now();
    location.replace(location.href.split('&')[0]+'&_cb='+now2+location.hash);
    setTimeout(function(){ location.reload(true); }, 50);
  }
})();
</script>
            """,
            height=0,
            width=0,
        )

