import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import calendar
import time
from .database import (
    get_connection, get_user_registros_dataframe,
    get_tecnicos_dataframe, get_clientes_dataframe, 
    get_tipos_dataframe, get_modalidades_dataframe,
    get_unassigned_records_for_user, get_user_rol_id
)
from .utils import get_week_dates, format_week_range, prepare_weekly_chart_data, show_success_message

def render_user_dashboard(user_id, nombre_completo_usuario):
    """Renderiza el dashboard completo del usuario con pestañas"""
    # Crear pestañas principales (eliminar la pestaña de diagnóstico)
    tab1, tab2 = st.tabs(["📝 Mis Registros", "📊 Registro de Horas"])
    
    with tab1:
        render_records_management(user_id, nombre_completo_usuario)
    
    with tab2:
        render_hours_overview(user_id, nombre_completo_usuario)
    
    # ELIMINAR COMPLETAMENTE estas líneas:
    # with tab3:
    #     # Agregar aquí la función de diagnóstico
    #     from .admin_panel import diagnosticar_registros_usuario
    #     diagnosticar_registros_usuario()

def render_hours_overview(user_id, nombre_completo_usuario):
    """Renderiza la vista general de horas (gráficos y estadísticas)"""
    st.header("Mis Registros de Horas")
    
    # Obtener registros del usuario
    user_registros_df = get_user_registros_dataframe(user_id)
    
    if not user_registros_df.empty:
        # Mejorar la conversión de fecha a datetime
        def convert_fecha_to_datetime(fecha_str):
            """Convierte fecha string a datetime con múltiples formatos"""
            try:
                # Intentar formato dd/mm/yy
                return pd.to_datetime(fecha_str, format='%d/%m/%y')
            except:
                try:
                    # Intentar formato dd/mm/yyyy
                    return pd.to_datetime(fecha_str, format='%d/%m/%Y')
                except:
                    try:
                        # Intentar conversión automática
                        return pd.to_datetime(fecha_str, dayfirst=True)
                    except:
                        # Si todo falla, retornar None
                        return pd.NaT
        
        # Aplicar la conversión mejorada
        user_registros_df['fecha_dt'] = user_registros_df['fecha'].apply(convert_fecha_to_datetime)
        
        # Filtrar registros con fechas válidas
        registros_validos = user_registros_df.dropna(subset=['fecha_dt'])
        registros_invalidos = len(user_registros_df) - len(registros_validos)
        
        if registros_invalidos > 0:
            st.warning(f"⚠️ {registros_invalidos} registros tienen fechas inválidas y no se mostrarán en el gráfico.")
        
        # Calcular total de horas registradas (solo registros válidos)
        total_horas = registros_validos['tiempo'].sum()
        st.metric("Total de Horas Registradas", f"{total_horas:.1f}")
        
        # Renderizar gráfico semanal con registros válidos
        if not registros_validos.empty:
            render_weekly_chart(registros_validos)
        else:
            st.error("No hay registros con fechas válidas para mostrar en el gráfico.")
        
        # Mostrar tabla de registros detallada (todos los registros)
        st.subheader("Detalle de Registros")
        
        # Mostrar registros sin la columna fecha_dt
        display_df = user_registros_df.drop(columns=['fecha_dt'])
        st.dataframe(display_df, use_container_width=True)
        
        # AGREGAR: Formularios de editar y eliminar debajo del detalle
        render_edit_delete_expanders(user_id, nombre_completo_usuario)
        
    else:
        st.info("No tienes registros de horas todavía.")

def render_records_management(user_id, nombre_completo_usuario):
    """Renderiza la gestión de registros (solo agregar)"""
    st.header("Gestión de Registros")
    
    # Formulario para agregar nuevo registro
    render_add_record_form(user_id, nombre_completo_usuario)
    
    # ELIMINAR esta línea:
    # render_edit_delete_expanders(user_id, nombre_completo_usuario)

def render_add_record_form(user_id, nombre_completo_usuario):
    """Renderiza el formulario para agregar nuevos registros"""
    st.subheader("Nuevo Registro de Horas")
    
    # Obtener el rol del usuario
    rol_id = get_user_rol_id(user_id)
    
    # Obtener listas de opciones
    clientes_df = get_clientes_dataframe()
    tipos_df = get_tipos_dataframe(rol_id=rol_id)  # Filtrar por rol
    modalidades_df = get_modalidades_dataframe()
    
    if clientes_df.empty or tipos_df.empty or modalidades_df.empty:
        st.warning("No hay datos suficientes para crear registros. Contacta al administrador para que configure clientes, tipos de tarea y modalidades.")
        return
    
    # Formulario para nuevo registro
    col1, col2 = st.columns(2)
    
    with col1:
        fecha_nuevo = st.date_input("Fecha", value=datetime.today(), key="new_fecha")
        fecha_formateada_nuevo = fecha_nuevo.strftime('%d/%m/%y')
        
        # El técnico es automáticamente el usuario logueado
        st.info(f"Técnico: {nombre_completo_usuario}")
        
        cliente_options = clientes_df['nombre'].tolist()
        cliente_selected_nuevo = st.selectbox("Cliente", options=cliente_options, key="new_cliente")
        
        tipo_options = tipos_df['descripcion'].tolist()
        tipo_selected_nuevo = st.selectbox("Tipo de Tarea", options=tipo_options, key="new_tipo")
    
    with col2:
        modalidad_options = modalidades_df['modalidad'].tolist()
        modalidad_selected_nuevo = st.selectbox("Modalidad", options=modalidad_options, key="new_modalidad")
        
        tarea_realizada_nuevo = st.text_input("Tarea Realizada", key="new_tarea")
        numero_ticket_nuevo = st.text_input("Número de Ticket", key="new_ticket")
        tiempo_nuevo = st.number_input("Tiempo (horas)", min_value=0.0, step=0.5, key="new_tiempo")
    
    descripcion_nuevo = st.text_area("Descripción (opcional)", key="new_descripcion")
    
    # Mes automático basado en la fecha
    mes_nuevo = calendar.month_name[fecha_nuevo.month]
    
    if st.button("💾 Guardar Registro", key="save_new_registro", type="primary"):
        if not tarea_realizada_nuevo:
            st.error("La tarea realizada es obligatoria.")
        elif tiempo_nuevo <= 0:
            st.error("El tiempo debe ser mayor que cero.")
        else:
            save_new_user_record(
                user_id, fecha_formateada_nuevo, nombre_completo_usuario,
                cliente_selected_nuevo, tipo_selected_nuevo, modalidad_selected_nuevo,
                tarea_realizada_nuevo, numero_ticket_nuevo, tiempo_nuevo, 
                descripcion_nuevo, mes_nuevo
            )

def render_edit_delete_expanders(user_id, nombre_completo_usuario):
    """Renderiza los desplegables para editar y eliminar registros"""
    # Obtener registros del usuario
    user_registros_df = get_user_registros_dataframe(user_id)
    
    # NUEVO: Obtener registros no asignados que podrían pertenecer al usuario
    unassigned_registros_df = get_unassigned_records_for_user(user_id)
    
    # Combinar ambos DataFrames
    if not unassigned_registros_df.empty:
        combined_df = pd.concat([user_registros_df, unassigned_registros_df], ignore_index=True)
        combined_df = combined_df.sort_values('fecha', ascending=False)
    else:
        combined_df = user_registros_df
    
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
                render_user_delete_record_form(registro_seleccionado, registro_id, nombre_completo_usuario)
                
        # Mostrar información sobre registros no asignados
        if not unassigned_registros_df.empty:
            st.info(f"ℹ️ Se encontraron {len(unassigned_registros_df)} registros no asignados que coinciden con tu nombre. Estos registros se incluyen en las opciones de edición/eliminación.")
    else:
        st.info("No hay registros para editar o eliminar.")

def save_new_user_record(user_id, fecha, tecnico, cliente, tipo, modalidad, tarea, ticket, tiempo, descripcion, mes):
    """Guarda un nuevo registro de usuario"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Obtener IDs
        c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (tecnico,))
        tecnico_result = c.fetchone()
        if not tecnico_result:
            st.error(f"No se encontró el técnico: {tecnico}")
            return
        id_tecnico = tecnico_result[0]
        
        c.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (cliente,))
        cliente_result = c.fetchone()
        if not cliente_result:
            st.error(f"No se encontró el cliente: {cliente}")
            return
        id_cliente = cliente_result[0]
        
        c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (tipo,))
        tipo_result = c.fetchone()
        if not tipo_result:
            st.error(f"No se encontró el tipo de tarea: {tipo}")
            return
        id_tipo = tipo_result[0]
        
        c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (modalidad,))
        modalidad_result = c.fetchone()
        if not modalidad_result:
            st.error(f"No se encontró la modalidad: {modalidad}")
            return
        id_modalidad = modalidad_result[0]
        
        # Verificar si ya existe un registro con los mismos datos
        c.execute('''
            SELECT COUNT(*) FROM registros 
            WHERE fecha = ? AND id_tecnico = ? AND id_cliente = ? AND id_tipo = ? 
            AND id_modalidad = ? AND tarea_realizada = ? AND tiempo = ?
        ''', (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, tiempo))
        
        duplicate_count = c.fetchone()[0]
        if duplicate_count > 0:
            st.error("Ya existe un registro con estos mismos datos. No se puede crear un duplicado.")
        else:
            # Insertar nuevo registro
            c.execute('''
                INSERT INTO registros 
                (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
                 numero_ticket, tiempo, descripcion, mes, usuario_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, ticket, 
                  tiempo, descripcion, mes, user_id))
            
            conn.commit()
            show_success_message("✅ Registro creado exitosamente.", 1)
            
            # Limpiar el formulario reiniciando la página
            st.rerun()
            
    except Exception as e:
        st.error(f"Error al guardar el registro: {str(e)}")
    finally:
        conn.close()

def render_weekly_chart(user_registros_df):
    """Renderiza el gráfico semanal de horas trabajadas"""
    st.subheader("Horas Trabajadas por Día de la Semana")
    
    # Inicializar week_offset si no existe
    if 'week_offset' not in st.session_state:
        st.session_state.week_offset = 0
    
    # Inicializar show_calendar si no existe
    if 'show_calendar' not in st.session_state:
        st.session_state.show_calendar = False
    
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
        if st.button("⬅️ Ant.", use_container_width=True):
            st.session_state.week_offset -= 1
            st.rerun()
    
    with nav_cols[3]:
        st.markdown(f"<p style='text-align: center; font-weight: bold; margin: 0; padding: 8px;'>{week_range_str}</p>", unsafe_allow_html=True)
    
    with nav_cols[4]:
        disable_next = st.session_state.week_offset == 0
        if st.button("Sig. ➡️", disabled=disable_next, use_container_width=True):
            st.session_state.week_offset += 1
            st.rerun()
    
    with nav_cols[5]:
        st.write("")  # Espacio vacío
    
    # Filtrar los registros para la semana seleccionada
    weekly_df = user_registros_df[
        (user_registros_df['fecha_dt'].dt.date >= start_of_selected_week.date()) &
        (user_registros_df['fecha_dt'].dt.date <= end_of_selected_week.date())
    ]
    
    if not weekly_df.empty:
        # Preparar datos para el gráfico
        horas_por_dia_final = prepare_weekly_chart_data(weekly_df, start_of_selected_week)
        
        fig = px.bar(horas_por_dia_final, x='dia_con_fecha', y='tiempo', 
                   labels={'dia_con_fecha': 'Día de la Semana', 'tiempo': 'Horas Totales'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No hay registros para la semana seleccionada.")

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
    
    # Para usuarios normales, solo pueden editar sus propios registros
    tecnico_selected_edit = nombre_completo_usuario
    st.info(f"Técnico: {tecnico_selected_edit} (no se puede cambiar)")
    
    # Selección de cliente
    cliente_options = clientes_df['nombre'].tolist()
    cliente_index = cliente_options.index(registro_seleccionado['cliente']) if registro_seleccionado['cliente'] in cliente_options else 0
    cliente_selected_edit = st.selectbox("Cliente", options=cliente_options, index=cliente_index, key="edit_cliente")
    
    # Selección de tipo de tarea
    tipo_options = tipos_df['descripcion'].tolist()
    tipo_index = tipo_options.index(registro_seleccionado['tipo_tarea']) if registro_seleccionado['tipo_tarea'] in tipo_options else 0
    tipo_selected_edit = st.selectbox("Tipo de Tarea", options=tipo_options, index=tipo_index, key="edit_tipo")
    
    # Selección de modalidad
    modalidad_options = modalidades_df['modalidad'].tolist()
    modalidad_index = modalidad_options.index(registro_seleccionado['modalidad']) if registro_seleccionado['modalidad'] in modalidad_options else 0
    modalidad_selected_edit = st.selectbox("Modalidad", options=modalidad_options, index=modalidad_index, key="edit_modalidad")
    
    # Campos adicionales
    tarea_realizada_edit = st.text_input("Tarea Realizada", value=registro_seleccionado['tarea_realizada'], key="edit_tarea")
    numero_ticket_edit = st.text_input("Número de Ticket", value=registro_seleccionado['numero_ticket'], key="edit_ticket")
    tiempo_edit = st.number_input("Tiempo (horas)", min_value=0.0, step=0.5, value=float(registro_seleccionado['tiempo']), key="edit_tiempo")
    descripcion_edit = st.text_area("Descripción", value=registro_seleccionado['descripcion'] if pd.notna(registro_seleccionado['descripcion']) else "", key="edit_descripcion")
    
    # Mes (automático basado en la fecha)
    mes_edit = calendar.month_name[fecha_edit.month]
    
    if st.button("Guardar Cambios", key="save_registro_edit"):
        if not tarea_realizada_edit:
            st.error("La tarea realizada es obligatoria.")
        elif tiempo_edit <= 0:
            st.error("El tiempo debe ser mayor que cero.")
        else:
            save_user_record_changes(
                registro_id, fecha_formateada_edit, tecnico_selected_edit,
                cliente_selected_edit, tipo_selected_edit, modalidad_selected_edit,
                tarea_realizada_edit, numero_ticket_edit, tiempo_edit, descripcion_edit, mes_edit
            )

def save_user_record_changes(registro_id, fecha, tecnico, cliente, tipo, modalidad, tarea, ticket, tiempo, descripcion, mes):
    """Guarda los cambios en un registro de usuario"""
    conn = get_connection()
    c = conn.cursor()
    
    # Obtener IDs
    c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (tecnico,))
    id_tecnico = c.fetchone()[0]
    
    c.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (cliente,))
    id_cliente = c.fetchone()[0]
    
    c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (tipo,))
    id_tipo = c.fetchone()[0]
    
    c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (modalidad,))
    id_modalidad = c.fetchone()[0]
    
    # Verificar si ya existe un registro con los mismos datos
    c.execute('''
        SELECT COUNT(*) FROM registros 
        WHERE fecha = ? AND id_tecnico = ? AND id_cliente = ? AND id_tipo = ? 
        AND id_modalidad = ? AND tarea_realizada = ? AND tiempo = ? AND id != ?
    ''', (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, tiempo, registro_id))
    
    duplicate_count = c.fetchone()[0]
    if duplicate_count > 0:
        st.error("Ya existe un registro con estos mismos datos. No se puede crear un duplicado.")
    else:
        # Actualizar registro
        c.execute('''
            UPDATE registros SET 
            fecha = ?, id_tecnico = ?, id_cliente = ?, id_tipo = ?, id_modalidad = ?, 
            tarea_realizada = ?, numero_ticket = ?, tiempo = ?, descripcion = ?, mes = ?
            WHERE id = ?
        ''', (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, ticket, tiempo, descripcion, mes, registro_id))
        
        conn.commit()
        show_success_message("✅ Registro actualizado exitosamente. Se ha verificado que no existen duplicados.", 1)
    
    conn.close()

def render_user_delete_record_form(registro_seleccionado, registro_id, nombre_completo_usuario):
    """Renderiza el formulario de eliminación de registros para usuarios"""
    st.warning("¿Estás seguro de que deseas eliminar este registro? Esta acción no se puede deshacer.")
    if st.button("Eliminar Registro", key="delete_registro_btn"):
        conn = get_connection()
        c = conn.cursor()
        
        # Verificar si el usuario tiene permiso para eliminar este registro
        if registro_seleccionado['tecnico'] == nombre_completo_usuario:
            c.execute("DELETE FROM registros WHERE id = ?", (registro_id,))
            conn.commit()
            show_success_message("✅ Registro eliminado exitosamente. La entrada ha sido completamente removida del sistema.", 1.5)
        else:
            st.error("No tienes permiso para eliminar este registro.")
        
        conn.close()

def assign_unassigned_records_to_user(user_id):
    """Asigna automáticamente registros no asignados al usuario actual"""
    conn = get_connection()
    c = conn.cursor()
    
    # Obtener el nombre completo del usuario
    c.execute("SELECT nombre, apellido FROM usuarios WHERE id = ?", (user_id,))
    user_data = c.fetchone()
    
    if not user_data or not user_data[0] or not user_data[1]:
        conn.close()
        return 0
    
    nombre_completo = f"{user_data[0]} {user_data[1]}"
    
    # Asignar registros
    c.execute("""
        UPDATE registros SET usuario_id = ? 
        WHERE usuario_id IS NULL AND id_tecnico IN (
            SELECT id_tecnico FROM tecnicos WHERE nombre = ?
        )
    """, (user_id, nombre_completo))
    
    registros_asignados = c.rowcount
    conn.commit()
    conn.close()
    
    return registros_asignados
