import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import time

def apply_custom_css():
    """Aplica estilos CSS personalizados"""
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    </style>
    """, unsafe_allow_html=True)

def initialize_session_state():
    """Inicializa variables de estado de sesión"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'username' not in st.session_state:
        st.session_state.username = None
    if 'is_admin' not in st.session_state:
        st.session_state.is_admin = False


def get_week_dates(week_offset=0):
    """Obtiene las fechas de inicio y fin de una semana"""
    today = datetime.now()
    start_of_week = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week

def format_week_range(start_date, end_date):
    """Formatea el rango de fechas de una semana"""
    return f"Semana del {start_date.strftime('%d/%m/%Y')} al {end_date.strftime('%d/%m/%Y')}"

def prepare_weekly_chart_data(weekly_df, start_of_week):
    """Prepara los datos para el gráfico semanal"""
    # Mapear días a español
    dias_es = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles', 
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    
    weekly_df['dia_semana'] = weekly_df['fecha_dt'].dt.day_name().map(dias_es)
    horas_por_dia = weekly_df.groupby('dia_semana')['tiempo'].sum().reset_index()
    
    # Asegurar que todos los días de la semana estén presentes y en orden
    dias_ordenados = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    dias_completos_df = pd.DataFrame({'dia_semana': dias_ordenados})
    horas_por_dia_final = pd.merge(dias_completos_df, horas_por_dia, on='dia_semana', how='left').fillna(0)
    
    # Crear etiquetas con día y fecha
    etiquetas_con_fecha = []
    for i, dia in enumerate(dias_ordenados):
        fecha_dia = start_of_week + timedelta(days=i)
        etiqueta = f"{dia}<br>{fecha_dia.strftime('%d/%m')}"
        etiquetas_con_fecha.append(etiqueta)
    
    horas_por_dia_final['dia_con_fecha'] = etiquetas_con_fecha
    
    return horas_por_dia_final

# NUEVO: utilidades para meses en español
MONTHS_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

def month_name_es(i: int) -> str:
    """Devuelve el nombre del mes en español para 1-12."""
    try:
        return MONTHS_ES[i]
    except Exception:
        return str(i)

def english_to_spanish_month(mes_str: str) -> str:
    """Traduce un nombre de mes en inglés a español. Si ya está en español o no se reconoce, lo devuelve tal cual."""
    if not mes_str:
        return mes_str
    mapping = {
        "january": "Enero",
        "february": "Febrero",
        "march": "Marzo",
        "april": "Abril",
        "may": "Mayo",
        "june": "Junio",
        "july": "Julio",
        "august": "Agosto",
        "september": "Septiembre",
        "october": "Octubre",
        "november": "Noviembre",
        "december": "Diciembre",
    }
    lower = str(mes_str).strip().lower()
    return mapping.get(lower, mes_str)

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


def render_excel_uploader(label="Selecciona un archivo Excel (.xls o .xlsx)", key="excel_upload", expanded=False):
    """Función reutilizable para cargar archivos Excel
    
    Args:
        label (str): Etiqueta para el cargador de archivos
        key (str): Clave única para el componente
        expanded (bool): Si el expander debe estar expandido por defecto
        
    Returns:
        tuple: (uploaded_file, excel_df) donde excel_df es None si no se ha cargado ningún archivo
    """
    excel_df = None
    
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
                # Leer el archivo Excel
                excel_df = pd.read_excel(uploaded_file, engine='openpyxl')
                
                st.subheader("Vista previa del archivo")
                st.dataframe(excel_df.head(), use_container_width=True)
            except Exception as e:
                st.error(f"Error al leer el archivo: {str(e)}")
                excel_df = None
    
    return uploaded_file, excel_df