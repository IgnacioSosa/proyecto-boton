import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import time
# Actualizar las importaciones al principio del archivo
from .database import (
    get_connection, get_registros_dataframe, get_registros_by_rol,
    get_tecnicos_dataframe, get_clientes_dataframe, get_tipos_dataframe,
    get_modalidades_dataframe, get_roles_dataframe, get_users_dataframe,
    get_grupos_dataframe, get_grupos_puntajes_dataframe, get_grupo_puntaje_by_nombre,
    set_grupo_puntaje_by_nombre, get_clientes_puntajes_dataframe, get_cliente_puntaje_by_nombre,
    set_cliente_puntaje_by_nombre, get_tipos_dataframe_with_roles, get_tipos_puntajes_dataframe,
    get_tipo_puntaje_by_descripcion, set_tipo_puntaje_by_descripcion
)
from .utils import show_success_message

def render_visor_dashboard(user_id, nombre_completo_usuario):
    """Renderiza el dashboard completo del hipervisor con pestañas"""
    st.header("Panel de Hipervisor")
    
    # Crear pestañas principales del panel de hipervisor (solo dos)
    tab_visualizacion, tab_gestion = st.tabs(["📊 Visualización de Datos", "⚙️ Gestión"])
    
    with tab_visualizacion:
        # Pestaña vacía
        st.info("Sección en desarrollo")
    
    with tab_gestion:
        # Llamar a la función que renderiza las pestañas de gestión
        render_records_management(user_id)

# Eliminar o comentar las funciones que no se usarán
# def render_data_visualization(user_id):
#     ...

# def render_role_visualizations(df, rol_id, rol_nombre):
#     ...

def render_records_management(user_id):
    """Renderiza la sección de gestión para hipervisores"""
    st.subheader("Gestión de Registros")
    
    # Crear pestañas para la sección de gestión
    tab_usuarios, tab_clientes, tab_grupo, tab_tipos = st.tabs(["👥 Usuarios", "🏢 Clientes", "👪 Grupo", "📋 Tipos de Tarea"])
    
    with tab_usuarios:
        # Obtener todos los usuarios excepto los ocultos
        users_df = get_users_dataframe()
        
        # Filtrar usuarios que no tengan rol_nombre 'sin_rol' (que serían los ocultos)
        users_df = users_df[users_df['rol_nombre'] != 'sin_rol']
        
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
            'rol_nombre': 'Rol'
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
                'roles_asignados': 'Roles Asignados',
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
                'roles_asociados': 'Roles Asociados',
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