import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import time
import calendar
from .utils import month_name_es
# Actualizar las importaciones al principio del archivo
from .database import (
    get_connection, get_registros_dataframe, get_registros_dataframe_with_date_filter,
    get_tecnicos_dataframe, get_clientes_dataframe, get_tipos_dataframe,
    get_modalidades_dataframe, get_roles_dataframe, get_users_dataframe,
    get_grupos_dataframe, get_grupos_puntajes_dataframe, get_grupo_puntaje_by_nombre,
    set_grupo_puntaje_by_nombre, get_clientes_puntajes_dataframe, get_cliente_puntaje_by_nombre,
    set_cliente_puntaje_by_nombre, get_tipos_dataframe_with_roles, get_tipos_puntajes_dataframe,
    get_tipo_puntaje_by_descripcion, set_tipo_puntaje_by_descripcion,
    get_all_proyectos, get_users_by_rol
)
from .utils import show_success_message
from .config import SYSTEM_ROLES, PROYECTO_ESTADOS
from .admin_planning import render_planning_management
from .admin_visualizations import render_role_visualizations
from .commercial_projects import render_project_detail_screen, render_create_project

def render_visor_dashboard(user_id, nombre_completo_usuario):
    """Renderiza el dashboard completo del hipervisor con pestañas"""
    st.header("Panel de Hipervisor")
    
    # Crear pestañas principales del panel de hipervisor (ahora tres)
    tab_visualizacion, tab_gestion, tab_planificacion = st.tabs(["📊 Visualización de Datos", "⚙️ Gestión", "📅 Planificación Semanal"])
    
    with tab_visualizacion:
        # Crear sub-pestañas para la sección de visualización
        tab_puntajes_cliente, tab_puntajes_tecnico, tab_eficiencia = st.tabs(["🏢 Puntajes por Cliente", "👨‍💻 Puntajes por Técnico", "⚖️ Eficiencia por Cliente"])
        
        with tab_puntajes_cliente:
            # Implementar la visualización de puntajes calculados por cliente
            render_score_calculation()
        
        with tab_puntajes_tecnico:
            # Implementar la visualización de puntajes calculados por técnico
            render_score_calculation_by_technician()
            
        with tab_eficiencia:
            # Implementar la visualización de eficiencia por cliente
            render_efficiency_analysis()
    
    with tab_gestion:
        # Llamar a la función que renderiza las pestañas de gestión
        render_records_management(user_id)

    with tab_planificacion:
        render_planning_management(restricted_role_name="Dpto Tecnico")

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
                height=500
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
                height=500
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
        clientes_df = get_clientes_puntajes_dataframe()
        
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
                st.rerun()
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
                st.rerun()
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
                st.rerun()
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


def render_visor_only_dashboard():
    """Renderiza el dashboard del visor con visualización y planificación"""
    st.header("Panel de Visor")
    
    # Crear pestañas para organizar las vistas
    tab_visualizacion, tab_planificacion = st.tabs(["📊 Visualización de Datos", "📅 Planificación Semanal"])
    
    with tab_visualizacion:
        # Solo mostrar la visualización de datos
        render_data_visualization_for_visor()
        
    with tab_planificacion:
        # Mostrar la planificación semanal restringida al Dpto Tecnico
        render_planning_management(restricted_role_name="Dpto Tecnico")

def render_data_visualization_for_visor():
    """Renderiza solo la visualización de datos para el rol visor"""
    # Importar la función desde admin_panel
    from .admin_panel import render_data_visualization
    
    # Llamar a la función de visualización existente
    render_data_visualization()

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
    # --- Early Handling of Selection via Form Submission ---
    params = st.query_params
    if "adm_proj_id" in params:
         try:
             pid_raw = params["adm_proj_id"]
             pid = int(pid_raw[0] if isinstance(pid_raw, list) else pid_raw)
             st.session_state.selected_project_id_adm = pid
             # Clean params and rerun to reflect state
             st.query_params.pop("adm_proj_id", None)
             st.rerun()
         except:
             pass

    st.header("Panel de Administración Comercial")

    # --- Global CSS for Projects (ensure it's always available) ---
    st.markdown("""
    <style>
      .project-card {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        background: #1f2937;
        border: 1px solid #374151;
        color: #e5e7eb;
        padding: 20px 24px;
        border-radius: 14px;
        box-sizing: border-box;
        text-decoration: none;
        box-shadow: 0 4px 10px rgba(0,0,0,0.25);
      }
      .project-card + .project-card { margin-top: 14px; }
      .project-card:hover {
        background: #111827;
        border-color: #2563eb;
        transform: translateY(-1px);
        transition: all .15s ease-in-out;
        transition: all .15s ease-in-out;
      }
      .project-info { display: flex; flex-direction: column; }
      .project-title {
        display: flex; align-items: center; gap: 10px;
        font-size: 22px; font-weight: 700;
      }
      .dot-left { width: 10px; height: 10px; border-radius: 50%; }
      .dot-left.prospecto { background: #60a5fa; }
      .dot-left.presupuestado { background: #34d399; }
      .dot-left.negociación { background: #8b5cf6; }
      .dot-left.objeción { background: #fbbf24; }
      .dot-left.ganado { background: #065f46; }
      .dot-left.perdido { background: #ef4444; }
      .project-sub { margin-top: 4px; color: #9ca3af; font-size: 16px; }
      .project-sub2 { margin-top: 2px; color: #9ca3af; font-size: 15px; }
      
      /* Highlights for card readability */
      .hl-label { color: #6b7280; font-weight: 600; font-size: 0.9em; text-transform: uppercase; letter-spacing: 0.05em; }
      .hl-val { color: #e5e7eb; font-weight: 500; }
      .hl-val.bright { color: #f3f4f6; font-weight: 600; }
      .hl-val.client { color: #60a5fa; font-weight: 700; }
      .hl-sep { color: #4b5563; margin: 0 6px; }

      .status-pill {
        padding: 10px 16px; border-radius: 999px;
        font-size: 18px; font-weight: 700;
        border: 2px solid transparent;
      }
      .status-pill.prospecto { color: #60a5fa; border-color: #60a5fa; }
      .status-pill.presupuestado { color: #34d399; border-color: #34d399; }
      .status-pill.negociación { color: #8b5cf6; border-color: #8b5cf6; }
      .status-pill.objeción { color: #fbbf24; border-color: #fbbf24; }
      .status-pill.ganado { color: #065f46; border-color: #065f46; }
      .status-pill.perdido { color: #ef4444; border-color: #ef4444; }
      /* Formulario clickeable */
      .card-form { position: relative; display: block; margin-bottom: 18px; }
      .card-form .card-submit {
        position: absolute; inset: 0; width: 100%; height: 100%;
        background: transparent; border: 0; padding: 0; margin: 0;
        cursor: pointer; opacity: 0; box-shadow: none; outline: none;
      }
      /* Improve select contrast */
      div[data-baseweb="select"] {
        background: #111827 !important;
        border: 1px solid #ef4444 !important;
        border-radius: 12px !important;
      }
      div[data-baseweb="select"] * { color: #e5e7eb !important; }
    </style>
    """, unsafe_allow_html=True)
    
    # --- Navigation Logic (Same as Dpto Comercial) ---
    labels = ["📊 Métricas", "📂 Proyectos Dpto Comercial", "🆕 Crear Proyecto", "👤 Contactos"]
    params = st.query_params

    # Determine initial tab from URL param or session state
    initial = None
    adm_tab = params.get("adm_tab")
    if adm_tab:
        val = adm_tab[0] if isinstance(adm_tab, list) else adm_tab
        if val in labels:
            initial = val
            
    if not initial:
        # If a project is selected, go to Projects (index 1), otherwise Metrics (index 0)
        if st.session_state.get("selected_project_id_adm"):
             initial = labels[1]
        else:
             initial = labels[0]

    # Render Segmented Control
    choice = st.segmented_control(
        label="Secciones Admin",
        options=labels,
        default=initial,
        key="adm_tabs_control",
        label_visibility="collapsed"
    )

    # Sync with URL
    current_val = adm_tab[0] if isinstance(adm_tab, list) else adm_tab if adm_tab else None
    if choice != current_val:
        try:
            st.query_params["adm_tab"] = choice
            st.rerun()
        except Exception:
            pass

    # --- Render Content based on Selection ---
    if choice == labels[2]:
        # Create Project View
        render_create_project(user_id)
        
    elif choice == labels[1]:
        # Projects View
        if st.session_state.get("selected_project_id_adm"):
             def back_to_list():
                 del st.session_state.selected_project_id_adm
                 st.rerun()
             
             render_project_detail_screen(user_id, st.session_state.selected_project_id_adm, bypass_owner=True, show_back_button=False, back_callback=back_to_list)
        else:
             render_adm_projects_list(user_id)
             
    elif choice == labels[3]:
        # Contacts View
        roles = get_roles_dataframe()
        comercial_role = roles[roles['nombre'] == 'Dpto Comercial']
        if comercial_role.empty:
            comercial_role = roles[roles['nombre'].str.lower().str.contains('comercial') & (roles['nombre'] != 'adm_comercial')]
        
        if comercial_role.empty:
            # Fallback if role not found, though unlikely
            rol_id = 0 
        else:
            rol_id = int(comercial_role.iloc[0]['id_rol'])
            
        from .admin_visualizations import render_adm_contacts
        render_adm_contacts(rol_id)

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
    # --- Notification Logic for Expiring Projects ---
    # Get ALL projects to check for alerts (ignoring current filters/pagination)
    all_alert_proyectos = get_all_proyectos()
    
    # Map Owner IDs to Names
    users_df_all = get_users_dataframe()
    users_df_all["nombre_completo"] = users_df_all.apply(lambda r: f"{(r['nombre'] or '').strip()} {(r['apellido'] or '').strip()}".strip(), axis=1)
    owner_map = {int(r["id"]): r["nombre_completo"] for _, r in users_df_all.iterrows()}

    # Group alerts by owner
    # Structure: { owner_name: { "vencidos": 0, "hoy": 0, "pronto": 0 } }
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

    # Generate grouped toasts
    if owner_alerts:
        MAX_TOASTS = 5
        shown_count = 0
        
        # Sort owners by severity (most critical first)
        # Severity score: Vencidos * 100 + Hoy * 50 + Pronto * 1
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


    st.subheader("Proyectos del Departamento Comercial")


    # --- Data Fetching ---
    
    # Filter by Vendedor (users with 'comercial' role)
    roles = get_roles_dataframe()
    comercial_role = roles[roles['nombre'] == 'Dpto Comercial']
    if comercial_role.empty:
        comercial_role = roles[roles['nombre'].str.lower().str.contains('comercial') & (roles['nombre'] != 'adm_comercial')]
    
    selected_user_id = None
    user_options = {"Todos": None}
    
    if not comercial_role.empty:
        rol_id = comercial_role.iloc[0]['id_rol']
        users_df = get_users_by_rol(rol_id) 
        
        if not users_df.empty:
            for _, u in users_df.iterrows():
                user_options[f"{u['nombre']} {u['apellido']}"] = u['id']
    
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
        selected_user_label = st.selectbox("Vendedor", options=list(user_options.keys()), key="adm_filter_vendedor")
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
    
    if not filter_ids and not comercial_role.empty:
            rol_id = comercial_role.iloc[0]['id_rol']
            users_df = get_users_by_rol(rol_id)
            if not users_df.empty:
                filter_ids = users_df['id'].tolist()
            
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
                st.rerun()
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
                    st.rerun()
            with col_next:
                if st.button("Siguiente", disabled=(page >= total_pages), key="adm_next_page", use_container_width=True):
                    st.session_state["adm_projects_page"] = page + 1
                    st.rerun()
