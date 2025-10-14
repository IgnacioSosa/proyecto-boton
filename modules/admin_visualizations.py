import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

from .database import (
    get_registros_dataframe,
    get_roles_dataframe,
    get_registros_by_rol_with_date_filter,
)
from .utils import month_name_es

# Opcional: si ya extrajiste gestión de registros a admin_records.py
try:
    from .admin_records import render_records_management
except Exception:
    render_records_management = None


def render_data_visualization():
    """Renderiza la sección de visualización de datos organizada por roles"""
    df = get_registros_dataframe()
    roles_df = get_roles_dataframe(exclude_admin=True, exclude_hidden=True)
    roles_filtrados = roles_df.sort_values('id_rol')

    if len(roles_filtrados) > 0:
        role_tabs = st.tabs([f"📊 {rol['nombre']}" for _, rol in roles_filtrados.iterrows()])

        if df.empty:
            for i, (_, rol) in enumerate(roles_filtrados.iterrows()):
                with role_tabs[i]:
                    st.info(f"No hay datos para mostrar para el rol {rol['nombre']}")
                    empty_df = pd.DataFrame()
                    client_tab, task_tab, group_tab, user_tab, data_tab = st.tabs(
                        ["Horas por Cliente", "Tipos de Tarea", "Grupos", "Horas por Usuario", "Tabla de Registros"]
                    )
                    with data_tab:
                        if render_records_management:
                            render_records_management(empty_df, rol['id_rol'])
                        else:
                            st.info("Módulo de gestión de registros no disponible.")
        else:
            for i, (_, rol) in enumerate(roles_filtrados.iterrows()):
                with role_tabs[i]:
                    render_role_visualizations(df, rol['id_rol'], rol['nombre'])
    else:
        st.info("No hay departamentos configurados para visualizar datos")


def render_role_visualizations(df, rol_id, rol_nombre):
    """Renderiza las visualizaciones específicas para un rol"""
    # Controles de filtro
    st.subheader(f"📊 Métricas - {rol_nombre}")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        filter_type = st.selectbox(
            "Filtro de Fecha",
            options=["current_month", "custom_month", "custom_range", "all_time"],
            format_func=lambda x: {
                "current_month": "Mes Actual",
                "custom_month": "Mes Específico",
                "custom_range": "Período de Tiempo",
                "all_time": "Total Acumulado",
            }[x],
            key=f"filter_type_{rol_id}",
        )

    custom_month = None
    custom_year = None
    start_date = None
    end_date = None

    if filter_type == "custom_month":
        with col2:
            current_year = datetime.now().year
            years = list(range(2020, current_year + 2))
            selected_year = st.selectbox(
                "Año",
                options=years,
                index=years.index(current_year) if current_year in years else 0,
                key=f"year_{rol_id}",
            )
        with col3:
            selected_month = st.selectbox(
                "Mes",
                options=list(range(1, 13)),
                format_func=lambda x: month_name_es(x),
                index=datetime.now().month - 1,
                key=f"month_{rol_id}",
            )
        custom_month = selected_month
        custom_year = selected_year
    elif filter_type == "custom_range":
        with col2:
            default_start = datetime.now().date().replace(day=1)
            start_date = st.date_input("Desde", value=default_start, key=f"start_date_{rol_id}")
        with col3:
            default_end = datetime.now().date()
            end_date = st.date_input("Hasta", value=default_end, key=f"end_date_{rol_id}")

    role_df = get_registros_by_rol_with_date_filter(
        rol_id, filter_type, custom_month, custom_year, start_date, end_date
    )

    client_tab, task_tab, group_tab, user_tab, data_tab = st.tabs(
        ["Horas por Cliente", "Tipos de Tarea", "Grupos", "Horas por Usuario", "Tabla de Registros"]
    )

    if role_df.empty:
        period_text = {
            "current_month": "el mes actual",
            "custom_month": f"{month_name_es(custom_month)} {custom_year}" if custom_month and custom_year else "el período seleccionado",
            "custom_range": (
                f"desde {start_date.strftime('%d/%m/%Y')} hasta {end_date.strftime('%d/%m/%Y')}"
                if start_date and end_date else "el período seleccionado"
            ),
            "all_time": "el período total",
        }[filter_type]

        with data_tab:
            st.info(f"No hay datos para mostrar para el departamento {rol_nombre} en {period_text}")
            if render_records_management:
                render_records_management(pd.DataFrame(), rol_id)
        return

    # Cliente
    with client_tab:
        st.subheader(f"Horas por Cliente - {rol_nombre}")
        tecnicos_disponibles = ['Todos'] + sorted(role_df['tecnico'].unique().tolist())
        tecnico_seleccionado = st.selectbox(
            "Filtrar por Usuario:",
            options=tecnicos_disponibles,
            key=f"tecnico_filter_cliente_{rol_id}",
        )

        if tecnico_seleccionado == 'Todos':
            df_filtrado = role_df
            titulo_grafico = f'Distribución por Cliente - {rol_nombre} (Todos los técnicos)'
        else:
            df_filtrado = role_df[role_df['tecnico'] == tecnico_seleccionado]
            titulo_grafico = f'Distribución por Cliente - {tecnico_seleccionado}'

        if df_filtrado.empty:
            st.info(f"No hay datos para el técnico {tecnico_seleccionado} en este período.")
        else:
            horas_por_cliente = df_filtrado.groupby('cliente')['tiempo'].sum().reset_index()
            fig1 = px.pie(horas_por_cliente, names='cliente', values='tiempo', title=titulo_grafico)
            st.plotly_chart(fig1, use_container_width=True, key=f"client_pie_{rol_id}")

            if tecnico_seleccionado != 'Todos':
                st.subheader(f"Análisis detallado de {tecnico_seleccionado} por cliente")
                detalle_cliente = df_filtrado.groupby('cliente').agg({
                    'tiempo': ['sum', 'count'],
                    'tipo_tarea': lambda x: ', '.join(x.unique()),
                    'fecha': ['min', 'max'],
                }).round(2)
                detalle_cliente.columns = [
                    'Horas Totales', 'Cantidad de Registros', 'Tipos de Tarea', 'Primera Fecha', 'Última Fecha'
                ]
                detalle_cliente = detalle_cliente.reset_index()
                total_horas_tecnico = detalle_cliente['Horas Totales'].sum()
                detalle_cliente['Porcentaje'] = (detalle_cliente['Horas Totales'] / total_horas_tecnico * 100).round(1)
                detalle_cliente = detalle_cliente.sort_values('Horas Totales', ascending=False)
                st.dataframe(detalle_cliente, use_container_width=True)

    # Tipos de Tarea
    with task_tab:
        st.subheader(f"Tipos de Tarea - {rol_nombre}")
        tipos_por_usuario = role_df.groupby(['tecnico', 'tipo_tarea']).agg({'tiempo': 'sum'}).reset_index()
        fig2 = px.bar(tipos_por_usuario, x='tipo_tarea', y='tiempo', color='tecnico', title='Distribución de tipos de tarea por usuario')
        st.plotly_chart(fig2, use_container_width=True, key=f"task_bar_{rol_id}")

    # Grupos
    with group_tab:
        st.subheader(f"Grupos - {rol_nombre}")
        try:
            grupos_df = role_df.groupby(['grupo']).agg({'tiempo': 'sum'}).reset_index()
            fig3 = px.bar(grupos_df, x='grupo', y='tiempo', title='Horas por grupo')
            st.plotly_chart(fig3, use_container_width=True, key=f"group_bar_{rol_id}")
        except Exception:
            st.info("No hay información de grupos disponible en los registros.")

    # Usuario
    with user_tab:
        st.subheader(f"Horas por Usuario - {rol_nombre}")
        horas_por_usuario = role_df.groupby('tecnico')['tiempo'].sum().reset_index()
        fig4 = px.bar(horas_por_usuario, x='tecnico', y='tiempo', title='Horas totales por usuario')
        st.plotly_chart(fig4, use_container_width=True, key=f"user_bar_{rol_id}")

    # Datos
    with data_tab:
        # Agregar gestión de registros
        if render_records_management:
            render_records_management(role_df, rol_id)
        else:
            st.subheader("Tabla de Registros")
            st.dataframe(role_df, use_container_width=True)