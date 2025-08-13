import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

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
    """Inicializa el estado de la sesión"""
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
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