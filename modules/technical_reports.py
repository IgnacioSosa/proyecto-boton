import html
import io
import os
import textwrap
import zipfile
from datetime import datetime

import pandas as pd
import streamlit as st
from sqlalchemy import text

from .config import PROJECT_UPLOADS_DIR
from .database import (
    ensure_projects_schema,
    get_all_proyectos,
    get_connection,
    get_engine,
    get_proyecto,
    get_proyectos_by_owner,
    get_proyectos_shared_with_user,
    queue_notification_event,
)
from .logging_utils import log_sql_error
from .quotes_data import is_project_open_status
from .ui_components import inject_project_card_css
from .utils import safe_rerun


def _scope_prefix(scope):
    return f"informes_tecnicos_{str(scope or 'commercial').strip().lower()}"


def _normalize_text(value):
    return " ".join(str(value or "").split()).strip()


def _normalize_multiline_text(value):
    return str(value or "").replace("\r\n", "\n").strip()


def _format_user_name(nombre, apellido, username=""):
    full = " ".join([str(nombre or "").strip(), str(apellido or "").strip()]).strip()
    return full or str(username or "Usuario").strip() or "Usuario"


def _format_datetime_label(value):
    try:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return "-"
        return parsed.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "-"


def _documents_zip_bytes(documents_df):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for _, row in documents_df.iterrows():
            file_path = str(row.get("file_path") or "").strip()
            if not file_path or not os.path.exists(file_path):
                continue
            arcname = str(row.get("filename") or os.path.basename(file_path) or "documento").strip() or "documento"
            zip_file.write(file_path, arcname=arcname)
    buffer.seek(0)
    return buffer.getvalue()


def _project_option_label(project_row):
    trato = project_row.get("trato_id") or project_row.get("id") or "-"
    titulo = _normalize_text(project_row.get("titulo")) or "Sin titulo"
    cliente = _normalize_text(project_row.get("cliente_nombre") or project_row.get("marca_nombre")) or "-"
    estado = _normalize_text(project_row.get("estado")) or "-"
    return f"Trato {trato} - {titulo} - {cliente} [{estado}]"


def _unique_filename(directory, original_name):
    base_name = os.path.basename(str(original_name or "archivo"))
    root, ext = os.path.splitext(base_name)
    candidate = base_name
    counter = 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{root}_{counter}{ext}"
        counter += 1
    return candidate


def _fetch_user_display_name(user_id):
    if user_id is None:
        return "Usuario"
    engine = get_engine()
    try:
        df = pd.read_sql_query(
            text(
                """
                SELECT nombre, apellido, username
                FROM usuarios
                WHERE id = :user_id
                LIMIT 1
                """
            ),
            con=engine,
            params={"user_id": int(user_id)},
        )
        if df.empty:
            return "Usuario"
        row = df.iloc[0].to_dict()
        return _format_user_name(row.get("nombre"), row.get("apellido"), row.get("username"))
    except Exception:
        return "Usuario"


def ensure_technical_reports_schema():
    ensure_projects_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS informes_tecnicos (
                id SERIAL PRIMARY KEY,
                proyecto_id INTEGER NOT NULL UNIQUE REFERENCES proyectos(id) ON DELETE CASCADE,
                requested_by INTEGER NOT NULL REFERENCES usuarios(id),
                estado VARCHAR(30) NOT NULL DEFAULT 'Solicitado',
                solicitud_inicial TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        try:
            c.execute("ALTER TABLE informes_tecnicos ADD COLUMN IF NOT EXISTS estado VARCHAR(30)")
        except Exception:
            pass
        try:
            c.execute("UPDATE informes_tecnicos SET estado = 'Solicitado' WHERE COALESCE(estado, '') = ''")
        except Exception:
            pass
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS informe_tecnico_comentarios (
                id SERIAL PRIMARY KEY,
                informe_id INTEGER NOT NULL REFERENCES informes_tecnicos(id) ON DELETE CASCADE,
                comentario TEXT NOT NULL,
                created_by INTEGER NULL REFERENCES usuarios(id),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS informe_tecnico_documentos (
                id SERIAL PRIMARY KEY,
                informe_id INTEGER NOT NULL REFERENCES informes_tecnicos(id) ON DELETE CASCADE,
                filename VARCHAR(255) NOT NULL,
                file_path TEXT NOT NULL,
                mime_type VARCHAR(100),
                file_size BIGINT,
                uploaded_by INTEGER NULL REFERENCES usuarios(id),
                is_vigente BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for ddl in [
            "CREATE INDEX IF NOT EXISTS idx_informes_tecnicos_proyecto_id ON informes_tecnicos(proyecto_id)",
            "CREATE INDEX IF NOT EXISTS idx_informes_tecnicos_requested_by ON informes_tecnicos(requested_by)",
            "CREATE INDEX IF NOT EXISTS idx_informe_tecnico_comentarios_informe_id ON informe_tecnico_comentarios(informe_id)",
            "CREATE INDEX IF NOT EXISTS idx_informe_tecnico_documentos_informe_id ON informe_tecnico_documentos(informe_id)",
        ]:
            try:
                c.execute(ddl)
            except Exception:
                pass
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log_sql_error(f"Error asegurando esquema de informes técnicos: {exc}")
    finally:
        conn.close()


def _get_visible_projects(user_id, scope="commercial", only_open=False):
    return _cached_visible_projects(user_id, scope=scope, only_open=only_open)


@st.cache_data(ttl=20, show_spinner=False)
def _cached_visible_projects(user_id, scope="commercial", only_open=False):
    ensure_technical_reports_schema()
    try:
        if scope == "technical_admin":
            df = get_all_proyectos()
        else:
            own_df = get_proyectos_by_owner(user_id)
            shared_df = get_proyectos_shared_with_user(user_id)
            frames = [frame for frame in [own_df, shared_df] if frame is not None and not frame.empty]
            df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if df.empty:
            return df
        df = df.drop_duplicates(subset=["id"]).copy()
        if only_open and "estado" in df.columns:
            df = df[df["estado"].apply(is_project_open_status)]
        if "id" in df.columns:
            df = df.sort_values("id", ascending=False, na_position="last")
        return df.reset_index(drop=True)
    except Exception as exc:
        log_sql_error(f"Error obteniendo tratos visibles para informes técnicos: {exc}")
        return pd.DataFrame()


def _visible_project_ids(user_id, scope="commercial", only_open=False):
    df = _get_visible_projects(user_id, scope=scope, only_open=only_open)
    if df.empty or "id" not in df.columns:
        return set()
    try:
        return {int(value) for value in df["id"].dropna().tolist()}
    except Exception:
        return set()


def get_technical_reports_dataframe(user_id=None, scope="commercial"):
    return _cached_technical_reports_dataframe(user_id=user_id, scope=scope)


@st.cache_data(ttl=20, show_spinner=False)
def _cached_technical_reports_dataframe(user_id=None, scope="commercial"):
    ensure_technical_reports_schema()
    engine = get_engine()
    try:
        df = pd.read_sql_query(
            text(
                """
                SELECT
                    it.id AS informe_id,
                    it.proyecto_id,
                    it.requested_by,
                    it.estado AS informe_estado,
                    it.solicitud_inicial,
                    it.created_at AS informe_created_at,
                    it.updated_at AS informe_updated_at,
                    p.id AS proyecto_id_real,
                    p.trato_id,
                    p.titulo AS trato_titulo,
                    p.descripcion AS trato_descripcion,
                    p.estado AS trato_estado,
                    p.fecha_cierre,
                    c.nombre AS cliente_nombre,
                    m.nombre AS marca_nombre,
                    TRIM(CONCAT(req.nombre, ' ', req.apellido)) AS solicitante_nombre,
                    TRIM(CONCAT(owner.nombre, ' ', owner.apellido)) AS vendedor_nombre,
                    COALESCE(comments.comments_count, 0) AS comentarios_count,
                    COALESCE(docs.docs_count, 0) AS documentos_count,
                    docs.vigente_filename,
                    docs.vigente_document_id
                FROM informes_tecnicos it
                JOIN proyectos p ON p.id = it.proyecto_id
                LEFT JOIN clientes c ON p.cliente_id = c.id_cliente
                LEFT JOIN marcas m ON p.marca_id = m.id_marca
                LEFT JOIN usuarios req ON req.id = it.requested_by
                LEFT JOIN usuarios owner ON owner.id = p.owner_user_id
                LEFT JOIN (
                    SELECT informe_id, COUNT(*) AS comments_count
                    FROM informe_tecnico_comentarios
                    GROUP BY informe_id
                ) comments ON comments.informe_id = it.id
                LEFT JOIN (
                    SELECT
                        d.informe_id,
                        COUNT(*) AS docs_count,
                        MAX(CASE WHEN d.is_vigente THEN d.filename END) AS vigente_filename,
                        MAX(CASE WHEN d.is_vigente THEN d.id END) AS vigente_document_id
                    FROM informe_tecnico_documentos d
                    GROUP BY d.informe_id
                ) docs ON docs.informe_id = it.id
                ORDER BY it.updated_at DESC, it.id DESC
                """
            ),
            con=engine,
        )
        if df.empty:
            return df
        if scope == "commercial":
            visible_ids = _visible_project_ids(user_id, scope=scope, only_open=False)
            if not visible_ids:
                return df.iloc[0:0].copy()
            df = df[df["proyecto_id"].isin(visible_ids)]
        return df.reset_index(drop=True)
    except Exception as exc:
        log_sql_error(f"Error listando informes técnicos: {exc}")
        return pd.DataFrame()


def get_technical_report(user_id=None, scope="commercial", report_id=None, project_id=None):
    df = get_technical_reports_dataframe(user_id=user_id, scope=scope)
    if df.empty:
        return None
    if report_id is not None:
        row = df[df["informe_id"] == int(report_id)]
        return row.iloc[0].to_dict() if not row.empty else None
    if project_id is not None:
        row = df[df["proyecto_id"] == int(project_id)]
        return row.iloc[0].to_dict() if not row.empty else None
    return None


def get_technical_report_comments_df(informe_id):
    return _cached_technical_report_comments_df(informe_id)


@st.cache_data(ttl=20, show_spinner=False)
def _cached_technical_report_comments_df(informe_id):
    ensure_technical_reports_schema()
    engine = get_engine()
    try:
        return pd.read_sql_query(
            text(
                """
                SELECT
                    c.id,
                    c.informe_id,
                    c.comentario,
                    c.created_by,
                    c.created_at,
                    TRIM(CONCAT(u.nombre, ' ', u.apellido)) AS autor_nombre,
                    u.username AS autor_username
                FROM informe_tecnico_comentarios c
                LEFT JOIN usuarios u ON u.id = c.created_by
                WHERE c.informe_id = :informe_id
                ORDER BY c.created_at ASC, c.id ASC
                """
            ),
            con=engine,
            params={"informe_id": int(informe_id)},
        )
    except Exception as exc:
        log_sql_error(f"Error listando comentarios de informe técnico {informe_id}: {exc}")
        return pd.DataFrame()


def get_technical_report_documents_df(informe_id):
    return _cached_technical_report_documents_df(informe_id)


@st.cache_data(ttl=20, show_spinner=False)
def _cached_technical_report_documents_df(informe_id):
    ensure_technical_reports_schema()
    engine = get_engine()
    try:
        return pd.read_sql_query(
            text(
                """
                SELECT
                    d.id,
                    d.informe_id,
                    d.filename,
                    d.file_path,
                    d.mime_type,
                    d.file_size,
                    d.uploaded_by,
                    d.is_vigente,
                    d.created_at,
                    TRIM(CONCAT(u.nombre, ' ', u.apellido)) AS autor_nombre,
                    u.username AS autor_username
                FROM informe_tecnico_documentos d
                LEFT JOIN usuarios u ON u.id = d.uploaded_by
                WHERE d.informe_id = :informe_id
                ORDER BY d.created_at DESC, d.id DESC
                """
            ),
            con=engine,
            params={"informe_id": int(informe_id)},
        )
    except Exception as exc:
        log_sql_error(f"Error listando documentos de informe técnico {informe_id}: {exc}")
        return pd.DataFrame()


def _clear_technical_reports_cache():
    _cached_visible_projects.clear()
    _cached_technical_reports_dataframe.clear()
    _cached_technical_report_comments_df.clear()
    _cached_technical_report_documents_df.clear()


def _persist_uploaded_documents(informe_id, uploaded_files, uploaded_by):
    docs_payload = []
    if not uploaded_files:
        return docs_payload
    save_dir = os.path.join(PROJECT_UPLOADS_DIR, "informes_tecnicos", str(informe_id))
    os.makedirs(save_dir, exist_ok=True)
    for uploaded_file in uploaded_files:
        file_bytes = uploaded_file.getvalue()
        unique_name = _unique_filename(save_dir, uploaded_file.name)
        file_path = os.path.join(save_dir, unique_name)
        with open(file_path, "wb") as output_file:
            output_file.write(file_bytes)
        docs_payload.append(
            {
                "filename": unique_name,
                "file_path": file_path,
                "mime_type": uploaded_file.type,
                "file_size": len(file_bytes),
                "uploaded_by": int(uploaded_by) if uploaded_by is not None else None,
            }
        )
    return docs_payload


def _append_documents_in_connection(conn, informe_id, docs_payload):
    inserted_ids = []
    if not docs_payload:
        return inserted_ids
    c = conn.cursor()
    for doc in docs_payload:
        c.execute(
            """
            INSERT INTO informe_tecnico_documentos (
                informe_id,
                filename,
                file_path,
                mime_type,
                file_size,
                uploaded_by
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                int(informe_id),
                str(doc.get("filename") or "").strip(),
                str(doc.get("file_path") or "").strip(),
                str(doc.get("mime_type") or "").strip() or None,
                int(doc.get("file_size") or 0),
                int(doc.get("uploaded_by")) if doc.get("uploaded_by") is not None else None,
            ),
        )
        row = c.fetchone()
        if row:
            inserted_ids.append(int(row[0]))
    return inserted_ids


def _set_vigente_document_in_connection(conn, informe_id, document_id=None):
    c = conn.cursor()
    c.execute(
        "UPDATE informe_tecnico_documentos SET is_vigente = FALSE WHERE informe_id = %s",
        (int(informe_id),),
    )
    if document_id is not None:
        c.execute(
            """
            UPDATE informe_tecnico_documentos
            SET is_vigente = TRUE
            WHERE informe_id = %s
              AND id = %s
            """,
            (int(informe_id), int(document_id)),
        )


def _queue_technical_report_notification(event_key, report_id, project, requested_by, acted_by, detail):
    try:
        project_trato = project.get("trato_id") or project.get("id") or "-"
        payload = {
            "report_id": int(report_id),
            "requested_by": int(requested_by) if requested_by is not None else None,
            "acted_by": int(acted_by) if acted_by is not None else None,
            "actor": _fetch_user_display_name(acted_by),
            "cliente": project.get("cliente_nombre") or project.get("marca_nombre") or "-",
            "trato": project_trato,
            "estado": project.get("estado") or "-",
            "detalle": str(detail or "").strip(),
        }
        dedupe_key = f"{event_key}:{int(report_id)}:{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        queue_notification_event(event_key, payload, dedupe_key=dedupe_key)
    except Exception as exc:
        log_sql_error(f"No se pudo encolar notificación de informe técnico: {exc}")


def save_technical_report_submission(
    project_id,
    acting_user_id,
    scope="commercial",
    initial_request="",
    comment="",
    uploaded_files=None,
    vigente_selection=None,
):
    ensure_technical_reports_schema()
    project = get_proyecto(project_id)
    if not project:
        raise ValueError("No se encontró el trato asociado.")
    if not is_project_open_status(project.get("estado")):
        raise ValueError("El informe técnico solo puede editarse mientras el trato siga abierto.")

    visible_ids = _visible_project_ids(acting_user_id, scope=scope, only_open=False)
    if scope == "commercial" and int(project_id) not in visible_ids:
        raise ValueError("No tienes permisos para operar sobre este trato.")

    normalized_initial_request = _normalize_multiline_text(initial_request)
    normalized_comment = _normalize_multiline_text(comment)

    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, requested_by, solicitud_inicial
            FROM informes_tecnicos
            WHERE proyecto_id = %s
            LIMIT 1
            """,
            (int(project_id),),
        )
        row = c.fetchone()
        created = False
        request_updated = False
        comment_added = False
        docs_payload = []
        inserted_doc_ids = []
        target_status = "Enviado" if scope == "technical_admin" else "Solicitado"

        if row:
            informe_id = int(row[0])
            requested_by = int(row[1])
            current_request = str(row[2] or "")
        else:
            if scope != "commercial":
                raise ValueError("El informe técnico debe ser creado por el sector comercial.")
            if not normalized_initial_request:
                raise ValueError("Debes completar la solicitud inicial para crear el informe técnico.")
            c.execute(
                """
                INSERT INTO informes_tecnicos (proyecto_id, requested_by, estado, solicitud_inicial)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (int(project_id), int(acting_user_id), target_status, normalized_initial_request),
            )
            informe_id = int(c.fetchone()[0])
            requested_by = int(acting_user_id)
            current_request = normalized_initial_request
            created = True
            request_updated = True

        if row and normalized_initial_request != current_request:
            if int(acting_user_id) != int(requested_by):
                raise ValueError("Solo el vendedor que solicitó el informe puede editar la solicitud inicial.")
            c.execute(
                """
                UPDATE informes_tecnicos
                SET solicitud_inicial = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (normalized_initial_request, int(informe_id)),
            )
            request_updated = True

        if normalized_comment:
            c.execute(
                """
                INSERT INTO informe_tecnico_comentarios (informe_id, comentario, created_by)
                VALUES (%s, %s, %s)
                """,
                (int(informe_id), normalized_comment, int(acting_user_id)),
            )
            comment_added = True

        docs_payload = _persist_uploaded_documents(informe_id, uploaded_files or [], acting_user_id)
        inserted_doc_ids = _append_documents_in_connection(conn, informe_id, docs_payload)

        selected_vigente_id = None
        if vigente_selection:
            token = str(vigente_selection).strip()
            if token.startswith("existing::"):
                selected_vigente_id = int(token.split("::", 1)[1])
            elif token.startswith("new::"):
                selected_name = token.split("::", 1)[1]
                for inserted_id, doc_payload in zip(inserted_doc_ids, docs_payload):
                    if str(doc_payload.get("filename") or "").strip() == str(selected_name).strip():
                        selected_vigente_id = int(inserted_id)
                        break
        elif inserted_doc_ids:
            selected_vigente_id = inserted_doc_ids[-1]

        if selected_vigente_id is not None:
            _set_vigente_document_in_connection(conn, informe_id, selected_vigente_id)

        if created or request_updated or comment_added or inserted_doc_ids:
            c.execute(
                """
                UPDATE informes_tecnicos
                SET estado = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (target_status, int(informe_id)),
            )
        else:
            raise ValueError("No hay cambios para enviar.")

        conn.commit()
        _clear_technical_reports_cache()

        detail_parts = []
        if created:
            detail_parts.append("Se creó la solicitud inicial del informe técnico.")
        elif request_updated:
            detail_parts.append("Se actualizó la solicitud inicial.")
        if comment_added:
            detail_parts.append(f"Nuevo comentario: {normalized_comment[:180]}")
        if inserted_doc_ids:
            detail_parts.append(f"Se adjuntaron {len(inserted_doc_ids)} archivo(s).")
        detail_text = " | ".join(detail_parts) or "Se registró una actualización en el informe técnico."
        event_key = "informe_tecnico_solicitado" if created else "informe_tecnico_actualizado"
        _queue_technical_report_notification(event_key, informe_id, project, requested_by, acting_user_id, detail_text)

        return {
            "report_id": int(informe_id),
            "created": created,
            "requested_by": int(requested_by),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _build_vigente_options(docs_df, uploaded_files):
    options = []
    current_index = 0
    if docs_df is not None and not docs_df.empty:
        for _, doc_row in docs_df.iterrows():
            doc_id = int(doc_row["id"])
            label = f"Actual: {doc_row['filename']}"
            if bool(doc_row.get("is_vigente")):
                current_index = len(options)
            options.append((f"existing::{doc_id}", label))
    for idx, uploaded_file in enumerate(uploaded_files or []):
        options.append((f"new::{uploaded_file.name}", f"Nuevo: {uploaded_file.name}"))
    if not options:
        return [], None, {}
    value_map = {label: value for value, label in options}
    labels = [label for _, label in options]
    default_label = labels[current_index] if 0 <= current_index < len(labels) else labels[0]
    return labels, default_label, value_map


def _build_technical_report_documents_display_df(docs_df):
    if docs_df is None or docs_df.empty:
        return pd.DataFrame()
    display_df = docs_df.copy().reset_index(drop=True)
    total = len(display_df.index)
    display_df["version_label"] = [f"{max(total - idx, 1)}" for idx in range(total)]
    display_df["vigente"] = display_df.get("is_vigente", pd.Series(dtype=bool)).apply(lambda value: "Si" if bool(value) else "")
    display_df["fecha"] = pd.to_datetime(display_df.get("created_at"), errors="coerce").dt.strftime("%d/%m/%Y %H:%M")
    return display_df


def _render_report_overview_card(project, report_row):
    trato = project.get("trato_id") or project.get("id") or "-"
    razon_social = _normalize_text(project.get("cliente_nombre") or project.get("marca_nombre")) or "-"
    descripcion = _normalize_text(project.get("descripcion")) or "Sin descripción"
    estado_trato = _normalize_text(project.get("estado")) or "-"
    solicitud = _normalize_text(report_row.get("solicitud_inicial")) if report_row else ""
    solicitud = solicitud or "Todavía no se cargó una solicitud."
    solicitante = _normalize_text(report_row.get("solicitante_nombre")) if report_row else ""
    solicitante = solicitante or "Pendiente"
    actualizado = _format_datetime_label(report_row.get("informe_updated_at")) if report_row else "-"
    estado_informe = _normalize_text(report_row.get("informe_estado")) if report_row else "Nuevo"
    estado_cls = _technical_report_status_class(estado_informe)

    st.markdown(
        f"""
        <style>
          .technical-detail-card {{
            margin: 0.15rem 0 1rem 0;
            padding: 1rem;
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.07);
            background: rgba(9, 12, 20, 0.92);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
          }}
          .technical-detail-head {{
            display:flex;
            justify-content:space-between;
            align-items:flex-start;
            gap:1rem;
            margin-bottom: 0.9rem;
          }}
          .technical-detail-eyebrow {{
            font-size:0.78rem;
            text-transform:uppercase;
            letter-spacing:0.08em;
            color:rgba(148,163,184,0.88);
            margin-bottom:0.22rem;
            font-weight:700;
          }}
          .technical-detail-title {{
            font-size:1.16rem;
            font-weight:700;
            line-height:1.25;
            margin-bottom:0.24rem;
          }}
          .technical-detail-meta {{
            color:rgba(226,232,240,0.74);
            font-size:0.92rem;
          }}
          .technical-detail-grid {{
            display:grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap:12px;
            margin: 0.9rem 0;
          }}
          .technical-detail-block {{
            background: rgba(255,255,255,0.07);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 0.85rem 0.9rem;
          }}
          .technical-detail-label {{
            font-size:0.76rem;
            text-transform:uppercase;
            letter-spacing:0.06em;
            color:rgba(148,163,184,0.84);
            margin-bottom:0.35rem;
            font-weight:700;
          }}
          .technical-detail-value {{
            font-size:1rem;
            font-weight:600;
            line-height:1.4;
            word-break:break-word;
          }}
          @media (max-width: 900px) {{
            .technical-detail-grid {{
              grid-template-columns: 1fr;
            }}
            .technical-detail-head {{
              flex-direction:column;
            }}
          }}
        </style>
        <div class="technical-detail-card">
          <div class="technical-detail-head">
            <div>
              <div class="technical-detail-eyebrow">Informe técnico</div>
              <div class="technical-detail-title">{html.escape(solicitud)}</div>
              <div class="technical-detail-meta">Trato {html.escape(str(trato))} • {html.escape(razon_social)} • Estado del trato: {html.escape(estado_trato)}</div>
            </div>
            <div><span class="technical-pill {estado_cls}">{html.escape(estado_informe)}</span></div>
          </div>
          <div class="technical-detail-grid">
            <div class="technical-detail-block">
              <div class="technical-detail-label">Trato</div>
              <div class="technical-detail-value">{html.escape(str(trato))}</div>
            </div>
            <div class="technical-detail-block">
              <div class="technical-detail-label">Razón social</div>
              <div class="technical-detail-value">{html.escape(razon_social)}</div>
            </div>
            <div class="technical-detail-block">
              <div class="technical-detail-label">Actualizado</div>
              <div class="technical-detail-value">{html.escape(actualizado)}</div>
            </div>
            <div class="technical-detail-block">
              <div class="technical-detail-label">Solicitó</div>
              <div class="technical-detail-value">{html.escape(solicitante)}</div>
            </div>
            <div class="technical-detail-block" style="grid-column: span 2;">
              <div class="technical-detail-label">Descripción del trato</div>
              <div class="technical-detail-value">{html.escape(descripcion)}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_project_technical_report_entry(user_id, project_id):
    project = get_proyecto(project_id)
    if not project:
        return
    report_row = get_technical_report(user_id=user_id, scope="commercial", project_id=project_id)
    project_open = is_project_open_status(project.get("estado"))
    button_label = "Ver informe técnico" if report_row else "Solicitar informe técnico"
    prefix = _scope_prefix("commercial")
    with st.container(border=True):
        info_col, action_col = st.columns([3.2, 1.3], vertical_alignment="center")
        with info_col:
            st.markdown("### Informe técnico")
            if report_row:
                updated_label = _format_datetime_label(report_row.get("informe_updated_at"))
                st.caption(
                    f"Asociado al trato {project.get('trato_id') or project_id}. "
                    f"Actualizado: {updated_label}. "
                    f"Comentarios: {int(report_row.get('comentarios_count') or 0)}. "
                    f"Adjuntos: {int(report_row.get('documentos_count') or 0)}."
                )
            elif project_open:
                st.caption("Solicita una consulta técnica formal asociada a este trato.")
            else:
                st.caption("El trato está cerrado y no tiene informe técnico asociado.")
        with action_col:
            if st.button(
                button_label,
                key=f"open_technical_report_from_project_{int(project_id)}",
                type="primary" if not report_row else "secondary",
                use_container_width=True,
                disabled=(not project_open and report_row is None),
            ):
                if report_row:
                    st.session_state[f"{prefix}_dialog_report_id"] = int(report_row.get("informe_id"))
                    st.session_state.pop(f"{prefix}_dialog_new_mode", None)
                    st.session_state.pop(f"{prefix}_dialog_project_id", None)
                else:
                    st.session_state[f"{prefix}_dialog_new_mode"] = True
                    st.session_state[f"{prefix}_dialog_project_id"] = int(project_id)
                    st.session_state.pop(f"{prefix}_dialog_report_id", None)
                st.query_params["ptab"] = "informes_tecnicos"
                safe_rerun()


def _render_comments_history(comments_df):
    st.markdown("**Comentarios**")
    if comments_df is None or comments_df.empty:
        st.caption("No hay comentarios registrados.")
        return

    items_html = []
    for _, row in comments_df.iterrows():
        author = html.escape(_format_user_name(row.get("autor_nombre"), "", row.get("autor_username")))
        fecha = html.escape(_format_datetime_label(row.get("created_at")))
        comentario = html.escape(str(row.get("comentario") or "-")).replace("\n", "<br>")
        items_html.append(
            textwrap.dedent(
                f"""
                <div class="technical-comment-item">
                  <div class="technical-comment-meta">
                    <span class="technical-comment-date">{fecha}</span>
                    <span class="technical-comment-author">{author}</span>
                  </div>
                  <div class="technical-comment-text">{comentario}</div>
                </div>
                """
            ).strip()
        )

    st.html(
        textwrap.dedent(
            f"""
            <style>
              body {{
                margin: 0;
                color: #f5f5f5;
                font-family: sans-serif;
              }}
              .technical-comments-scroll {{
                width: 100%;
                max-height: 320px;
                overflow-y: auto;
                padding-right: 8px;
                scrollbar-width: thin;
                scrollbar-color: rgba(160, 160, 160, 0.35) transparent;
              }}
              .technical-comments-scroll::-webkit-scrollbar {{
                width: 8px;
              }}
              .technical-comments-scroll::-webkit-scrollbar-track {{
                background: transparent;
              }}
              .technical-comments-scroll::-webkit-scrollbar-thumb {{
                background: rgba(160, 160, 160, 0.28);
                border-radius: 999px;
              }}
              .technical-comments-scroll::-webkit-scrollbar-thumb:hover {{
                background: rgba(160, 160, 160, 0.4);
              }}
              .technical-comment-item {{
                padding: 10px 0 12px 0;
                border-bottom: 1px solid rgba(128, 128, 128, 0.14);
              }}
              .technical-comment-item:last-child {{
                border-bottom: none;
                padding-bottom: 0;
              }}
              .technical-comment-meta {{
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                align-items: center;
                margin-bottom: 8px;
              }}
              .technical-comment-date {{
                display: inline-flex;
                align-items: center;
                padding: 2px 7px;
                border-radius: 6px;
                background: rgba(34, 197, 94, 0.08);
                color: #22c55e;
                font-family: monospace;
                font-size: 0.9rem;
              }}
              .technical-comment-author {{
                font-weight: 600;
              }}
              .technical-comment-text {{
                line-height: 1.5;
                word-break: break-word;
              }}
            </style>
            <div class="technical-comments-scroll">
              {''.join(items_html)}
            </div>
            """
        ).strip(),
        width="stretch",
    )


def _render_documents_section(docs_df, report_id):
    st.markdown("**Documentos adjuntos**")
    if docs_df is None or docs_df.empty:
        st.caption("No hay documentos cargados.")
        return

    display_df = _build_technical_report_documents_display_df(docs_df)
    st.dataframe(
        display_df[["version_label", "filename", "autor_nombre", "fecha", "vigente"]].rename(
            columns={
                "version_label": "Version",
                "filename": "Archivo",
                "autor_nombre": "Subido por",
                "fecha": "Fecha",
                "vigente": "Vigente",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    available_docs = []
    for _, row in display_df.iterrows():
        file_path = str(row.get("file_path") or "").strip()
        if not file_path or not os.path.exists(file_path):
            continue
        available_docs.append(row.to_dict())
    if not available_docs:
        st.caption("No se encontraron archivos disponibles para descargar.")
        return

    vigente_doc = next((doc for doc in available_docs if bool(doc.get("is_vigente"))), None)
    if vigente_doc is None and available_docs:
        vigente_doc = available_docs[0]

    if vigente_doc is not None:
        vigente_version = str(vigente_doc.get("version_label") or "Version").strip()
        vigente_name = str(vigente_doc.get("filename") or "Documento").strip()
        vigente_author = _format_user_name(vigente_doc.get("autor_nombre"), "", vigente_doc.get("autor_username"))
        vigente_date_label = _format_datetime_label(vigente_doc.get("created_at"))
        st.markdown(
            f"""
            <div style="
                margin: 0.35rem 0 0.85rem 0;
                padding: 0.9rem 1rem;
                border-radius: 12px;
                border: 1px solid rgba(34, 197, 94, 0.28);
                background: rgba(34, 197, 94, 0.08);
            ">
              <div style="display:flex; align-items:center; gap:0.55rem; margin-bottom:0.45rem;">
                <span style="
                    display:inline-flex;
                    align-items:center;
                    justify-content:center;
                    padding:0.18rem 0.62rem;
                    border-radius:999px;
                    background:rgba(34, 197, 94, 0.16);
                    border:1px solid rgba(34, 197, 94, 0.3);
                    color:#34d399;
                    font-size:0.78rem;
                    font-weight:700;
                ">Vigente</span>
                <span style="font-weight:700;">{html.escape(vigente_version)}</span>
              </div>
              <div style="font-size:1rem; font-weight:600; margin-bottom:0.3rem; word-break:break-word;">
                {html.escape(vigente_name)}
              </div>
              <div style="opacity:0.78; font-size:0.86rem;">
                Subido por {html.escape(vigente_author)} • {html.escape(vigente_date_label)}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    selector_options = [doc["id"] for doc in available_docs]
    selected_doc_id = st.selectbox(
        "Version para descargar",
        options=selector_options,
        format_func=lambda doc_id: next(
            (
                f"{doc.get('version_label') or 'Version'} - {doc.get('filename') or 'Documento'}"
            )
            for doc in available_docs
            if int(doc.get("id")) == int(doc_id)
        ),
        key=f"technical_report_doc_selector_{int(report_id or 0)}",
    )
    selected_doc = next(doc for doc in available_docs if int(doc.get("id")) == int(selected_doc_id))

    if bool(selected_doc.get("is_vigente")):
        st.caption("Estas por descargar el documento vigente.")

    download_cols = st.columns([1, 1.1, 2])
    with download_cols[0]:
        with open(str(selected_doc.get("file_path")), "rb") as file_obj:
            st.download_button(
                "Descargar archivo",
                data=file_obj.read(),
                file_name=selected_doc.get("filename") or "informe_tecnico",
                key=f"technical_report_dl_{selected_doc.get('id')}",
                use_container_width=True,
            )
    with download_cols[1]:
        if len(available_docs) > 1:
            st.download_button(
                "Descargar todo",
                data=_documents_zip_bytes(pd.DataFrame(available_docs)),
                file_name="informe_tecnico_adjuntos.zip",
                mime="application/zip",
                key=f"technical_report_dl_all_{int(report_id or 0)}",
                use_container_width=True,
            )


def _clear_report_dialog_state(scope):
    prefix = _scope_prefix(scope)
    for key in [
        f"{prefix}_dialog_report_id",
        f"{prefix}_dialog_new_mode",
        f"{prefix}_dialog_project_id",
        f"{prefix}_dialog_selector_project_id",
    ]:
        st.session_state.pop(key, None)


def _render_report_editor(user_id, project_id, scope, close_after_submit=False):
    project = get_proyecto(project_id)
    if not project:
        st.error("No se encontró el trato seleccionado.")
        return

    report_row = get_technical_report(user_id=user_id, scope=scope, project_id=project_id)
    report_exists = report_row is not None
    project_open = is_project_open_status(project.get("estado"))
    report_id = int(report_row.get("informe_id")) if report_row else None
    comments_df = get_technical_report_comments_df(report_id) if report_id else pd.DataFrame()
    docs_df = get_technical_report_documents_df(report_id) if report_id else pd.DataFrame()

    requested_by = int(report_row.get("requested_by")) if report_row and report_row.get("requested_by") is not None else None
    can_edit_initial_request = bool(project_open and scope == "commercial" and not report_exists)
    can_submit = bool(project_open and (scope == "technical_admin" or scope == "commercial"))

    if report_exists:
        _render_report_overview_card(project, report_row)
    elif not project_open:
        st.info("El trato está cerrado y no tiene informe técnico. No se puede crear uno nuevo.")
        return
    else:
        _render_report_overview_card(project, None)

    _render_comments_history(comments_df)
    _render_documents_section(docs_df, report_id)

    form_key = f"{_scope_prefix(scope)}_form_{int(project_id)}"
    default_initial = report_row.get("solicitud_inicial") if report_row else ""
    with st.form(form_key):
        initial_request = default_initial
        if not report_exists:
            initial_request = st.text_input(
                "Título de la solicitud",
                value=default_initial,
                disabled=not can_edit_initial_request,
                placeholder="Ej. Horas adicionales, Consulta técnica, Validación de alcance...",
            )
        comment = st.text_area(
            "Comentarios",
            value="",
            height=120,
            disabled=not can_submit,
            help="Cada comentario queda registrado con usuario, fecha y hora.",
        )
        uploaded_files = st.file_uploader(
            "Adjuntar informe",
            accept_multiple_files=True,
            type=["pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg"],
            key=f"{form_key}_upload",
            disabled=not can_submit,
        )
        vigente_options, vigente_default, vigente_values = _build_vigente_options(docs_df, uploaded_files)
        vigente_selection = None
        if vigente_options:
            vigente_label = st.radio(
                "Indicar cuál es la vigente",
                options=vigente_options,
                index=vigente_options.index(vigente_default) if vigente_default in vigente_options else 0,
                disabled=not can_submit,
            )
            vigente_selection = vigente_values.get(vigente_label)
        action_col_1, action_col_2 = st.columns(2)
        close_clicked = action_col_1.form_submit_button("Cerrar", use_container_width=True)
        send_clicked = action_col_2.form_submit_button("Enviar", type="primary", use_container_width=True, disabled=not can_submit)

    if close_clicked:
        _clear_report_dialog_state(scope)
        safe_rerun()
        return

    if send_clicked:
        try:
            result = save_technical_report_submission(
                project_id=project_id,
                acting_user_id=user_id,
                scope=scope,
                initial_request=initial_request,
                comment=comment,
                uploaded_files=uploaded_files,
                vigente_selection=vigente_selection,
            )
            message = "Informe técnico solicitado correctamente." if result.get("created") else "Informe técnico actualizado correctamente."
            st.success(message)
            if close_after_submit:
                _clear_report_dialog_state(scope)
            safe_rerun()
        except Exception as exc:
            st.error(str(exc))


def _technical_report_status_class(value):
    normalized = _normalize_text(value).lower()
    if normalized == "enviado":
        return "sent"
    return "requested"


def _render_technical_report_summary_card(row, scope):
    inject_project_card_css()
    project_id = int(row.get("proyecto_id") or 0)
    report_id = int(row.get("informe_id") or 0)
    trato = int(row.get("trato_id") or project_id or 0)
    titulo = str(row.get("solicitud_inicial") or row.get("trato_titulo") or "Sin titulo").strip() or "Sin titulo"
    cliente = _normalize_text(row.get("cliente_nombre") or row.get("marca_nombre")) or "-"
    solicitante = _normalize_text(row.get("solicitante_nombre")) or "-"
    vendedor = _normalize_text(row.get("vendedor_nombre")) or "-"
    updated_at = _format_datetime_label(row.get("informe_updated_at"))
    estado_informe = _normalize_text(row.get("informe_estado")) or "Solicitado"
    comentarios = int(pd.to_numeric(pd.Series([row.get("comentarios_count")]), errors="coerce").fillna(0).iloc[0])
    adjuntos = int(pd.to_numeric(pd.Series([row.get("documentos_count")]), errors="coerce").fillna(0).iloc[0])
    vigente = _normalize_text(row.get("vigente_filename")) or "Sin documento vigente"
    estado_cls = _technical_report_status_class(row.get("informe_estado"))
    open_param_name = f"{_scope_prefix(scope)}_open_report"

    def _html_escape(value):
        return html.escape(str(value or "-"))

    preserved_params_html = ""
    preserved_inputs = []
    for key, value in st.query_params.items():
        if key == open_param_name:
            continue
        values = value if isinstance(value, list) else [value]
        for entry in values:
            preserved_inputs.append(
                f'<input type="hidden" name="{_html_escape(key)}" value="{_html_escape(entry)}" />'
            )
    preserved_params_html = "".join(preserved_inputs)
    hidden_open = f'<input type="hidden" name="{_html_escape(open_param_name)}" value="{report_id}" />'

    st.html(
        f"""
        <style>
          .technical-report-card-wrap {{
            margin: 10px 0 14px 0;
          }}
          .technical-report-card-wrap .card-form {{
            display: block;
            text-decoration: none;
            position: relative;
          }}
          .technical-report-card-wrap .card-submit {{
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            opacity: 0;
            cursor: pointer;
            border: 0;
            background: transparent;
            padding: 0;
            margin: 0;
            z-index: 2;
          }}
          .technical-report-card {{
            border: 1px solid rgba(148, 163, 184, 0.20);
            border-radius: 14px;
            padding: 16px 18px;
            background: rgba(15, 23, 42, 0.30);
            cursor: pointer;
            position: relative;
            z-index: 1;
          }}
          .technical-report-card:hover {{
            border-color: rgba(96, 165, 250, 0.35);
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.22);
          }}
          .technical-report-card .head {{
            display:flex;
            justify-content:space-between;
            gap:16px;
            align-items:flex-start;
          }}
          .technical-report-card .title {{
            font-size: 1.08rem;
            font-weight: 700;
            line-height: 1.35;
          }}
          .technical-report-card .meta {{
            margin-top: 4px;
            opacity: 0.78;
            font-size: 0.92rem;
          }}
          .technical-report-card .grid {{
            display:grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap:12px;
            margin-top: 14px;
          }}
          .technical-report-card .block {{
            background: rgba(128, 128, 128, 0.08);
            border-radius: 10px;
            padding: 12px 14px;
          }}
          .technical-report-card .label {{
            font-size: 0.82rem;
            opacity: 0.72;
            margin-bottom: 4px;
          }}
          .technical-report-card .value {{
            font-size: 0.95rem;
            font-weight: 600;
            line-height: 1.35;
            word-break: break-word;
          }}
          .technical-pill {{
            display:inline-flex;
            align-items:center;
            justify-content:center;
            min-height:28px;
            padding: 0.2rem 0.65rem;
            border-radius:999px;
            border:1px solid rgba(148,163,184,0.25);
            font-size:0.78rem;
            font-weight:700;
            white-space:nowrap;
          }}
          .technical-pill.requested {{
            background: rgba(234, 179, 8, 0.12);
            color: #facc15;
            border-color: rgba(234, 179, 8, 0.3);
          }}
          .technical-pill.sent {{
            background: rgba(34, 197, 94, 0.12);
            color: #34d399;
            border-color: rgba(34, 197, 94, 0.3);
          }}
          @media (max-width: 1100px) {{
            .technical-report-card .grid {{
              grid-template-columns: 1fr;
            }}
          }}
        </style>
        <div class="technical-report-card-wrap">
          <form method="get" class="card-form">
            {preserved_params_html}
            {hidden_open}
            <button type="submit" class="card-submit"></button>
            <div class="technical-report-card">
              <div class="head">
                <div>
                  <div class="title">{html.escape(titulo)}</div>
                  <div class="meta">Trato {trato} • {html.escape(cliente)}</div>
                </div>
                <div>
                  <span class="technical-pill {estado_cls}">{html.escape(estado_informe)}</span>
                </div>
              </div>
              <div class="grid">
                <div class="block">
                  <div class="label">Solicitó</div>
                  <div class="value">{html.escape(solicitante)}</div>
                </div>
                <div class="block">
                  <div class="label">Vendedor</div>
                  <div class="value">{html.escape(vendedor)}</div>
                </div>
                <div class="block">
                  <div class="label">Actualizado</div>
                  <div class="value">{html.escape(updated_at)}</div>
                </div>
                <div class="block">
                  <div class="label">Comentarios</div>
                  <div class="value">{comentarios}</div>
                </div>
                <div class="block">
                  <div class="label">Adjuntos</div>
                  <div class="value">{adjuntos}</div>
                </div>
                <div class="block">
                  <div class="label">Vigente</div>
                  <div class="value">{html.escape(vigente)}</div>
                </div>
              </div>
            </div>
          </form>
          </div>
        </div>
        """,
        width="stretch",
    )


def _render_report_dialog(user_id, scope, report_id=None, default_project_id=None, lock_project_selection=False):
    title = "Solicitar informe técnico"
    if report_id is not None:
        report_row = get_technical_report(user_id=user_id, scope=scope, report_id=report_id)
        if report_row:
            report_title = _normalize_text(report_row.get("solicitud_inicial"))
            title = report_title or "Informe técnico"

    @st.dialog(title, width="large")
    def _dialog():
        selected_project_id = default_project_id
        if report_id is not None:
            report_row = get_technical_report(user_id=user_id, scope=scope, report_id=report_id)
            if not report_row:
                st.error("No se encontró el informe técnico seleccionado.")
                if st.button("Cerrar", use_container_width=True):
                    _clear_report_dialog_state(scope)
                    safe_rerun()
                return
            selected_project_id = int(report_row.get("proyecto_id"))
        elif scope == "commercial":
            visible_projects = _get_visible_projects(user_id, scope=scope, only_open=True)
            if visible_projects.empty:
                st.info("No tienes tratos abiertos disponibles para solicitar informes técnicos.")
                if st.button("Cerrar", use_container_width=True):
                    _clear_report_dialog_state(scope)
                    safe_rerun()
                return
            project_ids = [int(value) for value in visible_projects["id"].dropna().tolist()]
            if selected_project_id not in project_ids:
                selected_project_id = project_ids[0]
            selector_key = f"{_scope_prefix(scope)}_dialog_selector_project_id"
            if not lock_project_selection:
                selected_project_id = st.selectbox(
                    "Trato",
                    options=project_ids,
                    index=project_ids.index(selected_project_id) if selected_project_id in project_ids else 0,
                    format_func=lambda value: _project_option_label(
                        visible_projects.loc[visible_projects["id"] == int(value)].iloc[0].to_dict()
                    ),
                    key=selector_key,
                )
        _render_report_editor(user_id, int(selected_project_id), scope, close_after_submit=True)

    _dialog()


def render_technical_reports_workspace(user_id, scope="commercial", title=None):
    ensure_technical_reports_schema()
    title = title or _scope_prefix(scope)
    prefix = _scope_prefix(scope)
    open_param_name = f"{prefix}_open_report"
    pending_open_report = st.query_params.get(open_param_name)
    if pending_open_report:
        try:
            st.session_state[f"{prefix}_dialog_report_id"] = int(pending_open_report)
            st.session_state.pop(f"{prefix}_dialog_new_mode", None)
            st.session_state.pop(f"{prefix}_dialog_project_id", None)
            st.query_params.pop(open_param_name, None)
            safe_rerun()
        except Exception:
            pass
    section_title = "Consulta Informes Técnicos" if scope == "commercial" else "Seguimiento informe"
    st.subheader(section_title)
    reports_df = get_technical_reports_dataframe(user_id=user_id, scope=scope)

    create_col, _ = st.columns([0.24, 0.76])
    with create_col:
        if scope == "commercial":
            if st.button(
                "➕ Solicitar informe",
                key=f"{prefix}_new_report_btn",
                type="primary",
                use_container_width=False,
            ):
                st.session_state[f"{prefix}_dialog_new_mode"] = True
                st.session_state.pop(f"{prefix}_dialog_report_id", None)
                st.session_state.pop(f"{prefix}_dialog_project_id", None)
                safe_rerun()

    if reports_df.empty:
        reports_df = pd.DataFrame(
            columns=[
                "informe_id",
                "proyecto_id",
                "trato_id",
                "cliente_nombre",
                "marca_nombre",
                "trato_titulo",
                "informe_estado",
                "solicitante_nombre",
                "vendedor_nombre",
                "comentarios_count",
                "documentos_count",
                "vigente_filename",
                "informe_updated_at",
            ]
        )
    else:
        reports_df = reports_df.copy()

    reports_df["_client_filter"] = reports_df["cliente_nombre"].fillna(reports_df["marca_nombre"]).fillna("")
    unique_clients = sorted([value for value in reports_df.get("_client_filter", pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()])
    estado_options = sorted([value for value in reports_df.get("informe_estado", pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()])

    filter_cols = st.columns([1.2, 2, 2.4, 1.7, 1.5])
    with filter_cols[0]:
        filtro_id_raw = st.text_input("ID de trato", value="", key=f"{prefix}_filter_id_text")
        filtro_id = None
        try:
            filtro_id_str = str(filtro_id_raw or "").strip()
            if filtro_id_str:
                filtro_id = int(filtro_id_str)
        except Exception:
            filtro_id = None
    with filter_cols[1]:
        sel_cliente = st.selectbox("Cliente", options=["Todos"] + unique_clients, key=f"{prefix}_filter_cliente")
        filtro_cliente = sel_cliente if sel_cliente != "Todos" else ""
    with filter_cols[2]:
        filtro_nombre = st.text_input("Nombre del trato", value="", key=f"{prefix}_filter_nombre")
    with filter_cols[3]:
        filtro_estados = st.multiselect("Estado", options=estado_options, key=f"{prefix}_filter_estado_multi")
    with filter_cols[4]:
        ordenar_por = st.selectbox("Ordenar por", ["Más recientes", "Más antiguos"], key=f"{prefix}_sort_option")

    filtered_df = reports_df.copy()
    if filtro_id is not None:
        trato_series = filtered_df.get("trato_id").fillna(filtered_df.get("proyecto_id"))
        try:
            filtered_df = filtered_df[trato_series.astype("Int64") == int(filtro_id)]
        except Exception:
            filtered_df = filtered_df[trato_series.astype(str) == str(filtro_id)]
    if filtro_cliente:
        filtered_df = filtered_df[filtered_df.get("_client_filter", pd.Series(dtype=str)).fillna("") == filtro_cliente]
    if filtro_nombre:
        titulo_series = filtered_df.get("trato_titulo", pd.Series(dtype=str)).fillna("")
        filtered_df = filtered_df[titulo_series.str.contains(filtro_nombre, case=False, na=False)]
    if filtro_estados:
        filtered_df = filtered_df[filtered_df.get("informe_estado", pd.Series(dtype=str)).fillna("").isin(filtro_estados)]

    sort_updated = pd.to_datetime(filtered_df.get("informe_updated_at"), errors="coerce")
    filtered_df = (
        filtered_df.assign(_sort_updated=sort_updated)
        .sort_values(["_sort_updated", "informe_id"], ascending=[ordenar_por != "Más recientes", ordenar_por != "Más recientes"], na_position="last")
        .drop(columns=["_sort_updated"], errors="ignore")
    )

    if filtered_df.empty:
        st.info("No hay informes técnicos que coincidan con los filtros." if not reports_df.empty else "No hay informes técnicos registrados.")
    else:
        page_key = f"{prefix}_page"
        page_size_key = f"{prefix}_page_size"
        page_size_options = [5, 10, 15, 20, 30]
        if page_size_key not in st.session_state:
            st.session_state[page_size_key] = 10
        if st.session_state.get(page_size_key) not in page_size_options:
            st.session_state[page_size_key] = 10

        def on_page_size_change():
            st.session_state[page_key] = 1

        page_size = int(st.session_state.get(page_size_key, 10) or 10)
        total_items = len(filtered_df)
        page = int(st.session_state.get(page_key, 1) or 1)
        total_pages = max((total_items + page_size - 1) // page_size, 1)
        page = max(1, min(page, total_pages))
        st.session_state[page_key] = page

        start = (page - 1) * page_size
        end = start + page_size
        df_page = filtered_df.iloc[start:end]

        for _, row in df_page.iterrows():
            _render_technical_report_summary_card(row.to_dict(), scope=scope)

        count_text = f"Mostrando elementos {start + 1}-{min(end, total_items)} de {total_items}"
        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
        col_ps, col_text, col_spacer, col_prev, col_next = st.columns([0.7, 3.2, 3.1, 1, 1])
        with col_ps:
            st.selectbox(
                "filas / pagina",
                options=page_size_options,
                key=page_size_key,
                label_visibility="collapsed",
                on_change=on_page_size_change,
            )
        with col_text:
            st.markdown(
                f"<div style='display:flex; align-items:center; height:100%; color:#888; margin-top:6px;'>{count_text}</div>",
                unsafe_allow_html=True,
            )
        with col_prev:
            if st.button("Anterior", key=f"{prefix}_prev_page", disabled=(page <= 1), use_container_width=True):
                st.session_state[page_key] = page - 1
                safe_rerun()
        with col_next:
            if st.button("Siguiente", key=f"{prefix}_next_page", disabled=(page >= total_pages), use_container_width=True):
                st.session_state[page_key] = page + 1
                safe_rerun()

    dialog_report_id = st.session_state.get(f"{prefix}_dialog_report_id")
    dialog_new_mode = bool(st.session_state.get(f"{prefix}_dialog_new_mode"))
    dialog_project_id = st.session_state.get(f"{prefix}_dialog_project_id")
    if dialog_report_id:
        _render_report_dialog(user_id, scope, report_id=int(dialog_report_id))
    elif dialog_new_mode and scope == "commercial":
        _render_report_dialog(
            user_id,
            scope,
            report_id=None,
            default_project_id=int(dialog_project_id) if dialog_project_id is not None else None,
            lock_project_selection=dialog_project_id is not None,
        )
