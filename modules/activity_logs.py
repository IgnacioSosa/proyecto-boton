import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from .database import get_actividades_dataframe
from .logging_utils import log_app_error  # Añadir esta importación

def render_activity_logs():
    """Renderiza la visualización de registros de actividad de usuarios"""
    try:  # Añadir bloque try-except
        st.subheader("Registros de Actividad de Usuarios")
        
        # Obtener registros de actividad
        df = get_actividades_dataframe()
        
        if df.empty:
            st.info("No hay registros de actividad para mostrar")
            return
        
        # Convertir la columna fecha_hora a datetime ANTES de usarla
        if 'fecha_hora' in df.columns:
            df['fecha_hora'] = pd.to_datetime(df['fecha_hora'])
        
        # Añadir filtros
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Filtro por tipo de actividad
            tipos_actividad = ['Todos'] + sorted(df['tipo_actividad'].unique().tolist())
            tipo_seleccionado = st.selectbox("Tipo de actividad", tipos_actividad)
        
        with col2:
            # Filtro por usuario
            usuarios = ['Todos'] + sorted(df['username'].unique().tolist())
            usuario_seleccionado = st.selectbox("Usuario", usuarios)
        
        with col3:
            # Filtro por fecha
            fechas = sorted(df['fecha_hora'].dt.date.unique())
            if fechas:
                fecha_seleccionada = st.date_input("Fecha", value=max(fechas), min_value=min(fechas), max_value=max(fechas))
            else:
                fecha_seleccionada = None
        
        # Aplicar filtros
        df_filtrado = df.copy()
        
        if tipo_seleccionado != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['tipo_actividad'] == tipo_seleccionado]
        
        if usuario_seleccionado != 'Todos':
            df_filtrado = df_filtrado[df_filtrado['username'] == usuario_seleccionado]
        
        if fecha_seleccionada:
            df_filtrado = df_filtrado[df_filtrado['fecha_hora'].dt.date == fecha_seleccionada]
        
        # Preparar DataFrame para visualización
        df_display = df_filtrado.copy()
        
        # Formatear fecha y hora
        df_display['fecha_hora'] = df_display['fecha_hora'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Crear columna de nombre completo
        df_display['usuario'] = df_display.apply(
            lambda row: f"{row['nombre']} {row['apellido']}" if pd.notna(row['nombre']) and pd.notna(row['apellido']) else row['username'], 
            axis=1
        )
        
        # Seleccionar y renombrar columnas para mostrar
        df_display = df_display[['fecha_hora', 'usuario', 'tipo_actividad', 'descripcion']]
        df_display.columns = ['Fecha y Hora', 'Usuario', 'Tipo de Actividad', 'Descripción']
        
        # Mostrar tabla de registros
        st.dataframe(df_display, use_container_width=True)
        
        # Se eliminó la sección de gráficos estadísticos según lo solicitado
        
    except Exception as e:
        # Registrar el error en los logs
        error_msg = log_app_error(e, module="activity_logs", function="render_activity_logs")
        st.error(f"Error al cargar los registros de actividad: {str(e)}")