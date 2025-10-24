import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import timedelta, date as _date
from .database import (
    get_roles_dataframe,
    get_users_dataframe,
    get_users_by_rol,
    get_modalidades_dataframe,
    get_user_weekly_modalities,
    get_weekly_modalities_by_rol,  # nombre correcto
    upsert_user_modality_for_date,
    get_clientes_dataframe,
)
from .utils import get_week_dates, format_week_range

# Cachear funciones de obtención de datos para mejorar el rendimiento
@st.cache_data(ttl=3600) # Cachea por 1 hora
def cached_get_roles_dataframe(exclude_admin=True, exclude_sin_rol=True, exclude_hidden=True):
    return get_roles_dataframe(exclude_admin, exclude_sin_rol, exclude_hidden)

@st.cache_data(ttl=3600)
def cached_get_users_dataframe():
    return get_users_dataframe()

@st.cache_data(ttl=3600)
def cached_get_users_by_rol(rol_id, exclude_hidden=True):
    return get_users_by_rol(rol_id, exclude_hidden)

@st.cache_data(ttl=3600)
def cached_get_modalidades_dataframe():
    return get_modalidades_dataframe()

@st.cache_data(ttl=3600)
def cached_get_clientes_dataframe():
    return get_clientes_dataframe()

@st.cache_data(ttl=600) # Cachea por 10 minutos para los defaults
def cached_get_user_default_schedule(user_id):
    return get_user_default_schedule(user_id)

@st.cache_data(ttl=60) # Cachea por 1 minuto para asignaciones semanales
def cached_get_weekly_modalities_by_rol(rol_id, start_date, end_date):
    return get_weekly_modalities_by_rol(rol_id, start_date, end_date)

def render_planning_management():
    import unicodedata
    import difflib
    import re
    from .database import get_user_default_schedule  # NUEVO: necesario para aplicar defaults a la semana visible
    st.subheader("📅 Planificación Semanal de Usuarios (Admin)")

    # Inicializar variables para evitar UnboundLocalError
    selected_role_id = None
    selected_user_id = None

    # Navegación de semana con offset persistente
    if 'admin_week_offset' not in st.session_state:
        st.session_state.admin_week_offset = 0
    start_of_week, end_of_week = get_week_dates(st.session_state.admin_week_offset)
    start_date = start_of_week.date() if hasattr(start_of_week, "date") else start_of_week
    end_date = end_of_week.date() if hasattr(end_of_week, "date") else end_of_week

    week_range_str = format_week_range(start_of_week, end_of_week)
    nav_cols = st.columns([0.08, 0.84, 0.08])
    with nav_cols[0]:
        if st.button("⬅️", key="admin_week_prev", use_container_width=True):
            st.session_state.admin_week_offset -= 1
            st.rerun()
    with nav_cols[1]:
        st.markdown(
            f"<p style='text-align:center; margin:0; padding:6px; font-weight:600;'>Semana: {week_range_str}</p>",
            unsafe_allow_html=True
        )
    with nav_cols[2]:
        disable_next = st.session_state.admin_week_offset == 0
        if st.button("➡️", key="admin_week_next", disabled=disable_next, use_container_width=True):
            st.session_state.admin_week_offset += 1
            st.rerun()

    # Días laborales (Lunes-Viernes)
    week_dates = []
    current_date = start_date
    for _ in range(5):
        week_dates.append(current_date)
        current_date += timedelta(days=1)

    # Mapeo días ES
    day_mapping = {
        "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
        "Thursday": "Jueves", "Friday": "Viernes"
    }

    # Clientes para uso en vista
    clientes_df = cached_get_clientes_dataframe()
    cliente_options = [(int(row["id_cliente"]), row["nombre"]) for _, row in clientes_df.iterrows()]

    # Catálogo de modalidades para selects y validaciones
    modalidades_df = cached_get_modalidades_dataframe()
    options_ids = [int(row["id_modalidad"]) for _, row in modalidades_df.iterrows()]
    desc_by_id = {int(row["id_modalidad"]): str(row["descripcion"]) for _, row in modalidades_df.iterrows()}

    # Divider de separación (dejamos la vista para más abajo, tras los filtros)
    st.divider()
    st.markdown("Vista del departamento (solo lectura):")

    # [MOVIDO] Filtros de Departamento y Usuario bajo el título de la vista
    roles_df = cached_get_roles_dataframe(exclude_admin=True, exclude_sin_rol=True, exclude_hidden=True)
    roles_options = [(int(r["id_rol"]), r["nombre"]) for _, r in roles_df.iterrows()]
    if not roles_options:
        st.info("No hay departamentos disponibles.")
        return

    # Estilos para el placeholder alineado con el selectbox
    st.markdown("""
        <style>
        .placeholder-label {
            font-size: 0.90rem;
            font-weight: 600;
            color: rgba(255,255,255,0.75);
            margin: 0 0 4px 0;
        }
        .placeholder-select {
            min-height: 42px;
            display: flex;
            align-items: center;
            padding: 0 12px;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            background-color: rgba(38, 40, 51, 0.35);
        }
        </style>
    """, unsafe_allow_html=True)

    col_filtros = st.columns(2)
    with col_filtros[0]:
        selected_role_id = st.selectbox(
            "Departamento",
            options=[rid for rid, _ in roles_options],
            format_func=lambda rid: next(name for rid2, name in roles_options if rid2 == rid),
            key="admin_plan_role_v3_top",
            index=None  # Placeholder "Choose an option"
        )
        # Fallback: si por cualquier motivo el selectbox devuelve None, usa el valor persistido
        if selected_role_id is None:
            selected_role_id = st.session_state.get("admin_plan_role_v3_top")

        # Persistir siempre el departamento seleccionado para reutilizarlo al cambiar semana
        if selected_role_id is not None:
            st.session_state["admin_dept_for_view"] = int(selected_role_id)

    peers_df = pd.DataFrame()
    with col_filtros[1]:
        if selected_role_id is None:
            selected_user_id = None
            # Placeholder alineado con el selectbox
            st.markdown('<div class="placeholder-label">Usuario</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="placeholder-select">Selecciona un departamento para editar planificación.</div>',
                unsafe_allow_html=True
            )
        else:
            peers_df = cached_get_users_by_rol(selected_role_id, exclude_hidden=False).copy()
            peers_df["nombre_completo"] = peers_df.apply(lambda r: f"{r['nombre']} {r['apellido']}".strip(), axis=1)
            selected_user_id = st.selectbox(
                "Usuario",
                options=[int(uid) for uid in peers_df["id"].tolist()] if not peers_df.empty else [],
                format_func=lambda uid: peers_df.loc[peers_df["id"] == uid, "nombre_completo"].iloc[0],
                key="admin_plan_user_v3_top",
                index=None  # Placeholder "Choose an option"
            )

    # [REORDENADO] Mensaje/tabla debajo del recuadro de filtros
    dept_for_view = selected_role_id if selected_role_id is not None else st.session_state.get("admin_dept_for_view")
    if dept_for_view is None and selected_user_id is not None:
        try:
            udf = cached_get_users_dataframe()
            row = udf[udf["id"] == int(selected_user_id)]
            dept_for_view = int(row["rol_id"].iloc[0]) if not row.empty else None
        except Exception:
            dept_for_view = None

    # Re-persistir por si vino del usuario
    if dept_for_view is not None:
        st.session_state["admin_dept_for_view"] = int(dept_for_view)

    # NUEVO: reconstruir peers_df usando el departamento persistido si quedó vacío
    if (peers_df is None or peers_df.empty) and dept_for_view is not None:
        peers_df = cached_get_users_by_rol(int(dept_for_view), exclude_hidden=False).copy()
        if not peers_df.empty:
            peers_df["nombre_completo"] = peers_df.apply(lambda r: f"{r['nombre']} {r['apellido']}".strip(), axis=1)

    if dept_for_view is not None:
        # 1) Leer asignaciones reales de la semana y mapearlas
        rol_sched_df = cached_get_weekly_modalities_by_rol(dept_for_view, start_date, end_date)
        rol_map = {}
        for _, row in rol_sched_df.iterrows():
            fecha_obj = pd.to_datetime(row["fecha"]).date()
            display_val = row["modalidad"]
            try:
                if isinstance(display_val, str) and display_val.strip().lower() == "cliente":
                    cliente_nombre = row.get("cliente_nombre")
                    if cliente_nombre and str(cliente_nombre).strip():
                        display_val = str(cliente_nombre)
            except Exception:
                pass
            rol_map[(int(row["user_id"]), fecha_obj)] = display_val

        # 2) Mapeos de clientes
        cliente_nombres = {str(name).strip() for _, name in cliente_options}
        cliente_name_by_id = {int(cid): str(name) for cid, name in cliente_options}

        # 3) Defaults por usuario (si faltan, se infieren de la semana anterior y se guardan)
        defaults_by_user = {}
        prev_start = start_date - timedelta(days=7)
        prev_end = end_date - timedelta(days=7)
        for _, peer in peers_df.iterrows():
            uid = int(peer["id"])

            # Leer defaults existentes
            dmap = {}
            try:
                df_def = cached_get_user_default_schedule(uid)
                existing_dows = set(df_def["day_of_week"].astype(int).tolist()) if not df_def.empty else set()

                # Si no hay 5 días, intentar inferirlos de la semana anterior
                if len(existing_dows) < 5:
                    prev_df = get_user_weekly_modalities(uid, prev_start, prev_end)
                    inferred = {}
                    for _, r in prev_df.iterrows():
                        d = pd.to_datetime(r["fecha"]).date()
                        dow = d.weekday()
                        mod_id = int(r["modalidad_id"]) if "modalidad_id" in r and pd.notna(r["modalidad_id"]) else None
                        cli_id = int(r["cliente_id"]) if ("cliente_id" in r and pd.notna(r["cliente_id"])) else None
                        if mod_id is not None and dow in range(0, 5):
                            inferred[dow] = (mod_id, cli_id)

                    # Guardar lo inferido como defaults
                    for dow, pair in inferred.items():
                        try:
                            upsert_user_default_schedule(uid, int(dow), int(pair[0]), pair[1])
                        except Exception:
                            pass

                    # Volver a leer defaults para asegurar dmap
                    df_def = cached_get_user_default_schedule(uid)

                # Construir mapa final de defaults por weekday
                for _, r in df_def.iterrows():
                    dow = int(r["day_of_week"])
                    mod_id = int(r["modalidad_id"])
                    cli_id = int(r["cliente_id"]) if ("cliente_id" in r and pd.notna(r["cliente_id"])) else None
                    dmap[dow] = (mod_id, cli_id)
            except Exception:
                dmap = {}
            defaults_by_user[uid] = dmap

        # 4) AUTOCOMPLETAR: persistir en la semana visible lo que falte según defaults
        inserted = 0
        for _, peer in peers_df.iterrows():
            uid = int(peer["id"])
            dmap = defaults_by_user.get(uid, {})
            for day in week_dates:
                if (uid, day) in rol_map:
                    continue  # ya tiene asignación
                pair = dmap.get(day.weekday())
                if pair:
                    mod_id, cli_id = pair
                    try:
                        upsert_user_modality_for_date(uid, dept_for_view, day, int(mod_id), cli_id)
                        inserted += 1
                    except Exception:
                        pass

        # Si insertamos defaults, recargar la semana para reflejarlos
        if inserted > 0:
            rol_sched_df = get_weekly_modalities_by_rol(dept_for_view, start_date, end_date)
            rol_map = {}
            for _, row in rol_sched_df.iterrows():
                fecha_obj = pd.to_datetime(row["fecha"]).date()
                display_val = row["modalidad"]
                try:
                    if isinstance(display_val, str) and display_val.strip().lower() == "cliente":
                        cliente_nombre = row.get("cliente_nombre")
                        if cliente_nombre and str(cliente_nombre).strip():
                            display_val = str(cliente_nombre)
                except Exception:
                    pass
                rol_map[(int(row["user_id"]), fecha_obj)] = display_val

        # 5) Construcción de la matriz (con fallback visual si aún faltara algo)
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
                        mod_desc = desc_by_id.get(pair[0], "Sin asignar")
                        modalidad = cliente_name_by_id.get(pair[1], "Cliente") if mod_desc.strip().lower() == "cliente" else mod_desc
                    else:
                        modalidad = "Sin asignar"
                fila.append(modalidad)
                if modalidad != "Sin asignar":
                    asignadas_count += 1
            if asignadas_count > 0:
                matriz.append(fila)

        if matriz:
            columnas = ["Usuario"] + [f"{day_mapping.get(day.strftime('%A'), day.strftime('%A'))}\n{day.strftime('%d/%m')}" for day in week_dates]
            df_matriz = pd.DataFrame(matriz, columns=columnas)
        
            def colorear_modalidad(val):
                val_str = str(val).strip() if val is not None else ""
                val_norm = val_str.lower()
                if val_norm in ("presencial", "systemscorp"):
                    return "background-color: #28a745; color: white; font-weight: bold; border: 1px solid #3a3a3a"
                elif val_norm == "remoto":
                    return "background-color: #007bff; color: white; font-weight: bold; border: 1px solid #3a3a3a"
                elif val_norm == "sin asignar":
                    return "border: 1px solid #3a3a3a"
                elif val_str in cliente_nombres:
                    return "background-color: #8e44ad; color: white; font-weight: bold; border: 1px solid #3a3a3a"
                else:
                    return "background-color: #6c757d; color: white; font-weight: bold; border: 1px solid #3a3a3a"
            
            styled_df = (
                df_matriz
                    .style
                    .applymap(colorear_modalidad, subset=[c for c in df_matriz.columns if c != "Usuario"])
                    .set_properties(subset=["Usuario"], **{"border": "1px solid #3a3a3a"})
                    .hide(axis="index")
            )

            html = f"""
            <div class="table-wrapper" style="width: 1400px; overflow-x: auto;">
              <style>
                .table-wrapper {{ width: 1400px !important; }}
                .table-wrapper table.dataframe {{ width: 1400px !important; table-layout: fixed; border-collapse: collapse; }}
                .table-wrapper th, .table-wrapper td {{ border: 1px solid #3a3a3a; padding: 8px; white-space: nowrap; }}
                .table-wrapper td:first-child, .table-wrapper th:first-child {{ width: 200px; }}
                .table-wrapper th:not(:first-child), .table-wrapper td:not(:first-child) {{ width: 240px; }}
                .table-wrapper th {{ color: white; font-weight: bold; }}
                .table-wrapper td:first-child {{ color: white; font-weight: bold; }}
              </style>
              {styled_df.to_html()}
            </div>
            """

            # Altura dinámica; ancho ocupa todo el contenedor
            row_height = 40
            num_rows = len(matriz)
            total_height = 60 + num_rows * row_height
            total_height = min(900, max(380, total_height))

            components.html(html, height=total_height, scrolling=True, width=1400)
        else:
            st.info("No hay usuarios con días asignados en la semana seleccionada.")
    else:
        st.info("Selecciona un usuario o departamento para ver la vista del departamento.")

    # Apartado: subir cronograma por defecto (al final de la página)
    st.divider()
    with st.expander("📄 Cronograma por defecto (subir planilla)", expanded=False):
        file = st.file_uploader(
            "Subir CSV o Excel con columnas Equipo, Lunes, Martes, Miércoles, Jueves, Viernes",
            type=["csv", "xlsx"]
        )

        # NUEVO: botón para procesar y asignar
        process_clicked = st.button(
            "Procesar planilla y asignar días",
            key="process_default_schedule",
            type="primary",
            disabled=(file is None)
        )

        # Ejecuta el procesamiento solo al pulsar el botón
        if file is not None and process_clicked:
            try:
                # Leer archivo en crudo, sin asumir encabezado
                if file.name.lower().endswith(".xlsx"):
                    df_upload = pd.read_excel(file, header=None)
                else:
                    df_upload = pd.read_csv(file, header=None)

                # Detectar fila de encabezado (Equipo/Lunes/.../Viernes)
                def find_header_row(df0):
                    top = min(15, len(df0))
                    for i in range(top):
                        row_vals = [str(x).strip().lower() for x in df0.iloc[i].tolist()]
                        has_equipo = any(x == "equipo" for x in row_vals)
                        has_lunes = any("lunes" in x for x in row_vals)
                        has_viernes = any("viernes" in x for x in row_vals)
                        if has_equipo and has_lunes and has_viernes:
                            return i
                    return None

                header_idx = find_header_row(df_upload)
                if header_idx is None:
                    st.error("No se pudo detectar el encabezado (Equipo/Lunes/.../Viernes). Revisa tu archivo.")
                    return

                # Aplicar encabezado y recortar filas anteriores
                df_upload.columns = [str(x).strip() for x in df_upload.iloc[header_idx].tolist()]
                df_upload = df_upload.iloc[header_idx + 1:].reset_index(drop=True)

                # Normalizar nombres de columnas esperadas
                orig_cols = df_upload.columns.tolist()
                rename_map = {}
                for orig in orig_cols:
                    sc = str(orig).strip()
                    lc = sc.lower()
                    if lc == "equipo":
                        rename_map[orig] = "Equipo"
                    elif "lunes" in lc:
                        rename_map[orig] = "Lunes"
                    elif "martes" in lc:
                        rename_map[orig] = "Martes"
                    elif "miercoles" in lc or "miércoles" in lc:
                        rename_map[orig] = "Miércoles"
                    elif "jueves" in lc:
                        rename_map[orig] = "Jueves"
                    elif "viernes" in lc:
                        rename_map[orig] = "Viernes"
                df_upload = df_upload.rename(columns=rename_map)

                required_cols = ["Equipo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
                missing = [c for c in required_cols if c not in df_upload.columns]
                if missing:
                    st.error(f"Columnas faltantes en la planilla: {', '.join(missing)}")
                    return

                # Utilidades de normalización
                def normalize_text(s):
                    s = str(s or "").strip().lower()
                    s = unicodedata.normalize("NFD", s)
                    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
                    s = " ".join(s.split())
                    return s

                # Ignorar filas de encabezado/titulo (extendido)
                ignored_equipo_patterns = {"ultima actualizacion", "total oficina", "nan", ""}
                df_upload["Equipo_norm"] = df_upload["Equipo"].apply(normalize_text)
                df_upload = df_upload[~df_upload["Equipo_norm"].isin(ignored_equipo_patterns)]

                # Catálogo de usuarios
                usuarios_df = get_users_dataframe()
                usuarios_df["nombre_completo"] = usuarios_df.apply(
                    lambda r: f"{str(r['nombre']).strip()} {str(r['apellido']).strip()}".strip(), axis=1
                )
                name_to_id = {normalize_text(n): int(uid) for uid, n in zip(usuarios_df["id"], usuarios_df["nombre_completo"])}
                username_to_id = {normalize_text(u): int(uid) for uid, u in zip(usuarios_df["id"], usuarios_df["username"])}

                # Intento 'Apellido Nombre' adicional
                apell_nombre_to_id = {}
                for _, r in usuarios_df.iterrows():
                    apell_nombre = normalize_text(f"{str(r['apellido']).strip()} {str(r['nombre']).strip()}")
                    apell_nombre_to_id[apell_nombre] = int(r["id"])

                # Tokenización y cobertura de coincidencias parciales
                def tokenize(s):
                    s = normalize_text(s)
                    toks = [t for t in re.split(r"[\s\-/|,]+", s) if t and len(t) >= 2]
                    return set(toks)

                user_tokens_map = {}
                for _, r in usuarios_df.iterrows():
                    uid = int(r["id"])
                    toks = tokenize(f"{str(r['nombre']).strip()} {str(r['apellido']).strip()}")
                    uname = normalize_text(r["username"])
                    if uname:
                        toks |= tokenize(uname)
                    user_tokens_map[uid] = toks

                def match_user_id(equipo_raw):
                    raw = str(equipo_raw or "").strip()
                    if not raw:
                        return None

                    # 0) username entre paréntesis: "Nombre Apellido (username)"
                    m = re.search(r"\(([^)]+)\)", raw)
                    if m:
                        cand = normalize_text(m.group(1))
                        if cand in username_to_id:
                            return username_to_id[cand]

                    # 1) probar por partes (separadores comunes)
                    for sep in [" - ", "-", "/", "|", ","]:
                        if sep in raw:
                            parts = [p.strip() for p in raw.split(sep) if p.strip()]
                            for p in parts:
                                pk = normalize_text(p)
                                if pk in username_to_id:
                                    return username_to_id[pk]
                                if pk in name_to_id:
                                    return name_to_id[pk]
                                if pk in apell_nombre_to_id:
                                    return apell_nombre_to_id[pk]

                    # 2) exactas normalizadas
                    key = normalize_text(raw)
                    if key in name_to_id:
                        return name_to_id[key]
                    if key in apell_nombre_to_id:
                        return apell_nombre_to_id[key]
                    if key in username_to_id:
                        return username_to_id[key]

                    # 3) cobertura de tokens
                    eq_tokens = tokenize(raw)
                    candidates = []
                    for uid, toks in user_tokens_map.items():
                        inter = eq_tokens & toks
                        if inter:
                            coverage = len(inter) / max(1, len(eq_tokens))         # % de tokens del archivo cubiertos
                            jaccard = len(inter) / max(1, len(eq_tokens | toks))   # similitud global
                            score = (coverage * 0.7) + (jaccard * 0.3)
                            if coverage >= 0.6 or jaccard >= 0.45:
                                candidates.append((uid, score))
                    if len(candidates) == 1:
                        return candidates[0][0]
                    elif len(candidates) > 1:
                        candidates.sort(key=lambda x: x[1], reverse=True)
                        if candidates[0][1] - candidates[1][1] >= 0.15:
                            return candidates[0][0]

                    # 4) fuzzy con usernames
                    best_uname = difflib.get_close_matches(key, list(username_to_id.keys()), n=1, cutoff=0.75)
                    if best_uname:
                        return username_to_id.get(best_uname[0])

                    # 5) fuzzy con nombres/apellidos
                    keys_pool = list(name_to_id.keys()) + list(apell_nombre_to_id.keys())
                    best = difflib.get_close_matches(key, keys_pool, n=1, cutoff=0.8)
                    if best:
                        kb = best[0]
                        return name_to_id.get(kb) or apell_nombre_to_id.get(kb)

                    return None

                # Modalidades y clientes
                modalidades_df = get_modalidades_dataframe()
                mod_by_desc = {normalize_text(d): int(mid) for mid, d in zip(modalidades_df["id_modalidad"], modalidades_df["descripcion"])}

                # Asegurar modalidad 'Cliente'
                from .database import get_or_create_modalidad
                try:
                    cliente_mod_id = int(get_or_create_modalidad("Cliente"))
                    mod_by_desc["cliente"] = cliente_mod_id
                except Exception:
                    st.warning("No se pudo asegurar la modalidad 'Cliente'. Verifica el catálogo de modalidades.")

                clientes_df = get_clientes_dataframe()
                cliente_by_name = {normalize_text(n): int(cid) for cid, n in zip(clientes_df["id_cliente"], clientes_df["nombre"])}

                # Parser de celdas (se mantiene para carga de defaults)
                desc_by_mod_id = {int(mid): str(desc) for mid, desc in zip(modalidades_df["id_modalidad"], modalidades_df["descripcion"])}

                def parse_cell(cell_val):
                    s_raw = str(cell_val if cell_val is not None else "").strip()
                    if not s_raw:
                        return (None, None)
                    key = normalize_text(s_raw)

                    # 1) Coincidencia directa con cliente
                    if key in cliente_by_name:
                        return (cliente_mod_id, cliente_by_name[key])

                    # 2) Coincidencia directa con modalidad
                    if key in mod_by_desc:
                        return (mod_by_desc[key], None)

                    # 3) Buscar por partes (p.ej. "Cliente - Suteba", "Suteba, Cliente")
                    parts = [p.strip() for p in re.split(r"[\-/|,]", s_raw) if p.strip()]
                    mod_fallback = None
                    for p in reversed(parts):  # preferir el último token como posible cliente
                        pk = normalize_text(p)
                        if pk in cliente_by_name:
                            return (cliente_mod_id, cliente_by_name[pk])
                        if mod_fallback is None and pk in mod_by_desc:
                            mod_fallback = mod_by_desc[pk]
                    if mod_fallback is not None:
                        return (mod_fallback, None)

                    # 4) Fuzzy con clientes
                    best_cli = difflib.get_close_matches(key, list(cliente_by_name.keys()), n=1, cutoff=0.85)
                    if best_cli:
                        return (cliente_mod_id, cliente_by_name[best_cli[0]])

                    # 5) Fuzzy con modalidades
                    best_mod = difflib.get_close_matches(key, list(mod_by_desc.keys()), n=1, cutoff=0.85)
                    if best_mod:
                        return (mod_by_desc[best_mod[0]], None)

                    return (None, None)

                # Carga de cronograma por defecto (sin vistas de depuración)

                from .database import upsert_user_default_schedule
                errores = []
                actualizados = 0
                updated_users = set()  # NUEVO: trackear usuarios con cambios

                day_cols = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
                day_idx = {"Lunes": 0, "Martes": 1, "Miércoles": 2, "Jueves": 3, "Viernes": 4}

                # Procesamiento de filas
                for _, row in df_upload.iterrows():
                    equipo_val = row["Equipo"]
                    equipo_key = normalize_text(equipo_val)
                    if (not equipo_key) or any(p in equipo_key for p in ignored_equipo_patterns):
                        continue

                    uid = match_user_id(equipo_val)
                    if not uid:
                        errores.append(f"Usuario no encontrado: '{equipo_val}'")
                        continue

                    updated_one = False
                    for dc in day_cols:
                        mod_id, cli_id = parse_cell(row[dc])
                        if mod_id is None:
                            continue
                        dow = day_idx[dc]
                        try:
                            upsert_user_default_schedule(int(uid), int(dow), int(mod_id), cli_id)
                            updated_one = True
                        except Exception as e:
                            errores.append(f"{equipo_val} {dc}: {str(e)}")
                    if updated_one:
                        actualizados += 1
                        updated_users.add(int(uid))  # NUEVO: agregar usuario con cambios

                if actualizados > 0:
                    st.success(f"Cronograma por defecto actualizado para {actualizados} usuario(s).")
                else:
                    st.info("La planilla no actualizó cronogramas por defecto (posibles duplicados).")

                try:
                    week_days = []
                    d = start_date
                    for _ in range(5):
                        week_days.append(d)
                        d += timedelta(days=1)

                    cambios = 0

                    for _, row in df_upload.iterrows():
                        equipo_val = row.get("Equipo", "")
                        uid = match_user_id(equipo_val)
                        if not uid:
                            continue

                        row_u = usuarios_df[usuarios_df["id"] == int(uid)]
                        user_role_id = int(row_u["rol_id"].iloc[0]) if not row_u.empty else None
                        if user_role_id is None:
                            errores.append(f"Rol no encontrado para usuario {uid}")
                            continue

                        day_headers = {0: ["Lunes"], 1: ["Martes"], 2: ["Miércoles", "Miercoles"], 3: ["Jueves"], 4: ["Viernes"]}
                        row_schedule = {}
                        for dow, headers in day_headers.items():
                            cell_val = None
                            for h in headers:
                                if h in row:
                                    cell_val = row.get(h)
                                    break
                            mod_id, cli_id = parse_cell(cell_val)
                            if mod_id is None:
                                continue
                            row_schedule[dow] = (int(mod_id), cli_id)

                        for day in week_days:
                            pair = row_schedule.get(day.weekday())
                            if not pair:
                                continue
                            mod_id, cli_id = pair
                            try:
                                upsert_user_modality_for_date(int(uid), user_role_id, day, int(mod_id), cli_id)
                                cambios += 1
                            except Exception as e:
                                errores.append(f"UID {uid} {day.strftime('%d/%m')}: {str(e)}")

                    if cambios > 0:
                        st.success(f"Se aplicaron {cambios} asignaciones a la semana visible desde la planilla.")
                        st.rerun()
                    else:
                        st.info("La planilla no tenía asignaciones aplicables para esta semana.")
                except Exception as e:
                    st.error(f"Error al aplicar la planilla a la semana visible: {e}")
            except Exception as e:
                st.error(f"Error procesando la planilla: {e}")

    # Editor único: reutiliza los filtros superiores (selected_role_id/selected_user_id)
    if selected_user_id is not None and selected_role_id is not None:
        st.markdown("Editar modalidades del usuario seleccionado por día:")

        user_sched_df = get_user_weekly_modalities(selected_user_id, start_date, end_date)
        user_sched_map = {}
        user_client_map = {}
        for _, row in user_sched_df.iterrows():
            fecha_obj = pd.to_datetime(row["fecha"]).date()
            user_sched_map[fecha_obj] = int(row["modalidad_id"])
            if "cliente_id" in row and pd.notna(row["cliente_id"]):
                user_client_map[fecha_obj] = int(row["cliente_id"])

        # Defaults del usuario para autocompletar días futuros sin asignación
        default_by_dow = {}
        try:
            from .database import get_user_default_schedule
            defaults_df = get_user_default_schedule(selected_user_id)
            for _, r in defaults_df.iterrows():
                dow = int(r["day_of_week"])
                mod_id = int(r["modalidad_id"])
                cli_id = int(r["cliente_id"]) if ("cliente_id" in r and pd.notna(r["cliente_id"])) else None
                default_by_dow[dow] = (mod_id, cli_id)
        except Exception:
            default_by_dow = {}

        cols = st.columns(5)
        selected_by_day = {}
        selected_client_by_day = {}

        for i, day in enumerate(week_dates):
            dow = day.weekday()
            today = _date.today()
            default_pair = default_by_dow.get(dow)
            default_mod_id = user_sched_map.get(day, None)

            if default_mod_id is None and default_pair and day >= today:
                default_mod_id = default_pair[0]

            default_index = options_ids.index(default_mod_id) if (
                default_mod_id is not None and default_mod_id in options_ids
            ) else None

            with cols[i]:
                day_name_es = day_mapping.get(day.strftime("%A"), day.strftime("%A"))
                st.write(day_name_es)
                st.caption(day.strftime("%d/%m"))
                mod_id = st.selectbox(
                    "Modalidad",
                    options=options_ids,
                    format_func=lambda x: modalidades_df.loc[modalidades_df["id_modalidad"] == x, "descripcion"].iloc[0],
                    index=default_index,
                    key=f"admin_user_mod_v3_single_{selected_user_id}_{day.isoformat()}",
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
                            key=f"admin_client_v3_single_{selected_user_id}_{day.isoformat()}",
                            label_visibility="collapsed"
                        )
                        selected_client_by_day[day] = client_id

        # Validación previa: todos los días completos
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

        save_clicked = st.button(
            "Guardar Planificación del Usuario",
            type="primary",
            key=f"admin_save_user_week_single_{selected_user_id}",
            disabled=not form_complete
        )

        if save_clicked:
            if not form_complete:
                return
            errores = []
            try:
                for day in week_dates:
                    mod_id = selected_by_day[day]
                    es_cliente = desc_by_id.get(mod_id, "").strip().lower() == "cliente"
                    cliente_id = selected_client_by_day.get(day) if es_cliente else None
                    try:
                        upsert_user_modality_for_date(selected_user_id, selected_role_id, day, mod_id, cliente_id)
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
    else:
        pass
