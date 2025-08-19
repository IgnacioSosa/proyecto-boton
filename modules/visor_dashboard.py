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

# Función para calcular y visualizar puntajes por cliente
def render_score_calculation():
    """Renderiza la sección de cálculo y visualización de puntajes por cliente"""
    st.subheader("Cálculo de Puntajes por Cliente")
    
    # Obtener los datos necesarios
    registros_df = get_registros_dataframe()
    
    if registros_df.empty:
        st.info("No hay registros disponibles para calcular puntajes")
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
    
    # Obtener los datos necesarios
    registros_df = get_registros_dataframe()
    
    if registros_df.empty:
        st.info("No hay registros disponibles para calcular puntajes")
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

# Función para calcular y visualizar la eficiencia por cliente
def render_efficiency_analysis():
    """Renderiza la sección de análisis de eficiencia por cliente"""
    st.subheader("Análisis de Eficiencia por Cliente")
    
    # Obtener los datos necesarios
    registros_df = get_registros_dataframe()
    
    if registros_df.empty:
        st.info("No hay registros disponibles para calcular la eficiencia")
        return
    
    # Obtener los puntajes de clientes (valor del cliente)
    clientes_puntajes_df = get_clientes_puntajes_dataframe()
    
    # Calcular horas totales por cliente
    horas_por_cliente = registros_df.groupby('cliente')['tiempo'].sum().reset_index()
    horas_por_cliente.rename(columns={'tiempo': 'horas_totales'}, inplace=True)
    
    # Unir con los puntajes de clientes
    eficiencia_df = pd.merge(horas_por_cliente, clientes_puntajes_df, left_on='cliente', right_on='nombre', how='left')
    
    # Asegurar que no haya valores nulos en puntaje
    eficiencia_df['puntaje'] = eficiencia_df['puntaje'].fillna(0)
    
    # Evitar división por cero
    eficiencia_df['puntaje_ajustado'] = eficiencia_df['puntaje'].apply(lambda x: max(1, x))
    
    # Calcular la relación Rc = Hc/Vc
    eficiencia_df['relacion_horas_valor'] = eficiencia_df['horas_totales'] / eficiencia_df['puntaje_ajustado']
    
    # Calcular estadísticas para determinar umbrales automáticos
    rc_mean = eficiencia_df['relacion_horas_valor'].mean()
    rc_std = eficiencia_df['relacion_horas_valor'].std()
    rc_median = eficiencia_df['relacion_horas_valor'].median()
    rc_p75 = eficiencia_df['relacion_horas_valor'].quantile(0.75)
    rc_p80 = eficiencia_df['relacion_horas_valor'].quantile(0.80)
    
    # Opciones de umbral automático
    umbral_media_std = rc_mean + rc_std
    umbral_p75 = rc_p75
    umbral_p80 = rc_p80
    umbral_150_mediana = rc_median * 1.5
    
    # Configurar el factor de tolerancia (β) con opciones automáticas
    umbral_option = st.selectbox(
        "Método de umbral",
        options=[
            "Media + Desv. Estándar",
            "Percentil 80",
            "150% de la Mediana"
        ],
        index=0
    )
    
    if umbral_option == "Media + Desv. Estándar":
        beta = umbral_media_std
        st.info(f"Umbral calculado: {beta:.2f} (Media: {rc_mean:.2f}, Desv. Est.: {rc_std:.2f})")
    elif umbral_option == "Percentil 80":
        beta = umbral_p80
        st.info(f"Umbral calculado: {beta:.2f} (Percentil 80 de la distribución)")
    elif umbral_option == "150% de la Mediana":
        beta = umbral_150_mediana
        st.info(f"Umbral calculado: {beta:.2f} (150% de la mediana: {rc_median:.2f})")
    
    # Identificar clientes que exceden el umbral
    eficiencia_df['excede_umbral'] = eficiencia_df['relacion_horas_valor'] > beta
    
    # Mostrar alertas para clientes que exceden el umbral
    clientes_excedidos = eficiencia_df[eficiencia_df['excede_umbral']]
    
    # Preparar datos para el gráfico
    chart_df = eficiencia_df.copy()
    chart_df['color'] = chart_df['excede_umbral'].apply(lambda x: 'Excede umbral' if x else 'Dentro del umbral')
    
    # Crear gráfico de barras con Plotly
    fig = px.bar(
        chart_df,
        x='cliente',
        y='relacion_horas_valor',
        color='color',
        labels={
            'cliente': 'Cliente',
            'relacion_horas_valor': 'Relación Horas/Valor (Rc)',
            'color': 'Estado'
        },
        title=f'Relación Horas/Valor por Cliente (Umbral β = {beta})',
        color_discrete_map={
            'Excede umbral': 'red',
            'Dentro del umbral': 'green'
        }
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