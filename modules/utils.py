import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import time

def apply_custom_css():
    st.markdown("""
    <style>
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* Hacer que los selectbox se vean como los campos de texto */
    .stSelectbox > div > div {
        background-color: #262730 !important;
        border: 1px solid #4a4a4a !important;
        color: #ffffff !important;
    }
    
    /* Texto del selectbox */
    .stSelectbox > div > div > div {
        color: #ffffff !important;
    }
    
    /* Flecha del dropdown */
    .stSelectbox > div > div svg {
        fill: #ffffff !important;
    }
    
    /* Opciones del dropdown con sombreado */
    .stSelectbox [data-baseweb="select"] [data-baseweb="popover"] {
        background-color: #262730 !important;
        border: 2px solid #5a5a5a !important;
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.4), 0 4px 8px rgba(0, 0, 0, 0.3) !important;
        border-radius: 6px !important;
    }
    
    /* Items individuales del dropdown */
    .stSelectbox [data-baseweb="select"] [data-baseweb="menu"] > ul > li {
        background-color: #262730 !important;
        color: #ffffff !important;
        border-bottom: 1px solid #3a3a3a !important;
    }
    
    /* Hover en las opciones */
    .stSelectbox [data-baseweb="select"] [data-baseweb="menu"] > ul > li:hover {
        background-color: #3a3a3a !important;
        color: #ffffff !important;
    }
    
    /* Último item sin borde inferior */
    .stSelectbox [data-baseweb="select"] [data-baseweb="menu"] > ul > li:last-child {
        border-bottom: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

def initialize_session_state():
    """Inicializa el estado de la sesión con valores por defecto"""
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'username' not in st.session_state:
        st.session_state.username = None
    if 'user_role' not in st.session_state:
        st.session_state.user_role = None
    if 'user_role_id' not in st.session_state:
        st.session_state.user_role_id = None
    if 'user_grupo' not in st.session_state:
        st.session_state.user_grupo = None
    if 'is_authenticated' not in st.session_state:
        st.session_state.is_authenticated = False
    if 'show_2fa' not in st.session_state:
        st.session_state.show_2fa = False
    if 'temp_user_data' not in st.session_state:
        st.session_state.temp_user_data = None

def get_week_dates(week_offset=0):
    """Obtiene las fechas de la semana actual o con offset
    
    Args:
        week_offset (int): Número de semanas a desplazar (0 = semana actual, -1 = semana anterior, 1 = semana siguiente)
    
    Returns:
        tuple: (start_of_week, end_of_week) como objetos datetime
    """
    today = datetime.now()
    # Calcular el inicio de la semana con el offset
    start_of_week = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week

def format_week_dates(start_date, end_date):
    """Formatea las fechas de la semana para mostrar"""
    return f"{start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m/%Y')}"

def format_week_range(start_date, end_date):
    """Formatea el rango de fechas de una semana para mostrar
    
    Args:
        start_date (datetime): Fecha de inicio de la semana
        end_date (datetime): Fecha de fin de la semana
    
    Returns:
        str: Rango formateado como "dd/mm - dd/mm/yyyy"
    """
    return f"{start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m/%Y')}"

def prepare_weekly_data(df):
    """Prepara los datos para gráficos semanales"""
    if df.empty:
        return pd.DataFrame()
    
    # Convertir fecha a datetime si no lo está
    if 'fecha' in df.columns:
        df['fecha'] = pd.to_datetime(df['fecha'], format='%d/%m/%y', errors='coerce')
    
    # Filtrar datos de la semana actual
    start_of_week, end_of_week = get_week_dates()
    weekly_df = df[(df['fecha'] >= start_of_week) & (df['fecha'] <= end_of_week)]
    
    return weekly_df

def prepare_weekly_chart_data(df, start_of_week):
    """Prepara los datos para gráficos semanales con días específicos
    
    Args:
        df (pd.DataFrame): DataFrame con los datos de registros
        start_of_week (datetime): Fecha de inicio de la semana
    
    Returns:
        pd.DataFrame: DataFrame preparado para gráficos con columnas 'dia_con_fecha' y 'tiempo'
    """
    if df.empty:
        # Crear DataFrame vacío con estructura esperada
        dias_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        fechas_semana = [(start_of_week + timedelta(days=i)).strftime('%d/%m') for i in range(7)]
        dias_con_fecha = [f"{dia}\n{fecha}" for dia, fecha in zip(dias_semana, fechas_semana)]
        
        return pd.DataFrame({
            'dia_con_fecha': dias_con_fecha,
            'tiempo': [0] * 7
        })
    
    # Convertir fecha a datetime si no lo está
    if 'fecha' in df.columns:
        df = df.copy()
        df['fecha'] = pd.to_datetime(df['fecha'], format='%d/%m/%y', errors='coerce')
    
    # Crear columna de día de la semana
    df['dia_semana'] = df['fecha'].dt.day_name()
    
    # Mapear nombres de días al español
    day_mapping = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    df['dia_semana'] = df['dia_semana'].map(day_mapping)
    
    # Agrupar por día y sumar tiempo
    horas_por_dia = df.groupby('dia_semana')['tiempo'].sum().reset_index()
    
    # Crear lista completa de días de la semana con fechas
    dias_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    fechas_semana = [(start_of_week + timedelta(days=i)).strftime('%d/%m') for i in range(7)]
    
    # Crear DataFrame completo con todos los días
    dias_completos = []
    for i, dia in enumerate(dias_semana):
        tiempo = horas_por_dia[horas_por_dia['dia_semana'] == dia]['tiempo'].sum() if dia in horas_por_dia['dia_semana'].values else 0
        dias_completos.append({
            'dia_con_fecha': f"{dia}\n{fechas_semana[i]}",
            'tiempo': tiempo
        })
    
    return pd.DataFrame(dias_completos)

def month_name_es(month_num):
    """Convierte número de mes a nombre en español"""
    months = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }
    # Preservar si ya es un nombre de mes en español
    if isinstance(month_num, str):
        s = str(month_num).strip().capitalize()
        if s in months.values():
            return s
    try:
        month_num = int(month_num) if month_num is not None else 0
    except (ValueError, TypeError):
        month_num = 0
    if month_num < 1 or month_num > 12:
        from datetime import datetime
        month_num = datetime.now().month
    return months.get(month_num, 'Desconocido')

def show_success_message(message, delay=1):
    """Muestra un mensaje de éxito sin recargar automáticamente la página"""
    st.success(message)

def normalize_text(text):
    """Normaliza un texto: convierte a minúsculas y elimina tildes"""
    if not text or pd.isna(text):
        return ""
    
    import unicodedata
    text = str(text).lower().strip()
    # Eliminar tildes
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    return text

def normalize_sector_name(sector):
    """Normaliza el nombre de un sector para comparación insensible a mayúsculas/minúsculas y tildes"""
    return normalize_text(sector)

def detect_name_columns(df):
    """Detecta automáticamente las columnas de nombres en el DataFrame
    
    Args:
        df (pd.DataFrame): DataFrame a analizar
        
    Returns:
        dict: Mapeo de columnas detectadas a nombres estándar
    """
    import unicodedata
    
    def normalize_column_name(col):
        """Normaliza nombre de columna removiendo acentos y caracteres especiales"""
        if not col:
            return ""
        col = str(col).strip().lower()
        # Remover acentos
        col = unicodedata.normalize('NFD', col)
        col = ''.join(char for char in col if unicodedata.category(char) != 'Mn')
        return col
    
    # Mapeos posibles para cada campo
    field_mappings = {
        'fecha': ['fecha', 'date', 'dia', 'day'],
        'tecnico': ['tecnico', 'técnico', 'technician', 'tech', 'empleado', 'trabajador'],
        'cliente': ['cliente', 'client', 'customer', 'empresa', 'company'],
        'tipo_tarea': ['tipo tarea', 'tipo_tarea', 'task type', 'tipo', 'tarea', 'task'],
        'modalidad': ['modalidad', 'modality', 'modo', 'mode'],
        'tiempo': ['tiempo', 'time', 'horas', 'hours', 'duracion', 'duration'],
        'numero_ticket': ['numero ticket', 'n° ticket', 'ticket', 'numero_ticket', 'ticket_number'],
        'tarea_realizada': ['tarea realizada', 'descripcion', 'description', 'breve descripcion', 'detalle'],
        'grupo': ['grupo', 'group', 'sector', 'equipo', 'team', 'departamento']
    }
    
    detected_columns = {}
    df_columns_normalized = [normalize_column_name(col) for col in df.columns]
    
    for field, possible_names in field_mappings.items():
        for col_idx, norm_col in enumerate(df_columns_normalized):
            for possible_name in possible_names:
                if normalize_column_name(possible_name) in norm_col or norm_col in normalize_column_name(possible_name):
                    detected_columns[field] = df.columns[col_idx]
                    break
            if field in detected_columns:
                break
    
    return detected_columns

def render_excel_uploader(label="Selecciona un archivo Excel (.xls o .xlsx)", key="excel_upload", expanded=False, enable_sheet_selection=True):
    """Función reutilizable para cargar archivos Excel con selección de hojas
    
    Args:
        label (str): Etiqueta para el cargador de archivos
        key (str): Clave única para el componente
        expanded (bool): Si el expander debe estar expandido por defecto
        enable_sheet_selection (bool): Si habilitar la selección de hojas
        
    Returns:
        tuple: (uploaded_file, excel_df, selected_sheet) donde excel_df es None si no se ha cargado ningún archivo
    """
    excel_df = None
    selected_sheet = None
    
    with st.expander("📁 Cargar datos desde archivo Excel", expanded=expanded):
        uploaded_file = st.file_uploader(
            label,
            type=['xlsx', 'xls'],
            key=key
        )
        
        if uploaded_file is not None:
            try:
                # Importar explícitamente openpyxl antes de leer el Excel
                import openpyxl
                
                # Obtener nombres de las hojas si está habilitada la selección
                if enable_sheet_selection:
                    workbook = openpyxl.load_workbook(uploaded_file, read_only=True)
                    sheet_names = workbook.sheetnames
                    workbook.close()
                    
                    # Determinar el índice por defecto (buscar "METRICAS" primero)
                    default_index = 0
                    if "METRICAS" in sheet_names:
                        default_index = sheet_names.index("METRICAS")
                    
                    # Siempre mostrar el selectbox si hay hojas disponibles
                    if len(sheet_names) > 0:
                        selected_sheet = st.selectbox(
                            "Seleccionar hoja:",
                            options=sheet_names,
                            index=default_index,
                            key=f"{key}_sheet_selector"
                        )
                    else:
                        selected_sheet = sheet_names[0] if sheet_names else None
                        st.info(f"Hoja seleccionada automáticamente: **{selected_sheet}**")
                else:
                    selected_sheet = 0  # Primera hoja por defecto
                
                # Leer el archivo Excel con la hoja seleccionada
                excel_df = pd.read_excel(uploaded_file, sheet_name=selected_sheet, engine='openpyxl')
                
                st.subheader("Vista previa del archivo")
                st.dataframe(excel_df.head(), use_container_width=True)
                
            except Exception as e:
                st.error(f"Error al leer el archivo: {str(e)}")
                excel_df = None
                selected_sheet = None
    
    return uploaded_file, excel_df, selected_sheet