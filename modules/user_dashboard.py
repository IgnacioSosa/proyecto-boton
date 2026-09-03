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
    upsert_user_default_schedule,
    get_clientes_favoritos, toggle_cliente_favorito,
    get_vacaciones_activas, get_user_vacaciones, save_vacaciones, delete_vacaciones, update_vacaciones,
    get_upcoming_vacaciones,
    is_feriado,
    get_vacaciones_by_users_and_range
)
from .utils import (
    get_week_dates,
    format_week_range,
    prepare_weekly_chart_data,
    show_success_message,
    month_name_es,
    safe_rerun,
    parse_registro_datetime,
    format_registro_date_iso,
)
from .admin_planning import cached_get_weekly_modalities_by_rol, cached_get_user_default_schedule
from .ui_components import inject_project_card_css

def clear_chart_cache():
    """Limpia la caché de los gráficos en session_state para forzar recálculo"""
    # Iteramos sobre una copia de las claves para poder modificar el diccionario
    for key in list(st.session_state.keys()):
        if key.startswith("chart_data_"):
            del st.session_state[key]


def _parse_registro_datetime(fecha_val):
    return parse_registro_datetime(fecha_val)


def normalize_registro_tiempo(tiempo):
    """Normaliza el tiempo (horas) a float redondeado 2 decimales.

    Si no se puede parsear devuelve 0.0. No valida reglas de negocio; la
    validación de rango [0.5, 24] queda en validate_new_record_inputs.
    """
    if tiempo is None:
        return 0.0
    try:
        return round(float(tiempo), 2)
    except (TypeError, ValueError):
        return 0.0


def normalize_registro_text(value):
    """Normaliza strings de registros: strip + None/NaN/empty → ''"""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(value).strip()
    return s


def validate_new_record_inputs(cliente, tipo, modalidad, tarea_realizada, tiempo, fecha=None):
    """Validaciones de negocio puras para la carga/edición de un registro.

    Returns `(ok: bool, message: str)`.
    - ok=True  → datos válidos, message=""
    - ok=False → datos inválidos, message es el texto con el error para UI.

    No toca st.session_state ni DB, es 100% determinística y testeable.
    """
    if not normalize_registro_text(cliente):
        return False, "El cliente es obligatorio."
    if not normalize_registro_text(tipo):
        return False, "El tipo de tarea es obligatorio."
    if not normalize_registro_text(modalidad):
        return False, "La modalidad es obligatoria."
    if not normalize_registro_text(tarea_realizada):
        return False, "La tarea realizada es obligatoria."

    t = normalize_registro_tiempo(tiempo)
    if t < 0.5:
        return False, "El tiempo mínimo debe ser de 0.5 horas (30 minutos)."
    if t > 24:
        return False, "El tiempo máximo por registro es de 24 horas."

    if fecha is not None:
        # fecha puede ser str ISO, DD/MM/YY, date o datetime. Si no se puede
        # interpretar, reportar.
        parsed = parse_registro_datetime(fecha)
        if pd.isna(parsed):
            return False, "Fecha inválida."
    return True, ""


def _normalize_name_tokens(full_name):
    """Devuelve set de tokens alfanuméricos minúsculas para comparar nombres.

    Normaliza strings como "Sosa, Ignacio Martin" e "Ignacio Martin Sosa" al
    mismo set {"sosa","ignacio","martin"}, de forma que el orden y las
    comas no importen. Se ignoran tokens cortos tipo "de"/"la" para no
    dar falsos positivos.
    """
    s = normalize_registro_text(full_name).lower()
    if not s:
        return set()
    for ch in [",", ".", ";", ":", "-", "_", "/", "\\"]:
        s = s.replace(ch, " ")
    tokens = [t for t in s.split() if t]
    stop = {"de", "la", "los", "las", "del", "el", "y", "e"}
    return {t for t in tokens if len(t) >= 2 and t not in stop}


def can_user_delete_registro(
    nombre_tecnico_registro,
    nombre_usuario_sesion,
    user_rol_nombre=None,
    registro_usuario_id=None,
    session_user_id=None,
):
    """Chequeo multi-capa de ownership + permisos para borrar un registro.

    Capas (se acepta si alguna pasa):
      1. ID coincidente: registro_usuario_id == session_user_id.
      2. Nombre exacto (case/whitespace-insensitive): == owner.
      3. Nombres coinciden por tokens (soporta "Apellido, Nombre" vs
         "Nombre Apellido", con/sin tildes menores).
      4. Rol supervisor (adm_tecnico / admin / hipervisor / adm_comercial).
    """
    # Capa 1: id usuario (más robusta de todas, no depende de strings)
    try:
        rid = int(registro_usuario_id) if registro_usuario_id is not None else None
        sid = int(session_user_id) if session_user_id is not None else None
        if rid is not None and sid is not None and rid == sid:
            return True
    except (TypeError, ValueError):
        pass

    # Capa 2: nombre completo igual
    reg_name = normalize_registro_text(nombre_tecnico_registro).lower()
    session_name = normalize_registro_text(nombre_usuario_sesion).lower()
    if reg_name and session_name and reg_name == session_name:
        return True

    # Capa 3: coincidencia por tokens (Apellido, Nombre vs Nombre Apellido)
    reg_toks = _normalize_name_tokens(nombre_tecnico_registro)
    ses_toks = _normalize_name_tokens(nombre_usuario_sesion)
    if len(reg_toks) >= 2 and len(ses_toks) >= 2:
        common = reg_toks & ses_toks
        # Requerimos al menos 2 tokens en común para evitar falsos positivos
        # (ej: "Usuario A" vs "Usuario B" → comparten solo "usuario" → False)
        if len(common) >= 2 and (
            reg_toks == ses_toks
            or reg_toks.issubset(ses_toks)
            or ses_toks.issubset(reg_toks)
        ):
            return True

    # Capa 4: rol supervisor (permiso explícito, no requiere ownership)
    rol = normalize_registro_text(user_rol_nombre).lower()
    if rol in {"adm_tecnico", "admin", "hipervisor", "adm_comercial"}:
        return True

    return False


def parse_registro_option_id(option_text):
    """Extrae el id entero del formato usado por build_registro_options_for_selectbox.

    Devuelve None si no se puede parsear (seguridad: evita ValueError en UI).
    """
    if not option_text:
        return None
    try:
        head = str(option_text).split(" - ", 1)[0].strip()
        return int(head)
    except (TypeError, ValueError):
        return None


def build_registro_options_for_selectbox(registro_ids, registro_fechas, registro_tareas, registro_clientes):
    """Construye las opciones descriptivas del selectbox de registros (editar/eliminar).

    Maneja nulos, fechas date/datetime/string y textos vacíos. 100% pura.
    """
    options = []
    rids = list(registro_ids or [])
    rfechas = list(registro_fechas or [])
    rtareas = list(registro_tareas or [])
    rclientes = list(registro_clientes or [])
    n = max(len(rids), len(rfechas), len(rtareas), len(rclientes))
    for i in range(n):
        rid = rids[i] if i < len(rids) else ""
        rfecha = rfechas[i] if i < len(rfechas) else None
        rtarea = rtareas[i] if i < len(rtareas) else None
        rcliente = rclientes[i] if i < len(rclientes) else None

        tarea_display = rtarea if rtarea and str(rtarea).strip() else "Sin descripción"
        cliente_display = rcliente if rcliente and str(rcliente).strip() else "Sin cliente"
        if hasattr(rfecha, "strftime"):
            try:
                fecha_display = rfecha.strftime("%d/%m/%y")
            except Exception:
                fecha_display = rfecha if rfecha else "Sin fecha"
        else:
            parsed = parse_registro_datetime(rfecha)
            if pd.notna(parsed):
                fecha_display = parsed.strftime("%d/%m/%y")
            else:
                fecha_display = rfecha if rfecha and str(rfecha).strip() else "Sin fecha"
        options.append(f"{rid} - {fecha_display} - {cliente_display} - {tarea_display}")
    return options


def compute_new_batch_delete_ids(selected_options):
    """Extrae ids únicos y ordenados para eliminación masiva a partir de
    las opciones del multiselect. Omite entradas que no pueden parsearse.
    """
    ids = []
    seen = set()
    for opt in selected_options or []:
        rid = parse_registro_option_id(opt)
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        ids.append(rid)
    return sorted(ids)

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
                df_regs['fecha_dt'] = df_regs['fecha'].apply(_parse_registro_datetime)
        
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
            icon_str = "🔔" if has_alerts else "🔕"
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
        if hasattr(st, "fragment"):
            @st.fragment
            def _render_user_planner_fragment():
                render_weekly_modality_planner(user_id, nombre_completo_usuario)
            _render_user_planner_fragment()
        else:
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
    
    # Asegurar que existe fecha_dt con lógica robusta
    if 'fecha_dt' not in display_df.columns:
        display_df['fecha_dt'] = display_df['fecha'].apply(_parse_registro_datetime)
    
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
            safe_rerun()
    
    with nav_cols[1]:
        st.write("") 
    
    with nav_cols[2]:
        if st.button("⬅️", use_container_width=True):
            st.session_state.week_offset -= 1
            safe_rerun()
    
    with nav_cols[3]:
        st.markdown(f"<p style='text-align: center; font-weight: bold; margin: 0; padding: 8px;'>{week_range_str}</p>", unsafe_allow_html=True)
    
    with nav_cols[4]:
        disable_next = st.session_state.week_offset == 0
        if st.button("➡️", disabled=disable_next, use_container_width=True):
            st.session_state.week_offset += 1
            safe_rerun()
    
    with nav_cols[5]:
        st.write("")  
    
    # Verificar si existe la columna fecha_dt, si no, procesarla
    if 'fecha_dt' not in user_registros_df.columns:
        registros_validos = user_registros_df.dropna(subset=['fecha'])
        if registros_validos.empty:
            st.info("No hay registros válidos para mostrar.")
            return
        # Procesar fechas si no están procesadas
        user_registros_df['fecha_dt'] = user_registros_df['fecha'].apply(_parse_registro_datetime)
    
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
    if hasattr(st, "fragment"):
        @st.fragment
        def _render_records_form_fragment():
            render_add_record_form(user_id, nombre_completo_usuario)
        _render_records_form_fragment()
    else:
        render_add_record_form(user_id, nombre_completo_usuario)

def render_add_record_form(user_id, nombre_completo_usuario):
    """Renderiza el formulario para agregar nuevos registros"""
    st.subheader("Nuevo Registro de Horas")
    
    rol_id = get_user_rol_id(user_id)
    
    # Saneo EXTRA al render del form para casos límite (backup viejo,
    # assignaciones manuales rotas, etc.). Las 3 funciones son idempotentes
    # y baratas; corren solo 1 vez por rerun y garantizan que el JOIN
    # tipos_tarea_roles traiga resultados incluso si el admin seleccionó
    # dpto_tecnico pero por algún bug se guardó solo adm_tecnico.
    from .database import (
        migrate_task_type_department_roles,
        repair_task_type_roles_missing_from_departments,
        repair_task_types_without_any_roles,
    )
    migrate_task_type_department_roles()
    repair_task_type_roles_missing_from_departments()
    repair_task_types_without_any_roles()
    
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
    
    # --- Lógica para asegurar limpieza al entrar ---
    # Si detectamos que los widgets tienen valores pero no se ha enviado el form,
    # forzamos su limpieza si es la primera carga o recarga de la página.
    # Usamos una clave 'last_suffix' para detectar cambios de estado.
    if "last_form_suffix" not in st.session_state:
        st.session_state.last_form_suffix = suffix
    
    # Si el sufijo cambió (significa que se guardó exitosamente), los widgets nuevos (con nuevo key)
    # estarán vacíos por defecto.
    # Pero si el usuario recarga la página (F5), el sufijo puede mantenerse pero Streamlit 
    # podría persistir los valores en session_state.
    # Para asegurar limpieza total, podemos usar 'value=""' explícitamente si no hay interacción.
    
    grupo_selected = st.selectbox("Sector *", options=grupo_names, index=0, key=f"new_grupo_{suffix}")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Fecha por defecto: Hoy
        min_registro_date = datetime(2024, 1, 1).date()
        max_registro_date = (datetime.today() + timedelta(days=366)).date()
        fecha_nuevo = st.date_input(
            "Fecha *",
            value=datetime.today().date(),
            min_value=min_registro_date,
            max_value=max_registro_date,
            key=f"new_fecha_{suffix}"
        )
        # GUARDAR COMO ISO PARA EVITAR AMBIGÜEDAD (YYYY-MM-DD)
        fecha_formateada_nuevo = fecha_nuevo.strftime('%Y-%m-%d')

        cliente_rows = [
            (
                int(row["id_cliente"]),
                str(row["nombre"]).strip(),
                (str(row.get("alias") or "").strip() if pd.notna(row.get("alias")) else "")
            )
            for _, row in clientes_df.iterrows()
            if pd.notna(row.get("id_cliente")) and str(row.get("nombre") or "").strip()
        ]
        favoritos_ids = set(get_clientes_favoritos(user_id))
        ordered_cliente_rows = sorted(
            cliente_rows,
            key=lambda x: (0 if x[0] in favoritos_ids else 1, (x[2] or x[1]).upper())
        )
        cliente_ids = [cid for cid, _, _ in ordered_cliente_rows]
        cliente_name_by_id = {cid: cname for cid, cname, _ in ordered_cliente_rows}
        cliente_display_by_id = {cid: (alias if alias else cname) for cid, cname, alias in ordered_cliente_rows}

        cliente_col, favorito_col = st.columns([0.90, 0.10], vertical_alignment="bottom")
        with cliente_col:
            cliente_selected_id = st.selectbox(
                "Cliente *",
                options=cliente_ids,
                format_func=lambda cid: f"⭐ {cliente_display_by_id[cid]}" if cid in favoritos_ids else cliente_display_by_id[cid],
                index=None,
                placeholder="Seleccione un cliente...",
                key=f"new_cliente_{suffix}"
            )
        with favorito_col:
            try:
                cliente_selected_id_safe = int(cliente_selected_id) if cliente_selected_id is not None else None
            except (TypeError, ValueError):
                cliente_selected_id_safe = None
            star_filled = (cliente_selected_id_safe is not None and cliente_selected_id_safe in favoritos_ids)
            if st.button(
                "⭐" if star_filled else "☆",
                key=f"toggle_fav_cliente_{suffix}",
                disabled=(cliente_selected_id_safe is None),
                use_container_width=True
            ):
                if cliente_selected_id_safe is None:
                    st.toast("Selecciona un cliente antes de cambiar favoritos.", icon="ℹ️")
                else:
                    toggled = toggle_cliente_favorito(user_id, cliente_selected_id_safe)
                    if toggled:
                        st.toast("Cliente agregado a favoritos.", icon="⭐")
                    else:
                        st.toast("Cliente eliminado de favoritos.", icon="ℹ️")
                safe_rerun()

        cliente_selected_nuevo = cliente_name_by_id.get(cliente_selected_id) if cliente_selected_id is not None else None
        
        tipo_options = tipos_df['descripcion'].tolist()
        # Inicializar como vacío (None) para permitir escritura directa
        tipo_selected_nuevo = st.selectbox("Tipo de Tarea *", options=tipo_options, index=None, placeholder="Seleccione un tipo...", key=f"new_tipo_{suffix}")
        
        # Checkbox de Hora Extra - default False
        es_hora_extra_nuevo = st.checkbox("Hora extra", value=False, key=f"new_hora_extra_{suffix}")
    
    with col2:
        modalidad_options = modalidades_df['descripcion'].tolist()
        # Asegurar que Cliente esté disponible
        if 'Cliente' not in modalidad_options:
            modalidad_options.append('Cliente')
        
        # Inicializar como vacío (None) para permitir escritura directa
        modalidad_selected_nuevo = st.selectbox("Modalidad *", options=modalidad_options, index=None, placeholder="Seleccione una modalidad...", key=f"new_modalidad_{suffix}")
        
        # Inputs de texto vacíos por defecto
        # Streamlit mantiene el estado si la key es la misma.
        # Al incrementar el suffix en save_new_user_record, cambiamos la key, forzando un nuevo widget vacío.
        tarea_realizada_nuevo = st.text_input("Tarea Realizada *", value="", key=f"new_tarea_{suffix}", max_chars=100)
        numero_ticket_nuevo = st.text_input("Número de Ticket", value="", key=f"new_ticket_{suffix}", max_chars=20)
        # Tiempo default 0.5
        tiempo_nuevo = st.number_input("Tiempo (horas) *", value=0.5, min_value=0.5, step=0.5, key=f"new_tiempo_{suffix}")
    
    descripcion_nuevo = st.text_area("Descripción", value="", key=f"new_descripcion_{suffix}", max_chars=250)
    mes_nuevo = month_name_es(fecha_nuevo.month)
    
    if st.button("💾 Guardar Registro", key="save_new_registro", type="primary"):
        ok, msg = validate_new_record_inputs(
            cliente_selected_nuevo, tipo_selected_nuevo, modalidad_selected_nuevo,
            tarea_realizada_nuevo, tiempo_nuevo, fecha=fecha_formateada_nuevo
        )
        if not ok:
            st.error(msg)
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
    
    # Aplicar la conversión a ambos dataframes
    if not user_registros_df.empty:
        user_registros_df['fecha_dt'] = user_registros_df['fecha'].apply(_parse_registro_datetime)
    
    if not unassigned_registros_df.empty:
        unassigned_registros_df['fecha_dt'] = unassigned_registros_df['fecha'].apply(_parse_registro_datetime)
    
    # Combinar ambos DataFrames
    if not unassigned_registros_df.empty:
        combined_df = pd.concat([user_registros_df, unassigned_registros_df], ignore_index=True)
        # Mostrar primero los registros mas nuevos segun su ID
        combined_df = combined_df.sort_values('id', ascending=False)
    else:
        combined_df = user_registros_df
        if not combined_df.empty:
            # Mostrar primero los registros mas nuevos segun su ID
            combined_df = combined_df.sort_values('id', ascending=False)
    
    if not combined_df.empty:
        # Desplegable para editar registros
        with st.expander("✏️ Editar Registro", expanded=False):
            st.subheader("Editar Registro Existente")
            
            registro_ids = combined_df['id'].tolist()
            registro_fechas = combined_df['fecha'].tolist()
            registro_tareas = combined_df['tarea_realizada'].tolist()
            registro_clientes = combined_df['cliente'].tolist()
            
            registro_options = build_registro_options_for_selectbox(
                registro_ids, registro_fechas, registro_tareas, registro_clientes
            )
            
            selected_registro_edit = st.selectbox("Seleccionar Registro para Editar", options=registro_options, key="select_registro_edit")
            if selected_registro_edit:
                registro_id = parse_registro_option_id(selected_registro_edit)
                if registro_id is not None:
                    registro_seleccionado = combined_df[combined_df['id'] == registro_id].iloc[0]
                    render_user_edit_record_form(registro_seleccionado, registro_id, nombre_completo_usuario)
        
        # Desplegable para eliminación 1x1
        with st.expander("🗑️ Eliminar Registro (Individual)", expanded=False):
            st.subheader("Eliminar Registro Existente")
            
            selected_registro_delete = st.selectbox("Seleccionar Registro para Eliminar", options=registro_options, key="select_registro_delete")
            if selected_registro_delete:
                registro_id = parse_registro_option_id(selected_registro_delete)
                if registro_id is not None:
                    registro_seleccionado = combined_df[combined_df['id'] == registro_id].iloc[0]
                    def render_user_delete_record_form(registro_seleccionado, registro_id, nombre_completo_usuario):
                        """Renderiza el formulario de eliminación de registros para usuarios"""
                        st.warning("¿Estás seguro de que deseas eliminar este registro? Esta acción no se puede deshacer.")
                        if st.button("Eliminar Registro", key="delete_registro_btn"):
                            session_user_id = st.session_state.get("user_id")

                            # Obtener rol del usuario logueado si está disponible para permisos ampliados
                            user_rol_nombre = None
                            try:
                                conn_probe = get_connection()
                                try:
                                    c_probe = conn_probe.cursor()
                                    c_probe.execute("SELECT r.nombre FROM roles r JOIN usuarios u ON u.rol_id = r.id_rol WHERE u.id = %s LIMIT 1", (session_user_id,))
                                    row_probe = c_probe.fetchone()
                                    if row_probe and row_probe[0]:
                                        user_rol_nombre = row_probe[0]
                                finally:
                                    conn_probe.close()
                            except:
                                user_rol_nombre = None

                            registro_usuario_id = None
                            try:
                                if "usuario_id" in registro_seleccionado.index:
                                    val = registro_seleccionado["usuario_id"]
                                    if pd.notna(val):
                                        registro_usuario_id = int(val)
                            except Exception:
                                registro_usuario_id = None

                            if can_user_delete_registro(
                                registro_seleccionado['tecnico'],
                                nombre_completo_usuario,
                                user_rol_nombre=user_rol_nombre,
                                registro_usuario_id=registro_usuario_id,
                                session_user_id=session_user_id,
                            ):
                                conn = get_connection()
                                c = conn.cursor()
                                try:
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
                                        clear_chart_cache()
                                    except:
                                        pass
                                    
                                    show_success_message("✅ Registro eliminado exitosamente. La entrada ha sido completamente removida del sistema.", 1.5)
                                    safe_rerun()
                                finally:
                                    conn.close()
                            else:
                                st.error("No tienes permiso para eliminar este registro.")
                
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
                ids_to_delete = compute_new_batch_delete_ids(selected_registros_batch)
                count = len(ids_to_delete)
                if st.button(f"🗑️ Eliminar {count} Registros Seleccionados", type="primary", key="btn_batch_delete") and count > 0:
                    
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
                            clear_chart_cache()
                        except:
                            pass
                        
                        show_success_message(f"✅ Se han eliminado {deleted_count} registros exitosamente.", 2)
                        safe_rerun()
                    else:
                        st.error("Hubo un error al intentar eliminar los registros.")

        # Mostrar información sobre registros no asignados
        if not unassigned_registros_df.empty:
            st.info(f"ℹ️ Se encontraron {len(unassigned_registros_df)} registros no asignados que coinciden con tu nombre. Estos registros se incluyen en las opciones de edición/eliminación.")
    else:
        st.info("No hay registros para editar o eliminar.")

def get_total_hours_for_tecnico_on_date(conn, id_tecnico, fecha, exclude_registro_id=None):
    c = conn.cursor()
    fecha_str = format_registro_date_iso(fecha)
    if not fecha_str:
        return 0.0
    if exclude_registro_id is not None:
        c.execute(
            '''
            SELECT COALESCE(SUM(tiempo), 0)
            FROM registros
            WHERE id_tecnico = %s
              AND (
                    CASE
                        WHEN fecha ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN to_date(fecha, 'YYYY-MM-DD')
                        WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{2}$' THEN to_date(fecha, 'DD/MM/YY')
                        WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{4}$' THEN to_date(fecha, 'DD/MM/YYYY')
                        ELSE NULL
                    END
                  ) = %s::date
              AND id != %s
            ''',
            (id_tecnico, fecha_str, exclude_registro_id)
        )
    else:
        c.execute(
            '''
            SELECT COALESCE(SUM(tiempo), 0)
            FROM registros
            WHERE id_tecnico = %s
              AND (
                    CASE
                        WHEN fecha ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN to_date(fecha, 'YYYY-MM-DD')
                        WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{2}$' THEN to_date(fecha, 'DD/MM/YY')
                        WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{4}$' THEN to_date(fecha, 'DD/MM/YYYY')
                        ELSE NULL
                    END
                  ) = %s::date
            ''',
            (id_tecnico, fecha_str)
        )
    total = c.fetchone()[0]
    try:
        return round(float(total), 2)
    except Exception:
        return 0.0


def _resolve_id_tecnico_for_record(conn, tecnico_full_name, fallback_user_id):
    cur = conn.cursor()
    try:
        tecnico_lookup = (tecnico_full_name or "").strip()
        if not tecnico_lookup:
            return None
        # 1. Match exacto (normalizado) en tabla tecnicos por nombre completo
        cur.execute(
            """
            SELECT id_tecnico, nombre, apellido, email, activo
            FROM tecnicos
            WHERE (TRIM(COALESCE(nombre,'')) || ' ' || TRIM(COALESCE(apellido,''))) = %s
               OR (TRIM(COALESCE(nombre,'')) || TRIM(COALESCE(apellido,'')))   = %s
               OR TRIM(COALESCE(nombre,'')) = %s
            ORDER BY CASE WHEN activo IS TRUE THEN 0 ELSE 1 END, id_tecnico ASC
            """,
            (tecnico_lookup, tecnico_lookup.replace(' ', ''), tecnico_lookup),
        )
        rows = cur.fetchall() or []
        if len(rows) == 1:
            return int(rows[0][0])
        if len(rows) > 1:
            return int(rows[0][0])
        # 2. Sin match en tecnicos. Usar la tabla usuarios para desambiguar por email
        #    (hay usuarios adm_tecnico/tecnico que comparten nombre completo)
        user_email = None
        try:
            cur.execute(
                """
                SELECT email FROM usuarios WHERE id = %s AND COALESCE(email, '') <> ''
                """,
                (int(fallback_user_id),),
            )
            row = cur.fetchone()
            if row and row[0]:
                user_email = (row[0] or "").strip().lower()
        except Exception:
            user_email = None

        # 3. Buscar en usuarios por nombre completo para desambiguar (clave ÚNICA: id de usuario logueado)
        probable_user_row = None
        try:
            cur.execute(
                """
                SELECT COALESCE(email, ''), id, rol_id,
                       TRIM(COALESCE(nombre,'') || ' ' || COALESCE(apellido,''))
                FROM usuarios
                WHERE (TRIM(COALESCE(nombre,'')) || ' ' || TRIM(COALESCE(apellido,''))) = %s
                   OR (TRIM(COALESCE(nombre,'')) || TRIM(COALESCE(apellido,'')))   = %s
                   OR TRIM(COALESCE(nombre,'')) = %s
                ORDER BY id ASC
                """,
                (tecnico_lookup, tecnico_lookup.replace(' ', ''), tecnico_lookup),
            )
            user_rows = cur.fetchall() or []

            if len(user_rows) == 0:
                probable_user_row = None
            elif len(user_rows) == 1:
                probable_user_row = user_rows[0]
            else:
                # Múltiples homónimos (mismo nombre completo). CASO ESCALADO: algunos pueden
                # incluso compartir email. Entonces NO usamos email como clave única; usamos
                # el ID del usuario LOGUEADO (fallback_user_id) que garantiza 1 solo match.
                fallback_id = None
                try:
                    fallback_id = int(fallback_user_id)
                except Exception:
                    fallback_id = None

                matched_by_id = []
                matched_by_email = []
                if fallback_id is not None:
                    matched_by_id = [r for r in user_rows if int(r[1]) == fallback_id]

                if matched_by_id:
                    probable_user_row = matched_by_id[0]
                else:
                    if user_email:
                        matched_by_email = [
                            r for r in user_rows if (r[0] or "").strip().lower() == user_email
                        ]
                    if len(matched_by_email) == 1:
                        probable_user_row = matched_by_email[0]
                    elif len(matched_by_email) > 1:
                        # Comparten nombre y mail: elegimos el usuario más chico (más viejo)
                        # de este subgrupo, pero marcamos que no fue desambiguable.
                        probable_user_row = matched_by_email[0]
                    else:
                        # Fallback final: usuario más antiguo por ID (determinístico)
                        probable_user_row = user_rows[0]
        except Exception:
            probable_user_row = None

        # Derivar email del usuario probable (puede ser None incluso si hay probable_user_row)
        probable_email = None
        probable_user_id = None
        if probable_user_row:
            try:
                probable_email = (probable_user_row[0] or "").strip().lower() or None
            except Exception:
                probable_email = None
            try:
                probable_user_id = int(probable_user_row[1])
            except Exception:
                probable_user_id = None

        # 4. Intentar cross-match tecnicos.email vs usuarios.email
        id_tecnico = None
        if probable_email:
            try:
                cur.execute(
                    "SELECT id_tecnico FROM tecnicos WHERE LOWER(COALESCE(email,'')) = %s ORDER BY id_tecnico ASC",
                    (probable_email,),
                )
                row = cur.fetchone()
                if row:
                    id_tecnico = int(row[0])
            except Exception:
                id_tecnico = None

        # 5. Si no aparece el técnico, crearlo como entrada mínima para no romper FKs
        if id_tecnico is None:
            try:
                first_parts = tecnico_lookup.split(' ', 1)
                nombre_fallback = first_parts[0] or tecnico_lookup
                apellido_fallback = (first_parts[1] if len(first_parts) > 1 else None) or None
                cur.execute(
                    """
                    INSERT INTO tecnicos (nombre, apellido, email, activo)
                    VALUES (%s, %s, %s, TRUE)
                    ON CONFLICT DO NOTHING
                    RETURNING id_tecnico
                    """,
                    (nombre_fallback, apellido_fallback, probable_email or user_email or None),
                )
                row = cur.fetchone()
                if row:
                    id_tecnico = int(row[0])
                else:
                    cur.execute(
                        """
                        SELECT id_tecnico
                        FROM tecnicos
                        WHERE LOWER(COALESCE(email,'')) = COALESCE(%s, '')
                        ORDER BY id_tecnico ASC
                        LIMIT 1
                        """,
                        (probable_email or user_email or '',),
                    )
                    row = cur.fetchone()
                    if row:
                        id_tecnico = int(row[0])
                    else:
                        cur.execute(
                            """
                            SELECT id_tecnico
                            FROM tecnicos
                            WHERE (TRIM(COALESCE(nombre,'')) || ' ' || TRIM(COALESCE(apellido,''))) = %s
                            ORDER BY id_tecnico ASC
                            LIMIT 1
                            """,
                            (tecnico_lookup,),
                        )
                        row = cur.fetchone()
                        if row:
                            id_tecnico = int(row[0])
            except Exception:
                id_tecnico = None
        return id_tecnico
    finally:
        try:
            cur.close()
        except Exception:
            pass


def _resolve_single_entity_id(conn, sql, params, entity_name, required=True):
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
        if not rows:
            if required:
                raise ValueError(f"No se encontró {entity_name} con los parámetros indicados.")
            return None
        # Si hay múltiples filas (ej: misma descripción en modalidades con hidden=True/False),
        # tomar la primera; nunca acceder con [0] sobre None.
        row = rows[0]
        if row is None or row[0] is None:
            if required:
                raise ValueError(f"No se pudo obtener id para {entity_name}.")
            return None
        return row[0]
    finally:
        try:
            cur.close()
        except Exception:
            pass


def save_new_user_record(user_id, fecha, tecnico, cliente, tipo, modalidad, tarea, ticket, tiempo, descripcion, mes, grupo="General", es_hora_extra=False):
    """Guarda un nuevo registro de usuario con validación de duplicados"""
    try:
        conn = get_connection()
        c = conn.cursor()
        
        # Obtener IDs de las entidades (manejo robusto a None/duplicados)
        id_tecnico = _resolve_id_tecnico_for_record(conn, tecnico, user_id)
        if id_tecnico is None:
            st.error("No se pudo asociar el registro a un técnico válido. Verifica el usuario en la base.")
            return

        id_cliente = _resolve_single_entity_id(
            conn,
            "SELECT id_cliente FROM clientes WHERE nombre = %s",
            (cliente,),
            "cliente",
            required=True,
        )

        id_tipo = _resolve_single_entity_id(
            conn,
            "SELECT id_tipo FROM tipos_tarea WHERE descripcion = %s",
            (tipo,),
            "tipo de tarea",
            required=True,
        )

        id_modalidad = _resolve_single_entity_id(
            conn,
            "SELECT id_modalidad FROM modalidades_tarea WHERE descripcion = %s",
            (modalidad,),
            "modalidad de tarea",
            required=True,
        )
        
        # Usar la función centralizada para verificar duplicados
        from .database import check_record_duplicate
        # Normalizar tiempo a 2 decimales para consistencia y chequeo de duplicados
        tiempo = normalize_registro_tiempo(tiempo)
        if tiempo > 24:
            st.error("Un registro no puede superar 24 horas.")
            return
        # Verificar duplicado con tiempo normalizado
        if check_record_duplicate(fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, tiempo):
            st.warning("Ya existe un registro con los mismos datos y tiempo.")
            return
        total_horas_dia = get_total_hours_for_tecnico_on_date(conn, id_tecnico, fecha)
        if total_horas_dia + tiempo > 24:
            st.error(f"No se puede guardar. Total del día: {total_horas_dia}h + {tiempo}h supera 24h.")
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
            clear_chart_cache() # Limpiar también el caché del gráfico
        except:
            pass
            
        show_success_message("✅ Registro creado exitosamente.", 1)
        
        # Incrementar sufijo para resetear los widgets dinámicos en la próxima carga
        current_suffix = 0
        if "form_key_suffix" in st.session_state:
            current_suffix = st.session_state.form_key_suffix
            st.session_state.form_key_suffix += 1
            
        # Limpiar explícitamente las claves de estado de sesión relacionadas con el formulario
        keys_to_clear = [
            f"new_grupo_{current_suffix}", f"new_fecha_{current_suffix}", f"new_cliente_{current_suffix}", f"new_tipo_{current_suffix}", 
            f"new_modalidad_{current_suffix}", f"new_tarea_{current_suffix}", f"new_ticket_{current_suffix}", 
            f"new_tiempo_{current_suffix}", f"new_descripcion_{current_suffix}", f"new_hora_extra_{current_suffix}"
        ]
        
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        # Forzar limpieza adicional de los selectbox reseteando sus keys en el próximo renderizado
        # Al incrementar el suffix, las keys de los inputs de texto cambian automáticamente.
        # Para los selectbox (que no tenían suffix en sus keys antes), ahora debemos asegurarnos
        # de que se reinicialicen. Una forma es eliminar sus valores del session state.
        
        # Limpiar el formulario reiniciando la página
        safe_rerun()
        
    except Exception as e:
        st.error(f"Error al guardar el registro: {str(e)}")
    finally:
        conn.close()

def render_user_edit_record_form(registro_seleccionado, registro_id, nombre_completo_usuario):
    """Renderiza el formulario de edición de registros para usuarios"""
    # Formulario para editar el registro
    fecha_val = registro_seleccionado['fecha']
    
    fecha_parsed = parse_registro_datetime(fecha_val)
    fecha_value = fecha_parsed.date() if pd.notna(fecha_parsed) else datetime.today().date()
    
    min_registro_date = datetime(2024, 1, 1).date()
    max_registro_date = (datetime.today() + timedelta(days=366)).date()
    fecha_edit = st.date_input(
        "Fecha *",
        value=fecha_value,
        min_value=min_registro_date,
        max_value=max_registro_date,
        key="edit_fecha"
    )
    # Pasamos el objeto date directamente, la base de datos lo manejará mejor que un string
    
    # Obtener listas de técnicos, clientes, tipos y modalidades
    tecnicos_df = get_tecnicos_dataframe()
    clientes_df = get_clientes_dataframe()
    tipos_df = get_tipos_dataframe()
    modalidades_df = get_modalidades_dataframe()
    
    # Obtener el rol del usuario para los grupos (desambiguando duplicados por email de sesión)
    conn = get_connection()
    c = conn.cursor()
    session_user_id_for_edit = int(st.session_state.get("user_id")) if st.session_state.get("user_id") is not None else None
    session_email = None
    if session_user_id_for_edit:
        try:
            c.execute(
                "SELECT COALESCE(email,'') FROM usuarios WHERE id = %s",
                (session_user_id_for_edit,),
            )
            row = c.fetchone()
            if row and row[0]:
                session_email = (row[0] or "").strip().lower()
        except Exception:
            session_email = None

    c.execute(
        """
        SELECT COALESCE(email,''), id, rol_id,
               TRIM(COALESCE(nombre,'') || ' ' || COALESCE(apellido,''))
        FROM usuarios
        WHERE TRIM(COALESCE(nombre,'') || ' ' || COALESCE(apellido,'')) = %s
        """,
        (nombre_completo_usuario,),
    )
    user_rows = c.fetchall() or []
    conn.close()
    if not user_rows:
        user_data = None
    elif len(user_rows) == 1:
        user_data = user_rows[0][:2]
    else:
        fallback_id = None
        try:
            fallback_id = int(session_user_id_for_edit)
        except Exception:
            fallback_id = None
        matched_by_id = []
        matched_by_email = []
        if fallback_id is not None:
            matched_by_id = [r for r in user_rows if int(r[1]) == fallback_id]
        if matched_by_id:
            user_data = matched_by_id[0][:2]
        else:
            if session_email:
                matched_by_email = [
                    r for r in user_rows if (r[0] or "").strip().lower() == session_email
                ]
            if len(matched_by_email) == 1:
                user_data = matched_by_email[0][:2]
            elif len(matched_by_email) > 1:
                user_data = matched_by_email[0][:2]
            else:
                user_data = user_rows[0][:2]
    
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
    grupo_selected_edit = st.selectbox("Sector *", options=grupo_names, index=grupo_index, key="edit_grupo")
    
    # Selección de cliente
    cliente_rows_edit = [
        (
            int(row["id_cliente"]),
            str(row["nombre"]).strip(),
            (str(row.get("alias") or "").strip() if pd.notna(row.get("alias")) else "")
        )
        for _, row in clientes_df.iterrows()
        if pd.notna(row.get("id_cliente")) and str(row.get("nombre") or "").strip()
    ]
    cliente_ids_edit = [cid for cid, _, _ in cliente_rows_edit]
    cliente_real_by_id_edit = {cid: cname for cid, cname, _ in cliente_rows_edit}
    cliente_display_by_id_edit = {cid: (alias if alias else cname) for cid, cname, alias in cliente_rows_edit}
    cliente_index = 0
    for idx, cid in enumerate(cliente_ids_edit):
        if cliente_real_by_id_edit.get(cid) == registro_seleccionado['cliente']:
            cliente_index = idx
            break
    cliente_selected_id_edit = st.selectbox(
        "Cliente *",
        options=cliente_ids_edit,
        index=cliente_index if cliente_ids_edit else None,
        format_func=lambda cid: cliente_display_by_id_edit[cid],
        key="edit_cliente"
    )
    cliente_selected_edit = cliente_real_by_id_edit.get(cliente_selected_id_edit, registro_seleccionado['cliente'])
    
    # Selección de tipo de tarea
    tipo_options = tipos_df['descripcion'].tolist()
    tipo_index = tipo_options.index(registro_seleccionado['tipo_tarea']) if registro_seleccionado['tipo_tarea'] in tipo_options else 0
    tipo_selected_edit = st.selectbox("Tipo de Tarea *", options=tipo_options, index=tipo_index, key="edit_tipo")
    
    # Selección de modalidad
    modalidad_options = modalidades_df['descripcion'].tolist()
    # Asegurar que Cliente esté disponible
    if 'Cliente' not in modalidad_options:
        modalidad_options.append('Cliente')
    modalidad_index = modalidad_options.index(registro_seleccionado['modalidad']) if registro_seleccionado['modalidad'] in modalidad_options else 0
    modalidad_selected_edit = st.selectbox("Modalidad *", options=modalidad_options, index=modalidad_index, key="edit_modalidad")
    
    # Campos adicionales
    tarea_realizada_edit = st.text_input("Tarea Realizada *", value=registro_seleccionado['tarea_realizada'], key="edit_tarea", max_chars=100)
    numero_ticket_edit = st.text_input("Número de Ticket", value=registro_seleccionado['numero_ticket'], key="edit_ticket", max_chars=20)
    tiempo_edit = st.number_input("Tiempo (horas) *", min_value=0.5, step=0.5, value=float(registro_seleccionado['tiempo']), key="edit_tiempo")
    descripcion_edit = st.text_area("Descripción", value=registro_seleccionado['descripcion'] if pd.notna(registro_seleccionado['descripcion']) else "", key="edit_descripcion", max_chars=250)
    
    # Checkbox de Hora Extra
    es_hora_extra_edit = st.checkbox("Hora extra", value=bool(registro_seleccionado.get('es_hora_extra', False)), key="edit_hora_extra")
    
    # Mes (automático basado en la fecha)
    mes_edit = month_name_es(fecha_edit.month)
    
    if st.button("Guardar Cambios", key="save_registro_edit"):
        ok, msg = validate_new_record_inputs(
            cliente_selected_edit, tipo_selected_edit, modalidad_selected_edit,
            tarea_realizada_edit, tiempo_edit, fecha=fecha_edit
        )
        if not ok:
            st.error(msg)
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

    c.execute("SELECT usuario_id FROM registros WHERE id = %s", (registro_id,))
    row_actual = c.fetchone()
    old_usuario_id = int(row_actual[0]) if row_actual and row_actual[0] is not None else None
    fallback_user = old_usuario_id if old_usuario_id is not None else (
        int(st.session_state.get("user_id")) if st.session_state.get("user_id") is not None else None
    )
    
    # Obtener IDs (manejo robusto a None/duplicados)
    id_tecnico = _resolve_id_tecnico_for_record(conn, tecnico, fallback_user)
    if id_tecnico is None:
        st.error("No se pudo asociar el registro a un técnico válido. Verifica el usuario en la base.")
        conn.close()
        return
    
    id_cliente = _resolve_single_entity_id(
        conn,
        "SELECT id_cliente FROM clientes WHERE nombre = %s",
        (cliente,),
        "cliente",
        required=True,
    )

    id_tipo = _resolve_single_entity_id(
        conn,
        "SELECT id_tipo FROM tipos_tarea WHERE descripcion = %s",
        (tipo,),
        "tipo de tarea",
        required=True,
    )

    id_modalidad = _resolve_single_entity_id(
        conn,
        "SELECT id_modalidad FROM modalidades_tarea WHERE descripcion = %s",
        (modalidad,),
        "modalidad de tarea",
        required=True,
    )
    # Normalizar tiempo a 2 decimales para consistencia y chequeo de duplicados
    tiempo = normalize_registro_tiempo(tiempo)
    if tiempo > 24:
        st.error("Un registro no puede superar 24 horas.")
        conn.close()
        return
    total_horas_dia = get_total_hours_for_tecnico_on_date(conn, id_tecnico, fecha, exclude_registro_id=registro_id)
    if total_horas_dia + tiempo > 24:
        st.error(f"No se puede guardar. Total del día: {total_horas_dia}h + {tiempo}h supera 24h.")
        conn.close()
        return
    
    # Verificar si ya existe un registro con los mismos datos
    # Aseguramos que la fecha se pase como string ISO (YYYY-MM-DD) para evitar ambigüedades
    fecha_str = fecha.strftime('%Y-%m-%d') if hasattr(fecha, 'strftime') else str(fecha)
    
    c.execute('''
        SELECT COUNT(*) FROM registros 
        WHERE fecha::date = %s::date AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s 
        AND id_modalidad = %s AND tarea_realizada = %s AND tiempo = %s AND id != %s
    ''', (fecha_str, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, tiempo, registro_id))
    
    duplicate_count = c.fetchone()[0]
    if duplicate_count > 0:
        st.error("Ya existe un registro con estos mismos datos. No se puede crear un duplicado.")
    else:
        c.execute(
            '''
            SELECT u.id, COALESCE(u.email, ''), u.rol_id
            FROM usuarios u
            WHERE TRIM(u.nombre || ' ' || u.apellido) = %s
            ''',
            (tecnico,)
        )
        tecnico_rows = c.fetchall() or []
        if not tecnico_rows:
            tecnico_user = None
            registro_usuario_id = old_usuario_id
        else:
            session_email_edit = None
            try:
                suid = st.session_state.get("user_id")
                if suid is not None:
                    c.execute("SELECT COALESCE(email,'') FROM usuarios WHERE id = %s", (int(suid),))
                    row_se = c.fetchone()
                    if row_se and row_se[0]:
                        session_email_edit = (row_se[0] or "").strip().lower()
            except Exception:
                session_email_edit = None

            if len(tecnico_rows) == 1:
                tecnico_user = tecnico_rows[0]
            else:
                # Desambiguación: 1) por ID del técnico viejo (más probable en edición),
                # 2) por ID de la sesión (usuario que está editando), 3) por email, 4) fallback.
                fallback_tecnico_id = None
                try:
                    fallback_tecnico_id = int(fallback_user)
                except Exception:
                    fallback_tecnico_id = None
                session_id_edit = None
                try:
                    session_id_edit = int(st.session_state.get("user_id"))
                except Exception:
                    session_id_edit = None

                matched_by_old = []
                matched_by_sid = []
                matched_by_email = []

                if fallback_tecnico_id is not None:
                    matched_by_old = [r for r in tecnico_rows if int(r[0]) == fallback_tecnico_id]
                if matched_by_old:
                    tecnico_user = matched_by_old[0]
                else:
                    if session_id_edit is not None:
                        matched_by_sid = [r for r in tecnico_rows if int(r[0]) == session_id_edit]
                    if matched_by_sid:
                        tecnico_user = matched_by_sid[0]
                    else:
                        if session_email_edit:
                            matched_by_email = [
                                r for r in tecnico_rows if (r[1] or "").strip().lower() == session_email_edit
                            ]
                        if len(matched_by_email) == 1:
                            tecnico_user = matched_by_email[0]
                        elif len(matched_by_email) > 1:
                            tecnico_user = matched_by_email[0]
                        else:
                            tecnico_user = tecnico_rows[0]
            registro_usuario_id = int(tecnico_user[0]) if tecnico_user and tecnico_user[0] is not None else old_usuario_id

        # Actualizar registro
        c.execute('''
            UPDATE registros SET 
            fecha = %s, id_tecnico = %s, id_cliente = %s, id_tipo = %s, id_modalidad = %s, 
            tarea_realizada = %s, numero_ticket = %s, tiempo = %s, descripcion = %s, mes = %s, usuario_id = %s, grupo = %s, es_hora_extra = %s
            WHERE id = %s
        ''', (fecha_str, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, ticket, tiempo, descripcion, mes, registro_usuario_id, grupo, es_hora_extra, registro_id))
        
        conn.commit()
        
        # Registrar la actividad de edición
        from .database import registrar_edicion
        usuario_id = st.session_state.user_id
        username = st.session_state.username
        detalles = f"ID: {registro_id}, Cliente: {cliente}, Tarea: {tarea}, Tiempo: {tiempo}h"
        registrar_edicion(usuario_id, username, "registro de horas", detalles)
        
        # Limpiar caché de registros y gráficos para que se actualice la vista
        try:
            from .database import clear_user_registros_cache
            if old_usuario_id is not None:
                clear_user_registros_cache(old_usuario_id)
            if registro_usuario_id is not None and registro_usuario_id != old_usuario_id:
                clear_user_registros_cache(registro_usuario_id)
            clear_user_registros_cache(usuario_id)
            clear_chart_cache()
        except Exception as e:
            # print(f"Error limpiando caché: {e}")
            pass
        
        show_success_message("✅ Registro actualizado exitosamente. Se ha verificado que no existen duplicados.", 1)
        conn.close()
        safe_rerun()
    
    # Si no hubo éxito (por duplicado), cerramos aquí si no se cerró antes
    try:
        conn.close()
    except:
        pass

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
    st.markdown(
        """
        <style>
        .user-week-label {
            text-align: center;
            margin: 0;
            padding: 6px;
            font-weight: 600;
            white-space: nowrap;
        }
        @media (max-width: 768px) {
            .user-week-label {
                white-space: normal;
                line-height: 1.25;
                font-size: 0.95rem;
            }
            .office-card {
                padding: 12px !important;
            }
            .office-card-title {
                font-size: 1.35rem !important;
                line-height: 1.2 !important;
            }
            .office-chip {
                font-size: 0.9rem !important;
                padding: 6px 10px !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    
    rol_id = get_user_rol_id(user_id)
    role_ids_for_view = [int(rol_id)] if rol_id is not None else []
    try:
        import unicodedata
        import re
        from .database import get_roles_dataframe
        roles_all_df = get_roles_dataframe(
            exclude_admin=True,
            exclude_sin_rol=True,
            exclude_hidden=False
        )
        if not roles_all_df.empty and rol_id is not None:
            role_row = roles_all_df[roles_all_df["id_rol"] == int(rol_id)]
            if not role_row.empty:
                base_name = str(role_row.iloc[0]["nombre"])
                base_norm = unicodedata.normalize("NFD", base_name.lower())
                base_norm = "".join(ch for ch in base_norm if unicodedata.category(ch) != "Mn")
                base_norm = re.sub(r"[\s\-]+", "_", base_norm).strip("_")
                if "tecnic" in base_norm:
                    for _, rr in roles_all_df.iterrows():
                        rr_name = str(rr.get("nombre") or "")
                        rr_norm = unicodedata.normalize("NFD", rr_name.lower())
                        rr_norm = "".join(ch for ch in rr_norm if unicodedata.category(ch) != "Mn")
                        rr_norm = re.sub(r"[\s\-]+", "_", rr_norm).strip("_")
                        is_admin_tech = (
                            ("tecnic" in rr_norm) and (
                                rr_norm.startswith("adm_")
                                or rr_norm.startswith("admin_")
                                or ("administr" in rr_norm)
                            )
                        )
                        if is_admin_tech:
                            role_ids_for_view.append(int(rr["id_rol"]))
    except Exception:
        pass
    role_ids_for_view = sorted(set(int(x) for x in role_ids_for_view))

    modalidades_df = get_modalidades_dataframe()
    modalidad_options = modalidades_df[['id_modalidad', 'descripcion']].values.tolist()
    desc_by_id = {int(row['id_modalidad']): str(row['descripcion']) for _, row in modalidades_df.iterrows()}

    # Banner superior: quién está hoy (Presencial o Cliente: Systemscorp) en tu departamento
    try:
        from .utils import normalize_name
        today = datetime.today().date()
        today_frames = []
        peers_frames = []
        for rid in role_ids_for_view:
            rdf = get_weekly_modalities_by_rol(int(rid), today, today)
            if not rdf.empty:
                today_frames.append(rdf)
            udf = get_users_by_rol(int(rid), exclude_hidden=False).copy()
            if not udf.empty:
                peers_frames.append(udf)
        today_df = pd.concat(today_frames).drop_duplicates(subset=["user_id", "fecha"], keep="last").reset_index(drop=True) if today_frames else pd.DataFrame()
        peers_df_names = pd.concat(peers_frames).drop_duplicates(subset=["id"]).reset_index(drop=True) if peers_frames else pd.DataFrame()
        if "nombre_completo" not in peers_df_names.columns:
            peers_df_names["nombre_completo"] = peers_df_names.apply(
                lambda r: f"{r.get('nombre','')} {r.get('apellido','')}".strip(), axis=1
            )
        name_by_uid = {int(r["id"]): r["nombre_completo"] for _, r in peers_df_names.iterrows()}

        presentes = []
        for _, r in today_df.iterrows():
            uid = int(r.get("user_id"))
            modalidad = str(r.get("modalidad") or "").strip().lower()
            cliente_nombre = str(r.get("cliente_nombre") or "").strip()
            cliente_norm = normalize_name(cliente_nombre)
            es_systemscorp = "SYSTEMSCORP" in cliente_norm
            if modalidad == "presencial" or (modalidad == "cliente" and es_systemscorp):
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
    try:
        from .database import sync_user_schedule_roles_for_range
        sync_user_schedule_roles_for_range(start_date, end_date)
    except Exception:
        pass
    week_range_str = format_week_range(start_of_week, end_of_week)

    is_current_week = st.session_state.user_week_offset == 0
    week_indicator = " 📍 (Semana Actual)" if is_current_week else ""

    nav_cols = st.columns([0.25, 0.5, 0.25])
    with nav_cols[0]:
        if st.button("⬅️", key="user_week_prev", use_container_width=True):
            st.session_state.user_week_offset -= 1
            safe_rerun()
    with nav_cols[1]:
        center_row = st.columns([0.03, 0.94, 0.03])
        with center_row[1]:
            text_and_home = st.columns([0.86, 0.14])
            with text_and_home[0]:
                st.markdown(
                    f"<p class='user-week-label'>Semana: {week_range_str}{week_indicator}</p>",
                    unsafe_allow_html=True
                )
            with text_and_home[1]:
                if not is_current_week:
                    if st.button("🏠", key="user_week_home", help="Volver a la semana actual", use_container_width=True):
                        st.session_state.user_week_offset = 0
                        safe_rerun()
                else:
                    st.empty()
    with nav_cols[2]:
        if st.button("➡️", key="user_week_next", use_container_width=True):
            st.session_state.user_week_offset += 1
            safe_rerun()

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
    cliente_display_by_id = {}
    for _, row in clientes_df.iterrows():
        try:
            cid = int(row["id_cliente"])
        except Exception:
            continue
        nombre = str(row.get("nombre") or "").strip()
        alias = str(row.get("alias") or "").strip() if pd.notna(row.get("alias")) else ""
        if not nombre:
            continue
        cliente_display_by_id[cid] = alias if alias else nombre

    # Editor: solo los días del propio usuario
    st.markdown("Selecciona tu modalidad por día:")
    editor_cols = st.columns(5)
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

        with editor_cols[i]:
            day_name_es = day_mapping.get(day.strftime("%A"), day.strftime("%A"))
            st.write(day_name_es)
            st.caption(day.strftime("%d/%m"))
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
                    client_key = f"user_client_{user_id}_{day.isoformat()}"
                    if client_key not in st.session_state:
                        st.session_state[client_key] = default_client_id if default_client_id in client_ids else None
                    selected_client = st.selectbox(
                        "Cliente",
                        options=client_ids,
                        format_func=lambda cid: cliente_display_by_id.get(cid, next(name for cid2, name in cliente_options if cid2 == cid)),
                        index=None,
                        key=client_key,
                        placeholder="Selecciona cliente",
                        label_visibility="collapsed"
                    )
                    selected_client_by_day[day] = selected_client

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
    checkbox_key = f"user_apply_default_from_week_{user_id}"
    checkbox_reset_key = f"user_apply_default_reset_{user_id}"
    if st.session_state.get(checkbox_reset_key, False):
        st.session_state[checkbox_key] = False
        st.session_state[checkbox_reset_key] = False
    apply_to_default = st.checkbox(
        "Actualizar también mi cronograma habitual",
        value=False,
        key=checkbox_key,
        help="Al guardar, copia esta semana como cronograma por defecto. Se omiten automáticamente días con feriado/licencia/vacaciones."
    )

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
                updated_defaults = 0
                skipped_defaults = 0
                updated_future = 0
                if apply_to_default:
                    try:
                        import unicodedata

                        def _norm_desc(txt):
                            t = str(txt or "").strip().lower()
                            t = unicodedata.normalize("NFD", t)
                            t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
                            return " ".join(t.split())

                        licencia_mod_ids = set()
                        modalidades_all_df = get_modalidades_dataframe(exclude_hidden=False)
                        for _, mrow in modalidades_all_df.iterrows():
                            mid = mrow.get("id_modalidad")
                            if pd.isna(mid):
                                continue
                            desc_norm = _norm_desc(mrow.get("descripcion"))
                            if ("vacaciones" in desc_norm) or ("licencia" in desc_norm) or ("cumpleanos" in desc_norm):
                                licencia_mod_ids.add(int(mid))

                        vacation_days = set()
                        try:
                            vac_df = get_vacaciones_by_users_and_range([int(user_id)], start_date, end_date)
                            for _, vac_row in vac_df.iterrows():
                                try:
                                    vac_start = pd.to_datetime(vac_row["fecha_inicio"]).date()
                                    vac_end = pd.to_datetime(vac_row["fecha_fin"]).date()
                                    current_day = max(vac_start, start_date)
                                    last_day = min(vac_end, end_date)
                                    while current_day <= last_day:
                                        if current_day.weekday() < 5:
                                            vacation_days.add(current_day)
                                        current_day += timedelta(days=1)
                                except Exception:
                                    continue
                        except Exception:
                            vacation_days = set()

                        old_default_by_dow = dict(default_by_dow)
                        selected_by_dow = {}
                        selected_client_by_dow = {}
                        for day in week_dates:
                            selected_by_dow[int(day.weekday())] = int(selected_by_day.get(day)) if selected_by_day.get(day) is not None else None
                            selected_client_by_dow[int(day.weekday())] = selected_client_by_day.get(day)

                        for day in week_dates:
                            day_key = day.date() if hasattr(day, "date") else day
                            mod_id = selected_by_day.get(day)
                            if mod_id is None:
                                skipped_defaults += 1
                                continue
                            mod_desc_norm = _norm_desc(desc_by_id.get(mod_id, ""))
                            if day_key in feriados_set:
                                skipped_defaults += 1
                                continue
                            if day_key in vacation_days:
                                skipped_defaults += 1
                                continue
                            if (int(mod_id) in licencia_mod_ids) or ("feriado" in mod_desc_norm):
                                skipped_defaults += 1
                                continue

                            es_cliente = desc_by_id.get(mod_id, "").strip().lower() == "cliente"
                            cliente_id = selected_client_by_day.get(day) if es_cliente else None
                            upsert_user_default_schedule(int(user_id), int(day.weekday()), int(mod_id), cliente_id)
                            updated_defaults += 1

                        future_start = start_date + timedelta(days=7)
                        future_end = future_start + timedelta(days=7 * 12 - 1)
                        future_sched_df = get_user_weekly_modalities(int(user_id), future_start, future_end)
                        existing_by_date = {}
                        for _, ex_row in future_sched_df.iterrows():
                            try:
                                ex_date = pd.to_datetime(ex_row["fecha"]).date()
                                ex_mod = int(ex_row["modalidad_id"])
                                existing_by_date[ex_date] = ex_mod
                            except Exception:
                                continue

                        future_vac_days = set()
                        try:
                            vac_future_df = get_vacaciones_by_users_and_range([int(user_id)], future_start, future_end)
                            for _, vac_row in vac_future_df.iterrows():
                                try:
                                    vac_start = pd.to_datetime(vac_row["fecha_inicio"]).date()
                                    vac_end = pd.to_datetime(vac_row["fecha_fin"]).date()
                                    cur_day = max(vac_start, future_start)
                                    last_day = min(vac_end, future_end)
                                    while cur_day <= last_day:
                                        if cur_day.weekday() < 5:
                                            future_vac_days.add(cur_day)
                                        cur_day += timedelta(days=1)
                                except Exception:
                                    continue
                        except Exception:
                            future_vac_days = set()

                        cursor_day = future_start
                        while cursor_day <= future_end:
                            if cursor_day.weekday() >= 5:
                                cursor_day += timedelta(days=1)
                                continue
                            if is_feriado(cursor_day):
                                cursor_day += timedelta(days=1)
                                continue
                            if cursor_day in future_vac_days:
                                cursor_day += timedelta(days=1)
                                continue

                            dow = int(cursor_day.weekday())
                            new_mod_id = selected_by_dow.get(dow)
                            if new_mod_id is None:
                                cursor_day += timedelta(days=1)
                                continue

                            existing_mod = existing_by_date.get(cursor_day)
                            old_pair = old_default_by_dow.get(dow)

                            if existing_mod is not None:
                                if existing_mod in licencia_mod_ids:
                                    cursor_day += timedelta(days=1)
                                    continue
                                if old_pair is None or int(existing_mod) != int(old_pair[0]):
                                    cursor_day += timedelta(days=1)
                                    continue

                            is_cliente_mod = desc_by_id.get(new_mod_id, "").strip().lower() == "cliente"
                            new_cliente_id = selected_client_by_dow.get(dow) if is_cliente_mod else None
                            upsert_user_modality_for_date(int(user_id), int(rol_id), cursor_day, int(new_mod_id), new_cliente_id)
                            updated_future += 1
                            cursor_day += timedelta(days=1)

                        try:
                            cached_get_user_default_schedule.clear()
                        except Exception:
                            pass
                    except Exception as default_error:
                        st.warning(f"La planificación semanal se guardó, pero no se pudo actualizar el cronograma habitual: {default_error}")

                if apply_to_default:
                    st.success(f"Planificación guardada correctamente. Cronograma habitual actualizado en {updated_defaults} día(s) hábil(es), omitido en {skipped_defaults} por feriados/licencias/vacaciones y propagado a {updated_future} asignación(es) futura(s).")
                else:
                    st.success("Planificación guardada correctamente.")
                try:
                    cached_get_weekly_modalities_by_rol.clear()
                except Exception:
                    pass
                st.session_state[checkbox_reset_key] = True
                safe_rerun()
            else:
                st.error("Se encontraron errores al guardar:")
                for e in errores:
                    st.error(f"- {e}")
        except Exception as e:
            st.error(f"Error general al guardar: {str(e)}")

    # Vista del equipo (solo lectura, mismo departamento)
    peers_frames = []
    for rid in role_ids_for_view:
        udf = get_users_by_rol(int(rid), exclude_hidden=False).copy()
        if not udf.empty:
            peers_frames.append(udf)
    peers_df = pd.concat(peers_frames).drop_duplicates(subset=["id"]).reset_index(drop=True) if peers_frames else pd.DataFrame()
    
    # Modalidades actuales del usuario - usar objetos date consistentes
    user_sched_df = get_user_weekly_modalities(user_id, start_date, end_date)
    user_sched_map = {}
    for _, row in user_sched_df.iterrows():
        fecha_obj = pd.to_datetime(row['fecha']).date()
        user_sched_map[fecha_obj] = int(row['modalidad_id'])
    
    # Modalidades de todos en el rol para mostrar
    sched_frames = []
    for rid in role_ids_for_view:
        rdf = get_weekly_modalities_by_rol(int(rid), start_date, end_date)
        if not rdf.empty:
            sched_frames.append(rdf)
    rol_sched_df = pd.concat(sched_frames).drop_duplicates(subset=["user_id", "fecha"], keep="last").reset_index(drop=True) if sched_frames else pd.DataFrame()
    
    # Clientes y conjunto de nombres (para etiquetar y colorear como en Admin)
    clientes_df = get_clientes_dataframe()
    cliente_options = [(int(row["id_cliente"]), row["nombre"]) for _, row in clientes_df.iterrows()]
    cliente_nombres = {str(name).strip() for _, name in cliente_options}
    cliente_name_by_id = {int(cid): str(name).strip() for cid, name in cliente_options}
    cliente_alias_by_id = {}
    cliente_alias_by_name = {}
    cliente_alias_nombres = set()
    cliente_canonical_by_display = {}
    for _, row in clientes_df.iterrows():
        try:
            cid = int(row["id_cliente"])
        except Exception:
            continue
        nombre = str(row.get("nombre") or "").strip()
        alias = str(row.get("alias") or "").strip() if pd.notna(row.get("alias")) else ""
        if nombre:
            cliente_canonical_by_display[nombre.casefold()] = nombre
        if alias:
            cliente_alias_by_id[cid] = alias
            cliente_alias_nombres.add(alias)
            cliente_canonical_by_display[alias.casefold()] = nombre or alias
            if nombre:
                cliente_alias_by_name[nombre.casefold()] = alias
    
    # Mapa (user_id, fecha) -> display, reemplazando "Cliente" por nombre real
    rol_map = {}
    for _, row in rol_sched_df.iterrows():
        fecha_obj = pd.to_datetime(row["fecha"]).date()
        display_val = row["modalidad"]
        try:
            if isinstance(display_val, str) and display_val.strip().lower() == "cliente":
                cliente_id = int(row["cliente_id"]) if ("cliente_id" in row and pd.notna(row["cliente_id"])) else None
                cliente_nombre = row.get("cliente_nombre")
                if cliente_id is not None and cliente_id in cliente_alias_by_id:
                    display_val = cliente_alias_by_id[cliente_id]
                elif cliente_nombre and str(cliente_nombre).strip():
                    # Mostrar SOLO el nombre del cliente (sin "Cliente - ")
                    cliente_nombre = str(cliente_nombre).strip()
                    display_val = cliente_alias_by_name.get(cliente_nombre.casefold(), cliente_nombre)
                else:
                    display_val = "Cliente"
        except Exception:
            pass
        rol_map[(int(row["user_id"]), fecha_obj)] = display_val
    
    defaults_by_user = {}
    for _, peer in peers_df.iterrows():
        try:
            uid = int(peer["id"])
        except Exception:
            continue
        dmap = {}
        try:
            df_def = cached_get_user_default_schedule(uid)
            for _, r in df_def.iterrows():
                try:
                    dow = int(r.get("day_of_week"))
                except Exception:
                    continue
                try:
                    mod_id = int(r.get("modalidad_id"))
                except Exception:
                    continue
                cli_id = None
                try:
                    if pd.notna(r.get("cliente_id")):
                        cli_id = int(r.get("cliente_id"))
                except Exception:
                    cli_id = None
                dmap[dow] = (mod_id, cli_id)
        except Exception:
            dmap = {}
        defaults_by_user[uid] = dmap

    matriz = []
    for _, peer in peers_df.iterrows():
        peer_id = int(peer["id"])
        peer_name = peer["nombre_completo"]
        fila = [peer_name]
    
        asignadas_count = 0
        for day in week_dates:
            modalidad = rol_map.get((peer_id, day))
            if modalidad is None:
                pair = defaults_by_user.get(peer_id, {}).get(day.weekday())
                if pair:
                    mod_desc = str(desc_by_id.get(pair[0], "Sin asignar")).strip()
                    if mod_desc.lower() == "cliente" and pair[1] is not None:
                        modalidad = str(cliente_alias_by_id.get(pair[1], cliente_name_by_id.get(pair[1], f"Cliente ID {pair[1]}"))).strip()
                    else:
                        modalidad = mod_desc
                else:
                    modalidad = "Sin asignar"
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
            try:
                from .utils import normalize_name
                base = client_norm if is_cliente_prefixed else val_str
                nm = normalize_name(base).lower()
            except Exception:
                nm = ""
            if ("systemscorp" in nm) or (val_norm == "presencial"):
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
    
        def modality_bg_class(val):
            val_str = str(val).strip() if val is not None else ""
            val_norm = val_str.lower()
            is_cliente_prefixed = val_norm.startswith("cliente - ")
            client_norm = val_norm.split(" - ", 1)[1].strip() if is_cliente_prefixed else None
            base_display = client_norm if is_cliente_prefixed else val_str
            canonical_display = cliente_canonical_by_display.get(base_display.casefold(), base_display)
            is_cliente_name = (val_str in cliente_nombres) or (val_str in cliente_alias_nombres) or (canonical_display.casefold() != base_display.casefold())
            try:
                from .utils import normalize_name
                nm = normalize_name(canonical_display).lower()
            except Exception:
                nm = ""
            if ("systemscorp" in nm) or (val_norm == "presencial"):
                return "bg-green"
            if val_norm in ("remoto", "base en casa"):
                return "bg-blue"
            if val_norm in ("vacaciones", "feriado"):
                return "bg-orange"
            if val_norm == "licencia":
                return "bg-purple"
            if val_norm in ("dia de cumpleaños", "cumpleaños", "día de cumpleaños"):
                return "bg-pink"
            if val_norm == "sin asignar":
                return "bg-none"
            if val_norm == "cliente" or is_cliente_prefixed or is_cliente_name:
                return "bg-violet"
            return "bg-gray"

        from html import escape

        total_columns = len(columnas)
        desktop_user_col_width = 200
        desktop_day_col_width = 240
        mobile_user_col_width = 170
        mobile_day_col_width = 165
        desktop_table_width = desktop_user_col_width + max(0, total_columns - 1) * desktop_day_col_width
        mobile_table_width = max(920, mobile_user_col_width + max(0, total_columns - 1) * mobile_day_col_width)
        desktop_grid_template = f"{desktop_user_col_width}px " + " ".join([f"{desktop_day_col_width}px"] * max(0, total_columns - 1))
        mobile_grid_template = f"{mobile_user_col_width}px " + " ".join([f"{mobile_day_col_width}px"] * max(0, total_columns - 1))

        header_cells = []
        for idx, col in enumerate(columnas):
            header_class = "grid-cell grid-header"
            if idx == 0:
                header_class += " grid-sticky-col"
            header_html = "<br>".join(escape(part) for part in str(col).split("\n"))
            header_cells.append(f'<div class="{header_class}"><div class="cell-content">{header_html}</div></div>')

        body_rows = []
        for fila in matriz:
            row_cells = []
            for idx, cell in enumerate(fila):
                cell_text = "" if cell is None else str(cell)
                title_attr = escape(cell_text, quote=True)
                if idx == 0:
                    cell_class = "grid-cell grid-user grid-sticky-col"
                else:
                    cell_class = f"grid-cell {modality_bg_class(cell_text)}"
                row_cells.append(
                    f'<div class="{cell_class}" title="{title_attr}"><div class="cell-content">{escape(cell_text)}</div></div>'
                )
            body_rows.append(f'<div class="grid-row">{"".join(row_cells)}</div>')

        html = f"""
<div class="table-wrapper" style="width: {desktop_table_width}px; overflow-x: auto;">
  <style>
    .table-wrapper {{
        width: 100% !important;
        max-width: 100%;
        overflow-x: auto;
        position: relative;
        --theme-bg: var(--background-color, #0e1117);
        --theme-text: var(--text-color, #fafafa);
        --sticky-col-bg: var(--background-color, #0e1117);
    }}
    .table-grid {{
        min-width: {desktop_table_width}px;
        width: {desktop_table_width}px;
        border: 1px solid #3a3a3a;
        border-radius: 10px;
        overflow: visible;
        background-color: var(--theme-bg);
    }}
    .grid-row {{
        display: grid;
        grid-template-columns: {desktop_grid_template};
    }}
    .grid-cell {{
        border-right: 1px solid #3a3a3a;
        border-bottom: 1px solid #3a3a3a;
        min-width: 0;
        position: relative;
        overflow: hidden;
        box-sizing: border-box;
    }}
    .grid-row .grid-cell:last-child {{
        border-right: none;
    }}
    .table-grid .grid-row:last-child .grid-cell {{
        border-bottom: none;
    }}
    .grid-header {{
        font-weight: 600;
        background-color: var(--theme-bg);
    }}
    .grid-sticky-col {{
        position: sticky !important;
        left: 0;
        z-index: 30;
        isolation: isolate;
        background: var(--sticky-col-bg) !important;
        background-color: var(--sticky-col-bg) !important;
        box-shadow: 6px 0 0 var(--sticky-col-bg), 1px 0 0 #3a3a3a;
    }}
    .grid-sticky-col::after {{
        content: "";
        position: absolute;
        inset: 0;
        background: var(--sticky-col-bg) !important;
        background-color: var(--sticky-col-bg) !important;
        z-index: 0;
        pointer-events: none;
    }}
    .grid-header.grid-sticky-col {{
        z-index: 31;
    }}
    .grid-user {{
        background: var(--sticky-col-bg) !important;
        background-color: var(--sticky-col-bg) !important;
    }}
    .cell-content {{
        position: relative;
        z-index: 1;
        padding: 8px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        width: 100%;
        display: block;
        color: var(--theme-text);
        opacity: 0.85;
        box-sizing: border-box;
    }}
    .grid-header .cell-content,
    .grid-user .cell-content {{
        font-weight: 600;
        opacity: 1;
        background: var(--sticky-col-bg) !important;
        background-color: var(--sticky-col-bg) !important;
    }}
    .bg-green {{ background-color: #28a745; }}
    .bg-blue {{ background-color: #3399ff; }}
    .bg-orange {{ background-color: #f39c12; }}
    .bg-purple {{ background-color: #9b59b6; }}
    .bg-pink {{ background-color: #e84393; }}
    .bg-violet {{ background-color: #8e44ad; }}
    .bg-gray {{ background-color: #6c757d; }}
    .bg-none {{ background-color: transparent; }}
    @media (max-width: 768px) {{
        .table-wrapper {{
            width: 100% !important;
            -webkit-overflow-scrolling: touch;
        }}
        .table-grid {{
            min-width: {mobile_table_width}px;
            width: {mobile_table_width}px;
        }}
        .grid-row {{
            grid-template-columns: {mobile_grid_template};
        }}
        .grid-sticky-col {{
            box-shadow: 4px 0 0 var(--sticky-col-bg), 1px 0 0 #3a3a3a;
        }}
        .cell-content {{
            padding: 6px;
            font-size: 0.82rem;
        }}
        .grid-header .cell-content {{
            font-size: 0.9rem;
            line-height: 1.15;
        }}
    }}
  </style>
  <div class="table-grid">
    <div class="grid-row">{"".join(header_cells)}</div>
    {"".join(body_rows)}
  </div>
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
                        from .utils import show_success_message
                        show_success_message(f"¡{tipo_ausencia} registrada! Del {start_date} al {end_date}.", 1)
                        safe_rerun()
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
                                            # Invalidar cachés
                                            try:
                                                cached_get_weekly_modalities_by_rol.clear()
                                            except:
                                                pass
                                            # Limpieza ampliada de session_state para no mostrar data vieja
                                            try:
                                                from .database import clear_user_registros_cache
                                                clear_user_registros_cache(user_id)
                                            except Exception:
                                                pass
                                            try:
                                                keys_drop = []
                                                for k in st.session_state.keys():
                                                    if (k == f"user_registros_{user_id}"
                                                            or str(k).startswith(f"user_registros_{user_id}_")
                                                            or str(k).startswith("chart_data_")
                                                            or str(k).startswith("vacaciones_")
                                                            or str(k).startswith("tipos_")
                                                            or k in {"week_offset", "last_selected_date",
                                                                     "chart_data_weekly", "vac_year_selector"}):
                                                        keys_drop.append(k)
                                                for kd in keys_drop:
                                                    try:
                                                        del st.session_state[kd]
                                                    except Exception:
                                                        pass
                                            except Exception:
                                                pass
                                            from .utils import show_success_message
                                            show_success_message("Modificado correctamente", 0.5)
                                            st.session_state[edit_key] = False
                                            safe_rerun()
                                        else:
                                            st.error("Error al modificar")
                                with b2:
                                    if st.form_submit_button("❌ Cancelar"):
                                        st.session_state[edit_key] = False
                                        safe_rerun()
                        else:
                            col_a, col_b = st.columns([1, 4])
                            with col_a:
                                if st.button("✏️", key=f"btn_edit_vac_{row['id']}"):
                                    st.session_state[edit_key] = True
                                    safe_rerun()
                            with col_b:
                                if st.button("🗑️ Eliminar periodo", key=f"del_vac_{row['id']}"):
                                    ret = delete_vacaciones(row['id'])
                                    if ret:
                                        # Invalidar caché de admin
                                        try:
                                            cached_get_weekly_modalities_by_rol.clear()
                                        except:
                                            pass
                                        # Refuerzo limpieza cachés (delete_vacaciones ya lo hace
                                        # internamente, pero aseguramos UI refrescada aquí)
                                        try:
                                            from .database import clear_user_registros_cache
                                            clear_user_registros_cache(user_id)
                                        except Exception:
                                            pass
                                        try:
                                            keys_drop = []
                                            for k in st.session_state.keys():
                                                if (k == f"user_registros_{user_id}"
                                                        or str(k).startswith(f"user_registros_{user_id}_")
                                                        or str(k).startswith("chart_data_")
                                                        or str(k).startswith("vacaciones_")
                                                        or str(k).startswith("tipos_")
                                                        or k in {"week_offset", "last_selected_date",
                                                                 "chart_data_weekly", "vac_year_selector"}):
                                                    keys_drop.append(k)
                                            for kd in keys_drop:
                                                try:
                                                    del st.session_state[kd]
                                                except Exception:
                                                    pass
                                        except Exception:
                                            pass
                                        from .utils import show_success_message
                                        show_success_message("Periodo eliminado.", 0.5)
                                        safe_rerun()
                                    else:
                                        st.error("No se pudo eliminar.")
            else:
                st.caption("No tienes periodos de licencia registrados.")
        except Exception as e:
            st.error(f"Error cargando tus licencias: {e}")
