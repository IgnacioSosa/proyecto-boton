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
    upsert_user_modality_for_date,
    get_vacaciones_activas, get_user_vacaciones, save_vacaciones, delete_vacaciones, update_vacaciones,
    get_upcoming_vacaciones,
    is_feriado
)
from .utils import get_week_dates, format_week_range, prepare_weekly_chart_data, show_success_message, month_name_es
from .admin_planning import cached_get_weekly_modalities_by_rol
from .ui_components import inject_project_card_css

def render_user_dashboard(user_id, nombre_completo_usuario):
    """Renderiza el dashboard principal del usuario"""
    # Guard: usuario sin rol asignado
    from .config import SYSTEM_ROLES
    try:
        rol_id = get_user_rol_id(user_id)
        # Se permite el acceso incluso si rol_id es None o "Sin Rol"
        # para que se muestre el dashboard técnico por defecto
    except Exception:
        pass

    # Determinar si es usuario comercial: mostrar solo Proyectos
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT nombre FROM roles WHERE id_rol = %s", (rol_id,))
        row = c.fetchone()
        conn.close()
        rol_nombre = row[0] if row else None
    except:
        rol_nombre = None

    rol_lower = (rol_nombre or "").strip().lower()
    is_commercial = rol_lower in {"dpto comercial", "comercial"}
    if is_commercial:
        from .commercial_projects import render_commercial_projects
        render_commercial_projects(user_id, nombre_completo_usuario)
        return
    
    # --- Logic for Notification System (Technical User) ---
    alerts = []
    try:
        # 1. Get cached registers
        df_regs = get_user_registros_dataframe_cached(user_id)
        
        # 2. Ensure date column is datetime
        if not df_regs.empty:
            # Check if 'fecha' is already datetime (from process_registros_df)
            is_datetime = pd.api.types.is_datetime64_any_dtype(df_regs['fecha'])
            
            if is_datetime:
                df_regs['fecha_dt'] = df_regs['fecha']
            elif 'fecha_dt' not in df_regs.columns:
                def _parse_date(x):
                    try: return pd.to_datetime(x, format='%d/%m/%y')
                    except:
                        try: return pd.to_datetime(x, format='%d/%m/%Y')
                        except: return pd.to_datetime(x, dayfirst=True, errors='coerce')
                df_regs['fecha_dt'] = df_regs['fecha'].apply(_parse_date)
        
        # 3. Define range: Start of current month to Today
        now = datetime.now()
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=23, minute=59, second=59)
        
        # 4. Iterate and check
        current = start_date
        while current <= end_date:
            # Skip weekends (5=Sat, 6=Sun)
            if current.weekday() < 5:
                if is_feriado(current.date()):
                    current += timedelta(days=1)
                    continue
                day_hours = 0
                if not df_regs.empty:
                    # Filter for this day
                    mask = (df_regs['fecha_dt'].dt.date == current.date())
                    day_hours = df_regs.loc[mask, 'tiempo'].sum()
                
                if day_hours < 4:
                    date_str = current.strftime("%d/%m")
                    status = "Sin carga" if day_hours == 0 else f"{day_hours}hs"
                    alerts.append(f"{date_str} ({status})")
            
            current += timedelta(days=1)
            
    except Exception as e:
        # Fail silently to not crash dashboard
        # print(f"Error checking alerts: {e}") 
        pass

    has_alerts = len(alerts) > 0

    # --- Header with Notifications ---
    col_head, col_icon = st.columns([0.88, 0.12])
    with col_head:
        st.header(f"Dashboard - {nombre_completo_usuario}")
        
    with col_icon:
        st.write("")
        try:
            wrapper_class = "has-alerts" if has_alerts else "no-alerts"
            st.markdown(f"<div class='notif-trigger {wrapper_class}'>", unsafe_allow_html=True)
            icon_str = "🔔"
            with st.popover(icon_str, use_container_width=False):
                st.markdown("### ⚠️ Días con carga incompleta")
                st.caption("Umbral mínimo: 4 horas (lun-vie) - Mes en curso")
                if not has_alerts:
                    st.info("Todo al día. ¡Buen trabajo!")
                else:
                    for alert in alerts:
                        st.markdown(f"- **{alert}**")
            st.markdown("</div>", unsafe_allow_html=True)
        except Exception:
             if st.button("🔔"):
                 st.info(f"Alertas: {len(alerts)}")

    # --- Toast Notifications (Once per session) ---
    if not st.session_state.get('alerts_shown_tech', False):
        if has_alerts:
            count = len(alerts)
            msg = f"Tienes {count} días con carga incompleta este mes."
            st.toast(msg, icon="⚠️")
        st.session_state.alerts_shown_tech = True
    
    options = ["📝 Nuevo Registro", "📊 Mis Registros", "🏢 Planificación Semanal", "🌴 Licencias"]
    UTAB_MAPPING = {
        "registro": options[0],
        "resumen": options[1],
        "planificacion": options[2],
        "licencias": options[3],
    }
    params = st.query_params
    initial = None
    utab = params.get("utab")
    if utab:
        val = utab[0] if isinstance(utab, list) else utab
        if val in UTAB_MAPPING:
            initial = UTAB_MAPPING[val]
        elif val in options:
            initial = val
    if not initial:
        initial = options[0]
    if "user_main_tab" not in st.session_state:
        st.session_state["user_main_tab"] = initial
    if st.session_state["user_main_tab"] not in options:
        st.session_state["user_main_tab"] = options[0]
    choice = st.segmented_control(
        "Secciones",
        options,
        key="user_main_tab",
        label_visibility="collapsed",
    )
    rev_map = {v: k for k, v in UTAB_MAPPING.items()}
    current_val_param = utab[0] if isinstance(utab, list) else utab if utab else None
    target_param = rev_map.get(choice, choice)
    if current_val_param != target_param:
        try:
            st.query_params["utab"] = target_param
        except Exception:
            pass
    if choice == options[0]:
        render_records_management(user_id, nombre_completo_usuario)
    elif choice == options[1]:
        render_hours_overview(user_id, nombre_completo_usuario)
    elif choice == options[2]:
        render_weekly_modality_planner(user_id, nombre_completo_usuario)
    elif choice == options[3]:
        render_vacaciones_tab(user_id, nombre_completo_usuario)

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
    
    # Crear una copia para manipulación visual sin afectar el caché
    display_df = user_registros_df.copy()
    
    if 'fecha_dt' in display_df.columns:
        # Ordenar por fecha real (datetime)
        display_df = display_df.sort_values(by='fecha_dt', ascending=False)
        # Reemplazar columna de texto con objeto datetime para ordenamiento correcto en UI
        display_df['fecha'] = display_df['fecha_dt']
        # Eliminar columna auxiliar
        display_df = display_df.drop(columns=['fecha_dt'])
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "fecha": st.column_config.DateColumn(
                "Fecha",
                format="DD/MM/YYYY",
            ),
        }
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
            "Fecha",
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
        
        # Ajuste de color de texto para adaptarse al tema (claro/oscuro) usando variables CSS
        fig.update_layout(
            font=dict(color="var(--text-color)"),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        
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
    
    # Solo mostrar clientes activos para nuevos registros
    clientes_df = get_clientes_dataframe(only_active=True)
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
    
    # Inicializar sufijo para claves dinámicas si no existe
    if "form_key_suffix" not in st.session_state:
        st.session_state.form_key_suffix = 0
    
    suffix = st.session_state.form_key_suffix
    
    grupo_selected = st.selectbox("Sector:", options=grupo_names, index=0, key="new_grupo")
    
    col1, col2 = st.columns(2)
    
    with col1:
        fecha_nuevo = st.date_input("Fecha", value=datetime.today(), key="new_fecha")
        fecha_formateada_nuevo = fecha_nuevo.strftime('%d/%m/%y')
        
        cliente_options = clientes_df['nombre'].tolist()
        cliente_selected_nuevo = st.selectbox("Cliente", options=cliente_options, key="new_cliente")
        
        tipo_options = tipos_df['descripcion'].tolist()
        tipo_selected_nuevo = st.selectbox("Tipo de Tarea", options=tipo_options, key="new_tipo")
        
        # Checkbox de Hora Extra
        es_hora_extra_nuevo = st.checkbox("Hora extra", key=f"new_hora_extra_{suffix}")
    
    with col2:
        modalidad_options = modalidades_df['descripcion'].tolist()
        # Asegurar que Cliente esté disponible
        if 'Cliente' not in modalidad_options:
            modalidad_options.append('Cliente')
        modalidad_selected_nuevo = st.selectbox("Modalidad", options=modalidad_options, key="new_modalidad")
        
        tarea_realizada_nuevo = st.text_input("Tarea Realizada", key=f"new_tarea_{suffix}", max_chars=100)
        numero_ticket_nuevo = st.text_input("Número de Ticket", key=f"new_ticket_{suffix}", max_chars=20)
        tiempo_nuevo = st.number_input("Tiempo (horas)", min_value=0.5, step=0.5, key=f"new_tiempo_{suffix}")
    
    descripcion_nuevo = st.text_area("Descripción (opcional)", key=f"new_descripcion_{suffix}", max_chars=250)
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
                descripcion_nuevo, mes_nuevo, grupo_selected,
                es_hora_extra=es_hora_extra_nuevo
            )

def render_edit_delete_expanders(user_id, nombre_completo_usuario):
    """Renderiza los desplegables para editar y eliminar registros"""
    user_registros_df = get_user_registros_dataframe(user_id)
    unassigned_registros_df = get_unassigned_records_for_user(user_id)
    
    def convert_fecha_to_datetime(fecha_val):
        """Convierte fecha a datetime de forma segura"""
        if pd.isna(fecha_val): return pd.NaT
        if hasattr(fecha_val, 'date'): return fecha_val
        try:
            return pd.to_datetime(fecha_val, format='%d/%m/%y')
        except:
            try:
                return pd.to_datetime(fecha_val, format='%d/%m/%Y')
            except:
                try:
                    return pd.to_datetime(fecha_val, dayfirst=True)
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
                
                # Formatear fecha para mostrar
                if hasattr(rfecha, 'strftime'):
                    fecha_display = rfecha.strftime('%d/%m/%y')
                else:
                    fecha_display = rfecha if rfecha and str(rfecha).strip() else "Sin fecha"
                
                # Crear opción más descriptiva
                option = f"{rid} - {fecha_display} - {cliente_display} - {tarea_display}"
                registro_options.append(option)
            
            selected_registro_edit = st.selectbox("Seleccionar Registro para Editar", options=registro_options, key="select_registro_edit")
            if selected_registro_edit:
                registro_id = int(selected_registro_edit.split(' - ')[0])
                registro_seleccionado = combined_df[combined_df['id'] == registro_id].iloc[0]
                render_user_edit_record_form(registro_seleccionado, registro_id, nombre_completo_usuario)
        
        # Desplegable para eliminación 1x1
        with st.expander("🗑️ Eliminar Registro (Individual)", expanded=False):
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
                            
                            # Limpiar caché
                            try:
                                clear_user_registros_cache(st.session_state.user_id)
                            except:
                                pass
                            
                            show_success_message("✅ Registro eliminado exitosamente. La entrada ha sido completamente removida del sistema.", 1.5)
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("No tienes permiso para eliminar este registro.")
                        
                        conn.close()
                
                # Llamar a la función para mostrar el formulario de eliminación
                render_user_delete_record_form(registro_seleccionado, registro_id, nombre_completo_usuario)
        
        # Desplegable para eliminación MASIVA
        with st.expander("🔥 Eliminar Múltiples Registros", expanded=False):
            st.subheader("Selección Múltiple")
            st.warning("⚠️ Cuidado: Esta acción eliminará permanentemente TODOS los registros seleccionados.")
            
            selected_registros_batch = st.multiselect(
                "Selecciona los registros a eliminar:",
                options=registro_options,
                key="select_registro_batch_delete"
            )
            
            if selected_registros_batch:
                count = len(selected_registros_batch)
                if st.button(f"🗑️ Eliminar {count} Registros Seleccionados", type="primary", key="btn_batch_delete"):
                    # Extraer IDs
                    ids_to_delete = [int(opt.split(' - ')[0]) for opt in selected_registros_batch]
                    
                    # Validar permisos (solo registros propios)
                    # Aunque la lista ya viene filtrada por usuario en combined_df, es bueno doble chequear si fuera necesario.
                    # Aquí confiamos en combined_df que viene de get_user_registros_dataframe(user_id)
                    
                    from .database import delete_registros_batch, registrar_eliminacion
                    
                    deleted_count = delete_registros_batch(ids_to_delete)
                    
                    if deleted_count >= 0:
                        # Registrar auditoría (resumida)
                        usuario_id = st.session_state.user_id
                        username = st.session_state.username
                        detalles = f"Eliminación masiva de {deleted_count} registros. IDs: {ids_to_delete}"
                        registrar_eliminacion(usuario_id, username, "eliminación masiva", detalles)
                        
                        # Limpiar caché
                        try:
                            clear_user_registros_cache(st.session_state.user_id)
                        except:
                            pass
                        
                        show_success_message(f"✅ Se han eliminado {deleted_count} registros exitosamente.", 2)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Hubo un error al intentar eliminar los registros.")

        # Mostrar información sobre registros no asignados
        if not unassigned_registros_df.empty:
            st.info(f"ℹ️ Se encontraron {len(unassigned_registros_df)} registros no asignados que coinciden con tu nombre. Estos registros se incluyen en las opciones de edición/eliminación.")
    else:
        st.info("No hay registros para editar o eliminar.")

def save_new_user_record(user_id, fecha, tecnico, cliente, tipo, modalidad, tarea, ticket, tiempo, descripcion, mes, grupo="General", es_hora_extra=False):
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
        # Normalizar tiempo a 2 decimales para consistencia y chequeo de duplicados
        try:
            tiempo = round(float(tiempo), 2)
        except Exception:
            tiempo = 0.0
        # Verificar duplicado con tiempo normalizado
        if check_record_duplicate(fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, tiempo):
            st.warning("Ya existe un registro con los mismos datos y tiempo.")
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
        # Corregido: Usar el argumento grupo directamente
        usar_grupo_general = (grupo == "General")
        
        # NUEVO: Crear/obtener grupo con lógica diferente según si es "General" o específico
        if usar_grupo_general:
            # Para grupo "General", usar la función original
            from .database import get_or_create_grupo_with_department_association
            id_grupo = get_or_create_grupo_with_department_association(grupo, st.session_state.user_id, conn)
        else:
            # Para grupos específicos, usar la nueva función que asocia al departamento del técnico
            from .database import get_or_create_grupo_with_tecnico_department_association
            id_grupo = get_or_create_grupo_with_tecnico_department_association(grupo, tecnico, conn)
        
        # Insertar nuevo registro con el grupo (sector)
        c.execute('''
            INSERT INTO registros 
            (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
             numero_ticket, tiempo, descripcion, mes, usuario_id, grupo, es_hora_extra)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, ticket, 
              tiempo, descripcion, mes, registro_usuario_id, grupo, es_hora_extra))
        
        conn.commit()
        
        # Limpiar caché
        try:
            clear_user_registros_cache(registro_usuario_id)
        except:
            pass
            
        show_success_message("✅ Registro creado exitosamente.", 1)
        
        # Incrementar sufijo para resetear los widgets dinámicos en la próxima carga
        if "form_key_suffix" in st.session_state:
            st.session_state.form_key_suffix += 1
        
        # Limpiar el formulario reiniciando la página
        st.rerun()
        
    except Exception as e:
        st.error(f"Error al guardar el registro: {str(e)}")
    finally:
        conn.close()

def render_user_edit_record_form(registro_seleccionado, registro_id, nombre_completo_usuario):
    """Renderiza el formulario de edición de registros para usuarios"""
    # Formulario para editar el registro
    fecha_val = registro_seleccionado['fecha']
    
    # Manejo robusto de fecha (puede ser string o Timestamp)
    try:
        if hasattr(fecha_val, 'date'):
            fecha_value = fecha_val.date()
        else:
            # Intentar parsear como string
            fecha_str = str(fecha_val)
            try:
                fecha_value = datetime.strptime(fecha_str, '%d/%m/%y').date()
            except ValueError:
                try:
                    fecha_value = datetime.strptime(fecha_str, '%d/%m/%Y').date()
                except ValueError:
                    # Fallback a hoy si falla todo
                    fecha_value = datetime.today().date()
    except Exception:
        fecha_value = datetime.today().date()
    
    fecha_edit = st.date_input("Fecha", value=fecha_value, key="edit_fecha")
    # Pasamos el objeto date directamente, la base de datos lo manejará mejor que un string
    
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
    # Asegurar que Cliente esté disponible
    if 'Cliente' not in modalidad_options:
        modalidad_options.append('Cliente')
    modalidad_index = modalidad_options.index(registro_seleccionado['modalidad']) if registro_seleccionado['modalidad'] in modalidad_options else 0
    modalidad_selected_edit = st.selectbox("Modalidad", options=modalidad_options, index=modalidad_index, key="edit_modalidad")
    
    # Campos adicionales
    tarea_realizada_edit = st.text_input("Tarea Realizada", value=registro_seleccionado['tarea_realizada'], key="edit_tarea", max_chars=100)
    numero_ticket_edit = st.text_input("Número de Ticket", value=registro_seleccionado['numero_ticket'], key="edit_ticket", max_chars=20)
    tiempo_edit = st.number_input("Tiempo (horas)", min_value=0.5, step=0.5, value=float(registro_seleccionado['tiempo']), key="edit_tiempo")
    descripcion_edit = st.text_area("Descripción", value=registro_seleccionado['descripcion'] if pd.notna(registro_seleccionado['descripcion']) else "", key="edit_descripcion", max_chars=250)
    
    # Checkbox de Hora Extra
    es_hora_extra_edit = st.checkbox("Hora extra", value=bool(registro_seleccionado.get('es_hora_extra', False)), key="edit_hora_extra")
    
    # Mes (automático basado en la fecha)
    mes_edit = month_name_es(fecha_edit.month)
    
    if st.button("Guardar Cambios", key="save_registro_edit"):
        if not tarea_realizada_edit:
            st.error("La tarea realizada es obligatoria.")
        elif tiempo_edit < 0.5:
            st.error("El tiempo mínimo debe ser de 0.5 horas (30 minutos).")
        else:
            save_user_record_changes(
                registro_id, fecha_edit, tecnico_selected_edit,
                cliente_selected_edit, tipo_selected_edit, modalidad_selected_edit,
                tarea_realizada_edit, numero_ticket_edit, tiempo_edit, descripcion_edit, mes_edit,
                grupo_selected_edit, es_hora_extra=es_hora_extra_edit
            )

def save_user_record_changes(registro_id, fecha, tecnico, cliente, tipo, modalidad, tarea, ticket, tiempo, descripcion, mes, grupo="General", es_hora_extra=False):
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
        WHERE fecha::date = %s::date AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s 
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
            tarea_realizada = %s, numero_ticket = %s, tiempo = %s, descripcion = %s, mes = %s, grupo = %s, es_hora_extra = %s
            WHERE id = %s
        ''', (str(fecha), id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, ticket, tiempo, descripcion, mes, grupo, es_hora_extra, registro_id))
        
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

    
    rol_id = get_user_rol_id(user_id)
    modalidades_df = get_modalidades_dataframe()
    modalidad_options = modalidades_df[['id_modalidad', 'descripcion']].values.tolist()
    desc_by_id = {int(row['id_modalidad']): str(row['descripcion']) for _, row in modalidades_df.iterrows()}

    # Banner superior: quién está hoy (Presencial o Cliente: Systemscorp) en tu departamento
    try:
        today = datetime.today().date()
        today_df = get_weekly_modalities_by_rol(int(rol_id), today, today)
        peers_df_names = get_users_by_rol(int(rol_id)).copy()
        if "nombre_completo" not in peers_df_names.columns:
            peers_df_names["nombre_completo"] = peers_df_names.apply(
                lambda r: f"{r.get('nombre','')} {r.get('apellido','')}".strip(), axis=1
            )
        name_by_uid = {int(r["id"]): r["nombre_completo"] for _, r in peers_df_names.iterrows()}

        presentes = []
        for _, r in today_df.iterrows():
            uid = int(r.get("user_id"))
            modalidad = str(r.get("modalidad") or "").strip().lower()
            cliente_nombre = str(r.get("cliente_nombre") or "").strip().lower()
            if modalidad == "presencial" or (modalidad == "cliente" and cliente_nombre == "systemscorp"):
                presentes.append(name_by_uid.get(uid, str(uid)))

        presentes = sorted(set([n for n in presentes if n]))

        inject_project_card_css()

        day_mapping_local = {
            'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
            'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
        }
        today_name = day_mapping_local.get(today.strftime("%A"), today.strftime("%A"))
        date_str = today.strftime("%d/%m")
        chips_html = "".join([
            f"<span class='office-chip'>{n}</span>"
            for n in presentes
        ])
        content_html = chips_html if chips_html else "<span class='office-chip-empty'>Sin asignaciones</span>"

        st.markdown(
            f"""
            <div class="office-card">
              <div class="office-card-title">🏢 Hoy en la oficina — {today_name} {date_str}</div>
              <div style="display:flex; flex-wrap:wrap; gap:6px;">{content_html}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    except Exception as e:
        st.caption(f"No se pudo generar el resumen de hoy: {e}")

    # Línea de separación bajo el banner
    st.markdown("<div style='border-top: 2px solid #4b5563; margin: 8px 0 14px;'></div>", unsafe_allow_html=True)

    # Asegurar que 'Cliente' esté disponible en el desplegable
    from .database import get_or_create_modalidad
    try:
        cliente_mod_id = int(get_or_create_modalidad("Cliente"))
        desc_by_id[cliente_mod_id] = "Cliente"
        if cliente_mod_id not in [int(mid) for mid, _ in modalidad_options]:
            modalidad_options.append([cliente_mod_id, "Cliente"])
    except Exception as e:
        st.error(f"Error al asegurar modalidad Cliente: {e}")
        cliente_mod_id = 4
        desc_by_id[cliente_mod_id] = "Cliente"
        if cliente_mod_id not in [int(mid) for mid, _ in modalidad_options]:
            modalidad_options.append([cliente_mod_id, "Cliente"])

    # Asegurar que 'Base en Casa' esté disponible en el desplegable
    try:
        bec_mod_id = int(get_or_create_modalidad("Base en Casa"))
        desc_by_id[bec_mod_id] = "Base en Casa"
        if bec_mod_id not in [int(mid) for mid, _ in modalidad_options]:
            modalidad_options.append([bec_mod_id, "Base en Casa"])
    except Exception as e:
        st.warning(f"No se pudo asegurar modalidad 'Base en Casa': {e}")
    # IDs de modalidades a mostrar
    options_ids = [int(mid) for mid, _ in modalidad_options]
    # Navegación de semana (independiente de admin)
    if 'user_week_offset' not in st.session_state:
        st.session_state.user_week_offset = 0
    start_of_week, end_of_week = get_week_dates(st.session_state.user_week_offset)
    start_date = start_of_week.date() if hasattr(start_of_week, 'date') else start_of_week
    end_date = end_of_week.date() if hasattr(end_of_week, 'date') else end_of_week
    week_range_str = format_week_range(start_of_week, end_of_week)

    is_current_week = st.session_state.user_week_offset == 0
    week_indicator = " 📍 (Semana Actual)" if is_current_week else ""

    nav_cols = st.columns([0.25, 0.5, 0.25])
    with nav_cols[0]:
        if st.button("⬅️", key="user_week_prev", use_container_width=True):
            st.session_state.user_week_offset -= 1
            st.rerun()
    with nav_cols[1]:
        center_row = st.columns([0.03, 0.94, 0.03])
        with center_row[1]:
            text_and_home = st.columns([0.86, 0.14])
            with text_and_home[0]:
                st.markdown(
                    f"<p style='text-align:center; margin:0; padding:6px; font-weight:600; white-space: nowrap;'>Semana: {week_range_str}{week_indicator}</p>",
                    unsafe_allow_html=True
                )
            with text_and_home[1]:
                if not is_current_week:
                    if st.button("🏠", key="user_week_home", help="Volver a la semana actual", use_container_width=True):
                        st.session_state.user_week_offset = 0
                        st.rerun()
                else:
                    st.empty()
    with nav_cols[2]:
        if st.button("➡️", key="user_week_next", use_container_width=True):
            st.session_state.user_week_offset += 1
            st.rerun()

    week_dates = []
    current_date = start_date
    for _ in range(5):
        week_dates.append(current_date)
        current_date += timedelta(days=1)

    feriados_set = {d for d in week_dates if is_feriado(d)}

    # Mapeo de días
    day_mapping = {
        'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
        'Thursday': 'Jueves', 'Friday': 'Viernes'
    }

    # Modalidades actuales del usuario (incluye cliente si existe)
    user_sched_df = get_user_weekly_modalities(user_id, start_date, end_date)
    user_sched_map = {}
    user_client_map = {}
    for _, row in user_sched_df.iterrows():
        fecha_obj = pd.to_datetime(row['fecha']).date()
        user_sched_map[fecha_obj] = int(row['modalidad_id'])
        if "cliente_id" in row and pd.notna(row["cliente_id"]):
            user_client_map[fecha_obj] = int(row["cliente_id"])

    # Defaults del usuario (para autocompletar días futuros sin asignación)
    default_by_dow = {}
    try:
        from .database import get_user_default_schedule
        defaults_df = get_user_default_schedule(user_id)
        for _, r in defaults_df.iterrows():
            dow = int(r["day_of_week"])
            mod_id = int(r["modalidad_id"])
            cli_id = int(r["cliente_id"]) if ("cliente_id" in r and pd.notna(r["cliente_id"])) else None
            default_by_dow[dow] = (mod_id, cli_id)
    except Exception:
        default_by_dow = {}

    # Clientes
    clientes_df = get_clientes_dataframe()
    cliente_options = [(int(row["id_cliente"]), row["nombre"]) for _, row in clientes_df.iterrows()]

    # Editor: solo los días del propio usuario
    st.markdown("Selecciona tu modalidad por día:")
    title_cols = st.columns(5)
    for i, day in enumerate(week_dates):
        with title_cols[i]:
            day_name_es = day_mapping.get(day.strftime("%A"), day.strftime("%A"))
            st.write(day_name_es)
            st.caption(day.strftime("%d/%m"))

    control_cols = st.columns(5)
    selected_by_day = {}
    selected_client_by_day = {}

    for i, day in enumerate(week_dates):
        dow = day.weekday()
        today = datetime.today().date()
        default_pair = default_by_dow.get(dow)
        default_mod_id = user_sched_map.get(day, None)

        if default_mod_id is None and default_pair and day >= today:
            default_mod_id = default_pair[0]

        options_ids = [int(mid) for mid, _ in modalidad_options]
        default_index = options_ids.index(default_mod_id) if (
            default_mod_id is not None and default_mod_id in options_ids
        ) else None

        with control_cols[i]:
            mod_id = st.selectbox(
                "Modalidad",
                options=options_ids,
                format_func=lambda x: desc_by_id.get(x, f"Modalidad {x}"),
                index=default_index,
                key=f"user_mod_{user_id}_{day.isoformat()}",
                label_visibility="collapsed"
            )
            selected_by_day[day] = mod_id

            es_cliente = (mod_id is not None) and desc_by_id.get(mod_id, "").strip().lower() == "cliente"
            if es_cliente:
                if not cliente_options:
                    st.info("No hay clientes cargados.")
                else:
                    client_ids = [cid for cid, _ in cliente_options]
                    default_client_id = user_client_map.get(day, None)
                    if default_client_id is None and default_pair and day >= today:
                        default_client_id = default_pair[1]

                    client_index = client_ids.index(default_client_id) if (
                        default_client_id is not None and default_client_id in client_ids
                    ) else None

                    client_id = st.selectbox(
                        "Cliente",
                        options=client_ids,
                        format_func=lambda cid: next(name for cid2, name in cliente_options if cid2 == cid),
                        index=client_index,
                        key=f"user_client_{user_id}_{day.isoformat()}",
                        label_visibility="collapsed"
                    )
                    selected_client_by_day[day] = client_id

    # Validación y guardado (solo afecta al usuario actual)
    pending_days = []
    for day in week_dates:
        mod_id = selected_by_day.get(day)
        if mod_id is None:
            pending_days.append(day)
            continue
        es_cliente = desc_by_id.get(mod_id, "").strip().lower() == "cliente"
        if es_cliente and selected_client_by_day.get(day) is None:
            pending_days.append(day)

    form_complete = len(pending_days) == 0

    if st.button("Guardar Planificación Semanal", type="primary", disabled=not form_complete):
        try:
            errores = []
            for day in week_dates:
                mod_id = selected_by_day[day]
                es_cliente = desc_by_id.get(mod_id, "").strip().lower() == "cliente"
                cliente_id = selected_client_by_day.get(day) if es_cliente else None
                try:
                    upsert_user_modality_for_date(user_id, rol_id, day, mod_id, cliente_id)
                except Exception as day_error:
                    errores.append(f"{day.strftime('%d/%m')}: {str(day_error)}")

            if not errores:
                st.success("Planificación guardada correctamente.")
                st.rerun()
            else:
                st.error("Se encontraron errores al guardar:")
                for e in errores:
                    st.error(f"- {e}")
        except Exception as e:
            st.error(f"Error general al guardar: {str(e)}")

    # Vista del equipo (solo lectura, mismo departamento)
    peers_df = get_users_by_rol(rol_id)
    
    # Modalidades actuales del usuario - usar objetos date consistentes
    user_sched_df = get_user_weekly_modalities(user_id, start_date, end_date)
    user_sched_map = {}
    for _, row in user_sched_df.iterrows():
        fecha_obj = pd.to_datetime(row['fecha']).date()
        user_sched_map[fecha_obj] = int(row['modalidad_id'])
    
    # Modalidades de todos en el rol para mostrar
    rol_sched_df = get_weekly_modalities_by_rol(rol_id, start_date, end_date)
    
    # Clientes y conjunto de nombres (para etiquetar y colorear como en Admin)
    clientes_df = get_clientes_dataframe()
    cliente_options = [(int(row["id_cliente"]), row["nombre"]) for _, row in clientes_df.iterrows()]
    cliente_nombres = {str(name).strip() for _, name in cliente_options}
    
    # Mapa (user_id, fecha) -> display, reemplazando "Cliente" por nombre real
    rol_map = {}
    for _, row in rol_sched_df.iterrows():
        fecha_obj = pd.to_datetime(row["fecha"]).date()
        display_val = row["modalidad"]
        try:
            if isinstance(display_val, str) and display_val.strip().lower() == "cliente":
                cliente_nombre = row.get("cliente_nombre")
                if cliente_nombre and str(cliente_nombre).strip():
                    # Mostrar SOLO el nombre del cliente (sin "Cliente - ")
                    display_val = str(cliente_nombre).strip()
                else:
                    display_val = "Cliente"
        except Exception:
            pass
        rol_map[(int(row["user_id"]), fecha_obj)] = display_val
    
    matriz = []
    for _, peer in peers_df.iterrows():
        peer_id = int(peer["id"])
        peer_name = peer["nombre_completo"]
        fila = [peer_name]
    
        asignadas_count = 0
        for day in week_dates:
            modalidad = rol_map.get((peer_id, day), "Sin asignar")
            if day in feriados_set:
                modalidad = "Feriado"
            fila.append(modalidad)
            if modalidad not in ("Sin asignar", "Feriado"):
                asignadas_count += 1
    
        if asignadas_count > 0:
            matriz.append(fila)
    
    if matriz:
        columnas = ["Usuario"] + [f"{day_mapping.get(day.strftime('%A'), day.strftime('%A'))}\n{day.strftime('%d/%m')}" for day in week_dates]
        df_matriz = pd.DataFrame(matriz, columns=columnas)
    
        # Estilo idéntico al Admin (colores y bordes)
        def colorear_modalidad(val):
            val_str = str(val).strip() if val is not None else ""
            val_norm = val_str.lower()
        
            # Detectar si es "Cliente - <nombre>" o nombre de cliente sin prefijo
            is_cliente_prefixed = val_norm.startswith("cliente - ")
            client_norm = val_norm.split(" - ", 1)[1].strip() if is_cliente_prefixed else None
            is_cliente_name = val_str in cliente_nombres
        
            # Presencial y Systemscorp (comparten verde)
            if (
                val_norm in ("presencial", "systemscorp")
                or (is_cliente_prefixed and client_norm == "systemscorp")
                or (is_cliente_name and val_norm == "systemscorp")
            ):
                return "background-color: #28a745; color: var(--text-color); font-weight: 600; border: 1px solid #3a3a3a"
        
            # Remoto y Base en Casa (azules)
            elif val_norm in ("remoto", "base en casa"):
                return "background-color: #3399ff; color: var(--text-color); font-weight: 600; border: 1px solid #3a3a3a"

            # Vacaciones (naranja) y Feriados
            elif val_norm in ("vacaciones", "feriado"):
                return "background-color: #f39c12; color: var(--text-color); font-weight: 600; border: 1px solid #3a3a3a"

            # Licencias (amatista/púrpura)
            elif val_norm == "licencia":
                return "background-color: #9b59b6; color: var(--text-color); font-weight: 600; border: 1px solid #3a3a3a"

            # Cumpleaños (rosa fuerte)
            elif val_norm in ("dia de cumpleaños", "cumpleaños", "día de cumpleaños"):
                return "background-color: #e84393; color: var(--text-color); font-weight: 600; border: 1px solid #3a3a3a"

            # Sin asignar (solo borde)
            elif val_norm == "sin asignar":
                return "border: 1px solid #3a3a3a"
        
            # Otros clientes (violeta)
            elif val_norm == "cliente" or is_cliente_prefixed or is_cliente_name:
                return "background-color: #8e44ad; color: var(--text-color); font-weight: 600; border: 1px solid #3a3a3a"
        
            # Fallback (gris)
            else:
                return "background-color: #6c757d; color: var(--text-color); font-weight: 600; border: 1px solid #3a3a3a"
    
        styled_df = (
            df_matriz
                .style
                .map(colorear_modalidad, subset=[c for c in df_matriz.columns if c != "Usuario"])
                .set_properties(subset=["Usuario"], **{"border": "1px solid #3a3a3a"})
                .hide(axis="index")
        )
    
        # Render con HTML, igual que Admin
        import streamlit.components.v1 as components
        html = f"""
<div class="table-wrapper" style="width: 1400px; overflow-x: auto;">
  <style>
    .table-wrapper {{ width: 1400px !important; }}
    .table-wrapper table.dataframe {{ width: 1400px !important; table-layout: fixed; border-collapse: collapse; }}
    .table-wrapper th, .table-wrapper td {{ border: 1px solid #3a3a3a; padding: 8px; white-space: nowrap; }}
    .table-wrapper td:first-child, .table-wrapper th:first-child {{ width: 200px; }}
    .table-wrapper th:not(:first-child), .table-wrapper td:not(:first-child) {{ width: 240px; }}
    .table-wrapper th {{ color: var(--text-color); opacity: 0.85; font-weight: 600; }}
    .table-wrapper td:first-child {{ color: var(--text-color); opacity: 0.85; font-weight: 600; }}
    /* Ensure inline styles also respect opacity via inherited or forced text color behavior if needed */
    .table-wrapper td {{ color: var(--text-color); opacity: 0.85; }}
  </style>
  {styled_df.to_html()}
</div>
"""
        row_height = 40
        num_rows = len(matriz)
        total_height = 60 + num_rows * row_height
        total_height = min(900, max(380, total_height))
        st.markdown(html, unsafe_allow_html=True)
    else:
        st.info("No hay otros usuarios en tu mismo departamento.")

def render_vacaciones_tab(user_id, nombre_completo_usuario):
    """Renderiza la pestaña de gestión de licencias"""
    st.header("Gestión de Licencias")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("🏖️ Quién está de licencia")
        try:
            df_vacaciones = get_vacaciones_activas()
            if not df_vacaciones.empty:
                # Format display
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
        st.subheader("✈️ Modo Licencia")
        st.write("Configura tu periodo de licencia. Se generarán automáticamente los registros correspondientes.")
        
        tipo_ausencia = st.selectbox("Tipo de Licencia", ["Vacaciones", "Licencia", "Dia de Cumpleaños"], key="user_vac_tipo_sel")

        with st.form("vacaciones_form"):
            st.write(f"Solicitando: **{tipo_ausencia}**")
            
            if tipo_ausencia == "Dia de Cumpleaños":
                col_d1, _ = st.columns(2)
                with col_d1:
                    start_date = st.date_input("Fecha (1 día)", min_value=datetime.today(), key="user_vac_start_birthday")
                end_date = start_date
            else:
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    start_date = st.date_input("Fecha Inicio", min_value=datetime.today(), key="user_vac_start")
                with col_d2:
                    # Remove dynamic min_value dependency on start_date inside form to prevent widget reset issues
                    end_date = st.date_input("Fecha Fin", min_value=datetime.today(), key="user_vac_end")
                
            submit = st.form_submit_button("Registrar Licencia", type="primary")
            
            if submit:
                if start_date > end_date:
                    st.error("La fecha de fin debe ser posterior a la de inicio.")
                else:
                    try:
                        save_vacaciones(user_id, start_date, end_date, tipo=tipo_ausencia)
                        # Invalidar caché de admin para que se reflejen los cambios inmediatamente
                        try:
                            cached_get_weekly_modalities_by_rol.clear()
                        except:
                            pass
                        st.success(f"¡{tipo_ausencia} registrada! Del {start_date} al {end_date}.")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error guardando licencia: {e}")
        
        # Mis vacaciones futuras/historial
        st.markdown("---")
        
        col_header, col_year = st.columns([3, 1])
        with col_header:
            st.subheader("📅 Mis Periodos Registrados")
        
        current_year = datetime.now().year
        years = list(range(2024, current_year + 3))
        # Ensure current year is in list
        if current_year not in years: years.append(current_year)
        years.sort()
        
        with col_year:
             selected_year = st.selectbox(
                 "Año", 
                 options=years, 
                 index=years.index(current_year) if current_year in years else 0, 
                 key="vac_year_selector"
             )

        try:
            my_vacs = get_user_vacaciones(user_id, year=selected_year)
            if not my_vacs.empty:
                for _, row in my_vacs.iterrows():
                    row_tipo = row.get('tipo', 'Vacaciones')
                    if not row_tipo: row_tipo = 'Vacaciones'

                    with st.expander(f"{row_tipo}: {row['fecha_inicio']} - {row['fecha_fin']}"):
                        # Edit Logic
                        edit_key = f"edit_mode_vac_user_{row['id']}"
                        is_editing = st.session_state.get(edit_key, False)
                        
                        if is_editing:
                            edit_tipo_key = f"edit_tipo_sel_user_{row['id']}"
                            current_tipo = st.selectbox("Tipo", ["Vacaciones", "Licencia", "Dia de Cumpleaños"], 
                                                      index=["Vacaciones", "Licencia", "Dia de Cumpleaños"].index(row_tipo) if row_tipo in ["Vacaciones", "Licencia", "Dia de Cumpleaños"] else 0,
                                                      key=edit_tipo_key)

                            with st.form(key=f"edit_vac_form_user_{row['id']}"):
                                st.write("Modificar fechas:")
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
                                    c1, c2 = st.columns(2)
                                    with c1:
                                        n_start = st.date_input("Desde", value=d_start)
                                    with c2:
                                        n_end = st.date_input("Hasta", value=d_end, min_value=n_start)
                                    
                                b1, b2 = st.columns(2)
                                with b1:
                                    if st.form_submit_button("💾 Guardar"):
                                        if update_vacaciones(row['id'], n_start, n_end, tipo=current_tipo):
                                            # Invalidar caché de admin
                                            try:
                                                cached_get_weekly_modalities_by_rol.clear()
                                            except:
                                                pass
                                            st.success("Modificado correctamente")
                                            st.session_state[edit_key] = False
                                            time.sleep(0.5)
                                            st.rerun()
                                        else:
                                            st.error("Error al modificar")
                                with b2:
                                    if st.form_submit_button("❌ Cancelar"):
                                        st.session_state[edit_key] = False
                                        st.rerun()
                        else:
                            col_a, col_b = st.columns([1, 4])
                            with col_a:
                                if st.button("✏️", key=f"btn_edit_vac_{row['id']}"):
                                    st.session_state[edit_key] = True
                                    st.rerun()
                            with col_b:
                                if st.button("🗑️ Eliminar periodo", key=f"del_vac_{row['id']}"):
                                    if delete_vacaciones(row['id']):
                                        # Invalidar caché de admin
                                        try:
                                            cached_get_weekly_modalities_by_rol.clear()
                                        except:
                                            pass
                                        st.success("Periodo eliminado.")
                                        time.sleep(0.5)
                                        st.rerun()
                                    else:
                                        st.error("No se pudo eliminar.")
            else:
                st.caption("No tienes periodos de licencia registrados.")
        except Exception as e:
            st.error(f"Error cargando tus licencias: {e}")
