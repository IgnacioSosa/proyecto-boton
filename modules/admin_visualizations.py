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

# Importar uploader y tabla por separado
try:
    from .admin_records import render_records_import
except Exception:
    render_records_import = None

try:
    from .admin_records import render_records_table
except Exception:
    render_records_table = None

def render_unified_records_tab(df, roles_df):
    """Pestaña unificada de Tabla de Registros con selector de departamento y filtros de fecha."""
    st.subheader("📋 Tabla de Registros (Selecciona Departamento)")
    
    # IMPORTAR REGISTROS ARRIBA DE TODO
    if render_records_import:
        render_records_import(None)
        st.divider()
    
    # Fallback: sin departamentos (p. ej., base recién regenerada)
    if roles_df is None or roles_df.empty:
        st.info("No hay departamentos configurados. Agrega departamentos en Gestión > Departamentos.")
        # Mostrar tabla vacía debajo del uploader
        if render_records_table:
            render_records_table(pd.DataFrame(), None)
        else:
            st.subheader("Tabla de Registros")
            st.dataframe(pd.DataFrame(), use_container_width=True)
        return
    
    # Opciones de departamentos
    roles_list = [dict(rol) for _, rol in roles_df.iterrows()]
    
    # Mostrar solo el nombre en el desplegable; devolver el id_rol como valor
    role_ids = [r['id_rol'] for r in roles_list]
    role_name_by_id = {r['id_rol']: r['nombre'] for r in roles_list}
    selected_role_id = st.selectbox(
        "Departamento",
        options=role_ids,
        format_func=lambda rid: role_name_by_id.get(rid, str(rid)),
        key="role_selector_unified",
    )
    
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
            key="filter_type_unified",
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
                key="year_unified",
            )
        with col3:
            selected_month = st.selectbox(
                "Mes",
                options=list(range(1, 13)),
                format_func=lambda x: month_name_es(x),
                index=datetime.now().month - 1,
                key="month_unified",
            )
        custom_month = selected_month
        custom_year = selected_year
    elif filter_type == "custom_range":
        with col2:
            default_start = datetime.now().date().replace(day=1)
            start_date = st.date_input("Desde", value=default_start, key="start_date_unified")
        with col3:
            default_end = datetime.now().date()
            end_date = st.date_input("Hasta", value=default_end, key="end_date_unified")

    # Registros filtrados por departamento y período
    role_df = get_registros_by_rol_with_date_filter(
        selected_role_id, filter_type, custom_month, custom_year, start_date, end_date
    )
    
    # Mostrar la tabla debajo de los filtros
    if render_records_table:
        render_records_table(role_df, selected_role_id)
    else:
        st.subheader("Tabla de Registros")
        st.dataframe(role_df, use_container_width=True)


def render_data_visualization():
    """Renderiza la sección de visualización de datos con pestaña global de registros y métricas por departamento."""
    df = get_registros_dataframe()
    roles_df = get_roles_dataframe(exclude_admin=True, exclude_hidden=True)
    roles_filtrados = roles_df.sort_values('id_rol')

    if len(roles_filtrados) > 0:
        # Primero los departamentos, y al final la pestaña de registros
        tabs = st.tabs([f"📊 {rol['nombre']}" for _, rol in roles_filtrados.iterrows()] + ["📋 Tabla de Registros"])

        # Pestañas por departamento (solo métricas)
        for i, (_, rol) in enumerate(roles_filtrados.iterrows()):
            with tabs[i]:
                render_role_visualizations(df, rol['id_rol'], rol['nombre'])

        # Última pestaña: unificada de registros
        with tabs[len(roles_filtrados)]:
            render_unified_records_tab(df, roles_filtrados)
    else:
        # Sin departamentos: mantener una única pestaña de registros
        tabs = st.tabs(["📋 Tabla de Registros"])
        with tabs[0]:
            render_unified_records_tab(df, roles_filtrados)
    # (Se elimina el st.info() fuera del else que mostraba el mensaje siempre)


def render_role_visualizations(df, rol_id, rol_nombre):
    """Renderiza solo las visualizaciones (sin la subpestaña de Tabla de Registros)."""
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

    # Sin subpestaña de "Tabla de Registros" aquí; solo métricas
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
        st.info(f"No hay datos para mostrar para el departamento {rol_nombre} en {period_text}")
        return

    # Solo cuatro pestañas de métricas (se elimina 'Datos')
    client_tab, task_tab, group_tab, user_tab = st.tabs(
        ["Horas por Cliente", "Tipos de Tarea", "Grupos", "Horas por Usuario"]
    )

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
            fig1 = px.pie(
                horas_por_cliente, 
                names='cliente', 
                values='tiempo', 
                title=titulo_grafico,
                hover_data=['tiempo'],
                labels={'tiempo': 'Horas'}
            )
            fig1.update_traces(textposition='inside', textinfo='percent+label',
                               hovertemplate='<b>%{label}</b><br>Horas: %{value}<br>Porcentaje: %{percent}<extra></extra>')
            fig1.update_layout(showlegend=True, legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.01))
            st.plotly_chart(fig1, use_container_width=True, key=f"client_pie_{rol_id}")
            from .admin_panel import render_client_hours_detail
            render_client_hours_detail(horas_por_cliente)
            if tecnico_seleccionado != 'Todos':
                st.subheader(f"Análisis detallado de {tecnico_seleccionado} por cliente")
                detalle_cliente = df_filtrado.groupby('cliente').agg({
                    'tiempo': ['sum', 'count'],
                    'tipo_tarea': lambda x: ', '.join(x.unique()),
                    'fecha': ['min', 'max'],
                }).round(2)
                detalle_cliente.columns = ['Horas Totales', 'Cantidad de Registros', 'Tipos de Tarea', 'Primera Fecha', 'Última Fecha']
                detalle_cliente = detalle_cliente.reset_index()
                total_horas_tecnico = detalle_cliente['Horas Totales'].sum()
                detalle_cliente['Porcentaje'] = (detalle_cliente['Horas Totales'] / total_horas_tecnico * 100).round(1)
                detalle_cliente = detalle_cliente.sort_values('Horas Totales', ascending=False)
                st.dataframe(detalle_cliente, use_container_width=True)

    # Tipos de Tarea
    with task_tab:
        st.subheader(f"Tipos de Tarea - {rol_nombre}")
        tecnicos_disponibles = ['Todos'] + sorted(role_df['tecnico'].unique().tolist())
        tecnico_seleccionado = st.selectbox(
            "Filtrar por Usuario:",
            options=tecnicos_disponibles,
            key=f"tecnico_filter_tarea_{rol_id}",
        )
        if tecnico_seleccionado == 'Todos':
            df_filtrado = role_df
            titulo_grafico = f'Distribución por Tipo de Tarea - {rol_nombre} (Todos los técnicos)'
        else:
            df_filtrado = role_df[role_df['tecnico'] == tecnico_seleccionado]
            titulo_grafico = f'Distribución por Tipo de Tarea - {tecnico_seleccionado}'
        if df_filtrado.empty:
            st.info(f"No hay datos para el técnico {tecnico_seleccionado} en este período.")
        else:
            horas_por_tipo = df_filtrado.groupby('tipo_tarea')['tiempo'].sum().reset_index()
            fig2 = px.pie(
                horas_por_tipo, 
                names='tipo_tarea', 
                values='tiempo', 
                title=titulo_grafico,
                hover_data=['tiempo'],
                labels={'tiempo': 'Horas'}
            )
            fig2.update_traces(textposition='inside', textinfo='percent',
                               hovertemplate='<b>%{label}</b><br>Horas: %{value}<br>Porcentaje: %{percent}<extra></extra>')
            fig2.update_layout(showlegend=True, legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.01))
            st.plotly_chart(fig2, use_container_width=True, key=f"task_pie_{rol_id}")
            if tecnico_seleccionado == 'Todos':
                horas_por_tipo_sorted = horas_por_tipo.sort_values('tiempo', ascending=False)
                total_horas = horas_por_tipo_sorted['tiempo'].sum()
                horas_por_tipo_sorted['Porcentaje'] = (horas_por_tipo_sorted['tiempo'] / total_horas * 100).round(1)
                horas_por_tipo_sorted.columns = ['Tipo Tarea', 'Horas', 'Porcentaje']
                st.dataframe(horas_por_tipo_sorted, use_container_width=True)
            else:
                st.subheader(f"Detalle de contribuciones de {tecnico_seleccionado}")
                detalle_tipos = df_filtrado.groupby('tipo_tarea').agg({
                    'tiempo': ['sum', 'count'],
                    'cliente': lambda x: ', '.join(sorted(x.unique())),
                })
                detalle_tipos.columns = ['Horas Totales', 'Cantidad de Registros', 'Clientes']
                detalle_tipos = detalle_tipos.reset_index()
                total_horas_tecnico = detalle_tipos['Horas Totales'].sum()
                detalle_tipos['Porcentaje'] = (detalle_tipos['Horas Totales'] / total_horas_tecnico * 100).round(1)
                detalle_tipos = detalle_tipos.sort_values('Horas Totales', ascending=False)
                detalle_tipos.columns = ['Tipo Tarea', 'Horas Totales', 'Cantidad de Registros', 'Clientes', 'Porcentaje']
                st.dataframe(detalle_tipos, use_container_width=True)
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total de Horas", f"{total_horas_tecnico}")
                with col2:
                    st.metric("Tipos de Tarea", len(detalle_tipos))
                with col3:
                    total_registros = detalle_tipos['Cantidad de Registros'].sum()
                    st.metric("Total de Registros", total_registros)

    # Grupos
    with group_tab:
        st.subheader(f"Grupos - {rol_nombre}")
        tecnicos_disponibles = ['Todos'] + sorted(role_df['tecnico'].unique().tolist())
        tecnico_seleccionado = st.selectbox(
            "Filtrar por Usuario:",
            options=tecnicos_disponibles,
            key=f"tecnico_filter_grupo_{rol_id}",
        )
        if tecnico_seleccionado == 'Todos':
            df_filtrado = role_df
            titulo_grafico = f'Distribución por Grupos - {rol_nombre} (Todos los técnicos)'
        else:
            df_filtrado = role_df[role_df['tecnico'] == tecnico_seleccionado]
            titulo_grafico = f'Distribución por Grupos - {tecnico_seleccionado}'
        if df_filtrado.empty:
            st.info(f"No hay datos para el técnico {tecnico_seleccionado} en este período.")
        else:
            try:
                horas_por_grupo = df_filtrado.groupby('grupo')['tiempo'].sum().reset_index()
                fig3 = px.pie(
                    horas_por_grupo, 
                    names='grupo', 
                    values='tiempo', 
                    title=titulo_grafico,
                    hover_data=['tiempo'],
                    labels={'tiempo': 'Horas'}
                )
                fig3.update_traces(textposition='inside', textinfo='percent',
                                   hovertemplate='<b>%{label}</b><br>Horas: %{value}<br>Porcentaje: %{percent}<extra></extra>')
                fig3.update_layout(showlegend=True, legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.01))
                st.plotly_chart(fig3, use_container_width=True, key=f"group_pie_{rol_id}")
                if tecnico_seleccionado == 'Todos':
                    st.subheader("Detalle de horas por grupo")
                    horas_por_grupo_sorted = horas_por_grupo.sort_values('tiempo', ascending=False)
                    total_horas = horas_por_grupo_sorted['tiempo'].sum()
                    horas_por_grupo_sorted['Porcentaje'] = (horas_por_grupo_sorted['tiempo'] / total_horas * 100).round(1)
                    horas_por_grupo_sorted.columns = ['Grupo', 'Horas Totales', 'Porcentaje']
                    st.dataframe(horas_por_grupo_sorted, use_container_width=True)
                else:
                    st.subheader(f"Detalle de contribuciones de {tecnico_seleccionado}")
                    detalle_grupos = df_filtrado.groupby('grupo').agg({
                        'tiempo': ['sum', 'count'],
                        'cliente': lambda x: ', '.join(sorted(x.unique())),
                    })
                    detalle_grupos.columns = ['Horas Totales', 'Cantidad de Registros', 'Clientes']
                    detalle_grupos = detalle_grupos.reset_index()
                    total_horas_tecnico = detalle_grupos['Horas Totales'].sum()
                    detalle_grupos['Porcentaje'] = (detalle_grupos['Horas Totales'] / total_horas_tecnico * 100).round(1)
                    detalle_grupos = detalle_grupos.sort_values('Horas Totales', ascending=False)
                    detalle_grupos.columns = ['Grupo', 'Horas Totales', 'Cantidad de Registros', 'Clientes', 'Porcentaje']
                    st.dataframe(detalle_grupos, use_container_width=True)
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total de Horas", f"{total_horas_tecnico}")
                    with col2:
                        st.metric("Grupos", len(detalle_grupos))
                    with col3:
                        total_registros = detalle_grupos['Cantidad de Registros'].sum()
                        st.metric("Total de Registros", total_registros)
            except Exception:
                st.info("No hay información de grupos disponible en los registros.")

    # Usuario
    with user_tab:
        st.subheader(f"Horas por Usuario - {rol_nombre}")
        horas_por_usuario = role_df.groupby('tecnico')['tiempo'].sum().reset_index().sort_values('tecnico', ascending=True)
        fig4 = px.bar(
            horas_por_usuario, 
            x='tecnico', 
            y='tiempo',
            title=f'Horas por Usuario - {rol_nombre}',
            color='tecnico',
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        fig4.update_layout(
            showlegend=True,
            legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
            xaxis_title="",
            yaxis_title="Horas",
            height=400
        )
        fig4.update_xaxes(tickangle=0)
        st.plotly_chart(fig4, use_container_width=True, key=f"user_bar_{rol_id}")
        st.subheader("Detalle de horas por usuario")
        tabla_usuarios = horas_por_usuario.copy()
        tabla_usuarios.columns = ['Técnico', 'Horas']
        tabla_usuarios['Horas'] = tabla_usuarios['Horas'].apply(lambda x: f"{x:.1f}")
        st.dataframe(tabla_usuarios, use_container_width=True, hide_index=True)
