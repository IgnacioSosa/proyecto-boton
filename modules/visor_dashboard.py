import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import time
import calendar
from .utils import month_name_es, get_general_alerts
# Actualizar las importaciones al principio del archivo
from .database import (
    get_connection, get_registros_dataframe, get_registros_dataframe_with_date_filter,
    get_tecnicos_dataframe, get_clientes_dataframe, get_tipos_dataframe,
    get_modalidades_dataframe, get_roles_dataframe, get_users_dataframe,
    get_grupos_dataframe, get_grupos_puntajes_dataframe, get_grupo_puntaje_by_nombre,
    set_grupo_puntaje_by_nombre, get_clientes_puntajes_dataframe, get_cliente_puntaje_by_nombre,
    set_cliente_puntaje_by_nombre, get_tipos_dataframe_with_roles, get_tipos_puntajes_dataframe,
    get_tipo_puntaje_by_descripcion, set_tipo_puntaje_by_descripcion,
    get_all_proyectos, get_users_by_rol,
    get_vacaciones_activas, get_user_vacaciones, save_vacaciones, delete_vacaciones, update_vacaciones,
    get_upcoming_vacaciones,
    get_feriados_dataframe, add_feriado, toggle_feriado, delete_feriado
)
from .utils import show_success_message, render_excel_uploader, safe_rerun
from .config import SYSTEM_ROLES, PROYECTO_ESTADOS
from .admin_planning import render_planning_management, cached_get_weekly_modalities_by_rol
from .admin_visualizations import render_role_visualizations
from .commercial_projects import render_project_detail_screen, render_create_project
from .admin_brands import render_brand_management
from .admin_clients import render_client_management, render_client_crud_management
from .database import get_cliente_solicitudes_df, approve_cliente_solicitud, reject_cliente_solicitud, check_client_duplicate

def render_visor_dashboard(user_id, nombre_completo_usuario):
    """Renderiza el dashboard completo del hipervisor con navegación programable"""
    st.header("Panel de Hipervisor")

    main_options = ["📊 Visualización de Datos", "⚙️ Gestión", "📅 Planificación Semanal", "📅 Feriados"]

    if "visor_main_tab" not in st.session_state:
        st.session_state["visor_main_tab"] = main_options[0]

    if st.session_state["visor_main_tab"] not in main_options:
        st.session_state["visor_main_tab"] = main_options[0]

    selected_main = st.segmented_control(
        "Secciones Hipervisor",
        main_options,
        key="visor_main_tab",
        label_visibility="collapsed",
    )
    st.write("")

    if selected_main == "📊 Visualización de Datos":
        tab_puntajes_cliente, tab_puntajes_tecnico, tab_eficiencia = st.tabs(
            ["🏢 Puntajes por Cliente", "👨‍💻 Puntajes por Técnico", "⚖️ Eficiencia por Cliente"]
        )

        with tab_puntajes_cliente:
            render_score_calculation()

        with tab_puntajes_tecnico:
            render_score_calculation_by_technician()

        with tab_eficiencia:
            render_efficiency_analysis()

    elif selected_main == "⚙️ Gestión":
        render_records_management(user_id)

    elif selected_main == "📅 Planificación Semanal":
        render_planning_management(restricted_role_name="Dpto Tecnico")

    elif selected_main == "📅 Feriados":
        render_feriados_admin_tab()

# Función para calcular y visualizar puntajes por cliente
def render_score_calculation():
    """Renderiza la sección de cálculo y visualización de puntajes por cliente"""
    st.subheader("Cálculo de Puntajes por Cliente")
    
    # Agregar controles de filtro de fecha
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        filter_type = st.selectbox(
            "Filtro de Fecha",
            options=["current_month", "custom_month", "all_time"],
            format_func=lambda x: {
                "current_month": "Mes Actual",
                "custom_month": "Mes Específico", 
                "all_time": "Total Acumulado"
            }[x],
            key="filter_type_cliente"
        )
    
    custom_month = None
    custom_year = None
    
    if filter_type == "custom_month":
        with col2:
            current_year = datetime.now().year
            years = list(range(2020, current_year + 2))
            selected_year = st.selectbox(
                "Año", 
                options=years, 
                index=years.index(current_year) if current_year in years else 0,
                key="year_cliente"
            )
            
        with col3:
            months = [(i, month_name_es(i)) for i in range(1, 13)]
            selected_month = st.selectbox(
                "Mes",
                options=[m[0] for m in months],
                format_func=lambda x: month_name_es(x),
                index=datetime.now().month - 1,
                key="month_cliente"
            )
            
        custom_month = selected_month
        custom_year = selected_year
    
    # Obtener los datos necesarios con filtro de fecha
    registros_df = get_registros_dataframe_with_date_filter(filter_type, custom_month, custom_year)
    
    if registros_df.empty:
        period_text = {
            "current_month": "el mes actual",
            "custom_month": f"{month_name_es(custom_month)} {custom_year}" if custom_month and custom_year else "el período seleccionado",
            "all_time": "el período total"
        }[filter_type]
        st.info(f"No hay datos para mostrar en {period_text}")
        return
    
    # El resto de la función se mantiene igual
    # Obtener los puntajes de tipos de tarea
    tipos_puntajes_df = get_tipos_puntajes_dataframe()
    tipos_dict = dict(zip(tipos_puntajes_df['descripcion'], tipos_puntajes_df['puntaje']))
    
    # Obtener los puntajes de clientes
    clientes_puntajes_df = get_clientes_puntajes_dataframe()
    clientes_dict = dict(zip(clientes_puntajes_df['nombre'], clientes_puntajes_df['puntaje']))
    
    # Obtener los puntajes de grupos
    grupos_puntajes_df = get_grupos_puntajes_dataframe()
    grupos_dict = dict(zip(grupos_puntajes_df['nombre'], grupos_puntajes_df['puntaje']))
    
    # Crear un DataFrame para almacenar los resultados
    resultados = []
    
    # Calcular puntajes para cada registro según la fórmula PT=(T×C×N)×H
    for _, registro in registros_df.iterrows():
        tipo_tarea = registro['tipo_tarea']
        cliente = registro['cliente']
        grupo = registro['grupo']
        horas = registro['tiempo']
        
        # Obtener los puntajes (T, C, N) con valor mínimo de 1 para evitar puntajes cero
        puntaje_tipo = max(1, tipos_dict.get(tipo_tarea, 0))  # T
        puntaje_cliente = max(1, clientes_dict.get(cliente, 0))  # C
        puntaje_grupo = max(1, grupos_dict.get(grupo, 0))  # N
    
        # Aplicar la fórmula PT=(T×C×N)×H directamente sin raíz cúbica
        puntaje_total = (puntaje_tipo * puntaje_cliente * puntaje_grupo) * horas
        
        # Agregar al resultado
        resultados.append({
            'cliente': cliente,
            'puntaje': puntaje_total,
            'registro_id': registro.get('id', 0)
        })
    
    # Convertir a DataFrame
    resultados_df = pd.DataFrame(resultados)
    
    # Agrupar por cliente y sumar los puntajes
    if not resultados_df.empty:
        # Calcular puntaje total por cliente
        puntajes_por_cliente = resultados_df.groupby('cliente')['puntaje'].sum().reset_index()
        
        # Calcular cantidad de registros por cliente para el promedio
        conteo_por_cliente = resultados_df.groupby('cliente').size().reset_index(name='cantidad_registros')
        
        # Unir los dataframes
        puntajes_por_cliente = pd.merge(puntajes_por_cliente, conteo_por_cliente, on='cliente')
        
        # Calcular promedio
        puntajes_por_cliente['promedio'] = puntajes_por_cliente['puntaje'] / puntajes_por_cliente['cantidad_registros']
        
        # Redondear los puntajes al entero más cercano
        puntajes_por_cliente['puntaje'] = puntajes_por_cliente['puntaje'].round().astype(int)
        puntajes_por_cliente['promedio'] = puntajes_por_cliente['promedio'].round().astype(int)
        
        if not puntajes_por_cliente.empty:
            # Crear gráfico de barras para el promedio
            st.subheader("Visualización de Promedio de Puntajes por Cliente")
            fig = px.bar(
                puntajes_por_cliente,
                x='cliente',
                y='promedio',
                labels={'cliente': 'Cliente', 'promedio': 'Puntaje Promedio'},
                title="Promedio de Puntajes por Cliente",
                color='promedio',
                color_continuous_scale='Viridis'
            )
            
            # Personalizar el gráfico
            fig.update_layout(
                xaxis_title="Cliente",
                yaxis_title="Puntaje Promedio",
                height=500,
                font=dict(color="var(--text-color)"),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)"
            )
            
            # Mostrar el gráfico
            st.plotly_chart(fig, use_container_width=True)
            
            # Mostrar tabla de resultados
            st.subheader("Puntajes Calculados por Cliente")
            st.dataframe(
                puntajes_por_cliente.rename(columns={
                    'cliente': 'Cliente',
                    'puntaje': 'Puntaje Total',
                    'cantidad_registros': 'Cantidad de Registros',
                    'promedio': 'Promedio'
                }),
                use_container_width=True
            )
        else:
            st.info("No hay clientes con puntajes calculados")
    else:
        st.info("No hay datos suficientes para calcular puntajes")

# Función para calcular y visualizar puntajes por técnico
def render_score_calculation_by_technician():
    """Renderiza la sección de cálculo y visualización de puntajes por técnico"""
    st.subheader("Cálculo de Puntajes por Técnico")
    
    # Agregar controles de filtro de fecha
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        filter_type = st.selectbox(
            "Filtro de Fecha",
            options=["current_month", "custom_month", "all_time"],
            format_func=lambda x: {
                "current_month": "Mes Actual",
                "custom_month": "Mes Específico", 
                "all_time": "Total Acumulado"
            }[x],
            key="filter_type_tecnico"
        )
    
    custom_month = None
    custom_year = None
    
    if filter_type == "custom_month":
        with col2:
            current_year = datetime.now().year
            years = list(range(2020, current_year + 2))
            selected_year = st.selectbox(
                "Año", 
                options=years, 
                index=years.index(current_year) if current_year in years else 0,
                key="year_tecnico"
            )
            
        with col3:
            months = [(i, month_name_es(i)) for i in range(1, 13)]
            selected_month = st.selectbox(
                "Mes",
                options=[m[0] for m in months],
                format_func=lambda x: month_name_es(x),
                index=datetime.now().month - 1,
                key="month_tecnico"
            )
            
        custom_month = selected_month
        custom_year = selected_year
    
    # Obtener los datos necesarios con filtro de fecha
    registros_df = get_registros_dataframe_with_date_filter(filter_type, custom_month, custom_year)
    
    if registros_df.empty:
        period_text = {
            "current_month": "el mes actual",
            "custom_month": f"{calendar.month_name[custom_month]} {custom_year}" if custom_month and custom_year else "el período seleccionado",
            "all_time": "el período total"
        }[filter_type]
        st.info(f"No hay datos para mostrar en {period_text}")
        return
    
    # El resto de la función se mantiene igual
    # Obtener los puntajes de tipos de tarea
    tipos_puntajes_df = get_tipos_puntajes_dataframe()
    tipos_dict = dict(zip(tipos_puntajes_df['descripcion'], tipos_puntajes_df['puntaje']))
    
    # Obtener los puntajes de clientes
    clientes_puntajes_df = get_clientes_puntajes_dataframe()
    clientes_dict = dict(zip(clientes_puntajes_df['nombre'], clientes_puntajes_df['puntaje']))
    
    # Obtener los puntajes de grupos
    grupos_puntajes_df = get_grupos_puntajes_dataframe()
    grupos_dict = dict(zip(grupos_puntajes_df['nombre'], grupos_puntajes_df['puntaje']))
    
    # Crear un DataFrame para almacenar los resultados
    resultados = []
    
    # DataFrame para diagnóstico de puntajes cero
    diagnostico_ceros = []
    
    # Calcular puntajes para cada registro según la fórmula PT=(T×C×N)×H
    for _, registro in registros_df.iterrows():
        tipo_tarea = registro['tipo_tarea']
        cliente = registro['cliente']
        grupo = registro['grupo']
        tecnico = registro['tecnico']
        horas = registro['tiempo']
        
        # Obtener los puntajes originales (T, C, N)
        puntaje_tipo_orig = tipos_dict.get(tipo_tarea, 0)  # T
        puntaje_cliente_orig = clientes_dict.get(cliente, 0)  # C
        puntaje_grupo_orig = grupos_dict.get(grupo, 0)  # N
        
        # Verificar si algún puntaje es cero para diagnóstico
        if puntaje_tipo_orig == 0 or puntaje_cliente_orig == 0 or puntaje_grupo_orig == 0:
            diagnostico_ceros.append({
                'tecnico': tecnico,
                'tipo_tarea': tipo_tarea,
                'cliente': cliente,
                'grupo': grupo,
                'puntaje_tipo': puntaje_tipo_orig,
                'puntaje_cliente': puntaje_cliente_orig,
                'puntaje_grupo': puntaje_grupo_orig,
                'horas': horas
            })
        
        # Aplicar valor mínimo de 1 para evitar puntajes cero
        puntaje_tipo = max(1, puntaje_tipo_orig)  # T
        puntaje_cliente = max(1, puntaje_cliente_orig)  # C
        puntaje_grupo = max(1, puntaje_grupo_orig)  # N
    
        # Aplicar la fórmula PT=(T×C×N)×H directamente sin raíz cúbica
        puntaje_total = (puntaje_tipo * puntaje_cliente * puntaje_grupo) * horas
        
        # Agregar al resultado
        resultados.append({
            'tecnico': tecnico,
            'puntaje': puntaje_total,
            'registro_id': registro.get('id', 0)
        })
    
    # Convertir a DataFrame
    resultados_df = pd.DataFrame(resultados)
    
    # Agrupar por técnico y sumar los puntajes
    if not resultados_df.empty:
        # Calcular puntaje total por técnico
        puntajes_por_tecnico = resultados_df.groupby('tecnico')['puntaje'].sum().reset_index()
        
        # Calcular cantidad de registros por técnico para el promedio
        conteo_por_tecnico = resultados_df.groupby('tecnico').size().reset_index(name='cantidad_registros')
        
        # Unir los dataframes
        puntajes_por_tecnico = pd.merge(puntajes_por_tecnico, conteo_por_tecnico, on='tecnico')
        
        # Calcular promedio
        puntajes_por_tecnico['promedio'] = puntajes_por_tecnico['puntaje'] / puntajes_por_tecnico['cantidad_registros']
        
        # Redondear los puntajes al entero más cercano
        puntajes_por_tecnico['puntaje'] = puntajes_por_tecnico['puntaje'].round().astype(int)
        puntajes_por_tecnico['promedio'] = puntajes_por_tecnico['promedio'].round().astype(int)
        
        if not puntajes_por_tecnico.empty:
            # Crear gráfico de barras para el promedio
            st.subheader("Visualización de Promedio de Puntajes por Técnico")
            fig = px.bar(
                puntajes_por_tecnico,
                x='tecnico',
                y='promedio',
                labels={'tecnico': 'Técnico', 'promedio': 'Puntaje Promedio'},
                title="Promedio de Puntajes por Técnico",
                color='promedio',
                color_continuous_scale='Viridis'
            )
            
            # Personalizar el gráfico
            fig.update_layout(
                xaxis_title="Técnico",
                yaxis_title="Puntaje Promedio",
                height=500,
                font=dict(color="var(--text-color)"),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)"
            )
            
            # Mostrar el gráfico
            st.plotly_chart(fig, use_container_width=True)
            
            # Mostrar tabla de resultados
            st.subheader("Puntajes Calculados por Técnico")
            st.dataframe(
                puntajes_por_tecnico.rename(columns={
                    'tecnico': 'Técnico',
                    'puntaje': 'Puntaje Total',
                    'cantidad_registros': 'Cantidad de Registros',
                    'promedio': 'Promedio'
                }),
                use_container_width=True
            )
            
            # Mostrar diagnóstico de puntajes cero si hay datos
            if diagnostico_ceros:
                with st.expander("Diagnóstico de Puntajes Cero", expanded=False):
                    st.subheader("Registros con Factores de Puntaje Cero")
                    diagnostico_df = pd.DataFrame(diagnostico_ceros)
                    st.dataframe(diagnostico_df, use_container_width=True)
                    
                    # Análisis de factores que causan puntajes cero
                    st.subheader("Análisis de Factores que Causan Puntajes Cero")
                    
                    # Contar ocurrencias de cada factor
                    factor_tipo = (diagnostico_df['puntaje_tipo'] == 0).sum()
                    factor_cliente = (diagnostico_df['puntaje_cliente'] == 0).sum()
                    factor_grupo = (diagnostico_df['puntaje_grupo'] == 0).sum()
                    
                    # Crear DataFrame para visualización
                    factores_df = pd.DataFrame({
                        'Factor': ['Tipo de Tarea', 'Cliente', 'Grupo'],
                        'Ocurrencias': [factor_tipo, factor_cliente, factor_grupo]
                    })
                    
                    # Mostrar gráfico de barras
                    fig_factores = px.bar(
                        factores_df,
                        x='Factor',
                        y='Ocurrencias',
                        title="Factores que Causan Puntajes Cero",
                        color='Ocurrencias',
                        color_continuous_scale='Reds'
                    )
                    
                    fig_factores.update_layout(
                        font=dict(color="var(--text-color)"),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)"
                    )
                    
                    st.plotly_chart(fig_factores, use_container_width=True)
        else:
            st.info("No hay técnicos con puntajes calculados")
    else:
        st.info("No hay datos suficientes para calcular puntajes")

def render_records_management(user_id):
    """Renderiza la sección de gestión para hipervisores"""
    st.subheader("Gestión de Registros")
    
    # Crear pestañas para la sección de gestión
    tab_usuarios, tab_clientes, tab_grupo, tab_tipos = st.tabs(["👥 Usuarios", "🏢 Clientes", "👪 Grupo", "📋 Tipos de Tarea"])
    
    with tab_usuarios:
        # Obtener todos los usuarios excepto los ocultos
        users_df = get_users_dataframe()
        
        # Filtrar usuarios que no tengan rol_nombre 'sin_rol' (que serían los ocultos)
        users_df = users_df[users_df['rol_nombre'] != SYSTEM_ROLES['SIN_ROL']]
        
        # Mostrar la tabla de usuarios
        st.subheader("Lista de Usuarios")
        
        # Seleccionar y reordenar columnas para mostrar (eliminando 'id', 'is_admin' y 'is_active')
        columns_to_display = ['username', 'nombre', 'apellido', 'email', 'rol_nombre']
        users_df = users_df[columns_to_display]
        
        # Renombrar columnas para mejor visualización
        users_df = users_df.rename(columns={
            'username': 'Usuario',
            'nombre': 'Nombre',
            'apellido': 'Apellido',
            'email': 'Email',
            'rol_nombre': 'Departamento'
        })
        
        # Mostrar la tabla
        st.dataframe(users_df, use_container_width=True)
    
    with tab_clientes:
        # Obtener todos los clientes con sus puntajes desde la base de datos
        clientes_df = get_clientes_puntajes_dataframe(only_active=True)
        
        # Mostrar la tabla de clientes con puntajes
        st.subheader("Lista de Clientes")
        st.dataframe(
            clientes_df.rename(columns={
                'nombre': 'Nombre',
                'puntaje': 'Puntaje'
            }),
            use_container_width=True
        )
        
        # Agregar sección para asignar puntajes mediante desplegables
        st.subheader("Asignar Puntajes a Clientes")
        
        # Crear columnas para organizar los desplegables
        col1, col2 = st.columns(2)
        
        with col1:
            # Desplegable para seleccionar el cliente
            cliente_seleccionado = st.selectbox(
                "Seleccione un cliente",
                options=clientes_df['nombre'].tolist(),
                key="cliente_select"
            )
        
        with col2:
            # Obtener el puntaje actual del cliente seleccionado
            puntaje_actual = get_cliente_puntaje_by_nombre(cliente_seleccionado)
            
            # Desplegable para asignar puntaje 
            puntaje_asignado = st.selectbox(
                "Asigne un puntaje",
                options=list(range(6)),
                key="puntaje_cliente_select",
                index=puntaje_actual  # Valor actual desde la base de datos
            )
        
        # Botón para guardar el puntaje asignado
        if st.button("Guardar Puntaje", key="guardar_puntaje_cliente"):
            # Guardar el puntaje en la base de datos
            if set_cliente_puntaje_by_nombre(cliente_seleccionado, puntaje_asignado):
                # Mostrar mensaje de éxito
                st.success(f"Puntaje {puntaje_asignado} asignado al cliente {cliente_seleccionado}")
                # Recargar la página para actualizar la tabla
                safe_rerun()
            else:
                st.error(f"Error al guardar el puntaje para el cliente {cliente_seleccionado}")
    
    with tab_grupo:
        # Obtener todos los grupos con sus puntajes desde la base de datos
        grupos_df = get_grupos_puntajes_dataframe()
        
        # Seleccionar columnas excluyendo 'id_grupo'
        grupos_df = grupos_df[['nombre', 'roles_asignados', 'descripcion', 'puntaje']]
        
        # Mostrar la tabla de grupos con puntajes
        st.subheader("Lista de Grupos")
        st.dataframe(
            grupos_df.rename(columns={
                'nombre': 'Nombre',
                'roles_asignados': 'Departamentos Asignados',
                'descripcion': 'Descripción',
                'puntaje': 'Puntaje'
            }),
            use_container_width=True
        )
        
        # Agregar sección para asignar puntajes mediante desplegables
        st.subheader("Asignar Puntajes a Grupos")
        
        # Crear columnas para organizar los desplegables
        col1, col2 = st.columns(2)
        
        with col1:
            # Desplegable para seleccionar el grupo
            grupo_seleccionado = st.selectbox(
                "Seleccione un grupo",
                options=grupos_df['nombre'].tolist(),
                key="grupo_select"
            )
        
        with col2:
            # Obtener el puntaje actual del grupo seleccionado
            puntaje_actual = get_grupo_puntaje_by_nombre(grupo_seleccionado)
            
            # Desplegable para asignar puntaje 
            puntaje_asignado = st.selectbox(
                "Asigne un puntaje",
                options=list(range(6)),
                key="puntaje_select",
                index=puntaje_actual  # Valor actual desde la base de datos
            )
        
        # Botón para guardar el puntaje asignado
        if st.button("Guardar Puntaje", key="guardar_puntaje"):
            # Guardar el puntaje en la base de datos
            if set_grupo_puntaje_by_nombre(grupo_seleccionado, puntaje_asignado):
                # Mostrar mensaje de éxito
                st.success(f"Puntaje {puntaje_asignado} asignado al grupo {grupo_seleccionado}")
                # Recargar la página para actualizar la tabla
                safe_rerun()
            else:
                st.error(f"Error al guardar el puntaje para el grupo {grupo_seleccionado}")
    
    # Modificar la sección de la pestaña "Tipos de Tarea"
    with tab_tipos:
        # Obtener todos los tipos de tarea con sus puntajes desde la base de datos
        tipos_df = get_tipos_puntajes_dataframe()
        
        # Mostrar la tabla de tipos de tarea con puntajes
        st.subheader("Lista de Tipos de Tarea")
        st.dataframe(
            tipos_df.rename(columns={
                'descripcion': 'Descripción',
                'roles_asociados': 'Departamentos Asociados',
                'puntaje': 'Puntaje'
            }),
            use_container_width=True
        )
        
        # Agregar sección para asignar puntajes mediante desplegables
        st.subheader("Asignar Puntajes a Tipos de Tarea")
        
        # Crear columnas para organizar los desplegables
        col1, col2 = st.columns(2)
        
        with col1:
            # Desplegable para seleccionar el tipo de tarea
            tipo_seleccionado = st.selectbox(
                "Seleccione un tipo de tarea",
                options=tipos_df['descripcion'].tolist(),
                key="tipo_select"
            )
        
        with col2:
            # Obtener el puntaje actual del tipo de tarea seleccionado
            puntaje_actual = get_tipo_puntaje_by_descripcion(tipo_seleccionado)
            
            # Desplegable para asignar puntaje 
            puntaje_asignado = st.selectbox(
                "Asigne un puntaje",
                options=list(range(6)),
                key="puntaje_tipo_select",
                index=puntaje_actual  # Valor actual desde la base de datos
            )
        
        # Botón para guardar el puntaje asignado
        if st.button("Guardar Puntaje", key="guardar_puntaje_tipo"):
            # Guardar el puntaje en la base de datos
            if set_tipo_puntaje_by_descripcion(tipo_seleccionado, puntaje_asignado):
                # Mostrar mensaje de éxito
                st.success(f"Puntaje {puntaje_asignado} asignado al tipo de tarea {tipo_seleccionado}")
                # Recargar la página para actualizar la tabla
                safe_rerun()
            else:
                st.error(f"Error al guardar el puntaje para el tipo de tarea {tipo_seleccionado}")

# Función para calcular y visualizar la eficiencia por cliente
def render_efficiency_analysis():
    """Renderiza la sección de análisis de eficiencia por cliente"""
    st.subheader("Análisis de Eficiencia por Cliente")
    
    # Agregar controles de filtro de fecha
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        filter_type = st.selectbox(
            "Filtro de Fecha",
            options=["current_month", "custom_month", "all_time"],
            format_func=lambda x: {
                "current_month": "Mes Actual",
                "custom_month": "Mes Específico", 
                "all_time": "Total Acumulado"
            }[x],
            key="filter_type_eficiencia"
        )
    
    custom_month = None
    custom_year = None
    
    if filter_type == "custom_month":
        with col2:
            current_year = datetime.now().year
            years = list(range(2020, current_year + 2))
            selected_year = st.selectbox(
                "Año", 
                options=years, 
                index=years.index(current_year) if current_year in years else 0,
                key="year_eficiencia"
            )
            
        with col3:
            months = [(i, month_name_es(i)) for i in range(1, 13)]
            selected_month = st.selectbox(
                "Mes",
                options=[m[0] for m in months],
                format_func=lambda x: month_name_es(x),
                index=datetime.now().month - 1,
                key="month_eficiencia"
            )
            
        custom_month = selected_month
        custom_year = selected_year
    
    # Obtener los datos necesarios con filtro de fecha
    registros_df = get_registros_dataframe_with_date_filter(filter_type, custom_month, custom_year)
    
    if registros_df.empty:
        period_text = {
            "current_month": "el mes actual",
            "custom_month": f"{month_name_es(custom_month)} {custom_year}" if custom_month and custom_year else "el período seleccionado",
            "all_time": "el período total"
        }[filter_type]
        st.info(f"No hay datos para mostrar en {period_text}")
        return
    
    # Obtener los puntajes de tipos de tarea
    tipos_puntajes_df = get_tipos_puntajes_dataframe()
    tipos_dict = dict(zip(tipos_puntajes_df['descripcion'], tipos_puntajes_df['puntaje']))
    
    # Obtener los puntajes de clientes
    clientes_puntajes_df = get_clientes_puntajes_dataframe()
    clientes_dict = dict(zip(clientes_puntajes_df['nombre'], clientes_puntajes_df['puntaje']))
    
    # Obtener los puntajes de grupos
    grupos_puntajes_df = get_grupos_puntajes_dataframe()
    grupos_dict = dict(zip(grupos_puntajes_df['nombre'], grupos_puntajes_df['puntaje']))
    
    # Calcular eficiencia para cada cliente
    # Eficiencia (Rc) = Valor del Cliente / Horas Invertidas
    # Valor del Cliente = Suma de (T x N x H) para todos los registros de ese cliente
    # T = Puntaje del tipo de tarea
    # N = Puntaje del grupo
    # H = Horas
    
    resultados_eficiencia = []
    
    # Agrupar registros por cliente
    for cliente, grupo_registros in registros_df.groupby('cliente'):
        # Calcular valor total del cliente
        valor_total = 0
        horas_totales = 0
        
        for _, registro in grupo_registros.iterrows():
            tipo_tarea = registro['tipo_tarea']
            grupo = registro['grupo']
            horas = registro['tiempo']
            
            # Obtener puntajes (mínimo 1)
            puntaje_tipo = max(1, tipos_dict.get(tipo_tarea, 0))  # T
            puntaje_grupo = max(1, grupos_dict.get(grupo, 0))  # N
            
            # Calcular valor del registro: (T x N) x H
            # Nota: No incluimos el puntaje del cliente (C) en el cálculo del valor
            # porque queremos comparar este valor con las horas invertidas
            valor_registro = (puntaje_tipo * puntaje_grupo) * horas
            
            valor_total += valor_registro
            horas_totales += horas
        
        # Calcular relación Rc = Valor / Horas
        relacion = valor_total / horas_totales if horas_totales > 0 else 0
        
        resultados_eficiencia.append({
            'cliente': cliente,
            'horas_totales': horas_totales,
            'puntaje': valor_total,
            'relacion_horas_valor': relacion
        })
    
    # Convertir a DataFrame
    eficiencia_df = pd.DataFrame(resultados_eficiencia)
    
    if eficiencia_df.empty:
        st.info("No hay datos suficientes para calcular la eficiencia")
        return
        
    # Calcular el umbral beta
    # beta = Promedio de los puntajes de clientes asignados por la dirección
    puntajes_asignados = list(clientes_dict.values())
    beta = sum(puntajes_asignados) / len(puntajes_asignados) if puntajes_asignados else 0
    
    st.info(f"Umbral de eficiencia (β): {beta:.2f} (Promedio de puntajes de clientes)")
    
    # Identificar clientes que exceden el umbral (Rc > beta)
    # Según la lógica descrita: "Si Rc > β, el cliente está consumiendo más recursos de los que su valor justifica"
    clientes_excedidos = eficiencia_df[eficiencia_df['relacion_horas_valor'] > beta].copy()
    
    # Ordenar por relación de mayor a menor
    clientes_excedidos = clientes_excedidos.sort_values('relacion_horas_valor', ascending=False)
    
    # Visualización gráfica
    st.subheader("Gráfico de Eficiencia por Cliente")
    
    # Ordenar el dataframe completo para el gráfico
    chart_df = eficiencia_df.sort_values('relacion_horas_valor', ascending=False)
    
    # Crear gráfico de barras
    fig = px.bar(
        chart_df,
        x='cliente',
        y='relacion_horas_valor',
        title="Relación Valor/Horas por Cliente (Rc)",
        labels={'cliente': 'Cliente', 'relacion_horas_valor': 'Relación (Rc)'},
        color='relacion_horas_valor',
        color_continuous_scale='RdYlGn_r'  # Rojo para valores altos (ineficientes), Verde para bajos
    )
    
    # Agregar línea de umbral
    fig.update_layout(
        font=dict(color="var(--text-color)"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        shapes=[
            dict(
                type="line",
                y0=beta,
                y1=beta,
                x0=-0.5,
                x1=len(chart_df)-0.5,
                line=dict(
                    color="orange",
                    width=2,
                    dash="dash",
                )
            )
        ],
        annotations=[
            dict(
                x=len(chart_df)-1,
                y=beta,
                text=f"Umbral β = {beta:.2f}",
                showarrow=True,
                arrowhead=1,
                ax=0,
                ay=-20
            )
        ]
    )
    
    # Agregar línea horizontal para el umbral
    fig.add_shape(
        type="line",
        x0=-0.5,
        y0=beta,
        x1=len(chart_df)-0.5,
        y1=beta,
        line=dict(color="orange", width=2, dash="dash")
    )
    
    # Mostrar el gráfico
    st.plotly_chart(fig, use_container_width=True)
    
    # Mostrar tabla de clientes que exceden el umbral
    if not clientes_excedidos.empty:
        st.subheader("Clientes que exceden el umbral de eficiencia")
        
        # Preparar DataFrame para visualización
        display_df = clientes_excedidos[['cliente', 'horas_totales', 'puntaje', 'relacion_horas_valor']].copy()
        display_df.rename(columns={
            'cliente': 'Cliente',
            'horas_totales': 'Horas Totales',
            'puntaje': 'Valor del Cliente',
            'relacion_horas_valor': 'Relación (Rc)'
        }, inplace=True)
        
        # Formatear la relación con 2 decimales
        display_df['Relación (Rc)'] = display_df['Relación (Rc)'].round(2)
        
        # Mostrar tabla con resaltado
        st.dataframe(display_df, use_container_width=True)
    else:
        st.success(f"✅ Todos los clientes están dentro del umbral de eficiencia (Rc ≤ {beta})")
    
    # Mostrar tabla completa de todos los clientes
    st.subheader("Análisis completo de eficiencia por cliente")
    
    # Preparar DataFrame para visualización
    display_all_df = eficiencia_df[['cliente', 'horas_totales', 'puntaje', 'relacion_horas_valor']].copy()
    display_all_df.rename(columns={
        'cliente': 'Cliente',
        'horas_totales': 'Horas Totales',
        'puntaje': 'Valor del Cliente',
        'relacion_horas_valor': 'Relación (Rc)'
    }, inplace=True)
    
    # Formatear la relación con 2 decimales
    display_all_df['Relación (Rc)'] = display_all_df['Relación (Rc)'].round(2)
    
    # Ordenar por relación de mayor a menor
    display_all_df = display_all_df.sort_values('Relación (Rc)', ascending=False)
    
    # Mostrar tabla
    st.dataframe(display_all_df, use_container_width=True)


def get_technical_alerts_data():
    """Obtiene alertas de técnicos con carga horaria incompleta"""
    conn = get_connection()
    alerts = {} # {technician_name: [days]}
    
    try:
        c = conn.cursor()
        # 1. Obtener IDs de roles técnicos (busca 'tecnico' insensible a mayúsculas)
        c.execute("SELECT id_rol FROM roles WHERE LOWER(nombre) LIKE '%tecnico%' AND LOWER(nombre) != 'adm_tecnico'")
        roles = c.fetchall()
        
        if not roles:
            return {}
            
        role_ids = [r[0] for r in roles]
        
        # 2. Obtener usuarios activos con esos roles
        if not role_ids:
            return {}
            
        placeholders = ','.join(['%s'] * len(role_ids))
        c.execute(f"""
            SELECT id, nombre, apellido, username 
            FROM usuarios 
            WHERE rol_id IN ({placeholders}) AND is_active = true
        """, tuple(role_ids))
        
        users = c.fetchall() # list of (id, nombre, apellido, username)
        
        if not users:
            return {}
            
        # 3. Obtener registros del mes actual para estos usuarios
        now = datetime.now()
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59)
        
        user_ids = [u[0] for u in users]
        if not user_ids:
            return {}
            
        user_placeholders = ','.join(['%s'] * len(user_ids))
        
        c.execute(f"""
            SELECT usuario_id, fecha, tiempo
            FROM registros
            WHERE usuario_id IN ({user_placeholders})
        """, tuple(user_ids))
        
        regs = c.fetchall() # list of (usuario_id, fecha, tiempo)
        
        # Organizar registros por usuario
        regs_by_user = {}
        for uid, fecha, tiempo in regs:
            if uid not in regs_by_user:
                regs_by_user[uid] = []
            
            # Asegurar fecha como date object
            fecha_obj = None
            if isinstance(fecha, str):
                # Intentar varios formatos comunes
                formats = ['%d/%m/%y', '%d/%m/%Y', '%Y-%m-%d']
                for fmt in formats:
                    try:
                        fecha_obj = datetime.strptime(fecha, fmt).date()
                        break
                    except ValueError:
                        continue
                if fecha_obj is None:
                    # Fallback pandas
                    try:
                        fecha_obj = pd.to_datetime(fecha, dayfirst=True).date()
                    except:
                        continue
            elif isinstance(fecha, datetime):
                fecha_obj = fecha.date()
            else:
                fecha_obj = fecha # asume date object
            
            if fecha_obj:
                regs_by_user[uid].append({'fecha': fecha_obj, 'tiempo': float(tiempo)})
            
        # 4. Verificar días incompletos para cada usuario
        for uid, nombre, apellido, username in users:
            full_name = f"{nombre or ''} {apellido or ''}".strip()
            if not full_name:
                full_name = username
                
            user_alerts = []
            current = start_date
            
            user_regs = regs_by_user.get(uid, [])
            
            while current <= end_date:
                # Solo Lunes a Viernes (0-4)
                if current.weekday() < 5:
                    day_hours = 0
                    current_date = current.date()
                    
                    for r in user_regs:
                        if r['fecha'] == current_date:
                            day_hours += r['tiempo']
                    
                    if day_hours < 4:
                        date_str = current.strftime("%d/%m")
                        status = "Sin carga" if day_hours == 0 else f"{day_hours}hs"
                        user_alerts.append(f"{date_str} ({status})")
                        
                current += timedelta(days=1)
            
            if user_alerts:
                alerts[full_name] = user_alerts
                
    except Exception as e:
        print(f"Error getting technical alerts: {e}")
        pass
    finally:
        conn.close()
        
    return alerts

def render_admin_vacaciones_tab():
    """Renderiza la pestaña de gestión de licencias para administradores"""
    st.header("Gestión de Licencias (Admin)")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("🏖️ Quién está de licencia")
        try:
            df_vacaciones = get_vacaciones_activas()
            if not df_vacaciones.empty:
                df_display = df_vacaciones.copy()
                if 'tipo' not in df_display.columns:
                    df_display['tipo'] = 'Vacaciones'
                df_display['Periodo'] = df_display.apply(
                    lambda x: f"{x['fecha_inicio']}" if str(x['fecha_inicio']) == str(x['fecha_fin']) else f"{x['fecha_inicio']} al {x['fecha_fin']}", 
                    axis=1
                )
                st.dataframe(
                    df_display[['nombre', 'apellido', 'tipo', 'Periodo']],
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.info("No hay nadie de licencia actualmente.")
        except Exception as e:
            st.error(f"Error cargando lista de licencias: {e}")

        st.markdown("---")
        st.subheader("🗓️ Próximas Licencias")
        try:
            df_upcoming = get_upcoming_vacaciones()
            if not df_upcoming.empty:
                df_upcoming['Usuario'] = df_upcoming.apply(lambda x: f"{x['nombre']} {x['apellido']}".strip(), axis=1)
                df_upcoming['Tipo'] = df_upcoming['tipo'].fillna('Vacaciones')
                df_upcoming['Fechas'] = df_upcoming.apply(
                    lambda x: f"{x['fecha_inicio']}" if str(x['fecha_inicio']) == str(x['fecha_fin']) else f"{x['fecha_inicio']} al {x['fecha_fin']}", 
                    axis=1
                )
                
                st.dataframe(
                    df_upcoming[['Usuario', 'Tipo', 'Fechas']],
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.info("No hay licencias programadas próximamente.")
        except Exception as e:
            st.error(f"Error cargando próximas licencias: {e}")
    
    with col2:
        st.subheader("✈️ Asignar Licencia")
        st.write("Selecciona un técnico para establecer su periodo de licencia.")
        
        users_df = get_users_dataframe()
        if not users_df.empty:
            users_df = users_df[users_df['is_active'] == True]
            users_df['nombre_completo'] = users_df.apply(lambda x: f"{x['nombre']} {x['apellido']}".strip(), axis=1)
            users_df = users_df.sort_values('nombre_completo')
            
            user_options = {row['id']: row['nombre_completo'] for _, row in users_df.iterrows()}
            selected_user_id = st.selectbox("Seleccionar Usuario", options=list(user_options.keys()), format_func=lambda x: user_options[x])
            
            if selected_user_id:
                tipo_ausencia = st.selectbox("Tipo de Licencia", ["Vacaciones", "Licencia", "Dia de Cumpleaños"], key=f"tipo_sel_{selected_user_id}")
                
                with st.form("admin_vacaciones_form"):
                    st.write(f"Configurando **{tipo_ausencia}** para: **{user_options[selected_user_id]}**")
                    
                    if tipo_ausencia == "Dia de Cumpleaños":
                        col_d1, _ = st.columns(2)
                        with col_d1:
                            start_date = st.date_input("Fecha (1 día)", min_value=datetime.today(), key=f"adm_vac_start_bd_{selected_user_id}")
                        end_date = start_date
                    else:
                        col_d1, col_d2 = st.columns(2)
                        with col_d1:
                            start_date = st.date_input("Fecha Inicio", min_value=datetime.today(), key=f"adm_vac_start_{selected_user_id}")
                        with col_d2:
                            # Remove dynamic min_value dependency on start_date inside form
                            end_date = st.date_input("Fecha Fin", min_value=datetime.today(), key=f"adm_vac_end_{selected_user_id}")
                        
                    submit = st.form_submit_button("Asignar", type="primary")
                    
                    if submit:
                        if start_date > end_date:
                            st.error("La fecha de fin debe ser posterior a la de inicio.")
                        else:
                            try:
                                save_vacaciones(selected_user_id, start_date, end_date, tipo=tipo_ausencia)
                                # Limpiar caché de planificación para que se reflejen los cambios
                                cached_get_weekly_modalities_by_rol.clear()
                                from .utils import show_success_message
                                show_success_message(f"¡{tipo_ausencia} asignada para {user_options[selected_user_id]}! ({start_date} al {end_date})", 1)
                                safe_rerun()
                            except Exception as e:
                                st.error(f"Error guardando licencia: {e}")
                
                st.markdown("---")
                
                col_h, col_y = st.columns([3, 1])
                with col_h:
                    st.subheader(f"📅 Periodos de {user_options[selected_user_id]}")
                
                current_year = datetime.now().year
                years = list(range(2024, current_year + 3))
                if current_year not in years: years.append(current_year)
                years.sort()

                with col_y:
                    sel_year = st.selectbox(
                        "Año", 
                        options=years, 
                        index=years.index(current_year) if current_year in years else 0, 
                        key=f"vac_adm_year_sel_{selected_user_id}"
                    )

                try:
                    user_vacs = get_user_vacaciones(selected_user_id, year=sel_year)
                    if not user_vacs.empty:
                        for _, row in user_vacs.iterrows():
                            # Determine type for label (backward compat)
                            row_tipo = row.get('tipo', 'Vacaciones')
                            if not row_tipo: row_tipo = 'Vacaciones'
                            
                            with st.expander(f"{row_tipo}: {row['fecha_inicio']} - {row['fecha_fin']}"):
                                # Edit Mode Logic
                                edit_key = f"edit_mode_vac_admin_{row['id']}"
                                is_editing = st.session_state.get(edit_key, False)
                                
                                if is_editing:
                                    # Note: can't put selectbox inside form nicely if we want dynamic UI.
                                    # But for edit, maybe we keep it simple or use 2 steps.
                                    # Let's try to put type selector inside form for simplicity, or just above it.
                                    # Putting it above form in expander works.
                                    
                                    edit_tipo_key = f"edit_tipo_sel_admin_{row['id']}"
                                    current_tipo = st.selectbox("Tipo", ["Vacaciones", "Licencia", "Dia de Cumpleaños"], 
                                                              index=["Vacaciones", "Licencia", "Dia de Cumpleaños"].index(row_tipo) if row_tipo in ["Vacaciones", "Licencia", "Dia de Cumpleaños"] else 0,
                                                              key=edit_tipo_key)
                                    
                                    with st.form(key=f"edit_vac_form_admin_{row['id']}"):
                                        st.write("Editar fechas:")
                                        # Parse dates safely
                                        try:
                                            d_start = pd.to_datetime(row['fecha_inicio']).date()
                                        except:
                                            d_start = datetime.today().date()
                                            
                                        try:
                                            d_end = pd.to_datetime(row['fecha_fin']).date()
                                        except:
                                            d_end = datetime.today().date()
                                        
                                        if current_tipo == "Dia de Cumpleaños":
                                             n_start = st.date_input("Fecha", value=d_start)
                                             n_end = n_start
                                        else:
                                            c_e1, c_e2 = st.columns(2)
                                            with c_e1:
                                                n_start = st.date_input("Inicio", value=d_start)
                                            with c_e2:
                                                n_end = st.date_input("Fin", value=d_end, min_value=n_start)
                                        
                                        col_act_e1, col_act_e2 = st.columns(2)
                                        with col_act_e1:
                                            if st.form_submit_button("💾 Guardar"):
                                                if n_start > n_end:
                                                    st.error("Fecha fin debe ser posterior a inicio")
                                                else:
                                                    if update_vacaciones(row['id'], n_start, n_end, tipo=current_tipo):
                                                        # Limpiar caché de planificación
                                                        cached_get_weekly_modalities_by_rol.clear()
                                                        from .utils import show_success_message
                                                        show_success_message("Actualizado", 0.5)
                                                        st.session_state[edit_key] = False
                                                        safe_rerun()
                                                    else:
                                                        st.error("Error actualizando")
                                        with col_act_e2:
                                            if st.form_submit_button("❌ Cancelar"):
                                                st.session_state[edit_key] = False
                                                safe_rerun()
                                else:
                                    col_btns1, col_btns2 = st.columns([1, 4])
                                    with col_btns1:
                                        if st.button("✏️", key=f"btn_edit_vac_admin_{row['id']}"):
                                            st.session_state[edit_key] = True
                                            safe_rerun()
                                    with col_btns2:
                                        if st.button("🗑️ Eliminar periodo", key=f"del_vac_admin_{row['id']}"):
                                            if delete_vacaciones(row['id']):
                                                # Limpiar caché de planificación
                                                cached_get_weekly_modalities_by_rol.clear()
                                                from .utils import show_success_message
                                                show_success_message("Periodo eliminado.", 1)
                                                safe_rerun()
                                            else:
                                                st.error("Error al eliminar.")
                    else:
                        st.info("Este usuario no tiene vacaciones registradas.")
                except Exception as e:
                    st.error(f"Error cargando historial: {e}")
        else:
            st.warning("No hay usuarios activos disponibles.")

def render_visor_only_dashboard():
    """Renderiza el dashboard del visor con visualización y planificación"""

    alerts = get_technical_alerts_data()
    has_alerts = len(alerts) > 0

    col_head, col_icon = st.columns([0.88, 0.12])
    with col_head:
        st.header("Panel de Visor")

    with col_icon:
        st.write("")
        try:
            wrapper_class = "has-alerts" if has_alerts else "no-alerts"
            st.markdown(f"<div class='notif-trigger {wrapper_class}'>", unsafe_allow_html=True)
            icon_str = "🔔" if has_alerts else "🔕"
            with st.popover(icon_str, use_container_width=False):
                st.markdown("### ⚠️ Técnicos con carga incompleta")
                st.caption("Umbral mínimo: 4 horas (lun-vie) - Mes en curso")
                if not has_alerts:
                    st.info("Todo el equipo al día. ¡Excelente!")
                else:
                    for tech, days in alerts.items():
                        with st.expander(f"**{tech}** ({len(days)})"):
                            for day in days:
                                st.markdown(f"- {day}")
            st.markdown("</div>", unsafe_allow_html=True)
        except Exception:
            if st.button("🔔"):
                st.info(f"Alertas: {len(alerts)} técnicos")

    if not st.session_state.get("alerts_shown_adm_tech", False):
        if has_alerts:
            count = len(alerts)
            msg = f"Atención: {count} técnicos tienen días con carga incompleta."
            st.toast(msg, icon="⚠️")
        st.session_state.alerts_shown_adm_tech = True

    main_options = ["📊 Visualización de Datos", "📅 Planificación Semanal", "🌴 Licencias", "📅 Feriados"]

    if "visor_only_tab" not in st.session_state:
        st.session_state["visor_only_tab"] = main_options[0]

    if st.session_state["visor_only_tab"] not in main_options:
        st.session_state["visor_only_tab"] = main_options[0]

    selected_main = st.segmented_control(
        "Secciones Visor",
        main_options,
        key="visor_only_tab",
        label_visibility="collapsed",
    )
    st.write("")

    if selected_main == "📊 Visualización de Datos":
        render_data_visualization_for_visor()
    elif selected_main == "📅 Planificación Semanal":
        render_planning_management(restricted_role_name="Dpto Tecnico")
    elif selected_main == "🌴 Licencias":
        render_admin_vacaciones_tab()
    elif selected_main == "📅 Feriados":
        render_feriados_admin_tab()

def render_data_visualization_for_visor():
    """Renderiza solo la visualización de datos para el rol visor"""
    # Importar la función desde admin_panel
    from .admin_panel import render_data_visualization
    
    # Llamar a la función de visualización existente
    render_data_visualization()

def render_feriados_admin_tab():
    st.subheader("Feriados")
    year_options = [datetime.now().year - 1, datetime.now().year, datetime.now().year + 1]
    sel_year = st.selectbox("Año", options=year_options, index=1, key="visor_feriados_year")
    with st.form(key="visor_feriados_add_form"):
        col_a, col_b = st.columns([1, 1])
        with col_a:
            fecha = st.date_input("Fecha *", key="visor_feriado_fecha")
        with col_b:
            nombre = st.text_input("Nombre *", key="visor_feriado_nombre")
        tipo = st.selectbox("Tipo", options=["nacional", "regional", "empresa"], index=0, key="visor_feriado_tipo")
        submitted = st.form_submit_button("Agregar", type="primary")
        if submitted:
            if fecha and nombre:
                add_feriado(fecha, nombre, tipo, True)
                safe_rerun()
            else:
                st.error("Completa Fecha y Nombre.")
    df = get_feriados_dataframe(year=sel_year, include_inactive=True)
    if df.empty:
        st.info("No hay feriados definidos para este año.")
    else:
        df_display = df.copy()
        df_display["Fecha"] = pd.to_datetime(df_display["fecha"], errors="coerce").dt.strftime("%d/%m/%Y")
        df_display["Nombre"] = df_display["nombre"].fillna("")
        df_display["Tipo"] = df_display["tipo"].fillna("").astype(str).str.capitalize()
        df_display["Estado"] = df_display["activo"].map({True: "Activo", False: "Inactivo"})
        st.dataframe(
            df_display[["Fecha", "Nombre", "Tipo", "Estado"]],
            use_container_width=True,
            hide_index=True,
        )

        opciones = []
        for _, r in df.iterrows():
            fecha_val = pd.to_datetime(r["fecha"], errors="coerce")
            fecha_str = fecha_val.strftime("%d/%m/%Y") if not pd.isna(fecha_val) else "-"
            nombre_str = str(r.get("nombre") or "")
            label = f"{fecha_str} - {nombre_str}" if nombre_str else fecha_str
            opciones.append((label, int(r["id"]), bool(r.get("activo"))))

        if opciones:
            labels = [o[0] for o in opciones]
            selected_label = st.selectbox("Seleccionar feriado para acciones", options=labels, key="visor_feriado_select")
            selected = next(o for o in opciones if o[0] == selected_label)
            fid = selected[1]
            activo_sel = selected[2]
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Activar" if not activo_sel else "Desactivar", key="visor_feriado_toggle_selected"):
                    toggle_feriado(fid, not activo_sel)
                    safe_rerun()
            with col_b:
                if st.button("Eliminar", key="visor_feriado_delete_selected"):
                    delete_feriado(fid)
                    safe_rerun()

    st.divider()
    with st.expander("📥 Carga masiva desde Excel", expanded=False):
        uploaded_file, df, selected_sheet = render_excel_uploader(
            label="Seleccionar archivo con feriados (.xls o .xlsx)",
            key="visor_feriados_excel_upload",
            expanded=False,
            enable_sheet_selection=True
        )
        if uploaded_file is not None and df is not None:
            cols = list(df.columns)
            date_col = None
            for col in cols:
                series = df[col]
                if pd.api.types.is_datetime64_any_dtype(series):
                    date_col = col
                    break
            if date_col is None:
                lower_cols = [str(c).strip().lower() for c in cols]
                for idx, lc in enumerate(lower_cols):
                    if any(token in lc for token in ["feriado", "fecha"]):
                        date_col = cols[idx]
                        break
            if date_col is None and cols:
                date_col = cols[0]

            name_col = None
            type_col = None
            lower_cols = [str(c).strip().lower() for c in cols]
            for idx, lc in enumerate(lower_cols):
                if name_col is None and "nombre" in lc:
                    name_col = cols[idx]
                if type_col is None and "tipo" in lc:
                    type_col = cols[idx]

            resumen_partes = []
            if date_col:
                resumen_partes.append(f"Fechas: {date_col}")
            if name_col:
                resumen_partes.append(f"Nombres: {name_col}")
            else:
                resumen_partes.append("Nombres: autogenerados")
            if type_col:
                resumen_partes.append(f"Tipo: {type_col}")
            else:
                resumen_partes.append("Tipo: nacional por defecto")
            st.caption("Asignación automática → " + " | ".join(resumen_partes))

            if st.button("Procesar archivo y crear feriados", type="primary", key="process_visor_feriados_excel"):
                created = 0
                errors = 0
                series_fecha = df[date_col] if date_col in df.columns else pd.Series(dtype=object)
                series_nombre = df[name_col] if name_col else None
                series_tipo = df[type_col] if type_col else None
                for idx, v in series_fecha.items():
                    try:
                        if pd.isna(v):
                            continue
                        if isinstance(v, str):
                            parsed = pd.to_datetime(v, dayfirst=True, errors="coerce")
                        else:
                            parsed = pd.to_datetime(v, errors="coerce")
                        if pd.isna(parsed):
                            errors += 1
                            continue
                        fecha_val = parsed.date()

                        nombre_val = f"Feriado {fecha_val.strftime('%d/%m/%Y')}"
                        if series_nombre is not None:
                            raw_nombre = series_nombre.get(idx)
                            if not pd.isna(raw_nombre) and str(raw_nombre).strip():
                                nombre_val = str(raw_nombre).strip()

                        tipo_val = "nacional"
                        if series_tipo is not None:
                            raw_tipo = series_tipo.get(idx)
                            if not pd.isna(raw_tipo) and str(raw_tipo).strip():
                                tipo_val = str(raw_tipo).strip().lower()

                        if add_feriado(fecha_val, nombre_val, tipo_val, True):
                            created += 1
                        else:
                            errors += 1
                    except Exception:
                        errors += 1
                if created > 0:
                    st.success(f"Se crearon o actualizaron {created} feriados desde el archivo.")
                    if errors > 0:
                        st.warning(f"No se pudieron procesar {errors} filas.")
                    safe_rerun()
                else:
                    st.error("No se pudo crear ningún feriado desde el archivo.")

def _estado_to_class(s):
    s0 = str(s or "").strip()
    l = s0.lower()
    if not l:
        return ""
    legacy = {
        "activo": "prospecto",
        "pendiente": "presupuestado",
        "finalizado": "ganado",
        "cerrado": "perdido",
    }
    mapping = {
        "prospecto": "prospecto",
        "presupuestado": "presupuestado",
        "negociación": "negociación",
        "negociacion": "negociación",
        "objeción": "objeción",
        "objecion": "objeción",
        "ganado": "ganado",
        "perdido": "perdido",
    }
    if l in mapping:
        return mapping[l]
    return legacy.get(l, l)

def _estado_display(s):
    cls = _estado_to_class(s)
    disp = {
        "prospecto": "Prospecto",
        "presupuestado": "Presupuestado",
        "negociación": "Negociación",
        "objeción": "Objeción",
        "ganado": "Ganado",
        "perdido": "Perdido",
    }
    base = str(s or "").strip()
    return disp.get(cls, base or "-")

def render_adm_comercial_dashboard(user_id):
    # Import and inject centralized CSS (Theme Support)
    try:
        from .ui_components import inject_project_card_css
        inject_project_card_css()
    except ImportError:
        pass

    # --- Early Handling of Selection via Form Submission ---
    params = st.query_params
    if "adm_proj_id" in params:
         try:
             pid_raw = params["adm_proj_id"]
             pid = int(pid_raw[0] if isinstance(pid_raw, list) else pid_raw)
             st.session_state.selected_project_id_adm = pid
             # Clean params and rerun to reflect state
             st.query_params.pop("adm_proj_id", None)
             safe_rerun()
         except:
             pass

    # Check for notification redirects
    if "notification_redirect" in params:
        target = params.get("notification_redirect")
        if isinstance(target, list):
            target = target[0]
            
        if target == "client_requests":
            st.session_state["adm_tabs_control"] = "🏢 Clientes"
            st.session_state["adm_clients_subtab"] = "🟨 Solicitudes"
            # Clear params and rerun
            st.query_params.pop("notification_redirect", None)
            safe_rerun()

    # Calculate alerts for the icon
    alerts = get_general_alerts()
    owner_alerts = alerts["owner_alerts"]
    pending_reqs = alerts["pending_requests_count"]
    
    # Consider only owners with at least one real alert
    has_project_alerts = any(
        (v.get("vencidos", 0) > 0) or (v.get("hoy", 0) > 0) or (v.get("pronto", 0) > 0)
        for v in owner_alerts.values()
    )
    has_alerts = has_project_alerts or (pending_reqs > 0)

    # --- Toast Notifications (Once per session) ---
    if not st.session_state.get('alerts_shown', False):
        # Toast for Pending Client Requests
        if pending_reqs > 0:
            st.toast(f"🟨 Tienes {pending_reqs} solicitudes de clientes pendientes.", icon="📝")

        # Generate grouped toasts for projects
        if owner_alerts:
            MAX_TOASTS = 5
            shown_count = 0
            
            # Sort owners by severity (most critical first)
            sorted_owners = sorted(
                owner_alerts.items(),
                key=lambda x: (x[1]["vencidos"] * 100 + x[1]["hoy"] * 50 + x[1]["pronto"]),
                reverse=True
            )

            for owner, counts in sorted_owners:
                if shown_count >= MAX_TOASTS:
                    remaining = len(sorted_owners) - shown_count
                    st.toast(f"⚠️ ... y {remaining} personas más con alertas.", icon="ℹ️")
                    break
                
                parts = []
                if counts["vencidos"] > 0:
                    parts.append(f"{counts['vencidos']} vencidos")
                if counts["hoy"] > 0:
                    parts.append(f"{counts['hoy']} vencen hoy")
                if counts["pronto"] > 0:
                    parts.append(f"{counts['pronto']} vencen pronto")
                
                if parts:
                    msg = f"**{owner}**: " + ", ".join(parts)
                    icon = "🚨" if (counts["vencidos"] > 0 or counts["hoy"] > 0) else "⚠️"
                    st.toast(msg, icon=icon)
                    shown_count += 1
        
        # Mark alerts as shown for this session
        st.session_state.alerts_shown = True

    col_head, col_icon = st.columns([0.92, 0.08])
    with col_head:
        st.header("Panel de Administración Comercial")
    with col_icon:
        st.write("")  # Spacer for alignment
        try:
            wrapper_class = "has-alerts" if has_alerts else "no-alerts"
            st.markdown(f"<div class='notif-trigger {wrapper_class}'>", unsafe_allow_html=True)
            icon_str = "🔔" if has_alerts else "🔕"
            with st.popover(icon_str, use_container_width=True):
                st.markdown("### Notificaciones")
                if not has_alerts:
                    st.info("No hay alertas pendientes.")
                else:
                    if pending_reqs > 0:
                        label = f"🟨 Solicitudes de Clientes: {pending_reqs} pendientes"
                        if st.button(label, key="adm_com_btn_notif_client_reqs", use_container_width=True):
                            st.session_state["adm_tabs_control"] = "🏢 Clientes"
                            st.session_state["adm_clients_subtab"] = "🟨 Solicitudes"
                            safe_rerun()
                        st.divider()
                    
                    if owner_alerts:
                        sorted_owners = sorted(
                            owner_alerts.items(),
                            key=lambda x: (x[1]["vencidos"] * 100 + x[1]["hoy"] * 50 + x[1]["pronto"]),
                            reverse=True,
                        )
                        for owner, counts in sorted_owners:
                            parts = []
                            if counts["vencidos"] > 0:
                                parts.append(f"{counts['vencidos']} vencidos")
                            if counts["hoy"] > 0:
                                parts.append(f"{counts['hoy']} vencen hoy")
                            if counts["pronto"] > 0:
                                parts.append(f"{counts['pronto']} vencen pronto")
                            
                            if parts:
                                icon = "🚨" if (counts["vencidos"] > 0 or counts["hoy"] > 0) else "⚠️"
                                btn_label = f"{icon} {owner}: {', '.join(parts)}"
                                if st.button(btn_label, key=f"adm_com_alert_{owner}", use_container_width=True):
                                    st.session_state["adm_tabs_control"] = "📂 Tratos Dpto Comercial"
                                    st.session_state["adm_filter_vendedor_preset"] = owner
                                    safe_rerun()
                                st.divider()
            st.markdown("</div>", unsafe_allow_html=True)
        except AttributeError:
            if st.button("🔔"):
                st.info(f"Notificaciones: {pending_reqs} solicitudes, {len(owner_alerts)} alertas de proyectos")

    # --- Global CSS for Projects ---
    # (Removed hardcoded CSS to use centralized inject_project_card_css defined at top of function)
    
    # --- Navigation Logic (Same as Dpto Comercial) ---
    # Mapping for clean URLs
    ADM_TAB_MAPPING = {
        "metricas": "📊 Métricas",
        "tratos": "📂 Tratos Dpto Comercial",
        "nuevo_trato": "🆕 Nuevo Trato",
        "contactos": "👤 Contactos",
        "clientes": "🏢 Clientes",
        "marcas": "🏷️ Marcas"
    }
    ADM_TAB_LABELS = list(ADM_TAB_MAPPING.values())
    ADM_TAB_KEY_LOOKUP = {v: k for k, v in ADM_TAB_MAPPING.items()}
    
    labels = ADM_TAB_LABELS
    params = st.query_params

    # Handle forced tab switch from create project (prevents StreamlitAPIException)
    if "force_adm_tab" in st.session_state:
        forced_val = st.session_state.pop("force_adm_tab")
        st.session_state["adm_tabs_control"] = forced_val
        
        # Update URL immediately
        clean_key = ADM_TAB_KEY_LOOKUP.get(forced_val, forced_val)
        if "adm_tab" in params and params["adm_tab"] != clean_key:
            st.query_params["adm_tab"] = clean_key

    # Determine initial tab from URL param or session state
    initial = None
    adm_tab = params.get("adm_tab")
    if adm_tab:
        val = adm_tab[0] if isinstance(adm_tab, list) else adm_tab
        if val in ADM_TAB_MAPPING:
            initial = ADM_TAB_MAPPING[val]
        elif val in labels:
            initial = val
            
    if not initial:
        # If a project is selected, go to Projects (index 1), otherwise Metrics (index 0)
        if st.session_state.get("selected_project_id_adm"):
             initial = labels[1]
        else:
             initial = labels[0]

    # Ensure session state is initialized
    if "adm_tabs_control" not in st.session_state:
        st.session_state["adm_tabs_control"] = initial

    # Render Segmented Control
    choice = st.segmented_control(
        label="Secciones Admin",
        options=labels,
        key="adm_tabs_control",
        label_visibility="collapsed"
    )

    # Sync with URL
    current_val_param = adm_tab[0] if isinstance(adm_tab, list) else adm_tab if adm_tab else None
    target_param = ADM_TAB_KEY_LOOKUP.get(choice, choice)
    
    if current_val_param != target_param:
        try:
            st.query_params["adm_tab"] = target_param
            safe_rerun()
        except Exception:
            pass

    # Si salimos de la vista de proyectos, limpiar selección previa de admin
    if choice != labels[1] and "selected_project_id_adm" in st.session_state:
        del st.session_state["selected_project_id_adm"]

    # --- Render Content based on Selection ---

    # Calculate role ID for admin contact management reuse (cached)
    if "cached_comercial_rol_id" not in st.session_state:
        roles = get_roles_dataframe()
        comercial_role = roles[roles['nombre'] == 'Dpto Comercial']
        if comercial_role.empty:
            comercial_role = roles[roles['nombre'].str.lower().str.contains('comercial') & (roles['nombre'] != 'adm_comercial')]
        
        if comercial_role.empty:
            st.session_state["cached_comercial_rol_id"] = 0
        else:
            st.session_state["cached_comercial_rol_id"] = int(comercial_role.iloc[0]['id_rol'])
    
    rol_id = st.session_state["cached_comercial_rol_id"]

    if choice == labels[2]:
        # Create Project View
        render_create_project(user_id, is_admin=True, contact_key_prefix=f"adm_{rol_id}_")
        
    elif choice == labels[1]:
        # Projects View
        if st.session_state.get("selected_project_id_adm"):
             def back_to_list():
                 del st.session_state.selected_project_id_adm
                 safe_rerun()
             
             render_project_detail_screen(user_id, st.session_state.selected_project_id_adm, bypass_owner=True, show_back_button=True, back_callback=back_to_list)
        else:
             render_adm_projects_list(user_id)
             
    elif choice == labels[3]:
        # Contacts View
        from .admin_visualizations import render_adm_contacts
        render_adm_contacts(rol_id)

    elif choice == "🏢 Clientes":
        client_options = ["📋 Lista", "⚙️ Gestión", "🟨 Solicitudes"]
        
        # Ensure subtab state is initialized
        if "adm_clients_subtab" not in st.session_state:
            st.session_state["adm_clients_subtab"] = client_options[0]
            
        # If value is invalid (e.g. from old state), reset
        if st.session_state["adm_clients_subtab"] not in client_options:
             st.session_state["adm_clients_subtab"] = client_options[0]

        client_choice = st.segmented_control(
            "Secciones Clientes",
            client_options,
            key="adm_clients_subtab",
            label_visibility="collapsed"
        )
        
        if client_choice == "📋 Lista":
            render_client_management()
        elif client_choice == "⚙️ Gestión":
            render_client_crud_management()
        elif client_choice == "🟨 Solicitudes":
            st.subheader("🟨 Solicitudes de Clientes")
            req_df = get_cliente_solicitudes_df(estado='pendiente')
            if req_df.empty:
                st.info("No hay solicitudes pendientes.")
            else:
                users_df = get_users_dataframe()
                id_to_name = {int(r["id"]): f"{(r['nombre'] or '').strip()} {(r['apellido'] or '').strip()}".strip() for _, r in users_df.iterrows()}
                has_email = 'email' in req_df.columns
                has_cuit = 'cuit' in req_df.columns
                has_celular = 'celular' in req_df.columns
                has_web = 'web' in req_df.columns
                
                # Use native CSS variables for theme adaptation (like Contact cards)
                st.markdown(
                    """
                    <style>
                      .req-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 10px 0 16px; }
                      .req-card { 
                          background-color: var(--secondary-background-color); 
                          border: 1px solid rgba(128, 128, 128, 0.2); 
                          border-radius: 12px; 
                          padding: 14px; 
                      }
                      .req-title { 
                          font-weight: 600; 
                          color: var(--text-color); 
                          opacity: 0.7;
                          margin-bottom: 6px; 
                      }
                      .req-value { 
                          color: var(--text-color); 
                          font-weight: 500;
                      }
                      @media (max-width: 768px) { .req-grid { grid-template-columns: 1fr; } }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )
                for _, r in req_df.iterrows():
                    rid = int(r["id"])
                    requester = id_to_name.get(int(r["requested_by"]), "Usuario")
                    with st.expander(f"{r['nombre']} — {r['organizacion'] or ''} ({requester})"):
                        email_val = r["email"] if has_email else None
                        cuit_val = r["cuit"] if has_cuit else None
                        celular_val = r["celular"] if has_celular else None
                        web_val = r["web"] if has_web else None
                        org_card = (
                            f"""
                              <div class='req-card'>
                                <div class='req-title'>Organización</div>
                                <div class='req-value'>{(r['organizacion'] or '-')}</div>
                              </div>
                            """
                        ) if (str(r.get('organizacion') or '').strip()) else ""
                        web_html = (
                            (f"<a href='{str(web_val)}' target='_blank'>{str(web_val)}</a>")
                            if str(web_val or '').strip() else '-'
                        )
                        grid_html = (
                            f"""
                            <div class='req-grid'>
                              <div class='req-card'>
                                <div class='req-title'>Nombre</div>
                                <div class='req-value'>{(r['nombre'] or '')}</div>
                              </div>
                              {org_card}
                              <div class='req-card'>
                                <div class='req-title'>Teléfono</div>
                                <div class='req-value'>{(r['telefono'] or '-')}</div>
                              </div>
                              <div class='req-card'>
                                <div class='req-title'>Email</div>
                                <div class='req-value'>{(email_val or '-')}</div>
                              </div>
                              <div class='req-card'>
                                <div class='req-title'>CUIT</div>
                                <div class='req-value'>{(cuit_val or '-')}</div>
                              </div>
                              <div class='req-card'>
                                <div class='req-title'>Celular</div>
                                <div class='req-value'>{(celular_val or '-')}</div>
                              </div>
                              <div class='req-card'>
                                <div class='req-title'>Web</div>
                                <div class='req-value'>{web_html}</div>
                              </div>
                            </div>
                            """
                        )
                        st.markdown(grid_html, unsafe_allow_html=True)
                        cols = st.columns([1,1,4])
                        with cols[0]:
                            if st.button("Aprobar", key=f"adm_com_approve_client_req_{rid}", type="primary"):
                                success, msg = approve_cliente_solicitud(rid)
                                if success:
                                    st.success(msg)
                                    safe_rerun()
                                else:
                                    st.error(f"No se pudo aprobar la solicitud: {msg}")
                        with cols[1]:
                            if st.button("Rechazar", key=f"adm_com_reject_client_req_{rid}"):
                                success, msg = reject_cliente_solicitud(rid)
                                if success:
                                    st.info("Solicitud rechazada.")
                                    safe_rerun()
                                else:
                                    st.error(f"No se pudo rechazar la solicitud: {msg}")

    elif choice == "🏷️ Marcas":
        render_brand_management()

    else:
        # Metrics View
        roles = get_roles_dataframe()
        comercial_role = roles[roles['nombre'] == 'Dpto Comercial']
        if comercial_role.empty:
            comercial_role = roles[roles['nombre'].str.lower().str.contains('comercial') & (roles['nombre'] != 'adm_comercial')]
        
        if comercial_role.empty:
            st.error("No se encontró el departamento 'Dpto Comercial'.")
        else:
            rol_id = int(comercial_role.iloc[0]['id_rol'])
            from .admin_visualizations import render_commercial_department_dashboard
            render_commercial_department_dashboard(rol_id)


def render_adm_projects_list(user_id):
    # Import CSS injector from ui_components
    try:
        from .ui_components import inject_project_card_css
        inject_project_card_css()
    except ImportError:
        pass

    st.subheader("Tratos del Departamento Comercial")


    # --- Data Fetching ---
    
    # Filter by Vendedor (users with 'comercial' or 'adm_comercial' role)
    # We must include hidden roles because 'adm_comercial' is a hidden role
    roles = get_roles_dataframe(exclude_hidden=False)
    # Get relevant role IDs for both Dpto Comercial and adm_comercial
    target_roles_df = roles[roles['nombre'].isin(['Dpto Comercial', 'adm_comercial'])]
    
    selected_user_id = None
    user_options = {"Todos": None}
    all_target_user_ids = []
    
    if not target_roles_df.empty:
        for _, role_row in target_roles_df.iterrows():
            r_id = role_row['id_rol']
            # We must set exclude_hidden=False so that users with hidden roles (like adm_comercial) are returned
            users_df = get_users_by_rol(r_id, exclude_hidden=False) 
            
            if not users_df.empty:
                for _, u in users_df.iterrows():
                    u_id = u['id']
                    # Construct name safely
                    first = (u.get('nombre') or '').strip()
                    last = (u.get('apellido') or '').strip()
                    u_name = f"{first} {last}".strip()
                    
                    if u_name not in user_options:
                        user_options[u_name] = u_id
                        all_target_user_ids.append(u_id)
    
    # Map IDs to names for display (invert user_options)
    id_to_name = {v: k for k, v in user_options.items() if v is not None}
    
    # --- Filters UI ---
    # Get unique clients from ALL projects (or filtered by seller if we wanted strict dependency, but global is better for admin)
    # However, to avoid confusion, let's get clients from the currently available projects scope (which might be filtered by seller later)
    # But wait, filtering logic is sequential. 
    # Let's get ALL unique clients from the full project list for the dropdown options.
    all_proyectos_df = get_all_proyectos()
    unique_clients = sorted(all_proyectos_df["cliente_nombre"].dropna().unique().tolist())
    unique_clients = [c for c in unique_clients if c.strip()]
    opciones_clientes = ["Todos"] + unique_clients

    fcol1, fcol2, fcol3, fcol4, fcol5 = st.columns([2, 2, 2, 2, 2])
    
    with fcol1:
        # Replaces the old single selectbox
        user_keys = list(user_options.keys())
        default_idx = 0
        
        # Check for notification redirect preset
        if "adm_filter_vendedor_preset" in st.session_state:
            preset = st.session_state["adm_filter_vendedor_preset"]
            if preset in user_keys:
                default_idx = user_keys.index(preset)
            # Clear it immediately so it doesn't persist
            del st.session_state["adm_filter_vendedor_preset"]

        selected_user_label = st.selectbox("Vendedor", options=user_keys, index=default_idx, key="adm_filter_vendedor")
        selected_user_id = user_options[selected_user_label]
    
    with fcol2:
        sel_cliente = st.selectbox("Cliente", options=opciones_clientes, key="adm_filter_cliente")
        filtro_cliente = sel_cliente if sel_cliente != "Todos" else ""

    with fcol3:
        filtro_nombre = st.text_input("Nombre del proyecto", key="adm_filter_nombre")
        
    with fcol4:
        filtro_estados = st.multiselect("Estado", options=PROYECTO_ESTADOS, key="adm_filter_estado")
        
    with fcol5:
        ordenar_por = st.selectbox("Ordenar por", ["Defecto", "Fecha Cierre (Asc)", "Fecha Cierre (Desc)"], key="adm_sort_option")

    # --- Data Logic ---
    filter_ids = [selected_user_id] if selected_user_id else None
    
    # If no specific user selected ("Todos"), include all users from target roles
    if not filter_ids:
        filter_ids = all_target_user_ids
            
    proyectos_df = get_all_proyectos(filter_user_ids=filter_ids)
    
    # Apply Filters
    if filtro_cliente:
        proyectos_df = proyectos_df[proyectos_df.get("cliente_nombre", pd.Series(dtype=str)).fillna("") == filtro_cliente]

    if filtro_nombre:
        proyectos_df = proyectos_df[proyectos_df.get("titulo", pd.Series(dtype=str)).fillna("").str.contains(filtro_nombre, case=False, na=False)]
        
    if filtro_estados:
        proyectos_df = proyectos_df[
            proyectos_df.get("estado", pd.Series(dtype=str)).fillna("").apply(_estado_to_class).isin([e.lower() for e in filtro_estados])
        ]
        
    # Sorting
    if ordenar_por != "Defecto":
        temp_date_col = pd.to_datetime(proyectos_df["fecha_cierre"], errors="coerce")
        ascending_order = (ordenar_por == "Fecha Cierre (Asc)")
        sorted_indices = temp_date_col.sort_values(ascending=ascending_order, na_position='last').index
        proyectos_df = proyectos_df.loc[sorted_indices]

    # --- Handle Selection via Form Submission ---
    # The form in the card submits with 'adm_proj_id'
    params = st.query_params
    if "adm_proj_id" in params:
            try:
                pid_raw = params["adm_proj_id"]
                pid = int(pid_raw[0] if isinstance(pid_raw, list) else pid_raw)
                st.session_state.selected_project_id_adm = pid
                # Clean params
                st.query_params.pop("adm_proj_id", None)
                safe_rerun()
            except:
                pass

    # --- Pagination ---
    if proyectos_df.empty:
            st.info("No hay proyectos.")
    else:
            page_size = 6
            total_items = len(proyectos_df)
            page = int(st.session_state.get("adm_projects_page", 1) or 1)
            total_pages = max((total_items + page_size - 1) // page_size, 1)
            
            if page > total_pages: page = total_pages
            if page < 1: page = 1
            st.session_state["adm_projects_page"] = page
            
            start = (page - 1) * page_size
            end = start + page_size
            df_page = proyectos_df.iloc[start:end]
            
            count_text = f"Mostrando elementos {start+1}-{min(end, total_items)} de {total_items}"
            
            for _, row in df_page.iterrows():
                pid = int(row['id'])
                estado = _estado_to_class(row.get('estado'))
                estado_disp = _estado_display(row.get('estado'))
                title = row['titulo']
                cliente = row.get('cliente_nombre') or "Sin cliente"
                
                try:
                    _fc_dt = pd.to_datetime(row.get("fecha_cierre"), errors="coerce")
                    fc_fmt = _fc_dt.strftime("%d/%m/%Y") if not pd.isna(_fc_dt) else "-"
                except:
                    fc_fmt = "-"
                    
                tipo_venta_card = row.get("tipo_venta") or "-"
                
                # Resolve owner name
                owner_id_raw = row.get('owner_user_id')
                try:
                    owner_id = int(owner_id_raw) if pd.notna(owner_id_raw) else None
                except:
                    owner_id = None
                owner_name = id_to_name.get(owner_id, f"ID {owner_id}" if owner_id else "Sin asignar")
                
                # Alerts
                alert_html = ""
                try:
                    if row.get("estado") not in ["Ganado", "Perdido"]:
                        alert_color = ""
                        alert_text = ""
                        alert_bg = ""
                        
                        if pd.isna(_fc_dt):
                            alert_color = "#9ca3af"
                            alert_bg = "rgba(156, 163, 175, 0.2)"
                            alert_text = "Sin definir"
                        else:
                            days_diff = (_fc_dt.date() - pd.Timestamp.now().date()).days
                            if days_diff < 0:
                                alert_color = "#ef4444"
                                alert_bg = "rgba(239, 68, 68, 0.2)"
                                alert_text = f"Vencido {abs(days_diff)}d"
                            elif days_diff == 0:
                                alert_color = "#ef4444"
                                alert_bg = "rgba(239, 68, 68, 0.2)"
                                alert_text = "Vence hoy"
                            elif days_diff <= 7:
                                alert_color = "#f97316"
                                alert_bg = "rgba(249, 115, 22, 0.2)"
                                alert_text = f"{days_diff}d restantes"
                            elif days_diff <= 15:
                                alert_color = "#eab308"
                                alert_bg = "rgba(234, 179, 8, 0.2)"
                                alert_text = f"{days_diff}d restantes"
                            elif days_diff <= 30:
                                alert_color = "#22c55e"
                                alert_bg = "rgba(34, 197, 94, 0.2)"
                                alert_text = f"{days_diff}d restantes"
                            else:
                                alert_color = "#3b82f6"
                                alert_bg = "rgba(59, 130, 246, 0.2)"
                                alert_text = f"{days_diff}d restantes"
                        
                        if alert_text:
                            alert_html = f'''
                            <div style="display:flex; align-items:center; gap:6px; margin-right:12px; background:{alert_bg}; padding:4px 8px; border-radius:999px; border:1px solid {alert_color};">
                                <div style="width:8px; height:8px; border-radius:50%; background-color:{alert_color};"></div>
                                <span style="color:{alert_color}; font-size:0.85em; font-weight:600;">{alert_text}</span>
                            </div>
                            '''
                except:
                    pass
                
                alert_html = " ".join(alert_html.split())
                
                # Params for form
                def get_param(k):
                    v = params.get(k)
                    return (v[0] if isinstance(v, list) else v) if v else ""
                hidden_uid = get_param("uid")
                hidden_uexp = get_param("uexp")
                hidden_usig = get_param("usig")
                
                input_uid = f'<input type="hidden" name="uid" value="{hidden_uid}" />' if hidden_uid else ''
                input_uexp = f'<input type="hidden" name="uexp" value="{hidden_uexp}" />' if hidden_uexp else ''
                input_usig = f'<input type="hidden" name="usig" value="{hidden_usig}" />' if hidden_usig else ''

                st.markdown(
                    f"""
                    <form method="get" class="card-form">
                        <input type="hidden" name="adm_proj_id" value="{pid}" />
                        {input_uid}
                        {input_uexp}
                        {input_usig}
                        <div class="project-card">
                        <div class="project-info">
                            <div class="project-title">
                            <span class="dot-left {estado}"></span>
                            <span>{title}</span>
                            </div>
                            <div class="project-sub">
                                <span class="hl-label">ID</span> <span class="hl-val">{pid}</span>
                                <span class="hl-sep">•</span>
                                <span class="hl-val client">{cliente}</span>
                                <span class="hl-sep">•</span>
                                <span class="hl-label">👤</span> <span class="hl-val bright">{owner_name}</span>
                            </div>
                            <div class="project-sub2">
                                <span class="hl-label">Cierre:</span> <span class="hl-val">{fc_fmt}</span>
                                <span class="hl-sep">•</span>
                                <span class="hl-val">{tipo_venta_card}</span>
                            </div>
                        </div>
                        <div style="display:flex; align-items:center;">
                            {alert_html}
                            <span class="status-pill {estado}">{estado_disp}</span>
                        </div>
                        </div>
                        <button type="submit" class="card-submit"></button>
                    </form>
                    """.replace("\n", " "),
                    unsafe_allow_html=True
                )

            st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
            
            # Pagination controls: Text Left, Buttons Right
            col_text, col_spacer, col_prev, col_sep, col_next = st.columns([3, 3, 1, 0.5, 1])
            
            with col_text:
                st.markdown(f"<div style='display:flex; align-items:center; height:100%; color:#888;'>{count_text}</div>", unsafe_allow_html=True)
            with col_prev:
                if st.button("Anterior", disabled=(page <= 1), key="adm_prev_page", use_container_width=True):
                    st.session_state["adm_projects_page"] = page - 1
                    safe_rerun()
            with col_next:
                if st.button("Siguiente", disabled=(page >= total_pages), key="adm_next_page", use_container_width=True):
                    st.session_state["adm_projects_page"] = page + 1
                    safe_rerun()
