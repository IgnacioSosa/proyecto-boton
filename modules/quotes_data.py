import os
from datetime import datetime

import pandas as pd
from sqlalchemy import text

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


QUOTE_STATUS_OPTIONS = ["Solicitado", "Enviado", "Cancelado / Cerrado"]
QUOTE_ACTIVE_STATUS = {"solicitado", "enviado"}
PROJECT_CLOSED_STATUS = {"ganado", "perdido", "cerrado", "cancelado / cerrado"}


def _normalize_status(value):
    return str(value or "").strip().lower()


def is_project_open_status(value):
    return _normalize_status(value) not in PROJECT_CLOSED_STATUS


def is_quote_editable_status(value):
    return _normalize_status(value) in QUOTE_ACTIVE_STATUS


def ensure_quotes_schema():
    ensure_projects_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS cotizaciones (
                id SERIAL PRIMARY KEY,
                proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
                requested_by INTEGER NOT NULL REFERENCES usuarios(id),
                assigned_to INTEGER NULL REFERENCES usuarios(id),
                serie_num INTEGER,
                marca_id INTEGER NULL REFERENCES marcas(id_marca),
                estado VARCHAR(50) NOT NULL DEFAULT 'Solicitado',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        try:
            c.execute("ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS serie_num INTEGER")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS marca_id INTEGER")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE cotizaciones DROP CONSTRAINT IF EXISTS cotizaciones_marca_fk")
        except Exception:
            pass
        try:
            c.execute(
                """
                ALTER TABLE cotizaciones
                ADD CONSTRAINT cotizaciones_marca_fk
                FOREIGN KEY (marca_id) REFERENCES marcas(id_marca) ON DELETE SET NULL
                """
            )
        except Exception:
            pass
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS cotizacion_items (
                id SERIAL PRIMARY KEY,
                cotizacion_id INTEGER NOT NULL REFERENCES cotizaciones(id) ON DELETE CASCADE,
                cantidad NUMERIC(12, 2) NOT NULL,
                sku VARCHAR(120),
                modelo VARCHAR(200),
                descripcion TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS cotizacion_comentarios (
                id SERIAL PRIMARY KEY,
                cotizacion_id INTEGER NOT NULL REFERENCES cotizaciones(id) ON DELETE CASCADE,
                comentario TEXT NOT NULL,
                created_by INTEGER NULL REFERENCES usuarios(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS cotizacion_documentos (
                id SERIAL PRIMARY KEY,
                cotizacion_id INTEGER NOT NULL REFERENCES cotizaciones(id) ON DELETE CASCADE,
                filename VARCHAR(255) NOT NULL,
                file_path TEXT NOT NULL,
                mime_type VARCHAR(100),
                file_size BIGINT,
                uploaded_by INTEGER NULL REFERENCES usuarios(id),
                is_vigente BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS cotizacion_alertas_vistas (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                cotizacion_id INTEGER NOT NULL REFERENCES cotizaciones(id) ON DELETE CASCADE,
                seen_quote_updated_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, cotizacion_id, seen_quote_updated_at)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS notificacion_toasts_diarios (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                alert_key VARCHAR(120) NOT NULL,
                shown_on DATE NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, alert_key, shown_on)
            )
            """
        )
        try:
            c.execute("ALTER TABLE cotizaciones DROP CONSTRAINT IF EXISTS cotizaciones_estado_check")
        except Exception:
            pass
        try:
            c.execute(
                """
                ALTER TABLE cotizaciones
                ADD CONSTRAINT cotizaciones_estado_check
                CHECK (estado IN ('Solicitado', 'Enviado', 'Cancelado / Cerrado'))
                """
            )
        except Exception:
            pass
        for ddl in [
            "CREATE INDEX IF NOT EXISTS idx_cotizaciones_proyecto_id ON cotizaciones(proyecto_id)",
            "CREATE INDEX IF NOT EXISTS idx_cotizaciones_requested_by ON cotizaciones(requested_by)",
            "CREATE INDEX IF NOT EXISTS idx_cotizaciones_marca_id ON cotizaciones(marca_id)",
            "CREATE INDEX IF NOT EXISTS idx_cotizacion_items_cotizacion_id ON cotizacion_items(cotizacion_id)",
            "CREATE INDEX IF NOT EXISTS idx_cotizacion_comentarios_cotizacion_id ON cotizacion_comentarios(cotizacion_id)",
            "CREATE INDEX IF NOT EXISTS idx_cotizacion_documentos_cotizacion_id ON cotizacion_documentos(cotizacion_id)",
            "CREATE INDEX IF NOT EXISTS idx_cotizacion_alertas_vistas_user_id ON cotizacion_alertas_vistas(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_notificacion_toasts_diarios_user_day ON notificacion_toasts_diarios(user_id, shown_on)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_cotizaciones_project_series_unique ON cotizaciones(proyecto_id, serie_num) WHERE serie_num IS NOT NULL",
        ]:
            try:
                c.execute(ddl)
            except Exception:
                pass
        try:
            c.execute(
                """
                WITH numbered AS (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY proyecto_id
                            ORDER BY created_at ASC NULLS LAST, id ASC
                        ) AS new_serie_num
                    FROM cotizaciones
                )
                UPDATE cotizaciones q
                SET serie_num = numbered.new_serie_num
                FROM numbered
                WHERE q.id = numbered.id
                  AND q.serie_num IS NULL
                """
            )
        except Exception:
            pass
        try:
            c.execute(
                """
                UPDATE cotizaciones q
                SET marca_id = p.marca_id
                FROM proyectos p
                WHERE p.id = q.proyecto_id
                  AND q.marca_id IS NULL
                """
            )
        except Exception:
            pass
        try:
            c.execute(
                """
                UPDATE cotizaciones
                SET assigned_to = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE assigned_to IS NOT NULL
                """
            )
        except Exception:
            pass
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log_sql_error(f"Error asegurando esquema de cotizaciones: {exc}")
    finally:
        conn.close()


def get_purchase_users_df():
    ensure_quotes_schema()
    engine = get_engine()
    try:
        return pd.read_sql_query(
            text(
                """
                SELECT u.id, u.username, u.nombre, u.apellido, u.email
                FROM usuarios u
                JOIN roles r ON u.rol_id = r.id_rol
                WHERE u.is_active = TRUE
                  AND COALESCE(r.view_type, '') = 'compras'
                ORDER BY u.apellido, u.nombre, u.username
                """
            ),
            con=engine,
        )
    except Exception as exc:
        log_sql_error(f"Error listando usuarios de compras: {exc}")
        return pd.DataFrame()


def get_quote_assignee_users_df():
    ensure_quotes_schema()
    engine = get_engine()
    try:
        return pd.read_sql_query(
            text(
                """
                SELECT
                    u.id,
                    u.username,
                    u.nombre,
                    u.apellido,
                    u.email,
                    COALESCE(r.view_type, '') AS view_type,
                    COALESCE(r.nombre, '') AS rol_nombre
                FROM usuarios u
                JOIN roles r ON u.rol_id = r.id_rol
                WHERE u.is_active = TRUE
                  AND COALESCE(r.view_type, '') IN ('compras', 'admin_comercial')
                ORDER BY
                    CASE
                        WHEN COALESCE(r.view_type, '') = 'compras' THEN 0
                        ELSE 1
                    END,
                    u.apellido,
                    u.nombre,
                    u.username
                """
            ),
            con=engine,
        )
    except Exception as exc:
        log_sql_error(f"Error listando destinatarios de cotización: {exc}")
        return pd.DataFrame()


def _resolve_quote_assigned_to(assigned_to=None, require_available=True, allow_group_assignment=False):
    assignee_users = get_quote_assignee_users_df()
    if not allow_group_assignment:
        if require_available and assignee_users.empty:
            raise ValueError("No hay usuarios activos de Compras o adm_comercial para recibir la solicitud.")

    assignee_options = {
        int(row["id"]): row
        for _, row in assignee_users.iterrows()
        if pd.notna(row.get("id"))
    }
    if assigned_to is not None and str(assigned_to).strip():
        try:
            selected_assigned_to = int(assigned_to)
        except Exception as exc:
            raise ValueError("El destinatario seleccionado para la cotización no es válido.") from exc
        if assignee_options and selected_assigned_to not in assignee_options:
            raise ValueError("El destinatario seleccionado para la cotización no es válido.")
        return selected_assigned_to

    if allow_group_assignment:
        return None

    if assignee_options:
        return int(next(iter(assignee_options.keys())))
    return None


def get_visible_quote_projects(user_id, scope="commercial", only_open=False):
    ensure_quotes_schema()
    try:
        if scope in {"admin_comercial", "compras"}:
            df = get_all_proyectos()
        else:
            own_df = get_proyectos_by_owner(user_id)
            shared_df = get_proyectos_shared_with_user(user_id)
            frames = [frame for frame in [own_df, shared_df] if frame is not None and not frame.empty]
            if frames:
                df = pd.concat(frames, ignore_index=True)
            else:
                df = pd.DataFrame()
        if df.empty:
            return df
        df = df.drop_duplicates(subset=["id"]).copy()
        if only_open and "estado" in df.columns:
            df = df[df["estado"].apply(is_project_open_status)]
        if "created_at" in df.columns:
            df = df.sort_values("created_at", ascending=False, na_position="last")
        if "id" in df.columns:
            df = df.sort_values("id", ascending=False, na_position="last")
        return df
    except Exception as exc:
        log_sql_error(f"Error obteniendo tratos visibles para cotizaciones: {exc}")
        return pd.DataFrame()


def _sanitize_quote_items(items):
    sanitized = []
    for raw in items or []:
        cantidad_raw = str(raw.get("cantidad") or "").strip()
        sku = str(raw.get("sku") or "").strip()
        modelo = str(raw.get("modelo") or "").strip()
        descripcion = str(raw.get("descripcion") or "").strip()
        if not cantidad_raw and not sku and not modelo and not descripcion:
            continue
        try:
            cantidad = float(str(cantidad_raw).replace(",", "."))
        except Exception as exc:
            raise ValueError("La cantidad debe ser numérica.") from exc
        if cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor a cero.")
        if not any([sku, modelo, descripcion]):
            raise ValueError("Cada ítem debe tener al menos SKU, modelo o descripción.")
        sanitized.append(
            {
                "cantidad": cantidad,
                "sku": sku,
                "modelo": modelo,
                "descripcion": descripcion,
            }
        )
    if not sanitized:
        raise ValueError("Debes cargar al menos un ítem en la cotización.")
    return sanitized


def _visible_project_ids(user_id, scope="commercial", only_open=False):
    df = get_visible_quote_projects(user_id, scope=scope, only_open=only_open)
    if df.empty or "id" not in df.columns:
        return set()
    return {int(value) for value in df["id"].dropna().tolist()}


def _next_quote_series_num_in_connection(conn, proyecto_id):
    c = conn.cursor()
    c.execute(
        "SELECT COALESCE(MAX(serie_num), 0) + 1 FROM cotizaciones WHERE proyecto_id = %s",
        (int(proyecto_id),),
    )
    row = c.fetchone()
    try:
        return max(1, int(row[0] or 1))
    except Exception:
        return 1


def _annotate_quote_document_versions(df):
    if df is None or df.empty:
        return df
    out = df.copy()
    out["_created_at_sort"] = pd.to_datetime(out.get("created_at"), errors="coerce")
    ordered_idx = (
        out.assign(_created_at_fallback=out["_created_at_sort"])
        .sort_values(["_created_at_fallback", "id"], ascending=[True, True], na_position="last")
        .index.tolist()
    )
    version_map = {row_idx: pos + 1 for pos, row_idx in enumerate(ordered_idx)}
    out["version_num"] = [version_map.get(idx) for idx in out.index]
    def _version_suffix(value):
        try:
            num = int(value)
        except Exception:
            return ""
        if num <= 0:
            return ""
        letters = ""
        while num > 0:
            num -= 1
            letters = chr(ord("a") + (num % 26)) + letters
            num //= 26
        return letters

    series_num = pd.to_numeric(out.get("serie_num"), errors="coerce")
    out["version_label"] = [
        f"{int(serie)}{_version_suffix(version)}"
        if pd.notna(serie) and pd.notna(version)
        else (f"Version {int(version)}" if pd.notna(version) else "Version")
        for serie, version in zip(series_num, out["version_num"])
    ]
    return out.drop(columns=["_created_at_sort"], errors="ignore")


def _queue_quote_request_notification(cotizacion_id, requested_by, project, assigned_to=None, detail_suffix="", dedupe_key=None):
    try:
        detail_base = project.get("titulo") or project.get("descripcion") or ""
        detail = detail_base
        if str(detail_suffix or "").strip():
            detail = f"{detail_base} | {str(detail_suffix).strip()}" if detail_base else str(detail_suffix).strip()
        queue_notification_event(
            "cotizacion_solicitada",
            {
                "cotizacion_id": int(cotizacion_id),
                "requested_by": int(requested_by),
                "assigned_to": int(assigned_to) if assigned_to is not None else None,
                "cliente": project.get("cliente_nombre") or "-",
                "cuit": "",
                "trato": project.get("trato_id") or project.get("id") or "-",
                "tipo_venta": project.get("tipo_venta") or "-",
                "detalle": detail,
                "estado": "Solicitado",
            },
            dedupe_key=dedupe_key or f"cotizacion_solicitada:{int(cotizacion_id)}",
        )
    except Exception as exc:
        log_sql_error(f"No se pudo encolar notificación de cotización solicitada: {exc}")


def _queue_quote_sent_notification(cotizacion_id, requested_by, acted_by, project, detail_suffix="", dedupe_key=None):
    try:
        detail_base = project.get("titulo") or project.get("descripcion") or ""
        detail = detail_base
        if str(detail_suffix or "").strip():
            detail = f"{detail_base} | {str(detail_suffix).strip()}" if detail_base else str(detail_suffix).strip()
        queue_notification_event(
            "cotizacion_enviada",
            {
                "cotizacion_id": int(cotizacion_id),
                "requested_by": int(requested_by),
                "aprobador": project.get("compras_nombre") or project.get("comprador_nombre") or "Compras",
                "acted_by": int(acted_by),
                "cliente": project.get("cliente_nombre") or "-",
                "cuit": "",
                "trato": project.get("trato_id") or project.get("id") or "-",
                "tipo_venta": project.get("tipo_venta") or "-",
                "detalle": detail,
                "estado": "Enviado",
            },
            dedupe_key=dedupe_key or f"cotizacion_enviada:{int(cotizacion_id)}",
        )
    except Exception as exc:
        log_sql_error(f"No se pudo encolar notificación de cotización enviada: {exc}")


def get_cotizaciones_dataframe(user_id, scope="commercial"):
    ensure_quotes_schema()
    engine = get_engine()
    try:
        df = pd.read_sql_query(
            text(
                """
                SELECT
                    q.id AS cotizacion_id,
                    q.proyecto_id,
                    q.requested_by,
                    q.assigned_to,
                    q.serie_num AS cotizacion_serie,
                    q.marca_id AS cotizacion_marca_id,
                    q.estado AS cotizacion_estado,
                    q.created_at AS cotizacion_created_at,
                    q.updated_at AS cotizacion_updated_at,
                    p.id AS proyecto_id_real,
                    p.trato_id,
                    p.titulo AS trato_titulo,
                    p.descripcion AS trato_descripcion,
                    p.estado AS trato_estado,
                    p.tipo_venta,
                    p.fecha_cierre,
                    COALESCE(mq.nombre, m.nombre) AS marca_nombre,
                    mq.nombre AS cotizacion_marca_nombre,
                    m.nombre AS trato_marca_nombre,
                    c.nombre AS cliente_nombre,
                    c.alias AS cliente_alias,
                    c.cuit AS cliente_cuit,
                    c.telefono AS cliente_telefono,
                    TRIM(CONCAT(v.nombre, ' ', v.apellido)) AS vendedor_nombre,
                    TRIM(CONCAT(s.nombre, ' ', s.apellido)) AS solicitante_nombre,
                    TRIM(CONCAT(a.nombre, ' ', a.apellido)) AS compras_nombre,
                    TRIM(CONCAT(ct.nombre, ' ', COALESCE(ct.apellido, ''))) AS contacto_nombre,
                    ct.telefono AS contacto_telefono
                FROM cotizaciones q
                JOIN proyectos p ON p.id = q.proyecto_id
                LEFT JOIN clientes c ON p.cliente_id = c.id_cliente
                LEFT JOIN marcas m ON p.marca_id = m.id_marca
                LEFT JOIN marcas mq ON q.marca_id = mq.id_marca
                LEFT JOIN usuarios v ON p.owner_user_id = v.id
                LEFT JOIN usuarios s ON q.requested_by = s.id
                LEFT JOIN usuarios a ON q.assigned_to = a.id
                LEFT JOIN contactos ct ON p.contacto_id = ct.id_contacto
                ORDER BY q.created_at DESC, q.id DESC
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
        elif scope == "compras":
            if user_id is None:
                return df.iloc[0:0].copy()
            assigned_series = pd.to_numeric(df.get("assigned_to"), errors="coerce")
            mask_individual = assigned_series == int(user_id)
            mask_group = assigned_series.isna()
            df = df[mask_individual | mask_group]
        return df.reset_index(drop=True)
    except Exception as exc:
        log_sql_error(f"Error listando cotizaciones: {exc}")
        return pd.DataFrame()


def get_cotizacion(cotizacion_id, user_id=None, scope="commercial"):
    df = get_cotizaciones_dataframe(user_id, scope=scope)
    if df.empty:
        return None
    row = df[df["cotizacion_id"] == int(cotizacion_id)]
    return row.iloc[0].to_dict() if not row.empty else None


def get_quote_alerts_summary(user_id, scope="commercial"):
    alerts = {
        "pending_purchase_requests_count": 0,
        "sent_quotes_count": 0,
        "sent_quote_tokens": [],
    }
    df = get_cotizaciones_dataframe(user_id, scope=scope)
    if df is None or df.empty:
        return alerts
    status_series = df.get("cotizacion_estado", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    alerts["pending_purchase_requests_count"] = int((status_series == "Solicitado").sum())
    alerts["sent_quotes_count"] = int((status_series == "Enviado").sum())
    sent_df = df.loc[status_series == "Enviado", ["cotizacion_id", "cotizacion_updated_at"]].copy()
    if not sent_df.empty:
        sent_df["cotizacion_updated_at"] = pd.to_datetime(sent_df["cotizacion_updated_at"], errors="coerce")
        alerts["sent_quote_tokens"] = [
            f"{int(row['cotizacion_id'])}|{row['cotizacion_updated_at'].isoformat() if pd.notna(row['cotizacion_updated_at']) else 'na'}"
            for _, row in sent_df.iterrows()
            if pd.notna(row.get("cotizacion_id"))
        ]
    return alerts


def get_seen_quote_sent_tokens(user_id):
    ensure_quotes_schema()
    engine = get_engine()
    try:
        df = pd.read_sql_query(
            text(
                """
                SELECT cotizacion_id, seen_quote_updated_at
                FROM cotizacion_alertas_vistas
                WHERE user_id = :user_id
                """
            ),
            con=engine,
            params={"user_id": int(user_id)},
        )
        if df.empty:
            return set()
        df["seen_quote_updated_at"] = pd.to_datetime(df["seen_quote_updated_at"], errors="coerce")
        return {
            f"{int(row['cotizacion_id'])}|{row['seen_quote_updated_at'].isoformat() if pd.notna(row['seen_quote_updated_at']) else 'na'}"
            for _, row in df.iterrows()
            if pd.notna(row.get("cotizacion_id"))
        }
    except Exception as exc:
        log_sql_error(f"Error obteniendo alertas vistas de cotización: {exc}")
        return set()


def mark_quote_sent_tokens_seen(user_id, tokens):
    ensure_quotes_schema()
    normalized = [str(token).strip() for token in (tokens or []) if str(token).strip()]
    if not normalized:
        return True
    conn = get_connection()
    try:
        c = conn.cursor()
        for token in normalized:
            cotizacion_raw, _, updated_at_raw = token.partition("|")
            if not cotizacion_raw or not updated_at_raw:
                continue
            try:
                cotizacion_id = int(cotizacion_raw)
            except Exception:
                continue
            updated_at = pd.to_datetime(updated_at_raw, errors="coerce")
            if pd.isna(updated_at):
                continue
            c.execute(
                """
                INSERT INTO cotizacion_alertas_vistas (user_id, cotizacion_id, seen_quote_updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, cotizacion_id, seen_quote_updated_at) DO NOTHING
                """,
                (int(user_id), cotizacion_id, updated_at.to_pydatetime()),
            )
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        log_sql_error(f"Error marcando alertas vistas de cotización: {exc}")
        return False
    finally:
        conn.close()


def get_daily_toast_alert_keys_shown(user_id, alert_keys, shown_on=None):
    ensure_quotes_schema()
    normalized_keys = [str(key).strip() for key in (alert_keys or []) if str(key).strip()]
    if not normalized_keys:
        return set()
    target_date = shown_on or datetime.now().date()
    engine = get_engine()
    try:
        df = pd.read_sql_query(
            text(
                """
                SELECT alert_key
                FROM notificacion_toasts_diarios
                WHERE user_id = :user_id
                  AND shown_on = :shown_on
                  AND alert_key = ANY(:alert_keys)
                """
            ),
            con=engine,
            params={
                "user_id": int(user_id),
                "shown_on": target_date,
                "alert_keys": normalized_keys,
            },
        )
        if df.empty:
            return set()
        return {str(value).strip() for value in df["alert_key"].tolist() if str(value).strip()}
    except Exception as exc:
        log_sql_error(f"Error obteniendo toasts diarios vistos: {exc}")
        return set()


def mark_daily_toast_alerts_shown(user_id, alert_keys, shown_on=None):
    ensure_quotes_schema()
    normalized_keys = [str(key).strip() for key in (alert_keys or []) if str(key).strip()]
    if not normalized_keys:
        return True
    target_date = shown_on or datetime.now().date()
    conn = get_connection()
    try:
        c = conn.cursor()
        for alert_key in normalized_keys:
            c.execute(
                """
                INSERT INTO notificacion_toasts_diarios (user_id, alert_key, shown_on)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, alert_key, shown_on) DO NOTHING
                """,
                (int(user_id), alert_key, target_date),
            )
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        log_sql_error(f"Error marcando toasts diarios vistos: {exc}")
        return False
    finally:
        conn.close()


def get_cotizacion_items_df(cotizacion_id):
    ensure_quotes_schema()
    engine = get_engine()
    try:
        return pd.read_sql_query(
            text(
                """
                SELECT id, cantidad, sku, modelo, descripcion, created_at, updated_at
                FROM cotizacion_items
                WHERE cotizacion_id = :cotizacion_id
                ORDER BY id ASC
                """
            ),
            con=engine,
            params={"cotizacion_id": int(cotizacion_id)},
        )
    except Exception as exc:
        log_sql_error(f"Error obteniendo ítems de cotización: {exc}")
        return pd.DataFrame()


def get_cotizacion_comments_df(cotizacion_id):
    ensure_quotes_schema()
    engine = get_engine()
    try:
        return pd.read_sql_query(
            text(
                """
                SELECT
                    c.id,
                    c.comentario,
                    c.created_at,
                    TRIM(CONCAT(u.nombre, ' ', u.apellido)) AS autor_nombre
                FROM cotizacion_comentarios c
                LEFT JOIN usuarios u ON c.created_by = u.id
                WHERE c.cotizacion_id = :cotizacion_id
                ORDER BY c.created_at DESC, c.id DESC
                """
            ),
            con=engine,
            params={"cotizacion_id": int(cotizacion_id)},
        )
    except Exception as exc:
        log_sql_error(f"Error obteniendo comentarios de cotización: {exc}")
        return pd.DataFrame()


def get_cotizacion_documents_df(cotizacion_id):
    ensure_quotes_schema()
    engine = get_engine()
    try:
        df = pd.read_sql_query(
            text(
                """
                SELECT
                    d.id,
                    d.filename,
                    d.file_path,
                    d.mime_type,
                    d.file_size,
                    d.uploaded_by,
                    d.is_vigente,
                    d.created_at,
                    q.serie_num,
                    TRIM(CONCAT(u.nombre, ' ', u.apellido)) AS uploaded_by_name
                FROM cotizacion_documentos d
                JOIN cotizaciones q ON q.id = d.cotizacion_id
                LEFT JOIN usuarios u ON d.uploaded_by = u.id
                WHERE d.cotizacion_id = :cotizacion_id
                ORDER BY d.created_at DESC, d.id DESC
                """
            ),
            con=engine,
            params={"cotizacion_id": int(cotizacion_id)},
        )
        return _annotate_quote_document_versions(df)
    except Exception as exc:
        log_sql_error(f"Error obteniendo documentos de cotización: {exc}")
        return pd.DataFrame()


def _replace_quote_items_in_connection(conn, cotizacion_id, items):
    c = conn.cursor()
    c.execute("DELETE FROM cotizacion_items WHERE cotizacion_id = %s", (int(cotizacion_id),))
    for item in items:
        c.execute(
            """
            INSERT INTO cotizacion_items (cotizacion_id, cantidad, sku, modelo, descripcion)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                int(cotizacion_id),
                float(item["cantidad"]),
                item["sku"] or None,
                item["modelo"] or None,
                item["descripcion"] or None,
            ),
        )


def _insert_quote_comment_in_connection(conn, cotizacion_id, comentario, created_by):
    if not str(comentario or "").strip():
        return
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO cotizacion_comentarios (cotizacion_id, comentario, created_by)
        VALUES (%s, %s, %s)
        """,
        (int(cotizacion_id), str(comentario).strip(), int(created_by) if created_by is not None else None),
    )


def _default_quote_request_comment(new_version=False):
    if new_version:
        return "Se solicitó una nueva versión de la cotización."
    return "Se solicitó una cotización."


def _insert_quote_documents_in_connection(conn, cotizacion_id, documents):
    selected_new_doc_id = None
    c = conn.cursor()
    for document in documents or []:
        c.execute(
            """
            INSERT INTO cotizacion_documentos (cotizacion_id, filename, file_path, mime_type, file_size, uploaded_by, is_vigente)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                int(cotizacion_id),
                str(document.get("filename") or "").strip(),
                str(document.get("file_path") or "").strip(),
                str(document.get("mime_type") or "").strip() or None,
                int(document.get("file_size") or 0),
                int(document.get("uploaded_by")) if document.get("uploaded_by") is not None else None,
                bool(document.get("is_vigente")),
            ),
        )
        row = c.fetchone()
        if row and bool(document.get("is_vigente")):
            selected_new_doc_id = int(row[0])
    return selected_new_doc_id


def _set_quote_vigente_document_in_connection(conn, cotizacion_id, selected_doc_id=None):
    c = conn.cursor()
    c.execute("UPDATE cotizacion_documentos SET is_vigente = FALSE WHERE cotizacion_id = %s", (int(cotizacion_id),))
    if selected_doc_id:
        c.execute(
            "UPDATE cotizacion_documentos SET is_vigente = TRUE WHERE cotizacion_id = %s AND id = %s",
            (int(cotizacion_id), int(selected_doc_id)),
        )


def create_cotizacion(
    proyecto_id,
    requested_by,
    items,
    comentario_inicial="",
    documents=None,
    selected_existing_vigente_id=None,
    scope="commercial",
    initial_status="Solicitado",
    notify_request=True,
    allow_empty_items=False,
    assigned_to=None,
    marca_id=None,
):
    ensure_quotes_schema()
    visible_ids = _visible_project_ids(requested_by, scope=scope, only_open=True)
    if int(proyecto_id) not in visible_ids:
        raise ValueError("El trato seleccionado no está disponible para solicitar cotización.")

    project = get_proyecto(proyecto_id)
    if not project:
        raise ValueError("No se encontró el trato seleccionado.")
    if not is_project_open_status(project.get("estado")):
        raise ValueError("El trato seleccionado está cerrado, ganado o perdido.")

    initial_status = str(initial_status or "Solicitado").strip()
    if initial_status not in QUOTE_STATUS_OPTIONS:
        raise ValueError("Estado inicial de cotización inválido.")

    assigned_to = _resolve_quote_assigned_to(
        assigned_to=assigned_to,
        require_available=bool(notify_request or initial_status == "Solicitado"),
        allow_group_assignment=True,
    )
    sanitized_items = [] if allow_empty_items and not list(items or []) else _sanitize_quote_items(items)
    conn = get_connection()
    try:
        c = conn.cursor()
        serie_num = _next_quote_series_num_in_connection(conn, proyecto_id)
        effective_marca_id = marca_id if marca_id is not None else project.get("marca_id")
        c.execute(
            """
            INSERT INTO cotizaciones (proyecto_id, requested_by, assigned_to, serie_num, marca_id, estado)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (int(proyecto_id), int(requested_by), assigned_to, int(serie_num), int(effective_marca_id) if effective_marca_id is not None else None, initial_status),
        )
        cotizacion_id = int(c.fetchone()[0])
        _replace_quote_items_in_connection(conn, cotizacion_id, sanitized_items)
        effective_initial_comment = str(comentario_inicial or "").strip() or _default_quote_request_comment()
        _insert_quote_comment_in_connection(conn, cotizacion_id, effective_initial_comment, requested_by)
        selected_new_doc_id = _insert_quote_documents_in_connection(conn, cotizacion_id, documents or [])
        final_vigente_id = selected_new_doc_id or selected_existing_vigente_id
        if final_vigente_id:
            _set_quote_vigente_document_in_connection(conn, cotizacion_id, selected_doc_id=final_vigente_id)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log_sql_error(f"Error creando cotización: {exc}")
        raise
    finally:
        conn.close()

    if notify_request:
        _queue_quote_request_notification(
            cotizacion_id=cotizacion_id,
            requested_by=requested_by,
            project=project,
            assigned_to=assigned_to,
            dedupe_key=f"cotizacion_solicitada:{cotizacion_id}",
        )

    return cotizacion_id


def update_cotizacion(
    cotizacion_id,
    acting_user_id,
    items,
    new_comment="",
    documents=None,
    selected_existing_vigente_id=None,
    new_status=None,
    scope="commercial",
    assigned_to=None,
    marca_id=None,
):
    ensure_quotes_schema()
    current = get_cotizacion(cotizacion_id, user_id=acting_user_id, scope=scope)
    if not current:
        raise ValueError("No se encontró la cotización seleccionada.")

    project = get_proyecto(current["proyecto_id"])
    if not project:
        raise ValueError("No se pudo cargar el trato asociado.")
    previous_status = str(current.get("cotizacion_estado") or "").strip()
    assigned_to = _resolve_quote_assigned_to(
        assigned_to=assigned_to if assigned_to is not None else current.get("assigned_to"),
        require_available=False,
        allow_group_assignment=True,
    )

    sanitized_items = _sanitize_quote_items(items)
    conn = get_connection()
    try:
        c = conn.cursor()
        estado_to_save = current.get("cotizacion_estado") or "Solicitado"
        if new_status and str(new_status).strip() in QUOTE_STATUS_OPTIONS:
            estado_to_save = str(new_status).strip()
        marca_to_save = current.get("cotizacion_marca_id")
        if scope in {"commercial", "admin_comercial"} and marca_id is not None:
            marca_to_save = int(marca_id)
        c.execute(
            """
            UPDATE cotizaciones
            SET assigned_to = %s,
                marca_id = %s,
                estado = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (assigned_to, marca_to_save, estado_to_save, int(cotizacion_id)),
        )
        _replace_quote_items_in_connection(conn, cotizacion_id, sanitized_items)
        _insert_quote_comment_in_connection(conn, cotizacion_id, new_comment, acting_user_id)
        selected_new_doc_id = _insert_quote_documents_in_connection(conn, cotizacion_id, documents or [])
        final_vigente_id = selected_new_doc_id or selected_existing_vigente_id
        if final_vigente_id:
            _set_quote_vigente_document_in_connection(conn, cotizacion_id, selected_doc_id=final_vigente_id)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log_sql_error(f"Error actualizando cotización: {exc}")
        raise
    finally:
        conn.close()

    notify_sent = (
        scope == "compras"
        and previous_status != "Enviado"
        and str(estado_to_save or "").strip() == "Enviado"
    )
    if notify_sent:
        notification_project = dict(project or {})
        notification_project["compras_nombre"] = current.get("compras_nombre") or notification_project.get("compras_nombre")
        _queue_quote_sent_notification(
            cotizacion_id=cotizacion_id,
            requested_by=int(current.get("requested_by") or 0),
            acted_by=acting_user_id,
            project=notification_project,
            detail_suffix="Compras envio la cotizacion para revision.",
            dedupe_key=f"cotizacion_enviada:{int(cotizacion_id)}:{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        )

    return True


def append_cotizacion_documents(cotizacion_id, documents, selected_existing_vigente_id=None):
    ensure_quotes_schema()
    conn = get_connection()
    try:
        selected_new_doc_id = _insert_quote_documents_in_connection(conn, cotizacion_id, documents or [])
        final_vigente_id = selected_new_doc_id or selected_existing_vigente_id
        if final_vigente_id:
            _set_quote_vigente_document_in_connection(conn, cotizacion_id, selected_doc_id=final_vigente_id)
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        log_sql_error(f"Error adjuntando documentos a cotizacion: {exc}")
        raise
    finally:
        conn.close()


def close_quotes_for_project(project_id):
    ensure_quotes_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            UPDATE cotizaciones
            SET estado = 'Cancelado / Cerrado',
                updated_at = CURRENT_TIMESTAMP
            WHERE proyecto_id = %s
              AND COALESCE(estado, '') <> 'Cancelado / Cerrado'
            """,
            (int(project_id),),
        )
        conn.commit()
        return c.rowcount
    except Exception as exc:
        conn.rollback()
        log_sql_error(f"Error cerrando cotizaciones del trato {project_id}: {exc}")
        return 0
    finally:
        conn.close()


def request_new_cotizacion_version(cotizacion_id, acting_user_id, scope="commercial", request_comment="", assigned_to=None):
    ensure_quotes_schema()
    current = get_cotizacion(cotizacion_id, user_id=acting_user_id, scope=scope)
    if not current:
        raise ValueError("No se encontró la cotización seleccionada.")
    if scope not in {"commercial", "admin_comercial"}:
        raise ValueError("Solo comercial y adm_comercial pueden solicitar una nueva versión.")
    if not is_project_open_status(current.get("trato_estado")):
        raise ValueError("No se puede solicitar una nueva versión sobre un trato cerrado.")
    if not is_quote_editable_status(current.get("cotizacion_estado")):
        raise ValueError("Solo se puede solicitar nueva versión en cotizaciones activas.")

    docs_df = get_cotizacion_documents_df(cotizacion_id)
    if docs_df.empty:
        raise ValueError("Todavía no hay una versión previa cargada por compras para volver a solicitar.")

    project = get_proyecto(current["proyecto_id"])
    if not project:
        raise ValueError("No se pudo cargar el trato asociado.")

    assigned_to = _resolve_quote_assigned_to(
        assigned_to=assigned_to if assigned_to is not None else current.get("assigned_to"),
        require_available=True,
        allow_group_assignment=True,
    )
    note = str(request_comment or "").strip() or _default_quote_request_comment(new_version=True)

    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            UPDATE cotizaciones
            SET assigned_to = %s,
                estado = 'Solicitado',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (assigned_to, int(cotizacion_id)),
        )
        _insert_quote_comment_in_connection(conn, cotizacion_id, note, acting_user_id)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log_sql_error(f"Error solicitando nueva versión de cotización: {exc}")
        raise
    finally:
        conn.close()

    _queue_quote_request_notification(
        cotizacion_id=cotizacion_id,
        requested_by=acting_user_id,
        project=project,
        assigned_to=assigned_to,
        detail_suffix="Nueva versión solicitada",
        dedupe_key=f"cotizacion_solicitada:{int(cotizacion_id)}:{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
    )
    return True


def delete_cotizacion(cotizacion_id, acting_user_id, scope="commercial"):
    ensure_quotes_schema()
    if scope == "compras":
        raise ValueError("Compras no puede eliminar cotizaciones desde esta pestaña.")
    current = get_cotizacion(cotizacion_id, user_id=acting_user_id, scope=scope)
    if not current:
        raise ValueError("No se encontró la cotización seleccionada.")

    docs_df = get_cotizacion_documents_df(cotizacion_id)
    file_paths = [
        str(path).strip()
        for path in docs_df.get("file_path", pd.Series(dtype=str)).fillna("").tolist()
        if str(path).strip()
    ]

    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM cotizaciones WHERE id = %s", (int(cotizacion_id),))
        if not c.rowcount:
            raise ValueError("No se pudo eliminar la cotización seleccionada.")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log_sql_error(f"Error eliminando cotización: {exc}")
        raise
    finally:
        conn.close()

    for file_path in file_paths:
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception:
            pass

    return True
