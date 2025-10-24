import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import calendar
import time
from .database import (
    get_connection, get_user_registros_dataframe, get_user_registros_dataframe_cached,
    get_tecnicos_dataframe, get_clientes_dataframe, 
    get_tipos_dataframe, get_modalidades_dataframe,
    get_unassigned_records_for_user, get_user_rol_id,
    get_grupos_by_rol, clear_user_registros_cache,
    get_users_by_rol, get_user_weekly_modalities, get_weekly_modalities_by_rol,
    upsert_user_modality_for_date
)
from .utils import get_week_dates, format_week_range, prepare_weekly_chart_data, show_success_message, month_name_es

def render_user_dashboard(user_id, nombre_completo_usuario):
    """Renderiza el dashboard principal del usuario"""
    st.header(f"Dashboard - {nombre_completo_usuario}")
    
    tab_registros, tab_resumen, tab_planificacion = st.tabs(["📝 Nuevo Registro", "📊 Mis Registros", "🏢 Planificación Semanal"])
    
    with tab_registros:
        render_records_management(user_id, nombre_completo_usuario)
    
    with tab_resumen:
        render_hours_overview(user_id, nombre_completo_usuario)
        
    with tab_planificacion:
        render_weekly_modality_planner(user_id, nombre_completo_usuario)
    

def render_hours_overview(user_id, nombre_completo_usuario):
    """Renderiza la vista general de horas trabajadas"""
    user_registros_df = get_user_registros_dataframe_cached(user_id)
    
    if user_registros_df.empty:
        st.info("No tienes registros de horas aún. Ve a la pestaña 'Gestión de Registros' para agregar tu primer registro.")
        return
    
    # Gráfico semanal en la parte superior
    st.subheader("📈 Gráfico Semanal")
    render_weekly_chart_optimized(user_registros_df)
    
    # Detalle de registros en la parte inferior
    st.subheader("📋 Detalle de Registros")
    
    if 'fecha_dt' in user_registros_df.columns:
        user_registros_df = user_registros_df.drop(columns=['fecha_dt'])
    
    st.dataframe(
        user_registros_df,
        use_container_width=True,
        hide_index=True
    )
    
    render_edit_delete_expanders(user_id, nombre_completo_usuario)

def render_weekly_chart_optimized(user_registros_df):
    """Renderiza el gráfico semanal de horas trabajadas con optimizaciones"""
    
    # Inicializar week_offset si no existe
    if 'week_offset' not in st.session_state:
        st.session_state.week_offset = 0
    
    # Obtener fechas de la semana seleccionada
    start_of_selected_week, end_of_selected_week = get_week_dates(st.session_state.week_offset)
    week_range_str = format_week_range(start_of_selected_week, end_of_selected_week)
    
    # Texto "Ir a la semana de:" siempre visible
    st.markdown("**Ir a la semana de:**")
    
    # Layout simplificado - solo date_input y botones de navegación
    nav_cols = st.columns([1.8, 0.1, 0.6, 1.8, 0.6, 3.1])
    
    with nav_cols[0]:
        selected_date = st.date_input(
            "",
            value=datetime.today(),
            key="calendar_date_picker",
            label_visibility="collapsed"
        )
        
        # Detectar cambio en la fecha y actualizar automáticamente
        if 'last_selected_date' not in st.session_state:
            st.session_state.last_selected_date = datetime.today().date()
        
        if selected_date != st.session_state.last_selected_date:
            # Calcular el offset de semanas desde hoy hasta la fecha seleccionada
            today = datetime.today().date()
            days_diff = (selected_date - today).days
            st.session_state.week_offset = days_diff // 7
            st.session_state.last_selected_date = selected_date
            st.rerun()
    
    with nav_cols[1]:
        st.write("") 
    
    with nav_cols[2]:
        if st.button("⬅️", use_container_width=True):
            st.session_state.week_offset -= 1
            st.rerun()
    
    with nav_cols[3]:
        st.markdown(f"<p style='text-align: center; font-weight: bold; margin: 0; padding: 8px;'>{week_range_str}</p>", unsafe_allow_html=True)
    
    with nav_cols[4]:
        disable_next = st.session_state.week_offset == 0
        if st.button("➡️", disabled=disable_next, use_container_width=True):
            st.session_state.week_offset += 1
            st.rerun()
    
    with nav_cols[5]:
        st.write("")  
    
    # Verificar si existe la columna fecha_dt, si no, procesarla
    if 'fecha_dt' not in user_registros_df.columns:
        registros_validos = user_registros_df.dropna(subset=['fecha'])
        if registros_validos.empty:
            st.info("No hay registros válidos para mostrar.")
            return
        # Procesar fechas si no están procesadas
        def convert_fecha_to_datetime(fecha_str):
            try:
                return pd.to_datetime(fecha_str, format='%d/%m/%y')
            except:
                try:
                    return pd.to_datetime(fecha_str, format='%d/%m/%Y')
                except:
                    try:
                        return pd.to_datetime(fecha_str, dayfirst=True)
                    except:
                        return pd.NaT
        user_registros_df['fecha_dt'] = user_registros_df['fecha'].apply(convert_fecha_to_datetime)
    
    # OPTIMIZACIÓN: Filtrar los registros para la semana seleccionada de forma más eficiente
    weekly_df = user_registros_df[
        (user_registros_df['fecha_dt'].dt.date >= start_of_selected_week.date()) &
        (user_registros_df['fecha_dt'].dt.date <= end_of_selected_week.date())
    ]
    
    if not weekly_df.empty:
        # Preparar datos para el gráfico (usar caché si es posible)
        chart_cache_key = f"chart_data_{st.session_state.week_offset}"
        
        if chart_cache_key not in st.session_state:
            horas_por_dia_final = prepare_weekly_chart_data(weekly_df, start_of_selected_week)
            st.session_state[chart_cache_key] = horas_por_dia_final
        else:
            horas_por_dia_final = st.session_state[chart_cache_key]
        
        fig = px.bar(horas_por_dia_final, x='dia_con_fecha', y='tiempo', 
                   labels={'dia_con_fecha': 'Día de la Semana', 'tiempo': 'Horas Totales'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay registros para la semana seleccionada.")

def render_records_management(user_id, nombre_completo_usuario):
    """Renderiza la gestión de registros (solo agregar)"""
    render_add_record_form(user_id, nombre_completo_usuario)

def render_add_record_form(user_id, nombre_completo_usuario):
    """Renderiza el formulario para agregar nuevos registros"""
    st.subheader("Nuevo Registro de Horas")
    
    rol_id = get_user_rol_id(user_id)
    
    clientes_df = get_clientes_dataframe()
    tipos_df = get_tipos_dataframe(rol_id=rol_id)
    modalidades_df = get_modalidades_dataframe()
    grupos = get_grupos_by_rol(rol_id)
    
    if clientes_df.empty or tipos_df.empty or modalidades_df.empty:
        st.warning("No hay datos suficientes para completar el formulario. Contacta al administrador.")
    
    grupo_names = [grupo[1] for grupo in grupos]
    if "General" not in grupo_names:
        grupo_names.insert(0, "General")
    else:
        grupo_names.remove("General")
        grupo_names.insert(0, "General")
    
    
    st.info(f"Técnico: {nombre_completo_usuario}")
    
    
    grupo_selected = st.selectbox("Sector:", options=grupo_names, index=0, key="new_grupo")
    
    col1, col2 = st.columns(2)
    
    with col1:
        fecha_nuevo = st.date_input("Fecha", value=datetime.today(), key="new_fecha")
        fecha_formateada_nuevo = fecha_nuevo.strftime('%d/%m/%y')
        
        cliente_options = clientes_df['nombre'].tolist()
        cliente_selected_nuevo = st.selectbox("Cliente", options=cliente_options, key="new_cliente")
        
        tipo_options = tipos_df['descripcion'].tolist()
        tipo_selected_nuevo = st.selectbox("Tipo de Tarea", options=tipo_options, key="new_tipo")
    
    with col2:
        modalidad_options = modalidades_df['descripcion'].tolist()
        modalidad_selected_nuevo = st.selectbox("Modalidad", options=modalidad_options, key="new_modalidad")
        
        tarea_realizada_nuevo = st.text_input("Tarea Realizada", key="new_tarea")
        numero_ticket_nuevo = st.text_input("Número de Ticket", key="new_ticket")
        tiempo_nuevo = st.number_input("Tiempo (horas)", min_value=0.5, step=0.5, key="new_tiempo")
    
    descripcion_nuevo = st.text_area("Descripción (opcional)", key="new_descripcion")
    mes_nuevo = month_name_es(fecha_nuevo.month)
    
    if st.button("💾 Guardar Registro", key="save_new_registro", type="primary"):
        if not tarea_realizada_nuevo:
            st.error("La tarea realizada es obligatoria.")
        elif tiempo_nuevo < 0.5:
            st.error("El tiempo mínimo debe ser de 0.5 horas (30 minutos).")
        else:
            save_new_user_record(
                user_id, fecha_formateada_nuevo, nombre_completo_usuario,
                cliente_selected_nuevo, tipo_selected_nuevo, modalidad_selected_nuevo,
                tarea_realizada_nuevo, numero_ticket_nuevo, tiempo_nuevo, 
                descripcion_nuevo, mes_nuevo, grupo_selected
            )

def render_edit_delete_expanders(user_id, nombre_completo_usuario):
    """Renderiza los desplegables para editar y eliminar registros"""
    user_registros_df = get_user_registros_dataframe(user_id)
    unassigned_registros_df = get_unassigned_records_for_user(user_id)
    
    def convert_fecha_to_datetime(fecha_str):
        """Convierte fecha string a datetime con múltiples formatos"""
        try:
            return pd.to_datetime(fecha_str, format='%d/%m/%y')
        except:
            try:
                return pd.to_datetime(fecha_str, format='%d/%m/%Y')
            except:
                try:
                    return pd.to_datetime(fecha_str, dayfirst=True)
                except:
                    return pd.NaT
    
    # Aplicar la conversión a ambos dataframes
    if not user_registros_df.empty:
        user_registros_df['fecha_dt'] = user_registros_df['fecha'].apply(convert_fecha_to_datetime)
    
    if not unassigned_registros_df.empty:
        unassigned_registros_df['fecha_dt'] = unassigned_registros_df['fecha'].apply(convert_fecha_to_datetime)
    
    # Combinar ambos DataFrames
    if not unassigned_registros_df.empty:
        combined_df = pd.concat([user_registros_df, unassigned_registros_df], ignore_index=True)
        # Ordenar por fecha_dt en lugar de fecha
        combined_df = combined_df.sort_values('fecha_dt', ascending=False)
    else:
        combined_df = user_registros_df
        if not combined_df.empty:
            # Ordenar por fecha_dt en lugar de fecha
            combined_df = combined_df.sort_values('fecha_dt', ascending=False)
    
    if not combined_df.empty:
        # Desplegable para editar registros
        with st.expander("✏️ Editar Registro", expanded=False):
            st.subheader("Editar Registro Existente")
            
            registro_ids = combined_df['id'].tolist()
            registro_fechas = combined_df['fecha'].tolist()
            registro_tareas = combined_df['tarea_realizada'].tolist()
            registro_clientes = combined_df['cliente'].tolist()
            
            # Mejorar la construcción de opciones con manejo de valores nulos
            registro_options = []
            for rid, rfecha, rtarea, rcliente in zip(registro_ids, registro_fechas, registro_tareas, registro_clientes):
                # Manejar valores nulos o vacíos
                tarea_display = rtarea if rtarea and str(rtarea).strip() else "Sin descripción"
                cliente_display = rcliente if rcliente and str(rcliente).strip() else "Sin cliente"
                fecha_display = rfecha if rfecha and str(rfecha).strip() else "Sin fecha"
                
                # Crear opción más descriptiva
                option = f"{rid} - {fecha_display} - {cliente_display} - {tarea_display}"
                registro_options.append(option)
            
            selected_registro_edit = st.selectbox("Seleccionar Registro para Editar", options=registro_options, key="select_registro_edit")
            if selected_registro_edit:
                registro_id = int(selected_registro_edit.split(' - ')[0])
                registro_seleccionado = combined_df[combined_df['id'] == registro_id].iloc[0]
                render_user_edit_record_form(registro_seleccionado, registro_id, nombre_completo_usuario)
        
        # Desplegable para eliminar registros
        with st.expander("🗑️ Eliminar Registro", expanded=False):
            st.subheader("Eliminar Registro Existente")
            
            selected_registro_delete = st.selectbox("Seleccionar Registro para Eliminar", options=registro_options, key="select_registro_delete")
            if selected_registro_delete:
                registro_id = int(selected_registro_delete.split(' - ')[0])
                registro_seleccionado = combined_df[combined_df['id'] == registro_id].iloc[0]
                def render_user_delete_record_form(registro_seleccionado, registro_id, nombre_completo_usuario):
                    """Renderiza el formulario de eliminación de registros para usuarios"""
                    st.warning("¿Estás seguro de que deseas eliminar este registro? Esta acción no se puede deshacer.")
                    if st.button("Eliminar Registro", key="delete_registro_btn"):
                        conn = get_connection()
                        c = conn.cursor()
                        
                        # Verificar si el usuario tiene permiso para eliminar este registro
                        if registro_seleccionado['tecnico'] == nombre_completo_usuario:
                            c.execute("DELETE FROM registros WHERE id = %s", (registro_id,))
                            conn.commit()
                            
                            # Registrar la actividad de eliminación
                            from .database import registrar_eliminacion
                            usuario_id = st.session_state.user_id
                            username = st.session_state.username
                            detalles = f"ID: {registro_id}, Cliente: {registro_seleccionado['cliente']}, Tarea: {registro_seleccionado['tarea_realizada']}"
                            registrar_eliminacion(usuario_id, username, "registro de horas", detalles)
                            
                            show_success_message("✅ Registro eliminado exitosamente. La entrada ha sido completamente removida del sistema.", 1.5)
                        else:
                            st.error("No tienes permiso para eliminar este registro.")
                        
                        conn.close()
                
                # Llamar a la función para mostrar el formulario de eliminación
                render_user_delete_record_form(registro_seleccionado, registro_id, nombre_completo_usuario)
        
        # Mostrar información sobre registros no asignados
        if not unassigned_registros_df.empty:
            st.info(f"ℹ️ Se encontraron {len(unassigned_registros_df)} registros no asignados que coinciden con tu nombre. Estos registros se incluyen en las opciones de edición/eliminación.")
    else:
        st.info("No hay registros para editar o eliminar.")

def save_new_user_record(user_id, fecha, tecnico, cliente, tipo, modalidad, tarea, ticket, tiempo, descripcion, mes, grupo="General"):
    """Guarda un nuevo registro de usuario con validación de duplicados"""
    try:
        conn = get_connection()
        c = conn.cursor()
        
        # Obtener IDs de las entidades
        c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = %s", (tecnico,))
        id_tecnico = c.fetchone()[0]
        
        c.execute("SELECT id_cliente FROM clientes WHERE nombre = %s", (cliente,))
        id_cliente = c.fetchone()[0]
        
        c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = %s", (tipo,))
        id_tipo = c.fetchone()[0]
        
        c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE descripcion = %s", (modalidad,))
        id_modalidad = c.fetchone()[0]
        
        # Usar la función centralizada para verificar duplicados
        from .database import check_record_duplicate
        if check_record_duplicate(fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, tiempo):
            st.error("Ya existe un registro con estos mismos datos. No se puede crear un duplicado.")
            return
        
        # NUEVO: Buscar el rol del técnico para asignar correctamente
        c.execute('''
            SELECT u.id, u.rol_id 
            FROM usuarios u 
            WHERE (u.nombre || ' ' || u.apellido) = %s
        ''', (tecnico,))
        
        tecnico_user = c.fetchone()
        
        # Si el técnico tiene un usuario y un rol asignado, usar ese usuario_id
        # De lo contrario, usar el usuario_id proporcionado (el que está creando el registro)
        registro_usuario_id = user_id
        if tecnico_user:
            registro_usuario_id = tecnico_user[0]
        
        # Verificar si existe la columna grupo y obtener su valor
        grupo = "General"  # Valor predeterminado
        usar_grupo_general = True
        
        if 'grupo' in row and pd.notna(row['grupo']) and str(row['grupo']).strip() != '':
            grupo_valor = str(row['grupo']).strip()
            # Verificar que no sea un valor vacío o inválido
            if grupo_valor not in ['', 'nan', 'NaN', 'None', 'null', 'N/A', 'n/a']:
                grupo = ' '.join(grupo_valor.split()).title()
                usar_grupo_general = False
        
        # NUEVO: Crear/obtener grupo con lógica diferente según si es "General" o específico
        if usar_grupo_general:
            # Para grupo "General", usar la función original
            from .database import get_or_create_grupo_with_department_association
            id_grupo = get_or_create_grupo_with_department_association(grupo, st.session_state.user_id, conn)
        else:
            # Para grupos específicos, usar la nueva función que asocia al departamento del técnico
            from .database import get_or_create_grupo_with_tecnico_department_association
            id_grupo = get_or_create_grupo_with_tecnico_department_association(grupo, nombre_completo_usuario, conn)
        
        # Insertar nuevo registro con el grupo (sector)
        c.execute('''
            INSERT INTO registros 
            (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
             numero_ticket, tiempo, descripcion, mes, usuario_id, grupo, id_grupo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, ticket, 
              tiempo, descripcion, mes, registro_usuario_id, grupo, id_grupo))
        
        conn.commit()
        show_success_message("✅ Registro creado exitosamente.", 1)
        
        # Limpiar el formulario reiniciando la página
        st.rerun()
        
    except Exception as e:
        st.error(f"Error al guardar el registro: {str(e)}")
    finally:
        conn.close()

def render_user_edit_record_form(registro_seleccionado, registro_id, nombre_completo_usuario):
    """Renderiza el formulario de edición de registros para usuarios"""
    # Formulario para editar el registro
    fecha_str = registro_seleccionado['fecha']
    try:
        fecha_obj = datetime.strptime(fecha_str, '%d/%m/%y')
    except ValueError:
        try:
            fecha_obj = datetime.strptime(fecha_str, '%d/%m/%Y')
        except ValueError:
            fecha_obj = datetime.today()
    
    fecha_edit = st.date_input("Fecha", value=fecha_obj, key="edit_fecha")
    fecha_formateada_edit = fecha_edit.strftime('%d/%m/%y')
    
    # Obtener listas de técnicos, clientes, tipos y modalidades
    tecnicos_df = get_tecnicos_dataframe()
    clientes_df = get_clientes_dataframe()
    tipos_df = get_tipos_dataframe()
    modalidades_df = get_modalidades_dataframe()
    
    # Obtener el rol del usuario para los grupos
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, rol_id FROM usuarios WHERE (nombre || ' ' || apellido) = %s", (nombre_completo_usuario,))
    user_data = c.fetchone()
    conn.close()
    
    user_id = user_data[0] if user_data else None
    rol_id = user_data[1] if user_data else None
    
    # Para usuarios normales, solo pueden editar sus propios registros
    tecnico_selected_edit = nombre_completo_usuario
    st.info(f"Técnico: {tecnico_selected_edit} (no se puede cambiar)")
    
    # Selección de grupo (sector)
    grupos = get_grupos_by_rol(rol_id) if rol_id else []
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
    grupo_selected_edit = st.selectbox("Sector:", options=grupo_names, index=grupo_index, key="edit_grupo")
    
    # Selección de cliente
    cliente_options = clientes_df['nombre'].tolist()
    cliente_index = cliente_options.index(registro_seleccionado['cliente']) if registro_seleccionado['cliente'] in cliente_options else 0
    cliente_selected_edit = st.selectbox("Cliente", options=cliente_options, index=cliente_index, key="edit_cliente")
    
    # Selección de tipo de tarea
    tipo_options = tipos_df['descripcion'].tolist()
    tipo_index = tipo_options.index(registro_seleccionado['tipo_tarea']) if registro_seleccionado['tipo_tarea'] in tipo_options else 0
    tipo_selected_edit = st.selectbox("Tipo de Tarea", options=tipo_options, index=tipo_index, key="edit_tipo")
    
    # Selección de modalidad
    modalidad_options = modalidades_df['descripcion'].tolist()
    modalidad_index = modalidad_options.index(registro_seleccionado['modalidad']) if registro_seleccionado['modalidad'] in modalidad_options else 0
    modalidad_selected_edit = st.selectbox("Modalidad", options=modalidad_options, index=modalidad_index, key="edit_modalidad")
    
    # Campos adicionales
    tarea_realizada_edit = st.text_input("Tarea Realizada", value=registro_seleccionado['tarea_realizada'], key="edit_tarea")
    numero_ticket_edit = st.text_input("Número de Ticket", value=registro_seleccionado['numero_ticket'], key="edit_ticket")
    tiempo_edit = st.number_input("Tiempo (horas)", min_value=0.5, step=0.5, value=float(registro_seleccionado['tiempo']), key="edit_tiempo")
    descripcion_edit = st.text_area("Descripción", value=registro_seleccionado['descripcion'] if pd.notna(registro_seleccionado['descripcion']) else "", key="edit_descripcion")
    
    # Mes (automático basado en la fecha)
    mes_edit = month_name_es(fecha_edit.month)
    
    if st.button("Guardar Cambios", key="save_registro_edit"):
        if not tarea_realizada_edit:
            st.error("La tarea realizada es obligatoria.")
        elif tiempo_edit < 0.5:
            st.error("El tiempo mínimo debe ser de 0.5 horas (30 minutos).")
        else:
            save_user_record_changes(
                registro_id, fecha_formateada_edit, tecnico_selected_edit,
                cliente_selected_edit, tipo_selected_edit, modalidad_selected_edit,
                tarea_realizada_edit, numero_ticket_edit, tiempo_edit, descripcion_edit, mes_edit,
                grupo_selected_edit
            )

def save_user_record_changes(registro_id, fecha, tecnico, cliente, tipo, modalidad, tarea, ticket, tiempo, descripcion, mes, grupo="General"):
    """Guarda los cambios en un registro de usuario"""
    conn = get_connection()
    c = conn.cursor()
    
    # Obtener IDs
    c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = %s", (tecnico,))
    id_tecnico = c.fetchone()[0]
    
    c.execute("SELECT id_cliente FROM clientes WHERE nombre = %s", (cliente,))
    id_cliente = c.fetchone()[0]
    
    c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = %s", (tipo,))
    id_tipo = c.fetchone()[0]
    
    # En la función de actualización de registros
    c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE descripcion = %s", (modalidad,))
    id_modalidad = c.fetchone()[0]
    
    # Verificar si ya existe un registro con los mismos datos
    c.execute('''
        SELECT COUNT(*) FROM registros 
        WHERE fecha = %s AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s 
        AND id_modalidad = %s AND tarea_realizada = %s AND tiempo = %s AND id != %s
    ''', (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, tiempo, registro_id))
    
    duplicate_count = c.fetchone()[0]
    if duplicate_count > 0:
        st.error("Ya existe un registro con estos mismos datos. No se puede crear un duplicado.")
    else:
        # Actualizar registro
        c.execute('''
            UPDATE registros SET 
            fecha = %s, id_tecnico = %s, id_cliente = %s, id_tipo = %s, id_modalidad = %s, 
            tarea_realizada = %s, numero_ticket = %s, tiempo = %s, descripcion = %s, mes = %s, grupo = %s
            WHERE id = %s
        ''', (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, ticket, tiempo, descripcion, mes, grupo, registro_id))
        
        conn.commit()
        
        # Registrar la actividad de edición
        from .database import registrar_edicion
        usuario_id = st.session_state.user_id
        username = st.session_state.username
        detalles = f"ID: {registro_id}, Cliente: {cliente}, Tarea: {tarea}, Tiempo: {tiempo}h"
        registrar_edicion(usuario_id, username, "registro de horas", detalles)
        
        show_success_message("✅ Registro actualizado exitosamente. Se ha verificado que no existen duplicados.", 1)
    
    conn.close()

def assign_unassigned_records_to_user(user_id):
    """Asigna automáticamente registros no asignados al usuario actual"""
    conn = get_connection()
    c = conn.cursor()
    
    # Obtener el nombre completo del usuario
    c.execute("SELECT nombre, apellido FROM usuarios WHERE id = %s", (user_id,))
    user_data = c.fetchone()
    
    if not user_data or not user_data[0] or not user_data[1]:
        conn.close()
        return 0
    
    nombre_completo = f"{user_data[0]} {user_data[1]}"
    
    # Asignar registros
    c.execute("""
        UPDATE registros SET usuario_id = %s 
        WHERE usuario_id IS NULL AND id_tecnico IN (
            SELECT id_tecnico FROM tecnicos WHERE nombre = %s
        )
    """, (user_id, nombre_completo))
    
    registros_asignados = c.rowcount
    conn.commit()
    conn.close()
    
    return registros_asignados

def render_weekly_modality_planner(user_id, nombre_completo_usuario):
    """Renderiza el planificador semanal de modalidades"""
    st.subheader("Planificación Semanal de Modalidad")
    
    # Obtener rol y modalidades disponibles
    rol_id = get_user_rol_id(user_id)
    modalidades_df = get_modalidades_dataframe()
    modalidad_options = modalidades_df[['id_modalidad', 'descripcion']].values.tolist()
    
    # Rango de semana actual - asegurar que sea consistente
    start_of_week, end_of_week = get_week_dates()
    
    # Convertir a objetos date de forma consistente
    start_date = start_of_week.date() if hasattr(start_of_week, 'date') else start_of_week
    end_date = end_of_week.date() if hasattr(end_of_week, 'date') else end_of_week
    
    st.caption(f"Semana: {format_week_range(start_of_week, end_of_week)}")
    
    # Construir lista de días laborables (Lunes-Viernes) como objetos date
    # Asegurar que el lunes sea el primer día
    week_dates = []
    current_date = start_date
    for i in range(5):  # Solo días laborables
        week_dates.append(current_date)
        current_date += timedelta(days=1)
    
    # Mapeo de días al español
    day_mapping = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
    }
    
    # Peers del mismo rol
    peers_df = get_users_by_rol(rol_id)
    
    # Modalidades actuales del usuario - usar objetos date consistentes
    user_sched_df = get_user_weekly_modalities(user_id, start_date, end_date)
    user_sched_map = {}
    for _, row in user_sched_df.iterrows():
        fecha_obj = pd.to_datetime(row['fecha']).date()
        user_sched_map[fecha_obj] = int(row['modalidad_id'])
    
    # Modalidades de todos en el rol para mostrar
    rol_sched_df = get_weekly_modalities_by_rol(rol_id, start_date, end_date)
    
    # Construir UI por día para el usuario actual
    st.markdown("Selecciona tu modalidad por día (solo modifica tus días):")
    cols = st.columns(5)
    selected_by_day = {}
    
    for i, day in enumerate(week_dates):
        # Preseleccionar modalidad guardada si existe
        default_mod_id = user_sched_map.get(day, None)
        options_ids = [int(mid) for mid, _ in modalidad_options]
        default_index = options_ids.index(default_mod_id) if (default_mod_id is not None and default_mod_id in options_ids) else 0
        
        with cols[i]:
            # Convertir día a español
            day_name_en = day.strftime("%A")
            day_name_es = day_mapping.get(day_name_en, day_name_en)
            st.write(f"{day_name_es}")
            st.caption(f"{day.strftime('%d/%m')}")
            
            mod_id = st.selectbox(
                "Modalidad",
                options=options_ids,
                format_func=lambda x: modalidades_df.loc[modalidades_df['id_modalidad'] == x, 'descripcion'].iloc[0],
                index=default_index,
                key=f"user_mod_{day.isoformat()}",
                label_visibility="collapsed"
            )
            selected_by_day[day] = mod_id
    
    if st.button("Guardar Planificación Semanal", type="primary"):
        try:
            # Guardar cada día individualmente con manejo de errores específico
            errores = []
            for day, mod_id in selected_by_day.items():
                try:
                    upsert_user_modality_for_date(user_id, rol_id, day, mod_id)
                except Exception as day_error:
                    error_msg = f"Error guardando {day}: {str(day_error)}"
                    errores.append(error_msg)
                    st.error(error_msg)
            
            if not errores:
                st.success("Planificación guardada correctamente.")
                st.rerun()  # Refrescar la interfaz para mostrar los cambios
            else:
                st.error(f"Se encontraron {len(errores)} errores al guardar.")
                
        except Exception as e:
            st.error(f"Error general al guardar: {str(e)}")
    
    st.divider()
    st.markdown("Vista del equipo (solo lectura, mismo departamento):")
    
    # Construir matriz similar a tu captura: filas=usuarios, columnas=días
    # No editable para otros usuarios
    matriz = []
    peer_names = {int(row['id']): row['nombre_completo'] for _, row in peers_df.iterrows()}
    
    # Inicializar mapa de (user_id, fecha) -> modalidad
    rol_map = {}
    for _, row in rol_sched_df.iterrows():
        fecha_obj = pd.to_datetime(row['fecha']).date()
        rol_map[(int(row['user_id']), fecha_obj)] = row['modalidad']
    
    # Construir filas de la matriz (solo mostrar usuarios con al menos un día asignado)
    matriz = []
    for _, peer in peers_df.iterrows():
        peer_id = int(peer['id'])
        peer_name = peer['nombre_completo']
        fila = [peer_name]
    
        asignadas_count = 0
        # Agregar modalidad para cada día de la semana
        for day in week_dates:
            modalidad = rol_map.get((peer_id, day), "Sin asignar")
            fila.append(modalidad)
            if modalidad != "Sin asignar":
                asignadas_count += 1
    
        # Ocultar usuarios con todos los días "Sin asignar"
        if asignadas_count > 0:
            matriz.append(fila)
    
    # Crear DataFrame para mostrar (solo si hay filas)
    if matriz:
        columnas = ['Usuario']
        for day in week_dates:
            day_name = day_mapping.get(day.strftime('%A'), day.strftime('%A'))
            columnas.append(f"{day_name}\n{day.strftime('%d/%m')}")
        df_matriz = pd.DataFrame(matriz, columns=columnas)
        
        # Función para aplicar colores de fondo según la modalidad
        def colorear_modalidad(val):
            if val == "Presencial":
                return 'background-color: #28a745; color: white; font-weight: bold; border: 1px solid #000; padding: 5px'  # Verde intenso con borde negro
            elif val == "Remoto":
                return 'background-color: #007bff; color: white; font-weight: bold; border: 1px solid #000; padding: 5px'  # Azul intenso con borde negro
            elif val == "Sin asignar":
                return 'border: 1px solid #000; padding: 5px'  # Solo borde, sin cambio de color
            else:
                # Para otras modalidades futuras, usar un color distintivo
                return 'background-color: #6c757d; color: white; font-weight: bold; border: 1px solid #000; padding: 5px'  # Gris intenso con borde negro
        
        # Aplicar estilos solo a las columnas de días (no a la columna Usuario)
        styled_df = df_matriz.style.applymap(
            colorear_modalidad, 
            subset=[col for col in df_matriz.columns if col != 'Usuario']
        )
        
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
    else:
        st.info("No hay otros usuarios en tu mismo departamento.")
