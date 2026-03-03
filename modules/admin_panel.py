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
    add_registros_comerciales_batch
)
from .config import SYSTEM_ROLES, DEFAULT_VALUES, SYSTEM_LIMITS
from .nomina_management import render_nomina_edit_delete_forms
from .auth import create_user, validate_password, hash_password, is_2fa_enabled, unlock_user
from .utils import show_success_message, normalize_text, month_name_es, get_general_alerts, safe_rerun
from .activity_logs import render_activity_logs
from .backup_utils import create_full_backup_excel, restore_full_backup_excel

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
                WHERE fecha = %s AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s
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
    from .config import POSTGRES_CONFIG, UPLOADS_DIR, PROJECT_UPLOADS_DIR, update_env_values, reload_env
    from .database import get_current_project_id_sequence, set_project_id_sequence, get_roles_dataframe, update_rol_visibility
    from .utils import safe_rerun
    
    st.subheader("Administración")
    
    tabs_options = ["🔌 Conexiones", "📂 Configuración Proyectos", "💾 Backup & Restore", "👁️ Visibilidad Departamentos"]
    
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
            
            # Usar keys para poder limpiar el estado después
            uploaded_file = st.file_uploader("Subir archivo de respaldo (.xlsx)", type=["xlsx"], key="backup_uploader")
            
            if uploaded_file:
                st.write("Archivo cargado:", uploaded_file.name)
                
                # Definición del diálogo de confirmación
                @st.dialog("⚠️ Confirmación Final de Restauración")
                def show_restore_confirmation(file_obj):
                    # --- CONFIGURACIÓN DE ESTILO DE BOTONES ---
                    # Puedes modificar estos valores para ajustar la apariencia de los botones
                    # -----------------------------------------------------------------------
                    BTN_HEIGHT = "48px"         # Altura de los botones (ej: "48px", "55px")
                    BTN_WIDTH = "100%"          # Ancho de los botones (ej: "100%", "150px")
                    BTN_FONT_SIZE = "16px"      # Tamaño de la fuente (ej: "16px", "1.2rem")
                    
                    # Colores Botón Cancelar (Izquierda)
                    CANCEL_BTN_BG_COLOR = "#262730"       # Fondo
                    CANCEL_BTN_TEXT_COLOR = "#FFFFFF"     # Texto
                    CANCEL_BTN_BORDER_COLOR = "#31333F"   # Borde
                    
                    # Colores Botón Restaurar (Derecha)
                    RESTORE_BTN_BG_COLOR = "#FF4B4B"      # Fondo
                    RESTORE_BTN_TEXT_COLOR = "#FFFFFF"    # Texto
                    RESTORE_BTN_BORDER_COLOR = "#FF4B4B"  # Borde
                    # -----------------------------------------------------------------------

                    # Override CSS local para este diálogo: simetría total forzada y colores personalizados
                    st.markdown(f"""
                        <style>
                        /* Estilos base para ambos botones */
                        div[role="dialog"] button,
                        div[data-testid="stDialog"] button,
                        div[data-testid="stModal"] button {{
                            height: {BTN_HEIGHT} !important;
                            min-height: {BTN_HEIGHT} !important;
                            max-height: {BTN_HEIGHT} !important;
                            width: {BTN_WIDTH} !important;
                            padding: 0px 16px !important;
                            font-size: {BTN_FONT_SIZE} !important;
                            font-weight: 600 !important;
                            line-height: 1 !important; /* Line-height 1 para evitar espaciado extra */
                            border-radius: 8px !important;
                            border-width: 1px !important;
                            border-style: solid !important;
                            display: flex !important;
                            align-items: center !important;
                            justify-content: center !important;
                            margin: 0px !important;
                            box-sizing: border-box !important; /* Asegurar cálculo de tamaño consistente */
                        }}
                        
                        /* Forzar tamaño idéntico incluso si es primary/secondary */
                        div[role="dialog"] button[kind="primary"],
                        div[role="dialog"] button[kind="secondary"],
                        div[data-testid="stDialog"] button[kind="primary"],
                        div[data-testid="stDialog"] button[kind="secondary"] {{
                             height: {BTN_HEIGHT} !important;
                             min-height: {BTN_HEIGHT} !important;
                             max-height: {BTN_HEIGHT} !important;
                        }}
                        
                        /* Asegurar que el texto/contenido interno no afecte la altura */
                        div[role="dialog"] button p,
                        div[data-testid="stDialog"] button p,
                        div[data-testid="stModal"] button p {{
                            line-height: 1.5 !important;
                            margin: 0 !important;
                            padding: 0 !important;
                        }}

                        /* Botón Cancelar (Primera columna) */
                        div[role="dialog"] div[data-testid="stHorizontalBlock"] > div:nth-child(1) button {{
                            background-color: {CANCEL_BTN_BG_COLOR} !important;
                            color: {CANCEL_BTN_TEXT_COLOR} !important;
                            border-color: {CANCEL_BTN_BORDER_COLOR} !important;
                        }}
                        div[role="dialog"] div[data-testid="stHorizontalBlock"] > div:nth-child(1) button:hover {{
                            border-color: {CANCEL_BTN_TEXT_COLOR} !important;
                            filter: brightness(1.2);
                        }}

                        /* Botón Restaurar (Segunda columna) */
                        div[role="dialog"] div[data-testid="stHorizontalBlock"] > div:nth-child(2) button {{
                            background-color: {RESTORE_BTN_BG_COLOR} !important;
                            color: {RESTORE_BTN_TEXT_COLOR} !important;
                            border-color: {RESTORE_BTN_BORDER_COLOR} !important;
                        }}
                        div[role="dialog"] div[data-testid="stHorizontalBlock"] > div:nth-child(2) button:hover {{
                            box-shadow: 0 0 8px {RESTORE_BTN_BG_COLOR} !important;
                            filter: brightness(1.1);
                        }}
                        </style>
                    """, unsafe_allow_html=True)
                    
                    st.warning("🚨 ESTA ACCIÓN ES DESTRUCTIVA E IRREVERSIBLE")
                    st.markdown("""
                        Al confirmar:
                        1. Se **BORRARÁN** todos los datos actuales de la base de datos.
                        2. Se importarán los datos del archivo:
                    """)
                    st.code(file_obj.name)
                    st.markdown("¿Estás absolutamente seguro de querer continuar?")
                    
                    # Usar ratio 1:1 explícito para asegurar igualdad de ancho
                    col_cancel, col_confirm = st.columns([1, 1], gap="small")
                    
                    with col_cancel:
                        if st.button("Cancelar", use_container_width=True):
                            # Limpiar estado al cancelar
                            if 'backup_uploader' in st.session_state:
                                del st.session_state['backup_uploader']
                            if 'backup_confirm_checkbox' in st.session_state:
                                del st.session_state['backup_confirm_checkbox']
                            safe_rerun()
                    
                    with col_confirm:
                        should_restore = st.button("Restaurar", type="primary", use_container_width=True)
                    
                    # Placeholder para mensajes de estado (debajo de los botones)
                    status_placeholder = st.empty()
                    
                    if should_restore:
                        with st.spinner("Restaurando..."):
                            success, msg = restore_full_backup_excel(file_obj)
                            if success:
                                show_success_message(msg, 3)
                                # Limpiar estado al finalizar exitosamente
                                if 'backup_uploader' in st.session_state:
                                    del st.session_state['backup_uploader']
                                if 'backup_confirm_checkbox' in st.session_state:
                                    del st.session_state['backup_confirm_checkbox']
                                safe_rerun()
                            else:
                                status_placeholder.error(msg)

                confirm_restore = st.checkbox("Entiendo que perderé todos los datos actuales y deseo continuar.", value=False, key="backup_confirm_checkbox")
                
                if st.button("Iniciar Restauración", disabled=not confirm_restore, type="secondary"):
                    show_restore_confirmation(uploaded_file)
