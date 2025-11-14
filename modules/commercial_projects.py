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
    get_engine
)
from .config import PROYECTO_ESTADOS

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
    labels = ["🆕 Crear Proyecto", "📚 Mis Proyectos", "🤝 Compartidos Conmigo"]
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
    else:
        render_shared_with_me(user_id)

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
    

    # Formulario para evitar re-render hasta envío
    form = st.form("create_project_form", clear_on_submit=False)
    with form:
        clientes_df = get_clientes_dataframe()
        users_df = get_users_dataframe()
        users_df["nombre_completo"] = users_df.apply(lambda r: f"{r['nombre']} {r['apellido']}".strip(), axis=1)

        # Título
        titulo = st.text_input("Título")

        # Bloque: Datos del cliente
        st.markdown("**Datos del cliente**")
        client_options = clientes_df["nombre"].tolist()
        cliente_nombre = st.selectbox("Cliente", options=client_options, key="create_cliente")
        cliente_id = int(clientes_df.loc[clientes_df["nombre"] == cliente_nombre, "id_cliente"].iloc[0]) if client_options else None

        cl_cols = st.columns(2)
        with cl_cols[0]:
            persona_contacto = st.text_input("Persona de contacto")
            telefono = st.text_input("Teléfono")
        with cl_cols[1]:
            organizacion = st.text_input("Organización")
            correo = st.text_input("Correo electrónico")

    # Continuación del formulario: Datos del proyecto, Estado, Descripción, archivos, compartir y submit
    with form:
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

    # Envío del formulario: crear y redirigir a Mis Proyectos
    if submitted:
        if st.session_state.get("create_submit_clicked"):
            st.session_state["create_submit_clicked"] = False
            errors = []
            if not titulo.strip():
                errors.append("El título es obligatorio.")
            if not cliente_id:
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

            pid = create_proyecto(
                user_id,
                titulo,
                descripcion,
                cliente_id,
                estado,
                valor=_valor_int,
                moneda=_moneda,
                etiqueta=_etiqueta,
                probabilidad=_prob,
                fecha_cierre=_cierre,
                marca_id=_marca_id,
            )
            if pid is None:
                st.error("No se pudo crear el proyecto.")
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
                    add_proyecto_document(pid, user_id, unique_name, file_path, f.type, len(f.getvalue()))

            # Redirigir a Mis Proyectos y seleccionar el recién creado
            try:
                st.query_params["ptab"] = "📚 Mis Proyectos"
                st.query_params["myproj"] = str(pid)
                st.rerun()
            except Exception:
                st.success(f"Proyecto creado (ID {pid}).")
                st.session_state["created_project_id"] = pid
        else:
            pass

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
        font-size: 20px; font-weight: 600;
      }
      .dot-left { width: 10px; height: 10px; border-radius: 50%; }
      .dot-left.prospecto { background: #9ca3af; }
      .dot-left.presupuestado { background: #3b82f6; }
      .dot-left.negociación { background: #f59e0b; }
      .dot-left.objeción { background: #8b5cf6; }
      .dot-left.ganado { background: #10b981; }
      .dot-left.perdido { background: #ef4444; }
      .project-sub { margin-top: 4px; color: #9ca3af; font-size: 15px; }
      .status-pill {
        padding: 10px 16px; border-radius: 999px;
        font-size: 18px; font-weight: 700;
        border: 2px solid transparent;
      }
      .status-pill.prospecto { color: #9ca3af; border-color: #9ca3af; }
      .status-pill.presupuestado { color: #3b82f6; border-color: #3b82f6; }
      .status-pill.negociación { color: #f59e0b; border-color: #f59e0b; }
      .status-pill.objeción { color: #8b5cf6; border-color: #8b5cf6; }
      .status-pill.ganado { color: #10b981; border-color: #10b981; }
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
      .ext-link-btn { display:inline-block; padding:6px 10px; border:1px solid #374151; border-radius:8px; color:#e5e7eb; text-decoration:none; background:#111827; }
      .ext-link-btn:hover { border-color:#2563eb; background:#0b1220; }
    </style>
    """, unsafe_allow_html=True)

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

    # Tarjetas clickeables con formulario GET (preserva sesión firmada)
    for _, r in df.iterrows():
        pid = int(r["id"])
        estado = _estado_to_class(r.get("estado"))
        estado_disp = _estado_display(r.get("estado"))
        title = r["titulo"]
        cliente = r.get("cliente_nombre") or "Sin cliente"
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
                </div>
                <span class=\"status-pill {estado}\">{estado_disp}</span>
              </div>
              <button type=\"submit\" class=\"card-submit\"></button>
            </form>
            """,
            unsafe_allow_html=True
        )

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

    # FORM: evita rerender al cambiar widgets; sólo refresca al enviar
    with st.form(key=f"edit_form_{selected_pid}"):
        # Título primero
        titulo = st.text_input("Título", value=data["titulo"], key=f"edit_titulo_{selected_pid}")

        # Bloque: Datos del cliente
        st.markdown("**Datos del cliente**")
        clientes_df = get_clientes_dataframe()
        client_options = ["(Sin cliente)"] + clientes_df["nombre"].tolist()
        current_client_name = data.get("cliente_nombre") or "(Sin cliente)"
        cliente_nombre = st.selectbox(
            "Cliente",
            options=client_options,
            index=client_options.index(current_client_name) if current_client_name in client_options else 0,
            key=f"edit_cliente_{selected_pid}"
        )
        cliente_id = None if cliente_nombre == "(Sin cliente)" else int(
            clientes_df.loc[clientes_df["nombre"] == cliente_nombre, "id_cliente"].iloc[0]
        )
        cl_cols = st.columns(2)
        with cl_cols[0]:
            persona_contacto = st.text_input("Persona de contacto", key=f"edit_persona_{selected_pid}")
            telefono = st.text_input("Teléfono", key=f"edit_tel_{selected_pid}")
        with cl_cols[1]:
            organizacion = st.text_input("Organización", key=f"edit_org_{selected_pid}")
            correo = st.text_input("Correo electrónico", key=f"edit_mail_{selected_pid}")

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

        submitted = st.form_submit_button("Guardar cambios", type="primary")

    if submitted:
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
            if not cliente_id:
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
            ):
                # Refrescar tarjetas/listado y mantener selección y pestaña actual
                try:
                    st.query_params["ptab"] = "📚 Mis Proyectos"
                    st.query_params["myproj"] = str(selected_pid)
                    st.rerun()
                except Exception:
                    st.success("Proyecto actualizado.")
            else:
                st.error("No se pudo actualizar el proyecto.")

    st.divider()
    # Documentos (mover antes de compartidos para coincidir con "Crear")
    st.subheader("Documentos")
    files = st.file_uploader(
        "Adjuntar nuevos documentos (PDF)",
        accept_multiple_files=True,
        type=["pdf"],
        key=f"uploader_{selected_pid}"
    )
    if files:
        save_dir = os.path.join(os.getcwd(), "uploads", "projects", str(selected_pid))
        os.makedirs(save_dir, exist_ok=True)
        for f in files:
            unique_name = _unique_filename(save_dir, f.name)
            file_path = os.path.join(save_dir, unique_name)
            with open(file_path, "wb") as out:
                out.write(f.getvalue())
            add_proyecto_document(selected_pid, user_id, unique_name, file_path, f.type, len(f.getvalue()))
        st.success("Documentos subidos.")

    docs_df = get_proyecto_documentos(selected_pid)
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
        try:
            sel_row = docs_df.loc[docs_df['id'] == int(selected_doc_id)].iloc[0]
            fp = sel_row['file_path']
            fn = sel_row['filename']
            pass
            cols = st.columns([3, 1, 1, 1, 3])
            with cols[1]:
                try:
                    with open(fp, "rb") as fh:
                        st.download_button("Descargar", fh.read(), file_name=fn, key=f"dl_selector_{selected_pid}", use_container_width=True)
                except Exception:
                    st.button("Descargar", disabled=True, key=f"dl_selector_{selected_pid}_dis", use_container_width=True)
            with cols[2]:
                rel = _make_static_preview_link(fp, int(selected_doc_id))
                href = _absolute_static_url(rel) if rel else None
                if href:
                    st.link_button("Vista previa", href)
                else:
                    st.button("Vista previa", disabled=True, key=f"prev_selector_{selected_pid}_dis", use_container_width=True)
            with cols[3]:
                if st.button("Eliminar", key=f"del_selector_{selected_pid}", use_container_width=True):
                    if remove_proyecto_document(int(selected_doc_id), user_id):
                        st.success("Documento eliminado.")
                        st.rerun()
                    else:
                        st.error("No se pudo eliminar el documento.")
        except Exception:
            st.warning("No se pudo cargar el archivo seleccionado.")

    # NUEVO: compartir solo con usuarios del mismo departamento y excluyendo al actual
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
        key=f"share_users_{selected_pid}"  # clave única
    )
    if st.button("Actualizar compartidos", key=f"update_shares_{selected_pid}"):
        set_proyecto_shares(selected_pid, user_id, [name_to_id[n] for n in share_users])
        st.success("Compartidos actualizados.")

    

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
      .dot-left.prospecto { background: #9ca3af; }
      .dot-left.presupuestado { background: #3b82f6; }
      .dot-left.negociación { background: #f59e0b; }
      .dot-left.objeción { background: #8b5cf6; }
      .dot-left.ganado { background: #10b981; }
      .dot-left.perdido { background: #ef4444; }
      .shared-sub { margin-top: 4px; color: #9ca3af; font-size: 15px; }
      .shared-author { margin-top: 2px; color: #9ca3af; font-size: 14px; }
      .status-pill {
        padding: 10px 16px; border-radius: 999px;
        font-size: 18px; font-weight: 700;
        border: 2px solid transparent;
      }
      .status-pill.prospecto { color: #9ca3af; border-color: #9ca3af; }
      .status-pill.presupuestado { color: #3b82f6; border-color: #3b82f6; }
      .status-pill.negociación { color: #f59e0b; border-color: #f59e0b; }
      .status-pill.objeción { color: #8b5cf6; border-color: #8b5cf6; }
      .status-pill.ganado { color: #10b981; border-color: #10b981; }
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

    # Tarjetas clickeables con autor usando formulario GET (preserva sesión firmada)
    for _, r in df.iterrows():
        pid = int(r["id"])
        estado = _estado_to_class(r.get("estado"))
        estado_disp = _estado_display(r.get("estado"))
        title = r["titulo"]
        cliente = r.get("cliente_nombre") or "Sin cliente"
        author = id_to_name.get(int(r["owner_user_id"]), "Desconocido")
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
                  <div class=\"shared-author\">Compartido por: {author}</div>
                </div>
                <span class=\"status-pill {estado}\">{estado_disp}</span>
              </div>
              <button type=\"submit\" class=\"card-submit\"></button>
            </form>
            """,
            unsafe_allow_html=True
        )

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