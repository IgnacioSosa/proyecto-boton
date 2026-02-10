import os
import shutil
import base64
import html
import re
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from sqlalchemy import text
from .config import PROJECT_UPLOADS_DIR
from .database import (
    get_users_dataframe,
    get_clientes_dataframe,
    check_client_duplicate,
    create_proyecto,
    update_proyecto,
    delete_proyecto,
    get_proyectos_by_owner,
    get_proyectos_shared_with_user,
    get_proyecto_shared_users,
    get_proyecto,
    set_proyecto_shares,
    add_proyecto_document,
    get_proyecto_documentos,
    remove_proyecto_document,
    get_users_by_rol,         # NUEVO
    get_user_rol_id,          # NUEVO
    get_roles_dataframe,      # NUEVO
    get_marcas_dataframe,
    get_engine,
    get_contactos_por_cliente,
    get_contactos_por_marca,
    get_proyectos_por_contacto,
    check_client_duplicate,
    add_cliente_solicitud,
    add_client_full,
    reject_cliente_solicitud,
)
from .config import PROYECTO_ESTADOS, PROYECTO_TIPOS_VENTA
from .contacts_shared import render_shared_contacts_management
from .ui_components import inject_project_card_css

# --- Constants for URL Mapping ---
# Moved inside function to ensure scope availability during hot-reloads

def _validate_cuit(c):
    c = "".join(filter(str.isdigit, str(c)))
    if len(c) != 11: return False
    base = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    aux = 0
    for i in range(10): aux += int(c[i]) * base[i]
    aux = 11 - (aux % 11)
    if aux == 11: aux = 0
    elif aux == 10: aux = 9
    return int(c[10]) == aux

@st.dialog("Cargar cliente")
def manual_client_form(user_id):
    if "manual_step" not in st.session_state:
        st.session_state["manual_step"] = "confirm"
        st.session_state.pop("manual_request_id", None)
        st.session_state.pop("manual_client_name", None)
    
    step = st.session_state.get("manual_step", "confirm")
    
    if step == "confirm":
        st.write("Esta a punto de cargar un nuevo cliente de manera manual ¿desea continuar?")
        if st.button("Crear nuevo cliente", use_container_width=True, key="btn_confirm_manual_create"):
            st.session_state["manual_step"] = "form"
            st.rerun()
    elif step == "form":
        st.subheader("Solicitud de nuevo cliente")
        req_cuit = st.text_input("CUIT")
        req_nombre = st.text_input("Nombre (Razón Social)")
        req_email = st.text_input("Email")
        req_tel = st.text_input("Teléfono")
        req_cel = st.text_input("Celular")
        req_web = st.text_input("Web (URL)")
        
        if st.button("Enviar solicitud", type="primary", use_container_width=True, key="btn_submit_manual_request"):
            errors = []
            
            # Validaciones
            req_cuit_normalized = "".join(filter(str.isdigit, str(req_cuit))) if req_cuit else ""
            
            if not req_cuit:
                errors.append("El CUIT es obligatorio")
            elif not _validate_cuit(req_cuit_normalized):
                errors.append("El CUIT no es válido")
            
            if not req_nombre:
                errors.append("El nombre es obligatorio")
            
            if not req_email:
                errors.append("El email es obligatorio")
            elif not re.match(r"[^@]+@[^@]+\.[^@]+", req_email):
                errors.append("El formato del email no es válido")
            
            if not req_tel:
                errors.append("El teléfono es obligatorio")
            
            if not req_cel:
                errors.append("El celular es obligatorio")
            
            if errors:
                for e in errors:
                    st.error(e)
            else:
                # Validar duplicados antes de proceder
                is_dup, dup_msg = check_client_duplicate(req_cuit_normalized, req_nombre)
                
                if is_dup:
                    st.error(dup_msg)
                else:
                    # 1. Crear cliente temporal para que el comercial pueda trabajar
                    temp_cliente_id = add_client_full(
                    nombre=req_nombre,
                    organizacion="",
                    telefono=req_tel,
                    email=req_email
                )
                
                if temp_cliente_id:
                    # 2. Crear solicitud enlazada al cliente temporal
                    request_id = add_cliente_solicitud(
                        nombre=req_nombre,
                        telefono=req_tel,
                        email=req_email,
                        requested_by=user_id,
                        cuit=req_cuit_normalized,
                        celular=req_cel,
                        web=req_web,
                        tipo="Empresa",
                        temp_cliente_id=temp_cliente_id
                    )
                    
                    if request_id:
                        st.success("Solicitud enviada y cliente disponible temporalmente.")
                        st.session_state["manual_request_id"] = request_id
                        st.session_state["manual_client_name"] = req_nombre
                        st.session_state["create_cliente"] = req_nombre
                        st.session_state.pop("manual_step", None)
                        st.session_state["show_manual_client_dialog"] = False
                        st.query_params["_close_dialog"] = str(pd.Timestamp.now().timestamp())
                        st.rerun()
                    else:
                        st.error("Error al procesar la solicitud")
                else:
                    # Cliente ya existe o no se pudo crear
                    st.warning("El cliente ya existe en la lista general. Se ha seleccionado automáticamente.")
                    st.session_state["create_cliente"] = req_nombre
                    st.session_state.pop("manual_step", None)
                    st.session_state["show_manual_client_dialog"] = False
                    st.query_params["_close_dialog"] = str(pd.Timestamp.now().timestamp())
                    st.rerun()

def _is_auto_description(text: str) -> bool:
    """Detecta si la descripción proviene del resumen auto-generado previo."""
    t = (text or "").strip()
    if not t:
        return False
    if not t.lower().startswith("contacto:"):
        return False
    needles = ["Org.:", "Valor:", "Embudo:", "Etiqueta:", "Prob.:", "Cierre:", "Tel.:", "Email:"]
    return all(n in t for n in needles)

def render_commercial_projects(user_id, username_full=""):
    inject_project_card_css()
    # Define constants locally to prevent NameError scope issues
    PTAB_MAPPING = {
        "nuevo_trato": "🆕 Nuevo Trato",
        "mis_tratos": "📚 Mis Tratos",
        "tratos_compartidos": "🤝 Tratos Compartidos Conmigo",
        "contactos": "🧑‍💼 Contactos"
    }
    PTAB_KEY_LOOKUP = {v: k for k, v in PTAB_MAPPING.items()}

    labels = ["🆕 Nuevo Trato", "📚 Mis Tratos", "🤝 Tratos Compartidos Conmigo", "🧑‍💼 Contactos"]
    params = st.query_params
    
    # --- Notification Logic (Specific for Commercial User) ---
    _alerts_data = {"vencidos": 0, "hoy": 0, "pronto": 0}
    _has_alerts = False
    
    try:
        df_alerts = get_proyectos_by_owner(user_id)
        if not df_alerts.empty:
            _today = pd.Timestamp.now().date()
            for _, _row in df_alerts.iterrows():
                if _row.get("estado") in ["Ganado", "Perdido"]:
                    continue
                _fd_val = pd.to_datetime(_row.get("fecha_cierre"), errors="coerce")
                if not pd.isna(_fd_val):
                    _ddiff = (_fd_val.date() - _today).days
                    if _ddiff < 0:
                        _alerts_data["vencidos"] += 1
                    elif _ddiff == 0:
                        _alerts_data["hoy"] += 1
                    elif 0 < _ddiff <= 30: # Keeping 30 days as 'pronto' consistent with toast logic
                         # Note: Admin panel uses 7 days for 'pronto' in get_general_alerts, 
                         # but here we used 30 in toast. Let's align with toast for now or refine.
                         # Actually, toast used <= 30. Let's stick to that.
                        _alerts_data["pronto"] += 1
            
            if _alerts_data["vencidos"] > 0 or _alerts_data["hoy"] > 0 or _alerts_data["pronto"] > 0:
                _has_alerts = True
    except Exception:
        pass

    # --- Header with Notifications ---
    col_head, col_icon = st.columns([0.88, 0.12])
    with col_head:
        if username_full:
            st.header(f"Dashboard - {username_full}")
        else:
            st.header("Dashboard Comercial")
        
    with col_icon:
        st.write("") 
        try:
            wrapper_class = "has-alerts" if _has_alerts else "no-alerts"
            st.markdown(f"<div class='notif-trigger {wrapper_class}'>", unsafe_allow_html=True)
            icon_str = "🔔"
            with st.popover(icon_str, use_container_width=False):
                st.markdown("### Notificaciones")
                if not _has_alerts:
                    st.info("No hay alertas pendientes.")
                else:
                    parts = []
                    if _alerts_data["vencidos"] > 0: parts.append(f"{_alerts_data['vencidos']} vencidos")
                    if _alerts_data["hoy"] > 0: parts.append(f"{_alerts_data['hoy']} vencen hoy")
                    if _alerts_data["pronto"] > 0: parts.append(f"{_alerts_data['pronto']} vencen pronto")
                    
                    if parts:
                        icon = "🚨" if (_alerts_data["vencidos"] > 0 or _alerts_data["hoy"] > 0) else "⚠️"
                        label = f"{icon} Mis Tratos: {', '.join(parts)}"
                        if st.button(label, key="btn_notif_mis_tratos", use_container_width=True):
                            st.query_params["ptab"] = "mis_tratos"
                            st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        except Exception:
             if st.button("🔔"):
                 st.info(f"Alertas: {_alerts_data['vencidos']} vencidos")


    # --- Toast Notifications (Once per session) ---
    if not st.session_state.get('alerts_shown', False):
        if _has_alerts:
            _msgs = []
            if _alerts_data["vencidos"] > 0: _msgs.append(f"{_alerts_data['vencidos']} vencidos")
            if _alerts_data["hoy"] > 0: _msgs.append(f"{_alerts_data['hoy']} vencen hoy")
            if _alerts_data["pronto"] > 0: _msgs.append(f"{_alerts_data['pronto']} próximos a vencer")
            
            if _msgs:
                st.toast(f"📅 Estado de Tratos: {', '.join(_msgs)}", icon="⚠️")
        st.session_state.alerts_shown = True



    # Determinar pestaña inicial desde 'ptab' o por selección de proyecto
    if "force_proj_tab" in st.session_state:
        forced_val = st.session_state.pop("force_proj_tab")
        # Si el valor forzado es una etiqueta, intentar convertirla a key para el URL, 
        # pero mantenemos la etiqueta para el estado interno
        st.session_state["proj_tabs"] = forced_val
        
        # Actualizar URL con la key limpia si es posible
        clean_key = PTAB_KEY_LOOKUP.get(forced_val, forced_val)
        if "ptab" in params and params["ptab"] != clean_key:
             st.query_params["ptab"] = clean_key

    initial = None
    ptab = params.get("ptab")
    if ptab:
        ptab_val = ptab[0] if isinstance(ptab, list) else ptab
        
        # Check if it's a clean key
        if ptab_val in PTAB_MAPPING:
            initial = PTAB_MAPPING[ptab_val]
        # Fallback for legacy URLs (emojis)
        elif ptab_val in labels:
            initial = ptab_val
            
    if not initial:
        if "myproj" in params:
            initial = labels[1]
        elif "sharedproj" in params:
            initial = labels[2]
        else:
            initial = labels[1]

    # Ensure initial value is in labels
    if initial not in labels:
        initial = labels[1]

    # Ensure session state is initialized to avoid warning
    if "proj_tabs" not in st.session_state:
        st.session_state["proj_tabs"] = initial
    
    # Validation before rendering widget
    current_val = st.session_state.get("proj_tabs")
    if current_val not in labels:
         st.session_state["proj_tabs"] = labels[1]

    # Control de pestañas: sincronizar con el URL y evitar doble clic
    choice = st.segmented_control(label="Secciones", options=labels, key="proj_tabs")
    
    # Detectar cambio de pestaña para limpiar selección de proyecto
    if "last_proj_tab_val" not in st.session_state:
        st.session_state["last_proj_tab_val"] = choice
    elif st.session_state["last_proj_tab_val"] != choice:
        # Si cambió la pestaña, limpiar la selección de proyecto para no mostrar datos de otra vista
        if "selected_project_id" in st.session_state:
            del st.session_state["selected_project_id"]
        st.session_state["last_proj_tab_val"] = choice

    # Si el valor elegido difiere del URL, actualizar y forzar rerender inmediato
    # Logic: Get current param, convert to label if needed to compare with choice
    current_ptab_param = ptab[0] if isinstance(ptab, list) else ptab if ptab else None
    
    # Determine what the URL should be for the current choice
    target_param = PTAB_KEY_LOOKUP.get(choice, choice)
    
    # If URL is different from target, update it
    if current_ptab_param != target_param:
        try:
            st.query_params["ptab"] = target_param
            # Solo rerun si el cambio no fue solo de formato (ej. legacy -> clean) 
            # para evitar loops, aunque st.rerun es seguro.
            # En este caso, si el usuario navega, choice cambia, y queremos reflejarlo en URL.
            st.rerun()
        except Exception:
            pass

    if choice == labels[0]:
        render_create_project(user_id, is_admin=False)
    elif choice == labels[1]:
        render_my_projects(user_id)
    elif choice == labels[2]:
        render_shared_with_me(user_id)
    else:
        render_contacts_management(user_id)

# Utilidad: mostrar vista previa de PDF embebido
def _render_pdf_preview(file_path: str, height: int = 640):
    try:
        if not file_path.lower().endswith(".pdf"):
             st.info(f"Vista previa no disponible para este formato ({os.path.basename(file_path)}).")
             try:
                 with open(file_path, "rb") as f:
                     st.download_button("Descargar archivo", f, file_name=os.path.basename(file_path))
             except:
                 pass
             return

        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        data_url = f"data:application/pdf;base64,{b64}"
        html = f"<iframe src='{data_url}' width='100%' height='{height}' style='border:1px solid #374151;border-radius:12px;background:#111827'></iframe>"
        st.components.v1.html(html, height=height + 8)
    except Exception:
        st.warning("No se pudo mostrar la vista previa del PDF.")
        st.code(file_path)

# Utilidad: preparar un enlace estático servido por Streamlit para vista previa
def _make_static_preview_link(src_path: str, doc_id: int) -> str | None:
    try:
        base = os.path.basename(src_path)
        owner_sub = "unknown"
        proj_sub = "misc"
        try:
            q = text(
                """
                SELECT p.owner_user_id, d.proyecto_id
                FROM proyecto_documentos d
                JOIN proyectos p ON p.id = d.proyecto_id
                WHERE d.id = :id
                """
            )
            r = pd.read_sql_query(q, con=get_engine(), params={"id": int(doc_id)})
            if not r.empty:
                owner_id = r.iloc[0]["owner_user_id"]
                pid = r.iloc[0]["proyecto_id"]
                try:
                    owner_sub = str(int(owner_id))
                except Exception:
                    owner_sub = "unknown"
                try:
                    proj_sub = str(int(pid))
                except Exception:
                    proj_sub = "misc"
        except Exception:
            pass
        dest_dir = os.path.join(os.getcwd(), "static", "previews", owner_sub, proj_sub)
        os.makedirs(dest_dir, exist_ok=True)
        dest_name = f"{int(doc_id)}_{base}"
        dest_path = os.path.join(dest_dir, dest_name)
        if not os.path.exists(dest_path) or os.path.getmtime(src_path) > os.path.getmtime(dest_path):
            shutil.copyfile(src_path, dest_path)
        return f"/static/previews/{owner_sub}/{proj_sub}/{dest_name}"
    except Exception:
        return None

# Renderizar un visor con URL (evita data: URI para PDFs grandes)
def _render_pdf_preview_url(preview_url: str, height: int = 640):
    try:
        if not preview_url.lower().endswith(".pdf"):
            st.info("Vista previa no disponible para este formato.")
            st.link_button("Descargar archivo", preview_url)
            return

        html = f"<iframe src='{preview_url}' width='100%' height='{height}' style='border:1px solid #374151;border-radius:12px;background:#111827'></iframe>"
        st.components.v1.html(html, height=height + 8)
    except Exception:
        st.warning("No se pudo mostrar la vista previa por URL.")

# Construir URL absoluta al servidor actual (para evitar puertos inconsistentes)
def _absolute_static_url(rel_path: str) -> str:
    try:
        addr = st.get_option("server.address") or "localhost"
        port = st.get_option("server.port") or 8501
        base = f"http://{addr}:{port}"
        return f"{base}{rel_path}"
    except Exception:
        return rel_path

def _pdf_data_url(file_path: str) -> str | None:
    try:
        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f"data:application/pdf;base64,{b64}"
    except Exception:
        return None

def _unique_filename(directory: str, filename: str) -> str:
    name, ext = os.path.splitext(filename)
    candidate = filename
    i = 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{name}-{i}{ext}"
        i += 1
    return candidate

def _estado_to_class(s):
    s0 = str(s or "").strip()
    l = s0.lower()
    if not l:
        return ""
    legacy = {
        "activo": "prospecto",
        "pendiente": "presupuestado",
        "finalizado": "ganado",
        "cerrado": "perdido",
    }
    mapping = {
        "prospecto": "prospecto",
        "presupuestado": "presupuestado",
        "negociación": "negociación",
        "negociacion": "negociación",
        "objeción": "objeción",
        "objecion": "objeción",
        "ganado": "ganado",
        "perdido": "perdido",
    }
    if l in mapping:
        return mapping[l]
    return legacy.get(l, l)

def _estado_display(s):
    cls = _estado_to_class(s)
    disp = {
        "prospecto": "Prospecto",
        "presupuestado": "Presupuestado",
        "negociación": "Negociación",
        "objeción": "Objeción",
        "ganado": "Ganado",
        "perdido": "Perdido",
    }
    base = str(s or "").strip()
    return disp.get(cls, base or "-")

# Formatear miles con puntos al cambiar el campo de valor
def _format_valor_on_change():
    try:
        raw = st.session_state.get("create_valor", "")
        if not raw:
            return
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            st.session_state["create_valor"] = ""
            return
        as_int = int(digits)
        st.session_state["create_valor"] = f"{as_int:,}".replace(",", ".")
    except Exception:
        # Si algo falla, no bloquear la interacción
        pass

# Versión genérica para cualquier campo (edición y otros)
def _format_valor_on_change_key(field_key: str):
    try:
        raw = st.session_state.get(field_key, "")
        if not raw:
            return
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            st.session_state[field_key] = ""
            return
        as_int = int(digits)
        st.session_state[field_key] = f"{as_int:,}".replace(",", ".")
    except Exception:
        pass

def _make_format_valor_callback(field_key: str):
    def _cb():
        _format_valor_on_change_key(field_key)
    return _cb

def render_create_project(user_id, is_admin=False, contact_key_prefix=None):
    show_success_msg = None
    st.subheader("Crear Trato Comercial")
    try:
        # Se verifica si hubo un éxito previo para mostrar el mensaje
        pid_ok = st.session_state.get("create_success_pid")
        if pid_ok:
            # Guardamos el mensaje para mostrarlo al final (abajo)
            show_success_msg = f"Trato creado correctamente (ID {int(pid_ok)})."

            # Reset explícito de los campos principales del formulario (excepto file_uploader)
            st.session_state["create_titulo"] = ""
            st.session_state["create_valor"] = ""
            st.session_state["create_descripcion"] = ""
            st.session_state["create_cierre"] = None

            # Forzar regeneración del widget de archivos usando una versión distinta de key
            current_ver = st.session_state.get("create_initial_docs_version", 0)
            st.session_state["create_initial_docs_version"] = current_ver + 1

            # Limpieza de estados auxiliares relacionados
            for k in [
                "create_contacto_id",
                "create_cliente",
                "create_cliente_id",
                "create_share_users",
                "create_contacto_display",
                "create_cliente_manual_nombre",
                "create_cliente_manual_tel",
                "create_cliente_manual_cuit",
                "create_cliente_manual_cel",
                "create_cliente_manual_web",
                "create_cliente_manual_tipo",
                "create_cliente_manual_email",
                "create_cliente_text",
                "create_cliente_manual_textbox",
            ]:
                if k in st.session_state:
                    del st.session_state[k]
            st.session_state.pop("create_success_pid", None)
    except Exception:
        pass
    
    st.markdown(
        """
        <style>
        .stSelectbox div[data-baseweb="select"] { background-color: transparent; border-color: rgba(128, 128, 128, 0.4); }
        .stSelectbox { margin-top: -6px; }
        .client-grid { display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-top:10px; }
        /* .client-card, .client-title, .client-value moved to ui_components.py */
        .section-gap { height: 12px; }
        .section-line { height: 1px; background: rgba(128, 128, 128, 0.2); border-radius:999px; margin: 14px 0; }
        @media (max-width: 768px) { .client-grid { grid-template-columns: 1fr; } }
        </style>
        """,
        unsafe_allow_html=True,
    )
    clientes_df = get_clientes_dataframe(only_active=True)
    # manual_mode removed

    # Restore persisted form data if returning
    if "temp_form_data" in st.session_state:
        for k, v in st.session_state["temp_form_data"].items():
            if k not in st.session_state:
                st.session_state[k] = v
        del st.session_state["temp_form_data"]

    # Selección de cliente y contacto (fuera del form para actualización inmediata)
    st.markdown("**Datos del cliente**")
    cliente_id = None
    cliente_nombre = None
    
    all_clients = clientes_df["nombre"].tolist()
    client_opts = all_clients + ["➕ Crear nuevo cliente"]
    
    # Validar que el valor en session_state (si existe) esté en las opciones
    if "create_cliente" in st.session_state:
        if st.session_state["create_cliente"] not in client_opts:
            del st.session_state["create_cliente"]

    cliente_nombre = st.selectbox(
        "Cliente *",
        options=client_opts,
        key="create_cliente",
        placeholder="Seleccione cliente",
        index=None
    )

    if cliente_nombre == "➕ Crear nuevo cliente":
        # Reset selection to avoid loop when returning
        if "create_cliente" in st.session_state:
            del st.session_state["create_cliente"]
        
        st.session_state["show_manual_client_dialog"] = True
        st.rerun()
    elif cliente_nombre:
        # Si se selecciona un cliente válido, asegurar que el diálogo de creación manual esté cerrado
        # Esto previene que el modal reaparezca si se cerró sin acción previa
        if st.session_state.get("show_manual_client_dialog", False):
            st.session_state["show_manual_client_dialog"] = False

    if st.session_state.get("show_manual_client_dialog", False):
        manual_client_form(user_id)

    try:
        if cliente_nombre and cliente_nombre != "➕ Crear nuevo cliente":
            cliente_id = int(clientes_df.loc[clientes_df["nombre"] == cliente_nombre, "id_cliente"].iloc[0])
        else:
            cliente_id = None
    except Exception:
        cliente_id = None
    st.session_state["create_cliente_id"] = cliente_id

    # Mostrar datos del cliente seleccionados
    try:
        if cliente_nombre and cliente_nombre != "➕ Crear nuevo cliente":
            sel_row = clientes_df.loc[clientes_df["nombre"] == cliente_nombre].iloc[0]
        else:
            sel_row = None
    except Exception:
        sel_row = None
    name_val = str(cliente_nombre or "")
    tel_val = str((sel_row["telefono"] if sel_row is not None else "") or "")
    email_val = str((sel_row["email"] if sel_row is not None else "") or "")
    web_val = "-"
    cuit_val = "-"
    cel_val = "-"
    tipo_val = "-"
    st.markdown(
        f"""
        <div class='client-grid'>
            <div class='client-card'>
            <div class='client-title'>Nombre del cliente</div>
            <div class='client-value'>{name_val}</div>
            </div>
            <div class='client-card'>
            <div class='client-title'>Teléfono</div>
            <div class='client-value'>{tel_val or '-'}</div>
            </div>
            <div class='client-card'>
            <div class='client-title'>Email</div>
            <div class='client-value'>{email_val or '-'}</div>
            </div>
            <div class='client-card'>
            <div class='client-title'>Web</div>
            <div class='client-value'>{web_val}</div>
            </div>
            <div class='client-card'>
            <div class='client-title'>CUIT</div>
            <div class='client-value'>{cuit_val}</div>
            </div>
            <div class='client-card'>
            <div class='client-title'>Celular</div>
            <div class='client-value'>{cel_val}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # Botón para volver al listado de clientes y cancelar solicitud manual (si aplica)
    manual_req_id = st.session_state.get("manual_request_id")
    manual_client_name = st.session_state.get("manual_client_name")
    if manual_req_id and manual_client_name and manual_client_name == (cliente_nombre or ""):
        btn_cols = st.columns([3, 1])
        with btn_cols[0]:
            if st.button("Volver al listado de clientes", key="btn_back_list_after_manual"):
                success, msg = reject_cliente_solicitud(int(manual_req_id))
                if success:
                    st.session_state.pop("manual_request_id", None)
                    st.session_state.pop("manual_client_name", None)
                    st.session_state.pop("create_cliente", None)
                    st.session_state.pop("create_cliente_id", None)
                    st.rerun()
                else:
                    st.error(f"Error al cancelar solicitud: {msg}")
    st.markdown("<div class='section-line'></div>", unsafe_allow_html=True)

    contact_cliente_id = st.session_state.get("create_cliente_id")
    if not contact_cliente_id and cliente_nombre:
        try:
            contact_cliente_id = int(clientes_df.loc[clientes_df["nombre"] == cliente_nombre, "id_cliente"].iloc[0])
            st.session_state["create_cliente_id"] = contact_cliente_id
        except Exception:
            contact_cliente_id = None

    if contact_cliente_id is not None:
        contacto_options = []
        contacto_ids = []
        try:
            cdf = get_contactos_por_cliente(int(contact_cliente_id))
            for _, r in cdf.iterrows():
                disp = f"{r['nombre']} {str(r['apellido'] or '').strip()}".strip()
                if r.get('puesto'):
                    disp = f"{disp} - {r['puesto']}"
                contacto_options.append(disp)
                contacto_ids.append(int(r["id_contacto"]))
        except Exception:
            contacto_options, contacto_ids = [], []
        
        # Agregar opción para crear nuevo contacto
        contacto_display = contacto_options + ["➕ Crear nuevo contacto"]
        
        # Determine initial index based on create_contacto_id if present
        c_idx = None
        current_cid = st.session_state.get("create_contacto_id")
        if current_cid and contacto_ids:
            try:
                if int(current_cid) in contacto_ids:
                    c_idx = contacto_ids.index(int(current_cid))
            except:
                pass
        
        sb_contact_kwargs = {
            "label": "Contacto *",
            "options": contacto_display,
            "placeholder": "Seleccione un contacto...",
            "key": "create_contacto_display"
        }
        
        if "create_contacto_display" not in st.session_state:
            sb_contact_kwargs["index"] = c_idx

        contacto_choice = st.selectbox(**sb_contact_kwargs)

        if contacto_choice == "➕ Crear nuevo contacto":
            # Persist form data to prevent loss during tab switch
            keys_to_save = [
                "create_cliente", "create_titulo", "create_valor", "create_moneda", 
                "create_estado", "create_descripcion", "create_cliente_id",
                "create_tipo_venta", "create_marca", "create_cierre",
                "create_cliente_manual_nombre", "create_cliente_manual_tel",
                "create_cliente_manual_cuit", "create_cliente_manual_cel",
                "create_cliente_manual_web", "create_cliente_manual_tipo",
                "create_cliente_manual_email", "create_cliente_text",
                "create_cliente_manual_textbox"
            ]
            st.session_state["temp_form_data"] = {}
            for k in keys_to_save:
                if k in st.session_state:
                    st.session_state["temp_form_data"][k] = st.session_state[k]

            # Reset selection to avoid loop when returning
            if "create_contacto_display" in st.session_state:
                del st.session_state["create_contacto_display"]

            # Determine prefix for contact form
            target_prefix = contact_key_prefix if contact_key_prefix is not None else ""
            st.session_state[f"{target_prefix}_show_create_modal"] = True
            
            if is_admin:
                # Admin uses adm_tab and different label
                st.query_params["adm_tab"] = "contactos"
                st.query_params["return_to"] = "create_project"
                # Use a flag to update session state in the next run (handled in visor_dashboard.py)
                st.session_state["force_adm_tab"] = "👤 Contactos"
            else:
                # Commercial uses ptab and different label
                st.query_params["ptab"] = "contactos"
                st.query_params["return_to"] = "create_project"
                st.session_state["force_proj_tab"] = "🧑‍💼 Contactos"
                
            if st.session_state.get("create_cliente_id"):
                st.query_params["prefill_client_id"] = str(st.session_state["create_cliente_id"])
            st.rerun()

        try:
            if contacto_choice in contacto_options:
                idx = contacto_options.index(contacto_choice)
                st.session_state["create_contacto_id"] = contacto_ids[idx]
            else:
                st.session_state["create_contacto_id"] = None
        except Exception:
            st.session_state["create_contacto_id"] = None
        try:
            sel_cid = st.session_state.get("create_contacto_id")
            sel_row = cdf.loc[cdf["id_contacto"] == int(sel_cid)].iloc[0] if (sel_cid and not cdf.empty) else None
        except Exception:
            sel_row = None
        if sel_row is not None:
            st.markdown("<div class='section-gap'></div>", unsafe_allow_html=True)
            nombre_full = f"{str(sel_row['nombre'] or '').strip()} {str(sel_row['apellido'] or '').strip()}".strip()
            puesto_val = str(sel_row.get('puesto') or '-')
            tel_val = str(sel_row.get('telefono') or '-')
            email_val = str(sel_row.get('email') or '-')
            # dir_val = str(sel_row.get('direccion') or '-')
            st.markdown(
                f"""
                <div class='client-grid' style='margin-top:8px;'>
                  <div class='client-card'>
                    <div class='client-title'>Nombre</div>
                    <div class='client-value'>{nombre_full}</div>
                  </div>
                  <div class='client-card'>
                    <div class='client-title'>Puesto</div>
                    <div class='client-value'>{puesto_val}</div>
                  </div>
                  <div class='client-card'>
                    <div class='client-title'>Teléfono</div>
                    <div class='client-value'>{tel_val}</div>
                  </div>
                  <div class='client-card'>
                    <div class='client-title'>Email</div>
                    <div class='client-value'>{email_val}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("<div class='section-gap'></div>", unsafe_allow_html=True)
            st.markdown("<div class='section-line'></div>", unsafe_allow_html=True)
    else:
        st.session_state["create_contacto_id"] = None

    form = st.form("create_project_form", clear_on_submit=False)
    with form:
        titulo = st.text_input("Título *", key="create_titulo")
        
        # Calcular índice para Estado
        idx_st = 0
        if "create_estado" in st.session_state:
             val = st.session_state["create_estado"]
             if val in PROYECTO_ESTADOS:
                 idx_st = PROYECTO_ESTADOS.index(val)
        
        estado = st.selectbox("Estado *", options=PROYECTO_ESTADOS, index=idx_st, key="create_estado")
        
        # Calcular índice para Tipo Venta
        idx_tv = 0
        if "create_tipo_venta" in st.session_state:
             val = st.session_state["create_tipo_venta"]
             if val in PROYECTO_TIPOS_VENTA:
                 idx_tv = PROYECTO_TIPOS_VENTA.index(val)
        tipo_venta = st.selectbox("Tipo de Venta *", options=PROYECTO_TIPOS_VENTA, index=idx_tv, key="create_tipo_venta")

        m_opts = get_marcas_dataframe(only_active=True)
        m_list = m_opts["nombre"].tolist()
        idx_m = 0
        if "create_marca" in st.session_state:
             val = st.session_state["create_marca"]
             if val in m_list:
                 idx_m = m_list.index(val)
        marca_nombre = st.selectbox("Marca *", options=m_list, index=idx_m, key="create_marca")
        
        c1, c2 = st.columns([1, 1], vertical_alignment="bottom")
        with c1:
            valor = st.text_input("Valor *", help="Usar , para decimales", key="create_valor") # Se usará on_change en callback si se desea, pero form bloquea.
            # Nota: Dentro de st.form no se pueden usar callbacks con args fácilmente sin rerun. 
            # El format se hará al re-renderizar si persistimos, o al enviar.
            # Aquí dejamos simple texto.
        with c2:
            moneda = st.selectbox(
                "Moneda", 
                options=["USD", "ARS"], 
                index=0, 
                key="create_moneda"
            )
            
        cierre = st.date_input("Fecha estimada de cierre *", key="create_cierre")
        desc = st.text_area("Descripción * (mínimo 20 caracteres)", key="create_descripcion", max_chars=2000)

        uploader_version = st.session_state.get("create_initial_docs_version", 0)
        initial_files = st.file_uploader(
            "Adjuntar documentos iniciales (PDF o DOC) *",
            accept_multiple_files=True,
            type=["pdf", "doc", "docx"],
            key=f"create_initial_docs_{uploader_version}",
        )

        st.divider()
        # Unificar lógica con Edit: obtener colegas del rol del usuario actual Y adm_comercial
        share_options, name_to_id, id_to_name = [], {}, {}
        try:
            owner_rol_id = get_user_rol_id(int(user_id))
            if owner_rol_id is not None:
                users_frames = []
                
                # 1. Colegas del mismo rol
                df_peers = get_users_by_rol(owner_rol_id, exclude_hidden=False)
                if not df_peers.empty:
                    users_frames.append(df_peers)
                    
                # 2. Usuarios con rol 'adm_comercial'
                # Necesitamos buscar el ID del rol 'adm_comercial'
                roles_df = get_roles_dataframe(exclude_hidden=False)
                if not roles_df.empty:
                    adm_role = roles_df[roles_df["nombre"] == "adm_comercial"]
                    if not adm_role.empty:
                        adm_rol_id = int(adm_role.iloc[0]["id_rol"])
                        # Evitar duplicar consulta si el usuario YA es adm_comercial
                        if adm_rol_id != owner_rol_id:
                            df_admins = get_users_by_rol(adm_rol_id, exclude_hidden=False)
                            if not df_admins.empty:
                                users_frames.append(df_admins)
                        else:
                            # Si soy adm_comercial, quiero ver a los de Dpto Comercial también
                            comm_role = roles_df[roles_df["nombre"] == "Dpto Comercial"]
                            if not comm_role.empty:
                                comm_rol_id = int(comm_role.iloc[0]["id_rol"])
                                df_comm = get_users_by_rol(comm_rol_id, exclude_hidden=False)
                                if not df_comm.empty:
                                    users_frames.append(df_comm)
                
                if users_frames:
                    merged_users = pd.concat(users_frames).drop_duplicates(subset=["id"])
                    
                    id_to_name = {
                        int(u["id"]): f"{(u.get('nombre') or '').strip()} {(u.get('apellido') or '').strip()}".strip()
                        for _, u in merged_users.iterrows()
                        if int(u["id"]) != int(user_id)
                    }
                    share_options = [v for v in id_to_name.values() if v]
                    name_to_id = {v: k for k, v in id_to_name.items()}
            else:
                # Si no tiene rol, no mostramos error bloqueante pero avisamos
                st.warning("No se pudo obtener el rol del usuario actual.")

        except Exception as e:
            st.error(f"Error cargando lista de usuarios para compartir: {e}")
            print(f"DEBUG Error sharing users: {e}")
        
        share_users = st.multiselect(
            "Compartir con:",
            options=share_options,
            default=[],
            key="create_share_users"
        )
        share_ids = [name_to_id[n] for n in share_users]

        submitted = st.form_submit_button("Crear Trato", type="primary")
        if submitted:
            errors = []

            if not (titulo or "").strip():
                errors.append("El título es obligatorio.")

            final_cliente_id = st.session_state.get("create_cliente_id")
            if not final_cliente_id:
                errors.append("Seleccione un cliente.")

            # Sanitización de valor (eliminar todo menos dígitos, puntos y comas)
            raw_val = str(valor or "").strip()
            
            # 1. Regex para dejar solo caracteres válidos (0-9, ., ,)
            # Esto elimina letras, símbolos como &, guiones negativos, etc.
            import re
            sanitized_val = re.sub(r'[^0-9,.]', '', raw_val)
            
            # Verificar si quedó algo después de sanitizar
            digits = "".join(ch for ch in sanitized_val if ch.isdigit())
            
            if not digits:
                errors.append("El importe es obligatorio y debe ser numérico.")
            else:
                try:
                    # Convertir formato local (1.000,50) a float (1000.50)
                    v_str = sanitized_val.replace(".", "").replace(",", ".")
                    if float(v_str) < 0:
                        # Esto es técnicamente imposible si sanitizamos el signo menos, 
                        # pero mantenemos la lógica por seguridad futura.
                        errors.append("El importe no puede ser negativo.")
                except:
                    # Si falla el float (ej: "1.2.3"), es un error de formato
                    errors.append("Formato de importe inválido. Use solo números y coma para decimales.")

            if not cierre:
                errors.append("La fecha estimada de cierre es obligatoria.")

            if not marca_nombre:
                errors.append("La marca es obligatoria.")

            if not tipo_venta:
                errors.append("El tipo de venta es obligatorio.")

            desc_text = (desc or "").strip()
            if len(desc_text) < 20:
                errors.append("La descripción debe tener al menos 20 caracteres.")

            if not st.session_state.get("create_contacto_id"):
                errors.append("El contacto es obligatorio.")

            if estado != "Prospecto" and not initial_files:
                errors.append("Debe adjuntar al menos un documento inicial para este estado.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                try:
                    # Aplicar la misma sanitización antes de guardar
                    import re
                    sanitized_val = re.sub(r'[^0-9,.]', '', raw_val)
                    v_str = sanitized_val.replace(".", "").replace(",", ".")
                    val_float = float(v_str) if v_str else 0.0
                except Exception:
                    val_float = 0.0
                
                marca_id = None
                try:
                    marca_id = int(m_opts.loc[m_opts["nombre"] == marca_nombre, "id_marca"].iloc[0])
                except Exception:
                    pass
                
                new_pid = create_proyecto(
                    owner_user_id=user_id,
                    titulo=titulo,
                    descripcion=desc,
                    cliente_id=final_cliente_id,
                    estado=estado,
                    valor=val_float,
                    moneda=moneda,
                    marca_id=marca_id,
                    tipo_venta=tipo_venta,
                    fecha_cierre=cierre,
                    contacto_id=st.session_state.get("create_contacto_id")
                )
                if new_pid:
                    try:
                        if initial_files:
                            save_dir = os.path.join(PROJECT_UPLOADS_DIR, str(new_pid))
                            os.makedirs(save_dir, exist_ok=True)
                            for f in initial_files:
                                unique_name = _unique_filename(save_dir, f.name)
                                file_path = os.path.join(save_dir, unique_name)
                                data_bytes = f.getvalue()
                                with open(file_path, "wb") as out:
                                    out.write(data_bytes)
                                add_proyecto_document(new_pid, user_id, unique_name, file_path, f.type, len(data_bytes))
                    except Exception:
                        st.warning("Algunos documentos iniciales no pudieron guardarse.")

                    try:
                        set_proyecto_shares(new_pid, user_id, share_ids)
                    except Exception:
                        pass

                    st.session_state["create_success_pid"] = new_pid
                    st.rerun()
                else:
                    st.error("Error al crear el proyecto.")
    
    # Mostrar mensaje de éxito al final (para que se vea si el usuario está abajo)
    if show_success_msg:
        st.success(show_success_msg)



def render_my_projects(user_id):
    st.subheader("Mis Tratos")
    
    # Handle selection
    if "selected_pid_my" in st.query_params:
        try:
            pid = int(st.query_params["selected_pid_my"])
            st.session_state["selected_project_id"] = pid
            st.query_params.pop("selected_pid_my", None)
            st.rerun()
        except:
            pass
            
    # Show detail view if selected
    if st.session_state.get("selected_project_id"):
        def back_to_list():
            del st.session_state["selected_project_id"]
            st.rerun()
        
        render_project_detail_screen(user_id, st.session_state["selected_project_id"], is_owner=True, show_back_button=True, back_callback=back_to_list)
        return

    inject_project_card_css()
    
    df = get_proyectos_by_owner(user_id)
    if df.empty:
        st.info("No tienes tratos creados.")
        return

    estados_disponibles = PROYECTO_ESTADOS

    active_states_lower = ["prospecto", "presupuestado", "negociación", "objeción"]

    def _is_active_state(s):
        return _estado_to_class(s) in active_states_lower

    mask_active = df.get("estado", pd.Series(dtype=str)).fillna("").apply(_is_active_state)
    df_active_projects = df[mask_active]
    unique_clients = sorted(df_active_projects.get("cliente_nombre", pd.Series(dtype=str)).dropna().unique().tolist())
    unique_clients = [c for c in unique_clients if str(c).strip()]

    opciones_clientes = ["Todos"] + unique_clients

    fcol1, fcol2, fcol3, fcol4 = st.columns([2, 2, 2, 2])
    with fcol1:
        sel_cliente = st.selectbox("Cliente", options=opciones_clientes, key="my_filter_cliente_select")
        filtro_cliente = sel_cliente if sel_cliente != "Todos" else ""
    with fcol2:
        filtro_nombre = st.text_input("Nombre del proyecto", key="my_filter_nombre")
    with fcol3:
        filtro_estados = st.multiselect("Estado", options=estados_disponibles, key="my_filter_estado")
    with fcol4:
        ordenar_por = st.selectbox("Ordenar por", ["Más recientes", "Fecha Cierre (Asc)", "Fecha Cierre (Desc)"], key="my_sort_option")

    df_filtrado = df.copy()

    if filtro_cliente:
        df_filtrado = df_filtrado[
            df_filtrado.get("cliente_nombre", pd.Series(dtype=str)).fillna("") == filtro_cliente
        ]

    if filtro_nombre:
        df_filtrado = df_filtrado[
            df_filtrado.get("titulo", pd.Series(dtype=str)).fillna("").str.contains(filtro_nombre, case=False, na=False)
        ]

    if filtro_estados:
        df_filtrado = df_filtrado[
            df_filtrado.get("estado", pd.Series(dtype=str)).fillna("").apply(_estado_to_class).isin(
                [e.lower() for e in filtro_estados]
            )
        ]

    if ordenar_por != "Más recientes":
        temp_date_col = pd.to_datetime(df_filtrado.get("fecha_cierre"), errors="coerce")
        ascending_order = ordenar_por == "Fecha Cierre (Asc)"
        sorted_indices = temp_date_col.sort_values(ascending=ascending_order, na_position="last").index
        df_filtrado = df_filtrado.loc[sorted_indices]
    else:
        if "created_at" in df_filtrado.columns:
            df_filtrado = df_filtrado.sort_values("created_at", ascending=False)

    df = df_filtrado
    if df.empty:
        st.info("No hay proyectos que coincidan con los filtros.")
        return

    page_size = 10
    total_items = len(df)
    page_key = "my_projects_page"
    page = int(st.session_state.get(page_key, 1) or 1)
    total_pages = max((total_items + page_size - 1) // page_size, 1)

    if page > total_pages:
        page = total_pages
    if page < 1:
        page = 1

    st.session_state[page_key] = page

    start = (page - 1) * page_size
    end = start + page_size
    df_page = df.iloc[start:end]
    count_text = f"Mostrando elementos {start+1}-{min(end, total_items)} de {total_items}"

    for _, row in df_page.iterrows():
        render_project_card(row, user_id, is_owner=True, param_name="selected_pid_my")

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

    col_text, col_spacer, col_prev, col_sep, col_next = st.columns([3, 3, 1, 0.5, 1])

    with col_text:
        st.markdown(
            f"<div style='display:flex; align-items:center; height:100%; color:#888;'>{count_text}</div>",
            unsafe_allow_html=True,
        )
    with col_prev:
        if st.button(
            "Anterior",
            disabled=(page <= 1),
            key="my_prev_page",
            use_container_width=True,
        ):
            st.session_state[page_key] = page - 1
            st.rerun()
    with col_next:
        if st.button(
            "Siguiente",
            disabled=(page >= total_pages),
            key="my_next_page",
            use_container_width=True,
        ):
            st.session_state[page_key] = page + 1
            st.rerun()

def render_shared_with_me(user_id):
    st.subheader("Tratos Compartidos Conmigo")
    
    # Handle selection
    if "selected_pid_shared" in st.query_params:
        try:
            pid = int(st.query_params["selected_pid_shared"])
            st.session_state["selected_project_id"] = pid
            st.query_params.pop("selected_pid_shared", None)
            st.rerun()
        except:
            pass

    # Show detail view if selected
    if st.session_state.get("selected_project_id"):
        def back_to_list():
            del st.session_state["selected_project_id"]
            st.rerun()
            
        render_project_detail_screen(user_id, st.session_state["selected_project_id"], is_owner=False, show_back_button=True, back_callback=back_to_list)
        return

    inject_project_card_css()

    df = get_proyectos_shared_with_user(user_id)
    if df.empty:
        st.info("No tienes tratos compartidos.")
        return

    page_size = 10
    total_items = len(df)
    page_key = "shared_projects_page"
    page = int(st.session_state.get(page_key, 1) or 1)
    total_pages = max((total_items + page_size - 1) // page_size, 1)

    if page > total_pages:
        page = total_pages
    if page < 1:
        page = 1

    st.session_state[page_key] = page

    start = (page - 1) * page_size
    end = start + page_size
    df_page = df.iloc[start:end]
    count_text = f"Mostrando elementos {start+1}-{min(end, total_items)} de {total_items}"

    for _, row in df_page.iterrows():
        render_project_card(row, user_id, is_owner=False, param_name="selected_pid_shared")

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

    col_text, col_spacer, col_prev, col_sep, col_next = st.columns([3, 3, 1, 0.5, 1])

    with col_text:
        st.markdown(
            f"<div style='display:flex; align-items:center; height:100%; color:#888;'>{count_text}</div>",
            unsafe_allow_html=True,
        )
    with col_prev:
        if st.button(
            "Anterior",
            disabled=(page <= 1),
            key="shared_prev_page",
            use_container_width=True,
        ):
            st.session_state[page_key] = page - 1
            st.rerun()
    with col_next:
        if st.button(
            "Siguiente",
            disabled=(page >= total_pages),
            key="shared_next_page",
            use_container_width=True,
        ):
            st.session_state[page_key] = page + 1
            st.rerun()

def render_contacts_management(user_id):
    """
    Renderiza la gestión de contactos usando la lógica compartida.
    """
    inject_project_card_css()
    render_shared_contacts_management(username=st.session_state.get('username', ''), key_prefix="")

def render_project_card(row, user_id, is_owner, param_name="selected_pid_my"):
    pid = row["id"]
    titulo = html.escape(row.get("titulo") or "")
    cliente = html.escape(row.get("cliente_nombre") or "Sin cliente")
    estado_raw = row.get("estado")
    estado_cls = _estado_to_class(estado_raw)
    estado_disp = _estado_display(estado_raw)

    try:
        fc_dt = pd.to_datetime(row.get("fecha_cierre"), errors="coerce")
        fc_fmt = fc_dt.strftime("%d/%m/%Y") if not pd.isna(fc_dt) else "-"
    except Exception:
        fc_fmt = "-"

    tipo_venta_card = row.get("tipo_venta") or "-"
    
    # Preserve auth/query params (uid, uexp, usig) so we don't lose session
    params = st.query_params
    def _get_param(k):
        v = params.get(k)
        if isinstance(v, list):
            return v[0] if v else ""
        return v or ""
    hidden_uid = _get_param("uid")
    hidden_uexp = _get_param("uexp")
    hidden_usig = _get_param("usig")
    
    input_uid = f'<input type="hidden" name="uid" value="{hidden_uid}" />' if hidden_uid else ''
    input_uexp = f'<input type="hidden" name="uexp" value="{hidden_uexp}" />' if hidden_uexp else ''
    input_usig = f'<input type="hidden" name="usig" value="{hidden_usig}" />' if hidden_usig else ''

    ptab_val = ""
    if param_name == "selected_pid_my":
        ptab_val = "mis_tratos"
    elif param_name == "selected_pid_shared":
        ptab_val = "tratos_compartidos"
    input_ptab = f'<input type="hidden" name="ptab" value="{ptab_val}" />' if ptab_val else ''

    alert_html = ""
    try:
        if estado_cls not in ["ganado", "perdido"]:
            alert_color = ""
            alert_text = ""
            alert_bg = ""

            if pd.isna(fc_dt):
                alert_color = "#9ca3af"
                alert_bg = "rgba(156, 163, 175, 0.2)"
                alert_text = "Sin definir"
            else:
                days_diff = (fc_dt.date() - pd.Timestamp.now().date()).days

                if days_diff < 0:
                    alert_color = "#ef4444"
                    alert_bg = "rgba(239, 68, 68, 0.2)"
                    alert_text = f"Vencido {abs(days_diff)}d"
                elif days_diff == 0:
                    alert_color = "#ef4444"
                    alert_bg = "rgba(239, 68, 68, 0.2)"
                    alert_text = "Vence hoy"
                elif days_diff <= 7:
                    alert_color = "#f97316"
                    alert_bg = "rgba(249, 115, 22, 0.2)"
                    alert_text = f"{days_diff}d restantes"
                elif days_diff <= 15:
                    alert_color = "#eab308"
                    alert_bg = "rgba(234, 179, 8, 0.2)"
                    alert_text = f"{days_diff}d restantes"
                elif days_diff <= 30:
                    alert_color = "#22c55e"
                    alert_bg = "rgba(34, 197, 94, 0.2)"
                    alert_text = f"{days_diff}d restantes"

            if alert_text:
                alert_html = f"""
                <div style="display:flex; align-items:center; gap:6px; margin-right:12px; background:{alert_bg}; padding:4px 8px; border-radius:999px; border:1px solid {alert_color};">
                    <div style="width:8px; height:8px; border-radius:50%; background-color:{alert_color};"></div>
                    <span style="color:{alert_color}; font-size:0.85em; font-weight:600;">{alert_text}</span>
                </div>
                """
    except Exception:
        alert_html = ""

    alert_html = " ".join(alert_html.split()) if alert_html else ""

    st.markdown(
        f"""
<form method="get" class="card-form">
    <input type="hidden" name="{param_name}" value="{pid}" />
    {input_uid}
    {input_uexp}
    {input_usig}
    {input_ptab}
    <div class="project-card">
        <div class="project-info">
            <div class="project-title">
                <span class="dot-left {estado_cls}"></span>
                <span>{titulo}</span>
            </div>
            <div class="project-sub">
                <span class="hl-label">ID</span> <span class="hl-val">{pid}</span>
                <span class="hl-sep">•</span>
                <span class="hl-val client">{cliente}</span>
            </div>
            <div class="project-sub2">
                <span class="hl-label">Cierre:</span> <span class="hl-val">{fc_fmt}</span>
                <span class="hl-sep">•</span>
                <span class="hl-val">{tipo_venta_card}</span>
            </div>
        </div>
        <div style="display:flex; align-items:center;">
            {alert_html}
            <span class="status-pill {estado_cls}">{estado_disp}</span>
        </div>
    </div>
    <button type="submit" class="card-submit"></button>
</form>
""",
        unsafe_allow_html=True,
    )

def render_project_detail_screen(user_id, pid, is_owner=False, bypass_owner=False, show_back_button=True, back_callback=None):
    inject_project_card_css()

    try:
        proj = get_proyecto(pid)
    except Exception:
        st.error("Error al cargar proyecto")
        return

    if not proj:
        st.error("Proyecto no encontrado")
        return

    if bypass_owner:
        is_owner = True

    estado_raw = proj.get("estado")
    estado_cls = _estado_to_class(estado_raw)
    estado_disp = _estado_display(estado_raw)

    try:
        fc_dt = pd.to_datetime(proj.get("fecha_cierre"), errors="coerce")
        fc_fmt = fc_dt.strftime("%d/%m/%Y") if not pd.isna(fc_dt) else "-"
    except Exception:
        fc_dt = pd.NaT
        fc_fmt = "-"

    alert_chip = ""
    try:
        if estado_cls not in ["ganado", "perdido"]:
            alert_color = ""
            alert_bg = ""
            alert_text = ""
            if pd.isna(fc_dt):
                alert_color = "#9ca3af"
                alert_bg = "rgba(156, 163, 175, 0.2)"
                alert_text = "Sin definir"
            else:
                days_diff = (fc_dt.date() - pd.Timestamp.now().date()).days
                if days_diff < 0:
                    alert_color = "#ef4444"
                    alert_bg = "rgba(239, 68, 68, 0.2)"
                    alert_text = f"Vencido {abs(days_diff)}d"
                elif days_diff == 0:
                    alert_color = "#ef4444"
                    alert_bg = "rgba(239, 68, 68, 0.2)"
                    alert_text = "Vence hoy"
                elif days_diff <= 7:
                    alert_color = "#f97316"
                    alert_bg = "rgba(249, 115, 22, 0.2)"
                    alert_text = f"{days_diff}d restantes"
                elif days_diff <= 15:
                    alert_color = "#eab308"
                    alert_bg = "rgba(234, 179, 8, 0.2)"
                    alert_text = f"{days_diff}d restantes"
                elif days_diff <= 30:
                    alert_color = "#22c55e"
                    alert_bg = "rgba(34, 197, 94, 0.2)"
                    alert_text = f"{days_diff}d restantes"
            if alert_text:
                alert_chip = (
                    f"<span style=\"background:{alert_bg}; color:{alert_color}; border:1px solid {alert_color};"
                    f" padding:4px 10px; border-radius:999px; font-size:0.8rem; font-weight:600;\">{alert_text}</span>"
                )
    except Exception:
        alert_chip = ""

    client_name = proj.get("cliente_nombre") or proj.get("marca_nombre") or "-"
    contact_nombre = (proj.get("contacto_nombre") or "").strip()
    contact_apellido = (proj.get("contacto_apellido") or "").strip()
    contact_full = f"{contact_nombre} {contact_apellido}".strip() or "-"
    contact_puesto = (proj.get("contacto_puesto") or "").strip() or "-"

    val = proj.get("valor")
    mon = proj.get("moneda") or "ARS"
    
    if val is not None:
        try:
            val_fmt = f"{mon} {float(val):,.0f}".replace(",", ".")
        except Exception:
            val_fmt = f"{mon} {val}"
    else:
        val_fmt = f"{mon} -"

    marca_disp = proj.get("marca_nombre") or "-"
    tipo_venta_disp = proj.get("tipo_venta") or "-"
    desc_disp = proj.get("descripcion") or "-"

    titulo_html = html.escape(str(proj.get("titulo") or ""))
    client_html = html.escape(client_name)
    contact_html = html.escape(contact_full)
    puesto_html = html.escape(contact_puesto)
    valor_html = html.escape(val_fmt)
    marca_html = html.escape(marca_disp)
    tipo_venta_html = html.escape(tipo_venta_disp)
    desc_html = html.escape(desc_disp)

    estado_chip_html = f'<span class="status-pill {estado_cls}">{estado_disp}</span>'

    c1, c2, c3, c4 = st.columns([1.8, 1.6, 1.6, 4])
    with c1:
        if show_back_button:
            if st.button("← Volver a proyectos", key=f"close_{pid}", type="secondary"):
                if back_callback:
                    back_callback()
                else:
                    if "selected_project_id" in st.session_state:
                        del st.session_state["selected_project_id"]
                    st.rerun()
    @st.dialog("Editar Trato")
    def edit_project_dialog():
        with st.form(f"edit_proj_form_{pid}"):
            st.subheader("Editar Información")
            n_titulo = st.text_input("Título", value=proj["titulo"])
            idx_st = 0
            if proj["estado"] in PROYECTO_ESTADOS:
                idx_st = PROYECTO_ESTADOS.index(proj["estado"])
            n_estado = st.selectbox("Estado", options=PROYECTO_ESTADOS, index=idx_st)
            idx_tv = 0
            if proj["tipo_venta"] in PROYECTO_TIPOS_VENTA:
                idx_tv = PROYECTO_TIPOS_VENTA.index(proj["tipo_venta"])
            n_tipo = st.selectbox("Tipo Venta", options=PROYECTO_TIPOS_VENTA, index=idx_tv)
            c_val, c_mon = st.columns([1, 1], vertical_alignment="bottom")
            with c_val:
                current_val = float(proj["valor"] or 0.0)
                # Ensure initial value complies with min_value to prevent crash
                safe_val = current_val if current_val >= 0.0 else 0.0
                # Pre-format value to user locale style (comma for decimals)
                formatted_val = f"{safe_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                # Remove trailing zeros and decimal point if it's an integer value
                if formatted_val.endswith(",00"):
                     formatted_val = formatted_val[:-3]
                
                n_valor_str = st.text_input("Valor", help="Usar , para decimales", value=formatted_val)
            with c_mon:
                _mon_opts = ["USD", "ARS"]
                _mon_idx = 0
                if proj["moneda"] in _mon_opts:
                    _mon_idx = _mon_opts.index(proj["moneda"])
                
                n_moneda = st.selectbox(
                    "Moneda",
                    options=_mon_opts,
                    index=_mon_idx,
                )
            n_cierre = st.date_input(
                "Cierre Estimado", value=pd.to_datetime(proj["fecha_cierre"]) if proj["fecha_cierre"] else None
            )
            n_desc = st.text_area("Descripción", value=proj["descripcion"], max_chars=2000)
            st.divider()
            st.subheader("Documentos")
            files = st.file_uploader(
                "Adjuntar nuevos documentos (PDF o DOC)",
                accept_multiple_files=True,
                type=["pdf", "doc", "docx"],
                key=f"edit_files_{pid}",
            )
            docs_df = get_proyecto_documentos(pid)
            del_submit = False
            selected_doc_id = None
            if not docs_df.empty:
                ids = [int(x) for x in docs_df["id"].tolist()]
                labels = {int(d["id"]): d["filename"] for _, d in docs_df.iterrows()}
                selected_doc_id = st.selectbox(
                    "Gestionar Archivo Existente",
                    options=ids,
                    format_func=lambda i: labels.get(int(i), str(i)),
                    key=f"edit_doc_selector_{pid}",
                )

                # Download link for selected document
                if selected_doc_id:
                    try:
                        doc_row = docs_df[docs_df['id'] == int(selected_doc_id)].iloc[0]
                        fpath = doc_row['file_path']
                        fname = doc_row['filename']
                        if os.path.exists(fpath):
                            with open(fpath, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode()
                            href = f'<div style="margin-bottom:10px;"><a href="data:application/octet-stream;base64,{b64}" download="{fname}" style="color:#60a5fa; text-decoration:none; font-weight:600;">📥 Descargar {fname}</a></div>'
                            st.markdown(href, unsafe_allow_html=True)
                    except Exception:
                        pass

                d_cols = st.columns([1, 1])
                with d_cols[1]:
                    del_submit = st.form_submit_button("Eliminar Documento Seleccionado")
            else:
                st.caption("No hay documentos cargados.")
            
            st.divider()
            
            # Compartir con
            share_ids_selected = []
            try:
                # Obtener colegas del DUEÑO del proyecto (para que admin vea los pares del dueño)
                owner_rol_id = get_user_rol_id(int(proj["owner_user_id"]))
                commercial_users_df = get_users_by_rol(owner_rol_id)
                
                real_owner_id = int(proj["owner_user_id"])
                
                id_to_name = {
                    int(u["id"]): f"{u['nombre']} {u['apellido']}"
                    for _, u in commercial_users_df.iterrows()
                    if int(u["id"]) != real_owner_id
                }
                
                share_options = list(id_to_name.values())
                name_to_id = {v: k for k, v in id_to_name.items()}
                
                current_shared_ids = get_proyecto_shared_users(pid)
                default_shares = [id_to_name[uid] for uid in current_shared_ids if uid in id_to_name]
                
                share_users = st.multiselect(
                    "Compartir con:",
                    options=share_options,
                    default=default_shares,
                    key=f"edit_share_users_{pid}"
                )
                share_ids_selected = [name_to_id[n] for n in share_users]
            except Exception:
                pass

            st.divider()
            submitted = st.form_submit_button("Guardar cambios", type="primary")

        if del_submit and selected_doc_id:
            ok = False
            try:
                if remove_proyecto_document(int(selected_doc_id), user_id, bypass_owner=bypass_owner):
                    ok = True
                else:
                    st.error("Error al eliminar documento.")
            except Exception:
                st.error("Error al eliminar documento.")
            if ok:
                st.success("Archivo eliminado.")
                st.rerun()
            return

        if submitted:
            # Validation for mandatory files in states >= Presupuestado
            has_existing_docs = not docs_df.empty
            has_new_docs = files is not None and len(files) > 0
            
            # Sanitización de valor (eliminar todo menos dígitos, puntos y comas)
            raw_val = str(n_valor_str or "").strip()
            
            import re
            sanitized_val = re.sub(r'[^0-9,.]', '', raw_val)
            digits = "".join(ch for ch in sanitized_val if ch.isdigit())
            
            parsed_valor = 0.0
            if not digits:
                 st.error("El importe es obligatorio y debe ser numérico.")
                 return # Stop execution
            else:
                try:
                    # Convertir formato local (1.000,50) a float (1000.50)
                    v_str = sanitized_val.replace(".", "").replace(",", ".")
                    parsed_valor = float(v_str)
                    if parsed_valor < 0:
                        st.error("El importe no puede ser negativo.")
                        return # Stop execution
                except:
                    st.error("Formato de importe inválido. Use solo números y coma para decimales.")
                    return # Stop execution

            if n_estado != "Prospecto" and not (has_existing_docs or has_new_docs):
                st.error("Debe adjuntar al menos un documento para estados a partir de Presupuestado.")
            else:
                if update_proyecto(
                    pid,
                    user_id,
                    n_titulo,
                    n_desc,
                    proj["cliente_id"],
                    n_estado,
                    parsed_valor,
                    n_moneda,
                    proj["etiqueta"],
                    proj["probabilidad"],
                    proj["embudo"],
                    n_cierre,
                    proj["marca_id"],
                    proj["contacto_id"],
                    n_tipo,
                    bypass_owner=bypass_owner,
                ):
                    try:
                        if files:
                            save_dir = os.path.join(PROJECT_UPLOADS_DIR, str(pid))
                            os.makedirs(save_dir, exist_ok=True)
                            for f in files:
                                unique_name = _unique_filename(save_dir, f.name)
                                file_path = os.path.join(save_dir, unique_name)
                                data_bytes = f.getvalue()
                                with open(file_path, "wb") as out:
                                    out.write(data_bytes)
                                add_proyecto_document(pid, user_id, unique_name, file_path, f.type, len(data_bytes))
                    except Exception:
                        st.warning("Algunos documentos no pudieron guardarse.")
                    
                    # Actualizar compartidos
                    try:
                        set_proyecto_shares(pid, proj["owner_user_id"], share_ids_selected, bypass_owner=bypass_owner)
                    except Exception:
                        pass

                    st.success("Proyecto actualizado")
                    st.rerun()
                else:
                    st.error("Error al actualizar")
    with c2:
        if is_owner or bypass_owner:
            # Parámetros manuales del botón Editar
            edit_btn_label = "✏️ Editar"
            edit_btn_type = "secondary"
            edit_btn_key = f"btn_open_edit_{pid}"
            edit_btn_help = None
            
            if st.button(edit_btn_label, key=edit_btn_key, type=edit_btn_type, help=edit_btn_help, use_container_width=True):
                edit_project_dialog()
    with c3:
        if is_owner or bypass_owner:
            if st.button("🗑️ Eliminar", key=f"del_{pid}", type="primary", use_container_width=True):
                if delete_proyecto(pid, user_id, bypass_owner=bypass_owner):
                    st.success("Proyecto eliminado")
                    if "selected_project_id" in st.session_state:
                        del st.session_state["selected_project_id"]
                    if "selected_project_id_adm" in st.session_state:
                        if st.session_state["selected_project_id_adm"] == pid:
                            del st.session_state["selected_project_id_adm"]
                    st.rerun()
                else:
                    st.error("Error al eliminar")
    with c4:
        chips_html = " ".join([x for x in [alert_chip, estado_chip_html] if x])
        st.markdown(
            f"<div style='display:flex; justify-content:flex-end; gap:8px;'>{chips_html}</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div style="margin-top:16px; margin-bottom:12px;">
          <div style="font-size:2rem; font-weight:800; color:var(--text-color);">{titulo_html}</div>
          <div style="font-size:0.9rem; color:var(--text-color); opacity: 0.7;">Proyecto ID: {pid}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    st.markdown(
        """
        <style>
        /* Igualar tamaño de los botones de acción (Volver, Editar y Eliminar) en el encabezado */
        div[data-testid="stColumn"]:nth-of-type(1) .stButton > button,
        div[data-testid="stColumn"]:nth-of-type(2) .stButton > button,
        div[data-testid="stColumn"]:nth-of-type(3) .stButton > button {
            width: 100% !important;
            height: auto !important;
            min-height: 55px !important;
            font-size: 18px !important;
            font-weight: 600 !important;
            padding-top: 10px !important;
            padding-bottom: 10px !important;
            border-radius: 8px !important;
        }

        /* Restaurar estilo para botones dentro del panel de detalles */
        div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stColumn"] .stButton > button {
            min-height: auto !important;
            font-size: 1rem !important;
            padding-top: 0.5rem !important;
            padding-bottom: 0.5rem !important;
            width: auto !important;
        }

        /* Estilo para el contenedor principal - Adaptativo */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background-color: var(--background-color);
            border: 1px solid rgba(128, 128, 128, 0.2);
            border-radius: 14px;
            padding: 24px;
            box-shadow: 0 4px 14px rgba(0,0,0,0.1);
        }
        
        /* Estilo para las tarjetas internas - Adaptativo */
        .detail-item {
            background-color: var(--secondary-background-color);
            border: 1px solid rgba(128, 128, 128, 0.2);
            border-radius: 12px;
            padding: 16px;
            height: 100%;
        }
        .detail-label {
            color: var(--text-color);
            font-weight: 700;
            font-size: 14px;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            opacity: 0.8;
        }
        .detail-sublabel {
            font-size: 0.85rem;
            color: var(--text-color);
            margin-bottom: 2px;
            opacity: 0.6;
        }
        .detail-value {
            color: var(--text-color);
            font-size: 1rem;
            font-weight: 500;
        }
        .detail-value-group {
            margin-bottom: 12px;
        }
        .detail-value-group:last-child {
            margin-bottom: 0;
        }

        /* Overrides para mantener el look "Deep Dark" original solo en modo oscuro */
        [data-theme="dark"] div[data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #0b1220;
            border-color: #374151;
        }
        [data-theme="dark"] .detail-item {
            background-color: #020617 !important;
            border-color: #1f2937 !important;
        }
        [data-theme="dark"] .detail-label { color: #9ca3af !important; opacity: 1; }
        [data-theme="dark"] .detail-sublabel { color: #6b7280 !important; opacity: 1; }
        [data-theme="dark"] .detail-value { color: #e5e7eb !important; }
        </style>
        """,
        unsafe_allow_html=True
    )

    with st.container(border=True):
        g1, g2 = st.columns(2)

        with g1:
            st.markdown(
                f"""
                <div class="detail-item" style="margin-bottom:16px;">
                    <div class="detail-label">🏢 Cliente</div>
                    <div class="detail-value-group">
                        <div class="detail-sublabel">Nombre</div>
                        <div class="detail-value">{client_html}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                f"""
                <div class="detail-item">
                    <div class="detail-label">👤 Contacto</div>
                    <div class="detail-value-group">
                        <div class="detail-sublabel">Nombre</div>
                        <div class="detail-value">{contact_html}</div>
                    </div>
                    <div class="detail-value-group">
                        <div class="detail-sublabel">Puesto</div>
                        <div class="detail-value">{puesto_html}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with g2:
            st.markdown(
                f"""
                <div class="detail-item" style="margin-bottom:16px;">
                    <div class="detail-label">💰 Económico</div>
                    <div class="detail-value-group">
                        <div class="detail-sublabel">Valor</div>
                        <div class="detail-value">{valor_html}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                f"""
                <div class="detail-item">
                    <div class="detail-label">📊 Clasificación</div>
                    <div class="detail-value-group">
                        <div class="detail-sublabel">Fecha Cierre</div>
                        <div class="detail-value">{fc_fmt}</div>
                    </div>
                    <div class="detail-value-group">
                        <div class="detail-sublabel">Marca</div>
                        <div class="detail-value">{marca_html}</div>
                    </div>
                    <div class="detail-value-group">
                        <div class="detail-sublabel">Tipo Venta</div>
                        <div class="detail-value">{tipo_venta_html}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.write("")

        st.markdown(
            f"""
            <div class="detail-item">
                <div class="detail-label">📝 Descripción</div>
                <div class="detail-value">{desc_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.write("")

        st.subheader("📂 Documentos")

        docs = get_proyecto_documentos(pid)
        if docs.empty:
            st.info("No hay documentos adjuntos.")
        else:
            for _, d in docs.iterrows():
                d_col1, d_col2 = st.columns([0.8, 0.2])
                with d_col1:
                    st.markdown(f"**📄 {d['filename']}**")
                    st.caption(f"Subido: {d['uploaded_at']}")
                with d_col2:
                    fpath = d["file_path"]
                    if os.path.exists(fpath):
                        with open(fpath, "rb") as f:
                            st.download_button(
                                "Descargar",
                                f,
                                file_name=d["filename"],
                                key=f"dl_{d['id']}",
                            )
                st.write("")

    # zona de peligro se maneja en los botones superiores
