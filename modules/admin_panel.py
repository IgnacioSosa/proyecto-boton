import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
import calendar
from .database import (get_connection, get_registros_dataframe, get_tecnicos_dataframe,
                      get_clientes_dataframe, get_tipos_dataframe, get_modalidades_dataframe,
                      get_roles_dataframe, get_users_dataframe, get_tipos_dataframe_with_roles, 
                      get_grupos_dataframe, get_nomina_dataframe, test_connection,
                      get_registros_dataframe_with_date_filter, get_user_rol_id, 
                      get_user_registros_dataframe, get_user_info, add_empleado_nomina, 
                      update_empleado_nomina, empleado_existe, get_departamentos_list,
                      generate_users_from_nomina, generate_roles_from_nomina, 
                      get_or_create_tecnico, get_or_create_cliente, get_or_create_tipo_tarea, 
                      get_or_create_modalidad, registrar_actividad, add_client, add_grupo, 
                      get_roles_by_grupo, update_grupo_roles, get_registros_by_rol_with_date_filter)
from .config import SYSTEM_ROLES, DEFAULT_VALUES, SYSTEM_LIMITS
from .nomina_management import render_nomina_edit_delete_forms
from .auth import create_user, validate_password, hash_password, is_2fa_enabled, unlock_user
from .utils import show_success_message, normalize_text, month_name_es
from .activity_logs import render_activity_logs

def render_admin_panel():
    """Renderiza el panel completo de administrador"""
    st.header("Panel de Administrador")
    
    tab_visualizacion, tab_gestion = st.tabs(["📊 Visualización de Datos", "⚙️ Gestión"])
    
    with tab_visualizacion:
        render_data_visualization()
    
    with tab_gestion:
        render_management_tabs()

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
                    client_tab, task_tab, group_tab, user_tab, data_tab = st.tabs(["Horas por Cliente", "Tipos de Tarea", "Grupos", "Horas por Usuario", "Tabla de Registros"])
                    with data_tab:
                        render_records_management(empty_df, rol['id_rol'])
        else:
            for i, (_, rol) in enumerate(roles_filtrados.iterrows()):
                with role_tabs[i]:
                    render_role_visualizations(df, rol['id_rol'], rol['nombre'])
    else:
        st.info("No hay roles configurados para visualizar datos")

def render_role_visualizations(df, rol_id, rol_nombre):
    """Renderiza las visualizaciones específicas para un rol"""
    from datetime import datetime
    import calendar
    
    # Agregar controles de filtro de fecha
    st.subheader(f"📊 Métricas - {rol_nombre}")
    
    # Crear columnas para los filtros
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
            key=f"filter_type_{rol_id}"
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
                key=f"year_{rol_id}"
            )
            
        with col3:
            months = [(i, month_name_es(i)) for i in range(1, 13)]
            selected_month = st.selectbox(
                "Mes",
                options=[m[0] for m in months],
                format_func=lambda x: month_name_es(x),
                index=datetime.now().month - 1,
                key=f"month_{rol_id}"
            )
            
        custom_month = selected_month
        custom_year = selected_year
    
    # Obtener datos filtrados
    role_df = get_registros_by_rol_with_date_filter(rol_id, filter_type, custom_month, custom_year)
    
    # Crear pestañas para las diferentes visualizaciones del rol
    # Siempre crear las pestañas, incluso si no hay datos
    client_tab, task_tab, group_tab, user_tab, data_tab = st.tabs(["Horas por Cliente", "Tipos de Tarea", "Grupos", "Horas por Usuario", "Tabla de Registros"])
    
    # Verificar si hay datos para mostrar
    if role_df.empty:
        period_text = {
            "current_month": "el mes actual",
            "custom_month": f"{month_name_es(custom_month)} {custom_year}" if custom_month and custom_year else "el período seleccionado",
            "all_time": "el período total"
        }[filter_type]
        
        # Mostrar mensaje en la pestaña de datos
        with data_tab:
            st.info(f"No hay datos para mostrar para el rol {rol_nombre} en {period_text}")
            # Aún así, permitir cargar datos
            render_records_management(pd.DataFrame(), rol_id)
        return
    
    with client_tab:
        st.subheader(f"Horas por Cliente - {rol_nombre}")
        
        # Agregar filtro por técnico
        tecnicos_disponibles = ['Todos'] + sorted(role_df['tecnico'].unique().tolist())
        tecnico_seleccionado = st.selectbox(
            "Filtrar por Usuario:",
            options=tecnicos_disponibles,
            key=f"tecnico_filter_cliente_{rol_id}"
        )
        
        # Filtrar datos según el técnico seleccionado
        if tecnico_seleccionado == 'Todos':
            df_filtrado = role_df
            titulo_grafico = f'Distribución por Cliente - {rol_nombre} (Todos los técnicos)'
        else:
            df_filtrado = role_df[role_df['tecnico'] == tecnico_seleccionado]
            titulo_grafico = f'Distribución por Cliente - {tecnico_seleccionado}'
        
        if df_filtrado.empty:
            st.info(f"No hay datos para el técnico {tecnico_seleccionado} en este período.")
        else:
            # Calcular horas por cliente para el filtro seleccionado
            horas_por_cliente = df_filtrado.groupby('cliente')['tiempo'].sum().reset_index()
            
            # Gráfico de torta por cliente
            fig1 = px.pie(horas_por_cliente, names='cliente', values='tiempo', 
                          title=titulo_grafico)
            st.plotly_chart(fig1, use_container_width=True)
            
            # Mostrar información detallada según el filtro
            if tecnico_seleccionado != 'Todos':
                # Para un técnico específico, mostrar análisis detallado
                st.subheader(f"Análisis detallado de {tecnico_seleccionado} por cliente")
                
                # Crear tabla con detalles por cliente
                detalle_cliente = df_filtrado.groupby('cliente').agg({
                    'tiempo': ['sum', 'count'],
                    'tipo_tarea': lambda x: ', '.join(x.unique()),
                    'fecha': ['min', 'max']
                }).round(2)
                
                # Aplanar columnas multinivel
                detalle_cliente.columns = ['Horas Totales', 'Cantidad de Registros', 'Tipos de Tarea', 'Primera Fecha', 'Última Fecha']
                detalle_cliente = detalle_cliente.reset_index()
                
                # Calcular porcentaje de distribución
                total_horas_tecnico = detalle_cliente['Horas Totales'].sum()
                detalle_cliente['Porcentaje'] = (detalle_cliente['Horas Totales'] / total_horas_tecnico * 100).round(1)
                
                # Ordenar por horas totales descendente
                detalle_cliente = detalle_cliente.sort_values('Horas Totales', ascending=False)
                
                st.dataframe(detalle_cliente, use_container_width=True)
                
                # Mostrar métricas resumen
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total de Horas", f"{total_horas_tecnico:.1f}")
                with col2:
                    st.metric("Clientes Atendidos", len(detalle_cliente))
                with col3:
                    st.metric("Total de Registros", detalle_cliente['Cantidad de Registros'].sum())
                with col4:
                    cliente_principal = detalle_cliente.iloc[0]['cliente'] if len(detalle_cliente) > 0 else "N/A"
                    st.metric("Cliente Principal", cliente_principal)
                               
            else:
                # Para todos los técnicos, mostrar vista general
                render_client_hours_detail(horas_por_cliente)
    
    with task_tab:
        st.subheader(f"Tipos de Tarea - {rol_nombre}")
        
        # Agregar filtro por técnico
        tecnicos_disponibles = ['Todos'] + sorted(role_df['tecnico'].unique().tolist())
        tecnico_seleccionado = st.selectbox(
            "Filtrar por Usuario:",
            options=tecnicos_disponibles,
            key=f"tecnico_filter_{rol_id}"
        )
        
        # Filtrar datos según el técnico seleccionado
        if tecnico_seleccionado == 'Todos':
            df_filtrado = role_df
            titulo_grafico = f'Distribución por Tipo de Tarea - {rol_nombre} (Todos los técnicos)'
        else:
            df_filtrado = role_df[role_df['tecnico'] == tecnico_seleccionado]
            titulo_grafico = f'Distribución por Tipo de Tarea - {tecnico_seleccionado}'
        
        if df_filtrado.empty:
            st.info(f"No hay datos para el técnico {tecnico_seleccionado} en este período.")
        else:
            # Calcular horas por tipo de tarea para el filtro seleccionado
            horas_por_tipo = df_filtrado.groupby('tipo_tarea')['tiempo'].sum().reset_index()
            
            # Gráfico de torta por tipo de tarea
            fig2 = px.pie(horas_por_tipo, names='tipo_tarea', values='tiempo', 
                          title=titulo_grafico)
            st.plotly_chart(fig2, use_container_width=True)
            
            # Mostrar tabla detallada con información adicional
            if tecnico_seleccionado != 'Todos':
                # Para un técnico específico, mostrar detalles adicionales
                st.subheader(f"Detalle de contribuciones de {tecnico_seleccionado}")
                
                # Crear tabla con más detalles
                detalle_tecnico = df_filtrado.groupby('tipo_tarea').agg({
                    'tiempo': ['sum', 'count'],
                    'cliente': lambda x: ', '.join(x.unique())
                }).round(2)
                
                # Aplanar columnas multinivel
                detalle_tecnico.columns = ['Horas Totales', 'Cantidad de Registros', 'Clientes']
                detalle_tecnico = detalle_tecnico.reset_index()
                
                # Calcular porcentaje de contribución
                total_horas_tecnico = detalle_tecnico['Horas Totales'].sum()
                detalle_tecnico['Porcentaje'] = (detalle_tecnico['Horas Totales'] / total_horas_tecnico * 100).round(1)
                
                st.dataframe(detalle_tecnico, use_container_width=True)
                
                # Mostrar métricas resumen
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total de Horas", f"{total_horas_tecnico:.1f}")
                with col2:
                    st.metric("Tipos de Tarea", len(detalle_tecnico))
                with col3:
                    st.metric("Total de Registros", detalle_tecnico['Cantidad de Registros'].sum())
            else:
                # Para todos los técnicos, mostrar tabla simple
                st.dataframe(horas_por_tipo, use_container_width=True)
    
    # Nueva pestaña para visualización por grupos
    with group_tab:
        st.subheader(f"Grupos - {rol_nombre}")
        
        # Agregar filtro por técnico
        tecnicos_disponibles = ['Todos'] + sorted(role_df['tecnico'].unique().tolist())
        tecnico_seleccionado = st.selectbox(
            "Filtrar por Usuario:",
            options=tecnicos_disponibles,
            key=f"tecnico_filter_grupo_{rol_id}"
        )
        
        # Filtrar datos según el técnico seleccionado
        if tecnico_seleccionado == 'Todos':
            df_filtrado = role_df
            titulo_grafico = f'Distribución por Grupo - {rol_nombre} (Todos los técnicos)'
        else:
            df_filtrado = role_df[role_df['tecnico'] == tecnico_seleccionado]
            titulo_grafico = f'Distribución por Grupo - {tecnico_seleccionado}'
        
        if df_filtrado.empty:
            st.info(f"No hay datos para el técnico {tecnico_seleccionado} en este período.")
        else:
            # Asegurarse de que todos los registros tengan un grupo asignado
            df_filtrado['grupo'] = df_filtrado['grupo'].fillna('General')
            
            # Calcular horas por grupo para el filtro seleccionado
            horas_por_grupo = df_filtrado.groupby('grupo')['tiempo'].sum().reset_index()
            
            # Gráfico de torta por grupo
            fig_grupo = px.pie(horas_por_grupo, names='grupo', values='tiempo', 
                          title=titulo_grafico)
            st.plotly_chart(fig_grupo, use_container_width=True)
            
            # Mostrar tabla detallada con información adicional
            if tecnico_seleccionado != 'Todos':
                # Para un técnico específico, mostrar detalles adicionales
                st.subheader(f"Detalle de contribuciones de {tecnico_seleccionado} por grupo")
                
                # Crear tabla con más detalles
                detalle_grupo = df_filtrado.groupby('grupo').agg({
                    'tiempo': ['sum', 'count'],
                    'cliente': lambda x: ', '.join(sorted(set(x)))
                }).round(2)
                
                # Aplanar columnas multinivel
                detalle_grupo.columns = ['Horas Totales', 'Cantidad de Registros', 'Clientes']
                detalle_grupo = detalle_grupo.reset_index()
                
                # Calcular porcentaje de contribución
                total_horas_tecnico = detalle_grupo['Horas Totales'].sum()
                detalle_grupo['Porcentaje'] = (detalle_grupo['Horas Totales'] / total_horas_tecnico * 100).round(1)
                
                # Ordenar por horas totales descendente
                detalle_grupo = detalle_grupo.sort_values('Horas Totales', ascending=False)
                
                st.dataframe(detalle_grupo, use_container_width=True)
                
                # Mostrar métricas resumen
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total de Horas", f"{total_horas_tecnico:.1f}")
                with col2:
                    st.metric("Grupos", len(detalle_grupo))
                with col3:
                    grupo_principal = detalle_grupo.iloc[0]['grupo'] if len(detalle_grupo) > 0 else "N/A"
                    st.metric("Grupo Principal", grupo_principal)
            else:
                # Para todos los técnicos, mostrar vista general
                st.subheader("Detalle de horas por grupo")
                
                # Crear tabla con detalles por grupo
                detalle_grupo = df_filtrado.groupby('grupo').agg({
                    'tiempo': ['sum', 'count'],
                    'tecnico': lambda x: len(set(x)),
                    'cliente': lambda x: len(set(x))
                }).round(2)
                
                # Aplanar columnas multinivel
                detalle_grupo.columns = ['Horas Totales', 'Cantidad de Registros', 'Técnicos', 'Clientes']
                detalle_grupo = detalle_grupo.reset_index()
                
                # Calcular porcentaje de distribución
                total_horas = detalle_grupo['Horas Totales'].sum()
                detalle_grupo['Porcentaje'] = (detalle_grupo['Horas Totales'] / total_horas * 100).round(1)
                
                # Ordenar por horas totales descendente
                detalle_grupo = detalle_grupo.sort_values('Horas Totales', ascending=False)
                
                st.dataframe(detalle_grupo, use_container_width=True)
                
                # Mostrar métricas resumen
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total de Horas", f"{total_horas:.1f}")
                with col2:
                    st.metric("Grupos", len(detalle_grupo))
                with col3:
                    st.metric("Total de Registros", detalle_grupo['Cantidad de Registros'].sum())
                with col4:
                    grupo_principal = detalle_grupo.iloc[0]['grupo'] if len(detalle_grupo) > 0 else "N/A"
                    st.metric("Grupo Principal", grupo_principal)
    
    with user_tab:
        st.subheader(f"Horas por Usuario - {rol_nombre}")
        
        # Obtener lista de técnicos que son usuarios con rol técnico
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT (nombre || ' ' || apellido) as nombre_completo
            FROM usuarios 
            WHERE rol_id NOT IN (
                SELECT id_rol FROM roles WHERE nombre IN (%s, %s, %s)
            )
        """, (SYSTEM_ROLES['ADMIN'], SYSTEM_ROLES['SIN_ROL'], SYSTEM_ROLES['HIPERVISOR']))
        tecnicos_usuarios = [row[0] for row in c.fetchall()]
        conn.close()
        
        # Calcular horas por técnico para este rol
        horas_por_tecnico = role_df.groupby('tecnico')['tiempo'].sum().reset_index()
        
        # Si es el panel de admin, filtrar los técnicos que son usuarios
        if rol_nombre == 'admin':
            horas_por_tecnico = horas_por_tecnico[~horas_por_tecnico['tecnico'].isin(tecnicos_usuarios)]
        
        # Gráfico de barras por técnico
        fig3 = px.bar(horas_por_tecnico, x='tecnico', y='tiempo', 
                      title=f'Horas por Usuario - {rol_nombre}',
                      labels={'tecnico': 'Usuario', 'tiempo': 'Horas Totales'},
                      color='tecnico',
                      color_discrete_sequence=px.colors.qualitative.Set3)
        st.plotly_chart(fig3, use_container_width=True)
        
        # Mostrar tabla detallada
        st.dataframe(horas_por_tecnico, use_container_width=True)
        
    with data_tab:
        render_records_management(role_df, rol_id)

def render_client_hours_detail(horas_por_cliente):
    """Renderiza el detalle de horas por cliente"""
    st.subheader("Detalle de Horas por Cliente")
    
    # Crear un contenedor con borde para mejor visualización
    with st.container():
        # Dividir en columnas para mejor organización
        num_clientes = len(horas_por_cliente)
        if num_clientes > 0:
            # Crear columnas dinámicamente (máximo 3 por fila)
            cols_per_row = min(3, num_clientes)
            rows_needed = (num_clientes + cols_per_row - 1) // cols_per_row
            
            for row in range(rows_needed):
                cols = st.columns(cols_per_row)
                for col_idx in range(cols_per_row):
                    cliente_idx = row * cols_per_row + col_idx
                    if cliente_idx < num_clientes:
                        cliente_data = horas_por_cliente.iloc[cliente_idx]
                        with cols[col_idx]:
                            st.metric(
                                label=f"🏢 {cliente_data['cliente']}",
                                value=f"{cliente_data['tiempo']} hrs"
                            )

def render_excel_uploader(key="default_excel_uploader"):
    """Función reutilizable para cargar archivos Excel"""
    with st.expander("📁 Cargar datos desde archivo Excel"):
        uploaded_file = st.file_uploader(
            "Selecciona un archivo Excel (.xls o .xlsx)",
            type=['xlsx', 'xls'],
            key=key
        )
        
        excel_df = None
        if uploaded_file is not None:
            try:
                # Importar explícitamente openpyxl antes de leer el Excel
                import openpyxl
                
                # Leer todas las hojas del Excel para mostrar sus nombres
                excel_file = pd.ExcelFile(uploaded_file, engine='openpyxl')
                sheet_names = excel_file.sheet_names
                
                # Permitir al usuario seleccionar la hoja que desea cargar
                selected_sheet = st.selectbox(
                    "Selecciona la hoja a cargar:",
                    options=sheet_names,
                    index=1 if len(sheet_names) > 1 else 0,  # Por defecto seleccionar la segunda hoja si existe
                    key=f"{key}_sheet_selector"
                )
                
                # Leer la hoja seleccionada
                excel_df = pd.read_excel(uploaded_file, sheet_name=selected_sheet, engine='openpyxl')
                
                st.subheader("Vista previa del archivo")
                st.dataframe(excel_df.head(), use_container_width=True)
                
                # NUEVA FUNCIONALIDAD: Detección automática de columnas
                def detect_name_columns(df):
                    """Detecta automáticamente columnas de nombres y apellidos"""
                    nombre_patterns = ['NOMBRE', 'NAME', 'FIRST_NAME', 'FIRSTNAME', 'NOMBRES']
                    apellido_patterns = ['APELLIDO', 'APELLIDOS', 'LASTNAME', 'LAST_NAME', 'SURNAME']
                    
                    detected = {'nombres': [], 'apellidos': []}
                    
                    for col in df.columns:
                        col_upper = col.upper().strip()
                        
                        for pattern in nombre_patterns:
                            if pattern in col_upper:
                                detected['nombres'].append(col)
                                break
                        
                        for pattern in apellido_patterns:
                            if pattern in col_upper:
                                detected['apellidos'].append(col)
                                break
                    
                    return detected
                
                # Detectar columnas automáticamente
                detected_columns = detect_name_columns(excel_df)
                
                # Mostrar información sobre las columnas disponibles
                st.info(f"📋 **Todas las columnas disponibles:** {', '.join(excel_df.columns.tolist())}")
                
            except Exception as e:
                st.error(f"Error al leer el archivo: {str(e)}")
                return uploaded_file, None
        
        return uploaded_file, excel_df

def render_records_management(df, role_id=None):
    """Renderiza la gestión de registros para administradores"""
    st.subheader("Gestión de Registros")
    
    # Usar la función reutilizable para cargar Excel
    uploaded_file, excel_df = render_excel_uploader(
        key=f"excel_upload_{role_id if role_id else 'default'}"
    )
    
    if uploaded_file is not None and excel_df is not None:
        # Validar y estandarizar formato
        # CORREGIDO: Hacer la clave única basándose en el role_id
        button_key = f"process_excel_{role_id if role_id else 'default'}"
        if st.button("Procesar y cargar datos", key=button_key):
            success_count, error_count, duplicate_count = process_excel_data(excel_df)
            
            if success_count > 0:
                show_success_message(f"✅ {success_count} registros cargados exitosamente", 3)
            if duplicate_count > 0:
                st.warning(f"⚠️ {duplicate_count} registros duplicados omitidos")
                time.sleep(2)  # Pausa para que se vea el mensaje
            
            # Solo recargar si hubo registros exitosos
            if success_count > 0:
                time.sleep(1)  # Pausa adicional antes de recargar
                st.rerun()
    
    # Reordenar las columnas para que 'id' aparezca primero
    if 'id' in df.columns:
        # Obtener todas las columnas excepto 'id'
        other_columns = [col for col in df.columns if col != 'id']
        # Reordenar con 'id' primero, seguido de las demás columnas
        df = df[['id'] + other_columns]
    
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Agregar funcionalidad para editar o eliminar registros (solo admin)
    with st.expander("Editar o Eliminar Registro (Admin)"):
        if not df.empty:
            registro_ids = df['id'].tolist()
            registro_fechas = df['fecha'].tolist()
            registro_tecnicos = df['tecnico'].tolist()
            registro_clientes = df['cliente'].tolist()
            registro_tareas = df['tarea_realizada'].tolist()
            registro_tiempos = df['tiempo'].tolist()
            registro_tipos = df['tipo_tarea'].tolist()
            
            # Crear opciones más detalladas
            registro_options = [
                f"ID: {rid} | {rfecha} | {rtecnico} | {rcliente} | {rtipo} | {rtarea[:30]}{'...' if len(rtarea) > 30 else ''} | {rtiempo}h" 
                for rid, rfecha, rtecnico, rcliente, rtipo, rtarea, rtiempo in 
                zip(registro_ids, registro_fechas, registro_tecnicos, registro_clientes, registro_tipos, registro_tareas, registro_tiempos)
            ]
            
            selected_registro_admin = st.selectbox(
                "Seleccionar Registro", 
                options=registro_options, 
                key=f"select_registro_admin_{role_id if role_id else 'default'}",
                help="Formato: ID | Fecha | Técnico | Cliente | Tipo | Tarea | Tiempo"
            )
            
            if selected_registro_admin:
                # Extraer el ID del registro seleccionado
                registro_id_admin = int(selected_registro_admin.split(' | ')[0].replace('ID: ', ''))
                
                # Obtener datos del registro seleccionado
                registro_seleccionado_admin = df[df['id'] == registro_id_admin].iloc[0]
                
                # Mostrar vista previa del registro seleccionado
                st.markdown("**Vista previa del registro seleccionado:**")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.info(f"**Fecha:** {registro_seleccionado_admin['fecha']}\n**Técnico:** {registro_seleccionado_admin['tecnico']}")
                with col2:
                    st.info(f"**Cliente:** {registro_seleccionado_admin['cliente']}\n**Tipo:** {registro_seleccionado_admin['tipo_tarea']}")
                with col3:
                    st.info(f"**Tiempo:** {registro_seleccionado_admin['tiempo']} horas\n**Modalidad:** {registro_seleccionado_admin['modalidad']}")
                
                # Crear pestañas para editar o eliminar
                edit_tab_admin, delete_tab_admin = st.tabs(["Editar", "Eliminar"])
                
                with edit_tab_admin:
                    render_admin_edit_form(registro_seleccionado_admin, registro_id_admin, role_id)
                
                with delete_tab_admin:
                    render_admin_delete_form(registro_seleccionado_admin, registro_id_admin, role_id)
        else:
            st.info("No hay registros para gestionar.")

def render_admin_edit_form(registro_seleccionado, registro_id, role_id=None):
    """Renderiza el formulario de edición para administradores"""
    from datetime import datetime
    import calendar
    
    # Formulario para editar el registro
    fecha_str = registro_seleccionado['fecha']
    try:
        fecha_obj = datetime.strptime(fecha_str, '%d/%m/%y')
    except ValueError:
        try:
            fecha_obj = datetime.strptime(fecha_str, '%d/%m/%Y')
        except ValueError:
            fecha_obj = datetime.today()
    
    fecha_edit_admin = st.date_input("Fecha", value=fecha_obj, key=f"admin_edit_fecha_{role_id if role_id else 'default'}")
    fecha_formateada_edit_admin = fecha_edit_admin.strftime('%d/%m/%y')
    
    # Obtener listas de técnicos, clientes, tipos y modalidades
    tecnicos_df = get_tecnicos_dataframe()
    clientes_df = get_clientes_dataframe()
    tipos_df = get_tipos_dataframe()
    modalidades_df = get_modalidades_dataframe()
    
    # Selección de técnico (admin puede cambiar cualquier técnico)
    tecnico_options = tecnicos_df['nombre'].tolist()
    tecnico_index = tecnico_options.index(registro_seleccionado['tecnico']) if registro_seleccionado['tecnico'] in tecnico_options else 0
    tecnico_selected_edit_admin = st.selectbox("Técnico", options=tecnico_options, index=tecnico_index, key=f"admin_edit_tecnico_{role_id if role_id else 'default'}")
    
    # Selección de grupo (sector)
    # Para administradores, mostrar todos los grupos disponibles
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id_grupo, nombre FROM grupos ORDER BY nombre")
    grupos = c.fetchall()
    conn.close()
    
    grupo_names = [grupo[1] for grupo in grupos]
    
    # Asegurarse de que "General" esté al principio
    if "General" not in grupo_names:
        grupo_names.insert(0, "General")
    else:
        grupo_names.remove("General")
        grupo_names.insert(0, "General")
    
    # Determinar el índice del grupo actual
    grupo_actual = registro_seleccionado.get('grupo', "General")
    if pd.isna(grupo_actual) or not grupo_actual:
        grupo_actual = "General"
    
    grupo_index = grupo_names.index(grupo_actual) if grupo_actual in grupo_names else 0
    grupo_selected_edit_admin = st.selectbox("Sector:", options=grupo_names, index=grupo_index, key=f"admin_edit_grupo_{role_id if role_id else 'default'}")
    
    # Selección de cliente
    cliente_options = clientes_df['nombre'].tolist()
    cliente_index = cliente_options.index(registro_seleccionado['cliente']) if registro_seleccionado['cliente'] in cliente_options else 0
    cliente_selected_edit_admin = st.selectbox("Cliente", options=cliente_options, index=cliente_index, key=f"admin_edit_cliente_{role_id if role_id else 'default'}")
    
    # Selección de tipo de tarea
    tipo_options = tipos_df['descripcion'].tolist()
    tipo_index = tipo_options.index(registro_seleccionado['tipo_tarea']) if registro_seleccionado['tipo_tarea'] in tipo_options else 0
    tipo_selected_edit_admin = st.selectbox("Tipo de Tarea", options=tipo_options, index=tipo_index, key=f"admin_edit_tipo_{role_id if role_id else 'default'}")
    
    # Selección de modalidad
    modalidad_options = modalidades_df['descripcion'].tolist()
    modalidad_index = modalidad_options.index(registro_seleccionado['modalidad']) if registro_seleccionado['modalidad'] in modalidad_options else 0
    modalidad_selected_edit_admin = st.selectbox("Modalidad", options=modalidad_options, index=modalidad_index, key=f"admin_edit_modalidad_{role_id if role_id else 'default'}")
    
    # Campos adicionales
    tarea_realizada_edit_admin = st.text_input("Tarea Realizada", value=registro_seleccionado['tarea_realizada'], key=f"admin_edit_tarea_{role_id if role_id else 'default'}")
    numero_ticket_edit_admin = st.text_input("Número de Ticket", value=registro_seleccionado['numero_ticket'], key=f"admin_edit_ticket_{role_id if role_id else 'default'}")
    tiempo_edit_admin = st.number_input("Tiempo (horas)", min_value=0.0, step=0.5, value=float(registro_seleccionado['tiempo']), key=f"admin_edit_tiempo_{role_id if role_id else 'default'}")
    descripcion_edit_admin = st.text_area("Descripción", value=registro_seleccionado['descripcion'] if pd.notna(registro_seleccionado['descripcion']) else "", key=f"admin_edit_descripcion_{role_id if role_id else 'default'}")
    
    # Mes (automático basado en la fecha)
    mes_edit_admin = month_name_es(fecha_edit_admin.month)
    
    if st.button("Guardar Cambios (Admin)", key=f"admin_save_registro_edit_{role_id if role_id else 'default'}"):
        if not tarea_realizada_edit_admin:
            st.error("La tarea realizada es obligatoria.")
        elif tiempo_edit_admin <= 0:
            st.error("El tiempo debe ser mayor que cero.")
        else:
            conn = get_connection()
            c = conn.cursor()
            
            # Obtener IDs
            c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = %s", (tecnico_selected_edit_admin,))
            id_tecnico_admin = c.fetchone()[0]
            
            c.execute("SELECT id_cliente FROM clientes WHERE nombre = %s", (cliente_selected_edit_admin,))
            id_cliente_admin = c.fetchone()[0]
            
            c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = %s", (tipo_selected_edit_admin,))
            id_tipo_admin = c.fetchone()[0]
            
            c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE descripcion = %s", (modalidad_selected_edit_admin,))
            id_modalidad_admin = c.fetchone()[0]
            
            # Verificar duplicados manualmente
            c.execute('''
                SELECT id FROM registros 
                WHERE fecha = %s AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s
                AND id_modalidad = %s AND tarea_realizada = %s AND tiempo = %s AND id != %s
            ''', (fecha_formateada_edit_admin, id_tecnico_admin, id_cliente_admin, id_tipo_admin, 
                  id_modalidad_admin, tarea_realizada_edit_admin, tiempo_edit_admin, registro_id))
            
            if c.fetchone():
                st.error("Ya existe un registro con estos mismos datos. No se puede crear un duplicado.")
            else:
                # Actualizar registro
                c.execute('''
                    UPDATE registros SET 
                    fecha = %s, id_tecnico = %s, id_cliente = %s, id_tipo = %s, id_modalidad = %s,
                    tarea_realizada = %s, numero_ticket = %s, tiempo = %s, descripcion = %s, mes = %s, grupo = %s
                    WHERE id = %s
                ''', (fecha_formateada_edit_admin, id_tecnico_admin, id_cliente_admin, id_tipo_admin, 
                      id_modalidad_admin, tarea_realizada_edit_admin, numero_ticket_edit_admin, 
                      tiempo_edit_admin, descripcion_edit_admin, mes_edit_admin, grupo_selected_edit_admin, registro_id))
                
                conn.commit()
                show_success_message("✅ Registro actualizado exitosamente. Se ha verificado que no existen duplicados.", 1.5)
            
            conn.close()

def render_admin_delete_form(registro_seleccionado, registro_id, role_id=None):
    """Renderiza el formulario de eliminación para administradores"""
    st.subheader("Eliminar Registro")
    st.warning("¿Estás seguro de que deseas eliminar este registro? Esta acción no se puede deshacer.")
    
    # Mostrar información del registro a eliminar
    st.info(f"**Registro a eliminar:**\n"
            f"- **ID:** {registro_seleccionado['id']}\n"
            f"- **Fecha:** {registro_seleccionado['fecha']}\n"
            f"- **Técnico:** {registro_seleccionado['tecnico']}\n"
            f"- **Cliente:** {registro_seleccionado['cliente']}\n"
            f"- **Tarea:** {registro_seleccionado['tarea_realizada']}\n"
            f"- **Tiempo:** {registro_seleccionado['tiempo']} horas")
    
    if st.button("Eliminar Registro", key=f"admin_delete_registro_btn_{role_id if role_id else 'default'}", type="primary"):
        conn = get_connection()
        c = conn.cursor()
        
        # Eliminar el registro (administrador puede eliminar cualquier registro)
        c.execute("DELETE FROM registros WHERE id = %s", (registro_id,))
        conn.commit()
        conn.close()
        
        show_success_message("✅ Registro eliminado exitosamente. La entrada ha sido completamente removida del sistema.", 1.5)

def render_management_tabs():
    """Renderiza las pestañas de gestión"""
    # Crear sub-pestañas para gestionar diferentes entidades
    subtab_usuarios, subtab_clientes, subtab_tipos, subtab_modalidades, subtab_roles, subtab_grupos, subtab_nomina, subtab_registros = st.tabs([
        "👥 Usuarios", "🏢 Clientes", "📋 Tipos de Tarea", "🔄 Modalidades", "🔑 Roles", "👪 Grupos", "🏠 Nómina", "📝 Registros"
    ])
    
    # Gestión de Usuarios
    with subtab_usuarios:
        render_user_management()
    
    # Gestión de Clientes
    with subtab_clientes:
        render_client_management()
    
    # Gestión de Tipos de Tarea
    with subtab_tipos:
        render_task_type_management()
    
    # Gestión de Modalidades
    with subtab_modalidades:
        render_modality_management()
        
    # Gestión de Roles
    with subtab_roles:
        render_role_management()
    
    # Gestión de Grupos
    with subtab_grupos:
        render_grupo_management()
        
    # Gestión de Nómina
    with subtab_nomina:
        render_nomina_management()
        
    # Registros de actividad
    with subtab_registros:
        try:
            render_activity_logs()
        except Exception as e:
            from .utils import log_app_error
            log_app_error(e, module="admin_panel", function="render_management_tabs")
            st.error(f"Error al mostrar los registros de actividad: {str(e)}")
def render_user_management():
    """Renderiza la gestión de usuarios"""
    st.subheader("Gestión de Usuarios")
    
    # Obtener roles disponibles
    from .database import get_roles_dataframe
    roles_df = get_roles_dataframe(exclude_hidden=False) 
    
    # Botón para generar usuarios automáticamente desde la nómina
    with st.expander("👤 Generar Usuarios desde Nómina", expanded=True):
        st.info("Esta función creará usuarios automáticamente para los empleados en la nómina que aún no tienen usuario asociado.")
        
        # Checkbox para habilitar usuarios durante creación
        enable_users_on_creation = st.checkbox(
            "Habilitar usuarios durante creación", 
            value=False, 
            help="Si está marcado, los usuarios creados estarán activos inmediatamente. Si no está marcado, los usuarios se crearán deshabilitados."
        )
        
        if st.button("🔄 Generar Usuarios", type="primary", key="generate_users_user_tab"):
            with st.spinner("Generando usuarios..."):
                # Llamar a la función para generar usuarios con el parámetro de activación
                stats = generate_users_from_nomina(enable_users=enable_users_on_creation)
                
                # Mostrar siempre un mensaje, independientemente del resultado
                if stats["total_empleados"] == 0:
                    st.error("⚠️ NO SE DETECTARON NUEVOS USUARIOS PARA GENERAR. Todos los empleados en la nómina ya tienen usuarios asociados o no hay empleados en la nómina.")
                else:
                    if stats["usuarios_creados"] > 0:
                        st.success(f"✅ Se crearon {stats['usuarios_creados']} nuevos usuarios")
                        st.info(f"📊 También se crearon {stats['tecnicos_creados']} técnicos asociados")
                        
                        # Mostrar tabla con usuarios y contraseñas generadas
                        if stats.get('usuarios_generados'):
                            st.subheader("👥 Usuarios Generados")
                            
                            # Crear DataFrame para mostrar
                            import pandas as pd
                            df_usuarios = pd.DataFrame(stats['usuarios_generados'])
                            
                            # Mostrar tabla
                            st.dataframe(df_usuarios, use_container_width=True)
                            
                            # Botón para descargar CSV
                            csv = df_usuarios.to_csv(index=False)
                            st.download_button(
                                label="📥 Descargar lista de usuarios (CSV)",
                                data=csv,
                                file_name=f"usuarios_generados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                mime="text/csv"
                            )
                    
                    # Mostrar información sobre usuarios no generados por falta de correo
                    if stats["usuarios_sin_email"] > 0:
                        st.warning(f"⚠️ No se generaron {stats['usuarios_sin_email']} usuarios por falta de correo electrónico")
                        with st.expander("Ver empleados sin correo"):
                            for empleado in stats["empleados_sin_email"]:
                                st.write(f"• {empleado}")
                    
                    # Mostrar información sobre usuarios duplicados omitidos
                    if stats["usuarios_duplicados"] > 0:
                        st.info(f"ℹ️ Se omitieron {stats['usuarios_duplicados']} usuarios duplicados")
                        with st.expander("Ver empleados duplicados omitidos"):
                            for empleado in stats["empleados_duplicados"]:
                                st.write(f"• {empleado}")
                    
                    # Mostrar errores si los hay
                    if stats["errores"]:
                        st.error(f"❌ Ocurrieron {len(stats['errores'])} errores durante la creación de usuarios")
                        with st.expander("Ver errores"):
                            for error in stats["errores"]:
                                st.error(error)
    
    
    # Formulario para crear usuarios 
    with st.expander("Crear Usuario"):
    
        # Campos para el formulario
        new_user_username = st.text_input("Usuario", key="new_user_username")
        new_user_password = st.text_input("Contraseña", type="password", key="new_user_password")
        new_user_nombre = st.text_input("Nombre", key="new_user_nombre")
        new_user_apellido = st.text_input("Apellido", key="new_user_apellido")
        
        # Reemplazar checkbox por desplegable de roles
        rol_options = [f"{row['id_rol']} - {row['nombre']}" for _, row in roles_df.iterrows()]
        # Encontrar el índice de la opción 'sin_rol' para establecerla como predeterminada
        default_index = 0
        for i, option in enumerate(rol_options):
            if SYSTEM_ROLES['SIN_ROL'] in option.lower():
                default_index = i
                break
        
        selected_rol = st.selectbox("Rol", options=rol_options, index=default_index, key="new_user_rol")
        
        # Verificar que selected_rol no sea None antes de hacer split
        if selected_rol is not None:
            rol_id = int(selected_rol.split(' - ')[0])
        else:
            # Usar un valor predeterminado o mostrar un mensaje de error
            st.error("Por favor selecciona un rol")
            rol_id = None  # O un valor predeterminado como el ID de 'sin_rol'
        
        # Información sobre requisitos de contraseña
        st.info("La contraseña debe tener al menos 8 caracteres, una letra mayúscula, una letra minúscula, un número y un carácter especial.")
        
        # Botón para crear usuario
        if st.button("Crear Usuario", key="create_user_btn"):
            if new_user_username and new_user_password:
                if create_user(new_user_username, new_user_password, 
                              new_user_nombre, new_user_apellido, None, rol_id):
                    st.success(f"Usuario {new_user_username} creado exitosamente.")
                    st.rerun()
                # El mensaje de error ahora lo maneja la función create_user
            else:
                st.error("Usuario y contraseña son obligatorios.")
    
    # Tabla de usuarios existentes
    st.subheader("Usuarios Existentes")
    users_df = get_users_dataframe()
    
    # Mostrar tabla de usuarios
    if not users_df.empty:
        # Ocultar columna id
        if 'id' in users_df.columns:
            st.dataframe(users_df.drop(columns=['id']), use_container_width=True)
        else:
            st.dataframe(users_df, use_container_width=True)
    else:
        st.dataframe(users_df, use_container_width=True)
    
    # Formularios para editar y eliminar usuarios
    render_user_edit_form(users_df, roles_df)
    render_user_delete_form(users_df)

def render_user_edit_form(users_df, roles_df):
    """Renderiza el formulario de edición de usuarios"""
    # Formulario para editar usuarios
    with st.expander("Editar Usuario"):
        if not users_df.empty:
            user_ids = users_df['id'].tolist()
            user_usernames = users_df['username'].tolist()
            user_options = [f"{uid} - {uname}" for uid, uname in zip(user_ids, user_usernames)]
            
            selected_user_edit = st.selectbox("Seleccionar Usuario para Editar", 
                                             options=user_options, key="select_user_edit")
            if selected_user_edit:
                user_id = int(selected_user_edit.split(' - ')[0])
                user_row = users_df[users_df['id'] == user_id].iloc[0]
                
                # No permitir editar al propio usuario completamente
                disable_critical_fields = user_id == st.session_state.user_id
                if disable_critical_fields:
                    st.warning("Editando tu propio usuario. Algunos campos están restringidos.")
                
                # Campos editables
                edit_nombre = st.text_input("Nombre", value=user_row['nombre'] or "", 
                                           key="edit_user_nombre")
                edit_apellido = st.text_input("Apellido", value=user_row['apellido'] or "", 
                                            key="edit_user_apellido")
                
                # Obtener el rol actual del usuario
                conn = get_connection()
                c = conn.cursor()
                c.execute("SELECT rol_id FROM usuarios WHERE id = %s", (user_id,))
                current_rol_id = c.fetchone()
                conn.close()
                
                # Filtrar roles para proteger al usuario admin
                if user_row['username'].lower() == 'admin':
                    # Para el usuario admin, mostrar solo el rol admin
                    admin_rol = roles_df[roles_df['nombre'].str.lower() == 'admin']
                    if not admin_rol.empty:
                        admin_rol_id = admin_rol.iloc[0]['id_rol']
                        rol_options = [f"{admin_rol_id} - admin"]
                        selected_rol = rol_options[0]
                        rol_id = admin_rol_id
                        st.info("El usuario 'admin' debe mantener el rol de administrador.")
                else:
                    # Para otros usuarios, mostrar todos los roles disponibles
                    rol_options = [f"{row['id_rol']} - {row['nombre']}" for _, row in roles_df.iterrows()]
                    
                    # Encontrar el índice del rol actual
                    default_index = 0
                    if current_rol_id and current_rol_id[0]:
                        for i, option in enumerate(rol_options):
                            if option.startswith(f"{current_rol_id[0]} -"):
                                default_index = i
                                break
                    
                    selected_rol = st.selectbox("Rol", options=rol_options, 
                                              index=default_index, key="edit_user_rol",
                                              disabled=disable_critical_fields)
                    rol_id = int(selected_rol.split(' - ')[0])
                
                edit_is_active = st.checkbox("Usuario Activo", value=bool(user_row['is_active']), 
                                            key="edit_user_is_active", disabled=disable_critical_fields)
                
                # Añadir checkbox para 2FA
                # Consultar directamente a la base de datos el estado actual de 2FA
                is_2fa_enabled_db = is_2fa_enabled(user_id)
                
                edit_is_2fa_enabled = st.checkbox("Autenticación de dos factores (2FA)", 
                                                value=is_2fa_enabled_db,
                                                key="edit_user_2fa",
                                                help="Habilita o deshabilita la autenticación de dos factores para este usuario")
                
                try:
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute("SELECT failed_attempts, lockout_until FROM usuarios WHERE id = %s", (user_id,))
                    lock_row = c.fetchone()
                    conn.close()
                except Exception as e:
                    from .logging_utils import log_app_error
                    log_app_error(e, module="admin_panel", function="render_user_edit_form")
                    lock_row = None

                failed_attempts = int(lock_row[0] or 0) if lock_row else 0
                lockout_until = lock_row[1] if lock_row else None

                from datetime import datetime
                now = datetime.utcnow()
                locked = bool(lockout_until and now < lockout_until)
                remaining_minutes = 0
                if locked:
                    remaining_minutes = max(0, int((lockout_until - now).total_seconds() // 60) + 1)
                    st.warning(f"Este usuario está bloqueado por intentos fallidos. Tiempo restante ~{remaining_minutes} minuto(s).")
                else:
                    st.info("El usuario no está bloqueado actualmente.")

                # Botón de desbloqueo siempre visible; deshabilitado si no hay bloqueo
                from .auth import unlock_user
                clicked = st.button(
                    "Desbloquear Usuario",
                    key=f"unlock_user_{user_id}",
                    type="primary",
                    use_container_width=True,
                    disabled=not locked
                )
                if clicked and locked:
                    if unlock_user(user_row['username']):
                        st.success("Usuario desbloqueado correctamente.")
                        st.rerun()
                    else:
                        st.error("No se pudo desbloquear el usuario.")
                
                # Opción para cambiar contraseña
                change_password = st.checkbox("Cambiar Contraseña", key="change_password_check")
                new_password = ""
                if change_password:
                    new_password = st.text_input("Nueva Contraseña", type="password", 
                                                key="edit_user_password")
                    st.info("La contraseña debe tener al menos 8 caracteres, una letra mayúscula, una letra minúscula, un número y un carácter especial.")
                
                if st.button("Guardar Cambios de Usuario", key="save_user_edit"):
                    conn = get_connection()
                    c = conn.cursor()
                    
                    try:
                        # Determinar si es admin basado en el rol
                        c.execute('SELECT nombre FROM roles WHERE id_rol = %s', (rol_id,))
                        rol_nombre = c.fetchone()
                        is_admin = False
                        if rol_nombre and rol_nombre[0].lower() == 'admin':
                            is_admin = True
                        
                        # Actualizar información básica incluyendo 2FA
                        c.execute("""UPDATE usuarios SET nombre = %s, apellido = %s, is_admin = %s, is_active = %s, 
                                     rol_id = %s, is_2fa_enabled = %s WHERE id = %s""", 
                                 (edit_nombre, edit_apellido, is_admin, edit_is_active, 
                                  rol_id, edit_is_2fa_enabled, user_id))
                        
                        # Si se deshabilita 2FA, limpiar el secreto TOTP
                        # COMENTADO: La columna totp_secret no existe en la tabla usuarios actual
                        # if not edit_is_2fa_enabled:
                        #     c.execute("UPDATE usuarios SET totp_secret = NULL WHERE id = %s", (user_id,))
                        
                        # Cambiar contraseña si se solicitó
                        if change_password and new_password:
                            # Validar la contraseña
                            is_valid, messages = validate_password(new_password)
                            if is_valid:
                                hashed_password = hash_password(new_password)
                                c.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s", 
                                         (hashed_password, user_id))
                            else:
                                for message in messages:
                                    st.error(message)
                                conn.close()
                                return
                        
                        conn.commit()
                        st.success("Usuario actualizado exitosamente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al actualizar usuario: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay usuarios para editar.")

def render_user_delete_form(users_df):
    """Renderiza el formulario de eliminación de usuarios"""
    # Formulario para eliminar usuarios
    with st.expander("Eliminar Usuario"):
        if not users_df.empty:
            user_ids = users_df['id'].tolist()
            user_usernames = users_df['username'].tolist()
            user_options = [f"{uid} - {uname}" for uid, uname in zip(user_ids, user_usernames)]
            
            selected_user_delete = st.selectbox("Seleccionar Usuario para Eliminar", 
                                               options=user_options, key="select_user_delete")
            if selected_user_delete:
                user_id = int(selected_user_delete.split(' - ')[0])
                user_row = users_df[users_df['id'] == user_id].iloc[0]
                
                # No permitir eliminar al propio usuario
                if user_id == st.session_state.user_id:
                    st.error("No puedes eliminar tu propio usuario.")
                else:
                    st.warning("¿Estás seguro de que deseas eliminar este usuario? Esta acción no se puede deshacer.")
                    
                    # Mostrar información del usuario a eliminar
                    st.info(f"**Usuario a eliminar:**\n"
                            f"- **ID:** {user_row['id']}\n"
                            f"- **Usuario:** {user_row['username']}\n"
                            f"- **Nombre:** {user_row['nombre'] or 'N/A'}\n"
                            f"- **Apellido:** {user_row['apellido'] or 'N/A'}\n"
                            f"- **Es Admin:** {'Sí' if user_row['is_admin'] else 'No'}\n"
                            f"- **Activo:** {'Sí' if user_row['is_active'] else 'No'}")
                    
                    if st.button("Eliminar Usuario", key="delete_user_btn", type="primary"):
                        delete_user(user_id, user_row['username'])
        else:
            st.info("No hay usuarios para eliminar.")

def delete_user(user_id, username):
    """Elimina un usuario y sus registros asociados"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Verificar si el usuario tiene registros asociados
        c.execute("SELECT COUNT(*) FROM registros WHERE usuario_id = %s", (user_id,))
        registro_count = c.fetchone()[0]
        
        # Eliminar primero todos los registros del usuario
        if registro_count > 0:
            c.execute("DELETE FROM registros WHERE usuario_id = %s", (user_id,))
            st.info(f"Se eliminaron {registro_count} registros asociados al usuario.")
        
        # Eliminar el usuario
        c.execute("DELETE FROM usuarios WHERE id = %s", (user_id,))
        conn.commit()
        
        if registro_count > 0:
            show_success_message(f"✅ Usuario '{username}' y sus {registro_count} registros eliminados exitosamente.", 1.5)
        else:
            show_success_message(f"✅ Usuario '{username}' eliminado exitosamente.", 1.5)
    except Exception as e:
        st.error(f"Error al eliminar usuario: {str(e)}")
    finally:
        conn.close()

def render_client_management():
    """Renderiza la gestión de clientes"""
    st.subheader("🏢 Gestión de Clientes")
    
    # Obtener clientes
    clients_df = get_clientes_dataframe()
    
    # Mostrar clientes existentes
    if not clients_df.empty:
        st.subheader("Clientes Existentes")
        st.dataframe(clients_df, use_container_width=True)
    else:
        st.info("No hay clientes registrados.")
    
    # Formulario para agregar nuevo cliente
    with st.expander("Agregar Nuevo Cliente"):
        new_client_name = st.text_input("Nombre del Cliente", key="new_client_name")
        new_client_address = st.text_input("Dirección (opcional)", key="new_client_address")
        new_client_phone = st.text_input("Teléfono (opcional)", key="new_client_phone")
        new_client_email = st.text_input("Email (opcional)", key="new_client_email")
        
        if st.button("Agregar Cliente", key="add_client_btn", type="primary"):
            if new_client_name:
                # Normalizar entrada del usuario
                new_client_name_normalized = ' '.join(new_client_name.strip().split()).title()
                
                conn = get_connection()
                c = conn.cursor()
                try:
                    c.execute("INSERT INTO clientes (nombre, direccion, telefono, email) VALUES (%s, %s, %s, %s)", 
                             (new_client_name_normalized, new_client_address or '', new_client_phone or '', new_client_email or ''))
                    conn.commit()
                    st.success(f"Cliente '{new_client_name_normalized}' agregado exitosamente.")
                    st.rerun()
                except Exception as e:
                    if "UNIQUE constraint failed" in str(e) or "duplicate key value" in str(e):
                        st.error(f"Ya existe un cliente con ese nombre: '{new_client_name_normalized}'")
                    else:
                        st.error(f"Error al agregar cliente: {str(e)}")
                finally:
                    conn.close()
            else:
                st.error("El nombre del cliente es obligatorio.")
    
    # Renderizar formularios de edición y eliminación
    render_client_edit_delete_forms(clients_df)

def render_client_edit_delete_forms(clients_df):
    """Renderiza formularios de edición y eliminación de clientes"""
    # Formulario para editar clientes
    with st.expander("Editar Cliente"):
        if not clients_df.empty:
            client_ids = clients_df['id_cliente'].tolist()
            client_names = clients_df['nombre'].tolist()
            client_options = [f"{cid} - {cname}" for cid, cname in zip(client_ids, client_names)]
            
            selected_client_edit = st.selectbox("Seleccionar Cliente para Editar", 
                                               options=client_options, key="select_client_edit")
            if selected_client_edit:
                client_id = int(selected_client_edit.split(' - ')[0])
                client_row = clients_df[clients_df['id_cliente'] == client_id].iloc[0]
                
                edit_client_name = st.text_input("Nombre del Cliente", value=client_row['nombre'], key="edit_client_name")
                
                if st.button("Guardar Cambios de Cliente", key="save_client_edit"):
                    if edit_client_name:
                        # Normalizar entrada del usuario
                        edit_client_name_normalized = ' '.join(edit_client_name.strip().split()).title()
                        
                        conn = get_connection()
                        c = conn.cursor()
                        try:
                            c.execute("UPDATE clientes SET nombre = %s WHERE id_cliente = %s", (edit_client_name_normalized, client_id))
                            conn.commit()
                            st.success(f"Cliente actualizado a '{edit_client_name_normalized}' exitosamente.")
                            st.rerun()
                        except Exception as e:
                            if "UNIQUE constraint failed" in str(e) or "duplicate key value" in str(e):
                                st.error(f"Ya existe un cliente con ese nombre: '{edit_client_name_normalized}'")
                            else:
                                st.error(f"Error al actualizar cliente: {str(e)}")
                        finally:
                            conn.close()
                    else:
                        st.error("El nombre del cliente es obligatorio.")
        else:
            st.info("No hay clientes para editar.")
    
    # Formulario para eliminar clientes
    with st.expander("Eliminar Cliente"):
        if not clients_df.empty:
            client_ids = clients_df['id_cliente'].tolist()
            client_names = clients_df['nombre'].tolist()
            client_options = [f"{cid} - {cname}" for cid, cname in zip(client_ids, client_names)]
            
            selected_client_delete = st.selectbox("Seleccionar Cliente para Eliminar", 
                                                 options=client_options, key="select_client_delete")
            if selected_client_delete:
                client_id = int(selected_client_delete.split(' - ')[0])
                client_row = clients_df[clients_df['id_cliente'] == client_id].iloc[0]
                
                st.warning("¿Estás seguro de que deseas eliminar este cliente? Esta acción no se puede deshacer.")
                st.info(f"**Cliente a eliminar:** {client_row['nombre']}")
                
                if st.button("Eliminar Cliente", key="delete_client_btn", type="primary"):
                    conn = get_connection()
                    c = conn.cursor()
                    try:
                        # Verificar si hay registros asociados
                        c.execute("SELECT COUNT(*) FROM registros WHERE id_cliente = %s", (client_id,))
                        registro_count = c.fetchone()[0]
                        
                        if registro_count > 0:
                            st.error(f"No se puede eliminar el cliente porque tiene {registro_count} registros asociados.")
                        else:
                            c.execute("DELETE FROM clientes WHERE id_cliente = %s", (client_id,))
                            conn.commit()
                            show_success_message(f"✅ Cliente '{client_row['nombre']}' eliminado exitosamente.", 1.5)
                    except Exception as e:
                        st.error(f"Error al eliminar cliente: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay clientes para eliminar.")

def clean_duplicate_task_types():
    """Limpia tipos de tarea duplicados manteniendo solo uno de cada tipo"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Obtener todos los tipos de tarea
        c.execute("SELECT id_tipo, descripcion FROM tipos_tarea ORDER BY id_tipo")
        tipos = c.fetchall()
        
        # Agrupar por descripción normalizada
        grupos_duplicados = {}
        for id_tipo, descripcion in tipos:
            desc_normalizada = ' '.join(descripcion.strip().split()).lower()
            if desc_normalizada not in grupos_duplicados:
                grupos_duplicados[desc_normalizada] = []
            grupos_duplicados[desc_normalizada].append((id_tipo, descripcion))
        
        # Identificar duplicados
        duplicados_a_eliminar = []
        grupos_con_duplicados = 0
        
        for desc_norm, grupo in grupos_duplicados.items():
            if len(grupo) > 1:
                grupos_con_duplicados += 1
                # Mantener el primero (ID más bajo) y marcar el resto para eliminación
                for id_tipo, descripcion in grupo[1:]:
                    duplicados_a_eliminar.append(id_tipo)
        
        # Eliminar duplicados
        deleted_count = 0
        for id_tipo in duplicados_a_eliminar:
            # Verificar si hay registros asociados
            c.execute("SELECT COUNT(*) FROM registros WHERE id_tipo = %s", (id_tipo,))
            registro_count = c.fetchone()[0]
            
            if registro_count == 0:
                # Eliminar asociaciones con roles primero
                c.execute("DELETE FROM tipos_tarea_roles WHERE id_tipo = %s", (id_tipo,))
                # Eliminar el tipo de tarea
                c.execute("DELETE FROM tipos_tarea WHERE id_tipo = %s", (id_tipo,))
                deleted_count += 1
        
        conn.commit()
        return deleted_count, grupos_con_duplicados
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def render_task_type_management():
    """Renderiza la gestión de tipos de tarea"""
    st.subheader("Gestión de Tipos de Tarea")
    
    # Inicializar contador para generar keys únicos
    if "task_type_counter" not in st.session_state:
        st.session_state.task_type_counter = 0
    
    # Obtener roles disponibles (excluyendo admin y sin_rol)
    roles_df = get_roles_dataframe(exclude_admin=True, exclude_sin_rol=True)
    
    # Formulario para agregar tipos de tarea
    with st.expander("Agregar Tipo de Tarea"):
        # Usar un key dinámico que cambia después de cada adición exitosa
        new_task_type = st.text_input(
            "Descripción del Tipo de Tarea", 
            key=f"new_task_type_{st.session_state.task_type_counter}"
        )
        
        # Selección múltiple de roles
        selected_roles = st.multiselect(
            "Roles que pueden acceder a este tipo de tarea",
            options=get_roles_dataframe(exclude_admin=True)['id_rol'].tolist(),
            format_func=lambda x: roles_df.loc[roles_df['id_rol'] == x, 'nombre'].iloc[0],
            key=f"new_task_type_roles_{st.session_state.task_type_counter}"
        )
        
        if st.button("Agregar Tipo de Tarea", key="add_task_type_btn"):
            if new_task_type:
                # Normalizar entrada del usuario
                new_task_type_normalized = ' '.join(new_task_type.strip().split()).title()
                
                conn = get_connection()
                c = conn.cursor()
                try:
                    # Verificar duplicados antes de insertar
                    c.execute("SELECT id_tipo FROM tipos_tarea WHERE LOWER(TRIM(descripcion)) = LOWER(TRIM(%s))", 
                             (new_task_type_normalized,))
                    existing = c.fetchone()
                    
                    if existing:
                        st.error(f"⚠️ Ya existe un tipo de tarea similar: '{new_task_type_normalized}'")
                    else:
                        # Insertar el tipo de tarea
                        c.execute("INSERT INTO tipos_tarea (descripcion) VALUES (%s) RETURNING id_tipo", (new_task_type_normalized,))
                        tipo_id = c.fetchone()[0]
                        
                        # Asociar con los roles seleccionados
                        for rol_id in selected_roles:
                            c.execute("INSERT INTO tipos_tarea_roles (id_tipo, id_rol) VALUES (%s, %s)", 
                                     (tipo_id, rol_id))
                        
                        conn.commit()
                        st.success(f"✅ Tipo de tarea '{new_task_type_normalized}' agregado exitosamente.")
                        st.session_state.task_type_counter += 1
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al agregar tipo de tarea: {str(e)}")
                finally:
                    conn.close()
            else:
                st.error("La descripción del tipo de tarea es obligatoria.")
    
    # Tabla de tipos de tarea existentes con sus roles asociados
    tipos_df = get_tipos_dataframe_with_roles()
    st.subheader("Tipos de Tarea Existentes")
    if not tipos_df.empty:
        # Ocultar columna id_tipo
        if 'id_tipo' in tipos_df.columns:
            st.dataframe(tipos_df.drop(columns=['id_tipo']), use_container_width=True)
        else:
            st.dataframe(tipos_df, use_container_width=True)
    else:
        st.info("No hay tipos de tarea registrados.")
    
    # Formularios para editar y eliminar tipos de tarea
    render_task_type_edit_delete_forms(tipos_df, roles_df)

def render_task_type_edit_delete_forms(tipos_df, roles_df):
    """Renderiza formularios de edición y eliminación de tipos de tarea"""
    # Formulario para editar tipos de tarea
    with st.expander("Editar Tipo de Tarea"):
        if not tipos_df.empty:
            tipo_ids = tipos_df['id_tipo'].tolist()
            tipo_descriptions = tipos_df['descripcion'].tolist()
            tipo_options = [f"{tid} - {tdesc}" for tid, tdesc in zip(tipo_ids, tipo_descriptions)]
            
            selected_tipo_edit = st.selectbox("Seleccionar Tipo de Tarea para Editar", 
                                             options=tipo_options, key="select_tipo_edit")
            if selected_tipo_edit:
                tipo_id = int(selected_tipo_edit.split(' - ')[0])
                tipo_row = tipos_df[tipos_df['id_tipo'] == tipo_id].iloc[0]
                
                edit_tipo_desc = st.text_input("Descripción del Tipo de Tarea", value=tipo_row['descripcion'], key="edit_tipo_desc")
                
                # Obtener roles actuales para este tipo de tarea
                conn = get_connection()
                c = conn.cursor()
                c.execute("SELECT id_rol FROM tipos_tarea_roles WHERE id_tipo = %s", (tipo_id,))
                current_roles = [row[0] for row in c.fetchall()]
                conn.close()
                
                # Obtener opciones disponibles
                available_roles = get_roles_dataframe(exclude_admin=True)['id_rol'].tolist()
                
                # Filtrar current_roles para incluir solo los que están disponibles
                filtered_current_roles = [role for role in current_roles if role in available_roles]
                
                # Selección múltiple de roles
                edit_selected_roles = st.multiselect(
                    "Roles que pueden acceder a este tipo de tarea",
                    options=available_roles,
                    default=filtered_current_roles,
                    format_func=lambda x: roles_df.loc[roles_df['id_rol'] == x, 'nombre'].iloc[0],
                    key="edit_task_type_roles"
                )
                
                if st.button("Guardar Cambios de Tipo de Tarea", key="save_tipo_edit"):
                    if edit_tipo_desc:
                            # Normalizar entrada del usuario
                            edit_tipo_desc_normalized = ' '.join(edit_tipo_desc.strip().split()).title()
                            
                            conn = get_connection()
                            c = conn.cursor()
                            try:
                                # Verificar duplicados antes de actualizar
                                c.execute("SELECT id_tipo FROM tipos_tarea WHERE LOWER(TRIM(descripcion)) = LOWER(TRIM(%s)) AND id_tipo != %s", 
                                         (edit_tipo_desc_normalized, tipo_id))
                                existing = c.fetchone()
                                
                                if existing:
                                    st.error(f"⚠️ Ya existe un tipo de tarea similar: '{edit_tipo_desc_normalized}'")
                                else:
                                    # Actualizar descripción del tipo de tarea
                                    c.execute("UPDATE tipos_tarea SET descripcion = %s WHERE id_tipo = %s", (edit_tipo_desc_normalized, tipo_id))
                                    
                                    # Eliminar todas las asociaciones actuales
                                    c.execute("DELETE FROM tipos_tarea_roles WHERE id_tipo = %s", (tipo_id,))
                                    
                                    # Crear nuevas asociaciones con los roles seleccionados
                                    for rol_id in edit_selected_roles:
                                        c.execute("INSERT INTO tipos_tarea_roles (id_tipo, id_rol) VALUES (%s, %s)", 
                                                 (tipo_id, rol_id))
                                    
                                    conn.commit()
                                    st.success(f"✅ Tipo de tarea actualizado a '{edit_tipo_desc_normalized}' exitosamente.")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error al actualizar tipo de tarea: {str(e)}")
                            finally:
                                conn.close()
                    else:
                        st.error("La descripción del tipo de tarea es obligatoria.")
        else:
            st.info("No hay tipos de tarea para editar.")
    
    # Formulario para eliminar tipos de tarea
    with st.expander("Eliminar Tipo de Tarea"):
        if not tipos_df.empty:
            tipo_ids = tipos_df['id_tipo'].tolist()
            tipo_descriptions = tipos_df['descripcion'].tolist()
            tipo_options = [f"{tid} - {tdesc}" for tid, tdesc in zip(tipo_ids, tipo_descriptions)]
            
            selected_tipo_delete = st.selectbox("Seleccionar Tipo de Tarea para Eliminar", 
                                               options=tipo_options, key="select_tipo_delete")
            if selected_tipo_delete:
                tipo_id = int(selected_tipo_delete.split(' - ')[0])
                tipo_row = tipos_df[tipos_df['id_tipo'] == tipo_id].iloc[0]
                
                st.warning("¿Estás seguro de que deseas eliminar este tipo de tarea? Esta acción no se puede deshacer.")
                st.info(f"**Tipo de tarea a eliminar:** {tipo_row['descripcion']}")
                
                if st.button("Eliminar Tipo de Tarea", key="delete_tipo_btn", type="primary"):
                    conn = get_connection()
                    c = conn.cursor()
                    try:
                        # Verificar si hay registros asociados
                        c.execute("SELECT COUNT(*) FROM registros WHERE id_tipo = %s", (tipo_id,))
                        registro_count = c.fetchone()[0]
                        
                        if registro_count > 0:
                            st.error(f"No se puede eliminar el tipo de tarea porque tiene {registro_count} registros asociados.")
                        else:
                            # Eliminar primero las relaciones con roles
                            c.execute("DELETE FROM tipos_tarea_roles WHERE id_tipo = %s", (tipo_id,))
                            
                            # Eliminar puntajes asociados si existen
                            c.execute("DELETE FROM tipos_tarea_puntajes WHERE id_tipo = %s", (tipo_id,))
                            
                            # Finalmente eliminar el tipo de tarea
                            c.execute("DELETE FROM tipos_tarea WHERE id_tipo = %s", (tipo_id,))
                            conn.commit()
                            show_success_message(f"✅ Tipo de tarea '{tipo_row['descripcion']}' eliminado exitosamente.", 1.5)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error al eliminar tipo de tarea: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay tipos de tarea para eliminar.")

def render_modality_management():
    """Renderiza la gestión de modalidades"""
    st.subheader("Gestión de Modalidades")
    
    # Formulario para agregar modalidades
    with st.expander("Agregar Modalidad"):
        new_modality = st.text_input("Nombre de la Modalidad", key="new_modality")
        
        if st.button("Agregar Modalidad", key="add_modality_btn"):
            if new_modality:
                # Normalizar entrada del usuario
                new_modality_normalized = ' '.join(new_modality.strip().split()).title()
                
                conn = get_connection()
                c = conn.cursor()
                try:
                    c.execute("INSERT INTO modalidades_tarea (descripcion) VALUES (%s)", (new_modality_normalized,))
                    conn.commit()
                    st.success(f"Modalidad '{new_modality_normalized}' agregada exitosamente.")
                    st.rerun()
                except Exception as e:
                    if "UNIQUE constraint failed" in str(e):
                        st.error(f"Esta modalidad ya existe: '{new_modality_normalized}'")
                    else:
                        st.error(f"Error al agregar modalidad: {str(e)}")
                finally:
                    conn.close()
            else:
                st.error("El nombre de la modalidad es obligatorio.")
    
    # Tabla de modalidades existentes
    st.subheader("Modalidades Existentes")
    modalidades_df = get_modalidades_dataframe()
    if not modalidades_df.empty:
        # Ocultar columna id_modalidad
        if 'id_modalidad' in modalidades_df.columns:
            st.dataframe(modalidades_df.drop(columns=['id_modalidad']), use_container_width=True)
        else:
            st.dataframe(modalidades_df, use_container_width=True)
    else:
        st.dataframe(modalidades_df, use_container_width=True)
    
    # Formularios para editar y eliminar modalidades
    render_modality_edit_delete_forms(modalidades_df)

def render_modality_edit_delete_forms(modalidades_df):
    """Renderiza formularios de edición y eliminación de modalidades"""
    # Formulario para editar modalidades
    with st.expander("Editar Modalidad"):
        if not modalidades_df.empty:
            modalidad_ids = modalidades_df['id_modalidad'].tolist()
            modalidad_names = modalidades_df['descripcion'].tolist()
            modalidad_options = [f"{mid} - {mname}" for mid, mname in zip(modalidad_ids, modalidad_names)]
            
            selected_modalidad_edit = st.selectbox("Seleccionar Modalidad para Editar", 
                                                   options=modalidad_options, key="select_modalidad_edit")
            if selected_modalidad_edit:
                modalidad_id = int(selected_modalidad_edit.split(' - ')[0])
                modalidad_row = modalidades_df[modalidades_df['id_modalidad'] == modalidad_id].iloc[0]
                
                edit_modalidad_name = st.text_input("Nombre de la Modalidad", value=modalidad_row['descripcion'], key="edit_modalidad_name")
                
                if st.button("Guardar Cambios de Modalidad", key="save_modalidad_edit"):
                    if edit_modalidad_name:
                        # Normalizar entrada del usuario
                        edit_modalidad_name_normalized = ' '.join(edit_modalidad_name.strip().split()).title()
                        
                        conn = get_connection()
                        c = conn.cursor()
                        try:
                            c.execute("UPDATE modalidades_tarea SET descripcion = %s WHERE id_modalidad = %s", (edit_modalidad_name_normalized, modalidad_id))
                            conn.commit()
                            st.success(f"Modalidad actualizada a '{edit_modalidad_name_normalized}' exitosamente.")
                            st.rerun()
                        except Exception as e:
                            if "UNIQUE constraint failed" in str(e):
                                st.error(f"Ya existe una modalidad con ese nombre: '{edit_modalidad_name_normalized}'")
                            else:
                                st.error(f"Error al actualizar modalidad: {str(e)}")
                        finally:
                            conn.close()
                    else:
                        st.error("El nombre de la modalidad es obligatorio.")
        else:
            st.info("No hay modalidades para editar.")
    
    # Formulario para eliminar modalidades
    with st.expander("Eliminar Modalidad"):
        if not modalidades_df.empty:
            modalidad_ids = modalidades_df['id_modalidad'].tolist()
            modalidad_names = modalidades_df['descripcion'].tolist()
            modalidad_options = [f"{mid} - {mname}" for mid, mname in zip(modalidad_ids, modalidad_names)]
            
            selected_modalidad_delete = st.selectbox("Seleccionar Modalidad para Eliminar", 
                                                     options=modalidad_options, key="select_modalidad_delete")
            if selected_modalidad_delete:
                modalidad_id = int(selected_modalidad_delete.split(' - ')[0])
                modalidad_row = modalidades_df[modalidades_df['id_modalidad'] == modalidad_id].iloc[0]
                
                st.warning("¿Estás seguro de que deseas eliminar esta modalidad? Esta acción no se puede deshacer.")
                st.info(f"**Modalidad a eliminar:** {modalidad_row['descripcion']}")
                
                if st.button("Eliminar Modalidad", key="delete_modalidad_btn", type="primary"):
                    conn = get_connection()
                    c = conn.cursor()
                    try:
                        # Verificar si hay registros asociados
                        c.execute("SELECT COUNT(*) FROM registros WHERE modalidad_id = %s", (modalidad_id,))
                        registro_count = c.fetchone()[0]
                        
                        if registro_count > 0:
                            st.error(f"No se puede eliminar la modalidad porque tiene {registro_count} registros asociados.")
                        else:
                            c.execute("DELETE FROM modalidades_tarea WHERE id_modalidad = %s", (modalidad_id,))
                            conn.commit()
                            show_success_message(f"✅ Modalidad '{modalidad_row['descripcion']}' eliminada exitosamente.", 1.5)
                    except Exception as e:
                        st.error(f"Error al eliminar modalidad: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay modalidades para eliminar.")

def process_excel_data(excel_df):
    """Procesa y carga datos desde Excel con control de duplicados y estandarización"""
    import calendar
    import openpyxl  # Importar explícitamente openpyxl
    from datetime import datetime
    import unicodedata
    from .database import get_or_create_tecnico, get_or_create_cliente, get_or_create_tipo_tarea, get_or_create_modalidad
    
    # Función para normalizar nombres de columnas removiendo acentos y caracteres especiales
    def normalize_column_name(col):
        col = col.strip()
        # Remover acentos y caracteres especiales
        col = unicodedata.normalize('NFD', col)
        col = ''.join(char for char in col if unicodedata.category(char) != 'Mn')
        return col
    
    # Normalizar nombres de columnas del Excel
    original_columns = excel_df.columns.tolist()
    normalized_columns = [normalize_column_name(col) for col in original_columns]
    
    # Crear mapeo entre columnas normalizadas y nombres esperados
    column_mapping_normalized = {
        'Fecha': 'fecha',
        'Tecnico': 'tecnico',  # Sin acento
        'Cliente': 'cliente',
        'Tipo tarea': 'tipo_tarea',
        'Modalidad': 'modalidad',
        'N° de Ticket': 'numero_ticket',
        'Tiempo': 'tiempo',
        'Breve Descripcion': 'tarea_realizada',  # Sin acento
        'Sector': 'grupo',
        'Equipo': 'grupo'
    }
    
    # Validar que el DataFrame tenga las columnas requeridas (usando versiones normalizadas)
    required_columns_normalized = ['Fecha', 'Tecnico', 'Cliente', 'Tipo tarea', 'Modalidad']
    missing_columns = []
    
    for req_col in required_columns_normalized:
        if req_col not in normalized_columns:
            # Buscar la columna original correspondiente para mostrar en el error
            original_col = None
            for orig, norm in zip(original_columns, normalized_columns):
                if norm == req_col:
                    original_col = orig
                    break
            if not original_col:
                # Si no encontramos la columna, usar el nombre normalizado
                missing_columns.append(req_col)
    
    if missing_columns:
        st.error(f"❌ La planilla no tiene el formato correcto. Faltan las siguientes columnas: {', '.join(missing_columns)}")
        st.info("📋 **Formato esperado de la planilla:**")
        st.info("• Fecha")
        st.info("• Técnico (puede ser 'Tecnico' sin acento)")
        st.info("• Cliente")
        st.info("• Tipo tarea")
        st.info("• Modalidad")
        st.info("• N° de Ticket (opcional)")
        st.info("• Tiempo (opcional)")
        st.info("• Breve Descripción (opcional, puede ser sin acento)")
        st.info("• Sector o Equipo (opcional)")
        return 0, 0, 0
    
    # Crear DataFrame con columnas normalizadas
    excel_df_normalized = excel_df.copy()
    excel_df_normalized.columns = normalized_columns
    
    # Aplicar mapeo de columnas
    excel_df_mapped = excel_df_normalized.rename(columns=column_mapping_normalized)
    
    # Limpiar DataFrame: eliminar filas con fechas vacías
    excel_df_mapped = excel_df_mapped.dropna(subset=['fecha'])
    excel_df_mapped = excel_df_mapped[excel_df_mapped['fecha'] != '']
    
    if excel_df_mapped.empty:
        st.warning("No hay datos válidos para procesar después de filtrar fechas vacías.")
        return 0, 0, 0
    
    conn = get_connection()
    c = conn.cursor()
    
    success_count = 0
    error_count = 0
    duplicate_count = 0
    created_entities = {
        'tecnicos': set(),
        'clientes': set(),
        'tipos_tarea': set(),
        'modalidades': set()
    }
    
    # Nuevo: Registro de errores por tipo
    error_types = {
        'fecha_invalida': 0,
        'tecnico_vacio': 0,
        'cliente_vacio': 0,
        'tipo_tarea_vacio': 0,
        'modalidad_vacia': 0,
        'entidad_error': 0,
        'otros_errores': 0
    }
    
    # Mapear nombres de columnas de tu formato al formato esperado
    column_mapping = {
        'Fecha': 'fecha',
        'Técnico': 'tecnico', 
        'Cliente': 'cliente',
        'Tipo tarea': 'tipo_tarea',
        'Modalidad': 'modalidad',
        'N° de Ticket': 'numero_ticket',
        'Tiempo': 'tiempo',
        'Breve Descripción': 'tarea_realizada',
        'Sector': 'grupo',  # Mapeo existente para Sector
        'Equipo': 'grupo'   # Nuevo mapeo para Equipo
    }
    
    # Normalización más robusta de nombres de columnas
    import unicodedata
    
    def normalize_column_name(col):
        col = col.strip()
        return col
    
    excel_df.columns = [normalize_column_name(col) for col in excel_df.columns]
    
    # Renombrar columnas para que coincidan con el formato esperado
    excel_df_mapped = excel_df.rename(columns=column_mapping)
    
    # Obtener entidades existentes para evitar duplicados
    c.execute("SELECT nombre FROM tecnicos")
    existing_tecnicos = {row[0] for row in c.fetchall()}
    
    c.execute("SELECT nombre FROM clientes")
    existing_clientes = {row[0] for row in c.fetchall()}
    
    c.execute("SELECT descripcion FROM tipos_tarea")
    existing_tipos = {row[0] for row in c.fetchall()}
    
    c.execute("SELECT descripcion FROM modalidades_tarea")
    existing_modalidades = {row[0] for row in c.fetchall()}
    
    for index, row in excel_df_mapped.iterrows():
        try:
            # Verificar si la fecha es válida antes de procesarla
            if pd.isna(row['fecha']) or str(row['fecha']).strip() in ['', 'NaT', 'nan']:
                continue  # Omitir filas con fechas vacías
            
            # Estandarizar fecha
            fecha_str = str(row['fecha'])
            try:
                if '/' in fecha_str:
                    # Normalizar formato de fecha para manejar días con un solo dígito
                    partes = fecha_str.split('/')
                    # Asegurar que el día y mes tengan dos dígitos
                    if len(partes) == 3:
                        # Si el año tiene 2 dígitos
                        if len(partes[2]) == 2:
                            fecha_str = f"{int(partes[0]):02d}/{int(partes[1]):02d}/{partes[2]}"
                            fecha_obj = datetime.strptime(fecha_str, '%d/%m/%y')
                        else:  # Si el año tiene 4 dígitos
                            fecha_str = f"{int(partes[0]):02d}/{int(partes[1]):02d}/{partes[2]}"
                            fecha_obj = datetime.strptime(fecha_str, '%d/%m/%Y')
                    else:
                        # Si el formato no es el esperado, intentar con pandas
                        fecha_obj = pd.to_datetime(fecha_str)
                else:
                    fecha_obj = pd.to_datetime(fecha_str)
                fecha_formateada = fecha_obj.strftime('%d/%m/%y')
            except Exception as e:
                # Registrar error de fecha
                error_types['fecha_invalida'] += 1
                error_count += 1
                continue  # Omitir filas con fechas que no se pueden procesar
            
            # Verificar que los campos obligatorios no estén vacíos
            if pd.isna(row['tecnico']) or str(row['tecnico']).strip() in ['', 'nan', 'NaN', 'None', 'null']:
                error_types['tecnico_vacio'] += 1
                error_count += 1
                continue
                
            if pd.isna(row['cliente']) or str(row['cliente']).strip() in ['', 'nan', 'NaN', 'None', 'null']:
                error_types['cliente_vacio'] += 1
                error_count += 1
                continue
                
            if pd.isna(row['tipo_tarea']) or str(row['tipo_tarea']).strip() in ['', 'nan', 'NaN', 'None', 'null']:
                error_types['tipo_tarea_vacio'] += 1
                error_count += 1
                continue
                
            if pd.isna(row['modalidad']) or str(row['modalidad']).strip() in ['', 'nan', 'NaN', 'None', 'null']:
                error_types['modalidad_vacia'] += 1
                error_count += 1
                continue
            
            # Obtener y crear entidades automáticamente (normalizadas)
            tecnico = ' '.join(str(row['tecnico']).strip().split()).title()
            cliente = ' '.join(str(row['cliente']).strip().split()).title()
            tipo_tarea = ' '.join(str(row['tipo_tarea']).strip().split()).title()
            modalidad = ' '.join(str(row['modalidad']).strip().split()).title()
            
            # Verificar si existe la columna grupo y obtener su valor (normalizado)
            grupo = "General"  # Valor predeterminado (primera letra mayúscula)
            if 'grupo' in row and pd.notna(row['grupo']) and str(row['grupo']).strip() != '':
                grupo = ' '.join(str(row['grupo']).strip().split()).title()
            
            # Usar get_or_create para obtener IDs (creando si no existen)
            try:
                id_tecnico = get_or_create_tecnico(tecnico, conn)
                if tecnico not in existing_tecnicos:
                    created_entities['tecnicos'].add(tecnico)
                    
                id_cliente = get_or_create_cliente(cliente, conn)
                if cliente not in existing_clientes:
                    created_entities['clientes'].add(cliente)
                    
                id_tipo = get_or_create_tipo_tarea(tipo_tarea, conn)
                if tipo_tarea not in existing_tipos:
                    created_entities['tipos_tarea'].add(tipo_tarea)
                    
                id_modalidad = get_or_create_modalidad(modalidad, conn)
                if modalidad not in existing_modalidades:
                    created_entities['modalidades'].add(modalidad)
                    
            except Exception as e:
                error_types['entidad_error'] += 1
                error_count += 1
                continue
            
            # Validar otros campos (normalizados)
            tarea_realizada = ' '.join(str(row['tarea_realizada']).strip().split())
            numero_ticket = str(row['numero_ticket']).strip() if pd.notna(row['numero_ticket']) else 'N/A'
            tiempo = float(row['tiempo'])
            descripcion = ' '.join(str(row.get('descripcion', '')).strip().split()) if pd.notna(row.get('descripcion')) else ''
            mes = month_name_es(fecha_obj.month)
            
            # Verificar duplicados
            c.execute('''
                SELECT id, grupo FROM registros 
                WHERE fecha = %s AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s
                AND id_modalidad = %s AND tarea_realizada = %s AND tiempo = %s
            ''', (fecha_formateada, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, tiempo))
            
            registro_existente = c.fetchone()
            
            if registro_existente:
                registro_id, grupo_actual = registro_existente
                
                # Actualizar el grupo si ha cambiado
                if grupo != grupo_actual:
                    c.execute('''
                        UPDATE registros SET grupo = %s WHERE id = %s
                    ''', (grupo, registro_id))
                
                duplicate_count += 1
                continue
            
            # Insertar registro incluyendo el campo grupo
            c.execute('''
                INSERT INTO registros 
                (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
                 numero_ticket, tiempo, descripcion, mes, usuario_id, grupo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (fecha_formateada, id_tecnico, id_cliente, id_tipo, id_modalidad, 
                  tarea_realizada, numero_ticket, tiempo, descripcion, mes, None, grupo))
            
            success_count += 1
            
        except Exception as e:
            error_types['otros_errores'] += 1
            error_count += 1
    
    conn.commit()
    
    # NUEVA FUNCIONALIDAD: Asignación automática de registros por técnico
    auto_assign_records_by_technician(conn)
    
    # NUEVA FUNCIONALIDAD: Asignación automática de tipos de tarea a roles
    auto_assign_task_types_to_roles(conn)
    
    conn.close()
    
    # Mostrar resumen de entidades creadas
    if any(created_entities.values()):
        st.info("**Nuevas entidades creadas automáticamente:**")
        if created_entities['tecnicos']:
            st.write(f"• **Técnicos:** {', '.join(created_entities['tecnicos'])}")
        if created_entities['clientes']:
            st.write(f"• **Clientes:** {', '.join(created_entities['clientes'])}")
        if created_entities['tipos_tarea']:
            st.write(f"• **Tipos de tarea:** {', '.join(created_entities['tipos_tarea'])}")
        if created_entities['modalidades']:
            st.write(f"• **Modalidades:** {', '.join(created_entities['modalidades'])}")
    
    # Mostrar resumen de errores si hay alguno
    if error_count > 0:
        st.error(f"⚠️ {error_count} registros con errores no procesados:")
        for error_type, count in error_types.items():
            if count > 0:
                error_message = {
                    'fecha_invalida': "Fechas inválidas o con formato incorrecto",
                    'tecnico_vacio': "Campo 'técnico' vacío o inválido",
                    'cliente_vacio': "Campo 'cliente' vacío o inválido",
                    'tipo_tarea_vacio': "Campo 'tipo_tarea' vacío o inválido",
                    'modalidad_vacia': "Campo 'modalidad' vacío o inválido",
                    'entidad_error': "Error al crear/obtener entidades en la base de datos",
                    'otros_errores': "Otros errores no especificados"
                }
                st.write(f"• **{error_message[error_type]}:** {count}")
    
    return success_count, error_count, duplicate_count


def auto_assign_records_by_technician(conn):
    """Asigna automáticamente registros a usuarios basándose en el nombre del técnico"""
    from .utils import normalize_text  # Importar la función de normalización
    
    c = conn.cursor()
    
    # Obtener todos los usuarios con nombre y apellido
    c.execute("SELECT id, nombre, apellido FROM usuarios WHERE nombre IS NOT NULL AND apellido IS NOT NULL")
    usuarios = c.fetchall()
    
    # Obtener todos los técnicos
    c.execute("SELECT id_tecnico, nombre FROM tecnicos")
    tecnicos = c.fetchall()
    
    # Crear diccionario de técnicos normalizados
    tecnicos_dict = {}
    for tecnico_id, tecnico_nombre in tecnicos:
        nombre_norm = normalize_text(tecnico_nombre)
        tecnicos_dict[nombre_norm] = tecnico_id
    
    registros_asignados = 0
    
    for usuario_id, nombre, apellido in usuarios:
        nombre_completo = f"{nombre} {apellido}"
        nombre_norm = normalize_text(nombre_completo)
        
        # Buscar coincidencias exactas primero
        if nombre_norm in tecnicos_dict:
            tecnico_id = tecnicos_dict[nombre_norm]
            
            # Actualizar registros
            c.execute("""
                UPDATE registros SET usuario_id = %s 
                WHERE usuario_id IS NULL AND id_tecnico = %s
            """, (usuario_id, tecnico_id))
            
            registros_actualizados = c.rowcount
            registros_asignados += registros_actualizados
            
            if registros_actualizados > 0:
                st.info(f"✅ Asignados {registros_actualizados} registros a {nombre_completo}")
        else:
            # Buscar coincidencias parciales
            for tecnico_norm, tecnico_id in tecnicos_dict.items():
                # Verificar si el nombre normalizado del usuario está contenido en el nombre del técnico
                # o viceversa
                if (nombre_norm in tecnico_norm or tecnico_norm in nombre_norm) and len(nombre_norm) > 3:
                    # Actualizar registros
                    c.execute("""
                        UPDATE registros SET usuario_id = %s 
                        WHERE usuario_id IS NULL AND id_tecnico = %s
                    """, (usuario_id, tecnico_id))
                    
                    registros_actualizados = c.rowcount
                    registros_asignados += registros_actualizados
                    
                    if registros_actualizados > 0:
                        tecnico_original = next(nombre for id_t, nombre in tecnicos if id_t == tecnico_id)
                        st.info(f"✅ Asignados {registros_actualizados} registros a {nombre_completo} (coincidencia parcial con técnico '{tecnico_original}')")
    
    if registros_asignados > 0:
        conn.commit()
        st.success(f"🎯 Total de registros asignados automáticamente: {registros_asignados}")
    
    # Después de cargar los datos y asignar técnicos
    fix_existing_records_assignment(conn)
    
    # Limpiar asignaciones incorrectas de sin_rol antes de asignar nuevas
    clean_sin_rol_assignments()
    
    # Asignar automáticamente tipos de tarea a roles
    auto_assign_task_types_to_roles(conn)
    
    return registros_asignados


def clean_sin_rol_assignments():
    """Limpia las asignaciones de tipos de tarea al rol sin_rol"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Obtener el ID del rol sin_rol
        c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (SYSTEM_ROLES['SIN_ROL'],))
        sin_rol_result = c.fetchone()
        
        if sin_rol_result:
            sin_rol_id = sin_rol_result[0]
            
            # Eliminar asignaciones de sin_rol
            c.execute("DELETE FROM tipos_tarea_roles WHERE id_rol = %s", (sin_rol_id,))
            eliminadas = c.rowcount
            conn.commit()
            
            if eliminadas > 0:
                st.success(f"🧹 Se eliminaron {eliminadas} asignaciones incorrectas del rol '{SYSTEM_ROLES['SIN_ROL']}'")
    finally:
        conn.close()

def auto_assign_task_types_to_roles(conn):
    """Asigna automáticamente tipos de tarea a roles basándose en los registros de los técnicos"""
    c = conn.cursor()
    
    # Obtener todos los registros con información de técnico, tipo de tarea y usuario
    # EXCLUIR el rol 'sin_rol' de las asignaciones automáticas
    c.execute("""
        SELECT DISTINCT r.id_tipo, t.descripcion as tipo_descripcion, 
               u.rol_id, rol.nombre as rol_nombre, u.nombre, u.apellido
        FROM registros r
        JOIN tipos_tarea t ON r.id_tipo = t.id_tipo
        JOIN usuarios u ON r.usuario_id = u.id
        JOIN roles rol ON u.rol_id = rol.id_rol
        WHERE r.usuario_id IS NOT NULL 
          AND u.rol_id IS NOT NULL 
          AND rol.nombre != %s
          AND rol.nombre != %s
    """, (SYSTEM_ROLES['SIN_ROL'], SYSTEM_ROLES['ADMIN']))
    
    registros_con_roles = c.fetchall()
    
    if not registros_con_roles:
        st.info("No hay registros con usuarios y roles válidos asignados para procesar.")
        return
    
    asignaciones_realizadas = 0
    tipos_asignados = set()
    
    for id_tipo, tipo_descripcion, rol_id, rol_nombre, nombre_usuario, apellido_usuario in registros_con_roles:
        # Verificar si ya existe la asignación tipo_tarea -> rol
        c.execute("""
            SELECT COUNT(*) FROM tipos_tarea_roles 
            WHERE id_tipo = %s AND id_rol = %s
        """, (id_tipo, rol_id))
        
        existe_asignacion = c.fetchone()[0] > 0
        
        if not existe_asignacion:
            try:
                # Crear la asignación tipo_tarea -> rol
                c.execute("""
                    INSERT INTO tipos_tarea_roles (id_tipo, id_rol) 
                    VALUES (%s, %s)
                """, (id_tipo, rol_id))
                
                asignaciones_realizadas += 1
                tipos_asignados.add(f"'{tipo_descripcion}' → {rol_nombre}")
                
            except Exception as e:
                st.error(f"Error al asignar tipo de tarea '{tipo_descripcion}' al rol '{rol_nombre}': {str(e)}")
    
    # Asignar todos los tipos de tarea a todos los roles (excepto admin y sin_rol)
    query = """
    INSERT INTO tipos_tarea_roles (id_tipo, id_rol)
    SELECT DISTINCT tt.id_tipo, rol.id_rol
    FROM tipos_tarea tt
    CROSS JOIN roles rol
    LEFT JOIN tipos_tarea_roles ttr ON tt.id_tipo = ttr.id_tipo AND rol.id_rol = ttr.id_rol
    WHERE ttr.id_tipo IS NULL 
    AND rol.nombre != %s
    AND rol.nombre != %s
    """
    
    c.execute(query, (SYSTEM_ROLES['ADMIN'], SYSTEM_ROLES['SIN_ROL']))
    asignaciones_adicionales = c.rowcount
    asignaciones_realizadas += asignaciones_adicionales
    
    if asignaciones_realizadas > 0:
        conn.commit()
        st.success(f"✅ Se asignaron automáticamente {asignaciones_realizadas} tipos de tarea a roles")
        
        # Mostrar detalles de las asignaciones realizadas
        with st.expander("Ver asignaciones realizadas"):
            for asignacion in sorted(tipos_asignados):
                st.write(f"• {asignacion}")
            if asignaciones_adicionales > 0:
                st.write(f"• {asignaciones_adicionales} asignaciones automáticas adicionales")
    else:
        st.info("ℹ️ No se encontraron nuevas asignaciones de tipos de tarea a roles para realizar.")
    
    return asignaciones_realizadas


def fix_existing_records_assignment(conn=None):
    """Corrige la asignación de registros existentes basándose en el nombre del técnico y su rol"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    
    # Obtener todos los usuarios con nombre, apellido y rol
    c.execute("""
        SELECT u.id, u.nombre, u.apellido, u.rol_id, r.nombre as rol_nombre
        FROM usuarios u
        JOIN roles r ON u.rol_id = r.id_rol
        WHERE u.nombre IS NOT NULL AND u.apellido IS NOT NULL
    """)
    usuarios = c.fetchall()
    
    # Obtener todos los técnicos
    c.execute("SELECT id_tecnico, nombre FROM tecnicos")
    tecnicos = c.fetchall()
    
    # Mostrar información de diagnóstico resumida
    with st.spinner(f"Procesando {len(usuarios)} usuarios y {len(tecnicos)} técnicos..."):
        registros_asignados = 0
        tecnicos_procesados = set()
        
        def normalizar_texto(texto):
            import unicodedata
            texto_sin_acentos = ''.join(c for c in unicodedata.normalize('NFD', texto) 
                                      if unicodedata.category(c) != 'Mn')
            return texto_sin_acentos.lower()
        
        def find_matching_user_flexible(tecnico_nombre, usuarios_info):
            """Encuentra el usuario que coincide con el técnico usando lógica flexible"""
            # Para técnicos: extraer primer nombre y apellidos
            partes_tecnico = tecnico_nombre.strip().split()
            if len(partes_tecnico) == 0:
                return None, 0
            elif len(partes_tecnico) == 1:
                tecnico_primer_nombre = partes_tecnico[0].lower()
                tecnico_apellidos = ""
            else:
                tecnico_primer_nombre = partes_tecnico[0].lower()
                # Para técnicos, todo después del primer nombre son apellidos
                tecnico_apellidos = " ".join(partes_tecnico[1:]).lower()
            
            mejor_usuario = None
            mejor_puntuacion = 0
            
            for usuario_id, nombre, apellido, rol_id, rol_nombre in usuarios_info:
                # Para usuarios: usar los campos separados nombre y apellido
                partes_nombre_usuario = nombre.strip().split()
                usuario_primer_nombre = partes_nombre_usuario[0].lower() if partes_nombre_usuario else ""
                
                # El apellido del usuario (puede tener múltiples apellidos)
                usuario_apellidos = apellido.strip().lower()
                
                puntuacion = 0
                
                # PRIMERA PRIORIDAD: Coincidencia exacta completa
                nombre_completo_usuario = f"{nombre} {apellido}"
                if (normalizar_texto(tecnico_nombre) == normalizar_texto(nombre_completo_usuario)):
                    puntuacion = 100
                
                # SEGUNDA PRIORIDAD: Primer nombre + apellidos exactos
                elif (tecnico_primer_nombre == usuario_primer_nombre and 
                      tecnico_apellidos == usuario_apellidos):
                    puntuacion = 95
                
                # TERCERA PRIORIDAD: Primer nombre + primer apellido del técnico coincide con primer apellido del usuario
                elif tecnico_primer_nombre == usuario_primer_nombre and tecnico_apellidos:
                    partes_apellidos_tecnico = tecnico_apellidos.split()
                    partes_apellidos_usuario = usuario_apellidos.split()
                    
                    if (len(partes_apellidos_tecnico) >= 1 and len(partes_apellidos_usuario) >= 1 and
                        partes_apellidos_tecnico[0] == partes_apellidos_usuario[0]):
                        puntuacion = 90
                
                # CUARTA PRIORIDAD: Primer nombre + último apellido del técnico coincide con último apellido del usuario
                elif tecnico_primer_nombre == usuario_primer_nombre and tecnico_apellidos:
                    partes_apellidos_tecnico = tecnico_apellidos.split()
                    partes_apellidos_usuario = usuario_apellidos.split()
                    
                    if (len(partes_apellidos_tecnico) >= 1 and len(partes_apellidos_usuario) >= 1 and
                        partes_apellidos_tecnico[-1] == partes_apellidos_usuario[-1]):
                        puntuacion = 85
                
                # QUINTA PRIORIDAD: Primer nombre + cualquier apellido del técnico está en los apellidos del usuario
                elif (tecnico_primer_nombre == usuario_primer_nombre and tecnico_apellidos):
                    partes_apellidos_tecnico = tecnico_apellidos.split()
                    partes_apellidos_usuario = usuario_apellidos.split()
                    
                    coincidencias_apellidos = 0
                    for apellido_tecnico in partes_apellidos_tecnico:
                        if apellido_tecnico in partes_apellidos_usuario:
                            coincidencias_apellidos += 1
                    
                    if coincidencias_apellidos > 0:
                        # Puntuación basada en el porcentaje de apellidos que coinciden
                        porcentaje_coincidencia = coincidencias_apellidos / len(partes_apellidos_tecnico)
                        puntuacion = 70 + (porcentaje_coincidencia * 10)
                
                # SEXTA PRIORIDAD: Solo primer nombre coincide (casos especiales)
                elif (tecnico_primer_nombre == usuario_primer_nombre and not tecnico_apellidos):
                    puntuacion = 60
                
                # NUEVA LÓGICA: Buscar nombres del técnico en cualquier posición del nombre del usuario
                # Esto maneja casos como "Lucas Gómez" vs "Nicolas lucas Gomez"
                else:
                    # Obtener todas las partes del nombre completo del usuario
                    todas_partes_usuario = (nombre + " " + apellido).lower().split()
                    
                    # Contar coincidencias de nombres
                    coincidencias_nombres = 0
                    total_partes_tecnico = len(partes_tecnico)
                    
                    for parte_tecnico in partes_tecnico:
                        parte_tecnico_lower = parte_tecnico.lower()
                        # Buscar coincidencia exacta o similar (sin acentos)
                        for parte_usuario in todas_partes_usuario:
                            if (normalizar_texto(parte_tecnico_lower) == normalizar_texto(parte_usuario) or
                                parte_tecnico_lower == parte_usuario):
                                coincidencias_nombres += 1
                                break
                    
                    # Calcular puntuación basada en el porcentaje de coincidencias
                    if coincidencias_nombres > 0:
                        porcentaje_coincidencia = coincidencias_nombres / total_partes_tecnico
                        if porcentaje_coincidencia >= 0.5:  # Al menos 50% de coincidencia
                            puntuacion = 50 + (porcentaje_coincidencia * 30)  # 50-80 puntos
                
                if puntuacion > mejor_puntuacion:
                    mejor_puntuacion = puntuacion
                    mejor_usuario = {
                        "id": usuario_id,
                        "nombre_completo": nombre_completo_usuario,
                        "nombre": nombre,
                        "apellido": apellido,
                        "rol_id": rol_id,
                        "rol_nombre": rol_nombre
                    }
            
            return mejor_usuario, mejor_puntuacion
        
        # Procesar cada técnico
        for tecnico_id, tecnico_nombre in tecnicos:
            mejor_usuario, mejor_puntuacion = find_matching_user_flexible(tecnico_nombre, usuarios)
            
            # UMBRAL REDUCIDO: Permitir coincidencias más flexibles
            if mejor_usuario and mejor_puntuacion >= 50:  # Reducido de 80 a 50
                # Agregar a la lista de técnicos procesados
                tecnicos_procesados.add(tecnico_id)
                
                # Actualizar registros para este técnico
                c.execute("""
                    UPDATE registros SET usuario_id = %s 
                    WHERE id_tecnico = %s
                """, (mejor_usuario["id"], tecnico_id))
                
                registros_actualizados = c.rowcount
                registros_asignados += registros_actualizados
        
        # Mostrar resumen de resultados
        if registros_asignados > 0:
            conn.commit()
            st.success(f"🎯 Total de registros procesados: {registros_asignados}")
        else:
            st.info("No se encontraron nuevos registros para reasignar.")
    
    # Mostrar técnicos que no pudieron ser procesados con diagnóstico
    tecnicos_no_procesados = []
    for tecnico_id, tecnico_nombre in tecnicos:
        if tecnico_id not in tecnicos_procesados:
            tecnicos_no_procesados.append((tecnico_id, tecnico_nombre))
    
    if tecnicos_no_procesados:
        st.warning(f"⚠️ Técnicos que no pudieron ser procesados: {len(tecnicos_no_procesados)}")
        
        with st.expander("Ver técnicos no procesados"):
            for tecnico_id, tecnico_nombre in tecnicos_no_procesados:
                # Analizar por qué no se pudo procesar usando la nueva lógica
                mejor_usuario, mejor_puntuacion = find_matching_user_flexible(tecnico_nombre, usuarios)
                
                # Mostrar información de diagnóstico
                st.markdown(f"**{tecnico_nombre}**")
                if mejor_usuario:
                    st.write(f"Usuario más cercano: {mejor_usuario['nombre_completo']} (puntuación: {mejor_puntuacion:.1f})")
                    if mejor_puntuacion < 50:
                        st.write(f"Razón: Puntuación insuficiente (mínimo requerido: 50)")
                else:
                    st.write("Razón: No hay coincidencias con ningún usuario en el sistema")
                st.write("---")
    
    # Cerrar la conexión solo si la creamos aquí
    if close_conn:
        conn.close()
    return registros_asignados


def render_grupo_management():
    """Renderiza la gestión de grupos"""
    st.header("Gestión de Grupos")
    
    # Obtener roles disponibles
    roles_df = get_roles_dataframe()
    
    # Formulario para agregar nuevo grupo
    with st.expander("Agregar Nuevo Grupo", expanded=True):
        nombre_grupo = st.text_input("Nombre del Grupo", key="new_grupo_nombre")
        descripcion_grupo = st.text_area("Descripción (opcional)", key="new_grupo_desc")
        
        # Selección múltiple de roles
        selected_roles = st.multiselect(
            "Roles asignados a este grupo",
            options=roles_df['id_rol'].tolist(),
            format_func=lambda x: roles_df.loc[roles_df['id_rol'] == x, 'nombre'].iloc[0],
            key="new_grupo_roles"
        )
        
        if st.button("Agregar Grupo", key="add_grupo_btn"):
            if nombre_grupo:
                if add_grupo(nombre_grupo, descripcion_grupo):
                    # Obtener el ID del grupo recién creado
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute("SELECT id_grupo FROM grupos WHERE nombre = %s", (nombre_grupo,))
                    nuevo_grupo_id = c.fetchone()[0]
                    conn.close()
                    
                    # Asignar roles al grupo
                    update_grupo_roles(nuevo_grupo_id, selected_roles)
                    
                    show_success_message(f"✅ Grupo '{nombre_grupo}' agregado exitosamente.", 1.5)
                else:
                    st.error("Ya existe un grupo con ese nombre.")
            else:
                st.error("El nombre del grupo es obligatorio.")
    
    # Mostrar grupos existentes
    grupos_df = get_grupos_dataframe()
    if not grupos_df.empty:
        st.subheader("Grupos Existentes")
        # Ocultar columna id_grupo
        if 'id_grupo' in grupos_df.columns:
            st.dataframe(grupos_df.drop(columns=['id_grupo']), use_container_width=True)
        else:
            st.dataframe(grupos_df, use_container_width=True)
        
        # Formularios para editar y eliminar grupos
        render_grupo_edit_delete_forms(grupos_df)
    else:
        st.info("No hay grupos registrados.")

def render_grupo_edit_delete_forms(grupos_df):
    """Renderiza formularios de edición y eliminación de grupos"""
    # Obtener roles disponibles (excluyendo admin y sin_rol)
    roles_df = get_roles_dataframe(exclude_admin=True, exclude_sin_rol=True)
    
    # Formulario para editar grupos
    with st.expander("Editar Grupo"):
        if not grupos_df.empty:
            grupo_ids = grupos_df['id_grupo'].tolist()
            grupo_nombres = grupos_df['nombre'].tolist()
            grupo_options = [f"{gid} - {gnombre}" for gid, gnombre in zip(grupo_ids, grupo_nombres)]
            
            selected_grupo_edit = st.selectbox("Seleccionar Grupo para Editar", 
                                             options=grupo_options, key="select_grupo_edit")
            if selected_grupo_edit:
                grupo_id = int(selected_grupo_edit.split(' - ')[0])
                grupo_row = grupos_df[grupos_df['id_grupo'] == grupo_id].iloc[0]
                
                edit_grupo_nombre = st.text_input("Nombre del Grupo", value=grupo_row['nombre'], key="edit_grupo_nombre")
                edit_grupo_desc = st.text_area("Descripción", value=grupo_row['descripcion'] if pd.notna(grupo_row['descripcion']) else "", key="edit_grupo_desc")
                
                # Obtener roles actuales para este grupo
                current_roles = get_roles_by_grupo(grupo_id)
                current_role_ids = [r[0] for r in current_roles]
                
                # Selección múltiple de roles
                edit_selected_roles = st.multiselect(
                    "Roles asignados a este grupo",
                    options=roles_df['id_rol'].tolist(),
                    default=current_role_ids,
                    format_func=lambda x: roles_df.loc[roles_df['id_rol'] == x, 'nombre'].iloc[0],
                    key="edit_grupo_roles"
                )
                
                if st.button("Guardar Cambios de Grupo", key="save_grupo_edit"):
                    if edit_grupo_nombre:
                        conn = get_connection()
                        c = conn.cursor()
                        try:
                            from .utils import normalize_text
                            
                            # Verificar si el nombre ya existe para otro grupo (normalizado)
                            c.execute("SELECT id_grupo, nombre FROM grupos WHERE id_grupo != %s", (grupo_id,))
                            existing_grupos = c.fetchall()
                            nombre_normalizado = normalize_text(edit_grupo_nombre)
                            
                            duplicado = False
                            for existing_id, existing_nombre in existing_grupos:
                                if normalize_text(existing_nombre) == nombre_normalizado:
                                    duplicado = True
                                    break
                            
                            if not duplicado:
                                # Actualizar grupo
                                c.execute("UPDATE grupos SET nombre = %s, descripcion = %s WHERE id_grupo = %s", 
                                         (edit_grupo_nombre, edit_grupo_desc, grupo_id))
                                conn.commit()
                                
                                # Actualizar roles asignados
                                update_grupo_roles(grupo_id, edit_selected_roles)
                                
                                st.success("Grupo actualizado exitosamente.")
                                st.rerun()
                            else:
                                st.error("Ya existe otro grupo con ese nombre.")
                        except Exception as e:
                            st.error(f"Error al actualizar grupo: {str(e)}")
                        finally:
                            conn.close()
                    else:
                        st.error("El nombre del grupo es obligatorio.")
        else:
            st.info("No hay grupos para editar.")
    
    # Formulario para eliminar grupos
    with st.expander("Eliminar Grupo"):
        if not grupos_df.empty:
            grupo_ids = grupos_df['id_grupo'].tolist()
            grupo_nombres = grupos_df['nombre'].tolist()
            grupo_options = [f"{gid} - {gnombre}" for gid, gnombre in zip(grupo_ids, grupo_nombres)]
            
            selected_grupo_delete = st.selectbox("Seleccionar Grupo para Eliminar", 
                                               options=grupo_options, key="select_grupo_delete")
            if selected_grupo_delete:
                grupo_id = int(selected_grupo_delete.split(' - ')[0])
                grupo_row = grupos_df[grupos_df['id_grupo'] == grupo_id].iloc[0]
                
                st.warning("¿Estás seguro de que deseas eliminar este grupo? Esta acción no se puede deshacer.")
                st.info(f"**Grupo a eliminar:** {grupo_row['nombre']}")
                
                if st.button("Eliminar Grupo", key="delete_grupo_btn", type="primary"):
                    conn = get_connection()
                    c = conn.cursor()
                    try:
                        # Verificar si hay usuarios asociados con manejo de error
                        try:
                            c.execute("SELECT COUNT(*) FROM usuarios WHERE grupo_id = %s", (grupo_id,))
                            usuario_count = c.fetchone()[0]
                            
                            if usuario_count > 0:
                                st.error(f"No se puede eliminar el grupo porque tiene {usuario_count} usuarios asociados.")
                                return
                        except Exception as e:
                            # Si la columna no existe, asumimos que no hay usuarios asociados
                            if "column" in str(e).lower() and "grupo_id" in str(e):
                                # Continuar con la eliminación
                                pass
                            else:
                                # Si es otro error, lo mostramos
                                raise e
                        
                        # Eliminar primero las relaciones con roles
                        c.execute("DELETE FROM grupos_roles WHERE id_grupo = %s", (grupo_id,))
                        
                        # Finalmente eliminar el grupo
                        c.execute("DELETE FROM grupos WHERE id_grupo = %s", (grupo_id,))
                        conn.commit()
                        show_success_message(f"✅ Grupo '{grupo_row['nombre']}' eliminado exitosamente.", 1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al eliminar grupo: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay grupos para eliminar.")

def render_nomina_management():
    """Renderiza la gestión de nómina"""
    st.subheader("🏠 Gestión de Nómina")
    
    # Generar roles automáticamente al cargar la pestaña
    generate_roles_from_nomina()
    
    # Usar la función reutilizable para cargar Excel con parámetros personalizados
    uploaded_file, excel_df = render_excel_uploader(
        key="nomina_excel_upload"
    )
    
    if uploaded_file is not None and excel_df is not None:
        # Procesar las fechas para mostrar solo la fecha sin tiempo
        excel_df_display = excel_df.copy()
        
        # Procesar columnas de fecha para eliminar el tiempo en la vista
        date_columns = ['Fecha Nacimiento', 'FECHA NACIMIENTO', 'Fecha ingreso', 'FECHA INGRESO']
        for col in date_columns:
            if col in excel_df_display.columns:
                excel_df_display[col] = excel_df_display[col].apply(
                    lambda x: str(x).split(' ')[0] if pd.notna(x) and ' ' in str(x) else str(x) if pd.notna(x) else x
                )
        

        # Guardar el DataFrame procesado en session_state para mostrarlo después
        if st.button("💾 Procesar y Guardar Datos", type="primary"):
            # Hacer una copia para no modificar el original
            df_processed = excel_df.copy()
            
            # 1. Eliminar filas completamente vacías
            df_processed = df_processed.dropna(how='all')
            
            # 2. Eliminar columnas completamente vacías
            df_processed = df_processed.dropna(axis=1, how='all')
            
            # 3. Eliminar filas duplicadas basadas en todas las columnas
            initial_rows = len(df_processed)
            df_processed = df_processed.drop_duplicates()
            duplicates_removed = initial_rows - len(df_processed)
            
            # 4. Reemplazar celdas vacías con 'falta dato'
            df_processed = df_processed.fillna('falta dato')
            
            # Mostrar mensaje de procesamiento
            with st.spinner('Procesando y guardando datos...'):
                # Procesar y guardar directamente en la base de datos
                try:
                    from .database import process_nomina_excel
                    
                    # Usar la función existente para procesar y guardar
                    stats = process_nomina_excel(df_processed)
                    
                    # Extraer valores del diccionario de estadísticas
                    preview_df = stats['preview_df']
                    success_count = stats['success_count']
                    error_count = stats['error_count']
                    duplicate_count = stats['duplicate_count']
                    filtered_inactive_count = stats['filtered_inactive_count']
                    success_details = stats['success_details']
                    duplicate_details = stats['duplicate_details']
                    error_details = stats['error_details']
                    
                    # Mostrar estadísticas de procesamiento
                    st.success(f"✅ **Procesamiento completado exitosamente**")
                    
                    # Mensaje de confirmación persistente
                    if success_count > 0:
                        st.info(f"🎉 **¡Procesamiento exitoso!** Se crearon {success_count} empleados nuevos en la base de datos.")
                        # Pausa para que el mensaje sea visible por más tiempo
                        time.sleep(5) 
                    
                    # Mostrar resumen destacado condicionalmente
                    resumen_lines = []
                    if success_count > 0:
                        resumen_lines.append(f"- ✅ **{success_count} empleados creados exitosamente**")
                    if duplicate_count > 0:
                        resumen_lines.append(f"- 🔄 **{duplicate_count} empleados duplicados detectados**")
                    if error_count > 0:
                        resumen_lines.append(f"- ❌ **{error_count} empleados con errores**")
                    if filtered_inactive_count > 0:
                        resumen_lines.append(f"- 🚫 **{filtered_inactive_count} empleados inactivos filtrados**")
                    
                    if resumen_lines:
                        st.markdown(f"""
                        ### 📊 Resumen del procesamiento:
                        {chr(10).join(resumen_lines)}
                        """)
                        # Pausa para que el resumen sea visible por más tiempo
                        time.sleep(5) 
                      
                    
                    # Mostrar detalles de empleados creados exitosamente
                    if success_count > 0:
                        with st.expander(f"✅ Empleados creados exitosamente ({success_count})"):
                            for empleado in success_details:
                                st.write(f"• {empleado}")
                    
                    # Mostrar información adicional si hay errores o duplicados
                    if error_count > 0:
                        st.warning(f"⚠️ {error_count} empleados no se pudieron procesar. Revisa la consola para más detalles.")
                    
                    if duplicate_count > 0:
                        st.info(f"ℹ️ {duplicate_count} empleados duplicados fueron detectados y no se crearon nuevamente.")
                    
                    # Mostrar detalles de duplicados si los hay
                    if duplicate_count > 0:
                        with st.expander(f"🔄 Empleados duplicados ({duplicate_count})"):
                            st.write("Los siguientes empleados ya existían y no se crearon:")
                            for empleado in duplicate_details:
                                st.write(f"• {empleado}")
                    
                    # Mostrar detalles de errores si los hay
                    if error_count > 0:
                        with st.expander(f"❌ Empleados con errores ({error_count})"):
                            st.write("Los siguientes empleados no se pudieron procesar:")
                            for empleado in error_details:
                                st.write(f"• {empleado}")
                    
                    # Mostrar vista previa de los datos procesados (solo empleados activos)
                    st.subheader("📋 Vista previa de datos procesados (solo empleados activos)")
                    st.dataframe(preview_df, use_container_width=True)
                    
                    # Guardar el DataFrame de vista previa para mostrarlo en la tabla final
                    if 'nomina_preview_df' not in st.session_state:
                        st.session_state.nomina_preview_df = None
                    st.session_state.nomina_preview_df = preview_df
                    
                    # Generar roles automáticamente después de agregar empleados
                    roles_stats = generate_roles_from_nomina()
                    if roles_stats["roles_creados"] > 0:
                        st.success(f"✅ Se crearon {roles_stats['roles_creados']} nuevos roles basados en los sectores")
                        # Obtener los nombres de los roles creados si están disponibles
                        if roles_stats.get("nuevos_roles"):
                            st.info(f"Nuevos roles creados: {', '.join(roles_stats['nuevos_roles'])}")
                    
                    if duplicate_count > 0:
                        st.warning(f"⚠️ {duplicate_count} empleados ya existían en la base de datos")
                        time.sleep(3)
                    if error_count > 0:
                        st.error(f"❌ {error_count} errores durante el procesamiento")
                        time.sleep(2)
                    
                    if duplicates_removed > 0:
                        st.info(f"🔄 Se eliminaron {duplicates_removed} filas duplicadas del archivo")
                        time.sleep(3)
                    
                    
                    try:
                        # Limpiar el archivo subido del session_state para que desaparezca de la interfaz
                        if "nomina_excel_upload" in st.session_state:
                            del st.session_state["nomina_excel_upload"]
                        
                        # Mostrar mensaje de confirmación de eliminación
                        st.success("🗑️ **Archivo eliminado automáticamente** después del procesamiento exitoso")
                        time.sleep(2)
                        
                    except Exception as delete_error:
                        st.warning(f"⚠️ No se pudo eliminar automáticamente el archivo: {str(delete_error)}")
                        
                    st.rerun()
                        
                except Exception as e:
                    st.error(f"Error al procesar y guardar los datos: {str(e)}")
                    time.sleep(3)
    
    # Sección para mostrar empleados existentes
    st.subheader("👥 Empleados en Nómina")
    
    try:
        from .database import get_nomina_dataframe, get_nomina_dataframe_expanded
        nomina_df = get_nomina_dataframe()
        
        if not nomina_df.empty:
            # Mostrar estadísticas generales
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Empleados", len(nomina_df))
            with col2:
                activos = len(nomina_df[nomina_df.get('activo', 1) == 1]) if 'activo' in nomina_df.columns else len(nomina_df)
                st.metric("Empleados Activos", activos)
            with col3:
                # Excluir 'admin' y 'sin_rol' del conteo de departamentos
                if 'departamento' in nomina_df.columns:
                    departamentos_filtrados = nomina_df[~nomina_df['departamento'].isin([SYSTEM_ROLES['ADMIN'], SYSTEM_ROLES['SIN_ROL']])]
                    departamentos = departamentos_filtrados['departamento'].nunique()
                else:
                    departamentos = 0
                st.metric("Departamentos", departamentos)
            
            # Siempre mostrar la vista expandida por defecto
            expanded_df = get_nomina_dataframe_expanded()
            
            # Si hay datos de vista previa guardados (más completos), usar esos
            if 'nomina_preview_df' in st.session_state and st.session_state.nomina_preview_df is not None and not st.session_state.nomina_preview_df.empty:
                st.subheader("📊 Vista completa de empleados (con todas las columnas del Excel)")
                
                # Mostrar TODOS los empleados sin filtrar
                filtered_df = st.session_state.nomina_preview_df.copy()
                
                st.dataframe(filtered_df, use_container_width=True)
            else:
                # Mostrar vista expandida generada desde la BD
                st.subheader("📊 Vista completa de empleados")
                
                # Mostrar TODOS los empleados sin filtrar
                filtered_df = expanded_df.copy()
                
                st.dataframe(filtered_df, use_container_width=True)

            # Agregar formularios de gestión de empleados
            render_nomina_edit_delete_forms(nomina_df)
        else:
            st.info("No hay empleados registrados en la nómina. Carga un archivo Excel para comenzar.")
            
    except Exception as e:
        st.error(f"Error al cargar los datos de nómina: {str(e)}")



def render_role_management():
    """Renderiza la gestión de roles"""
    st.subheader("Gestión de Roles")
    
    # Generar roles automáticamente al cargar la pestaña
    generate_roles_from_nomina()
    
    # Formulario para agregar nuevo rol
    with st.expander("Agregar Rol"):
        nombre_rol = st.text_input("Nombre del Rol", key="new_role_name")
        descripcion_rol = st.text_area("Descripción del Rol", key="new_role_desc")
        is_hidden = st.checkbox("Ocultar en listas desplegables", key="new_role_hidden")
        
        if st.button("Agregar Rol", key="add_role_btn"):
            if nombre_rol:
                # Verificar que no sea un rol protegido
                if nombre_rol.lower() == 'admin':
                    st.error("No se puede crear un rol con el nombre 'admin' ya que es un rol protegido.")
                else:
                    conn = get_connection()
                    c = conn.cursor()
                    try:
                        # Verificar si ya existe un rol con el mismo nombre normalizado
                        from .utils import normalize_text
                        c.execute("SELECT id_rol, nombre FROM roles")
                        roles = c.fetchall()
                        
                        nombre_normalizado = normalize_text(nombre_rol)
                        duplicado = False
                        
                        for _, rol_nombre in roles:
                            if normalize_text(rol_nombre) == nombre_normalizado:
                                duplicado = True
                                break
                        
                        if not duplicado:
                            c.execute("INSERT INTO roles (nombre, descripcion, is_hidden) VALUES (%s, %s, %s)", 
                                     (nombre_rol, descripcion_rol, 1 if is_hidden else 0))
                            conn.commit()
                            st.success(f"Rol '{nombre_rol}' agregado correctamente.")
                            st.rerun()
                        else:
                            st.error("Este rol ya existe (con un nombre similar).")
                    except Exception as e:
                        if "UNIQUE constraint failed" in str(e):
                            st.error("Este rol ya existe.")
                        else:
                            st.error(f"Error al agregar rol: {str(e)}")
                    finally:
                        conn.close()
            else:
                st.error("El nombre del rol es obligatorio.")
    
    # Mostrar lista de roles existentes
    st.subheader("Roles Existentes")
    conn = get_connection()
    
    # Verificar si la columna is_hidden existe en la tabla roles
    c = conn.cursor()
    try:
        c.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'roles' AND column_name = 'is_hidden'
        """)
        has_is_hidden = c.fetchone() is not None
    except Exception:
        # Fallback para bases de datos que no soportan information_schema
        try:
            c.execute("SELECT is_hidden FROM roles LIMIT 1")
            has_is_hidden = True
        except Exception:
            has_is_hidden = False
    
    if has_is_hidden:
        roles_df = pd.read_sql("SELECT id_rol, nombre, descripcion, is_hidden FROM roles ORDER BY nombre", conn)
        # Convertir is_hidden a un formato más legible
        if 'is_hidden' in roles_df.columns:
            roles_df['Oculto'] = roles_df['is_hidden'].apply(lambda x: 'Sí' if x else 'No')
            roles_df = roles_df.drop(columns=['is_hidden'])
    else:
        roles_df = pd.read_sql("SELECT id_rol, nombre, descripcion FROM roles ORDER BY nombre", conn)
    
    conn.close()
    
    if not roles_df.empty:
        # Ocultar columna id_rol
        if 'id_rol' in roles_df.columns:
            st.dataframe(roles_df.drop(columns=['id_rol']), use_container_width=True)
        else:
            st.dataframe(roles_df, use_container_width=True)
    else:
        st.info("No hay roles registrados.")
    
    # Formularios para editar y eliminar roles
    render_role_edit_delete_forms(roles_df)

def render_role_edit_delete_forms(roles_df):
    """Renderiza formularios de edición y eliminación de roles"""
    # Formulario para editar roles
    with st.expander("Editar Rol"):
        if not roles_df.empty:
            # Filtrar roles protegidos para edición
            roles_editables_df = roles_df[~roles_df['nombre'].str.lower().isin(['admin'])]
            
            if not roles_editables_df.empty:
                rol_options = [f"{row['id_rol']} - {row['nombre']}" for _, row in roles_editables_df.iterrows()]
                selected_rol = st.selectbox("Seleccionar Rol para Editar", options=rol_options, key="select_rol_edit")
                
                if selected_rol:
                    rol_id = int(selected_rol.split(' - ')[0])
                    rol_actual = roles_editables_df[roles_editables_df['id_rol'] == rol_id].iloc[0]
                    
                    nuevo_nombre = st.text_input("Nuevo Nombre", value=rol_actual['nombre'], key="edit_role_name")
                    nueva_descripcion = st.text_area("Nueva Descripción", value=rol_actual['descripcion'] if pd.notna(rol_actual['descripcion']) else "", key="edit_role_desc")
                    is_hidden = st.checkbox("Ocultar en listas desplegables", value=bool(rol_actual.get('is_hidden', 0)), key="edit_role_hidden")
                    
                    if st.button("Guardar Cambios", key="save_rol_edit"):
                        if nuevo_nombre:
                            conn = get_connection()
                            c = conn.cursor()
                            try:
                                c.execute("UPDATE roles SET nombre = %s, descripcion = %s, is_hidden = %s WHERE id_rol = %s", 
                                        (nuevo_nombre, nueva_descripcion, 1 if is_hidden else 0, rol_id))
                                conn.commit()
                                st.success(f"Rol actualizado correctamente.")
                                st.rerun()
                            except Exception as e:
                                if "UNIQUE constraint failed" in str(e):
                                    st.error("Ya existe un rol con ese nombre.")
                                else:
                                    st.error(f"Error al actualizar rol: {str(e)}")
                            finally:
                                conn.close()
                        else:
                            st.error("El nombre del rol no puede estar vacío.")
            else:
                st.info("No hay roles disponibles para editar (los roles protegidos no se pueden modificar).")
        else:
            st.info("No hay roles para editar.")
    
    # Formulario para eliminar roles
    with st.expander("Eliminar Rol"):
        if not roles_df.empty:
            # Filtrar roles protegidos para eliminación usando criterios dinámicos
            # Los roles del sistema tienen descripciones que empiezan con "Rol del sistema:"
            roles_eliminables_df = roles_df[
                ~roles_df['descripcion'].str.startswith('Rol del sistema:', na=False)
            ]
            
            if not roles_eliminables_df.empty:
                rol_options = [f"{row['id_rol']} - {row['nombre']}" for _, row in roles_eliminables_df.iterrows()]
                selected_rol = st.selectbox("Seleccionar Rol para Eliminar", options=rol_options, key="select_rol_delete")
                
                if selected_rol:
                    rol_id = int(selected_rol.split(' - ')[0])
                    
                    if st.button("Eliminar Rol", key="delete_rol_btn"):
                        # Verificar si el rol está siendo usado por usuarios
                        conn = get_connection()
                        c = conn.cursor()
                        c.execute("SELECT COUNT(*) FROM usuarios WHERE rol_id = %s", (rol_id,))
                        count = c.fetchone()[0]
                        
                        if count > 0:
                            st.error(f"No se puede eliminar el rol porque está asignado a {count} usuarios.")
                        else:
                            c.execute("DELETE FROM roles WHERE id_rol = %s", (rol_id,))
                            conn.commit()
                            st.success("Rol eliminado exitosamente.")
                            st.rerun()
                        conn.close()
            else:
                st.info("No hay roles disponibles para eliminar (los roles protegidos no se pueden eliminar).")
        else:
                st.info("No hay roles para eliminar.")