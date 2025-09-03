import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
import sqlite3
import calendar
from .database import (
    get_connection, get_registros_dataframe, get_users_dataframe,
    get_tecnicos_dataframe, get_clientes_dataframe, get_tipos_dataframe, get_modalidades_dataframe,
    add_client, get_roles_dataframe, get_tipos_dataframe_with_roles,
    generate_roles_from_nomina, generate_users_from_nomina,
    get_grupos_dataframe, add_grupo, get_roles_by_grupo, update_grupo_roles,
    get_registros_by_rol_with_date_filter
)
from .nomina_management import render_nomina_edit_delete_forms
from .auth import create_user, validate_password, hash_password, is_2fa_enabled
from .utils import show_success_message
from .activity_logs import render_activity_logs

def render_admin_panel():
    """Renderiza el panel completo de administrador"""
    st.header("Panel de Administrador")
    
    # Crear pestañas principales del panel de administrador
    tab_visualizacion, tab_gestion = st.tabs(["📊 Visualización de Datos", "⚙️ Gestión"])
    
    with tab_visualizacion:
        render_data_visualization()
    
    with tab_gestion:
        render_management_tabs()

def render_data_visualization():
    """Renderiza la sección de visualización de datos organizada por roles"""
    # Obtener todos los registros
    df = get_registros_dataframe()
    
    if df.empty:
        st.info("No hay datos para mostrar")
        return
    
    # Obtener todos los roles disponibles
    roles_df = get_roles_dataframe()
    
    # Filtrar roles para omitir 'admin' y 'sin_rol' y ordenar por ID
    roles_filtrados = roles_df[~roles_df['nombre'].isin(['admin', 'sin_rol'])].sort_values('id_rol')
    
    # Crear pestañas para cada rol filtrado
    role_tabs = st.tabs([f"📊 {rol['nombre']}" for _, rol in roles_filtrados.iterrows()])
    
    # Para cada rol filtrado, crear sus propias visualizaciones
    for i, (_, rol) in enumerate(roles_filtrados.iterrows()):
        with role_tabs[i]:
            render_role_visualizations(df, rol['id_rol'], rol['nombre'])

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
            months = [(i, calendar.month_name[i]) for i in range(1, 13)]
            selected_month = st.selectbox(
                "Mes",
                options=[m[0] for m in months],
                format_func=lambda x: calendar.month_name[x],
                index=datetime.now().month - 1,
                key=f"month_{rol_id}"
            )
            
        custom_month = selected_month
        custom_year = selected_year
    
    # Obtener datos filtrados
    role_df = get_registros_by_rol_with_date_filter(rol_id, filter_type, custom_month, custom_year)
    
    if role_df.empty:
        period_text = {
            "current_month": "el mes actual",
            "custom_month": f"{calendar.month_name[custom_month]} {custom_year}" if custom_month and custom_year else "el período seleccionado",
            "all_time": "el período total"
        }[filter_type]
        st.info(f"No hay datos para mostrar para el rol {rol_nombre} en {period_text}")
        return
    
    # Crear pestañas para las diferentes visualizaciones del rol
    client_tab, task_tab, group_tab, user_tab, data_tab = st.tabs(["Horas por Cliente", "Tipos de Tarea", "Grupos", "Horas por Usuario", "Tabla de Registros"])
    
    with client_tab:
        st.subheader(f"Horas por Cliente - {rol_nombre}")
        
        # Agregar filtro por técnico
        tecnicos_disponibles = ['Todos'] + sorted(role_df['tecnico'].unique().tolist())
        tecnico_seleccionado = st.selectbox(
            "Filtrar por Técnico:",
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
            "Filtrar por Técnico:",
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
            "Filtrar por Técnico:",
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
            WHERE rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico')
        """)
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
                # Leer el archivo Excel
                excel_df = pd.read_excel(uploaded_file, engine='openpyxl')
                
                st.subheader("Vista previa del archivo")
                st.dataframe(excel_df.head(), use_container_width=True)
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
        if st.button("Procesar y cargar datos", key="process_excel"):
            success_count, error_count, duplicate_count = process_excel_data(excel_df)
            
            if success_count > 0:
                show_success_message(f"✅ {success_count} registros cargados exitosamente", 3)
            if duplicate_count > 0:
                st.warning(f"⚠️ {duplicate_count} registros duplicados omitidos")
                time.sleep(2)  # Pausa para que se vea el mensaje
            if error_count > 0:
                st.error(f"❌ {error_count} registros con errores no procesados")
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
    modalidad_options = modalidades_df['modalidad'].tolist()
    modalidad_index = modalidad_options.index(registro_seleccionado['modalidad']) if registro_seleccionado['modalidad'] in modalidad_options else 0
    modalidad_selected_edit_admin = st.selectbox("Modalidad", options=modalidad_options, index=modalidad_index, key=f"admin_edit_modalidad_{role_id if role_id else 'default'}")
    
    # Campos adicionales
    tarea_realizada_edit_admin = st.text_input("Tarea Realizada", value=registro_seleccionado['tarea_realizada'], key=f"admin_edit_tarea_{role_id if role_id else 'default'}")
    numero_ticket_edit_admin = st.text_input("Número de Ticket", value=registro_seleccionado['numero_ticket'], key=f"admin_edit_ticket_{role_id if role_id else 'default'}")
    tiempo_edit_admin = st.number_input("Tiempo (horas)", min_value=0.0, step=0.5, value=float(registro_seleccionado['tiempo']), key=f"admin_edit_tiempo_{role_id if role_id else 'default'}")
    descripcion_edit_admin = st.text_area("Descripción", value=registro_seleccionado['descripcion'] if pd.notna(registro_seleccionado['descripcion']) else "", key=f"admin_edit_descripcion_{role_id if role_id else 'default'}")
    
    # Mes (automático basado en la fecha)
    mes_edit_admin = calendar.month_name[fecha_edit_admin.month]
    
    if st.button("Guardar Cambios (Admin)", key=f"admin_save_registro_edit_{role_id if role_id else 'default'}"):
        if not tarea_realizada_edit_admin:
            st.error("La tarea realizada es obligatoria.")
        elif tiempo_edit_admin <= 0:
            st.error("El tiempo debe ser mayor que cero.")
        else:
            conn = get_connection()
            c = conn.cursor()
            
            # Obtener IDs
            c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (tecnico_selected_edit_admin,))
            id_tecnico_admin = c.fetchone()[0]
            
            c.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (cliente_selected_edit_admin,))
            id_cliente_admin = c.fetchone()[0]
            
            c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (tipo_selected_edit_admin,))
            id_tipo_admin = c.fetchone()[0]
            
            c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (modalidad_selected_edit_admin,))
            id_modalidad_admin = c.fetchone()[0]
            
            # Verificar si ya existe un registro con los mismos datos (excluyendo el registro actual)
            c.execute('''
                SELECT COUNT(*) FROM registros 
                WHERE fecha = ? AND id_tecnico = ? AND id_cliente = ? AND id_tipo = ? 
                AND id_modalidad = ? AND tarea_realizada = ? AND tiempo = ? AND id != ?
            ''', (fecha_formateada_edit_admin, id_tecnico_admin, id_cliente_admin, id_tipo_admin, 
                  id_modalidad_admin, tarea_realizada_edit_admin, tiempo_edit_admin, registro_id))
            
            duplicate_count_admin = c.fetchone()[0]
            if duplicate_count_admin > 0:
                st.error("Ya existe un registro con estos mismos datos. No se puede crear un duplicado.")
            else:
                # Actualizar registro
                c.execute('''
                    UPDATE registros SET 
                    fecha = ?, id_tecnico = ?, id_cliente = ?, id_tipo = ?, id_modalidad = ?,
                    tarea_realizada = ?, numero_ticket = ?, tiempo = ?, descripcion = ?, mes = ?, grupo = ?
                    WHERE id = ?
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
        c.execute("DELETE FROM registros WHERE id = ?", (registro_id,))
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
        # st.warning("Los usuarios se crearán con contraseñas aleatorias seguras que se mostrarán una sola vez.")
        
        if st.button("🔄 Generar Usuarios", type="primary", key="generate_users_user_tab"):
            with st.spinner("Generando usuarios..."):
                # Llamar a la función para generar usuarios
                stats = generate_users_from_nomina()
                
                # Mostrar siempre un mensaje, independientemente del resultado
                if stats["total"] == 0:
                    st.error("⚠️ NO SE DETECTARON NUEVOS USUARIOS PARA GENERAR. Todos los empleados en la nómina ya tienen usuarios asociados o no hay empleados en la nómina.")
                else:
                    if stats["creados"] > 0:
                        st.success(f"✅ Se crearon {stats['creados']} nuevos usuarios")
                        
                        # Mostrar tabla con los usuarios creados y sus contraseñas
                        if stats["usuarios"]:
                            st.warning("⚠️ **IMPORTANTE**: Guarde estas contraseñas ahora. No se mostrarán nuevamente.")
                            
                            # Crear DataFrame para mostrar los usuarios creados
                            users_df = pd.DataFrame(stats["usuarios"])
                            st.dataframe(users_df, use_container_width=True)
                            
                            # Opción para descargar como CSV
                            csv = users_df.to_csv(index=False)
                            st.download_button(
                                label="📥 Descargar usuarios y contraseñas",
                                data=csv,
                                file_name="nuevos_usuarios.csv",
                                mime="text/csv"
                            )
                    
                    if stats["errores"] > 0:
                        st.error(f"❌ Ocurrieron {stats['errores']} errores durante la creación de usuarios")
    
    
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
            if "sin_rol" in option.lower():
                default_index = i
                break
        
        selected_rol = st.selectbox("Rol", options=rol_options, index=default_index, key="new_user_rol")
        rol_id = int(selected_rol.split(' - ')[0])
        
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
                c.execute("SELECT rol_id FROM usuarios WHERE id = ?", (user_id,))
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
                        c.execute('SELECT nombre FROM roles WHERE id_rol = ?', (rol_id,))
                        rol_nombre = c.fetchone()
                        is_admin = False
                        if rol_nombre and rol_nombre[0].lower() == 'admin':
                            is_admin = True
                        
                        # Actualizar información básica incluyendo 2FA
                        c.execute("""UPDATE usuarios SET nombre = ?, apellido = ?, is_admin = ?, is_active = ?, 
                                     rol_id = ?, is_2fa_enabled = ? WHERE id = ?""", 
                                 (edit_nombre, edit_apellido, is_admin, edit_is_active, 
                                  rol_id, edit_is_2fa_enabled, user_id))
                        
                        # Si se deshabilita 2FA, limpiar el secreto TOTP
                        if not edit_is_2fa_enabled:
                            c.execute("UPDATE usuarios SET totp_secret = NULL WHERE id = ?", (user_id,))
                        
                        # Cambiar contraseña si se solicitó
                        if change_password and new_password:
                            # Validar la contraseña
                            is_valid, messages = validate_password(new_password)
                            if is_valid:
                                hashed_password = hash_password(new_password)
                                c.execute("UPDATE usuarios SET password = ? WHERE id = ?", 
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
        c.execute("SELECT COUNT(*) FROM registros WHERE usuario_id = ?", (user_id,))
        registro_count = c.fetchone()[0]
        
        # Eliminar primero todos los registros del usuario
        if registro_count > 0:
            c.execute("DELETE FROM registros WHERE usuario_id = ?", (user_id,))
            st.info(f"Se eliminaron {registro_count} registros asociados al usuario.")
        
        # Eliminar el usuario
        c.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
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
    st.subheader("Gestión de Clientes")
    
    # Formulario para agregar clientes
    with st.expander("Agregar Cliente"):
        new_client_name = st.text_input("Nombre del Cliente", key="new_client_name")
        
        if st.button("Agregar Cliente", key="add_client_btn"):
            if new_client_name:
                if add_client(new_client_name):
                    st.success(f"Cliente '{new_client_name}' agregado exitosamente.")
                    st.rerun()
                else:
                    st.error("Ya existe un cliente con ese nombre.")
            else:
                st.error("El nombre del cliente es obligatorio.")
    
    # Tabla de clientes existentes
    st.subheader("Clientes Existentes")
    clients_df = get_clientes_dataframe()
    # Ocultar columna id_cliente
    if not clients_df.empty and 'id_cliente' in clients_df.columns:
        st.dataframe(clients_df.drop(columns=['id_cliente']), use_container_width=True)
    else:
        st.dataframe(clients_df, use_container_width=True)
    
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
                        conn = get_connection()
                        c = conn.cursor()
                        try:
                            c.execute("UPDATE clientes SET nombre = ? WHERE id_cliente = ?", (edit_client_name, client_id))
                            conn.commit()
                            st.success("Cliente actualizado exitosamente.")
                            st.rerun()
                        except Exception as e:
                            if "UNIQUE constraint failed" in str(e):
                                st.error("Ya existe un cliente con ese nombre.")
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
                        c.execute("SELECT COUNT(*) FROM registros WHERE id_cliente = ?", (client_id,))
                        registro_count = c.fetchone()[0]
                        
                        if registro_count > 0:
                            st.error(f"No se puede eliminar el cliente porque tiene {registro_count} registros asociados.")
                        else:
                            c.execute("DELETE FROM clientes WHERE id_cliente = ?", (client_id,))
                            conn.commit()
                            show_success_message(f"✅ Cliente '{client_row['nombre']}' eliminado exitosamente.", 1.5)
                    except Exception as e:
                        st.error(f"Error al eliminar cliente: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay clientes para eliminar.")

def render_task_type_management():
    """Renderiza la gestión de tipos de tarea"""
    st.subheader("Gestión de Tipos de Tarea")
    
    # Inicializar contador para generar keys únicos
    if "task_type_counter" not in st.session_state:
        st.session_state.task_type_counter = 0
    
    # Obtener roles disponibles
    roles_df = get_roles_dataframe()
    
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
                conn = get_connection()
                c = conn.cursor()
                try:
                    # Insertar el tipo de tarea
                    c.execute("INSERT INTO tipos_tarea (descripcion) VALUES (?)", (new_task_type,))
                    tipo_id = c.lastrowid
                    
                    # Asociar con los roles seleccionados
                    for rol_id in selected_roles:
                        c.execute("INSERT INTO tipos_tarea_roles (id_tipo, id_rol) VALUES (?, ?)", 
                                 (tipo_id, rol_id))
                    
                    conn.commit()
                    st.success("Tipo de tarea agregado exitosamente.")
                    # Incrementar el contador para generar un nuevo key y limpiar el campo
                    st.session_state.task_type_counter += 1
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Ya existe un tipo de tarea con esa descripción.")
                finally:
                    conn.close()
            else:
                st.error("La descripción del tipo de tarea es obligatoria.")
    
    # Tabla de tipos de tarea existentes con sus roles asociados
    tipos_df = get_tipos_dataframe_with_roles()
    if not tipos_df.empty:
        st.subheader("Tipos de Tarea Existentes")
        # Ocultar columna id_tipo
        if 'id_tipo' in tipos_df.columns:
            st.dataframe(tipos_df.drop(columns=['id_tipo']), use_container_width=True)
        else:
            st.dataframe(tipos_df, use_container_width=True)
    else:
        st.subheader("Tipos de Tarea Existentes")
        st.dataframe(tipos_df, use_container_width=True)
    
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
                c.execute("SELECT id_rol FROM tipos_tarea_roles WHERE id_tipo = ?", (tipo_id,))
                current_roles = [row[0] for row in c.fetchall()]
                conn.close()
                
                # Selección múltiple de roles
                edit_selected_roles = st.multiselect(
                    "Roles que pueden acceder a este tipo de tarea",
                    options=get_roles_dataframe(exclude_admin=True)['id_rol'].tolist(),
                    default=current_roles,
                    format_func=lambda x: roles_df.loc[roles_df['id_rol'] == x, 'nombre'].iloc[0],
                    key="edit_task_type_roles"
                )
                
                if st.button("Guardar Cambios de Tipo de Tarea", key="save_tipo_edit"):
                    if edit_tipo_desc:
                        conn = get_connection()
                        c = conn.cursor()
                        try:
                            # Actualizar descripción del tipo de tarea
                            c.execute("UPDATE tipos_tarea SET descripcion = ? WHERE id_tipo = ?", (edit_tipo_desc, tipo_id))
                            
                            # Eliminar todas las asociaciones actuales
                            c.execute("DELETE FROM tipos_tarea_roles WHERE id_tipo = ?", (tipo_id,))
                            
                            # Crear nuevas asociaciones con los roles seleccionados
                            for rol_id in edit_selected_roles:
                                c.execute("INSERT INTO tipos_tarea_roles (id_tipo, id_rol) VALUES (?, ?)", 
                                         (tipo_id, rol_id))
                            
                            conn.commit()
                            st.success("Tipo de tarea actualizado exitosamente.")
                            st.rerun()
                        except Exception as e:
                            if "UNIQUE constraint failed" in str(e):
                                st.error("Ya existe un tipo de tarea con esa descripción.")
                            else:
                                st.error(f"Error al actualizar tipo de tarea: {str(e)}")
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
                        c.execute("SELECT COUNT(*) FROM registros WHERE id_tipo = ?", (tipo_id,))
                        registro_count = c.fetchone()[0]
                        
                        if registro_count > 0:
                            st.error(f"No se puede eliminar el tipo de tarea porque tiene {registro_count} registros asociados.")
                        else:
                            c.execute("DELETE FROM tipos_tarea WHERE id_tipo = ?", (tipo_id,))
                            conn.commit()
                            show_success_message(f"✅ Tipo de tarea '{tipo_row['descripcion']}' eliminado exitosamente.", 1.5)
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
                conn = get_connection()
                c = conn.cursor()
                try:
                    c.execute("INSERT INTO modalidades_tarea (modalidad) VALUES (?)", (new_modality,))
                    conn.commit()
                    st.success(f"Modalidad '{new_modality}' agregada exitosamente.")
                    st.rerun()
                except Exception as e:
                    if "UNIQUE constraint failed" in str(e):
                        st.error("Esta modalidad ya existe.")
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
            modalidad_names = modalidades_df['modalidad'].tolist()
            modalidad_options = [f"{mid} - {mname}" for mid, mname in zip(modalidad_ids, modalidad_names)]
            
            selected_modalidad_edit = st.selectbox("Seleccionar Modalidad para Editar", 
                                                   options=modalidad_options, key="select_modalidad_edit")
            if selected_modalidad_edit:
                modalidad_id = int(selected_modalidad_edit.split(' - ')[0])
                modalidad_row = modalidades_df[modalidades_df['id_modalidad'] == modalidad_id].iloc[0]
                
                edit_modalidad_name = st.text_input("Nombre de la Modalidad", value=modalidad_row['modalidad'], key="edit_modalidad_name")
                
                if st.button("Guardar Cambios de Modalidad", key="save_modalidad_edit"):
                    if edit_modalidad_name:
                        conn = get_connection()
                        c = conn.cursor()
                        try:
                            c.execute("UPDATE modalidades_tarea SET modalidad = ? WHERE id_modalidad = ?", (edit_modalidad_name, modalidad_id))
                            conn.commit()
                            st.success("Modalidad actualizada exitosamente.")
                            st.rerun()
                        except Exception as e:
                            if "UNIQUE constraint failed" in str(e):
                                st.error("Ya existe una modalidad con ese nombre.")
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
            modalidad_names = modalidades_df['modalidad'].tolist()
            modalidad_options = [f"{mid} - {mname}" for mid, mname in zip(modalidad_ids, modalidad_names)]
            
            selected_modalidad_delete = st.selectbox("Seleccionar Modalidad para Eliminar", 
                                                     options=modalidad_options, key="select_modalidad_delete")
            if selected_modalidad_delete:
                modalidad_id = int(selected_modalidad_delete.split(' - ')[0])
                modalidad_row = modalidades_df[modalidades_df['id_modalidad'] == modalidad_id].iloc[0]
                
                st.warning("¿Estás seguro de que deseas eliminar esta modalidad? Esta acción no se puede deshacer.")
                st.info(f"**Modalidad a eliminar:** {modalidad_row['modalidad']}")
                
                if st.button("Eliminar Modalidad", key="delete_modalidad_btn", type="primary"):
                    conn = get_connection()
                    c = conn.cursor()
                    try:
                        # Verificar si hay registros asociados
                        c.execute("SELECT COUNT(*) FROM registros WHERE id_modalidad = ?", (modalidad_id,))
                        registro_count = c.fetchone()[0]
                        
                        if registro_count > 0:
                            st.error(f"No se puede eliminar la modalidad porque tiene {registro_count} registros asociados.")
                        else:
                            c.execute("DELETE FROM modalidades_tarea WHERE id_modalidad = ?", (modalidad_id,))
                            conn.commit()
                            show_success_message(f"✅ Modalidad '{modalidad_row['modalidad']}' eliminada exitosamente.", 1.5)
                    except Exception as e:
                        st.error(f"Error al eliminar modalidad: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay modalidades para eliminar.")

def process_excel_data(excel_df):
    """Procesa y carga datos desde Excel con control de duplicados y estandarización"""
    import calendar
    import sqlite3
    import openpyxl  # Importar explícitamente openpyxl
    from datetime import datetime
    from .database import get_or_create_tecnico, get_or_create_cliente, get_or_create_tipo_tarea, get_or_create_modalidad
    
    # Limpiar DataFrame: eliminar filas con fechas vacías
    excel_df = excel_df.dropna(subset=['Fecha'])  # Eliminar filas donde 'Fecha' es NaN
    excel_df = excel_df[excel_df['Fecha'] != '']  # Eliminar filas donde 'Fecha' está vacía
    
    if excel_df.empty:
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
        'Sector': 'grupo'  # Agregar mapeo para la columna Sector/Grupo
    }
    
    # Renombrar columnas para que coincidan con el formato esperado
    excel_df_mapped = excel_df.rename(columns=column_mapping)
    
    # Obtener mapeos existentes para verificar qué entidades son nuevas
    tecnicos_df = get_tecnicos_dataframe()
    clientes_df = get_clientes_dataframe()
    tipos_df = get_tipos_dataframe()
    modalidades_df = get_modalidades_dataframe()
    
    existing_tecnicos = set(tecnicos_df['nombre'].tolist())
    existing_clientes = set(clientes_df['nombre'].tolist())
    existing_tipos = set(tipos_df['descripcion'].tolist())
    existing_modalidades = set(modalidades_df['modalidad'].tolist())
    
    for index, row in excel_df_mapped.iterrows():
        try:
            # Verificar si la fecha es válida antes de procesarla
            if pd.isna(row['fecha']) or str(row['fecha']).strip() in ['', 'NaT', 'nan']:
                continue  # Omitir filas con fechas vacías
            
            # Estandarizar fecha
            fecha_str = str(row['fecha'])
            try:
                if '/' in fecha_str:
                    if len(fecha_str.split('/')[-1]) == 2:
                        fecha_obj = datetime.strptime(fecha_str, '%d/%m/%y')
                    else:
                        fecha_obj = datetime.strptime(fecha_str, '%d/%m/%Y')
                else:
                    fecha_obj = pd.to_datetime(fecha_str)
                fecha_formateada = fecha_obj.strftime('%d/%m/%y')
            except:
                continue  # Omitir filas con fechas que no se pueden procesar
            
            # Obtener y crear entidades automáticamente
            tecnico = str(row['tecnico']).strip()
            cliente = str(row['cliente']).strip()
            tipo_tarea = str(row['tipo_tarea']).strip()
            modalidad = str(row['modalidad']).strip()
            
            # Verificar si existe la columna grupo y obtener su valor
            grupo = "General"  # Valor predeterminado
            if 'grupo' in row and pd.notna(row['grupo']) and str(row['grupo']).strip() != '':
                grupo = str(row['grupo']).strip()
            
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
                st.error(f"Fila {index + 1}: Error al crear/obtener entidades - {str(e)}")
                error_count += 1
                continue
            
            # Validar otros campos
            tarea_realizada = str(row['tarea_realizada']).strip()
            numero_ticket = str(row['numero_ticket']).strip() if pd.notna(row['numero_ticket']) else 'N/A'
            tiempo = float(row['tiempo'])
            descripcion = str(row.get('descripcion', '')).strip() if pd.notna(row.get('descripcion')) else ''
            mes = calendar.month_name[fecha_obj.month]
            
            # Verificar duplicados
            # Verificar duplicados
            c.execute('''
                SELECT COUNT(*) FROM registros 
                WHERE fecha = ? AND id_tecnico = ? AND id_cliente = ? AND id_tipo = ?
                AND id_modalidad = ? AND tarea_realizada = ? AND tiempo = ?
            ''', (fecha_formateada, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, tiempo))
            
            if c.fetchone()[0] > 0:
                duplicate_count += 1
                continue
            
            # Insertar registro incluyendo el campo grupo
            c.execute('''
                INSERT INTO registros 
                (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
                 numero_ticket, tiempo, descripcion, mes, usuario_id, grupo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (fecha_formateada, id_tecnico, id_cliente, id_tipo, id_modalidad, 
                  tarea_realizada, numero_ticket, tiempo, descripcion, mes, None, grupo))
            
            success_count += 1
            
        except Exception as e:
            st.error(f"Fila {index + 1}: Error al procesar - {str(e)}")
            error_count += 1
    
    conn.commit()
    
    # NUEVA FUNCIONALIDAD: Asignación automática de registros por técnico
    auto_assign_records_by_technician(conn)
    
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
    
    return success_count, error_count, duplicate_count


def auto_assign_records_by_technician(conn):
    """Asigna automáticamente registros a usuarios basándose en el nombre del técnico"""
    c = conn.cursor()
    
    # Obtener todos los usuarios con nombre y apellido
    c.execute("SELECT id, nombre, apellido FROM usuarios WHERE nombre IS NOT NULL AND apellido IS NOT NULL")
    usuarios = c.fetchall()
    
    registros_asignados = 0
    
    for usuario_id, nombre, apellido in usuarios:
        nombre_completo = f"{nombre} {apellido}"
        
        # Buscar registros sin usuario asignado donde el técnico coincida
        c.execute("""
            UPDATE registros SET usuario_id = ? 
            WHERE usuario_id IS NULL AND id_tecnico IN (
                SELECT id_tecnico FROM tecnicos WHERE nombre = ?
            )
        """, (usuario_id, nombre_completo))
        
        registros_actualizados = c.rowcount
        registros_asignados += registros_actualizados
        
        if registros_actualizados > 0:
            st.info(f"✅ Asignados {registros_actualizados} registros a {nombre_completo}")
    
    if registros_asignados > 0:
        conn.commit()
        st.success(f"🎯 Total de registros asignados automáticamente: {registros_asignados}")
    
    return registros_asignados


def fix_existing_records_assignment():
    """Corrige la asignación de registros existentes basándose en el nombre del técnico y su rol"""
    conn = get_connection()
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
        tecnicos_procesados = set()  # Conjunto para rastrear técnicos procesados
        
        # Función para normalizar texto (eliminar acentos y convertir a minúsculas)
        def normalizar_texto(texto):
            import unicodedata
            # Normalizar NFD y eliminar diacríticos
            texto_sin_acentos = ''.join(c for c in unicodedata.normalize('NFD', texto) 
                                      if unicodedata.category(c) != 'Mn')
            return texto_sin_acentos.lower()
        
        # Diccionario para almacenar información de usuarios por nombre normalizado
        usuarios_por_nombre = {}
        for usuario_id, nombre, apellido, rol_id, rol_nombre in usuarios:
            nombre_completo = f"{nombre} {apellido}"
            nombre_norm = normalizar_texto(nombre_completo)
            usuarios_por_nombre[nombre_norm] = {
                "id": usuario_id,
                "nombre_completo": nombre_completo,
                "nombre": nombre,
                "apellido": apellido,
                "rol_id": rol_id,
                "rol_nombre": rol_nombre
            }
        
        # Procesar cada técnico
        for tecnico_id, tecnico_nombre in tecnicos:
            tecnico_norm = normalizar_texto(tecnico_nombre)
            partes_tecnico = tecnico_norm.split()
            
            # Buscar coincidencias con usuarios
            for usuario_norm, usuario_info in usuarios_por_nombre.items():
                partes_usuario = usuario_norm.split()
                
                # Verificar coincidencias de nombre y apellido
                coincidencia_nombre = False
                coincidencia_apellido = False
                
                for parte_tecnico in partes_tecnico:
                    if len(parte_tecnico) > 2:  # Evitar partículas
                        for parte_usuario in partes_usuario:
                            if len(parte_usuario) > 2 and (parte_tecnico in parte_usuario or parte_usuario in parte_tecnico):
                                if not coincidencia_nombre:
                                    coincidencia_nombre = True
                                else:
                                    coincidencia_apellido = True
                                break
                
                # Si hay coincidencia tanto de nombre como de apellido
                if coincidencia_nombre and coincidencia_apellido:
                    # Agregar a la lista de técnicos procesados
                    tecnicos_procesados.add(tecnico_id)
                    
                    # Actualizar registros para este técnico
                    c.execute("""
                        UPDATE registros SET usuario_id = ? 
                        WHERE id_tecnico = ?
                    """, (usuario_info["id"], tecnico_id))
                    
                    registros_actualizados = c.rowcount
                    registros_asignados += registros_actualizados
                    break
        
        # Mostrar resumen de resultados
        if registros_asignados > 0:
            conn.commit()
            st.success(f"🎯 Total de registros reasignados: {registros_asignados}")
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
                # Analizar por qué no se pudo procesar
                tecnico_norm = normalizar_texto(tecnico_nombre)
                partes_tecnico = tecnico_norm.split()
                
                # Encontrar el usuario más cercano
                mejor_coincidencia = None
                mejor_puntuacion = 0
                razon = ""
                
                for usuario_norm, usuario_info in usuarios_por_nombre.items():
                    partes_usuario = usuario_norm.split()
                    puntuacion = 0
                    
                    # Verificar coincidencias parciales
                    for parte_tecnico in partes_tecnico:
                        if len(parte_tecnico) > 2:
                            for parte_usuario in partes_usuario:
                                if len(parte_usuario) > 2 and (parte_tecnico in parte_usuario or parte_usuario in parte_tecnico):
                                    puntuacion += 1
                                    break
                    
                    if puntuacion > mejor_puntuacion:
                        mejor_puntuacion = puntuacion
                        mejor_coincidencia = usuario_info["nombre_completo"]
                
                # Determinar la razón por la que no se procesó
                if mejor_puntuacion == 0:
                    razon = "No hay coincidencias con ningún usuario en el sistema"
                elif mejor_puntuacion == 1:
                    razon = "Solo hay coincidencia parcial con un usuario (nombre o apellido)"
                else:
                    razon = "Hay coincidencias parciales pero no suficientes para una asignación automática"
                
                # Mostrar información de diagnóstico
                st.markdown(f"**{tecnico_nombre}**")
                st.write(f"Razón: {razon}")
                if mejor_coincidencia:
                    st.write(f"Usuario más cercano: {mejor_coincidencia} (coincidencias: {mejor_puntuacion})")
                st.write("---")
    
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
                    c.execute("SELECT id_grupo FROM grupos WHERE nombre = ?", (nombre_grupo,))
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
                            c.execute("SELECT id_grupo, nombre FROM grupos WHERE id_grupo != ?", (grupo_id,))
                            existing_grupos = c.fetchall()
                            nombre_normalizado = normalize_text(edit_grupo_nombre)
                            
                            duplicado = False
                            for existing_id, existing_nombre in existing_grupos:
                                if normalize_text(existing_nombre) == nombre_normalizado:
                                    duplicado = True
                                    break
                            
                            if not duplicado:
                                # Actualizar grupo
                                c.execute("UPDATE grupos SET nombre = ?, descripcion = ? WHERE id_grupo = ?", 
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
                            c.execute("SELECT COUNT(*) FROM usuarios WHERE grupo_id = ?", (grupo_id,))
                            usuario_count = c.fetchone()[0]
                            
                            if usuario_count > 0:
                                st.error(f"No se puede eliminar el grupo porque tiene {usuario_count} usuarios asociados.")
                                return
                        except sqlite3.OperationalError as e:
                            # Si la columna no existe, asumimos que no hay usuarios asociados
                            if "no such column: grupo_id" in str(e):
                                # Continuar con la eliminación
                                pass
                            else:
                                # Si es otro error, lo mostramos
                                raise e
                        
                        # Eliminar el grupo
                        c.execute("DELETE FROM grupos WHERE id_grupo = ?", (grupo_id,))
                        conn.commit()
                        show_success_message(f"✅ Grupo '{grupo_row['nombre']}' eliminado exitosamente.", 1.5)
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
        
        st.subheader("📋 Datos originales del archivo")
        st.dataframe(excel_df_display, use_container_width=True)
        
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
                    preview_df, success_count, error_count, duplicate_count = process_nomina_excel(df_processed)
                    
                    # Mostrar estadísticas de procesamiento
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Filas procesadas", len(df_processed))
                    with col2:
                        st.metric("Duplicados eliminados", duplicates_removed)
                    with col3:
                        st.metric("Empleados guardados", success_count)
                    
                    # Mostrar resultados con mayor duración
                    if success_count > 0:
                        st.success(f"✅ {success_count} empleados guardados exitosamente en la nómina")
                        time.sleep(2)  # Hacer que el mensaje dure más tiempo
                        # Guardar el DataFrame de vista previa para mostrarlo en la tabla final
                        if 'nomina_preview_df' not in st.session_state:
                            st.session_state.nomina_preview_df = None
                        st.session_state.nomina_preview_df = preview_df
                        
                        # Generar roles automáticamente después de agregar empleados
                        roles_stats = generate_roles_from_nomina()
                        if roles_stats["nuevos"] > 0:
                            st.success(f"✅ Se crearon {roles_stats['nuevos']} nuevos roles basados en los sectores")
                            if roles_stats["nuevos_roles"]:
                                st.info(f"Nuevos roles creados: {', '.join(roles_stats['nuevos_roles'])}")
                        
                    if duplicate_count > 0:
                        st.warning(f"⚠️ {duplicate_count} empleados ya existían en la base de datos")
                        time.sleep(1.5)
                    if error_count > 0:
                        st.error(f"❌ {error_count} errores durante el procesamiento")
                        time.sleep(2)
                    
                    if duplicates_removed > 0:
                        st.info(f"🔄 Se eliminaron {duplicates_removed} filas duplicadas del archivo")
                        time.sleep(1.5)
                        
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
                    departamentos_filtrados = nomina_df[~nomina_df['departamento'].isin(['admin', 'sin_rol'])]
                    departamentos = departamentos_filtrados['departamento'].nunique()
                else:
                    departamentos = 0
                st.metric("Departamentos", departamentos)
            
            # Siempre mostrar la vista expandida por defecto
            expanded_df = get_nomina_dataframe_expanded()
            
            # Si hay datos de vista previa guardados (más completos), usar esos
            if 'nomina_preview_df' in st.session_state and st.session_state.nomina_preview_df is not None and not st.session_state.nomina_preview_df.empty:
                st.subheader("📊 Vista completa de empleados (con todas las columnas del Excel)")
                st.dataframe(st.session_state.nomina_preview_df, use_container_width=True)
            else:
                # Mostrar vista expandida generada desde la BD
                st.subheader("📊 Vista completa de empleados")
                st.dataframe(expanded_df, use_container_width=True)

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
                            c.execute("INSERT INTO roles (nombre, descripcion, is_hidden) VALUES (?, ?, ?)", 
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
    c.execute("PRAGMA table_info(roles)")
    columns = [column[1] for column in c.fetchall()]
    
    if 'is_hidden' in columns:
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
                                c.execute("UPDATE roles SET nombre = ?, descripcion = ?, is_hidden = ? WHERE id_rol = ?", 
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
            # Filtrar roles protegidos para eliminación
            roles_eliminables_df = roles_df[~roles_df['nombre'].str.lower().isin(['admin', 'tecnico', 'sin_rol'])]
            
            if not roles_eliminables_df.empty:
                rol_options = [f"{row['id_rol']} - {row['nombre']}" for _, row in roles_eliminables_df.iterrows()]
                selected_rol = st.selectbox("Seleccionar Rol para Eliminar", options=rol_options, key="select_rol_delete")
                
                if selected_rol:
                    rol_id = int(selected_rol.split(' - ')[0])
                    
                    if st.button("Eliminar Rol", key="delete_rol_btn"):
                        # Verificar si el rol está siendo usado por usuarios
                        conn = get_connection()
                        c = conn.cursor()
                        c.execute("SELECT COUNT(*) FROM usuarios WHERE rol_id = ?", (rol_id,))
                        count = c.fetchone()[0]
                        
                        if count > 0:
                            st.error(f"No se puede eliminar el rol porque está asignado a {count} usuarios.")
                        else:
                            c.execute("DELETE FROM roles WHERE id_rol = ?", (rol_id,))
                            conn.commit()
                            st.success("Rol eliminado exitosamente.")
                            st.rerun()
                        conn.close()
            else:
                st.info("No hay roles disponibles para eliminar (los roles protegidos no se pueden eliminar).")
        else:
                st.info("No hay roles para eliminar.")