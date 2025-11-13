import os
import shutil
import base64
import streamlit as st
import pandas as pd
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
    get_user_rol_id           # NUEVO
)

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
        dest_dir = os.path.join(os.getcwd(), "static", "previews")
        os.makedirs(dest_dir, exist_ok=True)
        dest_name = f"{int(doc_id)}_{base}"
        dest_path = os.path.join(dest_dir, dest_name)
        # Copiar si no existe o si el origen es más nuevo
        if not os.path.exists(dest_path) or os.path.getmtime(src_path) > os.path.getmtime(dest_path):
            shutil.copyfile(src_path, dest_path)
        return f"/static/previews/{dest_name}"
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
    form = st.form("create_project_form", clear_on_submit=True)
    with form:
        clientes_df = get_clientes_dataframe()
        users_df = get_users_dataframe()
        users_df["nombre_completo"] = users_df.apply(lambda r: f"{r['nombre']} {r['apellido']}".strip(), axis=1)

        # Título
        titulo = st.text_input("Título")

        # Bloque: Datos del cliente
        st.markdown("**Datos del cliente**")
        client_options = ["(Sin cliente)"] + clientes_df["nombre"].tolist()
        cliente_nombre = st.selectbox("Cliente", options=client_options, key="create_cliente")
        cliente_id = None if cliente_nombre == "(Sin cliente)" else int(clientes_df.loc[clientes_df["nombre"] == cliente_nombre, "id_cliente"].iloc[0])

        cl_cols = st.columns(2)
        with cl_cols[0]:
            persona_contacto = st.text_input("Persona de contacto")
            telefono = st.text_input("Teléfono")
        with cl_cols[1]:
            organizacion = st.text_input("Organización")
            correo = st.text_input("Correo electrónico")

        st.divider()
        # Bloque: Datos del proyecto
        st.markdown("**Datos del proyecto**")
        vd_cols = st.columns(2)
        with vd_cols[0]:
            # Valor como texto con separador de miles (.) + Moneda
            val_cols = st.columns([1, 1])
            with val_cols[0]:
                # En formulario no se permiten callbacks; aceptar entrada tal cual
                valor_raw = st.text_input("Valor", key="create_valor")
            with val_cols[1]:
                moneda = st.selectbox("Moneda", ["ARS", "USD"], index=0)
            etiqueta = st.text_input("Etiqueta")
            probabilidad = st.slider("Probabilidad", min_value=0, max_value=100, value=0, format="%d%%")
        with vd_cols[1]:
            embudo = st.text_input("Embudo")
            fecha_cierre = st.date_input("Fecha prevista de cierre")

        # Estado (incluye 'pendiente')
        estado = st.selectbox(
            "Estado",
            options=["activo", "pendiente", "finalizado", "cerrado"],
            key="create_estado"
        )

        descripcion = st.text_area("Descripción")

        # Uploader de documentos iniciales antes de crear
        initial_files = st.file_uploader(
            "Adjuntar documentos iniciales (PDF)",
            accept_multiple_files=True,
            type=["pdf"],
            key="create_initial_docs"
        )

        # Bloque: Datos del vendedor / compartir
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
            "Visible para",
            options=share_options,
            default=[],
            key="create_share_users"
        )
        share_ids = [name_to_id[n] for n in share_users]

        submitted = st.form_submit_button("Crear proyecto", type="primary")

    # Envío del formulario: crear y redirigir a Mis Proyectos
    if submitted:
        if not titulo.strip():
            st.error("El título es obligatorio.")
            return

        pid = create_proyecto(user_id, titulo, descripcion, cliente_id, estado)
        if pid is None:
            st.error("No se pudo crear el proyecto.")
            return

        set_proyecto_shares(pid, user_id, share_ids)

        docs_to_save = initial_files or []
        if docs_to_save:
            save_dir = os.path.join(os.getcwd(), "uploads", "projects", str(pid))
            os.makedirs(save_dir, exist_ok=True)
            for f in docs_to_save:
                file_path = os.path.join(save_dir, f.name)
                with open(file_path, "wb") as out:
                    out.write(f.getvalue())
                add_proyecto_document(pid, user_id, f.name, file_path, f.type, len(f.getvalue()))

        # Redirigir a Mis Proyectos y seleccionar el recién creado
        try:
            st.query_params["ptab"] = "📚 Mis Proyectos"
            st.query_params["myproj"] = str(pid)
            st.rerun()
        except Exception:
            st.success(f"Proyecto creado (ID {pid}).")
            st.session_state["created_project_id"] = pid

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
      .dot-left.activo { background: #10b981; }      /* verde */
      .dot-left.pendiente { background: #f59e0b; }   /* amarillo */
      .dot-left.finalizado { background: #f59e0b; }  /* ámbar */
      .dot-left.cerrado { background: #ef4444; }     /* rojo */
      .project-sub { margin-top: 4px; color: #9ca3af; font-size: 15px; }
      .status-pill {
        padding: 10px 16px; border-radius: 999px;
        font-size: 18px; font-weight: 700;
        border: 2px solid transparent;
      }
      .status-pill.activo { color: #10b981; border-color: #10b981; }
      .status-pill.pendiente { color: #f59e0b; border-color: #f59e0b; }
      .status-pill.finalizado { color: #f59e0b; border-color: #f59e0b; }
      .status-pill.cerrado { color: #ef4444; border-color: #ef4444; }
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
    try:
        estados_disponibles = sorted({
            (str(e or "").strip().lower())
            for e in df.get("estado", []).tolist()
            if str(e or "").strip().lower() != "eliminar"
        })
    except Exception:
        estados_disponibles = []

    fcol1, fcol2, fcol3 = st.columns([2, 2, 2])
    with fcol1:
        filtro_cliente = st.text_input("Cliente", key="my_filter_cliente")
    with fcol2:
        filtro_nombre = st.text_input("Nombre del proyecto", key="my_filter_nombre")
    with fcol3:
        filtro_estados = st.multiselect(
            "Estado",
            options=estados_disponibles,
            key="my_filter_estado"
        )

    def _norm(s):
        return str(s or "").strip()

    df_filtrado = df.copy()
    if filtro_cliente:
        df_filtrado = df_filtrado[df_filtrado.get("cliente_nombre", pd.Series(dtype=str)).fillna("").str.contains(filtro_cliente, case=False, na=False)]
    if filtro_nombre:
        df_filtrado = df_filtrado[df_filtrado.get("titulo", pd.Series(dtype=str)).fillna("").str.contains(filtro_nombre, case=False, na=False)]
    if filtro_estados:
        df_filtrado = df_filtrado[df_filtrado.get("estado", pd.Series(dtype=str)).fillna("").str.lower().isin([e.lower() for e in filtro_estados])]

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
        estado = (r["estado"] or "").strip().lower()
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
                <span class=\"status-pill {estado}\">{estado or "-"}</span>
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
                # En formulario no se permiten callbacks; aceptar entrada tal cual
                valor_raw = st.text_input(
                    "Valor",
                    key=f"edit_valor_{selected_pid}"
                )
            with val_cols[1]:
                moneda = st.selectbox("Moneda", ["ARS", "USD"], index=0, key=f"edit_moneda_{selected_pid}")
            etiqueta = st.text_input("Etiqueta", key=f"edit_tag_{selected_pid}")
            probabilidad = st.slider("Probabilidad", min_value=0, max_value=100, value=0, format="%d%%", key=f"edit_prob_{selected_pid}")
        with vd_cols[1]:
            embudo = st.text_input("Embudo", key=f"edit_embudo_{selected_pid}")
            fecha_cierre = st.date_input("Fecha prevista de cierre", key=f"edit_cierre_{selected_pid}")

        # Agregar opción especial solo en "Mis Proyectos" para eliminar (sin puntos)
        estado_options = ["activo", "pendiente", "finalizado", "cerrado", "Eliminar"]
        try:
            estado_index = ["activo", "pendiente", "finalizado", "cerrado"].index((data["estado"] or "").strip().lower())
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
            # Guardar sin autocompletar la descripción
            if update_proyecto(selected_pid, user_id, titulo=titulo, descripcion=descripcion, cliente_id=cliente_id, estado=estado):
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
            file_path = os.path.join(save_dir, f.name)
            with open(file_path, "wb") as out:
                out.write(f.getvalue())
            add_proyecto_document(selected_pid, user_id, f.name, file_path, f.type, len(f.getvalue()))
        st.success("Documentos subidos.")

    docs_df = get_proyecto_documentos(selected_pid)
    if not docs_df.empty:
        preview_key = f"preview_doc_{selected_pid}"
        current_preview_id = st.session_state.get(preview_key)
        for _, d in docs_df.iterrows():
            # Acciones administrativas
            if st.button(f"Eliminar {d['filename']}", key=f"del_doc_{selected_pid}_{int(d['id'])}"):
                if remove_proyecto_document(int(d["id"]), user_id):
                    st.success("Documento eliminado.")
                else:
                    st.error("No se pudo eliminar el documento.")

        # Selector de archivos con descarga única
        st.markdown("**Descargar por selector**")
        file_names = docs_df["filename"].tolist()
        if file_names:
            selected_name = st.selectbox(
                "Archivo",
                options=file_names,
                key=f"doc_selector_{selected_pid}"
            )
            try:
                sel_row = docs_df.loc[docs_df["filename"] == selected_name].iloc[0]
                sel_path = sel_row["file_path"]
                sel_id = int(sel_row["id"])

                cols = st.columns([1, 1, 6])
                with cols[0]:
                    with open(sel_path, "rb") as fh:
                        st.download_button(
                            label="Descargar",
                            data=fh.read(),
                            file_name=selected_name,
                            key=f"dl_selector_{selected_pid}"
                        )
                with cols[1]:
                    rel = _make_static_preview_link(sel_path, sel_id)
                    href = _absolute_static_url(rel) if rel else None
                    if href:
                        st.link_button("Vista previa", href)
                    else:
                        st.warning("No se pudo preparar la vista previa.")
            except Exception:
                st.warning("No se pudo cargar el archivo seleccionado.")

    # NUEVO: compartir solo con usuarios del mismo departamento y excluyendo al actual
    try:
        current_user_rol_id = get_user_rol_id(user_id)
        commercial_users_df = get_users_by_rol(current_user_rol_id)
        id_to_name = {
            int(u["id"]): f"{u['nombre']} {u['apellido']}"
            for _, u in commercial_users_df.iterrows()
            if int(u["id"]) != int(user_id)  # excluir al usuario actual
        }
        share_options = list(id_to_name.values())
        name_to_id = {v: k for k, v in id_to_name.items()}
    except Exception:
        share_options, name_to_id, id_to_name = [], {}, {}

    try:
        current_shared = pd.read_sql_query(
            text("SELECT user_id FROM proyecto_compartidos WHERE proyecto_id = :pid"),
            con=get_engine(),
            params={"pid": int(selected_pid)}
        )
        # esto ya excluye al actual porque id_to_name no lo contiene
        default_names = [
            id_to_name[int(u)]
            for u in current_shared["user_id"].tolist()
            if int(u) in id_to_name
        ]
    except Exception:
        default_names = []

    share_users = st.multiselect(
        "Visible para",
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
    try:
        estados_disponibles_shared = sorted({
            (str(e or "").strip().lower())
            for e in df.get("estado", []).tolist()
            if str(e or "").strip().lower() != "eliminar"
        })
    except Exception:
        estados_disponibles_shared = []

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
        df_shared_filtrado = df_shared_filtrado[df_shared_filtrado.get("estado", pd.Series(dtype=str)).fillna("").str.lower().isin([e.lower() for e in filtro_estados_s])]
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
      .dot-left.activo { background: #10b981; }
      .dot-left.pendiente { background: #f59e0b; }
      .dot-left.finalizado { background: #f59e0b; }
      .dot-left.cerrado { background: #ef4444; }
      .shared-sub { margin-top: 4px; color: #9ca3af; font-size: 15px; }
      .shared-author { margin-top: 2px; color: #9ca3af; font-size: 14px; }
      .status-pill {
        padding: 10px 16px; border-radius: 999px;
        font-size: 18px; font-weight: 700;
        border: 2px solid transparent;
      }
      .status-pill.activo { color: #10b981; border-color: #10b981; }
      .status-pill.pendiente { color: #f59e0b; border-color: #f59e0b; }
      .status-pill.finalizado { color: #f59e0b; border-color: #f59e0b; }
      .status-pill.cerrado { color: #ef4444; border-color: #ef4444; }
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
        estado = (r["estado"] or "").strip().lower()
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
                <span class=\"status-pill {estado}\">{estado or "-"}</span>
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
              <div class='detail-value'><span class='status-pill {(data['estado'] or '').strip().lower()}'>{data['estado']}</span></div>
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
        preview_key = f"preview_shared_doc_{selected_pid}"
        current_preview_id = st.session_state.get(preview_key)
        for _, d in docs_df.iterrows():
            # Sin botón de vista previa aquí; se muestra junto a "Descargar" en el selector
            pass

        # Selector de archivos con descarga única (solo compartidos)
        st.markdown("**Descargar por selector**")
        file_names = docs_df["filename"].tolist()
        if file_names:
            selected_name = st.selectbox(
                "Archivo",
                options=file_names,
                key=f"shared_doc_selector_{selected_pid}"
            )
            try:
                sel_row = docs_df.loc[docs_df["filename"] == selected_name].iloc[0]
                sel_path = sel_row["file_path"]
                sel_id = int(sel_row["id"])

                cols = st.columns([1, 1, 6])
                with cols[0]:
                    with open(sel_path, "rb") as fh:
                        st.download_button(
                            label="Descargar",
                            data=fh.read(),
                            file_name=selected_name,
                            key=f"dl_shared_selector_{selected_pid}"
                        )
                with cols[1]:
                    # Abrir directamente en el navegador con visor nativo
                    rel = _make_static_preview_link(sel_path, sel_id)
                    href = _absolute_static_url(rel) if rel else None
                    if href:
                        st.link_button("Vista previa", href)
                    else:
                        st.warning("No se pudo preparar la vista previa.")
            except Exception:
                st.warning("No se pudo preparar la descarga del archivo seleccionado.")