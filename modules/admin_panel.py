import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
import calendar
from .database import (
    get_connection, get_registros_dataframe, get_tecnicos_dataframe,
    get_clientes_dataframe, get_tipos_dataframe, get_modalidades_dataframe,
    get_roles_dataframe, get_users_dataframe, get_tipos_dataframe_with_roles, 
    get_grupos_dataframe, get_nomina_dataframe, test_connection,
    get_registros_dataframe_with_date_filter, get_user_rol_id, 
    get_user_registros_dataframe, get_user_info, add_empleado_nomina, 
    update_empleado_nomina, empleado_existe, get_departamentos_list,
    generate_users_from_nomina, generate_roles_from_nomina, 
    get_or_create_tecnico, get_or_create_cliente, get_or_create_tipo_tarea, 
    get_or_create_modalidad, registrar_actividad, add_client, add_grupo, 
    get_roles_by_grupo, update_grupo_roles, get_registros_by_rol_with_date_filter,
    get_tecnico_rol_id, get_or_create_grupo_with_department_association,
    get_or_create_grupo_with_tecnico_department_association,
    get_feriados_dataframe, add_feriado, toggle_feriado, delete_feriado,
    add_registros_comerciales_batch, send_test_notification_email
)
from .config import SYSTEM_ROLES, DEFAULT_VALUES, SYSTEM_LIMITS
from .nomina_management import render_nomina_edit_delete_forms
from .auth import create_user, validate_password, hash_password, is_2fa_enabled, unlock_user
from .utils import show_success_message, normalize_text, month_name_es, get_general_alerts, safe_rerun, parse_registro_datetime, format_registro_date_iso
from .activity_logs import render_activity_logs
from .backup_utils import create_full_backup_excel, restore_full_backup_excel


@st.cache_data(ttl=60)
def _cached_roles_dataframe_for_targets():
    return get_roles_dataframe(exclude_admin=False, exclude_sin_rol=False, exclude_hidden=False)


@st.cache_data(ttl=60)
def _cached_users_dataframe_for_targets():
    return get_users_dataframe()


def clear_restore_related_caches():
    """Limpia cachés de session_state que pueden quedar desfasadas tras un restore.

    Incluye (además de user_registros y gráficos) TODOS los flags y datos locales
    de forms de Nuevo Registro (sufijos, contadores, valores defaults del form),
    caches de gestión de tipos de tarea, y cualquier key que esté relacionada
    con carga dinámica de clientes / modalidades / grupos por rol (para que al
    rerenderear el dashboard del técnico NO queden frames viejos con 0 filas).
    """
    keys_to_delete = []
    for key in st.session_state.keys():
        if (
            # Cachés de registros / gráficos semanales
            key.startswith("user_registros_")
            or key.startswith("chart_data_")
            or key.startswith("task_type_")
            or key.startswith("planificacion_")
            or key.startswith("vacaciones_")
            or key.startswith("nuevo_reg_")
            or key.startswith("new_record_")
            or key.startswith("form_")
            or key.startswith("record_edit_")
            or key.startswith("modalidades_cache_")
            or key.startswith("clientes_cache_")
            or key.startswith("grupos_cache_")
            or key in {
                "week_offset",
                "last_selected_date",
                "form_key_suffix",
                "task_type_counter",
                # Flags locales usados por el dashboard técnico
                "last_saved_record_id",
                "flash_new_record_ok",
                "flash_new_record_err",
                "selected_employee_id",
                "selected_client_id",
            }
        ):
            keys_to_delete.append(key)

    for key in keys_to_delete:
        try:
            del st.session_state[key]
        except Exception:
            pass


def render_pending_client_requests(key_prefix=""):
    """Renderiza la lista de solicitudes de clientes pendientes"""
    st.subheader("🟨 Solicitudes de Clientes")
    from .database import get_cliente_solicitudes_df, approve_cliente_solicitud, reject_cliente_solicitud, get_users_dataframe
    
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
        has_tipo = 'tipo' in req_df.columns
        
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
                tipo_val = r["tipo"] if has_tipo else None
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
                    if st.button("Rechazar", key=f"{key_prefix}reject_client_req_{rid}"):
                        success, msg = reject_cliente_solicitud(rid)
                        if success:
                            st.info("Solicitud rechazada.")
                            safe_rerun()
                        else:
                            st.error(f"No se pudo rechazar la solicitud: {msg}")

def render_admin_panel():
    """Renderiza el panel completo de administrador"""
    
    # --- Mappings for clean URLs ---
    MAIN_TAB_MAPPING = {
        "visualizacion": "📊 Visualización de Datos",
        "gestion": "⚙️ Gestión",
        "admin": "🛠️ Administración"
    }
    MAIN_TAB_LOOKUP = {v: k for k, v in MAIN_TAB_MAPPING.items()}
    main_options = list(MAIN_TAB_MAPPING.values())

    # Notification Logic
    alerts = get_general_alerts()
    # owner_alerts = alerts["owner_alerts"] # Eliminado por solicitud del usuario
    pending_reqs = alerts["pending_requests_count"]

    # --- Restore Session State from Query Params (if present) ---
    # This handles page reloads (e.g. from HTML forms in Contacts)
    # Using 'last_known' pattern to avoid overwriting user interaction
    qp = st.query_params
    
    # 1. Main Tab
    current_main_slug = qp.get("adm_main")
    if current_main_slug:
        # If URL param exists and is different from last known URL state -> External Navigation (or first load)
        if current_main_slug != st.session_state.get("last_adm_main_slug"):
             val = MAIN_TAB_MAPPING.get(current_main_slug, current_main_slug)
             if val in MAIN_TAB_MAPPING.values():
                 st.session_state["admin_main_tab"] = val
                 st.session_state["last_adm_main_slug"] = current_main_slug

    # 2. Sub Tab (Gestión) - handled in render_management_tabs but we can init here if needed
    # We leave it to the specific function to handle the logic to keep code localized

    # 3. Client Tab - handled in render_management_tabs -> clients


    # Toast for Pending Client Requests
    if not st.session_state.get('alerts_shown', False):
        if pending_reqs > 0:
            st.toast(f"🟨 Tienes {pending_reqs} solicitudes de clientes pendientes.", icon="📝")
        # Mark alerts as shown for this session
        st.session_state.alerts_shown = True
    
    # has_alerts = bool(owner_alerts) or (pending_reqs > 0)
    has_alerts = pending_reqs > 0

    col_head, col_icon = st.columns([0.92, 0.08])
    with col_head:
        st.header("Panel de Administrador")
    with col_icon:
        st.write("")  # Spacer for alignment
        try:
            wrapper_class = "has-alerts" if has_alerts else "no-alerts"
            st.markdown(f"<div class='notif-trigger {wrapper_class}'>", unsafe_allow_html=True)
            icon_str = "🔔❗" if has_alerts else "🔕"
            with st.popover(icon_str, use_container_width=True):
                st.markdown("### Notificaciones")
                if not has_alerts:
                    st.info("No hay alertas pendientes.")
                else:
                    if pending_reqs > 0:
                        label = f"🟨 Solicitudes de Clientes: {pending_reqs} pendientes"
                        if st.button(label, key="btn_notif_client_reqs", use_container_width=True):
                            # Use clean URL params for navigation
                            st.query_params["adm_main"] = "gestion"
                            st.query_params["adm_sub"] = "clientes"
                            st.query_params["adm_cli"] = "solicitudes"
                            safe_rerun()
                        st.divider()
            st.markdown("</div>", unsafe_allow_html=True)
        except AttributeError:
            if st.button("🔔"):
                st.info(f"Notificaciones: {pending_reqs} solicitudes")

    # Navegación Principal con Segmented Control (Pestañas programables)
    
    if "admin_main_tab" not in st.session_state:
        st.session_state["admin_main_tab"] = main_options[0]
        
    if st.session_state["admin_main_tab"] not in main_options:
        st.session_state["admin_main_tab"] = main_options[0]

    selected_main = st.segmented_control(
        "Navegación Principal",
        main_options,
        key="admin_main_tab",
        label_visibility="collapsed"
    )
    
    # Sync main tab with URL (and update last known state)
    target_slug = MAIN_TAB_LOOKUP.get(selected_main, selected_main)
    current_url_slug = st.query_params.get("adm_main")
    
    if target_slug != current_url_slug:
        st.query_params["adm_main"] = target_slug
        st.session_state["last_adm_main_slug"] = target_slug
    
    st.write("") # Spacer

    if selected_main == "📊 Visualización de Datos":
        render_data_visualization()
    elif selected_main == "⚙️ Gestión":
        render_management_tabs()
    elif selected_main == "🛠️ Administración":
        render_admin_settings()

def render_data_visualization():
    """Renderiza la sección de visualización de datos organizada por roles"""
    from .admin_visualizations import render_data_visualization as _render_data_visualization
    return _render_data_visualization()

def render_role_visualizations(df, rol_id, rol_nombre):
    """Renderiza las visualizaciones específicas para un rol"""
    from .admin_visualizations import render_role_visualizations as _render_role_visualizations
    return _render_role_visualizations(df, rol_id, rol_nombre)

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
    from .utils import render_excel_uploader as _render_excel_uploader
    uploaded_file, excel_df, selected_sheet = _render_excel_uploader(key=key)
    return uploaded_file, excel_df, selected_sheet

def render_records_management(df, role_id=None):
    """Renderiza la gestión de registros para administradores"""
    from .admin_records import render_records_management as _render_records_management
    return _render_records_management(df, role_id)

def render_admin_edit_form(registro_seleccionado, registro_id, role_id=None):
    """Renderiza el formulario de edición para administradores"""
    from .admin_records import render_admin_edit_form as _render_admin_edit_form
    return _render_admin_edit_form(registro_seleccionado, registro_id, role_id)

def render_admin_delete_form(registro_seleccionado, registro_id, role_id=None):
    """Renderiza el formulario de eliminación para administradores"""
    from .admin_records import render_admin_delete_form as _render_admin_delete_form
    return _render_admin_delete_form(registro_seleccionado, registro_id, role_id)

def render_management_tabs():
    """Renderiza las pestañas de gestión"""
    
    # --- Mappings for clean URLs (Gestion) ---
    GESTION_TAB_MAPPING = {
        "usuarios": "👥 Usuarios",
        "clientes": "🏢 Clientes",
        "tipos_tarea": "📋 Tipos de Tarea",
        "modalidades": "🔄 Modalidades",
        "departamentos": "🏢 Departamentos",
        "planificacion": "📅 Planificación Semanal",
        "grupos": "👪 Grupos",
        "nomina": "🏠 Nómina",
        "marcas": "🏷️ Marcas",
        "registros": "📝 Registros",
        "feriados": "📅 Feriados"
    }
    GESTION_TAB_LOOKUP = {v: k for k, v in GESTION_TAB_MAPPING.items()}
    options_list = list(GESTION_TAB_MAPPING.values())
    
    # Restore from URL if needed (using last_known pattern)
    qp = st.query_params
    current_sub_slug = qp.get("adm_sub")
    if current_sub_slug:
        if current_sub_slug != st.session_state.get("last_adm_sub_slug"):
            val = GESTION_TAB_MAPPING.get(current_sub_slug, current_sub_slug)
            if val in options_list:
                st.session_state["admin_gestion_tab"] = val
                st.session_state["last_adm_sub_slug"] = current_sub_slug

    if "admin_gestion_tab" not in st.session_state:
        st.session_state["admin_gestion_tab"] = options_list[0]
        
    # Ensure valid selection
    if st.session_state["admin_gestion_tab"] not in options_list:
        st.session_state["admin_gestion_tab"] = options_list[0]
        
    # Use segmented_control for programmatic navigation (replaces selectbox)
    selected_gestion = st.segmented_control(
        "Seleccione Entidad a Gestionar:",
        options=options_list,
        key="admin_gestion_tab",
        label_visibility="collapsed"
    )
    
    # Sync gestion tab with URL
    target_slug = GESTION_TAB_LOOKUP.get(selected_gestion, selected_gestion)
    current_url_slug = st.query_params.get("adm_sub")
    
    if target_slug != current_url_slug:
        st.query_params["adm_sub"] = target_slug
        st.session_state["last_adm_sub_slug"] = target_slug

    st.write("") # Spacer

    # Gestión de Usuarios
    if selected_gestion == "👥 Usuarios":
        render_user_management()
    
    # Gestión de Clientes
    elif selected_gestion == "🏢 Clientes":
        # --- Mappings for clean URLs (Clients) ---
        CLIENT_TAB_MAPPING = {
            "lista": "📋 Lista",
            "gestion": "⚙️ Gestión",
            "contactos": "📞 Contactos",
            "solicitudes": "🟨 Solicitudes"
        }
        CLIENT_TAB_LOOKUP = {v: k for k, v in CLIENT_TAB_MAPPING.items()}
        client_options = list(CLIENT_TAB_MAPPING.values())
        
        # Restore from URL if needed (last_known pattern)
        qp = st.query_params
        current_cli_slug = qp.get("adm_cli")
        if current_cli_slug:
            if current_cli_slug != st.session_state.get("last_adm_cli_slug"):
                 val = CLIENT_TAB_MAPPING.get(current_cli_slug, current_cli_slug)
                 if val in client_options:
                     st.session_state["admin_clients_tab"] = val
                     st.session_state["last_adm_cli_slug"] = current_cli_slug

        if "admin_clients_tab" not in st.session_state:
            st.session_state["admin_clients_tab"] = client_options[0]
            
        # Ensure valid selection
        if st.session_state["admin_clients_tab"] not in client_options:
            st.session_state["admin_clients_tab"] = client_options[0]
            
        selected_client_sub = st.segmented_control(
            "Sección Clientes",
            client_options,
            key="admin_clients_tab",
            label_visibility="collapsed"
        )
        
        # Sync clients sub-tab with URL
        target_slug = CLIENT_TAB_LOOKUP.get(selected_client_sub, selected_client_sub)
        current_url_slug = st.query_params.get("adm_cli")
        
        if target_slug != current_url_slug:
            st.query_params["adm_cli"] = target_slug
            st.session_state["last_adm_cli_slug"] = target_slug
            
        st.write("")
        
        if selected_client_sub == "📋 Lista":
            render_client_management()
        elif selected_client_sub == "⚙️ Gestión":
            from .admin_clients import render_client_crud_management as _render_client_crud
            _render_client_crud()
        elif selected_client_sub == "📞 Contactos":
            from .contacts_shared import render_shared_contacts_management
            # Asumiendo que el usuario es Admin o tiene permisos suficientes
            username = st.session_state.get('username', 'Admin')
            # Pasamos key_prefix para evitar conflictos de claves con otras vistas
            render_shared_contacts_management(username, is_admin=True, key_prefix="admin_contacts")
        elif selected_client_sub == "🟨 Solicitudes":
            render_pending_client_requests()

    
    
    # Gestión de Tipos de Tarea
    elif selected_gestion == "📋 Tipos de Tarea":
        render_task_type_management()
    
    # Gestión de Modalidades
    elif selected_gestion == "🔄 Modalidades":
        render_modality_management()
        
    # Gestión de Departamentos
    elif selected_gestion == "🏢 Departamentos":
        render_department_management()
    
    # 📅 Planificación Semanal (nuevo)
    elif selected_gestion == "📅 Planificación Semanal":
        from .admin_planning import render_planning_management as _render_planning_management
        _render_planning_management()
    
    # Gestión de Grupos
    elif selected_gestion == "👪 Grupos":
        render_grupo_management()
        
    # Gestión de Nómina
    elif selected_gestion == "🏠 Nómina":
        render_nomina_management()
    
    # Gestión de Marcas
    elif selected_gestion == "🏷️ Marcas":
        from .admin_brands import render_brand_management as _render_brand_management
        _render_brand_management()
        
    # Registros de actividad
    elif selected_gestion == "📝 Registros":
        try:
            render_activity_logs()
        except Exception as e:
            from .utils import log_app_error
            log_app_error(e, module="admin_panel", function="render_management_tabs")
            st.error(f"Error al mostrar los registros de actividad: {str(e)}")
            st.error(f"Error al mostrar los registros de actividad: {str(e)}")
    
    # Gestión de Feriados
    elif selected_gestion == "📅 Feriados":
        render_feriados_management()

def render_feriados_management():
    st.subheader("Gestión de Feriados")
    year_options = [datetime.now().year - 1, datetime.now().year, datetime.now().year + 1]
    sel_year = st.selectbox("Año", options=year_options, index=1, key="adm_feriados_year")
    with st.form(key="adm_feriados_add_form"):
        col_a, col_b = st.columns([1, 1])
        with col_a:
            fecha = st.date_input("Fecha *", key="adm_feriado_fecha")
        with col_b:
            nombre = st.text_input("Nombre *", key="adm_feriado_nombre")
        tipo = st.selectbox("Tipo", options=["nacional", "regional", "empresa"], index=0, key="adm_feriado_tipo")
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
            selected_label = st.selectbox("Seleccionar feriado para acciones", options=labels, key="adm_feriado_select")
            selected = next(o for o in opciones if o[0] == selected_label)
            fid = selected[1]
            activo_sel = selected[2]
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Activar" if not activo_sel else "Desactivar", key="adm_feriado_toggle_selected"):
                    toggle_feriado(fid, not activo_sel)
                    safe_rerun()
            with col_b:
                if st.button("Eliminar", key="adm_feriado_delete_selected"):
                    delete_feriado(fid)
                    safe_rerun()

    st.divider()
    with st.expander("📥 Carga masiva desde Excel", expanded=False):
        from .utils import render_excel_uploader, detect_feriados_columns, excel_normalize_columns
        uploaded_file, df, selected_sheet = render_excel_uploader(
            label="Seleccionar archivo con feriados (.xls o .xlsx)",
            key="feriados_excel_upload",
            expanded=False,
            enable_sheet_selection=True
        )
        if uploaded_file is not None and df is not None:
            col_map = {}
            df = excel_normalize_columns(df, col_map)
            date_col, name_col, type_col = detect_feriados_columns(df)

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

            if st.button("Procesar archivo y crear feriados", type="primary", key="process_feriados_excel"):
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
def render_user_management():
    """Renderiza la gestión de usuarios"""
    from .admin_users import render_user_management as _render_user_management
    return _render_user_management()

def render_user_edit_form(users_df, roles_df):
    """Renderiza el formulario de edición de usuarios"""
    from .admin_users import render_user_edit_form as _render_user_edit_form
    return _render_user_edit_form(users_df, roles_df)

def render_user_delete_form(users_df):
    """Renderiza el formulario de eliminación de usuarios"""
    from .admin_users import render_user_delete_form as _render_user_delete_form
    return _render_user_delete_form(users_df)
def delete_user(user_id, username):
    """Elimina un usuario y sus registros asociados"""
    from .admin_users import delete_user as _delete_user
    return _delete_user(user_id, username)

def render_client_management():
    """Renderiza la gestión de clientes"""
    from .admin_clients import render_client_management as _render_client_management
    return _render_client_management()

def render_client_edit_delete_forms(clients_df):
    """Renderiza formularios de edición y eliminación de clientes"""
    from .admin_clients import render_client_edit_delete_forms as _render_client_edit_delete_forms
    return _render_client_edit_delete_forms(clients_df)

def clean_duplicate_task_types():
    """Limpia tipos de tarea duplicados manteniendo solo uno de cada tipo"""
    from .admin_task_types import clean_duplicate_task_types as _clean_duplicate_task_types
    return _clean_duplicate_task_types()

def render_task_type_management():
    """Renderiza la gestión de tipos de tarea"""
    from .admin_task_types import render_task_type_management as _render_task_type_management
    return _render_task_type_management()

def render_task_type_edit_delete_forms(tipos_df, roles_df):
    """Renderiza formularios de edición y eliminación de tipos de tarea"""
    from .admin_task_types import render_task_type_edit_delete_forms as _render_task_type_edit_delete_forms
    return _render_task_type_edit_delete_forms(tipos_df, roles_df)

def render_modality_management():
    """Renderiza la gestión de modalidades"""
    from .admin_modalities import render_modality_management as _render_modality_management
    return _render_modality_management()

def render_modality_edit_delete_forms(modalidades_df):
    """Renderiza formularios de edición y eliminación de modalidades"""
    from .admin_modalities import render_modality_edit_delete_forms as _render_modality_edit_delete_forms
    return _render_modality_edit_delete_forms(modalidades_df)

def render_department_management():
    """Renderiza la gestión de departamentos"""
    from .admin_departments import render_department_management as _render_department_management
    return _render_department_management()

def render_grupo_management():
    """Renderiza la gestión de grupos"""
    from .admin_groups import render_grupo_management as _render_grupo_management
    return _render_grupo_management()

def render_nomina_management():
    """Renderiza la gestión de nómina"""
    from .nomina_management import render_nomina_management as _render_nomina_management
    return _render_nomina_management()

def process_commercial_excel_data(excel_df):
    """Procesa y carga datos comerciales (detección automática)"""
    import streamlit as st
    import unicodedata
    
    def normalize_col(col):
        col = str(col).strip().lower()
        col = unicodedata.normalize('NFD', col)
        col = ''.join(char for char in col if unicodedata.category(char) != 'Mn')
        return col

    try:
        # Validar al menos fecha y responsable o cliente
        normalized_cols = [normalize_col(c) for c in excel_df.columns]
        
        # Palabras clave comerciales fuertes (Actualizado)
        comm_keywords = ['trato - id', 'trato - propietario', 'moneda', 'fecha prevista', 'ganado', 'perdido']
        has_comm = any(k in c for c in normalized_cols for k in comm_keywords)
        
        if not has_comm:
             # Si no tiene keywords comerciales, no es concluyente, pero si llegamos aquí es porque falló la técnica
             pass
        
        # Obtener el ID del usuario actual para asignar tratos sin propietario
        current_user_id = st.session_state.get('user_id')
        
        # Si es Admin (id=1), no asignar por defecto (dejar como NULL/Sin Asignar)
        # para que aparezcan en la vista de Comercial (que incluye no asignados)
        default_owner = current_user_id
        if current_user_id == 1:
            default_owner = None

        count, errors = add_registros_comerciales_batch(excel_df, default_user_id=default_owner)
        msg = f"✅ Se detectó formato COMERCIAL (Ventas/Tratos). {count} registros cargados/actualizados correctamente en la base de datos comercial."
        if errors:
            st.warning(f"{msg} Se encontraron {len(errors)} errores en filas individuales.")
        else:
            st.success(msg)
        return count, errors, 0, set()
    except Exception as e:
        st.error(f"Error procesando planilla comercial: {e}")
        return 0, [str(e)], 0, set()

def process_excel_data(excel_df):
    """Procesa y carga datos desde Excel con control de duplicados y estandarización"""
    import calendar
    import openpyxl  # Importar explícitamente openpyxl
    from datetime import datetime
    import unicodedata
    from .database import get_or_create_tecnico, get_or_create_cliente, get_or_create_tipo_tarea, get_or_create_modalidad, get_or_create_grupo_with_department_association
    import streamlit as st

    # Función auxiliar para verificar si un valor está vacío o es inválido
    def is_empty_or_invalid(value):
        """Verifica si un valor está vacío, es None, NaN o contiene solo espacios"""
        if value is None:
            return True
        if pd.isna(value):
            return True
        if str(value).strip() == '':
            return True
        return False

    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM usuarios WHERE rol_id != 1")  # rol_id 1 es admin
    non_admin_users = c.fetchone()[0]
    
    if non_admin_users == 0:
        st.warning("⚠️ No existen usuarios en el sistema para asignar los registros.")
        conn.close()
        return 0, 0, 0, set()
    
    # Obtener el usuario actual que está cargando la planilla
    current_user_id = st.session_state.get('user_id')

    # Función para normalizar nombres de columnas removiendo acentos y caracteres especiales
    def normalize_column_name(col):
        col = str(col).strip()
        # Remover acentos y caracteres especiales
        col = unicodedata.normalize('NFD', col)
        col = ''.join(char for char in col if unicodedata.category(char) != 'Mn')
        return col
    
    # Normalizar nombres de columnas del Excel
    normalized_columns = [normalize_column_name(col) for col in excel_df.columns]
    
    # --- DETECCIÓN DE TIPO DE PLANILLA ---
    # Convertir a minúsculas para detección flexible
    norm_cols_lower = [c.lower() for c in normalized_columns]
    
    tech_required = ['fecha', 'tecnico', 'cliente', 'tipo tarea', 'modalidad'] # Lowercase for check
    tech_matches = sum(1 for req in tech_required if req in norm_cols_lower)
    
    # Si tiene menos de 3 columnas técnicas coincidentes, verificar si es comercial
    if tech_matches < 3:
        # Palabras clave comerciales actualizadas según input del usuario
        comm_keywords = ['trato - id', 'trato - propietario', 'moneda', 'fecha prevista', 'ganado', 'perdido']
        comm_matches = sum(1 for kw in comm_keywords if any(kw in col for col in norm_cols_lower))
        
        # Si tiene keywords comerciales o (fecha + cliente pero no técnico/modalidad)
        if comm_matches >= 1:
             conn.close() # Cerrar conexión antes de delegar
             return process_commercial_excel_data(excel_df)
    # -------------------------------------
    
    # Mapeo de columnas esperadas (normalizadas)
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
        'Equipo': 'grupo',
        'Hora Extra': 'es_hora_extra' # Nuevo mapeo
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
        return 0, 0, 0, set()
    
    # Crear DataFrame con columnas normalizadas
    excel_df_normalized = excel_df.copy()
    excel_df_normalized.columns = normalized_columns
    
    # Aplicar mapeo de columnas
    excel_df_mapped = excel_df_normalized.rename(columns=column_mapping_normalized)
    # Eliminar posibles columnas duplicadas tras el mapeo
    excel_df_mapped = excel_df_mapped.loc[:, ~excel_df_mapped.columns.duplicated()]
    
    # Limpiar DataFrame: eliminar filas con fechas vacías
    excel_df_mapped = excel_df_mapped.dropna(subset=['fecha'])
    excel_df_mapped = excel_df_mapped[excel_df_mapped['fecha'] != '']
    
    if excel_df_mapped.empty:
        st.warning("No hay datos válidos para procesar después de filtrar fechas vacías.")
        return 0, 0, 0, set()
    
    success_count = 0
    error_count = 0
    duplicate_count = 0
    created_entities = {
        'tecnicos': set(),
        'clientes': set(),
        'tipos_tarea': set(),
        'modalidades': set(),
        'grupos': set()  # Agregar grupos a las entidades creadas
    }
    
    # Nuevo: Registro de errores por tipo
    error_types = {
        'fecha_invalida': 0,
        'tecnico_vacio': 0,
        'cliente_vacio': 0,
        'tipo_tarea_vacio': 0,
        'modalidad_vacia': 0,
        'entidad_error': 0,
        'cliente_no_existe': 0,
        'otros_errores': 0
    }
    
    missing_clients = set()
    
    # Obtener entidades existentes para evitar duplicados y optimizar búsqueda
    c.execute("SELECT nombre FROM tecnicos")
    existing_tecnicos = {row[0] for row in c.fetchall()}
    
    # Cargar todos los clientes con sus IDs para búsqueda inteligente en memoria
    c.execute("SELECT id_cliente, nombre FROM clientes")
    all_clients_data = c.fetchall() # Lista de tuplas (id, nombre)
    existing_clientes = {nombre for _, nombre in all_clients_data}
    
    # Pre-procesar clientes para búsqueda normalizada
    # Estructura: {'NOMBRE_NORMALIZADO': id_cliente}
    import re
    from .utils import normalize_name
        
    normalized_client_map = {}
    for cid, cname in all_clients_data:
        norm = normalize_name(cname)
        if norm:
            normalized_client_map[norm] = cid
            
    c.execute("SELECT descripcion FROM tipos_tarea")
    existing_tipos = {row[0] for row in c.fetchall()}
    
    c.execute("SELECT descripcion FROM modalidades_tarea")
    existing_modalidades = {row[0] for row in c.fetchall()}
    
    for index, row in excel_df_mapped.iterrows():
        try:
            # Validación temprana: omitir filas con campos críticos vacíos (sin reportar error)
            if (is_empty_or_invalid(row['fecha']) or 
                is_empty_or_invalid(row['tecnico']) or 
                is_empty_or_invalid(row['cliente']) or 
                is_empty_or_invalid(row['tipo_tarea']) or 
                is_empty_or_invalid(row['modalidad'])):
                continue  # Omitir silenciosamente
            
            # Estandarizar fecha
            fecha_str = str(row['fecha'])
            try:
                fecha_obj = parse_registro_datetime(fecha_str)
                fecha_formateada = format_registro_date_iso(fecha_obj)
                if not fecha_formateada:
                    raise ValueError("Fecha invalida")
            except Exception as e:
                # Solo reportar error si la fecha no está vacía
                if not is_empty_or_invalid(row['fecha']):
                    error_types['fecha_invalida'] += 1
                    error_count += 1
                continue  # Omitir filas con fechas que no se pueden procesar
            
            # Obtener y crear entidades automáticamente (normalizadas)
            tecnico = ' '.join(str(row['tecnico']).strip().split()).title()
            cliente = ' '.join(str(row['cliente']).strip().split()).title()
            tipo_tarea = ' '.join(str(row['tipo_tarea']).strip().split()).title()
            modalidad = ' '.join(str(row['modalidad']).strip().split()).title()
            
            # Verificar si existe la columna grupo y obtener su valor (normalizado)
            grupo = "General"  # Valor predeterminado (primera letra mayúscula)
            usar_grupo_general = True  # Flag para saber si usar asociación general
            
            if 'grupo' in row and not is_empty_or_invalid(row['grupo']):
                grupo_valor = str(row['grupo']).strip()
                # Verificar que no sea un valor vacío o inválido
                if not is_empty_or_invalid(grupo_valor):
                    grupo = ' '.join(grupo_valor.split()).title()
                    usar_grupo_general = False
            
            # Usar get_or_create para obtener IDs (creando si no existen)
            try:
                id_tecnico = get_or_create_tecnico(tecnico, conn)
                if tecnico not in existing_tecnicos:
                    created_entities['tecnicos'].add(tecnico)
                    
                # CAMBIO: No crear cliente automáticamente. Buscar existente.
                # Estrategia de búsqueda jerárquica INTELIGENTE:
                
                # 0. Preparar datos
                from .utils import find_cliente_id
                id_cliente = find_cliente_id(cliente, all_clients_data, normalized_client_map)

                # 4. Fallback a SQL "Starts With" (por si acaso, aunque cubierto por 3A)
                if not id_cliente and len(cliente) >= 3:
                     c.execute("SELECT id_cliente FROM clientes WHERE UPPER(nombre) LIKE %s LIMIT 1", (cliente.upper() + '%',))
                     res_cliente = c.fetchone()
                     if res_cliente:
                         id_cliente = res_cliente[0]
                
                if id_cliente:
                    # Encontrado
                    pass
                else:
                    # Cliente no existe y ya no se permite crear desde métricas
                    error_types['cliente_no_existe'] += 1
                    error_count += 1
                    missing_clients.add(cliente)
                    continue # Saltar este registro
                    
                # if cliente not in existing_clientes:
                #    created_entities['clientes'].add(cliente)
                    
                # Pasar el nombre del empleado (técnico) para asociación automática
                id_tipo = get_or_create_tipo_tarea(tipo_tarea, conn, empleado_nombre=tecnico)
                if tipo_tarea not in existing_tipos:
                    created_entities['tipos_tarea'].add(tipo_tarea)
                    
                id_modalidad = get_or_create_modalidad(modalidad, conn)
                if modalidad not in existing_modalidades:
                    created_entities['modalidades'].add(modalidad)
                    
                # Crear grupo con lógica diferente según si es "General" o específico
                if usar_grupo_general:
                    # Para grupo "General", usar la función original que asocia al usuario que sube la planilla
                    from .database import get_or_create_grupo_with_department_association
                    current_user_id = st.session_state.get('user_id')
                    id_grupo = get_or_create_grupo_with_department_association(grupo, current_user_id, conn)
                else:
                    # Para grupos específicos, usar la nueva función que asocia al departamento del técnico
                    id_grupo = get_or_create_grupo_with_tecnico_department_association(grupo, tecnico, conn)
                
                # Verificar si el grupo es nuevo para agregarlo a las entidades creadas
                c.execute("SELECT COUNT(*) FROM grupos WHERE nombre = %s", (grupo,))
                grupo_count = c.fetchone()[0]
                if grupo_count == 1:  # Si solo hay 1, significa que se acaba de crear
                    created_entities['grupos'].add(grupo)
                    
            except Exception as e:
                # Solo incrementar error si no es un problema de campos vacíos
                if not (is_empty_or_invalid(tecnico) or is_empty_or_invalid(cliente) or 
                       is_empty_or_invalid(tipo_tarea) or is_empty_or_invalid(modalidad)):
                    error_types['entidad_error'] += 1
                    error_count += 1
                continue
            
            # Validar otros campos (normalizados)
            tarea_realizada = ' '.join(str(row['tarea_realizada']).strip().split()) if not is_empty_or_invalid(row.get('tarea_realizada')) else 'N/A'
            numero_ticket = str(row['numero_ticket']).strip() if not is_empty_or_invalid(row.get('numero_ticket')) else 'N/A'
            
            # Validar tiempo (acepta "1,5", "1.5", "1,5 hs")
            raw_tiempo = row.get('tiempo')
            if is_empty_or_invalid(raw_tiempo):
                tiempo = 0.0
            else:
                try:
                    tiempo_str = str(raw_tiempo).strip().lower()
                    # Mantener solo dígitos y separadores decimal
                    tiempo_str = ''.join(ch for ch in tiempo_str if ch.isdigit() or ch in [',', '.'])
                    tiempo_str = tiempo_str.replace(',', '.')
                    tiempo = round(float(tiempo_str), 2)
                except Exception:
                    tiempo = 0.0
            descripcion = ' '.join(str(row.get('descripcion', '')).strip().split()) if not is_empty_or_invalid(row.get('descripcion')) else ''
            # Validar que el mes sea válido antes de convertir
            mes_num = fecha_obj.month
            if mes_num is None or mes_num < 1 or mes_num > 12:
                from datetime import datetime
                mes_num = datetime.now().month
            # Guardar número de mes; el nombre se resolverá al leer
            mes = mes_num

            # --- PROCESAMIENTO DE HORA EXTRA ---
            es_hora_extra = False
            raw_hora_extra = row.get('es_hora_extra')
            if not is_empty_or_invalid(raw_hora_extra):
                # Detectar checkbox marcado (True, 1, yes, si) o "x"
                val_he = str(raw_hora_extra).strip().lower()
                if val_he in ['true', '1', 'si', 'yes', 'x', 'v', 's']:
                    es_hora_extra = True
            # -----------------------------------

            # Verificar duplicados
            c.execute('''
                SELECT id, grupo, es_hora_extra FROM registros 
                WHERE (
                    CASE
                        WHEN fecha ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN to_date(fecha, 'YYYY-MM-DD')
                        WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{2}$' THEN to_date(fecha, 'DD/MM/YY')
                        WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{4}$' THEN to_date(fecha, 'DD/MM/YYYY')
                        ELSE NULL
                    END
                ) = %s::date AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s
                AND id_modalidad = %s AND tarea_realizada = %s AND tiempo = %s
            ''', (fecha_formateada, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, tiempo))
            
            registro_existente = c.fetchone()
            
            if registro_existente:
                registro_id, grupo_actual, he_actual = registro_existente
                
                # Actualizar el grupo o hora extra si han cambiado
                updates = []
                params = []
                
                if grupo != grupo_actual:
                    updates.append("grupo = %s")
                    params.append(grupo)
                
                # Convertir None a False para comparación segura
                he_actual_bool = bool(he_actual)
                if es_hora_extra != he_actual_bool:
                    updates.append("es_hora_extra = %s")
                    params.append(es_hora_extra)
                
                if updates:
                    params.append(registro_id)
                    sql_update = f"UPDATE registros SET {', '.join(updates)} WHERE id = %s"
                    c.execute(sql_update, tuple(params))
                
                duplicate_count += 1
                continue
            
            # Insertar registro incluyendo el campo grupo, hora extra y fecha de creación
            from datetime import datetime
            now_created_at = datetime.now()
            c.execute('''
                INSERT INTO registros 
                (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
                 numero_ticket, tiempo, descripcion, mes, usuario_id, grupo, es_hora_extra, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (fecha_formateada, id_tecnico, id_cliente, id_tipo, id_modalidad, 
                  tarea_realizada, numero_ticket, tiempo, descripcion, mes, None, grupo, es_hora_extra, now_created_at))
            
            success_count += 1
            
        except Exception as e:
            # Solo reportar errores que no sean por campos vacíos
            if not (is_empty_or_invalid(row.get('fecha')) and 
                   is_empty_or_invalid(row.get('tecnico')) and 
                   is_empty_or_invalid(row.get('cliente')) and 
                   is_empty_or_invalid(row.get('tipo_tarea')) and 
                   is_empty_or_invalid(row.get('modalidad'))):
                error_types['otros_errores'] += 1
                error_count += 1
            continue

    # Confirmar transacción y cerrar conexión
    conn.commit()
    conn.close()
    
    # Retornar los contadores de procesamiento
    return success_count, error_count, duplicate_count, missing_clients


def auto_assign_records_by_technician(conn):
    """Asigna automáticamente registros a usuarios basándose en el nombre del técnico"""
    from .admin_assignments import fix_existing_records_assignment_improved
    
    # Usar la función mejorada de asignación con umbral por defecto
    registros_asignados = fix_existing_records_assignment_improved(conn, umbral_minimo=70)
    
    return registros_asignados


def render_admin_settings():
    from .config import (
        POSTGRES_CONFIG,
        SMTP_CONFIG,
        NOTIFICATION_POLICIES_CONFIG,
        NOTIFICATION_POLICY_DEFINITIONS,
        NOTIFICATION_POLICY_FREQUENCIES,
        NOTIFICATION_POLICY_WEEKDAYS,
        NOTIFICATION_TEMPLATE_CONFIG,
        NOTIFICATION_TEMPLATES_CONFIG,
        NOTIFICATION_TEMPLATE_DEFINITIONS,
        UPLOADS_DIR,
        PROJECT_UPLOADS_DIR,
        encode_notification_policies,
        encode_notification_templates,
        update_env_values,
        reload_env,
        encode_env_multiline,
    )
    from .database import get_current_project_id_sequence, set_project_id_sequence, get_roles_dataframe, get_users_dataframe, update_rol_visibility
    from .utils import safe_rerun
    import html
    import re
    
    st.subheader("Administración")
    
    tabs_options = ["🔌 Conexiones", "✉️ SMTP y Notificaciones", "📅 Google Calendar", "📂 Configuración Proyectos", "💾 Backup & Restore", "👁️ Visibilidad Departamentos"]
    
    if "admin_active_tab" not in st.session_state:
        st.session_state.admin_active_tab = tabs_options[0]

    selected_admin_tab = st.segmented_control(
        "Secciones",
        tabs_options,
        key="admin_active_tab",
        label_visibility="collapsed"
    )
    
    if not selected_admin_tab:
        selected_admin_tab = tabs_options[0]
        
    st.divider()

    if selected_admin_tab == "👁️ Visibilidad Departamentos":
        st.markdown("### Configuración de Visibilidad de Departamentos")
        st.info("Marca los departamentos que deseas ocultar de las listas y menús principales.")
        
        # Cargar roles incluyendo ocultos
        roles_df = get_roles_dataframe(exclude_admin=True, exclude_hidden=False)
        
        if not roles_df.empty:
            # Asegurar que is_hidden sea bool
            roles_df['is_hidden'] = roles_df['is_hidden'].fillna(False).astype(bool)
            
            # Configurar editor
            edited_df = st.data_editor(
                roles_df[['id_rol', 'nombre', 'descripcion', 'is_hidden']],
                column_config={
                    "id_rol": st.column_config.NumberColumn("ID", disabled=True),
                    "nombre": st.column_config.TextColumn("Departamento", disabled=True),
                    "descripcion": st.column_config.TextColumn("Descripción", disabled=True),
                    "is_hidden": st.column_config.CheckboxColumn("¿Ocultar?", help="Si se marca, este departamento no aparecerá en los menús.")
                },
                hide_index=True,
                key="roles_visibility_editor",
                use_container_width=True
            )
            
            if st.button("Guardar Cambios de Visibilidad"):
                cambios = 0
                errores = 0
                
                for index, row in edited_df.iterrows():
                    # Verificar si hubo cambio respecto al original
                    original_hidden = roles_df.loc[roles_df['id_rol'] == row['id_rol'], 'is_hidden'].iloc[0]
                    if original_hidden != row['is_hidden']:
                        try:
                            success = update_rol_visibility(row['id_rol'], row['is_hidden'])
                            if success:
                                cambios += 1
                            else:
                                errores += 1
                        except Exception as e:
                            errores += 1
                
                if cambios > 0:
                    if errores > 0:
                        st.warning(f"Se actualizaron {cambios} roles, pero hubo {errores} errores.")
                    else:
                        st.success(f"✅ Visibilidad actualizada correctamente ({cambios} roles modificados).")
                        time.sleep(1)
                        safe_rerun()
                elif errores > 0:
                    st.error(f"Hubo {errores} errores al intentar actualizar.")
                else:
                    st.info("No se detectaron cambios para guardar.")
        else:
            st.info("No hay departamentos configurados.")

    if selected_admin_tab == "🔌 Conexiones":
        with st.form("admin_connections_form", clear_on_submit=False):
            st.markdown("**PostgreSQL**")
            col_conn1, col_conn2, col_conn3 = st.columns(3)
            with col_conn1:
                host = st.text_input("Host", value=POSTGRES_CONFIG['host'])
            with col_conn2:
                port = st.text_input("Puerto", value=str(POSTGRES_CONFIG['port']))
            with col_conn3:
                db   = st.text_input("Base de datos", value=POSTGRES_CONFIG['database'])
            
            col_auth1, col_auth2, col_auth3 = st.columns(3)
            with col_auth1:
                user = st.text_input("Usuario", value=POSTGRES_CONFIG['user'])
            with col_auth2:
                pwd  = st.text_input("Contraseña", value=POSTGRES_CONFIG['password'], type="password")
            with col_auth3:
                pwd_confirm = st.text_input("Confirmar Contraseña", value=POSTGRES_CONFIG['password'], type="password")
            
            update_sql = st.checkbox("Actualizar credenciales en PostgreSQL (ALTER USER)", value=False, 
                                   help="Si marcas esto, el sistema se conectará a la BD y ejecutará 'ALTER USER' para actualizar la contraseña del usuario especificado.")

            st.divider()
            st.markdown("**Rutas de almacenamiento**")
            uploads = st.text_input("Carpeta base de uploads (UPLOADS_DIR)", value=UPLOADS_DIR)
            proj_uploads = st.text_input("Carpeta de proyectos (PROJECT_UPLOADS_DIR)", value=PROJECT_UPLOADS_DIR)

            submitted = st.form_submit_button("Guardar configuración", type="primary")

        if submitted:
            # Validar contraseñas
            if pwd != pwd_confirm:
                st.error("❌ Las contraseñas no coinciden.")
            else:
                db_update_ok = True
                success_steps = []
                
                # Lógica de actualización SQL si se solicitó
                if update_sql:
                    try:
                        # Verificar que el usuario no esté vacío
                        if not user:
                            st.error("El usuario no puede estar vacío.")
                            db_update_ok = False
                        else:
                            conn = get_connection()
                            conn.autocommit = True
                            c = conn.cursor()
                            
                            # Sanitización básica
                            import re
                            if not re.match(r'^[a-zA-Z0-9_]+$', user):
                                raise Exception("Nombre de usuario contiene caracteres inválidos.")
                                
                            # Comprobar si el usuario existe
                            c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (user,))
                            if not c.fetchone():
                                st.warning(f"⚠️ El usuario '{user}' no existe en PostgreSQL. Se actualizará el .env pero la conexión fallará hasta que crees el usuario.")
                            else:
                                c.execute(f"ALTER USER {user} WITH PASSWORD %s", (pwd,))
                                success_steps.append("Contraseña actualizada en PostgreSQL.")
                            
                            conn.close()
                    except Exception as sql_e:
                        st.error(f"❌ Error SQL al actualizar base de datos: {sql_e}")
                        db_update_ok = False
                
                # Si la parte de BD salió bien (o no se solicitó), actualizar .env
                if db_update_ok:
                    ok = update_env_values({
                        "POSTGRES_HOST": host,
                        "POSTGRES_PORT": port,
                        "POSTGRES_DB": db,
                        "POSTGRES_USER": user,
                        "POSTGRES_PASSWORD": pwd,
                        "UPLOADS_DIR": uploads,
                        "PROJECT_UPLOADS_DIR": proj_uploads,
                    })
                    if ok:
                        reload_env()
                        success_steps.append("Configuración guardada en .env.")
                        st.success("✅ " + " ".join(success_steps))
                        st.info("Reinicia/recarga la app para asegurar que todas las conexiones usen los nuevos valores.")
                    else:
                        st.error("No se pudo escribir .env. Revisa permisos de archivo.")

    if selected_admin_tab == "✉️ SMTP y Notificaciones":
        st.markdown("### Configuración de notificaciones")
        notification_sections = ["📨 SMTP", "⏱️ Políticas", "📝 Plantillas"]
        if "admin_notification_section" not in st.session_state:
            st.session_state["admin_notification_section"] = notification_sections[0]
        selected_notification_section = st.segmented_control(
            "Configuración de notificaciones",
            notification_sections,
            key="admin_notification_section",
            label_visibility="collapsed",
        )
        if not selected_notification_section:
            selected_notification_section = notification_sections[0]

        if selected_notification_section == "📨 SMTP":
            st.info("Configura el envío de notificaciones por correo usando Gmail SMTP y una contraseña de aplicación.")

            smtp_security_labels = {
                "TLS / STARTTLS (Recomendado para Gmail)": "tls",
                "SSL / TLS": "ssl",
            }
            smtp_security_lookup = {v: k for k, v in smtp_security_labels.items()}
            current_security = SMTP_CONFIG.get("security", "tls")
            if current_security not in smtp_security_lookup:
                current_security = "tls"
            has_saved_password = bool(str(SMTP_CONFIG.get("password") or "").strip())

            with st.form("admin_smtp_settings_form", clear_on_submit=False):
                smtp_enabled = st.checkbox(
                    "Habilitar notificaciones por correo",
                    value=bool(SMTP_CONFIG.get("enabled", False)),
                    help="Activa el uso del servidor SMTP para futuros envíos de notificaciones."
                )

                col_smtp_1, col_smtp_2, col_smtp_3 = st.columns(3)
                with col_smtp_1:
                    smtp_host = st.text_input("Servidor SMTP", value=str(SMTP_CONFIG.get("host") or "smtp.gmail.com"))
                with col_smtp_2:
                    smtp_port = st.text_input("Puerto", value=str(SMTP_CONFIG.get("port") or "587"))
                with col_smtp_3:
                    smtp_security_label = st.selectbox(
                        "Seguridad",
                        options=list(smtp_security_labels.keys()),
                        index=list(smtp_security_labels.values()).index(current_security)
                    )

                col_mail_1, col_mail_2 = st.columns(2)
                with col_mail_1:
                    smtp_from_email = st.text_input(
                        "Correo remitente",
                        value=str(SMTP_CONFIG.get("from_email") or "")
                    )
                with col_mail_2:
                    smtp_from_name = st.text_input(
                        "Nombre visible del remitente",
                        value=str(SMTP_CONFIG.get("from_name") or "SIGO")
                    )

                col_auth_1, col_auth_2 = st.columns(2)
                with col_auth_1:
                    smtp_user = st.text_input(
                        "Usuario SMTP",
                        value=str(SMTP_CONFIG.get("user") or ""),
                        help="En Gmail suele ser la misma dirección de correo remitente."
                    )
                with col_auth_2:
                    smtp_password = st.text_input(
                        "Contraseña de aplicación de Gmail",
                        value="",
                        type="password",
                        help="Por seguridad no se muestra la actual. Déjalo vacío para conservar la contraseña guardada."
                    )

                smtp_password_confirm = st.text_input(
                    "Confirmar contraseña de aplicación",
                    value="",
                    type="password"
                )

                if has_saved_password:
                    st.caption("Ya existe una contraseña SMTP guardada. Si no deseas cambiarla, deja ambos campos de contraseña vacíos.")

                submitted_smtp = st.form_submit_button("Guardar configuración SMTP", type="primary")

            if submitted_smtp:
                errors = []
                smtp_host = (smtp_host or "").strip()
                smtp_port = (smtp_port or "").strip()
                smtp_from_email = (smtp_from_email or "").strip()
                smtp_from_name = " ".join(str(smtp_from_name or "").split()).strip()
                smtp_user = (smtp_user or "").strip()
                smtp_security = smtp_security_labels[smtp_security_label]
                effective_password = smtp_password if str(smtp_password).strip() else str(SMTP_CONFIG.get("password") or "")

                if smtp_password != smtp_password_confirm:
                    errors.append("Las contraseñas SMTP no coinciden.")

                if smtp_port and not smtp_port.isdigit():
                    errors.append("El puerto SMTP debe ser numérico.")
                elif smtp_port and not (1 <= int(smtp_port) <= 65535):
                    errors.append("El puerto SMTP debe estar entre 1 y 65535.")

                email_pattern = r"[^@]+@[^@]+\.[^@]+"
                if smtp_from_email and not re.match(email_pattern, smtp_from_email):
                    errors.append("El correo remitente no tiene un formato válido.")
                if smtp_user and not re.match(email_pattern, smtp_user):
                    errors.append("El usuario SMTP debe ser un email válido.")

                if smtp_enabled:
                    if not smtp_host:
                        errors.append("El servidor SMTP es obligatorio cuando el envío está habilitado.")
                    if not smtp_port:
                        errors.append("El puerto SMTP es obligatorio cuando el envío está habilitado.")
                    if not smtp_from_email:
                        errors.append("El correo remitente es obligatorio cuando el envío está habilitado.")
                    if not smtp_user:
                        errors.append("El usuario SMTP es obligatorio cuando el envío está habilitado.")
                    if not effective_password:
                        errors.append("Debes cargar la contraseña de aplicación de Gmail para habilitar el SMTP.")
                    if smtp_from_email and smtp_user and smtp_from_email.casefold() != smtp_user.casefold():
                        st.warning("En Gmail normalmente conviene que el remitente y el usuario SMTP sean la misma cuenta.")

                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    ok = update_env_values({
                        "SMTP_ENABLED": str(bool(smtp_enabled)).lower(),
                        "SMTP_HOST": smtp_host,
                        "SMTP_PORT": smtp_port,
                        "SMTP_SECURITY": smtp_security,
                        "SMTP_FROM_EMAIL": smtp_from_email,
                        "SMTP_FROM_NAME": smtp_from_name,
                        "SMTP_USER": smtp_user,
                        "SMTP_PASSWORD": effective_password,
                    })
                    if ok:
                        reload_env()
                        st.success("✅ Configuración SMTP guardada correctamente.")
                        if smtp_enabled:
                            st.info("Para Gmail usa verificación en dos pasos y una contraseña de aplicación activa en la cuenta emisora.")
                    else:
                        st.error("No se pudo escribir la configuración SMTP en .env. Revisa permisos del archivo.")

            if bool(SMTP_CONFIG.get("enabled")):
                st.caption("El mensaje de prueba usa la configuración SMTP ya guardada y envía el correo a la misma cuenta configurada.")
                if st.button("Enviar mensaje de prueba", key="admin_smtp_test_message_button"):
                    try:
                        test_recipient = send_test_notification_email()
                        st.success(f"✅ Mensaje de prueba enviado a {test_recipient}.")
                    except Exception as e:
                        st.error(f"No se pudo enviar el mensaje de prueba: {e}")

        if selected_notification_section == "⏱️ Políticas":
            st.info("Configura la periodicidad del correo por evento. Las alertas continuas conviene agruparlas para evitar envíos repetidos.")
            policy_labels = {
                definition["label"]: policy_key
                for policy_key, definition in NOTIFICATION_POLICY_DEFINITIONS.items()
            }
            policy_label_options = list(policy_labels.keys())
            current_policy_key = st.session_state.get("admin_notification_policy_key", "dia_pendiente_carga")
            current_policy_labels = {value: label for label, value in policy_labels.items()}
            default_policy_index = 0
            if current_policy_key in current_policy_labels:
                default_policy_index = policy_label_options.index(current_policy_labels[current_policy_key])

            selected_policy_label = st.selectbox(
                "Evento de notificación",
                options=policy_label_options,
                index=default_policy_index,
                key="admin_notification_policy_key_selector"
            )
            selected_policy_key = policy_labels[selected_policy_label]
            st.session_state["admin_notification_policy_key"] = selected_policy_key

            policy_definition = NOTIFICATION_POLICY_DEFINITIONS[selected_policy_key]
            policy_config = dict(NOTIFICATION_POLICIES_CONFIG.get(selected_policy_key) or policy_definition["default"])
            frequency_labels = {
                NOTIFICATION_POLICY_FREQUENCIES[frequency_key].capitalize(): frequency_key
                for frequency_key in policy_definition["allowed_frequencies"]
            }
            current_frequency = str(policy_config.get("frequency") or policy_definition["default"]["frequency"]).strip().lower()
            if current_frequency not in frequency_labels.values():
                current_frequency = policy_definition["default"]["frequency"]
            frequency_options = list(frequency_labels.keys())
            weekday_labels = {
                weekday_label.capitalize(): weekday_key
                for weekday_key, weekday_label in NOTIFICATION_POLICY_WEEKDAYS.items()
            }
            current_weekday = str(policy_config.get("weekday") or policy_definition["default"]["weekday"]).strip().lower()
            if current_weekday not in weekday_labels.values():
                current_weekday = policy_definition["default"]["weekday"]

            st.info(policy_definition["description"])
            st.markdown(
                f"**Plantilla asociada:** {NOTIFICATION_TEMPLATE_DEFINITIONS.get(selected_policy_key, NOTIFICATION_TEMPLATE_DEFINITIONS['default'])['label']}"
            )
            if current_frequency == "immediate":
                st.caption("Modo actual: envío apenas ocurre el evento, con control de duplicado por evento.")
            elif current_frequency == "daily":
                st.caption("Modo actual: resumen diario con una sola entrega por usuario y fecha.")
            else:
                weekday_name = NOTIFICATION_POLICY_WEEKDAYS.get(current_weekday, "lunes")
                st.caption(f"Modo actual: resumen semanal con corte el {weekday_name} y una sola entrega por semana.")

            current_target_scope = str(policy_config.get("target_scope") or "all").strip().lower()
            if current_target_scope not in {"all", "roles", "users"}:
                current_target_scope = "all"
            current_target_role_ids = policy_config.get("target_role_ids") or []
            if not isinstance(current_target_role_ids, list):
                current_target_role_ids = []
            current_target_user_ids = policy_config.get("target_user_ids") or []
            if not isinstance(current_target_user_ids, list):
                current_target_user_ids = []

            target_scope_labels = {
                "Todos": "all",
                "Rol": "roles",
                "Usuario": "users",
            }
            target_scope_options = list(target_scope_labels.keys())
            selected_target_scope_label = st.selectbox(
                "Aplicar a",
                options=target_scope_options,
                index=list(target_scope_labels.values()).index(current_target_scope),
                key=f"admin_notify_target_scope_{selected_policy_key}",
            )
            selected_target_scope = target_scope_labels[selected_target_scope_label]

            with st.form("admin_notification_policy_form", clear_on_submit=False):
                selected_target_role_ids = []
                selected_target_user_ids = []
                role_ids = []
                role_id_to_label = {}
                user_ids = []
                user_id_to_label = {}
                if selected_target_scope == "roles":
                    roles_df_for_targets = _cached_roles_dataframe_for_targets()
                    if not roles_df_for_targets.empty:
                        for _, row in roles_df_for_targets.iterrows():
                            try:
                                rid = int(row.get("id_rol"))
                            except Exception:
                                continue
                            label = str(row.get("nombre") or "").strip() or str(rid)
                            role_ids.append(rid)
                            role_id_to_label[rid] = label
                    default_role_ids = []
                    for rid in current_target_role_ids:
                        try:
                            rid_int = int(rid)
                        except Exception:
                            continue
                        if rid_int in role_ids and rid_int not in default_role_ids:
                            default_role_ids.append(rid_int)
                    selected_target_role_ids = st.multiselect(
                        "Roles",
                        options=role_ids,
                        default=default_role_ids,
                        format_func=lambda rid: role_id_to_label.get(rid, str(rid)),
                        key=f"admin_notify_target_roles_{selected_policy_key}",
                    )
                elif selected_target_scope == "users":
                    users_df_for_targets = _cached_users_dataframe_for_targets()
                    users_df_for_targets = (
                        users_df_for_targets[users_df_for_targets.get("is_active", True) == True]
                        if not users_df_for_targets.empty
                        else users_df_for_targets
                    )
                    if not users_df_for_targets.empty:
                        for _, row in users_df_for_targets.iterrows():
                            try:
                                uid = int(row.get("id"))
                            except Exception:
                                continue
                            nombre = str(row.get("nombre") or "").strip()
                            apellido = str(row.get("apellido") or "").strip()
                            username = str(row.get("username") or "").strip()
                            display = " ".join(part for part in [apellido, nombre] if part).strip()
                            if username:
                                display = f"{display} ({username})" if display else username
                            user_ids.append(uid)
                            user_id_to_label[uid] = display or str(uid)
                    default_user_ids = []
                    for uid in current_target_user_ids:
                        try:
                            uid_int = int(uid)
                        except Exception:
                            continue
                        if uid_int in user_ids and uid_int not in default_user_ids:
                            default_user_ids.append(uid_int)
                    selected_target_user_ids = st.multiselect(
                        "Usuarios",
                        options=user_ids,
                        default=default_user_ids,
                        format_func=lambda uid: user_id_to_label.get(uid, str(uid)),
                        key=f"admin_notify_target_users_{selected_policy_key}",
                    )

                policy_enabled = st.checkbox(
                    "Habilitar esta política",
                    value=bool(policy_config.get("enabled", True)),
                    help="Desactívala si no deseas que este evento participe en el flujo de correo."
                )
                policy_email_enabled = st.checkbox(
                    "Enviar por correo",
                    value=bool(policy_config.get("email_enabled", True)),
                    help="Mantiene disponible la regla pero sin usar el canal email."
                )

                selected_frequency_label = st.selectbox(
                    "Frecuencia de envío",
                    options=frequency_options,
                    index=frequency_options.index(NOTIFICATION_POLICY_FREQUENCIES[current_frequency].capitalize())
                )
                selected_frequency = frequency_labels[selected_frequency_label]
                policy_send_time = st.text_input(
                    "Hora de envío (HH:MM)",
                    value=str(policy_config.get("send_time") or policy_definition["default"]["send_time"]),
                    disabled=selected_frequency == "immediate",
                    help="Se usa en políticas diarias o semanales."
                )
                selected_weekday_label = st.selectbox(
                    "Día de corte semanal",
                    options=list(weekday_labels.keys()),
                    index=list(weekday_labels.values()).index(current_weekday),
                    disabled=selected_frequency != "weekly"
                )
                selected_weekday = weekday_labels[selected_weekday_label]

                submitted_policy = st.form_submit_button("Guardar política", type="primary")

            if submitted_policy:
                policy_errors = []
                policy_send_time = str(policy_send_time or "").strip()
                if selected_target_scope == "roles" and not (selected_target_role_ids or []):
                    policy_errors.append("Selecciona al menos un rol para aplicar esta política.")
                if selected_target_scope == "users" and not (selected_target_user_ids or []):
                    policy_errors.append("Selecciona al menos un usuario para aplicar esta política.")
                if selected_frequency != "immediate":
                    if not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", policy_send_time):
                        policy_errors.append("La hora de envío debe tener formato HH:MM.")
                else:
                    policy_send_time = policy_definition["default"]["send_time"]

                if policy_errors:
                    for error in policy_errors:
                        st.error(error)
                else:
                    updated_policies = {
                        policy_key: dict(policy_value)
                        for policy_key, policy_value in NOTIFICATION_POLICIES_CONFIG.items()
                    }
                    updated_policies[selected_policy_key] = {
                        "enabled": bool(policy_enabled),
                        "email_enabled": bool(policy_email_enabled),
                        "target_scope": selected_target_scope,
                        "target_role_ids": [int(rid) for rid in (selected_target_role_ids or [])] if selected_target_scope == "roles" else [],
                        "target_user_ids": [int(uid) for uid in (selected_target_user_ids or [])] if selected_target_scope == "users" else [],
                        "frequency": selected_frequency,
                        "send_time": policy_send_time,
                        "weekday": selected_weekday,
                    }
                    ok = update_env_values({
                        "NOTIFY_POLICIES": encode_notification_policies(updated_policies),
                    })
                    if ok:
                        reload_env()
                        st.success(f"✅ Política '{policy_definition['label']}' guardada correctamente.")
                    else:
                        st.error("No se pudo escribir la configuración de políticas en .env. Revisa permisos del archivo.")

        if selected_notification_section == "📝 Plantillas":
            st.caption("Puedes mantener una plantilla general y varias específicas según el tipo de evento.")

            template_labels = {
                definition["label"]: template_key
                for template_key, definition in NOTIFICATION_TEMPLATE_DEFINITIONS.items()
            }
            template_label_options = list(template_labels.keys())
            current_template_key = st.session_state.get("admin_notification_template_key", "default")
            current_template_labels = {value: label for label, value in template_labels.items()}
            default_template_index = 0
            if current_template_key in current_template_labels:
                default_template_index = template_label_options.index(current_template_labels[current_template_key])

            selected_template_label = st.selectbox(
                "Tipo de notificación",
                options=template_label_options,
                index=default_template_index,
                key="admin_notification_template_key_selector"
            )
            selected_template_key = template_labels[selected_template_label]
            st.session_state["admin_notification_template_key"] = selected_template_key

            template_definition = NOTIFICATION_TEMPLATE_DEFINITIONS[selected_template_key]
            template_config = dict(
                NOTIFICATION_TEMPLATES_CONFIG.get(selected_template_key)
                or NOTIFICATION_TEMPLATE_CONFIG
            )
            placeholder_descriptions = {
                "{nombre}": "Nombre del destinatario.",
                "{usuario}": "Usuario asociado a la notificación.",
                "{email}": "Correo del destinatario.",
                "{evento}": "Nombre del evento disparado.",
                "{detalle}": "Detalle resumido del evento.",
                "{fecha}": "Fecha del evento.",
                "{empresa}": "Nombre de la empresa o sistema.",
                "{solicitante}": "Usuario que creó la solicitud.",
                "{cliente}": "Nombre del cliente relacionado.",
                "{cuit}": "CUIT del cliente.",
                "{telefono}": "Teléfono del cliente.",
                "{aprobador}": "Usuario que aprobó o rechazó.",
                "{trato}": "Nombre del trato comercial.",
                "{fecha_cierre}": "Fecha de cierre del trato.",
                "{dias_restantes}": "Cantidad de días faltantes al vencimiento.",
                "{dias_vencido}": "Cantidad de días desde el vencimiento.",
                "{estado}": "Estado actual del trato.",
                "{periodo}": "Período que resume la alerta, por ejemplo mes en curso.",
                "{cantidad_alertas}": "Cantidad total de alertas incluidas en el correo.",
                "{resumen_alertas}": "Listado consolidado de fechas o pendientes detectados.",
                "{hoy_dia}": "Día de la semana (ej. Miércoles).",
                "{hoy_fecha}": "Fecha del día (DD/MM).",
                "{presentes_resumen}": "Listado de personas asignadas hoy en la oficina según planificación.",
                "{seccion_licencias}": "Sección opcional con licencias/vacaciones de la semana (vacío si no hay).",
                "{umbral_horas}": "Umbral mínimo de horas por día (lun-vie) para considerar carga completa.",
                "{cantidad_tecnicos}": "Cantidad de técnicos que presentan carga incompleta en el período.",
                "{resumen_tecnicos}": "Resumen de técnicos con carga incompleta (ej. '- Nombre (8)').",
                "{detalle_tecnicos}": "Detalle por técnico con los días detectados y su estado.",
            }

            st.info(template_definition["description"])
            st.markdown("**Etiquetas disponibles**")
            placeholders_html = "".join(
                (
                    f"<span title='{html.escape(placeholder_descriptions.get(placeholder, 'Variable disponible para esta plantilla.'), quote=True)}' "
                    "style='display:inline-flex;align-items:center;padding:0.35rem 0.75rem;border-radius:999px;"
                    "background:rgba(236,72,153,0.18);border:1px solid rgba(244,114,182,0.55);color:#f9a8d4;"
                    "font-weight:600;font-size:0.9rem;cursor:help;'>"
                    f"{html.escape(placeholder)}</span>"
                )
                for placeholder in template_definition["placeholders"]
            )
            st.markdown(
                (
                    "<div style='display:flex;flex-wrap:wrap;gap:0.5rem;"
                    "padding:0.35rem 0 1rem 0;'>"
                    f"{placeholders_html}"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

            with st.form("admin_notification_template_form", clear_on_submit=False):
                if selected_template_key == "default":
                    st.checkbox(
                        "Plantilla de respaldo activa",
                        value=True,
                        disabled=True,
                        help="Esta plantilla se usa cuando un evento no tiene una configuración específica."
                    )
                    template_enabled = True
                else:
                    template_enabled = st.checkbox(
                        "Habilitar esta plantilla",
                        value=bool(template_config.get("enabled", True)),
                        help="Si la desactivas, el sistema podrá usar la plantilla por defecto para este evento."
                    )

                template_subject = st.text_input(
                    "Asunto",
                    value=str(template_config.get("subject") or template_definition["subject"])
                )
                template_body = st.text_area(
                    "Cuerpo",
                    value=str(template_config.get("body") or template_definition["body"]),
                    height=240
                )

                submitted_template = st.form_submit_button("Guardar plantilla", type="primary")

            if submitted_template:
                template_errors = []
                template_subject = " ".join(str(template_subject or "").split()).strip()
                template_body = str(template_body or "").strip()

                if not template_subject:
                    template_errors.append("El asunto de la plantilla es obligatorio.")
                if not template_body:
                    template_errors.append("El cuerpo de la plantilla es obligatorio.")

                if template_errors:
                    for error in template_errors:
                        st.error(error)
                else:
                    updated_templates = {
                        template_key: dict(template_value)
                        for template_key, template_value in NOTIFICATION_TEMPLATES_CONFIG.items()
                    }
                    updated_templates[selected_template_key] = {
                        "enabled": bool(template_enabled),
                        "subject": template_subject,
                        "body": template_body,
                    }
                    default_template = updated_templates.get("default", NOTIFICATION_TEMPLATE_CONFIG)
                    ok = update_env_values({
                        "NOTIFY_TEMPLATES": encode_notification_templates(updated_templates),
                        "NOTIFY_TEMPLATE_SUBJECT": default_template.get("subject", "Nueva notificación de SIGO"),
                        "NOTIFY_TEMPLATE_BODY": encode_env_multiline(default_template.get("body", "")),
                    })
                    if ok:
                        reload_env()
                        st.success(f"✅ Plantilla '{template_definition['label']}' guardada correctamente.")
                    else:
                        st.error("No se pudo escribir la configuración de plantillas en .env. Revisa permisos del archivo.")

    if selected_admin_tab == "📅 Google Calendar":
        st.markdown("### Integración de Google Calendar")
        st.info("Configura la conexión con la API de Google Calendar mediante OAuth 2.0. Esto permitirá la sincronización e interacción de calendarios directamente desde el sistema.")

        callback_notice = st.session_state.pop("google_calendar_callback_notice", None)
        if isinstance(callback_notice, dict):
            notice_level = str(callback_notice.get("level") or "info").strip().lower()
            notice_message = str(callback_notice.get("message") or "").strip()
            if notice_message:
                if notice_level == "success":
                    st.success(notice_message)
                elif notice_level == "warning":
                    st.warning(notice_message)
                elif notice_level == "error":
                    st.error(notice_message)
                else:
                    st.info(notice_message)

        # Obtener el estado actual
        from .database import get_google_calendar_status, save_google_calendar_config, delete_google_calendar_config
        try:
            from .google_calendar import build_oauth_authorization_url, get_user_calendar, google_calendar_available
        except Exception as _gcal_exc:  # pragma: no cover - resguardo frente a cualquier error de import
            build_oauth_authorization_url = None
            get_user_calendar = None
            google_calendar_available = False
            import logging as _gcal_log
            _gcal_log.getLogger(__name__).warning(
                "Google Calendar no disponible en admin_settings: %s", _gcal_exc
            )

        if not google_calendar_available:
            st.warning(
                "⚠️ La integración con Google Calendar no está disponible. "
                "Faltan las dependencias opcionales de Google (google-auth, google-api-python-client). "
                "Instalarlas con: `pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client` "
                "y reiniciar la app."
            )
            st.info(
                "Mientras tanto, el resto del panel de administración y el sistema SIGO siguen funcionando normalmente."
            )
        else:
            status = get_google_calendar_status()

            # Mostrar el estado actual
            col_status1, col_status2 = st.columns(2)
            with col_status1:
                st.markdown("#### 🔑 Credenciales de la Aplicación")
                if status['credentials_uploaded']:
                    st.success("✅ Credenciales de API cargadas")
                    date_str = status['credentials_date'].strftime("%d/%m/%Y %H:%M") if status['credentials_date'] else "-"
                    user_str = status['credentials_user'] if status['credentials_user'] else "Desconocido"
                    st.markdown(f"**Fecha de carga:** {date_str}")
                    st.markdown(f"**Cargado por:** {user_str}")
                else:
                    st.warning("⚠️ No se han cargado las credenciales de API (client_secret.json)")
                    
            with col_status2:
                st.markdown("#### 🔗 Vinculación de Cuenta")
                if status['token_valid']:
                    st.success("✅ Cuenta de Google vinculada y autorizada")
                    date_str = status['token_date'].strftime("%d/%m/%Y %H:%M") if status['token_date'] else "-"
                    st.markdown(f"**Última sincronización:** {date_str}")
                else:
                    st.warning("⚠️ Cuenta de Google no vinculada o autorización expirada")

            st.divider()

            # Crear dos columnas para las acciones
            col_action1, col_action2 = st.columns(2)

            with col_action1:
                st.markdown("#### 📥 Cargar/Reemplazar Credenciales JSON")
                st.caption("Sube el archivo JSON de credenciales OAuth descargado de Google Cloud Console (credentials.json o client_secret*.json).")
                
                uploaded_json = st.file_uploader("Seleccione archivo de credenciales (.json)", type=["json"], key="google_credentials_uploader")

                # Usar un flag en session_state para evitar re-procesar el archivo en cada rerun
                if uploaded_json is not None:
                    file_id = uploaded_json.file_id
                    if st.session_state.get('gcal_last_uploaded_file_id') != file_id:
                        try:
                            import json
                            cred_content = json.load(uploaded_json)

                            # Validar estructura de Google OAuth
                            is_valid = False
                            if isinstance(cred_content, dict):
                                if "web" in cred_content:
                                    web_cfg = cred_content["web"]
                                    required = ["client_id", "client_secret", "auth_uri", "token_uri"]
                                    is_valid = all(k in web_cfg for k in required)
                                elif "installed" in cred_content:
                                    inst_cfg = cred_content["installed"]
                                    required = ["client_id", "client_secret", "auth_uri", "token_uri"]
                                    is_valid = all(k in inst_cfg for k in required)

                            if not is_valid:
                                st.error("❌ El archivo JSON no es un archivo de credenciales OAuth válido de Google (debe contener la clave 'web' o 'installed' con client_id y client_secret).")
                            else:
                                user_id = st.session_state.get('user_id')
                                if save_google_calendar_config('client_credentials', cred_content, user_id):
                                    # Marcar como procesado para no repetir en el próximo rerun
                                    st.session_state['gcal_last_uploaded_file_id'] = file_id
                                    st.toast("✅ Credenciales de Google Calendar guardadas correctamente.", icon="🔑")
                                    st.rerun()
                                else:
                                    st.error("❌ Error al guardar las credenciales en la base de datos.")
                        except Exception as ex:
                            st.error(f"❌ Error al procesar el archivo JSON: {str(ex)}")
                    else:
                        st.success("✅ Credenciales cargadas y almacenadas correctamente.")

            with col_action2:
                st.markdown("#### 🔌 Acciones de Conexión")
                
                if status['credentials_uploaded']:
                    if not status['token_valid']:
                        st.write("Para sincronizar los calendarios, debes autorizar el acceso a tu cuenta de Google.")
                        
                        host = st.context.headers.get("host", "localhost:8501")
                        proto = st.context.headers.get("x-forwarded-proto", "http")
                        redirect_uri = f"{proto}://{host}/"

                        try:
                            auth_url = build_oauth_authorization_url(redirect_uri, st.session_state.get('user_id'))
                            if auth_url:
                                st.link_button("🔑 Vincular Cuenta de Google", auth_url, type="primary", use_container_width=True)
                                st.caption(f"Asegúrese de agregar esta URI de redirección autorizada en Google Cloud Console: `{redirect_uri}`")
                            else:
                                st.error("No se pudo iniciar el flujo de autenticación. Verifique las credenciales.")
                        except Exception as e:
                            st.error(f"Error al generar URL de autorización: {str(e)}")
                    else:
                        st.write("La cuenta está vinculada. Puede verificar si la conexión sigue siendo activa o desvincularla.")
                        
                        if st.button("🔌 Probar Conexión con Google Calendar", use_container_width=True):
                            try:
                                cal_info = get_user_calendar(user_id=st.session_state.user_id)
                                st.success(f"✅ ¡Conexión exitosa! Calendario principal: **{cal_info.get('summary')}** (ID: {cal_info.get('id')})")
                            except Exception as e:
                                st.error(f"❌ Error de conexión: {str(e)}")
                                st.info("Si la autorización ha sido revocada, intente desvincular y volver a vincular la cuenta.")
                else:
                    st.info("Primero debe subir el archivo JSON de credenciales de Google para habilitar la vinculación de cuenta.")

            if status['credentials_uploaded'] or status['token_valid']:
                st.divider()
                st.markdown("#### 🗑️ Restablecer Configuración")
                st.write("Si desea eliminar completamente las credenciales y el token de acceso de la aplicación, utilice el siguiente botón. Esto detendrá toda sincronización con Google Calendar.")
                
                with st.expander("⚠️ Zona de Peligro - Eliminar Configuración", expanded=False):
                    st.write("Esta acción borrará de forma permanente los secretos y tokens de acceso almacenados en la base de datos.")
                    confirm = st.checkbox("Confirmo que deseo eliminar la configuración de Google Calendar")
                    if st.button("Eliminar Configuración por Completo", type="primary", disabled=not confirm):
                        ok_cred = delete_google_calendar_config('client_credentials')
                        ok_tok = delete_google_calendar_config('oauth_token')
                        if ok_cred or ok_tok:
                            st.success("✅ Configuración de Google Calendar eliminada con éxito.")
                            time.sleep(1)
                            safe_rerun()
                        else:
                            st.error("No se encontró configuración para eliminar.")

    if selected_admin_tab == "📂 Configuración Proyectos":
        st.subheader("Secuencia de IDs de Proyectos")
        st.info("Aquí puedes definir el número con el que comenzarán los IDs de los nuevos proyectos. Útil si migras de otro sistema.")
        
        current_seq = get_current_project_id_sequence()
        st.metric("Último ID generado (aprox)", current_seq)
        
        with st.form("admin_projects_seq_form"):
            new_start_val = st.number_input("Próximo ID de Proyecto", min_value=1, value=current_seq + 1, step=1, help="El siguiente proyecto creado tendrá este ID.")
            
            submit_seq = st.form_submit_button("Actualizar Secuencia")
            
            if submit_seq:
                success, msg = set_project_id_sequence(new_start_val)
                if success:
                    show_success_message(msg, 1)
                    safe_rerun()
                else:
                    st.error(f"Error: {msg}")

    # ===== INICIALIZACIÓN DE FLAGS GLOBALES DE RESTORE =====
    # Siempre inicializados, incluso antes de entrar a la pestaña Backup & Restore.
    # Esto evita AttributeError cuando un @st.dialog que se definió adentro de un
    # condicional hace safe_rerun() y Streamlit evalúa atributos que todavía no
    # entraron al bloque if de su definición.
    for _k, _default in (
        ("restore_in_progress", False),
        ("restore_pending_confirm", False),
        ("restore_result", None),
        ("restore_file_bytes", None),
    ):
        if _k not in st.session_state:
            st.session_state[_k] = _default

    if selected_admin_tab == "💾 Backup & Restore":
        st.subheader("Respaldo y Restauración del Sistema")
        st.warning("⚠️ Estas operaciones son críticas. Asegúrate de saber lo que haces.")
        
        col_backup, col_restore = st.columns(2)
        
        with col_backup:
            st.markdown("### 📥 Exportar Backup")
            st.info("Genera un archivo Excel (.xlsx) con TODAS las tablas de la base de datos.")
            
            if st.button("Generar Respaldo Completo"):
                with st.spinner("Generando archivo de respaldo..."):
                    excel_file = create_full_backup_excel()
                    if excel_file:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        st.download_button(
                            label="⬇️ Descargar Backup (.xlsx)",
                            data=excel_file,
                            file_name=f"backup_sigo_full_{timestamp}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                        st.success("Respaldo generado correctamente.")
                    else:
                        st.error("Error al generar el respaldo.")

        with col_restore:
            st.markdown("### 📤 Restaurar Backup")
            st.error("PELIGRO: Esto borrará TODOS los datos actuales y los reemplazará con el backup.")

            # ====== DIÁLOGOS (todos definidos FUERA de condicionales para evitar
            #         superposiciones / leaks de dialogs al rerun) ======

            # ====== FLAGS INTERMEDIOS para NO mostrar st.warning/st.success/st.code
            #         DENTRO de callbacks if st.button(): (evita warnings
            #         "fragment rerun was triggered with a callback that displays
            #         one or more elements" que salen en la consola)
            for _k, _default in (
                ("restore_pending_warning_confirm", False),
                ("restore_pending_open_confirm_dialog", None),  # bytes del Excel
                ("restore_pending_filename", None),             # nombre visual Excel
            ):
                if _k not in st.session_state:
                    st.session_state[_k] = _default

            # --- Handler común del botón "Continuar" (resultados success / error) ---
            # TRABAJO MÍNIMO dentro del callback: solo limpiar keys y rerun.
            def _finalize_restore_and_clear_all():
                for k in (
                    "restore_in_progress",
                    "restore_pending_confirm",
                    "restore_result",
                    "restore_file_bytes",
                    "backup_uploader",
                    "backup_confirm_checkbox",
                ):
                    if k in st.session_state:
                        del st.session_state[k]
                st.session_state["restore_pending_cache_cleanup"] = True
                safe_rerun()

            # Luego de cerrar el dialog de resultado, SI se seteó el flag anterior,
            # limpiamos las cachés en el cuerpo PRINCIPAL del render (no en un
            # button callback), sin que el usuario perciba delay en el dialog.
            if st.session_state.get("restore_pending_cache_cleanup"):
                try:
                    clear_restore_related_caches()
                except Exception:
                    pass
                try:
                    del st.session_state["restore_pending_cache_cleanup"]
                except Exception:
                    pass

            # ==== DIÁLOGOS DE RESULTADO (success y error) ====
            # NOTA: NO usamos on_click= en los botones porque dentro de @st.dialog
            # st.rerun() dentro de un callback es NO-OP → no hace nada.
            # Usamos if st.button(): <handler> (sin on_click) como todos los demás
            # botones del proyecto (Cancelar/Restaurar en confirm dialog).
            @st.dialog("✅ Restauración Finalizada")
            def _show_restore_success_dialog(msg: str):
                st.success(msg or "Restauración completada exitosamente.")
                if st.button("Continuar", type="primary", use_container_width=True):
                    _finalize_restore_and_clear_all()

            @st.dialog("⚠️ Error en Restauración")
            def _show_restore_error_dialog(msg: str):
                st.error(msg or "Ocurrió un error desconocido.")
                if st.button("Continuar", type="secondary", use_container_width=True):
                    _finalize_restore_and_clear_all()

            # ==== DIÁLOGO DE CONFIRMACIÓN (definido FUERA de condicionales) ====
            # SCOPEADO CON .restore-confirm-dialog.
            #
            # IMPORTANTE: NO recibe file_obj por parámetro.
            # Lee bytes + nombre desde st.session_state (restore_pending_*).
            # Esto evita tener que pasar uploaded_file dentro de if st.button(): 
            # (lo cual dispara warnings de fragment rerun porque el objeto 
            # uploaded_file tiene elementos display asociados).
            @st.dialog("⚠️ Confirmación Final de Restauración")
            def show_restore_confirmation():
                BTN_HEIGHT = "48px"
                BTN_WIDTH = "100%"
                BTN_FONT_SIZE = "16px"

                CANCEL_BTN_BG_COLOR = "#262730"
                CANCEL_BTN_TEXT_COLOR = "#FFFFFF"
                CANCEL_BTN_BORDER_COLOR = "#31333F"

                RESTORE_BTN_BG_COLOR = "#FF4B4B"
                RESTORE_BTN_TEXT_COLOR = "#FFFFFF"
                RESTORE_BTN_BORDER_COLOR = "#FF4B4B"

                st.markdown(f"""
                    <div class="restore-confirm-dialog">
                    <style>
                    .restore-confirm-dialog * {{
                        box-sizing: border-box !important;
                    }}
                    .restore-confirm-dialog button,
                    div[data-testid="stDialog"]:has(.restore-confirm-dialog) button {{
                        height: {BTN_HEIGHT} !important;
                        min-height: {BTN_HEIGHT} !important;
                        max-height: {BTN_HEIGHT} !important;
                        width: {BTN_WIDTH} !important;
                        padding: 0px 16px !important;
                        font-size: {BTN_FONT_SIZE} !important;
                        font-weight: 600 !important;
                        line-height: 1 !important;
                        border-radius: 8px !important;
                        border-width: 1px !important;
                        border-style: solid !important;
                        display: flex !important;
                        align-items: center !important;
                        justify-content: center !important;
                        margin: 0px !important;
                        box-sizing: border-box !important;
                    }}
                    div[data-testid="stDialog"]:has(.restore-confirm-dialog) 
                        button[kind="primary"],
                    div[data-testid="stDialog"]:has(.restore-confirm-dialog) 
                        button[kind="secondary"] {{
                            height: {BTN_HEIGHT} !important;
                            min-height: {BTN_HEIGHT} !important;
                            max-height: {BTN_HEIGHT} !important;
                    }}
                    .restore-confirm-dialog button p,
                    div[data-testid="stDialog"]:has(.restore-confirm-dialog) button p {{
                        line-height: 1.5 !important;
                        margin: 0 !important;
                        padding: 0 !important;
                    }}
                    div[data-testid="stDialog"]:has(.restore-confirm-dialog) 
                        div[data-testid="stHorizontalBlock"] > div:nth-child(1) button {{
                            background-color: {CANCEL_BTN_BG_COLOR} !important;
                            color: {CANCEL_BTN_TEXT_COLOR} !important;
                            border-color: {CANCEL_BTN_BORDER_COLOR} !important;
                    }}
                    div[data-testid="stDialog"]:has(.restore-confirm-dialog) 
                        div[data-testid="stHorizontalBlock"] > div:nth-child(1) button:hover {{
                            border-color: {CANCEL_BTN_TEXT_COLOR} !important;
                            filter: brightness(1.2);
                    }}
                    div[data-testid="stDialog"]:has(.restore-confirm-dialog) 
                        div[data-testid="stHorizontalBlock"] > div:nth-child(2) button {{
                            background-color: {RESTORE_BTN_BG_COLOR} !important;
                            color: {RESTORE_BTN_TEXT_COLOR} !important;
                            border-color: {RESTORE_BTN_BORDER_COLOR} !important;
                    }}
                    div[data-testid="stDialog"]:has(.restore-confirm-dialog) 
                        div[data-testid="stHorizontalBlock"] > div:nth-child(2) button:hover {{
                            box-shadow: 0 0 8px {RESTORE_BTN_BG_COLOR} !important;
                            filter: brightness(1.1);
                    }}
                    </style>
                    </div>
                """, unsafe_allow_html=True)

                # Todo el contenido visible: SOLO en el CUERPO del dialog, nunca
                # dentro de if st.button():.
                st.warning("🚨 ESTA ACCIÓN ES DESTRUCTIVA E IRREVERSIBLE")
                st.markdown("""
                    Al confirmar:
                    1. Se **BORRARÁN** todos los datos actuales de la base de datos.
                    2. Se importarán los datos del archivo:
                """)
                pending_name = st.session_state.get("restore_pending_filename")
                st.code(str(pending_name or "backup_sigo_full.xlsx"))
                st.markdown("¿Estás absolutamente seguro de querer continuar?")

                col_cancel, col_confirm = st.columns([1, 1], gap="small")

                with col_cancel:
                    if st.button("Cancelar", use_container_width=True):
                        # Solo flags intermedios + rerun. Ningún st.* acá.
                        for _k in (
                            "restore_pending_open_confirm_dialog",
                            "restore_pending_filename",
                            "restore_pending_confirm",
                            "backup_confirm_checkbox",
                        ):
                            if _k in st.session_state:
                                del st.session_state[_k]
                        safe_rerun()

                with col_confirm:
                    should_restore = st.button(
                        "Restaurar", type="primary", use_container_width=True,
                    )

                if should_restore:
                    st.session_state.restore_pending_confirm = True
                    st.session_state.restore_in_progress = True
                    st.session_state.restore_result = None
                    pending_bytes = st.session_state.get("restore_pending_open_confirm_dialog")
                    st.session_state.restore_file_bytes = (
                        pending_bytes
                        if isinstance(pending_bytes, (bytes, bytearray))
                        else st.session_state.get("restore_file_bytes")
                    )
                    for _k in ("restore_pending_open_confirm_dialog", "restore_pending_filename"):
                        if _k in st.session_state:
                            del st.session_state[_k]
                    safe_rerun()

            running = bool(st.session_state.get("restore_in_progress"))
            restore_result = st.session_state.get("restore_result")  # (success, msg) o None

            # ==== RENDER CONDICIONAL POST-RERUN (SÓLO EN EL CUERPO PRINCIPAL, SIN CALLBACKS) ====
            # 
            # Todos los st.warning / st.success / @st.dialog se muestran DESPUÉS de
            # un rerun que setea el flag, NUNCA directamente dentro de if st.button().
            # Así eliminamos el warning de Streamlit:
            # "A fragment rerun was triggered with a callback that displays one or
            # more elements."

            # 1. Warning amarillo de casilla no confirmada.
            if st.session_state.get("restore_pending_warning_confirm"):
                st.warning(
                    "Primero confirmá la casilla: "
                    "➡️ *Entiendo que perderé todos los datos actuales y deseo continuar.*"
                )
                try:
                    del st.session_state["restore_pending_warning_confirm"]
                except Exception:
                    pass

            # 2. Abrir dialog de confirmación (seteado por click en Iniciar Restauración).
            if st.session_state.get("restore_pending_open_confirm_dialog") is not None:
                show_restore_confirmation()

            # 3. Abrir dialogs de resultado.
            if restore_result is not None:
                _succ, _msg = restore_result
                if _succ:
                    _show_restore_success_dialog(str(_msg))
                else:
                    _show_restore_error_dialog(str(_msg))

            uploaded_file = st.file_uploader(
                "Subir archivo de respaldo (.xlsx)",
                type=["xlsx"],
                key="backup_uploader",
                disabled=running,
            )

            # --- UI DE PROGRESO (running, SÓLO si no hay resultado final) ---
            if running and restore_result is None:
                with st.container(border=True):
                    _st_prog_ph = st.empty()
                    progress_bar = _st_prog_ph.progress(0.03, "Preparando restauración...")

                    def _progress_cb(step_label, pct_float_0_1):
                        try:
                            progress_bar.progress(
                                max(0.0, min(1.0, float(pct_float_0_1))),
                                str(step_label),
                            )
                        except Exception:
                            pass

                    success, msg = False, "Restauración no ejecutada."
                    try:
                        file_bytes = (
                            uploaded_file.getvalue()
                            if uploaded_file
                            else st.session_state.get("restore_file_bytes")
                        )
                        if file_bytes:
                            import io as _io
                            file_obj = _io.BytesIO(file_bytes)
                            file_obj.seek(0)
                            success, msg = restore_full_backup_excel(
                                file_obj, progress_callback=_progress_cb,
                            )
                        else:
                            success, msg = False, "No se pudo obtener el archivo subido. Volvé a intentarlo."
                    except Exception as e:
                        success, msg = False, f"Error crítico en restauración: {e}"
                    finally:
                        st.session_state.restore_in_progress = False
                        st.session_state.restore_file_bytes = None

                    st.session_state.restore_result = (success, msg)
                    safe_rerun()

            # --- UI NORMAL (no running, sin resultado) ---
            if uploaded_file and not running and (restore_result is None):
                st.write("Archivo cargado:", uploaded_file.name)

                confirm_restore = st.checkbox(
                    "Entiendo que perderé todos los datos actuales y deseo continuar.",
                    value=False,
                    key="backup_confirm_checkbox",
                    disabled=running,
                )

                if st.button(
                    "Iniciar Restauración",
                    disabled=running,
                    type="secondary",
                ):
                    if not confirm_restore:
                        st.session_state["restore_pending_warning_confirm"] = True
                    else:
                        try:
                            st.session_state["restore_pending_open_confirm_dialog"] = (
                                uploaded_file.getvalue()
                            )
                            st.session_state["restore_pending_filename"] = str(
                                uploaded_file.name or "backup_sigo_full.xlsx"
                            )
                        except Exception:
                            st.session_state["restore_pending_warning_confirm"] = True
                    safe_rerun()
