import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

from .database import (
    get_registros_dataframe,
    get_roles_dataframe,
    get_registros_by_rol_with_date_filter,
    get_all_proyectos,
    get_users_by_rol,
    get_clientes_dataframe,
    get_marcas_dataframe,
    get_contactos_por_cliente,
    get_contactos_por_marca,
    get_contacto,
    update_contacto,
    add_contacto,
)
from .ui_components import inject_project_card_css

try:
    from .commercial_projects import get_proyecto, render_project_read_view, render_project_edit_form
except Exception:
    get_proyecto = None
    render_project_read_view = None
    render_project_edit_form = None
from .utils import month_name_es
from .config import PROYECTO_ESTADOS
from .contacts_shared import render_shared_contacts_management

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
    # IMPORTAR REGISTROS ARRIBA DE TODO
    if render_records_import:
        render_records_import(None)
        st.divider()
    else:
        st.error("❌ La función render_records_import no está disponible. Revisa los logs de la consola para más detalles.")
    # Encabezado único (se elimina "(Selecciona Departamento)")
    # Encabezado único
    st.subheader("📋 Tabla de Registros")
    
    # Fallback: sin departamentos (p. ej., base recién regenerada)
    if roles_df is None or roles_df.empty:
        st.info("No hay departamentos configurados. Agrega departamentos en Gestión > Departamentos.")
        if render_records_table:
            render_records_table(pd.DataFrame(), None, show_header=False)
        else:
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
    # Mostrar la tabla debajo de los filtros (sin duplicar título)
    if render_records_table:
        render_records_table(role_df, selected_role_id, show_header=False)
    else:
        st.dataframe(role_df, use_container_width=True)


def render_data_visualization():
    """Renderiza la sección de visualización de datos con pestaña global de registros y métricas por departamento."""
    df = get_registros_dataframe()
    roles_df = get_roles_dataframe(exclude_admin=True, exclude_hidden=True)
    
    # Filtrar roles que comienzan con 'adm_'
    if not roles_df.empty:
        roles_df = roles_df[~roles_df['nombre'].str.lower().str.startswith('adm_')]
        
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
    if rol_nombre == "Dpto Comercial":
        return render_commercial_department_dashboard(rol_id)
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
            
            # Crear versión corta del nombre para mejor visualización en el gráfico
            # "OSPIM - Obra Social..." -> "OSPIM"
            horas_por_cliente['cliente_corto'] = horas_por_cliente['cliente'].apply(
                lambda x: x.split(' - ')[0].strip() if isinstance(x, str) and ' - ' in x else str(x)
            )
            
            fig1 = px.pie(
                horas_por_cliente, 
                names='cliente_corto', 
                values='tiempo', 
                title=titulo_grafico,
                hover_data=['cliente'], # Mantenemos el nombre completo en los datos
                labels={'tiempo': 'Horas', 'cliente_corto': 'Cliente', 'cliente': 'Nombre Completo'}
            )
            fig1.update_traces(textposition='inside', textinfo='percent+label',
                               hovertemplate='<b>%{customdata[0]}</b><br>Horas: %{value}<br>Porcentaje: %{percent}<extra></extra>')
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
        
        # Función para acortar nombres
        def shorten_user_name(name):
            if not isinstance(name, str):
                return str(name)
            parts = name.strip().split()
            if len(parts) == 2:
                # Nombre + Apellido
                return f"{parts[0]} {parts[1]}"
            elif len(parts) >= 3:
                # Asumimos formato: Nombre + SegundoNombre + Apellido (+ SegundoApellido)
                # El usuario quiere "Daniel Vieira" de "Daniel alejandro Vieira maia" -> parts[0] + parts[2]
                return f"{parts[0]} {parts[2]}"
            return name

        horas_por_usuario['tecnico_corto'] = horas_por_usuario['tecnico'].apply(shorten_user_name)

        fig4 = px.bar(
            horas_por_usuario, 
            x='tecnico_corto', 
            y='tiempo',
            title=f'Horas por Usuario - {rol_nombre}',
            color='tecnico',
            color_discrete_sequence=px.colors.qualitative.Set3,
            hover_data=['tecnico'],
            labels={'tiempo': 'Horas', 'tecnico_corto': 'Usuario', 'tecnico': 'Nombre Completo'}
        )
        fig4.update_layout(
            showlegend=True,
            legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
            xaxis_title="",
            yaxis_title="Horas",
            height=400
        )
        # Ajuste: etiquetas horizontales por pedido del usuario
        fig4.update_xaxes(tickangle=0)
        st.plotly_chart(fig4, use_container_width=True, key=f"user_bar_{rol_id}")
        st.subheader("Detalle de horas por usuario")
        # Seleccionamos solo las columnas originales para la tabla
        tabla_usuarios = horas_por_usuario[['tecnico', 'tiempo']].copy()
        tabla_usuarios.columns = ['Técnico', 'Horas']
        tabla_usuarios['Horas'] = tabla_usuarios['Horas'].apply(lambda x: f"{x:.1f}")
        st.dataframe(tabla_usuarios, use_container_width=True, hide_index=True)

def render_commercial_department_dashboard(rol_id: int):
    st.subheader("📊 Dashboard Comercial")
    
    # --- FILTRO DE FECHA ---
    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    with col_f1:
        filter_type = st.selectbox(
            "Filtro de Fecha",
            options=["current_month", "custom_month", "custom_range", "all_time"],
            format_func=lambda x: {
                "current_month": "Mes Actual",
                "custom_month": "Mes Específico",
                "custom_range": "Período de Tiempo",
                "all_time": "Total Acumulado",
            }[x],
            key=f"comm_filter_type_{rol_id}",
        )

    custom_month = None
    custom_year = None
    start_date = None
    end_date = None

    if filter_type == "custom_month":
        with col_f2:
            current_year = datetime.now().year
            years = list(range(2020, current_year + 2))
            selected_year = st.selectbox(
                "Año",
                options=years,
                index=years.index(current_year) if current_year in years else 0,
                key=f"comm_year_{rol_id}",
            )
        with col_f3:
            selected_month = st.selectbox(
                "Mes",
                options=list(range(1, 13)),
                format_func=lambda x: month_name_es(x),
                index=datetime.now().month - 1,
                key=f"comm_month_{rol_id}",
            )
        custom_month = selected_month
        custom_year = selected_year
    elif filter_type == "custom_range":
        with col_f2:
            default_start = datetime.now().date().replace(day=1)
            start_date = st.date_input("Desde", value=default_start, key=f"comm_start_{rol_id}")
        with col_f3:
            default_end = datetime.now().date()
            end_date = st.date_input("Hasta", value=default_end, key=f"comm_end_{rol_id}")

    # Obtener vendedores (usuarios con rol comercial y adm_comercial si aplica)
    roles_df_all = get_roles_dataframe(exclude_hidden=False)
    target_role_ids = [int(rol_id)]
    
    if not roles_df_all.empty:
        # Buscar nombre del rol actual
        curr_role = roles_df_all[roles_df_all['id_rol'] == int(rol_id)]
        if not curr_role.empty and curr_role.iloc[0]['nombre'] == "Dpto Comercial":
            # Buscar id de adm_comercial
            adm_role = roles_df_all[roles_df_all['nombre'] == "adm_comercial"]
            if not adm_role.empty:
                target_role_ids.append(int(adm_role.iloc[0]['id_rol']))
    
    users_dfs = []
    for rid in target_role_ids:
        udf = get_users_by_rol(rid, exclude_hidden=False)
        if not udf.empty:
            users_dfs.append(udf)
            
    if users_dfs:
        users_df = pd.concat(users_dfs).drop_duplicates(subset=['id'])
    else:
        users_df = pd.DataFrame()
        
    users_df = users_df.copy()
    if not users_df.empty:
        users_df["nombre_completo"] = users_df.apply(lambda r: f"{(r['nombre'] or '').strip()} {(r['apellido'] or '').strip()}".strip(), axis=1)
    seller_map = {int(r["id"]): r.get("nombre_completo") for _, r in users_df.iterrows()} if not users_df.empty else {}
    # Proyectos
    all_df = get_all_proyectos(filter_user_ids=list(seller_map.keys()) if seller_map else None)
    all_df = all_df.copy()
    # Normalizaciones y columnas derivadas
    all_df["estado_norm"] = all_df.get("estado", pd.Series(dtype=str)).fillna("").str.lower()
    def _estado_disp(s):
        base = str(s or "").strip()
        mapping = {
            "prospecto":"Prospecto",
            "presupuestado":"Presupuestado",
            "negociación":"Negociación",
            "negociacion":"Negociación",
            "objeción":"Objeción",
            "objecion":"Objeción",
            "ganado":"Ganado",
            "perdido":"Perdido",
        }
        return mapping.get(all_df["estado_norm"], base) if isinstance(s, str) else base
    all_df["estado_disp"] = all_df.get("estado", pd.Series(dtype=str)).fillna("")
    all_df["seller"] = all_df.get("owner_user_id", pd.Series(dtype=int)).apply(lambda x: seller_map.get(int(x)) if pd.notna(x) else "Sin asignar")
    all_df["cliente_nombre"] = all_df.get("cliente_nombre", pd.Series(dtype=str)).fillna("")
    all_df["valor"] = pd.to_numeric(all_df.get("valor", pd.Series(dtype=float)), errors="coerce")
    all_df["moneda"] = all_df.get("moneda", pd.Series(dtype=str)).fillna("").str.upper()
    all_df["fecha_cierre_dt"] = pd.to_datetime(all_df.get("fecha_cierre"), errors="coerce")
    
    # --- APLICAR LOGICA FILTRO DE FECHA ---
    if filter_type == "current_month":
        now = datetime.now()
        all_df = all_df[
            (all_df["fecha_cierre_dt"].dt.year == now.year) & 
            (all_df["fecha_cierre_dt"].dt.month == now.month)
        ]
    elif filter_type == "custom_month":
        all_df = all_df[
            (all_df["fecha_cierre_dt"].dt.year == custom_year) & 
            (all_df["fecha_cierre_dt"].dt.month == custom_month)
        ]
    elif filter_type == "custom_range" and start_date and end_date:
        all_df = all_df[
            (all_df["fecha_cierre_dt"].dt.date >= start_date) & 
            (all_df["fecha_cierre_dt"].dt.date <= end_date)
        ]

    # Pestañas principales
    tab_vencimientos, tab_registros = st.tabs(["📅 Dashboard", "📝 Registro de tratos"])
    
    # --- PESTAÑA 1: Vencimientos (Tarjetas) ---
    with tab_vencimientos:
        # Estilos CSS para las tarjetas
        st.markdown("""
        <style>
        .project-card {
            width: 100%;
            height: 200px;
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
            background: #1f2937;
            border: 1px solid #374151;
            color: #e5e7eb;
            padding: 20px 24px;
            border-radius: 14px;
            box-sizing: border-box;
            box-shadow: 0 4px 10px rgba(0,0,0,0.25);
            margin-bottom: 32px;
        }
        .project-info { display: flex; flex-direction: column; height: 100%; justify-content: flex-start; }
        .project-title {
            display: flex; align-items: center; gap: 10px;
            font-size: 22px; font-weight: 700;
        }
        .dot-left { width: 10px; height: 10px; border-radius: 50%; background-color: #6b7280; }
        .dot-left.prospecto { background-color: #60a5fa; }
        .dot-left.presupuestado { background-color: #34d399; }
        .dot-left.negociación { background-color: #8b5cf6; }
        .dot-left.objeción { background-color: #fbbf24; }
        .dot-left.ganado { background-color: #065f46; }
        .dot-left.perdido { background-color: #ef4444; }

        .status-text { font-weight: 600; }
        .status-text.prospecto { color: #60a5fa; }
        .status-text.presupuestado { color: #34d399; }
        .status-text.negociación { color: #8b5cf6; }
        .status-text.objeción { color: #fbbf24; }
        .status-text.ganado { color: #065f46; }
        .status-text.perdido { color: #ef4444; }

        .project-sub { margin-top: 4px; color: #9ca3af; font-size: 16px; }
        .project-sub2 { margin-top: 2px; color: #9ca3af; font-size: 15px; }
        </style>
        """, unsafe_allow_html=True)

        # --- MÉTRICAS RESUMEN (Filtradas por Fecha) ---
        m_total = len(all_df)
        m_ganados = int((all_df["estado"].fillna("").str.lower() == "ganado").sum())
        m_perdidos = int((all_df["estado"].fillna("").str.lower() == "perdido").sum())
        # Activos son todos los que no son ganados ni perdidos
        m_activos_df = all_df[~all_df["estado"].fillna("").str.lower().isin(["ganado", "perdido"])]
        m_activos = len(m_activos_df)
        
        # Monto Total (Suma de valor de todos los proyectos filtrados por fecha, o solo activos? 
        # El usuario dijo "Monto total" y en su ejemplo coincidía con activos, pero "Monto total" suele ser todo.
        # Sin embargo, en ventas, sumar ganados + perdidos + activos es raro. 
        # Pero si filtro por "Cierre en Enero", quiero saber el volumen total que cierra en Enero.
        # Sumaré el valor de TODO lo que está en el filtro de fecha actual.
        m_ars = all_df[all_df["moneda"] == "ARS"]["valor"].sum()
        m_usd = all_df[all_df["moneda"] == "USD"]["valor"].sum()
        
        mk1, mk2, mk3, mk4 = st.columns(4)
        mk1.metric("Proyectos", m_total)
        mk2.metric("Activos", m_activos)
        mk3.metric("Ganados", m_ganados)
        mk4.metric("Perdidos", m_perdidos)
        
        st.markdown("") # Espacio vertical
        
        # Montos en fila separada para asegurar espacio completo
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            st.metric("Monto Total (ARS)", f"${m_ars:,.0f}".replace(",", "."))
        with m_col2:
            if m_usd > 0:
                st.metric("Monto Total (USD)", f"${m_usd:,.0f}".replace(",", "."))
        
        st.divider()

        st.caption("Proyectos ordenados por fecha de cierre próxima.")
        
        # Filtros básicos para esta vista también
        c1, c2 = st.columns([1, 1])
        with c1:
            vend_venc = st.selectbox("Vendedor", ["Todos"] + (sorted([v for v in set(seller_map.values()) if v]) if seller_map else []), key=f"venc_vend_{rol_id}")
        with c2:
            # Filtro de estado convertido a selectbox con opción "Todos"
            est_venc_options = ["Todos"] + PROYECTO_ESTADOS
            # Preseleccionar "Todos" o mantener lógica anterior si se prefiere
            est_venc = st.selectbox("Estado", options=est_venc_options, index=0, key=f"venc_est_{rol_id}")
            
        df_venc = all_df.copy()
        if vend_venc != "Todos":
            df_venc = df_venc[df_venc["seller"] == vend_venc]
        
        # Lógica de filtrado para selectbox
        if est_venc != "Todos":
            df_venc = df_venc[df_venc["estado"].fillna("").str.lower() == est_venc.lower()]
        else:
            # Si es "Todos", opcionalmente podríamos filtrar ganados/perdidos para que no saturen, 
            # pero el usuario pidió "Todos". Si se quiere ocultar finalizados por defecto, se requeriría lógica extra.
            # Por ahora "Todos" muestra todo.
            pass
            
        # Calcular días restantes y ordenar
        today_norm = pd.Timestamp.now().normalize()
        df_venc["dias_restantes"] = (df_venc["fecha_cierre_dt"].dt.normalize() - today_norm).dt.days
        # Ordenar: primero los vencidos (negativos), luego los próximos (positivos pequeños), luego lejanos, luego NaT
        df_venc = df_venc.sort_values(by="dias_restantes", ascending=True, na_position="last")
        
        if df_venc.empty:
            st.info("No hay proyectos que coincidan con los filtros.")
        else:
            # Pagination logic
            page_size = 6
            total_items = len(df_venc)
            page_key = f"adm_venc_page_{rol_id}"
            page = int(st.session_state.get(page_key, 1) or 1)
            total_pages = max((total_items + page_size - 1) // page_size, 1)
            
            if page > total_pages: page = total_pages
            if page < 1: page = 1
            st.session_state[page_key] = page
            
            start = (page - 1) * page_size
            end = start + page_size
            df_page = df_venc.iloc[start:end]
            count_text = f"Mostrando elementos {start+1}-{min(end, total_items)} de {total_items}"

            # Renderizar tarjetas
            # Obtener parámetros actuales para preservarlos en los formularios
            current_params = st.query_params.to_dict()
            
            # Helper para clases CSS
            def _get_estado_class(s):
                s = str(s or "").lower().strip()
                mapping = {
                    "prospecto": "prospecto",
                    "presupuestado": "presupuestado",
                    "negociación": "negociación",
                    "negociacion": "negociación",
                    "objeción": "objeción",
                    "objecion": "objeción",
                    "ganado": "ganado",
                    "perdido": "perdido"
                }
                return mapping.get(s, s.replace(" ", "-"))

            cols_per_row = 3
            cols = st.columns(cols_per_row)
            for idx, row in enumerate(df_page.to_dict('records')):
                with cols[idx % cols_per_row]:
                    # Datos del proyecto
                    pid = row.get('id')
                    titulo = row.get('titulo', 'Sin título')
                    cliente = row.get('cliente_nombre', 'Sin cliente')
                    seller = row.get('seller', 'Sin asignar')
                    moneda = row.get('moneda', '')
                    valor = row.get('valor', 0)
                    estado_texto = row.get('estado', '')
                    estado_class = _get_estado_class(estado_texto)
                    
                    # Cálculo de vencimiento
                    dias = row.get("dias_restantes")
                    deadline_html = ""
                    
                    if pd.notna(dias):
                        dias = int(dias)
                        alert_color = ""
                        alert_bg = ""
                        alert_text = ""
                        
                        if dias < 0:
                            alert_color = "#ef4444"
                            alert_bg = "rgba(239, 68, 68, 0.2)"
                            alert_text = f"Vencido {abs(dias)}d"
                        elif dias == 0:
                            alert_color = "#ef4444"
                            alert_bg = "rgba(239, 68, 68, 0.2)"
                            alert_text = "Vence hoy"
                        elif dias <= 7:
                            alert_color = "#f97316"
                            alert_bg = "rgba(249, 115, 22, 0.2)"
                            alert_text = f"{dias}d"
                        else:
                            alert_color = "#22c55e"
                            alert_bg = "rgba(34, 197, 94, 0.2)"
                            alert_text = f"{dias}d"
                            
                        if alert_text:
                            deadline_html = f'''
                            <div style="display:flex; align-items:center; gap:6px; background:{alert_bg}; padding:2px 8px; border-radius:999px; border:1px solid {alert_color}; white-space:nowrap;">
                                <div style="width:6px; height:6px; border-radius:50%; background-color:{alert_color};"></div>
                                <span style="color:{alert_color}; font-size:12px; font-weight:600;">{alert_text}</span>
                            </div>
                            '''
                            deadline_html = " ".join(deadline_html.split())
                    
                    # Tarjeta HTML estática (sin formulario)
                    st.markdown(f"""
                    <div class="project-card">
                        <div class="project-info">
                            <div class="project-title">
                                <span class="dot-left {estado_class}"></span>
                                <span>{titulo}</span>
                            </div>
                            <div class="project-sub">
                                🏢 {cliente} • 👤 {seller}
                            </div>
                            <div class="project-sub2">
                                💰 {moneda} {valor:,.0f} • <span class="status-text {estado_class}">{estado_texto}</span>
                            </div>
                        </div>
                        {deadline_html}
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
            
            # Pagination controls: Text Left, Buttons Right
            col_text, col_spacer, col_prev, col_sep, col_next = st.columns([3, 3, 1, 0.5, 1])
            
            with col_text:
                st.markdown(f"<div style='display:flex; align-items:center; height:100%; color:#888;'>{count_text}</div>", unsafe_allow_html=True)
            with col_prev:
                if st.button("Anterior", disabled=(page <= 1), key=f"venc_prev_{rol_id}", use_container_width=True):
                    st.session_state[page_key] = page - 1
                    st.rerun()
            with col_next:
                if st.button("Siguiente", disabled=(page >= total_pages), key=f"venc_next_{rol_id}", use_container_width=True):
                    st.session_state[page_key] = page + 1
                    st.rerun()

    # --- PESTAÑA 2: Registro de tratos ---
    with tab_registros:
        # Sub-pestañas
        subtab_trato, subtab_monto = st.tabs(["Por trato", "Por monto"])

        def render_subtab_content(mode="count"):
             # Filtro de Estado
             estados_opt = ["Todos"] + PROYECTO_ESTADOS
             key_suffix = f"{mode}_{rol_id}"
             estado_sel = st.selectbox("Estado", options=estados_opt, key=f"rt_estado_{key_suffix}")
             
             # Filtrar DF (all_df ya tiene filtro de fecha global)
             df_filtered = all_df.copy()
             if estado_sel != "Todos":
                 df_filtered = df_filtered[df_filtered["estado"].fillna("").str.lower() == estado_sel.lower()]
             
             # Agrupar por vendedor
             if mode == "count":
                 grouped = df_filtered.groupby("seller").size().reset_index(name="cantidad")
                 grouped = grouped[grouped["cantidad"] > 0]
                 
                 if not grouped.empty:
                     fig = px.bar(grouped, x="seller", y="cantidad", title="Tratos por Vendedor", text="cantidad")
                     st.plotly_chart(fig, use_container_width=True)
                 else:
                     st.info("No hay datos para mostrar.")
                     
             elif mode == "amount":
                 moneda_sel = st.selectbox("Moneda", ["ARS", "USD"], key=f"rt_moneda_{key_suffix}")
                 df_moneda = df_filtered[df_filtered["moneda"] == moneda_sel]
                 grouped = df_moneda.groupby("seller")["valor"].sum().reset_index(name="monto")
                 grouped = grouped[grouped["monto"] > 0]
                 
                 if not grouped.empty:
                     fig = px.bar(grouped, x="seller", y="monto", title=f"Monto por Vendedor ({moneda_sel})", text="monto")
                     fig.update_traces(texttemplate='%{text:.2s}', textposition='outside')
                     st.plotly_chart(fig, use_container_width=True)
                 else:
                     st.info(f"No hay montos en {moneda_sel}.")
            
             # Tabla exportable
             st.markdown("### Registros Detallados")
             cols_to_show = ["nombre", "cliente_nombre", "seller", "estado", "moneda", "valor", "fecha_cierre"]
             cols = [c for c in cols_to_show if c in df_filtered.columns]
             st.dataframe(df_filtered[cols], use_container_width=True)

        with subtab_trato:
            render_subtab_content(mode="count")
            
        with subtab_monto:
            render_subtab_content(mode="amount")

def render_adm_contacts(rol_id):
    """
    Renderiza la gestión de contactos para el administrador usando la lógica compartida.
    """
    if inject_project_card_css:
        inject_project_card_css()
    render_shared_contacts_management(username=st.session_state.get('username', ''), is_admin=True, key_prefix=f"adm_{rol_id}_")
