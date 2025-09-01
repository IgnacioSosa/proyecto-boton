import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import time

def apply_custom_css():
    """Aplica CSS personalizado para mejorar la visibilidad"""
    st.markdown("""
    <style>
        /* Contenedor del menú desplegable (popover) */
        div[data-baseweb="popover"] ul {
            background-color: #262730;
            border: 1px solid #F63366;
        }

        /* Opciones individuales en el menú */
        li[role="option"] {
            background-color: #262730;
            color: #FAFAFA;
        }

        /* Opción al pasar el mouse por encima (hover) */
        li[role="option"]:hover {
            background-color: #F63366;
            color: white;
        }
    </style>
    """, unsafe_allow_html=True)

def initialize_session_state():
    """Inicializa las variables de estado de la sesión"""
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'is_admin' not in st.session_state:
        st.session_state.is_admin = False
    if 'mostrar_perfil' not in st.session_state:
        st.session_state.mostrar_perfil = False
    if 'awaiting_2fa' not in st.session_state:
        st.session_state.awaiting_2fa = False

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

def show_success_message(message, delay=1):
    """Muestra un mensaje de éxito y recarga la página"""
    import time
    st.success(message)
    time.sleep(delay)
    st.rerun()


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