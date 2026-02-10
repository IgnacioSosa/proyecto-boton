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
        padding-top: 1rem;
        padding-bottom: 1rem;
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

    /* Estilos para botones primarios más grandes - ELIMINADO para evitar conflictos globales */
    /*
    .stButton > button[kind="primary"], 
    .stButton > button[data-testid="baseButton-primary"] {
        height: auto !important;
        min-height: 60px !important;
        font-size: 22px !important;
        padding-top: 15px !important;
        padding-bottom: 15px !important;
    }
    .stButton > button[kind="primary"] p, 
    .stButton > button[data-testid="baseButton-primary"] p {
        font-size: 22px !important;
    }
    */

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
    """Normaliza texto para comparaciones (lowercase, sin espacios extra)"""
    if not isinstance(text, str):
        return ""
    return " ".join(text.lower().split())

def normalize_sector_name(text):
    """Normaliza nombre de sector para comparaciones"""
    return normalize_text(text)

def month_name_es(month_num):
    """Retorna el nombre del mes en español"""
    meses = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
    }
    return meses.get(month_num, "")

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
                
            df = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
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
        # --- Solicitudes de Clientes ---
        req_df = get_cliente_solicitudes_df(estado='pendiente')
        alerts["pending_requests_count"] = len(req_df)
    except Exception as e:
        print(f"Error checking pending requests: {e}")
        
    try:
        # --- Alertas de Proyectos ---
        all_alert_proyectos = get_all_proyectos()
        
        # Map Owner IDs to Names
        users_df_all = get_users_dataframe()
        users_df_all["nombre_completo"] = users_df_all.apply(lambda r: f"{(r['nombre'] or '').strip()} {(r['apellido'] or '').strip()}".strip(), axis=1)
        owner_map = {int(r["id"]): r["nombre_completo"] for _, r in users_df_all.iterrows()}

        owner_alerts = {}
        today = pd.Timestamp.now().date()
        
        for _, row in all_alert_proyectos.iterrows():
            if row.get("estado") in ["Ganado", "Perdido"]:
                continue
                
            fc_dt = pd.to_datetime(row.get("fecha_cierre"), errors="coerce")
            if pd.isna(fc_dt):
                continue
                
            days_diff = (fc_dt.date() - today).days
            owner_name = owner_map.get(int(row["owner_user_id"]), "Desconocido") if pd.notna(row.get("owner_user_id")) else "Sin asignar"
            
            if owner_name not in owner_alerts:
                owner_alerts[owner_name] = {"vencidos": 0, "hoy": 0, "pronto": 0}
                
            if days_diff < 0:
                owner_alerts[owner_name]["vencidos"] += 1
            elif days_diff == 0:
                owner_alerts[owner_name]["hoy"] += 1
            elif days_diff <= 7: # Notify for next 7 days
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
    
    try:
        # Intentar parsear
        parsed_number = phonenumbers.parse(phone_str, region)
        
        # Verificar si es posible y válido
        if not phonenumbers.is_possible_number(parsed_number):
            return False, "El número de teléfono no parece ser posible."
            
        if not phonenumbers.is_valid_number(parsed_number):
            return False, "El número de teléfono no es válido."
            
        # Formatear a estándar internacional
        formatted_number = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        
        return True, formatted_number
        
    except phonenumbers.NumberParseException:
        return False, "Formato de teléfono irreconocible. Intente agregar el código de área."
