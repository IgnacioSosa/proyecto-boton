import os
import shutil
import base64
import streamlit as st
import pandas as pd
from sqlalchemy import text
from .database import (
    get_users_dataframe,
    get_clientes_dataframe,
    create_proyecto,
    update_proyecto,
    delete_proyecto,
    get_proyectos_by_owner,
    get_proyectos_shared_with_user,
    get_proyecto,
    set_proyecto_shares,
    add_proyecto_document,
    get_proyecto_documentos,
    remove_proyecto_document,
    get_users_by_rol,         # NUEVO
    get_user_rol_id,          # NUEVO
    get_marcas_dataframe,
    get_engine,
    get_contactos_por_cliente,
    get_contactos_por_marca,
    get_proyectos_por_contacto,
)

def _open_delete_contact_dialog(contact_id, uid, uexp, usig):
    assoc_df = pd.DataFrame()
    try:
        assoc_df = get_proyectos_por_contacto(int(contact_id))
    except Exception:
        assoc_df = pd.DataFrame()

    def _content():
        if assoc_df is not None and not assoc_df.empty:
            st.warning("No se puede eliminar: el contacto está asociado a proyectos")
            for _, pr in assoc_df.iterrows():
                st.write(f"• [{int(pr['id'])}] {pr['titulo']}")
            if st.button("Cerrar", key=f"close_del_{contact_id}"):
                try:
                    st.query_params["ptab"] = "🧑‍💼 Contactos"
                    if "del_prompt" in st.query_params:
                        del st.query_params["del_prompt"]
                    st.query_params["contactid"] = str(contact_id)
                    if uid:
                        st.query_params["uid"] = uid
                    if uexp:
                        st.query_params["uexp"] = uexp
                    if usig:
                        st.query_params["usig"] = usig
                except Exception:
                    pass
                st.rerun()
        else:
            st.info("Esta acción eliminará el contacto de forma permanente")
            cols = st.columns([1,1])
            with cols[0]:
                if st.button("Eliminar definitivamente", type="primary", key=f"confirm_del_{contact_id}"):
                    from .database import delete_contacto
                    ok = False
                    try:
                        ok = bool(delete_contacto(int(contact_id)))
                    except Exception:
                        ok = False
                    if ok:
                        st.success("Contacto eliminado")
                        try:
                            st.query_params["ptab"] = "🧑‍💼 Contactos"
                            if "contactid" in st.query_params:
                                del st.query_params["contactid"]
                            if "del_prompt" in st.query_params:
                                del st.query_params["del_prompt"]
                            if uid:
                                st.query_params["uid"] = uid
                            if uexp:
                                st.query_params["uexp"] = uexp
                            if usig:
                                st.query_params["usig"] = usig
                        except Exception:
                            pass
                        st.rerun()
                    else:
                        st.error("No se pudo eliminar el contacto")
            with cols[1]:
                if st.button("Cancelar", key=f"cancel_del_{contact_id}"):
                    try:
                        st.query_params["ptab"] = "🧑‍💼 Contactos"
                        if "del_prompt" in st.query_params:
                            del st.query_params["del_prompt"]
                        st.query_params["contactid"] = str(contact_id)
                        if uid:
                            st.query_params["uid"] = uid
                        if uexp:
                            st.query_params["uexp"] = uexp
                        if usig:
                            st.query_params["usig"] = usig
                    except Exception:
                        pass
                    st.rerun()

    st.dialog("Confirmar eliminación", width="small")(_content)()
from .config import PROYECTO_ESTADOS, PROYECTO_TIPOS_VENTA

def _is_auto_description(text: str) -> bool:
    """Detecta si la descripción proviene del resumen auto-generado previo."""
    t = (text or "").strip()
    if not t:
        return False
    if not t.lower().startswith("contacto:"):
        return False
    needles = ["Org.:", "Valor:", "Embudo:", "Etiqueta:", "Prob.:", "Cierre:", "Tel.:", "Email:"]
    return all(n in t for n in needles)

def render_commercial_projects(user_id):
    labels = ["🆕 Crear Proyecto", "📚 Mis Proyectos", "🤝 Compartidos Conmigo", "🧑‍💼 Contactos"]
    params = st.query_params

    # Determinar pestaña inicial desde 'ptab' o por selección de proyecto
    initial = None
    ptab = params.get("ptab")
    if ptab:
        ptab_val = ptab[0] if isinstance(ptab, list) else ptab
        if ptab_val in labels:
            initial = ptab_val
    if not initial:
        if "myproj" in params:
            initial = labels[1]
        elif "sharedproj" in params:
            initial = labels[2]
        else:
            initial = labels[0]

    # Control de pestañas: sincronizar con el URL y evitar doble clic
    choice = st.segmented_control(label="Secciones", options=labels, default=initial, key="proj_tabs")
    # Si el valor elegido difiere del URL, actualizar y forzar rerender inmediato
    current_ptab = ptab[0] if isinstance(ptab, list) else ptab if ptab else None
    if choice != current_ptab:
        try:
            st.query_params["ptab"] = choice
            st.rerun()
        except Exception:
            pass

    if choice == labels[0]:
        render_create_project(user_id)
    elif choice == labels[1]:
        render_my_projects(user_id)
    elif choice == labels[2]:
        render_shared_with_me(user_id)
    else:
        render_contacts_management(user_id)

# Utilidad: mostrar vista previa de PDF embebido
def _render_pdf_preview(file_path: str, height: int = 640):
    try:
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

def render_create_project(user_id):
    st.subheader("Crear Proyecto Comercial")
    try:
        pid_ok = st.session_state.get("create_success_pid")
        if pid_ok:
            st.success(f"Proyecto creado correctamente (ID {int(pid_ok)}).")
    except Exception:
        pass
    
    st.markdown(
        """
        <style>
        .stSelectbox div[data-baseweb="select"] { background-color: transparent; border-color: #444; }
        .stSelectbox { margin-top: -6px; }
        .client-grid { display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-top:10px; }
        .client-card { background:#111827; border:1px solid #374151; border-radius:12px; padding:12px; }
        .client-title { font-weight:600; color:#9ca3af; margin-bottom:6px; }
        .client-value { color:#e5e7eb; }
        .section-gap { height: 12px; }
        .section-line { height: 1px; background:#334155; border-radius:999px; margin: 14px 0; }
        @media (max-width: 768px) { .client-grid { grid-template-columns: 1fr; } }
        </style>
        """,
        unsafe_allow_html=True,
    )
    clientes_df = get_clientes_dataframe()
    manual_mode = bool(st.session_state.get("manual_mode", False))

    

    # Selección de cliente y contacto (fuera del form para actualización inmediata)
    st.markdown("**Datos del cliente**")
    cliente_id = None
    cliente_nombre = None
    if not manual_mode:
        all_clients = clientes_df["nombre"].tolist()
        client_opts = all_clients
        cliente_nombre = st.selectbox(
            "Cliente",
            options=client_opts,
            key="create_cliente",
            placeholder="Seleccione cliente"
        )
        btn_cols = st.columns([3,1])
        with btn_cols[1]:
            if st.button("El cliente no está en la lista? Carga manual", key="ask_manual_button"):
                st.session_state["manual_confirm"] = True
        try:
            cliente_id = int(clientes_df.loc[clientes_df["nombre"] == cliente_nombre, "id_cliente"].iloc[0])
        except Exception:
            cliente_id = None
        st.session_state["create_cliente_id"] = cliente_id

        # Mostrar datos del cliente seleccionados
        try:
            sel_row = clientes_df.loc[clientes_df["nombre"] == cliente_nombre].iloc[0] if cliente_nombre else None
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
              <div class='client-card'>
                <div class='client-title'>Tipo</div>
                <div class='client-value'>{tipo_val}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div class='section-line'></div>", unsafe_allow_html=True)
    else:
        manual_nombre = (st.session_state.get("create_cliente_manual_nombre", "") or "").strip()
        st.session_state["create_cliente_id"] = None
        if "create_cliente_text" not in st.session_state:
            st.session_state["create_cliente_text"] = manual_nombre
        st.text_input("Cliente", key="create_cliente_text", disabled=True)
        name_val = str(st.session_state.get("create_cliente_manual_nombre", "") or "")
        tel_val = str(st.session_state.get("create_cliente_manual_tel", "") or "")
        email_val = str(st.session_state.get("create_cliente_manual_email", "") or "-")
        web_raw = str(st.session_state.get("create_cliente_manual_web", "") or "-")
        web_val = f"<a href='{web_raw}' target='_blank'>{web_raw}</a>" if web_raw.startswith("http://") or web_raw.startswith("https://") else web_raw
        cuit_val = str(st.session_state.get("create_cliente_manual_cuit", "") or "-")
        cel_val = str(st.session_state.get("create_cliente_manual_cel", "") or "-")
        tipo_val = str(st.session_state.get("create_cliente_manual_tipo", "") or "-")
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
                <div class='client-value'>{email_val}</div>
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
              <div class='client-card'>
                <div class='client-title'>Tipo</div>
                <div class='client-value'>{tipo_val}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div class='section-line'></div>", unsafe_allow_html=True)
        if st.button("Volver al listado de clientes", key="back_list_button"):
            st.session_state["manual_mode"] = False

    st.markdown("**Contacto**")
    if not manual_mode and (st.session_state.get("create_cliente_id") is not None):
        contacto_options = []
        contacto_ids = []
        try:
            cdf = get_contactos_por_cliente(int(st.session_state.get("create_cliente_id")))
            for _, r in cdf.iterrows():
                disp = f"{r['nombre']} {str(r['apellido'] or '').strip()}".strip()
                if r.get('puesto'):
                    disp = f"{disp} - {r['puesto']}"
                contacto_options.append(disp)
                contacto_ids.append(int(r["id_contacto"]))
        except Exception:
            contacto_options, contacto_ids = [], []
        contacto_display = contacto_options
        contacto_choice = st.selectbox(
            "Contacto",
            options=contacto_display if contacto_display else ["(Sin contactos disponibles)"],
            index=0 if contacto_display else None,
            key="create_contacto_display",
        )
        try:
            st.session_state["create_contacto_id"] = contacto_ids[contacto_display.index(contacto_choice)] if contacto_display else None
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
            dir_val = str(sel_row.get('direccion') or '-')
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
                  <div class='client-card'>
                    <div class='client-title'>Dirección</div>
                    <div class='client-value'>{dir_val}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("<div class='section-gap'></div>", unsafe_allow_html=True)
            st.markdown("<div class='section-line'></div>", unsafe_allow_html=True)
    else:
        st.session_state["create_contacto_id"] = None

    # Formulario para evitar re-render hasta envío
    form = st.form("create_project_form", clear_on_submit=True)
    with form:
        titulo = st.text_input("Título")
        
        # Continuación del formulario: Datos del proyecto, Estado, Descripción, archivos, compartir y submit
        st.divider()
        st.markdown("**Datos del proyecto**")
        vd_cols = st.columns(2)
        with vd_cols[0]:
            val_cols = st.columns([1, 1])
            with val_cols[0]:
                valor_raw = st.text_input("Valor", key="create_valor")
            with val_cols[1]:
                moneda = st.selectbox("Moneda", ["ARS", "USD"], index=0, key="create_moneda")
            etiqueta = st.text_input("Etiqueta", key="create_etiqueta")
            probabilidad = st.slider("Probabilidad", min_value=0, max_value=100, value=0, format="%d%%", key="create_probabilidad")
            tipo_venta = st.selectbox("Tipo de Venta", options=PROYECTO_TIPOS_VENTA, key="create_tipo_venta")
        with vd_cols[1]:
            marcas_df = get_marcas_dataframe()
            marca_options = marcas_df["nombre"].tolist()
            marca_nombre = st.selectbox("Marca", options=marca_options, key="create_marca")
            fecha_cierre = st.date_input("Fecha prevista de cierre", key="create_cierre")
        st.divider()
        estado = st.selectbox("Estado", options=PROYECTO_ESTADOS, key="create_estado")
        descripcion = st.text_area("Descripción")
        initial_files = st.file_uploader(
            "Adjuntar documentos iniciales (PDF)",
            accept_multiple_files=True,
            type=["pdf"],
            key="create_initial_docs"
        )
        st.divider()
        try:
            current_user_rol_id = get_user_rol_id(user_id)
            commercial_users_df = get_users_by_rol(current_user_rol_id)
            id_to_name = {
                int(u["id"]): f"{u['nombre']} {u['apellido']}"
                for _, u in commercial_users_df.iterrows()
                if int(u["id"]) != int(user_id)
            }
            share_options = list(id_to_name.values())
            name_to_id = {v: k for k, v in id_to_name.items()}
        except Exception:
            share_options, name_to_id, id_to_name = [], {}, {}
        share_users = st.multiselect(
            "Compartir con:",
            options=share_options,
            default=[],
            key="create_share_users"
        )
        share_ids = [name_to_id[n] for n in share_users]

        def _mark_create_submitted():
            st.session_state["create_submit_clicked"] = True
        submitted = st.form_submit_button("Crear proyecto", type="primary", on_click=_mark_create_submitted)

    # Diálogos fuera del form
    if st.session_state.get("manual_confirm"):
        import streamlit as _st
        @_st.dialog("Cliente no encontrado")
        def _confirm_manual_dialog():
            st.write("cliente no encontrado, ¿Desea cargarlo manualmente?")
            st.markdown('<div class="dlg-actions">', unsafe_allow_html=True)
            col1, col2 = st.columns([1,1])
            with col1:
                if st.button("Cargar manualmente", key="confirm_manual_accept"):
                    st.session_state["manual_mode"] = True
                    st.session_state["manual_request_open"] = True
                    st.session_state["manual_confirm"] = False
                    st.rerun()
            with col2:
                if st.button("Continuar sin cargar", key="confirm_manual_cancel"):
                    st.session_state["manual_confirm"] = False
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        _confirm_manual_dialog()

    if st.session_state.get("manual_request_open"):
        import streamlit as _st
        @_st.dialog("Solicitud de nuevo cliente")
        def _request_manual_dialog():
            st.markdown(
                """
                <style>
                .dlg-dark .stTextInput > div > div > input { background:#2b2f37; color:#e5e7eb; border:1px solid #374151; }
                .dlg-dark .stTextInput > div > div > input:focus { border-color:#2563eb; box-shadow: 0 0 0 1px #2563eb inset; }
                .dlg-dark .stTextArea textarea { background:#2b2f37; color:#e5e7eb; border:1px solid #374151; }
                .dlg-dark .stTextArea textarea:focus { border-color:#2563eb; box-shadow: 0 0 0 1px #2563eb inset; }
                .dlg-dark label { color:#e5e7eb; font-weight:600; }
                .dlg-dark .stButton > button { background:#111827; color:#e5e7eb; border:1px solid #374151; border-radius:8px; }
                .dlg-dark .stButton > button:hover { border-color:#2563eb; background:#0b1220; }
                .dlg-dark hr { border-color:#374151; }
                </style>
                """,
                unsafe_allow_html=True,
            )
            st.markdown('<div class="dlg-dark">', unsafe_allow_html=True)
            cuit_req = st.text_input("CUIT", key="req_cliente_cuit")
            nombre_req = st.text_input("Nombre", key="req_cliente_nombre")
            tel_req = st.text_input("Teléfono", key="req_cliente_tel")
            cel_req = st.text_input("Celular", key="req_cliente_cel")
            web_req = st.text_input("Web (URL)", key="req_cliente_web")
            tipo_req = st.selectbox("Tipo", options=["opcion 1", "opcion 2", "opcion 3"], key="req_cliente_tipo")
            st.markdown('<div class="dlg-actions">', unsafe_allow_html=True)
            col1, col2 = st.columns([1,1])
            from .database import add_cliente_solicitud
            with col1:
                if st.button("Enviar solicitud", key="send_client_request"):
                    ok = False
                    errors = []
                    if not (cuit_req or "").strip():
                        errors.append("El CUIT es obligatorio.")
                    if not (nombre_req or "").strip():
                        errors.append("El nombre es obligatorio.")
                    if not (tel_req or "").strip():
                        errors.append("El teléfono es obligatorio.")
                    if not (cel_req or "").strip():
                        errors.append("El celular es obligatorio.")
                    web_ok = str(web_req or "").strip().lower().startswith("http://") or str(web_req or "").strip().lower().startswith("https://")
                    if not web_ok:
                        errors.append("La web debe ser una URL válida (http/https).")
                    if not (tipo_req or "").strip():
                        errors.append("El tipo es obligatorio.")
                    if errors:
                        for e in errors:
                            st.error(e)
                    else:
                        try:
                            ok = bool(add_cliente_solicitud(nombre=(nombre_req or "").strip(), telefono=(tel_req or "").strip(), requested_by=int(user_id), cuit=(cuit_req or "").strip(), celular=(cel_req or "").strip(), web=(web_req or "").strip(), tipo=(tipo_req or "").strip()))
                        except Exception:
                            ok = False
                    if ok:
                        st.session_state["manual_request_open"] = False
                        st.session_state["manual_mode"] = True
                        st.session_state["create_cliente_manual_nombre"] = (nombre_req or "").strip()
                        st.session_state["create_cliente_manual_tel"] = (tel_req or "").strip()
                        st.session_state["create_cliente_manual_cuit"] = (cuit_req or "").strip()
                        st.session_state["create_cliente_manual_cel"] = (cel_req or "").strip()
                        st.session_state["create_cliente_manual_web"] = (web_req or "").strip()
                        st.session_state["create_cliente_manual_tipo"] = (tipo_req or "").strip()
                        st.session_state["create_cliente_text"] = (nombre_req or "").strip()
                        st.session_state["create_cliente_id"] = None
                        st.rerun()
            with col2:
                if st.button("Cancelar", key="cancel_client_request"):
                    st.session_state["manual_request_open"] = False
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)
        _request_manual_dialog()

    # Envío del formulario: crear y redirigir a Mis Proyectos
    if submitted:
        if st.session_state.get("create_submit_clicked"):
            st.session_state["create_submit_clicked"] = False
            errors = []
            if not titulo.strip():
                errors.append("El título es obligatorio.")
            manual_mode = bool(st.session_state.get("manual_mode", False))
            manual_nombre = (st.session_state.get("create_cliente_manual_nombre", "") or "").strip()
            cliente_id = st.session_state.get("create_cliente_id")
            if not cliente_id and not manual_nombre:
                errors.append("El cliente es obligatorio.")
            try:
                raw_val_chk = str(st.session_state.get("create_valor", ""))
                digits_chk = "".join(ch for ch in raw_val_chk if ch.isdigit())
                if not digits_chk:
                    errors.append("El importe es obligatorio.")
            except Exception:
                errors.append("El importe es obligatorio.")
            if not fecha_cierre:
                errors.append("La fecha prevista de cierre es obligatoria.")
            marca_nombre = st.session_state.get("create_marca")
            if not marca_nombre:
                errors.append("La marca es obligatoria.")
            if not descripcion or len(str(descripcion).strip()) < 100:
                errors.append("La descripción debe tener al menos 100 caracteres.")
            docs_to_save = initial_files or []
            if not docs_to_save:
                errors.append("Debe adjuntar al menos un documento PDF.")
            if errors:
                for e in errors:
                    st.error(e)
                return
            try:
                raw_val = str(st.session_state.get("create_valor", ""))
                digits = "".join(ch for ch in raw_val if ch.isdigit())
                if digits:
                    as_int = int(digits)
                    st.session_state["create_valor"] = f"{as_int:,}".replace(",", ".")
            except Exception:
                pass

            try:
                _raw_val = str(st.session_state.get("create_valor", ""))
                _digits = "".join(ch for ch in _raw_val if ch.isdigit())
                _valor_int = int(_digits) if _digits else None
            except Exception:
                _valor_int = None
            _moneda = st.session_state.get("create_moneda")
            _etiqueta = st.session_state.get("create_etiqueta")
            _prob = st.session_state.get("create_probabilidad")
            _cierre = st.session_state.get("create_cierre")
            _marca_id = None
            try:
                if not marcas_df.empty and marca_nombre:
                    _marca_id = int(marcas_df.loc[marcas_df["nombre"] == marca_nombre, "id_marca"].iloc[0])
            except Exception:
                _marca_id = None

            extra_cliente_text = (st.session_state.get("create_cliente_manual_textbox") or "").strip()
            final_descripcion = descripcion
            if manual_mode and extra_cliente_text:
                final_descripcion = f"Cliente (manual):\n{extra_cliente_text}\n\n{str(descripcion or '')}"
            pid = create_proyecto(
                user_id,
                titulo,
                final_descripcion,
                (int(cliente_id) if (cliente_id is not None and not manual_mode) else None),
                estado,
                valor=_valor_int,
                moneda=_moneda,
                etiqueta=_etiqueta,
                probabilidad=_prob,
                fecha_cierre=_cierre,
                marca_id=_marca_id,
                contacto_id=st.session_state.get("create_contacto_id"),
                tipo_venta=st.session_state.get("create_tipo_venta")
            )
            if pid is None:
                details = None
                try:
                    log_path = os.path.join(os.getcwd(), "logs", "sql", "sql_errors.log")
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        tail = "".join(lines[-5:]) if lines else None
                        details = tail
                except Exception:
                    details = None
                st.error("No se pudo crear el proyecto.")
                if details:
                    st.caption(f"Detalle: {details}")
                st.info("Verifique: Estado permitido, fecha de cierre válida, cliente seleccionado o carga manual, marca seleccionada, descripción mínima de 100 caracteres.")
                return

            set_proyecto_shares(pid, user_id, share_ids)

            if docs_to_save:
                save_dir = os.path.join(os.getcwd(), "uploads", "projects", str(pid))
                os.makedirs(save_dir, exist_ok=True)
                for f in docs_to_save:
                    unique_name = _unique_filename(save_dir, f.name)
                    file_path = os.path.join(save_dir, unique_name)
                    with open(file_path, "wb") as out:
                        out.write(f.getvalue())
                    try:
                        add_proyecto_document(
                            project_id=int(pid),
                            owner_user_id=int(user_id),
                            filename=str(unique_name),
                            file_path=str(file_path),
                            mime_type="application/pdf",
                            file_size=len(f.getvalue())
                        )
                    except Exception:
                        pass

        # Notificar y limpiar
        try:
            st.session_state["create_success_pid"] = int(pid)
            st.success(f"Proyecto creado correctamente (ID {int(pid)}).")
            for k in [
                "create_valor","create_moneda","create_etiqueta","create_probabilidad","create_cierre",
                "create_marca","create_estado","create_tipo_venta","create_contacto_id","create_cliente_id",
                "create_cliente","create_cliente_manual_nombre","create_cliente_manual_tel","create_cliente_manual_cuit",
                "create_cliente_manual_cel","create_cliente_manual_web","create_cliente_manual_tipo","create_cliente_manual_email",
                "create_cliente_text","create_cliente_manual_textbox","manual_request_open","manual_confirm"
            ]:
                try:
                    st.session_state.pop(k, None)
                except Exception:
                    pass
            st.session_state["manual_mode"] = False
        except Exception:
            pass
        try:
            st.query_params["manual"] = "0"
        except Exception:
            pass

    # Limpieza de estados obsoletos
    if st.session_state.get("create_after_dialog") and not submitted:
        st.session_state.pop("create_after_dialog", None)
        st.session_state["create_submit_clicked"] = False

def render_my_projects(user_id):
    st.subheader("Mis Proyectos")

    # Selección por query params; soporta repliegue si el valor está vacío
    params = st.query_params
    if "myproj" in params:
        raw = params["myproj"]
        pid_str = raw[0] if isinstance(raw, list) else raw
        if pid_str:
            try:
                st.session_state["selected_project_id"] = int(pid_str)
            except Exception:
                st.session_state.pop("selected_project_id", None)
        else:
            st.session_state.pop("selected_project_id", None)
    else:
        st.session_state.pop("selected_project_id", None)

    df = get_proyectos_by_owner(user_id)
    if df.empty:
        return

    # Estilos de tarjetas con punto por estado y pill a la derecha
    st.markdown("""
    <style>
      .project-card {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        background: #1f2937;
        border: 1px solid #374151;
        color: #e5e7eb;
        padding: 20px 24px;
        border-radius: 14px;
        box-sizing: border-box;
        text-decoration: none;
        box-shadow: 0 4px 10px rgba(0,0,0,0.25);
      }
      .project-card + .project-card { margin-top: 14px; }
      .project-card:hover {
        background: #111827;
        border-color: #2563eb;
        transform: translateY(-1px);
        transition: all .15s ease-in-out;
      }
      .project-info { display: flex; flex-direction: column; }
      .project-title {
        display: flex; align-items: center; gap: 10px;
        font-size: 22px; font-weight: 700;
      }
      .dot-left { width: 10px; height: 10px; border-radius: 50%; }
      .dot-left.prospecto { background: #60a5fa; }
      .dot-left.presupuestado { background: #34d399; }
      .dot-left.negociación { background: #8b5cf6; }
      .dot-left.objeción { background: #fbbf24; }
      .dot-left.ganado { background: #065f46; }
      .dot-left.perdido { background: #ef4444; }
      .project-sub { margin-top: 4px; color: #9ca3af; font-size: 16px; }
      .project-sub2 { margin-top: 2px; color: #9ca3af; font-size: 15px; }
      .status-pill {
        padding: 10px 16px; border-radius: 999px;
        font-size: 18px; font-weight: 700;
        border: 2px solid transparent;
      }
      .status-pill.prospecto { color: #60a5fa; border-color: #60a5fa; }
      .status-pill.presupuestado { color: #34d399; border-color: #34d399; }
      .status-pill.negociación { color: #8b5cf6; border-color: #8b5cf6; }
      .status-pill.objeción { color: #fbbf24; border-color: #fbbf24; }
      .status-pill.ganado { color: #065f46; border-color: #065f46; }
      .status-pill.perdido { color: #ef4444; border-color: #ef4444; }
      /* Formulario clickeable: botón invisible cubre toda la tarjeta */
      .card-form { position: relative; display: block; }
      .card-form .card-submit {
        position: absolute; inset: 0; width: 100%; height: 100%;
        background: transparent; border: 0; padding: 0; margin: 0;
        cursor: pointer; opacity: 0; box-shadow: none; outline: none;
      }
      .card-form { margin-bottom: 18px; }
      .card-details-gap { height: 16px; }
      /* Estado visual de tarjeta seleccionada */
      .project-card.selected { background:#0a1324; border-color:#2563eb; box-shadow:0 0 0 2px rgba(37,99,235,0.30) inset; }
      /* Panel de detalle estilizado */
      .detail-panel { width:100%; background:#0b1220; border:1px solid #374151; border-radius:14px; padding:16px 18px; color:#e5e7eb; box-shadow:0 4px 10px rgba(0,0,0,0.25); }
      .detail-grid { display:grid; grid-template-columns: 160px 1fr; gap:8px 14px; align-items:center; }
      .detail-label { color:#9ca3af; font-weight:600; }
      .detail-value { color:#e5e7eb; }
      .detail-divider { margin:12px 0; border-top:1px dashed #374151; }
      .ext-link-btn { display:inline-block; padding:6px 10px; border:1px solid #374151; border-radius:8px; color:#e5e7eb !important; text-decoration:none !important; background:#111827; cursor:pointer; }
      .ext-link-btn:hover { border-color:#2563eb; background:#0b1220; color:#e5e7eb !important; text-decoration:none !important; }
    </style>
    """, unsafe_allow_html=True)
    if st.session_state.get("last_success_message"):
        st.success(st.session_state.get("last_success_message"))
        st.session_state.pop("last_success_message", None)

    # Filtros: Cliente, Nombre del proyecto, Estado
    estados_disponibles = PROYECTO_ESTADOS

    fcol1, fcol2, fcol3 = st.columns([2, 2, 2])
    with fcol1:
        filtro_cliente = st.text_input("Cliente", key="my_filter_cliente")
    with fcol2:
        filtro_nombre = st.text_input("Nombre del proyecto", key="my_filter_nombre")
    with fcol3:
        filtro_estados = st.multiselect("Estado", options=estados_disponibles, key="my_filter_estado")

    def _norm(s):
        return str(s or "").strip()

    df_filtrado = df.copy()
    if filtro_cliente:
        df_filtrado = df_filtrado[df_filtrado.get("cliente_nombre", pd.Series(dtype=str)).fillna("").str.contains(filtro_cliente, case=False, na=False)]
    if filtro_nombre:
        df_filtrado = df_filtrado[df_filtrado.get("titulo", pd.Series(dtype=str)).fillna("").str.contains(filtro_nombre, case=False, na=False)]
    if filtro_estados:
        df_filtrado = df_filtrado[
            df_filtrado.get("estado", pd.Series(dtype=str)).fillna("").apply(_estado_to_class).isin([e.lower() for e in filtro_estados])
        ]

    df = df_filtrado

    # Mejora de contraste del desplegable/multiselect (compartir)
    st.markdown("""
    <style>
      div[data-baseweb="select"] {
        background: #111827 !important;
        border: 1px solid #ef4444 !important;
        border-radius: 12px !important;
      }
      div[data-baseweb="select"] * { color: #e5e7eb !important; }
      /* Panel de detalles, ítems verticales y más espaciado */
      .detail-panel { width:100%; max-width: 980px; margin: 0 auto; background:#0b1220; border:1px solid #374151; border-radius:14px; padding:24px 26px; color:#e5e7eb; box-shadow:0 4px 12px rgba(0,0,0,0.28); }
      .detail-item { margin-bottom: 18px; }
      .detail-label { display:block; color:#9ca3af; font-weight:700; font-size:18px; margin-bottom:6px; }
      .detail-value { display:block; color:#e5e7eb; font-size:20px; }
      .detail-divider { margin:18px 0; border-top:1px dashed #374151; }
      .doc-header { font-size:20px; font-weight:800; color:#e5e7eb; margin-bottom:8px; }
    </style>
    """, unsafe_allow_html=True)
    

    selected_pid = st.session_state.get("selected_project_id")

    # Si se solicita vista previa en nueva pestaña, mostrar solo el visor y salir
    params = st.query_params
    try:
        raw_prev = params.get("previewdoc")
        prev_id_str = raw_prev[0] if isinstance(raw_prev, list) else raw_prev
        preview_doc_id = int(prev_id_str) if prev_id_str else None
    except Exception:
        preview_doc_id = None
    if selected_pid and preview_doc_id:
        docs_df_preview = get_proyecto_documentos(selected_pid)
        match = docs_df_preview.loc[docs_df_preview["id"] == preview_doc_id]
        if not match.empty:
            file_path = match.iloc[0]["file_path"]
            st.subheader("Vista previa")
            href = _make_static_preview_link(file_path, preview_doc_id)
            if href:
                # Botón para abrir en nueva pestaña con visor nativo del navegador
                abs_url = _absolute_static_url(href)
                st.link_button("Abrir en navegador", abs_url)
                # Visor por URL estática
                _render_pdf_preview_url(href, height=800)
                # Fallback: visor embebido en base64 si el anterior no carga
                with st.expander("Si no se ve, usar visor alterno"):
                    _render_pdf_preview(file_path, height=800)
            else:
                # Si no pudimos preparar URL estática, usar el visor embebido directamente
                _render_pdf_preview(file_path, height=800)
            # Link para volver sin el parámetro de vista previa
            def qp(k):
                v = params.get(k)
                return (v[0] if isinstance(v, list) else v) if v else ""
            uid = qp("uid"); uexp = qp("uexp"); usig = qp("usig")
            back_href = f"?ptab=📚 Mis Proyectos&myproj={selected_pid}" + \
                        (f"&uid={uid}" if uid else "") + \
                        (f"&uexp={uexp}" if uexp else "") + \
                        (f"&usig={usig}" if usig else "")
            st.markdown(f"<a href=\"{back_href}\" class=\"ext-link-btn\">Volver</a>", unsafe_allow_html=True)
            return

    page_size = 10
    total_items = len(df)
    page = int(st.session_state.get("my_projects_page", 1) or 1)
    total_pages = max((total_items + page_size - 1) // page_size, 1)
    if page > total_pages:
        page = total_pages
    if page < 1:
        page = 1
    st.session_state["my_projects_page"] = page
    start = (page - 1) * page_size
    end = start + page_size
    df_page = df.iloc[start:end]
    count_text = f"Mostrando elementos {start+1}-{min(end, total_items)} de {total_items}"
    for _, r in df_page.iterrows():
        pid = int(r["id"])
        estado = _estado_to_class(r.get("estado"))
        estado_disp = _estado_display(r.get("estado"))
        title = r["titulo"]
        cliente = r.get("cliente_nombre") or "Sin cliente"
        try:
            _fc_dt = pd.to_datetime(r.get("fecha_cierre"), errors="coerce")
            fc_fmt = _fc_dt.strftime("%d/%m/%Y") if not pd.isna(_fc_dt) else "-"
        except Exception:
            fc_fmt = "-"
        tipo_venta_card = r.get("tipo_venta") or "-"
        # Preservar uid/uexp/usig del URL al enviar el formulario
        params = st.query_params
        def get_param(k):
            v = params.get(k)
            return (v[0] if isinstance(v, list) else v) if v else ""
        hidden_uid = get_param("uid")
        hidden_uexp = get_param("uexp")
        hidden_usig = get_param("usig")
        hidden_val = "" if selected_pid == pid else str(pid)
        selected_class = " selected" if selected_pid == pid else ""

        st.markdown(
            f"""
            <form method=\"get\" class=\"card-form\">
              <input type=\"hidden\" name=\"myproj\" value=\"{hidden_val}\" />
              <input type=\"hidden\" name=\"ptab\" value=\"📚 Mis Proyectos\" />
              {f'<input type=\"hidden\" name=\"uid\" value=\"{hidden_uid}\" />' if hidden_uid else ''}
              {f'<input type=\"hidden\" name=\"uexp\" value=\"{hidden_uexp}\" />' if hidden_uexp else ''}
              {f'<input type=\"hidden\" name=\"usig\" value=\"{hidden_usig}\" />' if hidden_usig else ''}
              <div class=\"project-card{selected_class}\">
                <div class=\"project-info\">
                  <div class=\"project-title\">
                    <span class=\"dot-left {estado}\"></span>
                    <span>{title}</span>
                  </div>
                  <div class=\"project-sub\">ID {pid} · {cliente}</div>
                  <div class=\"project-sub2\">Cierre: {fc_fmt} · {tipo_venta_card}</div>
                </div>
                <span class=\"status-pill {estado}\">{estado_disp}</span>
              </div>
              <button type=\"submit\" class=\"card-submit\"></button>
            </form>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    controls = st.columns([2, 1, 1])
    with controls[0]:
        st.caption(count_text)
    with controls[1]:
        prev_clicked = st.button("Anterior", disabled=(page <= 1), key="my_prev_page")
    with controls[2]:
        next_clicked = st.button("Siguiente", disabled=(page >= total_pages), key="my_next_page")
    if prev_clicked and page > 1:
        st.session_state["my_projects_page"] = page - 1
        st.rerun()
    if next_clicked and page < total_pages:
        st.session_state["my_projects_page"] = page + 1
        st.rerun()

    # Sin mensaje: retorno silencioso si no hay selección
    if not selected_pid:
        return

    # Editor del proyecto seleccionado
    data = get_proyecto(selected_pid)
    if not data:
        st.error("No se pudo cargar el proyecto.")
        return

    st.divider()
    st.subheader("Editar proyecto")
    st.markdown("<div class='card-details-gap'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        <style>
        .stSelectbox div[data-baseweb="select"] { background-color: transparent; border-color: #444; }
        .stSelectbox { margin-top: -6px; }
        .client-grid { display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-top:10px; }
        .client-card { background:#111827; border:1px solid #374151; border-radius:12px; padding:12px; }
        .client-title { font-weight:600; color:#9ca3af; margin-bottom:6px; }
        .client-value { color:#e5e7eb; }
        .section-gap { height: 12px; }
        .section-line { height: 1px; background:#334155; border-radius:999px; margin: 14px 0; }
        @media (max-width: 768px) { .client-grid { grid-template-columns: 1fr; } }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # FORM: evita rerender al cambiar widgets; sólo refresca al enviar
    with st.form(key=f"edit_form_{selected_pid}"):
        # Título primero
        titulo = st.text_input("Título", value=data["titulo"], key=f"edit_titulo_{selected_pid}")

        # Bloque: Datos del cliente
        st.markdown("**Datos del cliente**")
        clientes_df = get_clientes_dataframe()
        all_clients = clientes_df["nombre"].tolist()
        current_client_name = data.get("cliente_nombre") or ""
        # Solo select con nombre dinámico solicitado
        dyn_name_e = st.session_state.get(f"edit_cliente_name_{selected_pid}")
        client_opts_e = all_clients.copy()
        if dyn_name_e and dyn_name_e not in client_opts_e:
            client_opts_e = [dyn_name_e] + client_opts_e
        cliente_nombre = st.selectbox(
            "Cliente",
            options=client_opts_e,
            index=(client_opts_e.index(current_client_name) if current_client_name in client_opts_e else 0),
            key=f"edit_cliente_{selected_pid}",
            placeholder="Seleccione cliente"
        )
        try:
            cliente_id = int(clientes_df.loc[clientes_df["nombre"] == cliente_nombre, "id_cliente"].iloc[0])
        except Exception:
            cliente_id = None
        # Resumen de cliente en tarjetas
        try:
            sel_row_c = clientes_df.loc[clientes_df["nombre"] == cliente_nombre].iloc[0] if cliente_nombre else None
        except Exception:
            sel_row_c = None
        name_val_c = str(cliente_nombre or "")
        tel_val_c = str((sel_row_c["telefono"] if sel_row_c is not None else "") or "")
        email_val_c = str((sel_row_c["email"] if sel_row_c is not None else "") or "")
        web_val_c = "-"; cuit_val_c = "-"; cel_val_c = "-"; tipo_val_c = "-"
        st.markdown(
            f"""
            <div class='client-grid'>
              <div class='client-card'>
                <div class='client-title'>Nombre del cliente</div>
                <div class='client-value'>{name_val_c}</div>
              </div>
              <div class='client-card'>
                <div class='client-title'>Teléfono</div>
                <div class='client-value'>{tel_val_c or '-'}</div>
              </div>
              <div class='client-card'>
                <div class='client-title'>Email</div>
                <div class='client-value'>{email_val_c or '-'}</div>
              </div>
              <div class='client-card'>
                <div class='client-title'>Web</div>
                <div class='client-value'>{web_val_c}</div>
              </div>
              <div class='client-card'>
                <div class='client-title'>CUIT</div>
                <div class='client-value'>{cuit_val_c}</div>
              </div>
              <div class='client-card'>
                <div class='client-title'>Celular</div>
                <div class='client-value'>{cel_val_c}</div>
              </div>
              <div class='client-card'>
                <div class='client-title'>Tipo</div>
                <div class='client-value'>{tipo_val_c}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Bloque: Contacto (entre cliente y datos del proyecto)
        st.markdown("**Contacto**")
        contacto_options_e = []
        contacto_ids_e = []
        try:
            if cliente_id:
                cdf = get_contactos_por_cliente(cliente_id)
                for _, r in cdf.iterrows():
                    disp = f"{r['nombre']} {str(r['apellido'] or '').strip()}".strip()
                    if r.get('puesto'):
                        disp = f"{disp} - {r['puesto']}"
                    contacto_options_e.append(disp)
                    contacto_ids_e.append(int(r["id_contacto"]))
            current_marca_e = (st.session_state.get(f"edit_marca_{selected_pid}") or data.get("marca_nombre") or "").strip()
            if current_marca_e:
                marcas_df_pre_e = get_marcas_dataframe()
                try:
                    marca_id_pre_e = int(marcas_df_pre_e.loc[marcas_df_pre_e["nombre"] == current_marca_e, "id_marca"].iloc[0])
                except Exception:
                    marca_id_pre_e = None
                if marca_id_pre_e:
                    mdf = get_contactos_por_marca(marca_id_pre_e)
                    for _, r in mdf.iterrows():
                        disp = f"{r['nombre']} {str(r['apellido'] or '').strip()}".strip()
                        if r.get('puesto'):
                            disp = f"{disp} - {r['puesto']}"
                        if int(r["id_contacto"]) not in contacto_ids_e:
                            contacto_options_e.append(disp)
                            contacto_ids_e.append(int(r["id_contacto"]))
        except Exception:
            contacto_options_e, contacto_ids_e = [], []
        default_contact_id = data.get("contacto_id")
        default_index = contacto_ids_e.index(int(default_contact_id)) if (default_contact_id and int(default_contact_id) in contacto_ids_e) else None
        contacto_choice_e = st.selectbox(
            "Contacto",
            options=contacto_options_e if contacto_options_e else ["(Sin contactos disponibles)"],
            index=default_index if default_index is not None else (0 if contacto_options_e else None),
            key=f"edit_contacto_display_{selected_pid}",
        )
        try:
            st.session_state[f"edit_contacto_id_{selected_pid}"] = contacto_ids_e[contacto_options_e.index(contacto_choice_e)] if contacto_options_e else None
        except Exception:
            st.session_state[f"edit_contacto_id_{selected_pid}"] = None
        # Resumen de contacto en tarjetas
        try:
            sel_cid_e = st.session_state.get(f"edit_contacto_id_{selected_pid}")
            sel_row_e = cdf.loc[cdf["id_contacto"] == int(sel_cid_e)].iloc[0] if (sel_cid_e and not cdf.empty) else None
        except Exception:
            sel_row_e = None
        if sel_row_e is not None:
            st.markdown("<div class='section-gap'></div>", unsafe_allow_html=True)
            nombre_full_e = f"{str(sel_row_e['nombre'] or '').strip()} {str(sel_row_e['apellido'] or '').strip()}".strip()
            puesto_val_e = str(sel_row_e.get('puesto') or '-')
            tel_val_e = str(sel_row_e.get('telefono') or '-')
            email_val_e = str(sel_row_e.get('email') or '-')
            dir_val_e = str(sel_row_e.get('direccion') or '-')
            st.markdown(
                f"""
                <div class='client-grid'>
                  <div class='client-card'>
                    <div class='client-title'>Nombre</div>
                    <div class='client-value'>{nombre_full_e}</div>
                  </div>
                  <div class='client-card'>
                    <div class='client-title'>Puesto</div>
                    <div class='client-value'>{puesto_val_e}</div>
                  </div>
                  <div class='client-card'>
                    <div class='client-title'>Teléfono</div>
                    <div class='client-value'>{tel_val_e}</div>
                  </div>
                  <div class='client-card'>
                    <div class='client-title'>Email</div>
                    <div class='client-value'>{email_val_e}</div>
                  </div>
                  <div class='client-card'>
                    <div class='client-title'>Dirección</div>
                    <div class='client-value'>{dir_val_e}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("<div class='section-line'></div>", unsafe_allow_html=True)

        st.divider()
        # Bloque: Datos del proyecto
        st.markdown("**Datos del proyecto**")
        vd_cols = st.columns(2)
        with vd_cols[0]:
            val_cols = st.columns([1, 1])
            with val_cols[0]:
                _v_init = data.get("valor")
                _v_show = f"{int(_v_init):,}".replace(",", ".") if _v_init is not None else ""
                valor_raw = st.text_input(
                    "Valor",
                    value=_v_show,
                    key=f"edit_valor_{selected_pid}"
                )
            with val_cols[1]:
                _m_init = (data.get("moneda") or "ARS")
                _m_index = ["ARS", "USD"].index(_m_init) if _m_init in ["ARS", "USD"] else 0
                moneda = st.selectbox("Moneda", ["ARS", "USD"], index=_m_index, key=f"edit_moneda_{selected_pid}")
            etiqueta = st.text_input("Etiqueta", value=data.get("etiqueta") or "", key=f"edit_tag_{selected_pid}")
            _prob_init = int(data.get("probabilidad") or 0)
            probabilidad = st.slider("Probabilidad", min_value=0, max_value=100, value=_prob_init, format="%d%%", key=f"edit_prob_{selected_pid}")
            _tv_init = data.get("tipo_venta") or PROYECTO_TIPOS_VENTA[0]
            _tv_index = PROYECTO_TIPOS_VENTA.index(_tv_init) if _tv_init in PROYECTO_TIPOS_VENTA else 0
            tipo_venta_e = st.selectbox("Tipo de Venta", options=PROYECTO_TIPOS_VENTA, index=_tv_index, key=f"edit_tipo_venta_{selected_pid}")
        with vd_cols[1]:
            marcas_df = get_marcas_dataframe()
            marca_options = marcas_df["nombre"].tolist()
            current_marca = data.get("marca_nombre") or (marca_options[0] if marca_options else "")
            marca_nombre = st.selectbox(
                "Marca",
                options=marca_options,
                index=marca_options.index(current_marca) if current_marca in marca_options else 0,
                key=f"edit_marca_{selected_pid}"
            )
            _fc_init = data.get("fecha_cierre")
            fecha_cierre = st.date_input("Fecha prevista de cierre", value=_fc_init, key=f"edit_cierre_{selected_pid}")
        

        # Agregar opción especial solo en "Mis Proyectos" para eliminar (sin puntos)
        estado_options = PROYECTO_ESTADOS + ["Eliminar"]
        try:
            estado_index = PROYECTO_ESTADOS.index((data["estado"] or "").strip())
        except Exception:
            estado_index = 0
        estado = st.selectbox(
            "Estado",
            options=estado_options,
            index=estado_index,
            key=f"edit_estado_{selected_pid}"
        )

        # Ocultar la descripción auto-generada previa para que el usuario escriba la suya
        _desc_raw = data.get("descripcion") or ""
        _desc_value = "" if _is_auto_description(_desc_raw) else _desc_raw
        descripcion = st.text_area("Descripción", value=_desc_value, key=f"edit_desc_{selected_pid}")

        st.divider()
        st.subheader("Documentos")
        files = st.file_uploader(
            "Adjuntar nuevos documentos (PDF)",
            accept_multiple_files=True,
            type=["pdf"],
            key=f"uploader_{selected_pid}"
        )
        docs_df = get_proyecto_documentos(selected_pid)
        selected_doc_id = None
        if not docs_df.empty:
            ids = [int(x) for x in docs_df['id'].tolist()]
            labels = {}
            for _, d in docs_df.iterrows():
                fid = int(d['id'])
                fn = d['filename']
                labels[fid] = fn
            selected_doc_id = st.selectbox(
                "Archivo",
                options=ids,
                format_func=lambda i: labels.get(int(i), str(i)),
                key=f"doc_selector_{selected_pid}"
            )
            sel_row = docs_df.loc[docs_df['id'] == int(selected_doc_id)].iloc[0]
            fp = sel_row['file_path']
            fn = sel_row['filename']
            if not os.path.exists(fp):
                candidate = os.path.join(os.getcwd(), "uploads", "projects", str(selected_pid), fn)
                if os.path.exists(candidate):
                    fp = candidate
                    try:
                        from .database import update_proyecto_document_path
                        update_proyecto_document_path(int(selected_doc_id), fp)
                    except Exception:
                        pass
            exists = os.path.exists(fp)
            if not exists:
                st.error("Archivo no encontrado en almacenamiento.")
            cols = st.columns([3, 1, 1, 1, 3])
            href = _pdf_data_url(fp) if exists else None
            with cols[1]:
                if href:
                    st.markdown(f"<a href='{href}' download='{fn}' class='ext-link-btn'>Descargar</a>", unsafe_allow_html=True)
                else:
                    st.markdown("<a class='ext-link-btn' style='pointer-events:none;opacity:.6'>Descargar</a>", unsafe_allow_html=True)
            with cols[2]:
                if href:
                    st.markdown(f"<a href='{href}' target='_blank' class='ext-link-btn'>Vista previa</a>", unsafe_allow_html=True)
                else:
                    st.markdown("<a class='ext-link-btn' style='pointer-events:none;opacity:.6'>Vista previa</a>", unsafe_allow_html=True)
            with cols[3]:
                del_submit = st.form_submit_button("Eliminar")
        else:
            st.caption("No hay documentos cargados para este proyecto.")

        st.divider()
        share_options, name_to_id, id_to_name = [], {}, {}
        default_names = []
        try:
            current_user_rol_id = get_user_rol_id(user_id)
            commercial_users_df = get_users_by_rol(current_user_rol_id)
            id_to_name = {
                int(u["id"]): f"{u['nombre']} {u['apellido']}"
                for _, u in commercial_users_df.iterrows()
                if int(u["id"]) != int(user_id)
            }
            share_options = list(id_to_name.values())
            name_to_id = {v: k for k, v in id_to_name.items()}
            current_shared = pd.read_sql_query(
                text("SELECT user_id FROM proyecto_compartidos WHERE proyecto_id = :pid"),
                con=get_engine(),
                params={"pid": int(selected_pid)}
            )
            default_names = [
                id_to_name[int(u)]
                for u in current_shared["user_id"].tolist()
                if int(u) in id_to_name
            ]
        except Exception:
            pass
        share_users = st.multiselect(
            "Compartir con:",
            options=share_options,
            default=default_names,
            key=f"share_users_{selected_pid}"
        )

        submitted = st.form_submit_button("Guardar cambios", type="primary")

    
    # Documentos y compartidos se gestionan dentro del formulario de edición

    # Sección de visualización de documentos fuera del formulario eliminada

    share_options, name_to_id, id_to_name = [], {}, {}
    default_names = []
    try:
        current_user_rol_id = get_user_rol_id(user_id)
        commercial_users_df = get_users_by_rol(current_user_rol_id)
        id_to_name = {
            int(u["id"]): f"{u['nombre']} {u['apellido']}"
            for _, u in commercial_users_df.iterrows()
            if int(u["id"]) != int(user_id)
        }
        share_options = list(id_to_name.values())
        name_to_id = {v: k for k, v in id_to_name.items()}

        current_shared = pd.read_sql_query(
            text("SELECT user_id FROM proyecto_compartidos WHERE proyecto_id = :pid"),
            con=get_engine(),
            params={"pid": int(selected_pid)}
        )
        default_names = [
            id_to_name[int(u)]
            for u in current_shared["user_id"].tolist()
            if int(u) in id_to_name
        ]
    except Exception:
        pass

    

    # Eliminar documento dentro del mismo formulario
    if 'del_submit' in locals() and del_submit and st.session_state.get(f"doc_selector_{selected_pid}"):
        try:
            if remove_proyecto_document(int(st.session_state.get(f"doc_selector_{selected_pid}")), user_id):
                st.success("Archivo eliminado.")
                st.rerun()
            else:
                st.error("No se pudo eliminar el documento.")
        except Exception:
            st.error("No se pudo eliminar el documento.")
        return

    if submitted:
        # El flujo de solicitud se maneja por selección del desplegable
        pass
        # Si el usuario eligió "Eliminar", confirmar antes de proceder
        if estado == "Eliminar":
            @st.dialog("Confirmar eliminación")
            def _confirm_delete_dialog():
                st.write("Vas a eliminar este proyecto. Esta acción no puede deshacerse.")
                bcols = st.columns(2)
                with bcols[0]:
                    if st.button("Aceptar", type="primary", key=f"confirm_del_{selected_pid}"):
                        if delete_proyecto(selected_pid, user_id):
                            st.success("Proyecto eliminado definitivamente.")
                            try:
                                st.query_params["myproj"] = ""
                                st.rerun()
                            except Exception:
                                pass
                        else:
                            st.error("No se pudo eliminar el proyecto.")
                with bcols[1]:
                    if st.button("Cancelar", type="secondary", key=f"cancel_del_{selected_pid}"):
                        st.session_state[f"edit_estado_{selected_pid}"] = (data["estado"] or "activo").strip().lower()
                        # No forzar rerun; se cerrará el diálogo y persistirán los valores actuales
            _confirm_delete_dialog()
        else:
            errors = []
            if not titulo.strip():
                errors.append("El título es obligatorio.")
            # Cliente: permitir guardar con texto aunque no exista
            if not cliente_id and not (st.session_state.get(f"edit_cliente_name_{selected_pid}") or "").strip():
                errors.append("El cliente es obligatorio.")
            try:
                _raw_val_e = str(st.session_state.get(f"edit_valor_{selected_pid}", ""))
                _digits_e = "".join(ch for ch in _raw_val_e if ch.isdigit())
                _valor_int_e = int(_digits_e) if _digits_e else None
                if _valor_int_e is None:
                    errors.append("El importe es obligatorio.")
            except Exception:
                _valor_int_e = None
                errors.append("El importe es obligatorio.")
            _moneda_e = st.session_state.get(f"edit_moneda_{selected_pid}")
            _etiqueta_e = st.session_state.get(f"edit_tag_{selected_pid}")
            _prob_e = st.session_state.get(f"edit_prob_{selected_pid}")
            marca_nombre_e = st.session_state.get(f"edit_marca_{selected_pid}")
            _cierre_e = st.session_state.get(f"edit_cierre_{selected_pid}")
            if not _cierre_e:
                errors.append("La fecha prevista de cierre es obligatoria.")
            if not descripcion or len(str(descripcion).strip()) < 100:
                errors.append("La descripción debe tener al menos 100 caracteres.")
            _marca_id_e = None
            try:
                if marca_nombre_e and not marcas_df.empty:
                    _marca_id_e = int(marcas_df.loc[marcas_df["nombre"] == marca_nombre_e, "id_marca"].iloc[0])
            except Exception:
                _marca_id_e = None
            if _marca_id_e is None:
                errors.append("La marca es obligatoria.")
            if errors:
                for e in errors:
                    st.error(e)
                return

            if update_proyecto(
                selected_pid,
                user_id,
                titulo=titulo,
                descripcion=descripcion,
                cliente_id=cliente_id,
                estado=estado,
                valor=_valor_int_e,
                moneda=_moneda_e,
                etiqueta=_etiqueta_e,
                probabilidad=_prob_e,
                fecha_cierre=_cierre_e,
                marca_id=_marca_id_e,
                contacto_id=st.session_state.get(f"edit_contacto_id_{selected_pid}"),
                tipo_venta=st.session_state.get(f"edit_tipo_venta_{selected_pid}")
            ):
                # Guardar documentos adjuntos
                try:
                    if 'files' in locals() and files:
                        save_dir = os.path.join(os.getcwd(), "uploads", "projects", str(selected_pid))
                        os.makedirs(save_dir, exist_ok=True)
                        for f in files:
                            unique_name = _unique_filename(save_dir, f.name)
                            file_path = os.path.join(save_dir, unique_name)
                            with open(file_path, "wb") as out:
                                out.write(f.getvalue())
                            add_proyecto_document(selected_pid, user_id, unique_name, file_path, f.type, len(f.getvalue()))
                except Exception:
                    st.warning("Algunos documentos no pudieron guardarse.")

                # Actualizar compartidos dentro del mismo submit
                try:
                    if 'share_users' in locals():
                        set_proyecto_shares(selected_pid, user_id, [name_to_id[n] for n in share_users])
                except Exception:
                    st.warning("No se pudieron actualizar los compartidos.")

                st.session_state["last_success_message"] = "Cambios guardados exitosamente."
                try:
                    st.query_params["ptab"] = "📚 Mis Proyectos"
                    st.query_params["myproj"] = ""
                    st.rerun()
                except Exception:
                    st.success("Cambios guardados exitosamente.")
            else:
                st.error("No se pudo actualizar el proyecto.")


def render_contacts_management(user_id):
    st.subheader("Contactos")

    st.markdown("""
    <style>
      .shared-card {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        background: #1f2937;
        border: 1px solid #374151;
        color: #e5e7eb;
        padding: 20px 24px;
        border-radius: 14px;
        box-sizing: border-box;
        text-decoration: none;
        box-shadow: 0 4px 10px rgba(0,0,0,0.25);
      }
      .shared-card + .shared-card { margin-top: 14px; }
      .shared-card:hover {
        background: #111827;
        border-color: #2563eb;
        transform: translateY(-1px);
        transition: all .15s ease-in-out;
      }
      .shared-info { display: flex; flex-direction: column; }
      .shared-title {
        display: flex; align-items: center; gap: 10px;
        font-size: 20px; font-weight: 600;
      }
      .dot-left { width: 10px; height: 10px; border-radius: 50%; }
      .dot-left.prospecto { background: #60a5fa; }
      .shared-sub { margin-top: 4px; color: #9ca3af; font-size: 16px; }
      .shared-sub2 { margin-top: 2px; color: #9ca3af; font-size: 15px; }
      .status-pill { padding: 10px 16px; border-radius: 999px; font-size: 18px; font-weight: 700; border: 2px solid #60a5fa; color:#60a5fa; }
      .card-details-gap { height: 16px; }
      .card-form { position: relative; display: block; }
      .card-form .card-submit { position: absolute; inset: 0; width: 100%; height: 100%; background: transparent; border: 0; padding: 0; margin: 0; cursor: pointer; opacity: 0; box-shadow: none; outline: none; }
      .shared-card.selected { background:#0a1324; border-color:#2563eb; box-shadow:0 0 0 2px rgba(37,99,235,0.30) inset; }
      .contact-form-card { background:#0b1220; border:1px solid #374151; border-radius:14px; padding:18px 20px; box-shadow:0 6px 16px rgba(0,0,0,0.30); }
      .contact-form-card:before { display:none !important; }
      .contact-form-title { font-size:22px; font-weight:800; color:#e5e7eb; margin-bottom:12px; letter-spacing:0.2px; }
      .contact-form-grid { display:grid; grid-template-columns: 1fr 1fr; gap:14px 18px; }
      .contact-form-row { display:grid; grid-template-columns: 1fr 1fr; gap:14px 18px; margin-top:6px; }
      .contact-form-actions { margin-top:16px; }
      .contact-form-card .stTextInput > div > div > input { background:#111827; color:#e5e7eb; border:1px solid #374151; }
      .contact-form-card .stTextInput > div > div > input:focus { border-color:#2563eb; box-shadow:0 0 0 1px #2563eb inset; }
      .contact-form-card .stTextArea textarea { background:#111827; color:#e5e7eb; border:1px solid #374151; }
      .contact-form-card .stTextArea textarea:focus { border-color:#2563eb; box-shadow:0 0 0 1px #2563eb inset; }
      .contact-form-card .stSelectbox div[data-baseweb="select"] { background:#111827; color:#e5e7eb; border:1px solid #374151; }
      .contact-form-card .stSelectbox div[data-baseweb="select"]:hover { border-color:#2563eb; }
      .contact-form-card .stButton > button { background:#1f2937; color:#e5e7eb; border:1px solid #374151; border-radius:10px; }
      .contact-form-card .stButton > button:hover { background:#111827; border-color:#2563eb; }
      .chip { display:inline-block; padding:6px 10px; border-radius:999px; border:1px solid #374151; color:#9ca3af; font-weight:700; font-size:12px; }
    </style>
    """, unsafe_allow_html=True)

    if st.button("Nuevo contacto", key="toggle_new_contact"):
        st.session_state["show_contact_form"] = not st.session_state.get("show_contact_form", False)

    if st.session_state.get("show_contact_form", False):
        with st.form("contact_form"):
            st.markdown("<div class='contact-form-title'>Crear nuevo contacto</div>", unsafe_allow_html=True)
            cols_main = st.columns(2)
            with cols_main[0]:
                nombre = st.text_input("Nombre", key="contact_nombre")
                apellido = st.text_input("Apellido", key="contact_apellido")
                puesto = st.text_input("Puesto", key="contact_puesto")
            with cols_main[1]:
                telefono = st.text_input("Teléfono", key="contact_telefono")
                email = st.text_input("Mail", key="contact_email")
                direccion = st.text_input("Dirección", key="contact_direccion")
            row = st.columns(2)
            with row[0]:
                etiqueta_tipo = st.selectbox("Etiqueta", options=["cliente", "marca"], index=0, key="contact_etiqueta_tipo")
            etiqueta_id = None
            entidad_nombre = None
            with row[1]:
                if etiqueta_tipo == "cliente":
                    cdf = get_clientes_dataframe()
                    c_opts = [(int(row["id_cliente"]), row["nombre"]) for _, row in cdf.iterrows()]
                    cid = st.selectbox("Cliente", options=[cid for cid, _ in c_opts], format_func=lambda cid: next(name for cid2, name in c_opts if cid2 == cid), key="contact_cliente_id")
                    etiqueta_id = cid
                    try:
                        entidad_nombre = next(name for cid2, name in c_opts if cid2 == cid)
                    except Exception:
                        entidad_nombre = None
                else:
                    mdf = get_marcas_dataframe()
                    m_opts = [(int(row["id_marca"]), row["nombre"]) for _, row in mdf.iterrows()]
                    mid = st.selectbox("Marca", options=[mid for mid, _ in m_opts], format_func=lambda mid: next(name for mid2, name in m_opts if mid2 == mid), key="contact_marca_id")
                    etiqueta_id = mid
                    try:
                        entidad_nombre = next(name for mid2, name in m_opts if mid2 == mid)
                    except Exception:
                        entidad_nombre = None
            from .database import add_contacto
            submitted = st.form_submit_button("Guardar contacto", type="primary")
            if submitted:
                if not str(nombre or "").strip():
                    st.error("El nombre es obligatorio")
                elif etiqueta_id is None:
                    st.error("Seleccione etiqueta y entidad")
                else:
                    ok = add_contacto(nombre, apellido, puesto, telefono, email, direccion, etiqueta_tipo, etiqueta_id)
                    if ok:
                        st.success("Contacto guardado")
                        st.session_state["show_contact_form"] = False
                        st.rerun()
                    else:
                        st.error("No se pudo guardar el contacto")

    st.divider()

    filtro_tipo = st.selectbox("Ver por", options=["cliente", "marca"], index=0, key="view_contact_tipo")
    entidad_id = None
    entidad_nombre = None
    if filtro_tipo == "cliente":
        cdf_v = get_clientes_dataframe()
        c_opts_v = [(int(row["id_cliente"]), row["nombre"]) for _, row in cdf_v.iterrows()]
        if c_opts_v:
            entidad_id = st.selectbox("Cliente", options=[cid for cid, _ in c_opts_v], format_func=lambda cid: next(name for cid2, name in c_opts_v if cid2 == cid), key="view_contact_cliente_id")
            try:
                entidad_nombre = next(name for cid2, name in c_opts_v if cid2 == entidad_id)
            except Exception:
                entidad_nombre = None
    else:
        mdf_v = get_marcas_dataframe()
        m_opts_v = [(int(row["id_marca"]), row["nombre"]) for _, row in mdf_v.iterrows()]
        if m_opts_v:
            entidad_id = st.selectbox("Marca", options=[mid for mid, _ in m_opts_v], format_func=lambda mid: next(name for mid2, name in m_opts_v if mid2 == mid), key="view_contact_marca_id")
            try:
                entidad_nombre = next(name for mid2, name in m_opts_v if mid2 == entidad_id)
            except Exception:
                entidad_nombre = None

    if entidad_id is None:
        return

    if filtro_tipo == "cliente":
        dfc = get_contactos_por_cliente(entidad_id)
        df_list = dfc
    else:
        dfm = get_contactos_por_marca(entidad_id)
        df_list = dfm

    if df_list.empty:
        st.info("No hay contactos para la selección")
        return

    params = st.query_params
    if "contactid" in params:
        raw = params["contactid"]
        cid_str = raw[0] if isinstance(raw, list) else raw
        if cid_str:
            try:
                st.session_state["selected_contact_id"] = int(cid_str)
            except Exception:
                st.session_state.pop("selected_contact_id", None)
        else:
            st.session_state.pop("selected_contact_id", None)

    selected_cid = st.session_state.get("selected_contact_id")
    def _get_param(k):
        v = params.get(k)
        return (v[0] if isinstance(v, list) else v) if v else ""
    _hidden_uid = _get_param("uid")
    _hidden_uexp = _get_param("uexp")
    _hidden_usig = _get_param("usig")

    ct_page_size = 10
    ct_total_items = len(df_list)
    ct_page = int(st.session_state.get("contacts_page", 1) or 1)
    ct_total_pages = max((ct_total_items + ct_page_size - 1) // ct_page_size, 1)
    if ct_page > ct_total_pages:
        ct_page = ct_total_pages
    if ct_page < 1:
        ct_page = 1
    st.session_state["contacts_page"] = ct_page
    ct_start = (ct_page - 1) * ct_page_size
    ct_end = ct_start + ct_page_size
    df_contacts_page = df_list.iloc[ct_start:ct_end]
    ct_count_text = f"Mostrando elementos {ct_start+1}-{min(ct_end, ct_total_items)} de {ct_total_items}"

    for _, r in df_contacts_page.iterrows():
        cid = int(r["id_contacto"]) if "id_contacto" in r else None
        nombre_full = f"{r['nombre']} {str(r.get('apellido') or '').strip()}".strip()
        puesto_disp = str(r.get('puesto') or '').strip() or "-"
        email_disp = str(r.get('email') or '').strip() or "-"
        tel_disp = str(r.get('telefono') or '').strip() or "-"
        selected_class = " selected" if selected_cid == cid else ""
        hidden_val = "" if selected_cid == cid else str(cid)
        st.markdown(
            f"""
            <form method=\"get\" class=\"card-form\">
              <input type=\"hidden\" name=\"ptab\" value=\"🧑‍💼 Contactos\" />
              <input type=\"hidden\" name=\"contactid\" value=\"{hidden_val}\" />
              {f'<input type=\"hidden\" name=\"uid\" value=\"{_hidden_uid}\" />' if _hidden_uid else ''}
              {f'<input type=\"hidden\" name=\"uexp\" value=\"{_hidden_uexp}\" />' if _hidden_uexp else ''}
              {f'<input type=\"hidden\" name=\"usig\" value=\"{_hidden_usig}\" />' if _hidden_usig else ''}
              <div class=\"shared-card{selected_class}\">
                <div class=\"shared-info\">
                  <div class=\"shared-title\">
                    <span class=\"dot-left prospecto\"></span>
                    <span>{nombre_full}</span>
                  </div>
                  <div class=\"shared-sub\">{puesto_disp} · {email_disp}</div>
                  <div class=\"shared-sub2\">{tel_disp} · {('Cliente: ' + entidad_nombre) if filtro_tipo=='cliente' else ('Marca: ' + entidad_nombre)}</div>
                </div>
                <span class=\"status-pill\">Contacto</span>
              </div>
              <button type=\"submit\" class=\"card-submit\"></button>
            </form>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    ct_controls = st.columns([2, 1, 1])
    with ct_controls[0]:
        st.caption(ct_count_text)
    with ct_controls[1]:
        ct_prev_clicked = st.button("Anterior", disabled=(ct_page <= 1), key="contacts_prev_page")
    with ct_controls[2]:
        ct_next_clicked = st.button("Siguiente", disabled=(ct_page >= ct_total_pages), key="contacts_next_page")
    if ct_prev_clicked and ct_page > 1:
        st.session_state["contacts_page"] = ct_page - 1
        st.rerun()
    if ct_next_clicked and ct_page < ct_total_pages:
        st.session_state["contacts_page"] = ct_page + 1
        st.rerun()

    if not selected_cid:
        return

    match_df = df_list[df_list["id_contacto"] == selected_cid] if "id_contacto" in df_list.columns else df_list.iloc[0:0]
    if match_df.empty:
        return
    m = match_df.iloc[0]
    nombre_full = f"{m['nombre']} {str(m.get('apellido') or '').strip()}".strip()
    puesto_disp = str(m.get('puesto') or '').strip() or "-"
    email_disp = str(m.get('email') or '').strip() or "-"
    tel_disp = str(m.get('telefono') or '').strip() or "-"
    direccion_disp = str(m.get('direccion') or '').strip() or "-"

    st.markdown(
        """
        <style>
          .detail-panel { width:100%; max-width: 1080px; margin: 12px auto 0; background:#0b1220; border:1px solid #374151; border-radius:14px; padding:26px 30px; color:#e5e7eb; box-shadow:0 4px 14px rgba(0,0,0,0.30); }
          .detail-title { font-size:28px; font-weight:800; margin-bottom:14px; color:#e5e7eb; display:flex; align-items:center; justify-content:space-between; }
          .detail-grid2 { display:grid; grid-template-columns: 1fr 1fr; gap:16px 24px; align-items:start; }
          .detail-item { background:#0f172a; border:1px solid #1f2937; border-radius:12px; padding:14px 16px; }
          .detail-item.wide { grid-column: 1 / -1; }
          .detail-label { display:block; color:#9ca3af; font-weight:800; font-size:18px; margin-bottom:8px; letter-spacing:0.2px; }
          .detail-value { display:block; color:#e5e7eb; font-size:20px; }
          .detail-actions { display:flex; gap:8px; }
          .ext-link-btn { display:inline-block; padding:6px 10px; border:1px solid #374151; border-radius:8px; color:#e5e7eb !important; text-decoration:none !important; background:#111827; cursor:pointer; }
          .ext-link-btn:hover { border-color:#2563eb; background:#0b1220; }
          .ext-link-btn.danger { border-color:#ef4444; color:#ef4444 !important; }
          .ext-link-btn.danger:hover { background:#1f2937; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    # Preservar sesión en acciones
    edit_href = f"?ptab=🧑‍💼 Contactos&contactid={selected_cid}&edit=1" + \
                (f"&uid={_hidden_uid}" if _hidden_uid else "") + \
                (f"&uexp={_hidden_uexp}" if _hidden_uexp else "") + \
                (f"&usig={_hidden_usig}" if _hidden_usig else "")
    del_href = f"?ptab=🧑‍💼 Contactos&del_contact={selected_cid}" + \
               (f"&uid={_hidden_uid}" if _hidden_uid else "") + \
               (f"&uexp={_hidden_uexp}" if _hidden_uexp else "") + \
               (f"&usig={_hidden_usig}" if _hidden_usig else "")

    st.markdown(
        f"""
        <div class='detail-panel'>
          <div class='detail-title'>
            <span>{nombre_full}</span>
            <span class='detail-actions'>
              <form method="get" style="display:inline" class="inline-form">
                <input type="hidden" name="ptab" value="🧑‍💼 Contactos" />
                <input type="hidden" name="contactid" value="{selected_cid}" />
                <input type="hidden" name="edit" value="1" />
                {f'<input type="hidden" name="uid" value="{_hidden_uid}" />' if _hidden_uid else ''}
                {f'<input type="hidden" name="uexp" value="{_hidden_uexp}" />' if _hidden_uexp else ''}
                {f'<input type="hidden" name="usig" value="{_hidden_usig}" />' if _hidden_usig else ''}
                <button type="submit" class="ext-link-btn">Editar</button>
              </form>
              <form method="get" style="display:inline" class="inline-form">
                <input type="hidden" name="ptab" value="🧑‍💼 Contactos" />
                <input type="hidden" name="contactid" value="{selected_cid}" />
                <input type="hidden" name="del_prompt" value="{selected_cid}" />
                {f'<input type="hidden" name="uid" value="{_hidden_uid}" />' if _hidden_uid else ''}
                {f'<input type="hidden" name="uexp" value="{_hidden_uexp}" />' if _hidden_uexp else ''}
                {f'<input type="hidden" name="usig" value="{_hidden_usig}" />' if _hidden_usig else ''}
                <button type="submit" class="ext-link-btn danger">Eliminar</button>
              </form>
            </span>
          </div>
          <div class='detail-grid2'>
            <div class='detail-item'>
              <div class='detail-label'>Puesto</div>
              <div class='detail-value'>{puesto_disp}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Teléfono</div>
              <div class='detail-value'>{tel_disp}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Mail</div>
              <div class='detail-value'>{email_disp}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Dirección</div>
              <div class='detail-value'>{direccion_disp}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Etiqueta</div>
              <div class='detail-value'>{'Cliente' if filtro_tipo=='cliente' else 'Marca'}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>{'Cliente' if filtro_tipo=='cliente' else 'Marca'}</div>
              <div class='detail-value'>{entidad_nombre or '-'}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Acciones via query params
    _edit_flag = params.get("edit")
    if _edit_flag:
        st.session_state["edit_contact_open"] = True
    _del_prompt = params.get("del_prompt")
    try:
        _del_prompt_id = int((_del_prompt[0] if isinstance(_del_prompt, list) else _del_prompt)) if _del_prompt else None
    except Exception:
        _del_prompt_id = None
    if _del_prompt_id:
        _open_delete_contact_dialog(_del_prompt_id, _hidden_uid, _hidden_uexp, _hidden_usig)

    if st.session_state.get("edit_contact_open"):
        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
        with st.form(f"edit_contact_form_{selected_cid}"):
            from .database import get_contacto, update_contacto
            data_c = get_contacto(selected_cid) or {}
            en_tipo = (data_c.get("etiqueta_tipo") or ("cliente" if filtro_tipo == "cliente" else "marca")).strip().lower()
            en_id = data_c.get("etiqueta_id") if data_c else (entidad_id or None)
            cols_edit = st.columns(2)
            with cols_edit[0]:
                nombre_e = st.text_input("Nombre", value=data_c.get("nombre") or "")
                apellido_e = st.text_input("Apellido", value=data_c.get("apellido") or "")
                puesto_e = st.text_input("Puesto", value=data_c.get("puesto") or "")
            with cols_edit[1]:
                telefono_e = st.text_input("Teléfono", value=data_c.get("telefono") or "")
                email_e = st.text_input("Mail", value=data_c.get("email") or "")
                direccion_e = st.text_input("Dirección", value=data_c.get("direccion") or "")
            row_e = st.columns(2)
            with row_e[0]:
                etiqueta_tipo_e = st.selectbox("Etiqueta", options=["cliente", "marca"], index=(0 if en_tipo == "cliente" else 1))
            etiqueta_id_e = None
            entidad_nombre_e = None
            with row_e[1]:
                if etiqueta_tipo_e == "cliente":
                    cdf_e = get_clientes_dataframe()
                    c_opts_e = [(int(row["id_cliente"]), row["nombre"]) for _, row in cdf_e.iterrows()]
                    default_cid = en_id if en_tipo == "cliente" else entidad_id
                    cid_e = st.selectbox("Cliente", options=[cid for cid, _ in c_opts_e], index=(next((i for i,(cid,_) in enumerate(c_opts_e) if cid == default_cid), 0) if c_opts_e else 0), format_func=lambda cid: next(name for cid2, name in c_opts_e if cid2 == cid))
                    etiqueta_id_e = cid_e
                    try:
                        entidad_nombre_e = next(name for cid2, name in c_opts_e if cid2 == cid_e)
                    except Exception:
                        entidad_nombre_e = None
                else:
                    mdf_e = get_marcas_dataframe()
                    m_opts_e = [(int(row["id_marca"]), row["nombre"]) for _, row in mdf_e.iterrows()]
                    default_mid = en_id if en_tipo == "marca" else None
                    mid_e = st.selectbox("Marca", options=[mid for mid, _ in m_opts_e], index=(next((i for i,(mid,_) in enumerate(m_opts_e) if mid == default_mid), 0) if m_opts_e else 0), format_func=lambda mid: next(name for mid2, name in m_opts_e if mid2 == mid))
                    etiqueta_id_e = mid_e
                    try:
                        entidad_nombre_e = next(name for mid2, name in m_opts_e if mid2 == mid_e)
                    except Exception:
                        entidad_nombre_e = None
            submitted_e = st.form_submit_button("Guardar cambios", type="primary")
            if submitted_e:
                ok = False
                if not str(nombre_e or "").strip():
                    st.error("El nombre es obligatorio")
                elif etiqueta_id_e is None:
                    st.error("Seleccione etiqueta y entidad")
                else:
                    try:
                        ok = bool(update_contacto(selected_cid, nombre_e, apellido_e, puesto_e, telefono_e, email_e, direccion_e, etiqueta_tipo_e, etiqueta_id_e))
                    except Exception:
                        ok = False
                if ok:
                    st.success("Contacto actualizado")
                    st.session_state["edit_contact_open"] = False
                    st.rerun()
                else:
                    st.error("No se pudo actualizar el contacto")

    

def render_shared_with_me(user_id):
    st.subheader("Proyectos Compartidos Conmigo")

    # Selección por query params; soporta repliegue si el valor está vacío
    params = st.query_params
    if "sharedproj" in params:
        raw = params["sharedproj"]
        pid_str = raw[0] if isinstance(raw, list) else raw
        if pid_str:
            try:
                st.session_state["selected_shared_project_id"] = int(pid_str)
            except Exception:
                st.session_state.pop("selected_shared_project_id", None)
        else:
            st.session_state.pop("selected_shared_project_id", None)
    else:
        st.session_state.pop("selected_shared_project_id", None)

    df = get_proyectos_shared_with_user(user_id)
    if df.empty:
        return

    # Autor (propietario) del proyecto
    users_df = get_users_dataframe()
    users_df["nombre_completo"] = users_df.apply(lambda r: f"{(r['nombre'] or '').strip()} {(r['apellido'] or '').strip()}".strip(), axis=1)
    id_to_name = {int(r["id"]): r["nombre_completo"] for _, r in users_df.iterrows()}
    name_to_id = {v: k for k, v in id_to_name.items()}

    # Filtros: Cliente, Nombre del proyecto, Estado, Compartido por
    estados_disponibles_shared = PROYECTO_ESTADOS

    autores_disponibles = sorted({
        id_to_name.get(int(uid), "Desconocido")
        for uid in df.get("owner_user_id", []).tolist()
        if uid is not None
    })

    sf1, sf2, sf3, sf4 = st.columns([2, 2, 2, 2])
    with sf1:
        filtro_cliente_s = st.text_input("Cliente", key="shared_filter_cliente")
    with sf2:
        filtro_nombre_s = st.text_input("Nombre del proyecto", key="shared_filter_nombre")
    with sf3:
        filtro_estados_s = st.multiselect(
            "Estado",
            options=estados_disponibles_shared,
            key="shared_filter_estado"
        )
    with sf4:
        filtro_autores_s = st.multiselect(
            "Compartido por",
            options=autores_disponibles,
            key="shared_filter_autor"
        )

    df_shared_filtrado = df.copy()
    if filtro_cliente_s:
        df_shared_filtrado = df_shared_filtrado[df_shared_filtrado.get("cliente_nombre", pd.Series(dtype=str)).fillna("").str.contains(filtro_cliente_s, case=False, na=False)]
    if filtro_nombre_s:
        df_shared_filtrado = df_shared_filtrado[df_shared_filtrado.get("titulo", pd.Series(dtype=str)).fillna("").str.contains(filtro_nombre_s, case=False, na=False)]
    if filtro_estados_s:
        df_shared_filtrado = df_shared_filtrado[
            df_shared_filtrado.get("estado", pd.Series(dtype=str)).fillna("").apply(_estado_to_class).isin([e.lower() for e in filtro_estados_s])
        ]
    if filtro_autores_s:
        autores_ids = [name_to_id.get(n) for n in filtro_autores_s if name_to_id.get(n) is not None]
        df_shared_filtrado = df_shared_filtrado[df_shared_filtrado.get("owner_user_id", pd.Series(dtype=int)).isin(autores_ids)]

    df = df_shared_filtrado

    # Estilos de tarjeta compartida con punto por estado
    st.markdown("""
    <style>
      .shared-card {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        background: #1f2937;
        border: 1px solid #374151;
        color: #e5e7eb;
        padding: 20px 24px;
        border-radius: 14px;
        box-sizing: border-box;
        text-decoration: none;
        box-shadow: 0 4px 10px rgba(0,0,0,0.25);
      }
      .shared-card + .shared-card { margin-top: 14px; }
      .shared-card:hover {
        background: #111827;
        border-color: #2563eb;
        transform: translateY(-1px);
        transition: all .15s ease-in-out;
      }
      .shared-info { display: flex; flex-direction: column; }
      .shared-title {
        display: flex; align-items: center; gap: 10px;
        font-size: 20px; font-weight: 600;
      }
      .dot-left { width: 10px; height: 10px; border-radius: 50%; }
      .dot-left.prospecto { background: #60a5fa; }
      .dot-left.presupuestado { background: #34d399; }
      .dot-left.negociación { background: #8b5cf6; }
      .dot-left.objeción { background: #fbbf24; }
      .dot-left.ganado { background: #065f46; }
      .dot-left.perdido { background: #ef4444; }
      .shared-sub { margin-top: 4px; color: #9ca3af; font-size: 16px; }
      .shared-sub2 { margin-top: 2px; color: #9ca3af; font-size: 15px; }
      .shared-author { margin-top: 2px; color: #9ca3af; font-size: 14px; }
      .status-pill {
        padding: 10px 16px; border-radius: 999px;
        font-size: 18px; font-weight: 700;
        border: 2px solid transparent;
      }
      .status-pill.prospecto { color: #60a5fa; border-color: #60a5fa; }
      .status-pill.presupuestado { color: #34d399; border-color: #34d399; }
      .status-pill.negociación { color: #8b5cf6; border-color: #8b5cf6; }
      .status-pill.objeción { color: #fbbf24; border-color: #fbbf24; }
      .status-pill.ganado { color: #065f46; border-color: #065f46; }
      .status-pill.perdido { color: #ef4444; border-color: #ef4444; }
      /* Formulario clickeable: botón invisible cubre toda la tarjeta */
      .card-form { position: relative; display: block; }
      .card-form .card-submit {
        position: absolute; inset: 0; width: 100%; height: 100%;
        background: transparent; border: 0; padding: 0; margin: 0;
        cursor: pointer; opacity: 0; box-shadow: none; outline: none;
      }
      .card-form { margin-bottom: 18px; }
      .card-details-gap { height: 16px; }
      /* Estado visual de tarjeta seleccionada */
      .shared-card.selected { background:#0a1324; border-color:#2563eb; box-shadow:0 0 0 2px rgba(37,99,235,0.30) inset; }
    </style>
    """, unsafe_allow_html=True)

    selected_pid = st.session_state.get("selected_shared_project_id")

    # Si se solicita vista previa en nueva pestaña, mostrar solo el visor y salir
    params = st.query_params
    try:
        raw_prev = params.get("previewdoc")
        prev_id_str = raw_prev[0] if isinstance(raw_prev, list) else raw_prev
        preview_doc_id = int(prev_id_str) if prev_id_str else None
    except Exception:
        preview_doc_id = None
    if selected_pid and preview_doc_id:
        docs_df_preview = get_proyecto_documentos(selected_pid)
        match = docs_df_preview.loc[docs_df_preview["id"] == preview_doc_id]
        if not match.empty:
            file_path = match.iloc[0]["file_path"]
            st.subheader("Vista previa")
            href = _make_static_preview_link(file_path, preview_doc_id)
            if href:
                _render_pdf_preview_url(href, height=800)
                with st.expander("Si no se ve, usar visor alterno"):
                    _render_pdf_preview(file_path, height=800)
            else:
                _render_pdf_preview(file_path, height=800)
            # Link para volver sin el parámetro de vista previa
            def qp(k):
                v = params.get(k)
                return (v[0] if isinstance(v, list) else v) if v else ""
            uid = qp("uid"); uexp = qp("uexp"); usig = qp("usig")
            back_href = f"?ptab=🤝 Compartidos Conmigo&sharedproj={selected_pid}" + \
                        (f"&uid={uid}" if uid else "") + \
                        (f"&uexp={uexp}" if uexp else "") + \
                        (f"&usig={usig}" if usig else "")
            st.markdown(f"<a href=\"{back_href}\" class=\"ext-link-btn\">Volver</a>", unsafe_allow_html=True)
            return

    sp_page_size = 10
    sp_total_items = len(df)
    sp_page = int(st.session_state.get("shared_projects_page", 1) or 1)
    sp_total_pages = max((sp_total_items + sp_page_size - 1) // sp_page_size, 1)
    if sp_page > sp_total_pages:
        sp_page = sp_total_pages
    if sp_page < 1:
        sp_page = 1
    st.session_state["shared_projects_page"] = sp_page
    sp_start = (sp_page - 1) * sp_page_size
    sp_end = sp_start + sp_page_size
    df_shared_page = df.iloc[sp_start:sp_end]
    sp_count_text = f"Mostrando elementos {sp_start+1}-{min(sp_end, sp_total_items)} de {sp_total_items}"

    for _, r in df_shared_page.iterrows():
        pid = int(r["id"])
        estado = _estado_to_class(r.get("estado"))
        estado_disp = _estado_display(r.get("estado"))
        title = r["titulo"]
        cliente = r.get("cliente_nombre") or "Sin cliente"
        author = id_to_name.get(int(r["owner_user_id"]), "Desconocido")
        try:
            _fc_dt = pd.to_datetime(r.get("fecha_cierre"), errors="coerce")
            fc_fmt = _fc_dt.strftime("%d/%m/%Y") if not pd.isna(_fc_dt) else "-"
        except Exception:
            fc_fmt = "-"
        tipo_venta_card = r.get("tipo_venta") or "-"
        params = st.query_params
        def get_param(k):
            v = params.get(k)
            return (v[0] if isinstance(v, list) else v) if v else ""
        hidden_uid = get_param("uid")
        hidden_uexp = get_param("uexp")
        hidden_usig = get_param("usig")
        hidden_val = "" if selected_pid == pid else str(pid)
        selected_class = " selected" if selected_pid == pid else ""

        st.markdown(
            f"""
            <form method=\"get\" class=\"card-form\">
              <input type=\"hidden\" name=\"sharedproj\" value=\"{hidden_val}\" />
              <input type=\"hidden\" name=\"ptab\" value=\"🤝 Compartidos Conmigo\" />
              {f'<input type=\"hidden\" name=\"uid\" value=\"{hidden_uid}\" />' if hidden_uid else ''}
              {f'<input type=\"hidden\" name=\"uexp\" value=\"{hidden_uexp}\" />' if hidden_uexp else ''}
              {f'<input type=\"hidden\" name=\"usig\" value=\"{hidden_usig}\" />' if hidden_usig else ''}
              <div class=\"shared-card{selected_class}\">
                <div class=\"shared-info\">
                  <div class=\"shared-title\">
                    <span class=\"dot-left {estado}\"></span>
                    <span>{title}</span>
                  </div>
                  <div class=\"shared-sub\">ID {pid} · {cliente}</div>
                  <div class=\"shared-sub2\">Cierre: {fc_fmt} · {tipo_venta_card}</div>
                  <div class=\"shared-author\">Compartido por: {author}</div>
                </div>
                <span class=\"status-pill {estado}\">{estado_disp}</span>
              </div>
              <button type=\"submit\" class=\"card-submit\"></button>
            </form>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
    sp_controls = st.columns([2, 1, 1])
    with sp_controls[0]:
        st.caption(sp_count_text)
    with sp_controls[1]:
        sp_prev_clicked = st.button("Anterior", disabled=(sp_page <= 1), key="shared_prev_page")
    with sp_controls[2]:
        sp_next_clicked = st.button("Siguiente", disabled=(sp_page >= sp_total_pages), key="shared_next_page")
    if sp_prev_clicked and sp_page > 1:
        st.session_state["shared_projects_page"] = sp_page - 1
        st.rerun()
    if sp_next_clicked and sp_page < sp_total_pages:
        st.session_state["shared_projects_page"] = sp_page + 1
        st.rerun()

    # Sin mensaje: retorno silencioso si no hay selección
    if not selected_pid:
        return

    data = get_proyecto(selected_pid)
    if not data:
        st.error("No se pudo cargar el proyecto.")
        return

    # Separación visual entre la tarjeta y el detalle
    st.markdown("<div class='card-details-gap'></div>", unsafe_allow_html=True)

    author = id_to_name.get(int(data["owner_user_id"]), "Desconocido")

    # Estilos para detalle con título grande y grilla de dos columnas
    st.markdown(
        """
        <style>
          .detail-panel { width:100%; max-width: 1080px; margin: 0 auto; background:#0b1220; border:1px solid #374151; border-radius:14px; padding:26px 30px; color:#e5e7eb; box-shadow:0 4px 14px rgba(0,0,0,0.30); }
          .detail-title { font-size:28px; font-weight:800; margin-bottom:14px; color:#e5e7eb; }
          .detail-grid2 { display:grid; grid-template-columns: 1fr 1fr; gap:16px 24px; align-items:start; }
          .detail-item { background:#0f172a; border:1px solid #1f2937; border-radius:12px; padding:14px 16px; }
          .detail-item.wide { grid-column: 1 / -1; }
          .detail-label { display:block; color:#9ca3af; font-weight:800; font-size:18px; margin-bottom:8px; letter-spacing:0.2px; }
          .detail-value { display:block; color:#e5e7eb; font-size:20px; }
          .detail-divider { margin:20px 0; border-top:1px dashed #374151; }
          .doc-header { font-size:22px; font-weight:800; color:#e5e7eb; margin-bottom:10px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Formatear solo hora y minutos de la fecha de creación
    try:
        created_dt = pd.to_datetime(data.get("created_at"), errors="coerce")
        created_fmt = created_dt.strftime("%d/%m/%Y %H:%M") if not pd.isna(created_dt) else str(data.get("created_at") or "")
    except Exception:
        created_fmt = str(data.get("created_at") or "")
    try:
        fc_dt = pd.to_datetime(data.get("fecha_cierre"), errors="coerce")
        fc_fmt = fc_dt.strftime("%d/%m/%Y") if not pd.isna(fc_dt) else "-"
    except Exception:
        fc_fmt = "-"
    tipo_v_disp = data.get("tipo_venta") or "-"
    importe_disp = None
    try:
        _v = data.get("valor")
        _m = data.get("moneda") or ""
        importe_disp = (f"{int(_v):,}".replace(",", ".") + (f" { _m }" if _m else "")) if _v is not None else None
    except Exception:
        importe_disp = None
    prob_disp = data.get("probabilidad")
    etiqueta_disp = data.get("etiqueta") or "-"
    marca_disp = data.get("marca_nombre") or "-"
    contacto_disp = None
    try:
        cn = (data.get("contacto_nombre") or "").strip()
        ca = (data.get("contacto_apellido") or "").strip()
        cp = (data.get("contacto_puesto") or "").strip()
        base = f"{cn} {ca}".strip()
        contacto_disp = f"{base} - {cp}".strip() if cp else (base or None)
    except Exception:
        contacto_disp = None

    st.markdown(
        f"""
        <div class='detail-panel'>
          <div class='detail-title'>{data['titulo']}</div>
          <div class='detail-grid2'>
            <div class='detail-item'>
              <div class='detail-label'>Descripción</div>
              <div class='detail-value'>{data.get('descripcion') or '-'}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Cliente</div>
              <div class='detail-value'>{data.get('cliente_nombre') or 'Sin cliente'}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Estado</div>
              <div class='detail-value'><span class='status-pill {_estado_to_class(data.get('estado'))}'>{_estado_display(data.get('estado'))}</span></div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Compartido por</div>
              <div class='detail-value'>{author}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Fecha prevista de cierre</div>
              <div class='detail-value'>{fc_fmt}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Tipo de Venta</div>
              <div class='detail-value'>{tipo_v_disp}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Importe</div>
              <div class='detail-value'>{importe_disp or '-'}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Probabilidad</div>
              <div class='detail-value'>{(str(prob_disp) + '%') if (prob_disp is not None) else '-'}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Etiqueta</div>
              <div class='detail-value'>{etiqueta_disp}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Marca</div>
              <div class='detail-value'>{marca_disp}</div>
            </div>
            <div class='detail-item'>
              <div class='detail-label'>Contacto</div>
              <div class='detail-value'>{contacto_disp or '-'}</div>
            </div>
            <div class='detail-item wide'>
              <div class='detail-label'>Fechas</div>
              <div class='detail-value'>Creado: {created_fmt}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Documentos disponibles para descarga y vista previa (sin permisos de borrado/edición)
    docs_df = get_proyecto_documentos(selected_pid)
    if not docs_df.empty:
        st.markdown("<div class='detail-divider'></div>", unsafe_allow_html=True)
        st.markdown("<div class='doc-header'>Documentos</div>", unsafe_allow_html=True)
        ids = [int(x) for x in docs_df['id'].tolist()]
        labels = {}
        for _, d in docs_df.iterrows():
            fid = int(d['id'])
            fn = d['filename']
            labels[fid] = fn

        selected_doc_id = st.selectbox(
            "Archivo",
            options=ids,
            format_func=lambda i: labels.get(int(i), str(i)),
            key=f"shared_doc_selector_{selected_pid}"
        )
        try:
            sel_row = docs_df.loc[docs_df['id'] == int(selected_doc_id)].iloc[0]
            fp = sel_row['file_path']
            fn = sel_row['filename']
            pass
            cols = st.columns([3, 1, 1, 3])
            with cols[1]:
                try:
                    with open(fp, "rb") as fh:
                        st.download_button("Descargar", fh.read(), file_name=fn, key=f"dl_shared_selector_{selected_pid}", use_container_width=True)
                except Exception:
                    st.button("Descargar", disabled=True, key=f"dl_shared_selector_{selected_pid}_dis", use_container_width=True)
            with cols[2]:
                rel = _make_static_preview_link(fp, int(selected_doc_id))
                href = _absolute_static_url(rel) if rel else None
                if href:
                    st.link_button("Vista previa", href)
                else:
                    st.button("Vista previa", disabled=True, key=f"prev_shared_selector_{selected_pid}_dis", use_container_width=True)
        except Exception:
            st.warning("No se pudo preparar la descarga del archivo seleccionado.")