import json
import os
import re
import smtplib
from email.message import EmailMessage
import psycopg2
import psycopg2.extras
import pandas as pd
import uuid
import zlib
from datetime import datetime, timedelta
from .logging_utils import log_app_error, log_sql_error
from contextlib import contextmanager
from .config import (
    POSTGRES_CONFIG,
    DEFAULT_ADMIN_USERNAME,
    DEFAULT_ADMIN_PASSWORD,
    PROJECT_UPLOADS_DIR,
    SYSTEM_ROLES,
    SMTP_CONFIG,
    NOTIFICATION_POLICY_DEFINITIONS,
    get_notification_policy,
    get_notification_template,
    DEPARTMENT_EXPANSION_MAP,
)
from .utils import month_name_es, normalize_cuit, normalize_web, parse_registro_datetime, format_registro_date_iso, normalize_name
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
_ENGINE = None


def _is_path_within(base_dir, target_path):
    try:
        base_abs = os.path.abspath(str(base_dir or ""))
        target_abs = os.path.abspath(str(target_path or ""))
        if not base_abs or not target_abs:
            return False
        return os.path.commonpath([base_abs, target_abs]) == base_abs
    except Exception:
        return False


def _remove_empty_dirs_upwards(start_dir, stop_dirs=None):
    current_dir = os.path.abspath(str(start_dir or ""))
    stop_set = {os.path.abspath(str(path)) for path in (stop_dirs or []) if str(path).strip()}
    while current_dir and current_dir not in stop_set and os.path.isdir(current_dir):
        try:
            if os.listdir(current_dir):
                break
            os.rmdir(current_dir)
        except Exception:
            break
        parent_dir = os.path.dirname(current_dir)
        if not parent_dir or parent_dir == current_dir:
            break
        current_dir = parent_dir

def get_engine():
    """Devuelve un engine de SQLAlchemy para PostgreSQL usando POSTGRES_CONFIG"""
    global _ENGINE
    if _ENGINE is None:
        db_url = URL.create(
            "postgresql+psycopg2",
            username=POSTGRES_CONFIG['user'],
            password=POSTGRES_CONFIG['password'],
            host=POSTGRES_CONFIG['host'],
            port=int(POSTGRES_CONFIG['port']),
            database=POSTGRES_CONFIG['database'],
        )
        _ENGINE = create_engine(db_url, pool_pre_ping=True)
    return _ENGINE

def get_connection():
    """Establece conexión con PostgreSQL"""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_CONFIG['host'],
            port=POSTGRES_CONFIG['port'],
            database=POSTGRES_CONFIG['database'],
            user=POSTGRES_CONFIG['user'],
            password=POSTGRES_CONFIG['password']
        )
        return conn
    except UnicodeDecodeError:
        # Esto sucede cuando el mensaje de error de Postgres (ej: autenticación falló)
        # tiene caracteres que no son UTF-8 (ej: tildes en CP1252) y psycopg2 intenta decodificarlos.
        # Asumimos que es un error de conexión/credenciales.
        log_sql_error("Error de conexión (UnicodeDecodeError - Probablemente credenciales inválidas)")
        raise Exception("Error de conexión o credenciales inválidas.")
    except Exception as e:
        log_sql_error(f"Error conectando a PostgreSQL: {e}")
        raise

def test_connection():
    """Prueba la conexión a la base de datos"""
    try:
        conn = get_connection()
        conn.close()
        return True
    except Exception as e:
        log_sql_error(f"Error en test de conexión: {e}")
        return False

@contextmanager
def db_connection():
    """Context manager para conexiones a la base de datos"""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


NOTIFICATION_WEEKDAY_INDEX = {
    'monday': 0,
    'tuesday': 1,
    'wednesday': 2,
    'thursday': 3,
    'friday': 4,
}


def ensure_notifications_schema():
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS notification_event_queue (
                id SERIAL PRIMARY KEY,
                event_key VARCHAR(100) NOT NULL,
                dedupe_key VARCHAR(255) UNIQUE,
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                last_error TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_notification_event_queue_status_created
            ON notification_event_queue (status, created_at)
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS notification_delivery_log (
                id SERIAL PRIMARY KEY,
                event_key VARCHAR(100) NOT NULL,
                frequency VARCHAR(20) NOT NULL,
                recipient_user_id INTEGER NULL REFERENCES usuarios(id) ON DELETE SET NULL,
                recipient_email VARCHAR(200) NOT NULL,
                dedupe_key VARCHAR(255) NOT NULL UNIQUE,
                source_queue_id INTEGER NULL REFERENCES notification_event_queue(id) ON DELETE SET NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_notification_delivery_log_event_created
            ON notification_delivery_log (event_key, created_at)
        """)
        conn.commit()
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error asegurando esquema de notificaciones: {e}")
        raise
    finally:
        conn.close()


def _normalize_notification_email(value):
    email = str(value or '').strip()
    if not email or email.lower() == 'none':
        return ''
    return email


def _notification_send_time_tuple(value):
    raw_value = str(value or '').strip()
    if len(raw_value) == 5 and raw_value[2] == ':' and raw_value.replace(':', '').isdigit():
        hours, minutes = raw_value.split(':', 1)
        hours_i = int(hours)
        minutes_i = int(minutes)
        if 0 <= hours_i <= 23 and 0 <= minutes_i <= 59:
            return hours_i, minutes_i
    return 9, 0


def _notification_policy_due_now(policy, now):
    frequency = str(policy.get('frequency') or 'daily').strip().lower()
    if frequency == 'immediate':
        return True
    send_hours, send_minutes = _notification_send_time_tuple(policy.get('send_time'))
    if (now.hour, now.minute) < (send_hours, send_minutes):
        return False
    if frequency == 'weekly':
        weekday = str(policy.get('weekday') or 'monday').strip().lower()
        return now.weekday() == NOTIFICATION_WEEKDAY_INDEX.get(weekday, 0)
    return frequency == 'daily'


def _notification_is_smtp_ready():
    return bool(
        SMTP_CONFIG.get('enabled')
        and str(SMTP_CONFIG.get('host') or '').strip()
        and str(SMTP_CONFIG.get('port') or '').strip()
        and _normalize_notification_email(SMTP_CONFIG.get('from_email'))
    )


def _notification_string(value, empty_value='-'):
    if value is None:
        return empty_value
    if isinstance(value, float) and pd.isna(value):
        return empty_value
    text_value = str(value).strip()
    return text_value if text_value else empty_value


def _notification_compact_name(nombre, apellido='', fallback='Usuario'):
    full_name = " ".join(part for part in [str(nombre or '').strip(), str(apellido or '').strip()] if part)
    return full_name or fallback


def _notification_fetch_user(conn, user_id):
    if user_id in (None, ''):
        return None
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            """
            SELECT id, username, nombre, apellido, email, is_admin, is_active, rol_id
            FROM usuarios
            WHERE id = %s
            """,
            (int(user_id),)
        )
        row = c.fetchone()
        if not row:
            return None
        data = dict(row)
        data['email'] = _normalize_notification_email(data.get('email'))
        data['display_name'] = _notification_compact_name(
            data.get('nombre'),
            data.get('apellido'),
            data.get('username') or data['email'] or 'Usuario'
        )
        return data
    except Exception:
        return None


def _queue_notification_event_in_connection(conn, event_key, payload, dedupe_key=None):
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO notification_event_queue (event_key, dedupe_key, payload)
        VALUES (%s, %s, %s)
        ON CONFLICT (dedupe_key) DO NOTHING
        RETURNING id
        """,
        (
            str(event_key or '').strip(),
            str(dedupe_key).strip() if dedupe_key else None,
            psycopg2.extras.Json(payload or {}),
        )
    )
    row = c.fetchone()
    return int(row[0]) if row else None


def queue_notification_event(event_key, payload, dedupe_key=None):
    ensure_notifications_schema()
    conn = get_connection()
    try:
        event_id = _queue_notification_event_in_connection(conn, event_key, payload, dedupe_key=dedupe_key)
        conn.commit()
        return event_id
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error encolando notificación {event_key}: {e}")
        return None
    finally:
        conn.close()


def _notification_delivery_exists(conn, dedupe_key):
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM notification_delivery_log WHERE dedupe_key = %s LIMIT 1",
        (str(dedupe_key).strip(),)
    )
    return c.fetchone() is not None


def _notification_record_delivery(conn, event_key, frequency, recipient, dedupe_key, subject, body, source_queue_id=None):
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO notification_delivery_log (
            event_key,
            frequency,
            recipient_user_id,
            recipient_email,
            dedupe_key,
            source_queue_id,
            subject,
            body
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (dedupe_key) DO NOTHING
        """,
        (
            str(event_key or '').strip(),
            str(frequency or '').strip(),
            recipient.get('user_id'),
            recipient.get('email'),
            str(dedupe_key).strip(),
            source_queue_id,
            str(subject or ''),
            str(body or ''),
        )
    )


def _notification_update_queue_status(conn, queue_id, status, last_error=None):
    c = conn.cursor()
    c.execute(
        """
        UPDATE notification_event_queue
        SET status = %s,
            last_error = %s,
            processed_at = CASE WHEN %s IN ('processed', 'discarded') THEN CURRENT_TIMESTAMP ELSE NULL END
        WHERE id = %s
        """,
        (
            str(status or 'pending').strip(),
            str(last_error or '').strip() or None,
            str(status or 'pending').strip(),
            int(queue_id),
        )
    )


def _notification_effective_template(event_key):
    event_template = get_notification_template(event_key)
    if event_template.get('enabled'):
        return event_template
    default_template = get_notification_template('default')
    return default_template


def _notification_render_text(template_text, context):
    return re.sub(
        r"\{([^{}]+)\}",
        lambda match: str(context.get(match.group(1), '')),
        str(template_text or '')
    )


def _notification_send_email(recipient_email, subject, body):
    if not _notification_is_smtp_ready():
        raise RuntimeError("SMTP no está configurado para envíos automáticos.")
    host = str(SMTP_CONFIG.get('host') or '').strip()
    port = int(str(SMTP_CONFIG.get('port') or '587').strip())
    security = str(SMTP_CONFIG.get('security') or 'tls').strip().lower()
    sender_email = _normalize_notification_email(SMTP_CONFIG.get('from_email'))
    sender_name = str(SMTP_CONFIG.get('from_name') or 'SIGO').strip() or 'SIGO'
    username = str(SMTP_CONFIG.get('user') or '').strip()
    password = str(SMTP_CONFIG.get('password') or '')

    message = EmailMessage()
    message['Subject'] = str(subject or '').strip() or 'Notificación SIGO'
    message['From'] = f"{sender_name} <{sender_email}>"
    message['To'] = recipient_email
    message.set_content(str(body or ''), subtype='plain', charset='utf-8')

    smtp_client = None
    try:
        if security == 'ssl':
            smtp_client = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            smtp_client = smtplib.SMTP(host, port, timeout=20)
            smtp_client.ehlo()
            smtp_client.starttls()
            smtp_client.ehlo()
        if username:
            smtp_client.login(username, password)
        smtp_client.send_message(message)
    finally:
        if smtp_client is not None:
            try:
                smtp_client.quit()
            except Exception:
                pass


def _notification_event_label(event_key):
    definition = NOTIFICATION_POLICY_DEFINITIONS.get(str(event_key or '').strip(), {})
    return str(definition.get('label') or event_key or 'Notificación')


def _notification_build_context(conn, event_key, payload, recipient, now):
    payload = dict(payload or {})
    requester = _notification_fetch_user(conn, payload.get('requested_by'))
    recipient_name = recipient.get('display_name') or recipient.get('email') or 'Usuario'
    context = {
        'nombre': recipient_name,
        'usuario': payload.get('usuario') or recipient_name,
        'email': recipient.get('email') or '',
        'evento': _notification_event_label(event_key),
        'detalle': payload.get('detalle') or '',
        'fecha': now.strftime("%d/%m/%Y %H:%M"),
        'empresa': 'SIGO',
        'solicitante': payload.get('solicitante') or (requester.get('display_name') if requester else 'Usuario'),
        'cliente': payload.get('cliente') or payload.get('nombre') or '-',
        'cuit': payload.get('cuit') or '-',
        'telefono': payload.get('telefono') or '-',
        'aprobador': payload.get('aprobador') or 'Administración',
        'periodo': payload.get('periodo') or '',
        'cantidad_alertas': payload.get('cantidad_alertas') or '0',
        'resumen_alertas': payload.get('resumen_alertas') or '',
        'trato': payload.get('trato') or '-',
        'fecha_cierre': payload.get('fecha_cierre') or '-',
        'dias_restantes': payload.get('dias_restantes') or '-',
        'dias_vencido': payload.get('dias_vencido') or '-',
        'estado': payload.get('estado') or '-',
    }
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            context[key] = json.dumps(value, ensure_ascii=False)
        else:
            context[key] = value
    return context


def _notification_admin_recipients(conn):
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute(
        """
        SELECT id, username, nombre, apellido, email, rol_id
        FROM usuarios
        WHERE is_admin = TRUE
          AND is_active = TRUE
          AND COALESCE(email, '') <> ''
        ORDER BY apellido, nombre, username
        """
    )
    recipients = []
    for row in c.fetchall():
        email = _normalize_notification_email(row.get('email'))
        if not email:
            continue
        recipients.append({
            'user_id': int(row['id']),
            'email': email,
            'display_name': _notification_compact_name(row.get('nombre'), row.get('apellido'), row.get('username') or email),
            'rol_id': int(row['rol_id']) if row.get('rol_id') is not None else None,
            'dedupe_key': f"user:{int(row['id'])}",
        })
    return recipients


def _notification_view_type_recipients(conn, view_type):
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute(
        """
        SELECT u.id, u.username, u.nombre, u.apellido, u.email, u.rol_id
        FROM usuarios u
        JOIN roles r ON u.rol_id = r.id_rol
        WHERE u.is_active = TRUE
          AND COALESCE(u.email, '') <> ''
          AND COALESCE(r.view_type, '') = %s
        ORDER BY u.apellido, u.nombre, u.username
        """,
        (str(view_type or '').strip(),)
    )
    recipients = []
    for row in c.fetchall():
        email = _normalize_notification_email(row.get('email'))
        if not email:
            continue
        recipients.append({
            'user_id': int(row['id']),
            'email': email,
            'display_name': _notification_compact_name(row.get('nombre'), row.get('apellido'), row.get('username') or email),
            'rol_id': int(row['rol_id']) if row.get('rol_id') is not None else None,
            'dedupe_key': f"user:{int(row['id'])}",
        })
    return recipients


def _notification_policy_allows_recipient(policy, recipient):
    scope = str((policy or {}).get('target_scope') or 'all').strip().lower()
    if scope not in {'all', 'roles', 'users'}:
        scope = 'all'
    if scope == 'all':
        return True
    user_id = recipient.get('user_id')
    if user_id is None:
        return False
    try:
        user_id = int(user_id)
    except Exception:
        return False
    if scope == 'users':
        allowed_user_ids = policy.get('target_user_ids') or []
        if not isinstance(allowed_user_ids, list):
            return False
        try:
            allowed_set = {int(x) for x in allowed_user_ids}
        except Exception:
            allowed_set = set()
        return user_id in allowed_set
    role_id = recipient.get('rol_id')
    if role_id is None:
        return False
    try:
        role_id = int(role_id)
    except Exception:
        return False
    allowed_role_ids = policy.get('target_role_ids') or []
    if not isinstance(allowed_role_ids, list):
        return False
    try:
        allowed_set = {int(x) for x in allowed_role_ids}
    except Exception:
        allowed_set = set()
    return role_id in allowed_set


def _notification_recipients_for_event(conn, event_key, payload):
    payload = dict(payload or {})
    if event_key == 'cliente_solicitud_creada':
        return _notification_admin_recipients(conn)
    if event_key == 'cotizacion_solicitada':
        assignee = _notification_fetch_user(conn, payload.get('assigned_to'))
        if assignee and assignee.get('email') and bool(assignee.get('is_active', True)):
            return [{
                'user_id': int(assignee['id']),
                'email': assignee['email'],
                'display_name': assignee['display_name'],
                'rol_id': int(assignee['rol_id']) if assignee.get('rol_id') is not None else None,
                'dedupe_key': f"user:{int(assignee['id'])}",
            }]
        recipients = []
        seen_keys = set()
        for view_type in ('compras', 'admin_comercial'):
            for candidate in _notification_view_type_recipients(conn, view_type):
                key = candidate.get('dedupe_key')
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                recipients.append(candidate)
        return recipients
    if event_key in {'cliente_solicitud_aprobada', 'cliente_solicitud_rechazada', 'cotizacion_enviada'}:
        requester = _notification_fetch_user(conn, payload.get('requested_by'))
        if requester and requester.get('email') and bool(requester.get('is_active', True)):
            return [{
                'user_id': int(requester['id']),
                'email': requester['email'],
                'display_name': requester['display_name'],
                'rol_id': int(requester['rol_id']) if requester.get('rol_id') is not None else None,
                'dedupe_key': f"user:{int(requester['id'])}",
            }]
    if event_key == 'informe_tecnico_solicitado':
        return _notification_view_type_recipients(conn, 'admin_tecnico')
    if event_key == 'cotizacion_tecnica_solicitada':
        recipients = []
        seen_keys = set()
        acted_by = payload.get('acted_by')

        def _append_tech_recipient(candidate):
            if not candidate or not candidate.get('email'):
                return
            try:
                candidate_user_id = int(candidate.get('user_id') or candidate.get('id'))
            except Exception:
                candidate_user_id = None
            if acted_by is not None and candidate_user_id is not None:
                try:
                    if int(acted_by) == candidate_user_id:
                        return
                except Exception:
                    pass
            dedupe_key = candidate.get('dedupe_key') or (f"user:{candidate_user_id}" if candidate_user_id is not None else None)
            if not dedupe_key or dedupe_key in seen_keys:
                return
            seen_keys.add(dedupe_key)
            recipients.append({
                'user_id': candidate_user_id,
                'email': candidate.get('email'),
                'display_name': candidate.get('display_name') or 'Usuario',
                'rol_id': int(candidate['rol_id']) if candidate.get('rol_id') is not None else None,
                'dedupe_key': dedupe_key,
            })

        for user in _notification_view_type_recipients(conn, 'adm_tecnico'):
            _append_tech_recipient(user)
        for user in _notification_view_type_recipients(conn, 'dpto_tecnico'):
            _append_tech_recipient(user)
        for user in _notification_view_type_recipients(conn, 'visor'):
            _append_tech_recipient(user)
        return recipients
    if event_key == 'informe_tecnico_actualizado':
        recipients = []
        seen_keys = set()
        acted_by = payload.get('acted_by')

        def _append_recipient(candidate):
            if not candidate or not candidate.get('email'):
                return
            try:
                candidate_user_id = int(candidate.get('user_id') or candidate.get('id'))
            except Exception:
                candidate_user_id = None
            if acted_by is not None and candidate_user_id is not None:
                try:
                    if int(acted_by) == candidate_user_id:
                        return
                except Exception:
                    pass
            dedupe_key = candidate.get('dedupe_key') or (f"user:{candidate_user_id}" if candidate_user_id is not None else None)
            if not dedupe_key or dedupe_key in seen_keys:
                return
            seen_keys.add(dedupe_key)
            recipients.append({
                'user_id': candidate_user_id,
                'email': candidate.get('email'),
                'display_name': candidate.get('display_name') or 'Usuario',
                'rol_id': int(candidate['rol_id']) if candidate.get('rol_id') is not None else None,
                'dedupe_key': dedupe_key,
            })

        requester = _notification_fetch_user(conn, payload.get('requested_by'))
        if requester and requester.get('email') and bool(requester.get('is_active', True)):
            _append_recipient({
                'id': int(requester['id']),
                'user_id': int(requester['id']),
                'email': requester['email'],
                'display_name': requester['display_name'],
                'rol_id': requester.get('rol_id'),
                'dedupe_key': f"user:{int(requester['id'])}",
            })
        for technical_user in _notification_view_type_recipients(conn, 'admin_tecnico'):
            _append_recipient(technical_user)
        return recipients
    return []


def _notification_send_for_recipient(conn, event_key, frequency, payload, recipient, dedupe_key, source_queue_id=None, now=None):
    now = now or datetime.now()
    template = _notification_effective_template(event_key)
    if not template.get('enabled'):
        raise RuntimeError("No hay una plantilla habilitada para este evento.")
    context = _notification_build_context(conn, event_key, payload, recipient, now)
    subject = _notification_render_text(template.get('subject'), context).strip()
    body = _notification_render_text(template.get('body'), context).strip()
    _notification_send_email(recipient['email'], subject, body)
    _notification_record_delivery(
        conn,
        event_key,
        frequency,
        recipient,
        dedupe_key,
        subject,
        body,
        source_queue_id=source_queue_id,
    )


def _notification_process_event_queue(now, max_emails=None, deadline=None):
    results = {'sent': 0, 'processed': 0, 'discarded': 0, 'errors': 0}
    import time as _time
    def _should_stop():
        if deadline is not None and _time.time() >= float(deadline):
            return True
        if max_emails is not None and results['sent'] >= int(max_emails):
            return True
        return False
    conn = get_connection()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            """
            SELECT id, event_key, payload, created_at
            FROM notification_event_queue
            WHERE status = 'pending'
            ORDER BY created_at ASC, id ASC
            LIMIT 100
            """
        )
        rows = c.fetchall()
        for row in rows:
            if _should_stop():
                return results
            event_key = str(row['event_key'] or '').strip()
            payload = dict(row.get('payload') or {})
            policy = get_notification_policy(event_key)
            if not policy.get('enabled') or not policy.get('email_enabled'):
                _notification_update_queue_status(conn, row['id'], 'discarded', 'Política deshabilitada.')
                conn.commit()
                results['discarded'] += 1
                continue
            if not _notification_policy_due_now(policy, now):
                continue
            recipients = _notification_recipients_for_event(conn, event_key, payload)
            recipients = [r for r in recipients if _notification_policy_allows_recipient(policy, r)]
            if not recipients:
                _notification_update_queue_status(conn, row['id'], 'discarded', 'No se encontraron destinatarios válidos.')
                conn.commit()
                results['discarded'] += 1
                continue
            pending_errors = []
            sent_this_event = False
            for recipient in recipients:
                if _should_stop():
                    return results
                delivery_dedupe_key = f"{event_key}:{int(row['id'])}:{recipient['dedupe_key']}"
                if _notification_delivery_exists(conn, delivery_dedupe_key):
                    sent_this_event = True
                    continue
                try:
                    _notification_send_for_recipient(
                        conn,
                        event_key,
                        policy.get('frequency'),
                        payload,
                        recipient,
                        delivery_dedupe_key,
                        source_queue_id=int(row['id']),
                        now=now,
                    )
                    conn.commit()
                    sent_this_event = True
                    results['sent'] += 1
                except Exception as e:
                    conn.rollback()
                    pending_errors.append(str(e))
                    results['errors'] += 1
                    log_app_error(e, module="database", function="_notification_process_event_queue")
            if pending_errors:
                c_retry = conn.cursor()
                c_retry.execute(
                    """
                    UPDATE notification_event_queue
                    SET last_error = %s
                    WHERE id = %s
                    """,
                    ("\n".join(pending_errors), int(row['id']))
                )
                conn.commit()
            elif sent_this_event:
                _notification_update_queue_status(conn, row['id'], 'processed')
                conn.commit()
                results['processed'] += 1
        return results
    finally:
        conn.close()


def _notification_pending_load_alerts(user_id, reference_now=None):
    reference_now = reference_now or datetime.now()
    alerts = []
    try:
        df_regs = get_user_registros_dataframe(user_id)
        if not df_regs.empty:
            if pd.api.types.is_datetime64_any_dtype(df_regs['fecha']):
                df_regs['fecha_dt'] = df_regs['fecha']
            else:
                df_regs['fecha_dt'] = df_regs['fecha'].apply(parse_registro_datetime)
        start_date = reference_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = reference_now.replace(hour=23, minute=59, second=59, microsecond=999999)
        current = start_date
        while current <= end_date:
            if current.weekday() < 5 and not is_feriado(current.date()):
                day_hours = 0
                if not df_regs.empty:
                    mask = df_regs['fecha_dt'].dt.date == current.date()
                    day_hours = float(df_regs.loc[mask, 'tiempo'].sum())
                if day_hours < 4:
                    status = "Sin carga" if day_hours == 0 else f"{day_hours:g}hs"
                    alerts.append(f"{current.strftime('%d/%m')} ({status})")
            current += timedelta(days=1)
    except Exception as e:
        log_app_error(e, module="database", function="_notification_pending_load_alerts")
    return alerts


def _notification_pending_load_candidates(conn):
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute(
        """
        SELECT u.id, u.username, u.nombre, u.apellido, u.email, u.rol_id, COALESCE(r.view_type, '') AS view_type
        FROM usuarios u
        LEFT JOIN roles r ON u.rol_id = r.id_rol
        WHERE u.is_active = TRUE
          AND u.is_admin = FALSE
          AND COALESCE(u.email, '') <> ''
        ORDER BY u.apellido, u.nombre, u.username
        """
    )
    rows = []
    for row in c.fetchall():
        email = _normalize_notification_email(row.get('email'))
        if not email:
            continue
        rows.append({
            'user_id': int(row['id']),
            'email': email,
            'display_name': _notification_compact_name(row.get('nombre'), row.get('apellido'), row.get('username') or email),
            'username': row.get('username') or '',
            'rol_id': int(row['rol_id']) if row.get('rol_id') is not None else None,
        })
    return rows


def _notification_pending_load_period_label(now, frequency):
    if str(frequency or '').strip().lower() == 'weekly':
        week_start = (now - timedelta(days=now.weekday())).date()
        week_end = week_start + timedelta(days=4)
        return f"la semana {week_start.strftime('%d/%m/%Y')} al {week_end.strftime('%d/%m/%Y')}"
    return f"{now.strftime('%B %Y')}"


def _notification_pending_load_period_key(now, frequency):
    if str(frequency or '').strip().lower() == 'weekly':
        iso_year, iso_week, _ = now.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    return now.strftime("%Y-%m-%d")


def _notification_all_active_email_recipients(conn):
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute(
        """
        SELECT id, username, nombre, apellido, email, rol_id
        FROM usuarios
        WHERE is_active = TRUE
          AND COALESCE(email, '') <> ''
        ORDER BY apellido, nombre, username
        """
    )
    recipients = []
    for row in c.fetchall():
        email = _normalize_notification_email(row.get('email'))
        if not email:
            continue
        recipients.append({
            'user_id': int(row['id']),
            'email': email,
            'display_name': _notification_compact_name(row.get('nombre'), row.get('apellido'), row.get('username') or email),
            'rol_id': int(row['rol_id']) if row.get('rol_id') is not None else None,
            'dedupe_key': f"user:{int(row['id'])}",
        })
    return recipients


def _notification_hoy_oficina_presentes(conn, today_date):
    try:
        ensure_user_modality_schedule_exists()
    except Exception:
        pass
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute(
        """
        SELECT s.user_id, u.nombre, u.apellido, u.username, m.descripcion AS modalidad, c.nombre AS cliente_nombre
        FROM user_modalidad_schedule s
        JOIN usuarios u ON s.user_id = u.id
        JOIN modalidades_tarea m ON s.modalidad_id = m.id_modalidad
        LEFT JOIN clientes c ON s.cliente_id = c.id_cliente
        WHERE s.fecha = %s
          AND u.is_active = TRUE
        """,
        (today_date,)
    )
    presentes = []
    for row in c.fetchall():
        modalidad = str(row.get('modalidad') or '').strip().lower()
        cliente_nombre = str(row.get('cliente_nombre') or '').strip()
        cliente_norm = normalize_name(cliente_nombre)
        es_systemscorp = 'SYSTEMSCORP' in cliente_norm
        if modalidad == 'presencial' or (modalidad == 'cliente' and es_systemscorp):
            presentes.append(
                _notification_compact_name(row.get('nombre'), row.get('apellido'), row.get('username') or f"{int(row.get('user_id'))}")
            )
    presentes = sorted({name for name in presentes if str(name).strip()})
    return presentes


def _notification_licencias_semana(conn, week_start, week_end):
    try:
        ensure_vacaciones_schema()
    except Exception:
        pass
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute(
        """
        SELECT v.usuario_id, u.nombre, u.apellido, u.username, v.fecha_inicio, v.fecha_fin, v.tipo
        FROM vacaciones v
        JOIN usuarios u ON v.usuario_id = u.id
        WHERE u.is_active = TRUE
          AND v.fecha_inicio <= %s
          AND v.fecha_fin >= %s
        ORDER BY v.fecha_inicio ASC, u.apellido, u.nombre, u.username
        """,
        (week_end, week_start)
    )
    items = []
    for row in c.fetchall():
        start = row.get('fecha_inicio')
        end = row.get('fecha_fin')
        tipo_raw = str(row.get('tipo') or '').strip()
        tipo_lower = tipo_raw.lower()
        if 'cumple' in tipo_lower:
            tipo_label = 'Día de cumpleaños'
        elif 'licen' in tipo_lower:
            tipo_label = 'Licencia'
        else:
            tipo_label = 'Vacaciones'
        if start and end and str(start) == str(end):
            rango = pd.to_datetime(start).strftime("%d/%m")
        else:
            start_str = pd.to_datetime(start).strftime("%d/%m") if start else "-"
            end_str = pd.to_datetime(end).strftime("%d/%m") if end else "-"
            rango = f"{start_str} al {end_str}"
        display_name = _notification_compact_name(row.get('nombre'), row.get('apellido'), row.get('username') or f"{int(row.get('usuario_id'))}")
        items.append(f"- {display_name} {tipo_label.lower()} {rango}")
    return items


def _notification_process_hoy_en_la_oficina(now, max_emails=None, deadline=None):
    event_key = 'hoy_en_la_oficina'
    policy = get_notification_policy(event_key)
    results = {'sent': 0, 'errors': 0}
    import time as _time
    def _should_stop():
        if deadline is not None and _time.time() >= float(deadline):
            return True
        if max_emails is not None and results['sent'] >= int(max_emails):
            return True
        return False
    if not policy.get('enabled') or not policy.get('email_enabled'):
        return results
    if not _notification_policy_due_now(policy, now):
        return results
    today = now.date()
    week_start = (now - timedelta(days=now.weekday())).date()
    week_end = week_start + timedelta(days=4)
    day_es = {
        'Monday': 'Lunes',
        'Tuesday': 'Martes',
        'Wednesday': 'Miércoles',
        'Thursday': 'Jueves',
        'Friday': 'Viernes',
        'Saturday': 'Sábado',
        'Sunday': 'Domingo',
    }.get(now.strftime('%A'), now.strftime('%A'))
    hoy_fecha = today.strftime("%d/%m")
    presentes_resumen = "- Sin asignaciones"
    seccion_licencias = ""
    conn = get_connection()
    try:
        presentes = _notification_hoy_oficina_presentes(conn, today)
        if presentes:
            presentes_resumen = "\n".join(f"- {name}" for name in presentes)
        licencias = _notification_licencias_semana(conn, week_start, week_end)
        if licencias:
            seccion_licencias = "De licencia:\n" + "\n".join(licencias) + "\n"
        recipients = _notification_all_active_email_recipients(conn)
        recipients = [r for r in recipients if _notification_policy_allows_recipient(policy, r)]
        frequency = str(policy.get('frequency') or 'daily').strip().lower()
        period_key = today.isoformat()
        payload = {
            'hoy_dia': day_es,
            'hoy_fecha': hoy_fecha,
            'presentes_resumen': presentes_resumen,
            'seccion_licencias': seccion_licencias,
        }
        for recipient in recipients:
            if _should_stop():
                return results
            delivery_dedupe_key = f"{event_key}:{frequency}:{period_key}:user:{recipient['user_id']}"
            if _notification_delivery_exists(conn, delivery_dedupe_key):
                continue
            try:
                _notification_send_for_recipient(
                    conn,
                    event_key,
                    frequency,
                    payload,
                    recipient,
                    delivery_dedupe_key,
                    source_queue_id=None,
                    now=now,
                )
                conn.commit()
                results['sent'] += 1
            except Exception as e:
                conn.rollback()
                results['errors'] += 1
                log_app_error(e, module="database", function="_notification_process_hoy_en_la_oficina")
        return results
    finally:
        conn.close()


def _notification_process_tecnicos_carga_incompleta(now, max_emails=None, deadline=None):
    event_key = 'tecnicos_carga_incompleta'
    policy = get_notification_policy(event_key)
    results = {'sent': 0, 'errors': 0}
    import time as _time
    def _should_stop():
        if deadline is not None and _time.time() >= float(deadline):
            return True
        if max_emails is not None and results['sent'] >= int(max_emails):
            return True
        return False
    if not policy.get('enabled') or not policy.get('email_enabled'):
        return results
    if not _notification_policy_due_now(policy, now):
        return results

    frequency = str(policy.get('frequency') or 'daily').strip().lower()
    period_key = _notification_pending_load_period_key(now, frequency)
    period_label = _notification_pending_load_period_label(now, frequency)

    conn = get_connection()
    try:
        tecnicos = _notification_pending_load_candidates(conn)
        tecnicos_con_alertas = []
        for tecnico in tecnicos:
            alerts = _notification_pending_load_alerts(tecnico['user_id'], reference_now=now)
            if alerts:
                tecnicos_con_alertas.append((tecnico, alerts))

        if not tecnicos_con_alertas:
            return results

        tecnicos_con_alertas.sort(key=lambda pair: (-len(pair[1]), str(pair[0].get('display_name') or '').casefold()))

        resumen_tecnicos = "\n".join(
            f"- {tecnico['display_name']} ({len(alerts)})"
            for tecnico, alerts in tecnicos_con_alertas
        )
        detalle_blocks = []
        for tecnico, alerts in tecnicos_con_alertas:
            detalle_blocks.append(
                f"{tecnico['display_name']} ({len(alerts)}):\n" + "\n".join(f"- {item}" for item in alerts)
            )
        detalle_tecnicos = "\n\n".join(detalle_blocks)

        recipients = _notification_all_active_email_recipients(conn)
        recipients = [r for r in recipients if _notification_policy_allows_recipient(policy, r)]

        payload = {
            'periodo': period_label,
            'umbral_horas': 4,
            'cantidad_tecnicos': len(tecnicos_con_alertas),
            'resumen_tecnicos': resumen_tecnicos,
            'detalle_tecnicos': detalle_tecnicos,
        }

        for recipient in recipients:
            if _should_stop():
                return results
            delivery_dedupe_key = f"{event_key}:{frequency}:{period_key}:user:{recipient['user_id']}"
            if _notification_delivery_exists(conn, delivery_dedupe_key):
                continue
            try:
                _notification_send_for_recipient(
                    conn,
                    event_key,
                    frequency,
                    payload,
                    recipient,
                    delivery_dedupe_key,
                    source_queue_id=None,
                    now=now,
                )
                conn.commit()
                results['sent'] += 1
            except Exception as e:
                conn.rollback()
                results['errors'] += 1
                log_app_error(e, module="database", function="_notification_process_tecnicos_carga_incompleta")

        return results
    finally:
        conn.close()


def _notification_process_pending_load(now, max_emails=None, deadline=None):
    event_key = 'dia_pendiente_carga'
    policy = get_notification_policy(event_key)
    results = {'sent': 0, 'errors': 0}
    import time as _time
    def _should_stop():
        if deadline is not None and _time.time() >= float(deadline):
            return True
        if max_emails is not None and results['sent'] >= int(max_emails):
            return True
        return False
    if not policy.get('enabled') or not policy.get('email_enabled'):
        return results
    if not _notification_policy_due_now(policy, now):
        return results
    conn = get_connection()
    try:
        recipients = _notification_pending_load_candidates(conn)
        recipients = [r for r in recipients if _notification_policy_allows_recipient(policy, r)]
        frequency = str(policy.get('frequency') or 'daily').strip().lower()
        period_key = _notification_pending_load_period_key(now, frequency)
        period_label = _notification_pending_load_period_label(now, frequency)
        for recipient in recipients:
            if _should_stop():
                return results
            alerts = _notification_pending_load_alerts(recipient['user_id'], reference_now=now)
            if not alerts:
                continue
            delivery_dedupe_key = f"{event_key}:{frequency}:{period_key}:user:{recipient['user_id']}"
            if _notification_delivery_exists(conn, delivery_dedupe_key):
                continue
            payload = {
                'usuario': recipient['display_name'],
                'periodo': period_label,
                'cantidad_alertas': len(alerts),
                'resumen_alertas': "\n".join(f"- {item}" for item in alerts),
                'detalle': 'Se detectaron jornadas hábiles con menos de 4 horas registradas.',
            }
            try:
                _notification_send_for_recipient(
                    conn,
                    event_key,
                    frequency,
                    payload,
                    recipient,
                    delivery_dedupe_key,
                    source_queue_id=None,
                    now=now,
                )
                conn.commit()
                results['sent'] += 1
            except Exception as e:
                conn.rollback()
                results['errors'] += 1
                log_app_error(e, module="database", function="_notification_process_pending_load")
        return results
    finally:
        conn.close()


def process_automatic_notifications(now=None, max_seconds=2.0, max_emails=15):
    now = now or datetime.now()
    if not _notification_is_smtp_ready():
        return {'sent': 0, 'processed': 0, 'discarded': 0, 'errors': 0}
    ensure_notifications_schema()
    import time as _time
    start_ts = _time.time()
    deadline = None
    try:
        max_seconds = float(max_seconds) if max_seconds is not None else None
        if max_seconds and max_seconds > 0:
            deadline = start_ts + max_seconds
    except Exception:
        deadline = None
    try:
        max_emails = int(max_emails) if max_emails is not None else None
    except Exception:
        max_emails = None
    lock_conn = get_connection()
    lock_key = 874221
    try:
        c = lock_conn.cursor()
        c.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
        lock_row = c.fetchone()
        if not lock_row or not bool(lock_row[0]):
            return {'sent': 0, 'processed': 0, 'discarded': 0, 'errors': 0}
        remaining = max_emails
        event_results = _notification_process_event_queue(now, max_emails=remaining, deadline=deadline)
        if remaining is not None:
            remaining = max(0, remaining - int(event_results.get('sent', 0)))
        office_results = _notification_process_hoy_en_la_oficina(now, max_emails=remaining, deadline=deadline)
        if remaining is not None:
            remaining = max(0, remaining - int(office_results.get('sent', 0)))
        supervisor_results = _notification_process_tecnicos_carga_incompleta(now, max_emails=remaining, deadline=deadline)
        if remaining is not None:
            remaining = max(0, remaining - int(supervisor_results.get('sent', 0)))
        pending_results = _notification_process_pending_load(now, max_emails=remaining, deadline=deadline)
        return {
            'sent': event_results['sent'] + pending_results['sent'] + office_results['sent'] + supervisor_results['sent'],
            'processed': event_results['processed'],
            'discarded': event_results['discarded'],
            'errors': event_results['errors'] + pending_results['errors'] + office_results['errors'] + supervisor_results['errors'],
        }
    finally:
        try:
            c = lock_conn.cursor()
            c.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
        except Exception:
            pass
        lock_conn.close()


def ensure_maintenance_schema(conn=None):
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS maintenance_flags (
                key VARCHAR(200) PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                details TEXT
            )
            """
        )
        conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_sql_error(f"Error asegurando esquema de mantenimiento: {e}")
        raise
    finally:
        if close_conn:
            conn.close()


def _maintenance_lock_key(key: str) -> int:
    value = zlib.crc32(str(key or "").encode("utf-8")) & 0xFFFFFFFF
    return int(value)


def run_maintenance_once(key: str, fn, details: str | None = None) -> bool:
    ensure_maintenance_schema()
    conn = get_connection()
    lock_key = _maintenance_lock_key(key)
    try:
        c = conn.cursor()
        c.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
        row = c.fetchone()
        if not row or not bool(row[0]):
            return False

        c.execute("SELECT 1 FROM maintenance_flags WHERE key = %s LIMIT 1", (str(key),))
        if c.fetchone():
            return False

        try:
            fn()
        except Exception as e:
            log_app_error(e, module="database", function="run_maintenance_once")
            return False

        c.execute(
            "INSERT INTO maintenance_flags (key, details) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
            (str(key), str(details or "").strip() or None),
        )
        conn.commit()
        return True
    finally:
        try:
            c = conn.cursor()
            c.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
        except Exception:
            pass
        conn.close()


def send_test_notification_email():
    recipient_email = _normalize_notification_email(SMTP_CONFIG.get('user') or SMTP_CONFIG.get('from_email'))
    if not recipient_email:
        raise RuntimeError("Configura el usuario SMTP o el correo remitente antes de enviar la prueba.")
    subject = "Prueba de correo SMTP - SIGO"
    body = (
        "Hola,\n\n"
        "Este es un mensaje de prueba enviado desde la configuración SMTP de SIGO.\n\n"
        f"Servidor: {str(SMTP_CONFIG.get('host') or '').strip()}\n"
        f"Puerto: {str(SMTP_CONFIG.get('port') or '').strip()}\n"
        f"Seguridad: {str(SMTP_CONFIG.get('security') or '').strip().upper()}\n"
        f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        "Si recibiste este correo, el envío está funcionando correctamente."
    )
    _notification_send_email(recipient_email, subject, body)
    return recipient_email


def get_current_project_id_sequence(conn=None):
    """Obtiene el último valor de la secuencia de IDs de proyectos"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    try:
        c = conn.cursor()
        # En PostgreSQL, last_value es el último valor emitido. 
        # Si queremos saber el próximo, normalmente es last_value + 1 (si is_called es true)
        # Pero para configuración, mostrar el último valor generado o el actual es útil.
        
        # 1. Obtener nombre de la secuencia de forma segura
        c.execute("SELECT pg_get_serial_sequence('proyectos', 'id')")
        row_seq = c.fetchone()
        
        if row_seq and row_seq[0]:
            seq_name = row_seq[0]
            # 2. Consultar valor actual directamente de la secuencia
            # Usamos SQL dinámico seguro porque seq_name viene de pg_get_serial_sequence
            query = f"SELECT last_value FROM {seq_name}"
            c.execute(query)
            row = c.fetchone()
            if row:
                return row[0]
        
        return 0
    except Exception as e:
        log_sql_error(f"Error obteniendo secuencia de proyectos: {e}")
        return 0
    finally:
        if close_conn:
            conn.close()

def get_user_info_safe(user_id):
    """Obtiene información del usuario de manera segura"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT id, username, is_admin, rol_id, nombre, apellido, email
            FROM usuarios 
            WHERE id = %s AND is_active = TRUE
        """, (user_id,))
        result = c.fetchone()
        conn.close()
        
        if result:
            return {
                'id': result[0],
                'username': result[1],
                'is_admin': result[2],
                'rol_id': result[3],
                'nombre': result[4] or '',
                'apellido': result[5] or '',
                'email': result[6] or ''
            }
        return None
    except Exception as e:
        log_sql_error(f"Error en get_user_info_safe: {e}")
        return None

def set_project_id_sequence(new_start_value, conn=None):
    """Establece el valor de reinicio de la secuencia de IDs de proyectos"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
        conn.autocommit = True # Necesario para setval a veces, o commit explícito
    
    try:
        c = conn.cursor()
        # setval(sequence, value, is_called)
        # Si is_called es false, el próximo nextval devolverá value.
        # Si is_called es true (default), el próximo nextval devolverá value + increment.
        # Queremos que el PRÓXIMO proyecto tenga el ID new_start_value.
        # Entonces usamos is_called=false.
        
        # Primero obtenemos el nombre de la secuencia dinámicamente para ser seguros
        c.execute("SELECT pg_get_serial_sequence('proyectos', 'id')")
        seq_name = c.fetchone()[0]
        
        if seq_name:
            query = f"SELECT setval('{seq_name}', %s, false)"
            c.execute(query, (new_start_value,))
            return True, f"Secuencia actualizada. El próximo proyecto tendrá ID {new_start_value}."
        else:
            return False, "No se encontró la secuencia de proyectos."
            
    except Exception as e:
        log_sql_error(f"Error actualizando secuencia de proyectos: {e}")
        return False, str(e)
    finally:
        if close_conn:
            conn.close()


def ensure_contactos_schema():
    """Asegura el esquema de la tabla contactos"""
    conn = get_connection()
    try:
        conn.autocommit = True
        c = conn.cursor()
        for ddl in [
            "ALTER TABLE contactos ADD COLUMN IF NOT EXISTS celular VARCHAR(50)",
            "ALTER TABLE contactos ADD COLUMN IF NOT EXISTS notes TEXT",
            "ALTER TABLE contactos ADD COLUMN IF NOT EXISTS direccion VARCHAR(300)", # Re-ensure just in case
        ]:
            try:
                c.execute(ddl)
            except Exception:
                pass
    finally:
        conn.close()

def ensure_clientes_schema():
    """Asegura que la tabla clientes tenga todas las columnas necesarias"""
    conn = get_connection()
    try:
        # Usar autocommit para evitar problemas de transacción con DDLs
        conn.autocommit = True
        c = conn.cursor()
        for ddl in [
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS cuit VARCHAR(32)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS alias VARCHAR(200)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS celular VARCHAR(20)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS web VARCHAR(300)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS organizacion VARCHAR(300)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS email VARCHAR(100)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS telefono VARCHAR(50)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS direccion VARCHAR(300)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS notes TEXT"
        ]:
            try:
                c.execute(ddl)
            except Exception as e:
                log_sql_error(f"Error ejecutando DDL en clientes: {e}")
        
        try:
            c.execute("ALTER TABLE clientes ALTER COLUMN celular TYPE VARCHAR(30)")
        except Exception:
            pass
                
    except Exception as e:
        log_sql_error(f"Error asegurando esquema de clientes: {e}")
    finally:
        conn.close()


def ensure_cliente_solicitudes_schema():
    """Asegura que la tabla cliente_solicitudes tenga todas las columnas necesarias"""
    conn = get_connection()
    try:
        conn.autocommit = True
        c = conn.cursor()
        
        # Crear tabla si no existe
        c.execute('''
            CREATE TABLE IF NOT EXISTS cliente_solicitudes (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                organizacion VARCHAR(200),
                telefono VARCHAR(50),
                email VARCHAR(100),
                cuit VARCHAR(32),
                celular VARCHAR(20),
                web VARCHAR(300),
                tipo VARCHAR(50),
                requested_by INTEGER NOT NULL REFERENCES usuarios(id),
                estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                temp_cliente_id INTEGER
            )
        ''')
        
        # Asegurar columnas individuales
        ddls = [
            "ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS email VARCHAR(100)",
            "ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS cuit VARCHAR(32)",
            "ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS celular VARCHAR(20)",
            "ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS web VARCHAR(300)",
            "ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS tipo VARCHAR(50)",
            "ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS temp_cliente_id INTEGER",
            "ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS notes TEXT"
        ]
        
        for ddl in ddls:
            try:
                c.execute(ddl)
            except Exception as e:
                log_sql_error(f"Error executing DDL '{ddl}': {e}")
                
    except Exception as e:
        log_sql_error(f"Error asegurando esquema de cliente_solicitudes: {e}")
    finally:
        conn.close()


def ensure_projects_schema(conn=None):
    """Crea las tablas relacionadas con proyectos si no existen"""
    try:
        if conn is None:
            conn = get_connection()
            # Usar autocommit para operaciones DDL y evitar transacciones abortadas
            try:
                conn.autocommit = True
            except Exception:
                pass
            close_conn = True
        else:
            close_conn = False

        c = conn.cursor()
        try:
            c.execute('''
                CREATE TABLE IF NOT EXISTS marcas (
                    id_marca SERIAL PRIMARY KEY,
                    nombre VARCHAR(100) UNIQUE NOT NULL
                )
            ''')
        except Exception as e:
            log_sql_error(f"No se pudo asegurar tabla marcas: {e}")
        
        try:
            c.execute("ALTER TABLE marcas ADD COLUMN IF NOT EXISTS activa BOOLEAN DEFAULT TRUE")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE marcas ADD COLUMN IF NOT EXISTS cuit VARCHAR(32)")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE marcas ADD COLUMN IF NOT EXISTS email VARCHAR(200)")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE marcas ADD COLUMN IF NOT EXISTS telefono VARCHAR(100)")
        except Exception:
            pass
        try:
             c.execute("ALTER TABLE marcas ALTER COLUMN telefono TYPE VARCHAR(100)")
        except Exception:
             pass
        try:
            c.execute("ALTER TABLE marcas ADD COLUMN IF NOT EXISTS celular VARCHAR(50)")
        except Exception:
            pass
        # Ensure celular is large enough
        try:
            c.execute("ALTER TABLE marcas ALTER COLUMN celular TYPE VARCHAR(50)")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE marcas ADD COLUMN IF NOT EXISTS web VARCHAR(300)")
        except Exception:
            pass

        # Tabla de contactos (asociables a clientes o marcas)
        try:
            c.execute('''
                CREATE TABLE IF NOT EXISTS contactos (
                    id_contacto SERIAL PRIMARY KEY,
                    nombre VARCHAR(100) NOT NULL,
                    apellido VARCHAR(100),
                    puesto VARCHAR(100),
                    telefono VARCHAR(50),
                    email VARCHAR(200),
                    direccion VARCHAR(300),
                    notes TEXT,
                    etiqueta_tipo VARCHAR(20) NOT NULL CHECK (etiqueta_tipo IN ('cliente','marca')),
                    etiqueta_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Ensure column notes if table exists
            c.execute("ALTER TABLE contactos ADD COLUMN IF NOT EXISTS notes TEXT")
        except Exception as e:
            log_sql_error(f"No se pudo asegurar tabla contactos: {e}")
        c.execute('''
            CREATE TABLE IF NOT EXISTS proyectos (
                id SERIAL PRIMARY KEY,
                owner_user_id INTEGER NOT NULL REFERENCES usuarios(id),
                cliente_id INTEGER NULL REFERENCES clientes(id_cliente),
                titulo VARCHAR(200) NOT NULL,
                descripcion TEXT,
                estado VARCHAR(20) NOT NULL DEFAULT 'Prospecto',
                valor INTEGER NULL,
                moneda VARCHAR(10),
                etiqueta VARCHAR(100),
                probabilidad INTEGER,
                embudo VARCHAR(200),
                marca_id INTEGER NULL REFERENCES marcas(id_marca),
                fecha_cierre DATE,
                trato_id BIGINT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Constraint de estado permitido: forzar recreación para asegurar conjunto correcto
        try:
            c.execute("ALTER TABLE proyectos DROP CONSTRAINT IF EXISTS proyectos_estado_check")
            c.execute("ALTER TABLE proyectos ADD CONSTRAINT proyectos_estado_check CHECK (estado IN ('Prospecto','Presupuestado','Negociación','Objeción','Ganado','Perdido','Abierto','En Progreso'))")
        except Exception as e:
            log_sql_error(f"No se pudo asegurar constraint proyectos_estado_check: {e}")
        try:
            c.execute("ALTER TABLE proyectos ALTER COLUMN estado SET DEFAULT 'Prospecto'")
        except Exception:
            pass

        c.execute('''
            CREATE TABLE IF NOT EXISTS proyecto_compartidos (
                proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES usuarios(id),
                shared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (proyecto_id, user_id)
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS proyecto_documentos (
                id SERIAL PRIMARY KEY,
                proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
                filename VARCHAR(255) NOT NULL,
                file_path TEXT NOT NULL,
                mime_type VARCHAR(100),
                file_size INTEGER,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        try:
            c.execute("ALTER TABLE proyecto_documentos ADD COLUMN IF NOT EXISTS is_vigente BOOLEAN NOT NULL DEFAULT TRUE")
        except Exception:
            pass

        try:
            c.execute("ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS valor BIGINT")
        except Exception:
            pass
        # Asegurar tipo BIGINT para evitar overflow
        try:
            c.execute("ALTER TABLE proyectos ALTER COLUMN valor TYPE BIGINT USING valor::bigint")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS moneda VARCHAR(10)")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS etiqueta VARCHAR(100)")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS probabilidad INTEGER")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS tipo_venta VARCHAR(40)")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos DROP CONSTRAINT IF EXISTS proyectos_tipo_venta_check")
            c.execute("ALTER TABLE proyectos ADD CONSTRAINT proyectos_tipo_venta_check CHECK (tipo_venta IS NULL OR tipo_venta IN ('Venta de equipo','Licencia','Soporte y mantenimiento','Servicios','Contratos'))")
        except Exception as e:
            log_sql_error(f"No se pudo asegurar constraint proyectos_tipo_venta_check: {e}")
        try:
            c.execute("ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS embudo VARCHAR(200)")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS fecha_cierre DATE")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS trato_id BIGINT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos DROP CONSTRAINT IF EXISTS proyectos_trato_id_unique")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos ADD CONSTRAINT proyectos_trato_id_unique UNIQUE (trato_id)")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS marca_id INTEGER")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS contacto_id INTEGER")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos DROP CONSTRAINT IF EXISTS proyectos_marca_fk")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos ADD CONSTRAINT proyectos_marca_fk FOREIGN KEY (marca_id) REFERENCES marcas(id_marca) ON DELETE SET NULL")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos DROP CONSTRAINT IF EXISTS proyectos_contacto_fk")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE proyectos ADD CONSTRAINT proyectos_contacto_fk FOREIGN KEY (contacto_id) REFERENCES contactos(id_contacto) ON DELETE SET NULL")
        except Exception:
            pass

        try:
            c.execute("ALTER TABLE proyectos ALTER COLUMN owner_user_id DROP NOT NULL")
        except Exception as e:
            # log_sql_error(f"No se pudo alterar owner_user_id a NULL (puede que ya sea nullable): {e}")
            pass

        # Si autocommit no está habilitado (conn provisto externamente), confirmar cambios
        try:
            if not getattr(conn, 'autocommit', False):
                conn.commit()
        except Exception:
            pass
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_sql_error(f"Error asegurando esquema de proyectos: {e}")
    finally:
        if 'close_conn' in locals() and close_conn:
            conn.close()


def create_proyecto(owner_user_id, titulo, descripcion, cliente_id=None, estado='activo', valor=None, moneda=None, etiqueta=None, probabilidad=None, embudo=None, fecha_cierre=None, marca_id=None, contacto_id=None, tipo_venta=None):
    """Crea un proyecto y retorna su ID"""
    ensure_projects_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO proyectos (owner_user_id, cliente_id, titulo, descripcion, estado, valor, moneda, etiqueta, probabilidad, embudo, fecha_cierre, marca_id, contacto_id, tipo_venta)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            int(owner_user_id),
            cliente_id,
            str(titulo).strip(),
            str(descripcion or '').strip(),
            str(estado).strip(),
            valor,
            moneda,
            etiqueta,
            probabilidad,
            embudo,
            fecha_cierre,
            marca_id,
            contacto_id,
            tipo_venta,
        ))
        pid = c.fetchone()[0]
        
        # Asegurar que trato_id tenga valor (usamos el mismo ID generado) para consistencia
        c.execute("UPDATE proyectos SET trato_id = id WHERE id = %s AND trato_id IS NULL", (pid,))
        
        conn.commit()
        return int(pid)
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error creando proyecto: {e}")
        return None
    finally:
        conn.close()

def ensure_feriados_schema():
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS feriados (
                id SERIAL PRIMARY KEY,
                fecha DATE NOT NULL UNIQUE,
                nombre VARCHAR(200) NOT NULL,
                tipo VARCHAR(20),
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        return True
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_sql_error(f"Error asegurando feriados: {e}")
        return False
    finally:
        conn.close()

def get_feriados_dataframe(year=None, include_inactive=False):
    ensure_feriados_schema()
    engine = get_engine()
    base = "SELECT id, fecha, nombre, tipo, activo, created_at FROM feriados"
    where = []
    params = {}
    if year:
        where.append("EXTRACT(YEAR FROM fecha) = :year")
        params["year"] = int(year)
    if not include_inactive:
        where.append("activo IS TRUE")
    query = base + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY fecha"
    try:
        return pd.read_sql_query(text(query), con=engine, params=params if params else None)
    except Exception:
        return pd.DataFrame()

def add_feriado(fecha, nombre, tipo="nacional", activo=True):
    ensure_feriados_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO feriados (fecha, nombre, tipo, activo)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (fecha) DO UPDATE SET nombre = EXCLUDED.nombre, tipo = EXCLUDED.tipo, activo = EXCLUDED.activo
            RETURNING id
            """,
            (fecha, str(nombre).strip(), str(tipo or "").strip() or None, bool(activo))
        )
        row = c.fetchone()
        conn.commit()
        return int(row[0]) if row else None
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_sql_error(f"Error agregando feriado: {e}")
        return None
    finally:
        conn.close()

def toggle_feriado(feriado_id, activo=True):
    ensure_feriados_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE feriados SET activo = %s WHERE id = %s", (bool(activo), int(feriado_id)))
        conn.commit()
        return True
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_sql_error(f"Error actualizando feriado: {e}")
        return False
    finally:
        conn.close()

def delete_feriado(feriado_id):
    ensure_feriados_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM feriados WHERE id = %s", (int(feriado_id),))
        conn.commit()
        return True
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_sql_error(f"Error eliminando feriado: {e}")
        return False
    finally:
        conn.close()

def is_feriado(d):
    ensure_feriados_schema()
    try:
        engine = get_engine()
        q = text("SELECT 1 FROM feriados WHERE fecha = :f AND activo IS TRUE LIMIT 1")
        df = pd.read_sql_query(q, con=engine, params={"f": pd.to_datetime(d).date()})
        return not df.empty
    except Exception:
        return False


def update_proyecto(project_id, owner_user_id, titulo=None, descripcion=None, cliente_id=None, estado=None, valor=None, moneda=None, etiqueta=None, probabilidad=None, embudo=None, fecha_cierre=None, marca_id=None, contacto_id=None, tipo_venta=None, bypass_owner=False):
    """Actualiza campos de un proyecto del propietario (o admin si bypass_owner=True)"""
    ensure_projects_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        sets = []
        params = []
        if titulo is not None:
            sets.append("titulo = %s")
            params.append(str(titulo).strip())
        if descripcion is not None:
            sets.append("descripcion = %s")
            params.append(str(descripcion or '').strip())
        if cliente_id is not None:
            sets.append("cliente_id = %s")
            params.append(cliente_id)
        if estado is not None:
            sets.append("estado = %s")
            params.append(str(estado).strip())
        if valor is not None:
            sets.append("valor = %s")
            params.append(valor)
        if moneda is not None:
            sets.append("moneda = %s")
            params.append(moneda)
        if etiqueta is not None:
            sets.append("etiqueta = %s")
            params.append(etiqueta)
        if probabilidad is not None:
            sets.append("probabilidad = %s")
            params.append(int(probabilidad))
        if embudo is not None:
            sets.append("embudo = %s")
            params.append(embudo)
        if fecha_cierre is not None:
            sets.append("fecha_cierre = %s")
            params.append(fecha_cierre)
        if marca_id is not None:
            sets.append("marca_id = %s")
            params.append(int(marca_id))
        if contacto_id is not None:
            sets.append("contacto_id = %s")
            params.append(int(contacto_id))
        if tipo_venta is not None:
            sets.append("tipo_venta = %s")
            params.append(tipo_venta)
        if not sets:
            return False

        if bypass_owner:
            sql = f"UPDATE proyectos SET {', '.join(sets)}, updated_at = CURRENT_TIMESTAMP WHERE id = %s"
            params.append(int(project_id))
        else:
            sql = f"UPDATE proyectos SET {', '.join(sets)}, updated_at = CURRENT_TIMESTAMP WHERE id = %s AND owner_user_id = %s"
            params.extend([int(project_id), int(owner_user_id)])
        c.execute(sql, tuple(params))
        conn.commit()
        updated = c.rowcount > 0
        if updated and estado is not None:
            estado_norm = str(estado).strip().lower()
            if estado_norm in {"ganado", "perdido", "cerrado", "cancelado / cerrado"}:
                try:
                    from .quotes_data import close_quotes_for_project

                    close_quotes_for_project(project_id)
                except Exception as sync_exc:
                    log_sql_error(f"Error sincronizando cierre de cotizaciones del trato {project_id}: {sync_exc}")
        return updated
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error actualizando proyecto: {e}")
        return False
    finally:
        conn.close()


def delete_proyecto(project_id, owner_user_id, bypass_owner=False):
    """Elimina un proyecto del propietario (o admin si bypass_owner=True)"""
    ensure_projects_schema()
    conn = get_connection()
    file_paths_to_delete = []
    quote_ids = []
    try:
        c = conn.cursor()
        if bypass_owner:
            c.execute("SELECT id FROM proyectos WHERE id = %s", (int(project_id),))
        else:
            c.execute(
                "SELECT id FROM proyectos WHERE id = %s AND owner_user_id = %s",
                (int(project_id), int(owner_user_id)),
            )
        project_row = c.fetchone()
        if not project_row:
            return False

        c.execute(
            """
            SELECT file_path
            FROM proyecto_documentos
            WHERE proyecto_id = %s
            """,
            (int(project_id),),
        )
        file_paths_to_delete.extend(
            str(row[0]).strip()
            for row in c.fetchall()
            if row and str(row[0] or "").strip()
        )

        c.execute(
            """
            SELECT id
            FROM cotizaciones
            WHERE proyecto_id = %s
            """,
            (int(project_id),),
        )
        quote_ids = [int(row[0]) for row in c.fetchall() if row and row[0] is not None]

        if quote_ids:
            c.execute(
                """
                SELECT d.file_path
                FROM cotizacion_documentos d
                JOIN cotizaciones c ON c.id = d.cotizacion_id
                WHERE c.proyecto_id = %s
                """,
                (int(project_id),),
            )
            file_paths_to_delete.extend(
                str(row[0]).strip()
                for row in c.fetchall()
                if row and str(row[0] or "").strip()
            )

        if bypass_owner:
            c.execute("DELETE FROM proyectos WHERE id = %s", (int(project_id),))
        else:
            c.execute("DELETE FROM proyectos WHERE id = %s AND owner_user_id = %s", (int(project_id), int(owner_user_id)))
        conn.commit()
        deleted = c.rowcount > 0
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error borrando proyecto: {e}")
        return False
    finally:
        conn.close()
    if not deleted:
        return False

    project_upload_dir = os.path.join(PROJECT_UPLOADS_DIR, str(project_id))
    quote_root_dir = os.path.join(PROJECT_UPLOADS_DIR, "cotizaciones")
    stop_dirs = [PROJECT_UPLOADS_DIR, quote_root_dir]

    for file_path in file_paths_to_delete:
        try:
            if not _is_path_within(PROJECT_UPLOADS_DIR, file_path):
                continue
            if os.path.isfile(file_path):
                os.remove(file_path)
            _remove_empty_dirs_upwards(os.path.dirname(file_path), stop_dirs=stop_dirs)
        except Exception:
            pass

    _remove_empty_dirs_upwards(project_upload_dir, stop_dirs=stop_dirs)
    for quote_id in quote_ids:
        _remove_empty_dirs_upwards(
            os.path.join(quote_root_dir, str(int(quote_id))),
            stop_dirs=stop_dirs,
        )

    return True


def get_proyecto(project_id):
    """Obtiene un proyecto por ID"""
    ensure_projects_schema()
    engine = get_engine()
    try:
        df = pd.read_sql_query(text("""
            SELECT p.*, c.nombre AS cliente_nombre, c.alias AS cliente_alias, m.nombre AS marca_nombre, 
                   ct.nombre AS contacto_nombre, ct.apellido AS contacto_apellido, ct.puesto AS contacto_puesto,
                   ct.email AS contacto_email, ct.telefono AS contacto_telefono, ct.direccion AS contacto_direccion
            FROM proyectos p
            LEFT JOIN clientes c ON p.cliente_id = c.id_cliente
            LEFT JOIN marcas m ON p.marca_id = m.id_marca
            LEFT JOIN contactos ct ON p.contacto_id = ct.id_contacto
            WHERE p.id = :pid
        """), con=engine, params={"pid": int(project_id)})
        return df.iloc[0].to_dict() if not df.empty else None
    except Exception as e:
        log_sql_error(f"Error obteniendo proyecto: {e}")
        return None


def get_all_proyectos(filter_user_ids=None, include_unassigned=False):
    """Lista todos los proyectos, opcionalmente filtrados por una lista de IDs de usuario"""
    # Force reload check
    # print(f"DEBUG: get_all_proyectos called with include_unassigned={include_unassigned}")
    ensure_projects_schema()
    engine = get_engine()
    try:
        query = """
            SELECT p.*, c.nombre AS cliente_nombre, c.alias AS cliente_alias, m.nombre AS marca_nombre,
                   TRIM(CONCAT(u.nombre, ' ', u.apellido)) as usuario_nombre,
                   TRIM(CONCAT(co.nombre, ' ', COALESCE(co.apellido, ''))) as contacto_nombre_completo
            FROM proyectos p
            LEFT JOIN clientes c ON p.cliente_id = c.id_cliente
            LEFT JOIN marcas m ON p.marca_id = m.id_marca
            LEFT JOIN usuarios u ON p.owner_user_id = u.id
            LEFT JOIN contactos co ON p.contacto_id = co.id_contacto
        """
        params = {}
        if filter_user_ids:
            if include_unassigned:
                query += " WHERE (p.owner_user_id IN :uids OR p.owner_user_id IS NULL)"
            else:
                query += " WHERE p.owner_user_id IN :uids"
            params["uids"] = tuple(filter_user_ids)
        elif include_unassigned and not filter_user_ids:
             # Si no hay filtro de usuarios, pero se pide incluir no asignados, no se hace nada especial
             # porque la query base ya trae todo (incluidos los NULL)
             pass
            
        query += " ORDER BY p.created_at DESC"
        
        df = pd.read_sql_query(text(query), con=engine, params=params)
        return df
    except Exception as e:
        log_sql_error(f"Error listando todos los proyectos: {e}")
        return pd.DataFrame()


def get_proyectos_by_owner(owner_user_id):
    """Lista proyectos de un propietario"""
    ensure_projects_schema()
    engine = get_engine()
    try:
        df = pd.read_sql_query(text("""
            SELECT p.*, c.nombre AS cliente_nombre, c.alias AS cliente_alias, m.nombre AS marca_nombre
            FROM proyectos p
            LEFT JOIN clientes c ON p.cliente_id = c.id_cliente
            LEFT JOIN marcas m ON p.marca_id = m.id_marca
            WHERE p.owner_user_id = :uid
            ORDER BY p.created_at DESC
        """), con=engine, params={"uid": int(owner_user_id)})
        return df
    except Exception as e:
        log_sql_error(f"Error listando proyectos del dueño: {e}")
        return pd.DataFrame()


def get_proyectos_shared_with_user(user_id):
    """Lista proyectos compartidos con un usuario"""
    ensure_projects_schema()
    engine = get_engine()
    try:
        df = pd.read_sql_query(text("""
            SELECT p.*, c.nombre AS cliente_nombre, c.alias AS cliente_alias, m.nombre AS marca_nombre
            FROM proyecto_compartidos s
            JOIN proyectos p ON p.id = s.proyecto_id
            LEFT JOIN clientes c ON p.cliente_id = c.id_cliente
            LEFT JOIN marcas m ON p.marca_id = m.id_marca
            WHERE s.user_id = :uid
            ORDER BY p.updated_at DESC
        """), con=engine, params={"uid": int(user_id)})
        return df
    except Exception as e:
        log_sql_error(f"Error listando proyectos compartidos: {e}")
        return pd.DataFrame()


def set_proyecto_shares(project_id, owner_user_id, user_ids, bypass_owner=False):
    """Establece usuarios con acceso compartido a un proyecto (o admin si bypass_owner=True)"""
    ensure_projects_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        # Verificar propiedad
        if not bypass_owner:
            c.execute("SELECT 1 FROM proyectos WHERE id = %s AND owner_user_id = %s", (int(project_id), int(owner_user_id)))
            if not c.fetchone():
                return False

        # Limpiar actuales y setear nuevos (idempotente)
        c.execute("DELETE FROM proyecto_compartidos WHERE proyecto_id = %s", (int(project_id),))
        for uid in set(int(u) for u in (user_ids or [])):
            c.execute("""
                INSERT INTO proyecto_compartidos (proyecto_id, user_id)
                VALUES (%s, %s)
                ON CONFLICT (proyecto_id, user_id) DO NOTHING
            """, (int(project_id), int(uid)))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error estableciendo compartidos: {e}")
        return False
    finally:
        conn.close()

def get_proyecto_shared_users(project_id):
    """Obtiene la lista de IDs de usuarios con los que se comparte un proyecto"""
    ensure_projects_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT user_id FROM proyecto_compartidos WHERE proyecto_id = %s", (int(project_id),))
        rows = c.fetchall()
        return [r[0] for r in rows]
    except Exception as e:
        log_sql_error(f"Error obteniendo usuarios compartidos: {e}")
        return []
    finally:
        conn.close()

def add_registros_comerciales_batch(df, default_user_id=None):
    """
    Importa registros comerciales desde un DataFrame.
    Retorna (count_success, errors_list).
    """
    import unicodedata
    
    conn = get_connection()
    c = conn.cursor()
    success_count = 0
    errors = []
    
    # Ensure schemas once
    ensure_projects_schema()
    ensure_contactos_schema()
    
    # Pre-fetch users for mapping
    try:
        users_df = get_users_dataframe()
        user_map = {}
        if not users_df.empty:
            for _, row in users_df.iterrows():
                # Map "firstname lastname"
                full_name = f"{row['nombre']} {row['apellido']}".strip().lower()
                user_map[full_name] = row['id']
                # Map "lastname firstname"
                rev_name = f"{row['apellido']} {row['nombre']}".strip().lower()
                user_map[rev_name] = row['id']
                # Map username (exact match)
                if row.get('username'):
                    user_map[str(row['username']).strip().lower()] = row['id']
    except Exception as e:
        log_sql_error(f"Error pre-fetching users: {e}")
        user_map = {}

    def normalize_col(col):
        col = str(col).strip().lower()
        col = unicodedata.normalize('NFD', col)
        col = ''.join(char for char in col if unicodedata.category(char) != 'Mn')
        return col

    # Normalize DataFrame columns
    df.columns = [normalize_col(col) for col in df.columns]
    
    col_map = {
        'trato_id': None,
        'titulo': None,
        'valor': None,
        'moneda': None,
        'fecha_cierre': None,
        'estado': None,
        'cliente': None,
        'propietario': None,
        'probabilidad': None,
        'etiqueta': None,
        'organizacion': None,
        'persona': None,
        'created_at': None,
        'marca': None,
        'apellido': None
    }
    
    for col in df.columns:
        if 'trato - id' in col: col_map['trato_id'] = col
        elif 'trato - titulo' in col: col_map['titulo'] = col
        elif 'trato - título' in col: col_map['titulo'] = col # Explicit accent match
        elif 'titulo' in col and not col_map['titulo']: col_map['titulo'] = col
        elif 'trato - valor' in col: col_map['valor'] = col
        elif 'valor' in col and not col_map['valor']: col_map['valor'] = col
        elif 'trato - moneda' in col: col_map['moneda'] = col
        elif 'moneda' in col and not col_map['moneda']: col_map['moneda'] = col
        elif 'trato - fecha de cierre prevista' in col: col_map['fecha_cierre'] = col
        elif 'fecha prevista' in col: col_map['fecha_cierre'] = col
        elif 'trato - estado' in col: col_map['estado'] = col
        elif 'estado' in col and not col_map['estado']: col_map['estado'] = col
        elif 'trato - propietario' in col: col_map['propietario'] = col
        elif 'propietario' in col and not col_map['propietario']: col_map['propietario'] = col
        elif 'organizacion - nombre' in col: col_map['organizacion'] = col
        elif 'organizacion' in col and not col_map['organizacion']: col_map['organizacion'] = col
        elif 'cliente' in col and not col_map['cliente']: col_map['cliente'] = col
        elif 'persona - nombre' in col: col_map['persona'] = col
        elif 'trato - nombre' in col: col_map['persona'] = col # "Trato - Nombre" es el nombre del contacto, no el título
        elif 'nombre' in col and not col_map['persona']: col_map['persona'] = col
        elif 'contacto' in col and not col_map['persona']: col_map['persona'] = col # Mapear "Contacto" (exportado) a persona
        elif 'apellido' in col: col_map['apellido'] = col
        elif 'trato - probabilidad' in col: col_map['probabilidad'] = col
        elif 'trato - etiqueta' in col: col_map['etiqueta'] = col
        elif 'trato - trato creado' in col: col_map['created_at'] = col
        elif 'fecha creacion' in col: col_map['created_at'] = col
        elif 'marca' in col: col_map['marca'] = col

    for index, row in df.iterrows():
        try:
            trato_id_val = row.get(col_map['trato_id'])
            if pd.isna(trato_id_val):
                continue
            
            try:
                trato_id = int(float(trato_id_val))
            except:
                continue

            titulo = row.get(col_map['titulo'])
            if pd.isna(titulo): titulo = f"Trato {trato_id}"
            
            valor = 0.0
            if col_map['valor']:
                raw_val = row.get(col_map['valor'])
                try:
                    # Normalizar valor
                    val = str(raw_val).strip()
                    val = unicodedata.normalize('NFKD', val)
                    val = val.replace('$', '').replace('ARS', '').replace('USD', '').strip()
                    
                    if not val or val.lower() == 'nan':
                        valor = 0.0
                    else:
                        # Manejo de formatos numéricos (1.000,00 vs 1,000.00)
                        if '.' in val and ',' in val:
                            if val.rfind('.') < val.rfind(','): # Formato 1.000,00 (Europeo/Latam)
                                val = val.replace('.', '').replace(',', '.')
                            else: # Formato 1,000.00 (US)
                                val = val.replace(',', '')
                        elif ',' in val: # Solo coma (1000,00 -> 1000.00)
                            val = val.replace(',', '.')
                        elif '.' in val:
                            # Heurística para miles con punto (ej: 1.200 -> 1200, pero 1.5 -> 1.5)
                            # Si hay puntos y no comas, y los grupos son de 3 dígitos (excepto el primero), asumimos miles
                            parts = val.split('.')
                            if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
                                val = val.replace('.', '')
                        
                        valor = float(val)
                except Exception as e_val:
                    # Log warning but continue
                    errors.append(f"⚠️ Fila {index}: No se pudo parsear valor '{raw_val}' -> 0.0")
                    valor = 0.0
            
            moneda = row.get(col_map['moneda'])
            if pd.isna(moneda): moneda = 'USD'
            
            fecha_cierre = row.get(col_map['fecha_cierre'])
            if pd.isna(fecha_cierre): fecha_cierre = None
            
            created_at_val = None
            if col_map.get('created_at'):
                val = row.get(col_map['created_at'])
                if pd.notna(val):
                    try:
                        created_at_val = pd.to_datetime(val, dayfirst=True)
                    except:
                        created_at_val = val

            estado = row.get(col_map['estado'])
            if pd.isna(estado): estado = 'Abierto'
            
            cliente_id = None
            cliente_nombre = row.get(col_map['organizacion'])
            if pd.isna(cliente_nombre) and col_map['cliente']:
                cliente_nombre = row.get(col_map['cliente'])
                
            if pd.notna(cliente_nombre):
                # Using existing get_or_create_cliente function
                cliente_id = get_or_create_cliente(str(cliente_nombre).strip(), conn=conn)
            
            contacto_id = None
            if cliente_id:
                persona_nombre = None
                persona_apellido = None
                
                # Intentar obtener nombre y apellido de columnas separadas si existen
                if col_map.get('persona'):
                    persona_nombre = row.get(col_map['persona'])
                
                # Buscar columna de apellido
                col_apellido = col_map.get('apellido')
                
                # Si no está mapeada, buscarla (fallback)
                if not col_apellido:
                    for c_name in df.columns:
                        if 'apellido' in str(c_name).lower():
                            col_apellido = c_name
                            break
                
                if col_apellido:
                    val_ap = row.get(col_apellido)
                    if pd.notna(val_ap):
                        persona_apellido = val_ap
                
                if pd.notna(persona_nombre):
                    p_nombre = str(persona_nombre).strip()
                    if p_nombre:
                        c_nombre = p_nombre
                        c_apellido = ''
                        
                        if pd.notna(persona_apellido):
                             c_apellido = str(persona_apellido).strip()
                        elif ' ' in p_nombre:
                            # Fallback si no hay columna apellido pero el nombre tiene espacios
                            parts = p_nombre.split(' ', 1)
                            c_nombre = parts[0]
                            c_apellido = parts[1]
                        
                        # Si encontramos nombre, intentamos agregar el contacto
                        if c_nombre:
                            # Pass connection to reuse it
                            new_contact_id = add_contacto(c_nombre, c_apellido, etiqueta_tipo='cliente', etiqueta_id=cliente_id, conn=conn)
                            if new_contact_id:
                                contacto_id = new_contact_id
            
            owner_id = default_user_id
            propietario_nombre = row.get(col_map['propietario'])
            if pd.notna(propietario_nombre):
                p_norm = str(propietario_nombre).strip().lower()
                if p_norm in user_map:
                    owner_id = user_map[p_norm]
            
            marca_id = None
            if col_map['marca']:
                marca_nombre = row.get(col_map['marca'])
                if pd.notna(marca_nombre):
                    try:
                        # add_marca handles duplicates and returns ID
                        marca_id = add_marca(str(marca_nombre).strip(), conn=conn)
                    except Exception:
                        pass

            c.execute("SELECT id FROM proyectos WHERE trato_id = %s", (trato_id,))
            exists = c.fetchone()
            
            if exists:
                c.execute("""
                    UPDATE proyectos SET
                    titulo = %s,
                    valor = %s,
                    moneda = %s,
                    fecha_cierre = %s,
                    estado = %s,
                    cliente_id = COALESCE(%s, cliente_id),
                    contacto_id = COALESCE(%s, contacto_id),
                    owner_user_id = COALESCE(%s, owner_user_id),
                    marca_id = COALESCE(%s, marca_id),
                    created_at = COALESCE(%s, created_at),
                    updated_at = NOW()
                    WHERE id = %s
                """, (titulo, valor, moneda, fecha_cierre, estado, cliente_id, contacto_id, owner_id, marca_id, created_at_val, exists[0]))
            else:
                # Intentamos usar el trato_id como ID del proyecto para mantener sincronización
                # Esto requiere que no exista ya un proyecto con ese ID (que no sea este trato)
                try:
                    c.execute("""
                        INSERT INTO proyectos (
                            id, trato_id, titulo, valor, moneda, fecha_cierre, estado, cliente_id, contacto_id, owner_user_id, marca_id, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()), NOW()
                        )
                    """, (trato_id, trato_id, titulo, valor, moneda, fecha_cierre, estado, cliente_id, contacto_id, owner_id, marca_id, created_at_val))
                except Exception as e:
                    # Si falla (ej. ID duplicado), insertar sin forzar ID
                    c.execute("ROLLBACK") # Rollback parcial si fuera necesario, pero psycopg2 lo maneja en bloque
                    # Re-intentar sin ID
                    c.execute("""
                        INSERT INTO proyectos (
                            trato_id, titulo, valor, moneda, fecha_cierre, estado, cliente_id, contacto_id, owner_user_id, marca_id, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()), NOW()
                        )
                    """, (trato_id, titulo, valor, moneda, fecha_cierre, estado, cliente_id, contacto_id, owner_id, marca_id, created_at_val))
            
            success_count += 1
            
            # Commit progresivo para evitar perder todo si hay un error y liberar memoria
            conn.commit()
            
        except Exception as e:
            conn.rollback() # Rollback solo de la transacción actual (fila actual si se hizo commit anterior)
            errors.append(f"Fila {index}: {str(e)}")
            
    # Sincronizar secuencia de IDs al final de la importación
    try:
        # Obtener nombre de la secuencia dinámicamente
        c.execute("SELECT pg_get_serial_sequence('proyectos', 'id')")
        seq_row = c.fetchone()
        if seq_row and seq_row[0]:
            seq_name = seq_row[0]
            # setval(seq, val) por defecto pone is_called=true, así que el siguiente será val+1
            c.execute(f"SELECT setval('{seq_name}', (SELECT MAX(id) FROM proyectos))")
        else:
            # Fallback al nombre estándar
            c.execute("SELECT setval('proyectos_id_seq', (SELECT MAX(id) FROM proyectos))")
    except Exception as seq_err:
        log_sql_error(f"Error sincronizando secuencia de IDs: {seq_err}")

    conn.commit()
    conn.close()
    return success_count, errors


# Gestión de contactos
def add_contacto(nombre, apellido=None, puesto=None, telefono=None, email=None, direccion=None, etiqueta_tipo='cliente', etiqueta_id=None, notes=None, celular=None, conn=None):
    if conn is None:
        ensure_projects_schema()
        ensure_contactos_schema()
        
    if etiqueta_id is None:
        return False
        
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True
        
    try:
        c = conn.cursor()
        
        # Check for duplicates (same name, surname, entity)
        c.execute("""
            SELECT id_contacto FROM contactos 
            WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(%s)) 
            AND LOWER(TRIM(COALESCE(apellido, ''))) = LOWER(TRIM(COALESCE(%s, ''))) 
            AND etiqueta_tipo = %s 
            AND etiqueta_id = %s
        """, (str(nombre).strip(), apellido or '', str(etiqueta_tipo).strip().lower(), int(etiqueta_id)))
        
        existing = c.fetchone()
        if existing:
            return existing[0]

        c.execute(
            """
            INSERT INTO contactos (nombre, apellido, puesto, telefono, email, direccion, etiqueta_tipo, etiqueta_id, notes, celular)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id_contacto
            """,
            (str(nombre).strip(), apellido or '', puesto or '', telefono or '', email or '', direccion or '', str(etiqueta_tipo).strip().lower(), int(etiqueta_id), notes or '', celular or '')
        )
        new_id = c.fetchone()[0]
        
        if should_close:
            conn.commit()
            
        return new_id
    except Exception as e:
        # Only rollback if we own the connection or if we want to abort the transaction
        # If we are part of a larger transaction, rolling back here might be intended 
        # (to fail the current row operation) but we should be careful.
        # Ideally, we should use SAVEPOINTs, but for now we rely on the caller committing frequently.
        if should_close:
             conn.rollback()
        log_sql_error(f"Error agregando contacto: {e}")
        return None
    finally:
        if should_close:
            conn.close()

def get_contactos_por_cliente(cliente_id):
    ensure_projects_schema()
    engine = get_engine()
    try:
        df = pd.read_sql_query(text("""
            SELECT id_contacto, nombre, apellido, puesto, telefono, email, direccion, notes, celular, etiqueta_tipo, etiqueta_id
            FROM contactos 
            WHERE etiqueta_tipo = 'cliente' AND etiqueta_id = :cid
            ORDER BY nombre, apellido
        """), con=engine, params={"cid": int(cliente_id)})
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo contactos por cliente: {e}")
        return pd.DataFrame()

def get_contactos_por_marca(marca_id):
    ensure_projects_schema()
    engine = get_engine()
    try:
        df = pd.read_sql_query(text("""
            SELECT id_contacto, nombre, apellido, puesto, telefono, email, direccion, notes, celular, etiqueta_tipo, etiqueta_id
            FROM contactos 
            WHERE etiqueta_tipo = 'marca' AND etiqueta_id = :mid
            ORDER BY nombre, apellido
        """), con=engine, params={"mid": int(marca_id)})
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo contactos por marca: {e}")
        return pd.DataFrame()


def get_proyectos_por_contacto(contacto_id):
    ensure_projects_schema()
    engine = get_engine()
    try:
        df = pd.read_sql_query(text("""
            SELECT id, titulo
            FROM proyectos
            WHERE contacto_id = :cid
            ORDER BY id
        """), con=engine, params={"cid": int(contacto_id)})
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo proyectos por contacto: {e}")
        return pd.DataFrame()

def get_contacto(contacto_id):
    ensure_projects_schema()
    engine = get_engine()
    try:
        df = pd.read_sql_query(text("""
            SELECT id_contacto, nombre, apellido, puesto, telefono, email, direccion, etiqueta_tipo, etiqueta_id, notes, celular
            FROM contactos
            WHERE id_contacto = :cid
        """), con=engine, params={"cid": int(contacto_id)})
        if df.empty:
            return None
        return df.iloc[0].to_dict()
    except Exception as e:
        log_sql_error(f"Error obteniendo contacto: {e}")
        return None

def update_contacto(id_contacto, nombre=None, apellido=None, puesto=None, telefono=None, email=None, direccion=None, etiqueta_tipo=None, etiqueta_id=None, notes=None, celular=None):
    ensure_projects_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        sets = []
        params = []
        if nombre is not None:
            sets.append("nombre = %s"); params.append(str(nombre).strip())
        if apellido is not None:
            sets.append("apellido = %s"); params.append(apellido or '')
        if puesto is not None:
            sets.append("puesto = %s"); params.append(puesto or '')
        if telefono is not None:
            sets.append("telefono = %s"); params.append(telefono or '')
        if email is not None:
            sets.append("email = %s"); params.append(email or '')
        if direccion is not None:
            sets.append("direccion = %s"); params.append(direccion or '')
        if etiqueta_tipo is not None:
            sets.append("etiqueta_tipo = %s"); params.append(str(etiqueta_tipo).strip().lower())
        if etiqueta_id is not None:
            sets.append("etiqueta_id = %s"); params.append(int(etiqueta_id))
        if notes is not None:
            sets.append("notes = %s"); params.append(notes or '')
        if celular is not None:
            sets.append("celular = %s"); params.append(celular or '')
        if not sets:
            return False
        params.append(int(id_contacto))
        query = f"UPDATE contactos SET {', '.join(sets)} WHERE id_contacto = %s"
        c.execute(query, tuple(params))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error actualizando contacto: {e}")
        return False
    finally:
        conn.close()

def delete_contacto(id_contacto):
    ensure_projects_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM contactos WHERE id_contacto = %s", (int(id_contacto),))
        conn.commit()
        return c.rowcount > 0
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error eliminando contacto: {e}")
        return False
    finally:
        conn.close()
def add_proyecto_document(project_id, owner_user_id, filename, file_path, mime_type=None, file_size=None):
    """Agrega un documento al proyecto si el usuario es el propietario"""
    ensure_projects_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        # Verificar propiedad
        c.execute("SELECT 1 FROM proyectos WHERE id = %s AND owner_user_id = %s", (int(project_id), int(owner_user_id)))
        if not c.fetchone():
            return False

        c.execute("""
            INSERT INTO proyecto_documentos (proyecto_id, filename, file_path, mime_type, file_size)
            VALUES (%s, %s, %s, %s, %s)
        """, (int(project_id), str(filename), str(file_path), mime_type, file_size))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error agregando documento: {e}")
        return False
    finally:
        conn.close()


def get_proyecto_documentos(project_id):
    """Lista documentos de un proyecto"""
    ensure_projects_schema()
    engine = get_engine()
    try:
        df = pd.read_sql_query(text("""
            SELECT id, filename, file_path, mime_type, file_size, uploaded_at, is_vigente
            FROM proyecto_documentos
            WHERE proyecto_id = :pid
            ORDER BY uploaded_at DESC
        """), con=engine, params={"pid": int(project_id)})
        return df
    except Exception as e:
        log_sql_error(f"Error listando documentos del proyecto: {e}")
        return pd.DataFrame()


def remove_proyecto_document(doc_id, owner_user_id, bypass_owner=False):
    """Elimina un documento del proyecto si pertenece al propietario (o admin si bypass_owner=True)"""
    ensure_projects_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        # Verificar que el doc pertenece a un proyecto del owner
        if bypass_owner:
            c.execute("""
                SELECT d.file_path
                FROM proyecto_documentos d
                WHERE d.id = %s
            """, (int(doc_id),))
            row = c.fetchone()
            if not row:
                return False
            file_path = row[0]
        else:
            c.execute("""
                SELECT d.file_path, p.owner_user_id
                FROM proyecto_documentos d
                JOIN proyectos p ON p.id = d.proyecto_id
                WHERE d.id = %s
            """, (int(doc_id),))
            row = c.fetchone()
            if not row or int(row[1]) != int(owner_user_id):
                return False
            file_path = row[0]

        c.execute("DELETE FROM proyecto_documentos WHERE id = %s", (int(doc_id),))
        conn.commit()
        try:
            import os
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
        return True
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error borrando documento: {e}")
        return False
    finally:
        conn.close()

def update_proyecto_document_path(doc_id, new_path):
    """Actualiza la ruta del archivo almacenada para un documento."""
    ensure_projects_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "UPDATE proyecto_documentos SET file_path = %s WHERE id = %s",
            (str(new_path), int(doc_id))
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error actualizando ruta de documento: {e}")
        return False
    finally:
        conn.close()

def init_db():
    """Inicializa la estructura de la base de datos"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        c.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                nombre VARCHAR(100),
                apellido VARCHAR(100),
                email VARCHAR(100),
                is_admin BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                is_2fa_enabled BOOLEAN DEFAULT FALSE,
                rol_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Asegurar columna para secreto TOTP (si no existe)
        c.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS totp_secret VARCHAR(255)")
        
        # Bloqueo por intentos fallidos (si no existen)
        c.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS failed_attempts INTEGER DEFAULT 0")
        c.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS lockout_until TIMESTAMP NULL")
        
        # Tabla de roles
        c.execute('''
            CREATE TABLE IF NOT EXISTS roles (
                id_rol SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL UNIQUE,
                descripcion TEXT,
                is_hidden BOOLEAN DEFAULT FALSE,
                view_type VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute("ALTER TABLE roles ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN DEFAULT FALSE")
        
        # Tabla de grupos
        c.execute('''
            CREATE TABLE IF NOT EXISTS grupos (
                id_grupo SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL UNIQUE,
                descripcion TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla grupos_roles
        c.execute('''
            CREATE TABLE IF NOT EXISTS grupos_roles (
                id SERIAL PRIMARY KEY,
                id_grupo INTEGER NOT NULL,
                id_rol INTEGER NOT NULL,
                FOREIGN KEY (id_grupo) REFERENCES grupos (id_grupo),
                FOREIGN KEY (id_rol) REFERENCES roles (id_rol),
                UNIQUE(id_grupo, id_rol)
            )
        ''')
        
        # Tabla de grupos_puntajes
        c.execute('''
            CREATE TABLE IF NOT EXISTS grupos_puntajes (
                id SERIAL PRIMARY KEY,
                id_grupo INTEGER NOT NULL,
                puntaje INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (id_grupo) REFERENCES grupos (id_grupo),
                UNIQUE(id_grupo)
            )
        ''')
        
        # Tabla de tipos_tarea_puntajes
        c.execute('''
            CREATE TABLE IF NOT EXISTS tipos_tarea_puntajes (
                id SERIAL PRIMARY KEY,
                id_tipo INTEGER NOT NULL,
                puntaje INTEGER NOT NULL DEFAULT 0,
                UNIQUE(id_tipo)
            )
        ''')
        
        # Tabla de técnicos
        c.execute('''
            CREATE TABLE IF NOT EXISTS tecnicos (
                id_tecnico SERIAL PRIMARY KEY,
                nombre VARCHAR(200) NOT NULL,
                apellido VARCHAR(100),
                email VARCHAR(100),
                telefono VARCHAR(20),
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de clientes
        c.execute('''CREATE TABLE IF NOT EXISTS clientes (
                id_cliente SERIAL PRIMARY KEY,
                nombre VARCHAR(200) NOT NULL UNIQUE,
                alias VARCHAR(200),
                direccion VARCHAR(300),
                telefono VARCHAR(20),
                email VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Solicitudes de nuevos clientes (aprobación por admin)
        c.execute('''CREATE TABLE IF NOT EXISTS cliente_solicitudes (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(200) NOT NULL,
                organizacion VARCHAR(300),
                telefono VARCHAR(20),
                requested_by INTEGER NOT NULL REFERENCES usuarios(id),
                estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de clientes_puntajes
        c.execute('''CREATE TABLE IF NOT EXISTS clientes_puntajes (
                id SERIAL PRIMARY KEY,
                id_cliente INTEGER NOT NULL,
                puntaje INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (id_cliente) REFERENCES clientes (id_cliente),
                UNIQUE(id_cliente)
            )
        ''')
        
        # Asegurar esquema de proyectos (depende de usuarios y clientes)
        ensure_projects_schema(conn)

        # Tabla de tipos de tarea
        c.execute('''
            CREATE TABLE IF NOT EXISTS tipos_tarea (
                id_tipo SERIAL PRIMARY KEY,
                descripcion VARCHAR(200) NOT NULL UNIQUE,
                hidden BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de vacaciones
        c.execute('''
            CREATE TABLE IF NOT EXISTS vacaciones (
                id SERIAL PRIMARY KEY,
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
                fecha_inicio DATE NOT NULL,
                fecha_fin DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de modalidades de tarea
        c.execute('''
            CREATE TABLE IF NOT EXISTS modalidades_tarea (
                id_modalidad SERIAL PRIMARY KEY,
                descripcion VARCHAR(200) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Sembrar modalidades requeridas (si no existen)
        required_modalidades = [
            "Cliente",
            "Presencial",
            "Remoto",
            "Feriado",
            "Base en Casa",
        ]
        for nombre in required_modalidades:
            c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE descripcion = %s", (nombre,))
            if not c.fetchone():
                c.execute("INSERT INTO modalidades_tarea (descripcion) VALUES (%s)", (nombre,))

        # Asegurar columna is_hidden en modalidades_tarea
        conn.commit()
        try:
            c.execute("ALTER TABLE modalidades_tarea ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN DEFAULT FALSE")
            conn.commit()
        except Exception:
            conn.rollback()

        # Sembrar modalidad Vacaciones (oculta)
        try:
            c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE descripcion = 'Vacaciones'")
            if not c.fetchone():
                c.execute("INSERT INTO modalidades_tarea (descripcion, is_hidden) VALUES ('Vacaciones', TRUE)")
            else:
                c.execute("UPDATE modalidades_tarea SET is_hidden = TRUE WHERE descripcion = 'Vacaciones'")
            conn.commit()
        except Exception:
            conn.rollback()

        # Asegurar columna hidden en tipos_tarea
        conn.commit()
        try:
            c.execute("ALTER TABLE tipos_tarea ADD COLUMN IF NOT EXISTS hidden BOOLEAN DEFAULT FALSE")
            conn.commit()
        except Exception:
            conn.rollback()

        # Sembrar tipo Vacaciones
        try:
            c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = 'Vacaciones'")
            if not c.fetchone():
                c.execute("INSERT INTO tipos_tarea (descripcion, hidden) VALUES ('Vacaciones', TRUE)")
            else:
                # Asegurar que esté oculto si ya existe
                c.execute("UPDATE tipos_tarea SET hidden = TRUE WHERE descripcion = 'Vacaciones'")
            conn.commit()
        except Exception:
            conn.rollback()

        # Tabla tipos_tarea_roles
        c.execute('''
            CREATE TABLE IF NOT EXISTS tipos_tarea_roles (
                id SERIAL PRIMARY KEY,
                id_tipo INTEGER NOT NULL,
                id_rol INTEGER NOT NULL,
                FOREIGN KEY (id_tipo) REFERENCES tipos_tarea (id_tipo),
                FOREIGN KEY (id_rol) REFERENCES roles (id_rol),
                UNIQUE(id_tipo, id_rol)
            )
        ''')
        # Tabla de registros de trabajo
        c.execute('''CREATE TABLE IF NOT EXISTS registros (
            id SERIAL PRIMARY KEY,
            fecha VARCHAR(20) NOT NULL,
            id_tecnico INTEGER NOT NULL,
            id_cliente INTEGER NOT NULL,
            id_tipo INTEGER NOT NULL,
            id_modalidad INTEGER NOT NULL,
            tarea_realizada TEXT NOT NULL,
            numero_ticket VARCHAR(50) NOT NULL,
            tiempo INTEGER NOT NULL,
            descripcion TEXT,
            mes VARCHAR(20) NOT NULL,
            usuario_id INTEGER,
            grupo VARCHAR(100),
            es_hora_extra BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (id_tecnico) REFERENCES tecnicos (id_tecnico),
            FOREIGN KEY (id_cliente) REFERENCES clientes (id_cliente),
            FOREIGN KEY (id_tipo) REFERENCES tipos_tarea (id_tipo),
            FOREIGN KEY (id_modalidad) REFERENCES modalidades_tarea (id_modalidad),
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )''')
        
        # Asegurar columna es_hora_extra en registros
        try:
            c.execute("ALTER TABLE registros ADD COLUMN IF NOT EXISTS es_hora_extra BOOLEAN DEFAULT FALSE")
            conn.commit()
        except Exception:
            conn.rollback()
        
        # Asegurar tipo decimal para 'tiempo' en registros
        try:
            c.execute("""
                SELECT data_type 
                FROM information_schema.columns
                WHERE table_name = 'registros' AND column_name = 'tiempo'
            """)
            row = c.fetchone()
            if row and row[0] == 'integer':
                c.execute("""
                    ALTER TABLE registros
                    ALTER COLUMN tiempo TYPE NUMERIC(6,2)
                    USING tiempo::numeric
                """)
        except Exception:
            pass
        
        # Tabla de nómina
        c.execute('''
            CREATE TABLE IF NOT EXISTS nomina (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                apellido VARCHAR(100),
                email VARCHAR(100),
                documento VARCHAR(50),
                cargo VARCHAR(150),
                departamento VARCHAR(100),
                fecha_ingreso DATE,
                fecha_nacimiento DATE,
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabla de registro de actividades de usuarios
        c.execute('''
            CREATE TABLE IF NOT EXISTS actividades_usuarios (
                id SERIAL PRIMARY KEY,
                usuario_id INTEGER,
                username VARCHAR(50),
                tipo_actividad VARCHAR(50) NOT NULL,
                descripcion TEXT,
                fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
            )
        ''')
        
        # Tabla de códigos de recuperación
        c.execute('''
            CREATE TABLE IF NOT EXISTS recovery_codes (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                code VARCHAR(100),
                used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES usuarios (id)
            )
        ''')
        
        # Agregar foreign keys a usuarios después de crear las tablas
        conn.commit()
        try:
            c.execute('''
                ALTER TABLE usuarios 
                ADD CONSTRAINT fk_usuarios_rol 
                FOREIGN KEY (rol_id) REFERENCES roles (id_rol)
            ''')
            conn.commit()
        except Exception:
            conn.rollback()  # La constraint ya existe o error
            
        try:
            c.execute('''
                ALTER TABLE tipos_tarea_puntajes 
                ADD CONSTRAINT fk_tipos_tarea_puntajes_tipo 
                FOREIGN KEY (id_tipo) REFERENCES tipos_tarea (id_tipo)
            ''')
            conn.commit()
        except Exception:
            conn.rollback()  # La constraint ya existe o error
        
        # Insertar roles del sistema si no existen
        # Primero obtenemos todos los roles existentes para comparar normalizados
        c.execute('SELECT nombre FROM roles')
        existing_roles_raw = [r[0] for r in c.fetchall()]
        
        from .utils import clean_role_name
        
        role_view_type_map = {
            'ADMIN': 'administrador',
            'ADM_COMERCIAL': 'admin_comercial',
            'DPTO_COMERCIAL': 'comercial',
            'COMPRAS': 'compras',
        }
        role_clean_aliases_map = {
            'COMPRAS': {'compras', 'dpto_compras'},
        }
        
        for role_key, role_desc in SYSTEM_ROLES.items():
            try:
                # Normalizamos el rol que queremos insertar
                target_clean = clean_role_name(role_desc)
                accepted_clean_names = role_clean_aliases_map.get(role_key, {target_clean})
                
                # Verificamos si ya existe algún rol que normalizado sea igual
                exists = False
                ex_role = None
                for ex_role in existing_roles_raw:
                    if clean_role_name(ex_role) in accepted_clean_names:
                        exists = True
                        break
                
                expected_view_type = role_view_type_map.get(role_key)
                if exists and expected_view_type:
                    try:
                        c.execute(
                            """
                            UPDATE roles
                            SET nombre = %s,
                                view_type = %s
                            WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(%s))
                              AND (
                                  LOWER(TRIM(nombre)) <> LOWER(TRIM(%s))
                                  OR COALESCE(view_type, '') <> %s
                              )
                            """,
                            (role_desc, expected_view_type, ex_role, role_desc, expected_view_type),
                        )
                        existing_roles_raw = [role_desc if str(name or '').strip().lower() == str(ex_role or '').strip().lower() else name for name in existing_roles_raw]
                    except Exception:
                        conn.rollback()
                
                if not exists:
                    # SIN_ROL y HIPERVISOR deben estar ocultos
                    is_hidden = True if role_key in ['SIN_ROL', 'HIPERVISOR'] else False
                    
                    # Asignar view_type para admin y otros roles de sistema
                    view_type = expected_view_type
                    
                    if view_type:
                         c.execute('INSERT INTO roles (nombre, descripcion, is_hidden, view_type) VALUES (%s, %s, %s, %s)',
                             (role_desc, f'Rol del sistema: {role_desc}', is_hidden, view_type))
                    else:
                         c.execute('INSERT INTO roles (nombre, descripcion, is_hidden) VALUES (%s, %s, %s)',
                             (role_desc, f'Rol del sistema: {role_desc}', is_hidden))
                    
                    # Actualizamos la lista local para futuras iteraciones en este mismo loop
                    existing_roles_raw.append(role_desc)

                conn.commit()
            except Exception:
                conn.rollback()
        
        # Verificar si el usuario admin existe, si no, crearlo
        try:
            from .auth import hash_password
            c.execute('SELECT * FROM usuarios WHERE username = %s', (DEFAULT_ADMIN_USERNAME,))
            if not c.fetchone():
                # Obtener el ID del rol admin
                c.execute('SELECT id_rol FROM roles WHERE nombre = %s', (SYSTEM_ROLES['ADMIN'],))
                admin_role = c.fetchone()
                admin_rol_id = admin_role[0] if admin_role else None
                
                c.execute('INSERT INTO usuarios (username, password_hash, is_admin, is_active, rol_id) VALUES (%s, %s, %s, %s, %s)',
                          (DEFAULT_ADMIN_USERNAME, hash_password(DEFAULT_ADMIN_PASSWORD), True, True, admin_rol_id))
            conn.commit()
        except Exception:
            conn.rollback()
        
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error inicializando base de datos: {e}")
        raise
    finally:
        conn.close()

def create_default_admin():
    """Crea el usuario admin por defecto si no existe"""
    from .auth import hash_password
    
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Verificar si ya existe el admin
        c.execute("SELECT COUNT(*) FROM usuarios WHERE username = %s", (DEFAULT_ADMIN_USERNAME,))
        if c.fetchone()[0] == 0:
            # Obtener el rol de admin
            c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (SYSTEM_ROLES['ADMIN'],))
            admin_rol = c.fetchone()
            
            if admin_rol:
                # Crear hash de la contraseña
                password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
                
                c.execute('''
                    INSERT INTO usuarios (username, password_hash, is_admin, rol_id, is_active)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (DEFAULT_ADMIN_USERNAME, password_hash, True, admin_rol[0], True))
                
                conn.commit()
                
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error creando admin por defecto: {e}")
        raise
    finally:
        conn.close()

def get_users_dataframe():
    """Obtiene DataFrame de usuarios con información completa"""
    try:
        query = """SELECT u.id, u.username, u.nombre, u.apellido, u.email, u.is_admin, u.is_active, 
               u.rol_id, r.nombre as rol_nombre
               FROM usuarios u 
               LEFT JOIN roles r ON u.rol_id = r.id_rol
               ORDER BY u.is_admin DESC, u.apellido, u.nombre"""
        
        engine = get_engine()
        users_df = pd.read_sql_query(query, con=engine)
        
        # Reemplazar valores None con 'None' para mejor visualización
        users_df['email'] = users_df['email'].fillna('None')
        users_df['nombre'] = users_df['nombre'].fillna('None')
        users_df['apellido'] = users_df['apellido'].fillna('None')
        users_df['rol_nombre'] = users_df['rol_nombre'].fillna(SYSTEM_ROLES['SIN_ROL'])
        
        return users_df
        
    except Exception as e:
        log_sql_error(f"Error obteniendo usuarios: {e}")
        return pd.DataFrame()

def process_registros_df(df):
    """Procesa el DataFrame de registros: fechas, ordenamiento y mes"""
    if df.empty:
        return df

    # Convertir fecha a datetime para ordenamiento y extracción de mes
    if 'fecha' in df.columns:
        # Guardar string original por si acaso se necesita
        df['fecha_str'] = df['fecha'].astype(str)
        
        # Convertir a datetime
        df['fecha_dt'] = df['fecha'].apply(parse_registro_datetime)
        
        # Calcular columna mes si existe fecha válida
        # Aseguramos que 'mes' exista
        if 'mes' not in df.columns:
            df['mes'] = ''
            
        # Rellenar mes basado en la fecha
        mask_valid = df['fecha_dt'].notna()
        if mask_valid.any():
            # Extraer número de mes y convertir a nombre
            df.loc[mask_valid, 'mes'] = df.loc[mask_valid, 'fecha_dt'].dt.month.apply(month_name_es)
            
        # Ordenar por fecha descendente (más reciente primero)
        df = df.sort_values(by='fecha_dt', ascending=False)
        
        # Reemplazar la columna fecha (string) con el objeto datetime real
        # Esto permite que Streamlit ordene cronológicamente en lugar de alfabéticamente
        df['fecha'] = df['fecha_dt']
        
        # Eliminar columna auxiliar fecha_dt
        df = df.drop(columns=['fecha_dt'])
        
    return df

def get_registros_dataframe():
    """Obtiene DataFrame de registros con información completa"""
    try:
        query = '''
            SELECT r.id, r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.descripcion as modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.es_hora_extra, r.descripcion, r.mes, 
                   r.created_at as "Fecha Creación"
            FROM registros r
            LEFT JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            LEFT JOIN clientes c ON r.id_cliente = c.id_cliente
            LEFT JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            LEFT JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
            ORDER BY r.id DESC
        '''
        engine = get_engine()
        df = pd.read_sql_query(query, con=engine)
        
        if 'id' in df.columns:
            other_columns = [col for col in df.columns if col != 'id']
            df = df[['id'] + other_columns]
        
        # Procesar fechas y meses
        df = process_registros_df(df)
        
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo registros: {e}")
        return pd.DataFrame()

def get_registros_dataframe_with_date_filter(filter_type='current_month', custom_month=None, custom_year=None):
    """Obtiene DataFrame de registros filtrados por fecha
    
    Args:
        filter_type (str): 'current_month', 'custom_month', 'all_time'
        custom_month (int): Mes específico (1-12) para filtro personalizado
        custom_year (int): Año específico para filtro personalizado
    """
    try:
        query = '''
            SELECT r.id, r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.descripcion as modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.es_hora_extra, r.descripcion, r.mes,
                   r.created_at as "Fecha Creación"
            FROM registros r
            LEFT JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            LEFT JOIN clientes c ON r.id_cliente = c.id_cliente
            LEFT JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            LEFT JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
            ORDER BY r.id DESC
        '''
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine)
        
        # Procesar fechas y meses
        df = process_registros_df(df)

        if not df.empty and filter_type in ('current_month', 'custom_month'):
            target_month = datetime.now().month if filter_type == 'current_month' else int(custom_month)
            target_year = datetime.now().year if filter_type == 'current_month' else int(custom_year)
            if pd.api.types.is_datetime64_any_dtype(df['fecha']):
                df = df[(df['fecha'].dt.month == target_month) & (df['fecha'].dt.year == target_year)]
        
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo registros con filtro de fecha: {e}")
        return pd.DataFrame()

def get_user_registros_dataframe(user_id):
    """Obtiene DataFrame de registros de un usuario específico"""
    try:
        query = '''
            SELECT r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.descripcion as modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.es_hora_extra, r.descripcion, r.mes, r.id,
                   r.created_at as "Fecha Creación"
            FROM registros r
            LEFT JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            LEFT JOIN clientes c ON r.id_cliente = c.id_cliente
            LEFT JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            LEFT JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
            WHERE r.usuario_id = :user_id
            ORDER BY r.fecha DESC
        '''
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine, params={"user_id": user_id})
        
        # Procesar fechas y meses
        df = process_registros_df(df)
        
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo registros de usuario: {e}")
        return pd.DataFrame()

def get_user_registros_dataframe_cached(user_id):
    """Obtiene DataFrame de registros de un usuario específico con caché en session_state"""
    import streamlit as st
    
    # Usar caché en session_state para evitar consultas repetidas
    cache_key = f"user_registros_{user_id}"
    
    if cache_key not in st.session_state:
        query = '''
            SELECT r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.descripcion as modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.es_hora_extra, r.descripcion, r.mes, r.id,
                   r.created_at as "Fecha Creación"
            FROM registros r
            LEFT JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            LEFT JOIN clientes c ON r.id_cliente = c.id_cliente
            LEFT JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            LEFT JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
            WHERE r.usuario_id = :user_id
            ORDER BY r.fecha DESC
        '''
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine, params={"user_id": user_id})
            
        # Procesar fechas y meses usando la función centralizada
        if not df.empty:
            df = process_registros_df(df)
            
        st.session_state[cache_key] = df
    
    return st.session_state[cache_key]

def clear_user_registros_cache(user_id):
    """Limpia el caché de registros de un usuario específico"""
    import streamlit as st
    
    cache_key = f"user_registros_{user_id}"
    if cache_key in st.session_state:
        del st.session_state[cache_key]

def get_tecnicos_dataframe():
    """Obtiene DataFrame de técnicos"""
    engine = get_engine()
    df = pd.read_sql_query("SELECT * FROM tecnicos", con=engine)
    return df

def get_clientes_dataframe(only_active=False):
    """Obtiene DataFrame de clientes"""
    engine = get_engine()
    query = "SELECT * FROM clientes"
    if only_active:
        query += " WHERE activo IS TRUE"
    # Asegurar ordenamiento consistente
    query += " ORDER BY nombre"
    
    try:
        df = pd.read_sql_query(query, con=engine)
    except Exception:
        # Fallback por si la columna activo aún no existe en tiempo de ejecución (aunque ensure debería haber corrido)
        # O intentar correr ensure_clientes_schema() y reintentar
        ensure_clientes_schema()
        df = pd.read_sql_query(query, con=engine)
        
    return df

def get_marcas_dataframe(only_active=False):
    engine = get_engine()
    query = "SELECT id_marca, cuit, nombre, email, telefono, celular, web, activa FROM marcas"
    if only_active:
        query += " WHERE activa IS TRUE"
    query += " ORDER BY nombre"
    df = pd.read_sql_query(query, con=engine)
    return df

def add_marca(nombre, cuit=None, email=None, telefono=None, celular=None, web=None, conn=None):
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
        
    try:
        c = conn.cursor()
        # Check case-insensitive to avoid duplicates
        c.execute("SELECT id_marca FROM marcas WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(%s))", (str(nombre).strip(),))
        row = c.fetchone()
        if row:
            return int(row[0])
            
        clean_cuit = normalize_cuit(cuit)
        web_val = normalize_web(web)
        email_val = (email or "").strip()
        tel_val = (telefono or "").strip()
        cel_val = (celular or "").strip()
        
        c.execute(
            "INSERT INTO marcas (nombre, cuit, email, telefono, celular, web, activa) VALUES (%s, %s, %s, %s, %s, %s, TRUE) RETURNING id_marca",
            (
                str(nombre).strip(), 
                clean_cuit if clean_cuit else None, 
                email_val if email_val else None, 
                tel_val if tel_val else None, 
                cel_val if cel_val else None, 
                web_val if web_val else None
            )
        )
        new_id = c.fetchone()[0]
        # Commit if we own the connection, or if we want to persist immediately (brands are global)
        conn.commit()
        return int(new_id)
    except Exception as e:
        if close_conn:
            conn.rollback()
        log_sql_error(f"Error agregando marca: {e}")
        return None
    finally:
        if close_conn:
            conn.close()

def update_marca(id_marca, nombre, activa=True, cuit=None, email=None, telefono=None, celular=None, web=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        assignments = ["nombre = %s", "activa = %s"]
        values = [str(nombre).strip(), bool(activa)]
        if cuit is not None:
            clean_cuit = normalize_cuit(cuit)
            assignments.append("cuit = %s")
            values.append(clean_cuit if clean_cuit else None)
        if email is not None:
            assignments.append("email = %s")
            val = (email or "").strip()
            values.append(val if val else None)
        if telefono is not None:
            assignments.append("telefono = %s")
            val = (telefono or "").strip()
            values.append(val if val else None)
        if celular is not None:
            assignments.append("celular = %s")
            val = (celular or "").strip()
            values.append(val if val else None)
        if web is not None:
            web_val = normalize_web(web)
            assignments.append("web = %s")
            values.append(web_val if web_val else None)
        values.append(int(id_marca))
        sql = f"UPDATE marcas SET {', '.join(assignments)} WHERE id_marca = %s"
        c.execute(sql, tuple(values))
        conn.commit()
        if c.rowcount > 0:
            return True, None
        else:
            return False, "No se encontró la marca o no hubo cambios."
    except Exception as e:
        conn.rollback()
        error_msg = str(e)
        log_sql_error(f"Error actualizando marca: {error_msg}")
        return False, error_msg
    finally:
        conn.close()

def delete_marca(id_marca):
    ensure_projects_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM marcas WHERE id_marca = %s", (int(id_marca),))
        conn.commit()
        return c.rowcount > 0
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error eliminando marca: {e}")
        return False
    finally:
        conn.close()

def get_tipos_dataframe(rol_id=None):
    """Obtiene DataFrame de tipos de tarea.

    Args:
        rol_id (int, optional): Si se proporciona, filtra los tipos de tarea
            por rol. IMPORTANTE: si rol_id corresponde a un rol
            "departamento" (dpto_tecnico, dpto_comercial, ...), la query se
            expande automáticamente a TODOS los roles individuales de ese
            departamento mediante WHERE IN. Esto permite que usuarios que
            tienen asignado el dpto_* como su rol_id (común en instalaciones
            antiguas) vean los mismos tipos que los roles individuales.
    """
    # 0. Bootstrap: asegurar que existan tecnico/comercial/compras y que los
    #    usuarios no-admin NO tengan dpto_* ni adm_* como rol_id (caso típico
    #    de restore de Excel viejo).
    bootstrap_missing_roles_and_users()
    # 1. Sanea data vieja (departamentos -> roles individuales) antes del filtro.
    migrate_task_type_department_roles()
    # 2. Repara tipos que por algún bug quedaron con un subset de los
    #    roles individuales de un dpto (ej: solo adm_tecnico, sin tecnico).
    repair_task_type_roles_missing_from_departments()
    # 3. Saneo de emergencia: si el backup viejo restauró tipos_tarea pero no
    #    tipos_tarea_roles (tabla totalmente vacía). En ese caso ningún tipo tiene
    #    roles y el JOIN de abajo devuelve 0 filas. Este saneo agrega roles a todos
    #    los individuales a cualquier tipo huérfano -> queda con 0 roles.
    repair_task_types_without_any_roles()

    engine = get_engine()
    if rol_id is not None:
        # Expandir rol_id vía helper centralizado (si es dpto_*, devuelve
        # todos los individuales; si es individual, devuelve [rol_id]).
        try:
            rid_int = int(rol_id)
        except (TypeError, ValueError):
            rid_int = None
        expanded_ids = expand_role_ids_to_individuals([rid_int] if rid_int is not None else [])
        # Si la expansión no devolvió nada (rol desconocido), al menos
        # usamos el rol_id original para no romper la query.
        target_ids = list(dict.fromkeys(
            [int(x) for x in expanded_ids if x is not None]
        )) or ([rid_int] if rid_int is not None else [])
        param_names = [f"p{i}" for i in range(len(target_ids))]
        placeholders = ",".join(f":{p}" for p in param_names)
        params = {p: val for p, val in zip(param_names, target_ids)}
        query = f"""
        SELECT DISTINCT t.* 
        FROM tipos_tarea t
        JOIN tipos_tarea_roles tr ON t.id_tipo = tr.id_tipo
        WHERE tr.id_rol IN ({placeholders})
        ORDER BY t.descripcion
        """
        df = pd.read_sql_query(text(query), con=engine, params=params)
    else:
        df = pd.read_sql_query("SELECT * FROM tipos_tarea WHERE (hidden IS FALSE OR hidden IS NULL) ORDER BY descripcion", con=engine)
    return df

def get_tipos_dataframe_with_roles(skip_repairs=False):
    """Obtiene DataFrame de tipos de tarea con sus roles asociados.

    Args:
        skip_repairs (bool): Si es True, NO ejecuta el repair de "completar
            subsets de roles dentro de un dpto". Usar esta opción en el PANEL
            DE ADMINISTRADOR, porque cuando el usuario elige un subset
            custom (ej: solo tecnico, sin adm_tecnico) ese subset es la
            configuración DESEADA y no debe "repararse" agregando lo que
            falta de un dpto. Si es False (default), se ejecutan todos los
            saneos (modo dashboard del usuario común).

    Cuando skip_repairs=False (default): antes de armar el STRING_AGG corre
    los mismos 3 saneos que el dropdown del dashboard técnico, para que el
    usuario común nunca vea 0 tipos por una inconsistencia de data.
    """
    # 0. Bootstrap: siempre corre, no destruye subsets. Asegura roles
    #    individuales mínimos y que usuarios no-admin no tengan dpto_/adm_.
    bootstrap_missing_roles_and_users()
    # 1. Siempre correr migrate y orphans (son seguros, no destruyen config).
    migrate_task_type_department_roles()
    repair_task_types_without_any_roles()
    # 2. repair subsets (llenar faltantes de un dpto) SOLO si skip_repairs=False.
    if not skip_repairs:
        repair_task_type_roles_missing_from_departments()
    try:
        query = """
        SELECT t.id_tipo, t.descripcion, 
               STRING_AGG(r.nombre, ', ') as roles_asociados
        FROM tipos_tarea t
        LEFT JOIN tipos_tarea_roles tr ON t.id_tipo = tr.id_tipo
        LEFT JOIN roles r ON tr.id_rol = r.id_rol
        GROUP BY t.id_tipo, t.descripcion
        ORDER BY t.descripcion
        """
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine)
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo tipos de tarea con roles: {e}")
        return pd.DataFrame()

def get_tipos_by_rol(rol_id):
    """Obtiene los tipos de tarea disponibles para un rol específico.

    Si `rol_id` pertenece a un departamento (dpto_*) se expande a todos
    los roles individuales de ese departamento antes de filtrar.
    """
    try:
        rid_int = int(rol_id)
    except (TypeError, ValueError):
        return pd.DataFrame()
    expanded_ids = expand_role_ids_to_individuals([rid_int])
    target_ids = list(dict.fromkeys(
        [int(x) for x in expanded_ids if x is not None]
    )) or [rid_int]
    param_names = [f"p{i}" for i in range(len(target_ids))]
    placeholders = ",".join(f":{p}" for p in param_names)
    params = {p: val for p, val in zip(param_names, target_ids)}
    query = f"""
    SELECT DISTINCT t.id_tipo, t.descripcion
    FROM tipos_tarea t
    JOIN tipos_tarea_roles tr ON t.id_tipo = tr.id_tipo
    WHERE tr.id_rol IN ({placeholders}) AND (t.hidden IS FALSE OR t.hidden IS NULL)
    ORDER BY t.descripcion
    """
    try:
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine, params=params)
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo tipos por rol: {e}")
        return pd.DataFrame()

def get_modalidades_dataframe(exclude_hidden=True):
    """Obtiene DataFrame de modalidades"""
    engine = get_engine()
    query = "SELECT * FROM modalidades_tarea"
    if exclude_hidden:
        query += " WHERE is_hidden IS FALSE OR is_hidden IS NULL"
    query += " ORDER BY descripcion"
    df = pd.read_sql_query(query, con=engine)
    return df


def ensure_user_modality_schedule_exists(conn=None):
    """Asegura que existe la tabla de programación de modalidades de usuario"""
    if conn is None:
        conn = get_connection()
        close_conn = True
    else:
        close_conn = False

    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_modalidad_schedule (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            rol_id INTEGER NOT NULL,
            fecha DATE NOT NULL,
            modalidad_id INTEGER NOT NULL,
            cliente_id INTEGER NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, fecha),
            FOREIGN KEY (user_id) REFERENCES usuarios (id),
            FOREIGN KEY (rol_id) REFERENCES roles (id_rol),
            FOREIGN KEY (modalidad_id) REFERENCES modalidades_tarea (id_modalidad)
        )
    ''')
    # Intentar agregar la columna si la tabla ya existía sin cliente_id (PostgreSQL)
    try:
        c.execute("ALTER TABLE user_modalidad_schedule ADD COLUMN IF NOT EXISTS cliente_id INTEGER NULL")
    except Exception:
        pass
    conn.commit()
    if close_conn:
        conn.close()


def get_users_by_rol(rol_id, exclude_hidden=True, only_active=True):
    """Obtiene usuarios por rol_id"""
    try:
        query = """
            SELECT u.id, u.nombre, u.apellido
            FROM usuarios u
            JOIN roles r ON u.rol_id = r.id_rol
            WHERE u.rol_id = :rol_id
            {extra}
            ORDER BY u.nombre, u.apellido
        """
        extra_parts = []
        if exclude_hidden:
            extra_parts.append("AND r.is_hidden = FALSE")
        if only_active:
            extra_parts.append("AND u.is_active = TRUE")
        extra = "\n            ".join(extra_parts)
        engine = get_engine()
        df = pd.read_sql_query(text(query.format(extra=extra)), con=engine, params={"rol_id": int(rol_id)})
        # Agregar columna nombre_completo
        df["nombre_completo"] = df.apply(lambda row: f"{row['nombre']} {row['apellido']}".strip(), axis=1)
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo usuarios por rol: {e}")
        return pd.DataFrame()


def sync_user_schedule_roles_for_range(start_date, end_date):
    """Sincroniza rol_id en user_modalidad_schedule con el rol actual del usuario
    para todas las filas entre start_date y end_date. Devuelve cantidad de filas actualizadas."""
    ensure_user_modality_schedule_exists()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            UPDATE user_modalidad_schedule s
            SET rol_id = u.rol_id,
                updated_at = CURRENT_TIMESTAMP
            FROM usuarios u
            WHERE s.user_id = u.id
              AND s.fecha BETWEEN %s AND %s
              AND s.rol_id <> u.rol_id
        """, (start_date, end_date))
        conn.commit()
        return c.rowcount
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error sincronizando roles en schedule: {e}")
        return 0
    finally:
        conn.close()

def get_user_weekly_modalities(user_id, start_date, end_date):
    """Obtiene las modalidades semanales de un usuario"""
    try:
        ensure_user_modality_schedule_exists()
        query = """
            SELECT fecha, modalidad_id, cliente_id
            FROM user_modalidad_schedule
            WHERE user_id = :user_id
              AND fecha BETWEEN :start_date AND :end_date
            ORDER BY fecha
        """
        engine = get_engine()
        df = pd.read_sql_query(
            text(query),
            con=engine,
            params={"user_id": int(user_id), "start_date": start_date, "end_date": end_date},
        )
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo modalidades semanales de usuario: {e}")
        return pd.DataFrame()


def get_weekly_modalities_by_rol(rol_id, start_date, end_date):
    """Obtiene las modalidades semanales de todos los usuarios de un rol"""
    try:
        ensure_user_modality_schedule_exists()
        query = """
            SELECT s.user_id, u.nombre, u.apellido, s.fecha, s.modalidad_id, m.descripcion AS modalidad,
                   s.cliente_id, c.nombre AS cliente_nombre
            FROM user_modalidad_schedule s
            JOIN usuarios u ON s.user_id = u.id
            JOIN modalidades_tarea m ON s.modalidad_id = m.id_modalidad
            LEFT JOIN clientes c ON s.cliente_id = c.id_cliente
            WHERE s.rol_id = :rol_id
              AND s.fecha BETWEEN :start_date AND :end_date
            ORDER BY u.nombre, u.apellido, s.fecha
        """
        engine = get_engine()
        df = pd.read_sql_query(
            text(query),
            con=engine,
            params={"rol_id": int(rol_id), "start_date": start_date, "end_date": end_date},
        )
        df["nombre_completo"] = df.apply(lambda row: f"{row['nombre']} {row['apellido']}".strip(), axis=1)
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo modalidades semanales por rol: {e}")
        return pd.DataFrame()


def sync_user_schedule_roles_for_range(start_date, end_date):
    """Sincroniza rol_id en user_modalidad_schedule con el rol actual del usuario
    para todas las filas entre start_date y end_date. Devuelve cantidad de filas actualizadas."""
    ensure_user_modality_schedule_exists()
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            UPDATE user_modalidad_schedule s
            SET rol_id = u.rol_id,
                updated_at = CURRENT_TIMESTAMP
            FROM usuarios u
            WHERE s.user_id = u.id
              AND s.fecha BETWEEN %s AND %s
              AND s.rol_id <> u.rol_id
        """, (start_date, end_date))
        conn.commit()
        return c.rowcount
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error sincronizando roles en schedule: {e}")
        return 0
    finally:
        conn.close()


def upsert_user_modality_for_date(user_id, rol_id, fecha, modalidad_id, cliente_id=None):
    """Inserta o actualiza la modalidad de un usuario para una fecha específica, opcionalmente con cliente"""
    ensure_user_modality_schedule_exists()
    conn = get_connection()
    c = conn.cursor()
    try:
        # Intentar ON CONFLICT (PostgreSQL)
        c.execute("""
            INSERT INTO user_modalidad_schedule (user_id, rol_id, fecha, modalidad_id, cliente_id, updated_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, fecha)
            DO UPDATE SET modalidad_id = EXCLUDED.modalidad_id,
                          rol_id = EXCLUDED.rol_id,
                          cliente_id = EXCLUDED.cliente_id,
                          updated_at = CURRENT_TIMESTAMP
        """, (int(user_id), int(rol_id), fecha, int(modalidad_id), cliente_id))
        conn.commit()
    except Exception:
        # Fallback si la BD no soporta ON CONFLICT
        try:
            c.execute("SELECT id FROM user_modalidad_schedule WHERE user_id=%s AND fecha=%s", (int(user_id), fecha))
            row = c.fetchone()
            if row:
                c.execute("""
                    UPDATE user_modalidad_schedule
                    SET modalidad_id=%s, rol_id=%s, cliente_id=%s, updated_at=CURRENT_TIMESTAMP
                    WHERE user_id=%s AND fecha=%s
                """, (int(modalidad_id), int(rol_id), cliente_id, int(user_id), fecha))
            else:
                c.execute("""
                    INSERT INTO user_modalidad_schedule (user_id, rol_id, fecha, modalidad_id, cliente_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (int(user_id), int(rol_id), fecha, int(modalidad_id), cliente_id))
            conn.commit()
        except Exception as e2:
            conn.rollback()
            log_sql_error(f"Error upsert modalidad diaria: {e2}")
            raise
    finally:
        conn.close()

def ensure_user_default_schedule_exists(conn=None):
    """Crea la tabla de cronograma por defecto por usuario y día de semana si no existe"""
    if conn is None:
        conn = get_connection()
        close_conn = True
    else:
        close_conn = False

    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_default_schedule (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,  -- 0=Lunes ... 4=Viernes
            modalidad_id INTEGER NOT NULL,
            cliente_id INTEGER NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, day_of_week),
            FOREIGN KEY (user_id) REFERENCES usuarios (id),
            FOREIGN KEY (modalidad_id) REFERENCES modalidades_tarea (id_modalidad)
        )
    """)
    # Asegurar columna cliente_id si la tabla existía sin ella
    try:
        c.execute("ALTER TABLE user_default_schedule ADD COLUMN IF NOT EXISTS cliente_id INTEGER NULL")
    except Exception:
        pass

    conn.commit()
    if close_conn:
        conn.close()

def get_user_default_schedule(user_id):
    """Devuelve DataFrame con el cronograma por defecto para un usuario"""
    try:
        ensure_user_default_schedule_exists()
        engine = get_engine()
        df = pd.read_sql_query(
            text("SELECT day_of_week, modalidad_id, cliente_id FROM user_default_schedule WHERE user_id = :uid ORDER BY day_of_week"),
            con=engine,
            params={"uid": int(user_id)},
        )
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo cronograma por defecto de usuario: {e}")
        return pd.DataFrame()

def upsert_user_default_schedule(user_id, day_of_week, modalidad_id, cliente_id=None):
    """Inserta/actualiza el cronograma por defecto del usuario para un día de semana"""
    ensure_user_default_schedule_exists()
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO user_default_schedule (user_id, day_of_week, modalidad_id, cliente_id, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, day_of_week)
            DO UPDATE SET modalidad_id = EXCLUDED.modalidad_id,
                          cliente_id = EXCLUDED.cliente_id,
                          updated_at = CURRENT_TIMESTAMP
        """, (int(user_id), int(day_of_week), int(modalidad_id), cliente_id))
        conn.commit()
    except Exception:
        try:
            c.execute("SELECT id FROM user_default_schedule WHERE user_id=%s AND day_of_week=%s", (int(user_id), int(day_of_week)))
            row = c.fetchone()
            if row:
                c.execute("""
                    UPDATE user_default_schedule
                    SET modalidad_id=%s, cliente_id=%s, updated_at=CURRENT_TIMESTAMP
                    WHERE user_id=%s AND day_of_week=%s
                """, (int(modalidad_id), cliente_id, int(user_id), int(day_of_week)))
            else:
                c.execute("""
                    INSERT INTO user_default_schedule (user_id, day_of_week, modalidad_id, cliente_id)
                    VALUES (%s, %s, %s, %s)
                """, (int(user_id), int(day_of_week), int(modalidad_id), cliente_id))
            conn.commit()
        except Exception as e2:
            conn.rollback()
            log_sql_error(f"Error upsert cronograma por defecto: {e2}")
            raise
    finally:
        conn.close()

def upsert_user_default_schedule_bulk(user_id, schedule_dict):
    """Upsert en bloque: schedule_dict = {dow: (modalidad_id, cliente_id)}"""
    ensure_user_default_schedule_exists()
    for dow, pair in schedule_dict.items():
        modalidad_id, cliente_id = pair
        upsert_user_default_schedule(user_id, int(dow), int(modalidad_id), cliente_id)

def get_roles_dataframe(exclude_admin=False, exclude_sin_rol=False, exclude_hidden=True):
    """Obtiene DataFrame de roles
    
    Args:
        exclude_admin (bool): Si es True, excluye el rol de admin de los resultados
        exclude_sin_rol (bool): Si es True, excluye el rol sin_rol de los resultados
        exclude_hidden (bool): Si es True, excluye los roles marcados como ocultos
    """
    query = "SELECT id_rol, nombre, descripcion, is_hidden, view_type FROM roles"
    
    conditions = []
    if exclude_admin:
        conditions.append(f"nombre != '{SYSTEM_ROLES['ADMIN']}'")
    if exclude_sin_rol:
        conditions.append(f"nombre != '{SYSTEM_ROLES['SIN_ROL']}'")
    if exclude_hidden:
        conditions.append("is_hidden = FALSE")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY nombre"
    
    engine = get_engine()
    df = pd.read_sql_query(query, con=engine)
    return df

def update_rol_visibility(rol_id, is_hidden):
    """Actualiza la visibilidad de un rol"""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE roles SET is_hidden = %s WHERE id_rol = %s", (bool(is_hidden), int(rol_id)))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error actualizando visibilidad de rol: {e}")
        return False
    finally:
        conn.close()


def expand_role_ids_to_individuals(role_ids):
    """Expande una lista de id_rol para que contenga solo roles INDIVIDUALES reales.

    - Si el id_rol corresponde a un nombre que empieza con "dpto_" o que existe
      como clave en DEPARTMENT_EXPANSION_MAP, se reemplaza por los id_rol de
      sus roles individuales componentes.
    - Si el id_rol ya es un rol individual (tecnico, adm_tecnico, comercial, ...),
      se mantiene sin cambios.
    - Retorna siempre una lista de enteros, sin duplicados, en orden estable.

    NOTA: esta función NO ejecuta migrate_task_type_department_roles() para no
    alterar el contenido de tipos_tarea_roles mientras la UI de Admin está
    resolviendo un save / edit que acaba de leer la tabla. La migración se
    ejecuta puntualmente antes del filtro del dropdown (get_tipos_dataframe).
    """
    if role_ids is None:
        return []
    try:
        input_ids = [int(rid) for rid in list(role_ids)]
    except (TypeError, ValueError):
        return []
    if not input_ids:
        return []

    # Garantía previa: si faltan tecnico/comercial/compras o hay usuarios con
    # dpto_* como rol_id, el bootstrap los crea antes de expandir.
    bootstrap_missing_roles_and_users()

    all_roles_df = get_roles_dataframe(exclude_admin=False, exclude_sin_rol=False, exclude_hidden=False)
    if all_roles_df.empty:
        return input_ids

    def _norm(s):
        return re.sub(r"[^a-z0-9]+", "_", str(s or "").strip().lower()).strip("_")

    id_to_name = {}
    name_to_id = {}
    for row in all_roles_df.itertuples(index=False):
        rid = getattr(row, "id_rol", None)
        rname = getattr(row, "nombre", None)
        if pd.notna(rid) and pd.notna(rname):
            try:
                ridi = int(rid)
            except (TypeError, ValueError):
                continue
            id_to_name[ridi] = str(rname).strip()
            name_to_id[_norm(rname)] = ridi

    # Construir mapa normalizado de expansión: dpto normalizado -> set(nombres
    # individuales normalizados). Además guardamos el set original para poder
    # buscar por prefijo cuando hay variaciones de nombres en la tabla roles.
    expansion_norm = {}
    expansion_original_lower = {}
    for k, vs in (DEPARTMENT_EXPANSION_MAP or {}).items():
        kn = _norm(k)
        expansion_norm[kn] = {_norm(v) for v in vs}
        expansion_original_lower[str(k).strip().lower()] = {
            str(v).strip().lower() for v in vs
        }

    # Nombres originales de roles individuales para fallback por prefijo derivado
    indiv_names_lower = sorted(
        {str(v).strip().lower() for vs in (DEPARTMENT_EXPANSION_MAP or {}).values() for v in vs}
    )

    output_ids = []
    seen = set()
    for rid in input_ids:
        original_name = id_to_name.get(rid)
        if original_name is None:
            continue
        norm_name = _norm(original_name)
        original_lower = original_name.strip().lower()

        # 1. Match normalizado exacto contra DEPARTMENT_EXPANSION_MAP
        expanded_norm = expansion_norm.get(norm_name)
        # 2. Match exacto lowercase contra DEPARTMENT_EXPANSION_MAP
        expanded_orig = expansion_original_lower.get(original_lower)
        # 3. Match por prefijo "dpto_XXX": derivar nombres adm_XXX y XXX
        expanded_prefix = None
        if expanded_norm is None and expanded_orig is None and original_lower.startswith("dpto_"):
            core = original_lower[len("dpto_"):]
            core_norm = norm_name[len("dpto_"):] if norm_name.startswith("dpto_") else core
            derived = {f"adm_{core}", core, f"adm_{core_norm}", core_norm}
            expanded_prefix = derived

        target_names_norm = set()
        if expanded_norm:
            target_names_norm.update(expanded_norm)
        if expanded_orig:
            for tn in expanded_orig:
                target_names_norm.add(_norm(tn))
        if expanded_prefix:
            for tn in expanded_prefix:
                target_names_norm.add(_norm(tn))

        # Si NO es un dpto, pasamos directo como individual. Pero antes
        # verificamos que no sea un dpto por descarte: si empieza con dpto_
        # pero no matcheó nada, agregamos la derivación heurística.
        if not target_names_norm and not original_lower.startswith("dpto_"):
            # Caso B: ya es rol individual. Guardar ID directamente.
            if rid in seen:
                continue
            seen.add(rid)
            output_ids.append(int(rid))
            continue

        # Caso A: es un dpto (o derivado de dpto_). Expandir a individuales.
        expanded_any = False
        for tn_norm in sorted(target_names_norm):
            if not tn_norm:
                continue
            target_id = name_to_id.get(tn_norm)
            # NO usamos heurístico de substring aquí (antes endswith/_bugg
            # porque matcheaba dpto_tecnico en vez de tecnico). Solo
            # matcheamos nombres normalizados EXACTOS. Si el rol individual
            # no existe en la tabla roles, el Paso 0 de bootstrap (se ejecuta
            # antes de estos helpers) lo habrá creado.
            if target_id is None or target_id in seen:
                continue
            seen.add(target_id)
            output_ids.append(int(target_id))
            expanded_any = True
        # Si la expansión no produjo nada (dpto sin matches), al menos
        # insertamos el id original para no perder la asignación.
        if not expanded_any and rid not in seen:
            seen.add(rid)
            output_ids.append(int(rid))
    return output_ids


def build_individual_role_to_departments_map():
    """Devuelve dict { nombre_rol_individual_NORMALIZADO: set(nombres_deptos_cubren_el_rol_NORMALIZADOS) }.

    Es el inverso de DEPARTMENT_EXPANSION_MAP. Ejemplo:
      "tecnico"     -> {"dpto_tecnico"}
      "adm_tecnico" -> {"dpto_tecnico"}
      "admin"       -> {"dpto_administracion"}

    TODO normalizado para matchear acentos/capitalización de la tabla roles.
    """
    def _norm(s):
        return re.sub(r"[^a-z0-9]+", "_", str(s or "").strip().lower()).strip("_")

    rev = {}
    for dpto_name, indivs in (DEPARTMENT_EXPANSION_MAP or {}).items():
        dpto_key = _norm(dpto_name)
        for indiv in indivs:
            indiv_key = _norm(indiv)
            rev.setdefault(indiv_key, set()).add(dpto_key)
    return rev


def individual_role_ids_to_department_ids(role_ids, all_roles_df=None):
    """Traduce una lista de id_rol (mezcla de individuales y deptos) a SOLAMENTE
    los ids de los departamentos que los cubren.

    - Si el input es un dpto, se deja (sin duplicar).
    - Si el input es un rol individual, se reemplaza por TODOS los dptos que
      lo incluyen según el inverso de DEPARTMENT_EXPANSION_MAP.
    - Si un rol individual no pertenece a ningún dpto, se ignora (la UI de
      "departamentos permitidos" no tiene forma de guardarlo).

    Usa normalización robusta (regex + lowercase) para matchear nombres de
    la tabla roles aunque tengan acentos o mayúsculas distintas al mapa.

    Devuelve lista ordenada de ints sin duplicados.
    """
    if not role_ids:
        return []
    if all_roles_df is None:
        all_roles_df = get_roles_dataframe(exclude_admin=False, exclude_sin_rol=False, exclude_hidden=False)
    if all_roles_df.empty:
        return []

    def _norm(s):
        return re.sub(r"[^a-z0-9]+", "_", str(s or "").strip().lower()).strip("_")

    id_to_normname = {}
    normname_to_id = {}
    for row in all_roles_df.itertuples(index=False):
        rid = getattr(row, "id_rol", None)
        rname = getattr(row, "nombre", None)
        if pd.notna(rid) and pd.notna(rname):
            try:
                ridi = int(rid)
            except (TypeError, ValueError):
                continue
            nn = _norm(rname)
            id_to_normname[ridi] = nn
            if nn:
                normname_to_id[nn] = ridi

    dept_norm_names = {_norm(k) for k in (DEPARTMENT_EXPANSION_MAP or {}).keys()}
    indiv_norm_to_dept_norms = build_individual_role_to_departments_map()

    out_dept_norm = set()
    for rid in role_ids:
        try:
            ridi = int(rid)
        except (TypeError, ValueError):
            continue
        norm = id_to_normname.get(ridi)
        if not norm:
            continue
        if norm in dept_norm_names:
            out_dept_norm.add(norm)
            continue
        for dnorm in indiv_norm_to_dept_norms.get(norm, set()):
            out_dept_norm.add(dnorm)

    result = []
    seen = set()
    for dnorm in sorted(out_dept_norm):
        did = normname_to_id.get(dnorm)
        if did is None or did in seen:
            continue
        seen.add(did)
        result.append(int(did))
    return result


def only_department_roles(roles_df):
    """Filtra un dataframe de roles quedándose solo con los que son DEPARTAMENTOS
    (según DEPARTMENT_EXPANSION_MAP o prefijo dpto_). Devuelve df filtrado."""
    if roles_df is None or roles_df.empty:
        return roles_df.copy() if roles_df is not None else roles_df
    dept_names = {
        str(k).strip().lower()
        for k in (DEPARTMENT_EXPANSION_MAP or {}).keys()
    }
    mask = roles_df["nombre"].astype(str).str.strip().str.lower().apply(
        lambda n: (n in dept_names) or n.startswith("dpto_")
    )
    return roles_df.loc[mask].reset_index(drop=True)


def repair_task_type_roles_missing_from_departments():
    """Reparación conservadora: si algún tipo de tarea tiene un subset de los
    roles individuales de un dpto (ej: solo adm_tecnico pero no tecnico) se
    le agregan los faltantes, para no dejar a técnicos normales sin ver el
    tipo (sucede cuando la UI de Admin guardó un edit, por error, habiendo
    cargado roles individuales como defaults).

    Es idempotente: no inserta duplicados. Retorna dict con stats.

    ATENCIÓN: usa normalización robusta de nombres (igual que
    expand_role_ids_to_individuals) porque en la tabla `roles` los nombres
    pueden tener acentos ("Técnico") o capitalización distinta al
    DEPARTMENT_EXPANSION_MAP (que siempre es ASCII sin acentos).
    """
    conn = None
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'tipos_tarea_roles'
            )
        """)
        if not c.fetchone()[0]:
            return {"fixed_tipos": 0, "inserted_rows": 0}

        def _norm(s):
            return re.sub(r"[^a-z0-9]+", "_", str(s or "").strip().lower()).strip("_")

        c.execute("SELECT id_rol, nombre FROM roles")
        all_roles = c.fetchall()
        # id_rol -> nombre NORMALIZADO (para comparar con el mapa)
        id_to_normname = {}
        # nombre original (para construir reverse map si fuese necesario)
        id_to_origname = {}
        # nombre NORMALIZADO -> id_rol (para insertar)
        normname_to_id = {}
        for rid, name in all_roles:
            try:
                ridi = int(rid)
            except (TypeError, ValueError):
                continue
            oname = str(name or "").strip()
            nname = _norm(oname)
            id_to_normname[ridi] = nname
            id_to_origname[ridi] = oname.lower()
            if nname:
                normname_to_id[nname] = ridi

        # Expansión y mapa inverso, TODO con claves normalizadas.
        expansion_norm = {
            _norm(k): {_norm(v) for v in vs}
            for k, vs in (DEPARTMENT_EXPANSION_MAP or {}).items()
        }
        # indiv_norm_name -> set dept_norm_names (mapa inverso normalizado)
        indiv_norm_to_deptnorms = {}
        for dpt_norm, indiv_norms in expansion_norm.items():
            for inorm in indiv_norms:
                indiv_norm_to_deptnorms.setdefault(inorm, set()).add(dpt_norm)

        c.execute("SELECT id_tipo, id_rol FROM tipos_tarea_roles")
        rows = c.fetchall()
        # id_tipo -> set de NORMALIZED rolenames que ya tiene asignados
        tipo_to_rolnorms = {}
        # También guardamos los id_rol tal cual para no repetir lógica
        for tid, rid in rows:
            try:
                tidi = int(tid)
                ridi = int(rid)
            except (TypeError, ValueError):
                continue
            rnorm = id_to_normname.get(ridi)
            if not rnorm:
                continue
            tipo_to_rolnorms.setdefault(tidi, set()).add(rnorm)

        fixed_tipos = 0
        inserted_rows = 0
        insert_sql = """
            INSERT INTO tipos_tarea_roles (id_tipo, id_rol)
            SELECT %s, %s
            WHERE NOT EXISTS (
                SELECT 1 FROM tipos_tarea_roles
                WHERE id_tipo = %s AND id_rol = %s
            )
        """
        for tidi, rolnorms in tipo_to_rolnorms.items():
            # Qué deptos (normalizados) cubre este tipo según sus roles.
            implied_depts_norm = set()
            for rn in rolnorms:
                implied_depts_norm.update(indiv_norm_to_deptnorms.get(rn, set()))
                # Además, si el propio rolname ya ES un depto normalizado
                # (porque quedó un dpto_ en la tabla), lo agregamos también.
                if rn in expansion_norm:
                    implied_depts_norm.add(rn)

            # Qué roles individuales (normalizados) DEBERÍA tener para cubrir
            # todos esos deptos.
            expected_indiv_norm = set()
            for dname_norm in implied_depts_norm:
                expected_indiv_norm.update(expansion_norm.get(dname_norm, set()))
            missing_norm = expected_indiv_norm - rolnorms
            if not missing_norm:
                continue
            changed = False
            for mname_norm in sorted(missing_norm):
                mid = normname_to_id.get(mname_norm)
                # IMPORTANTE: NO usamos SOLO match EXACTO por _norm. El
                # heurístico endswith() era buggy porque agarraba dpto_tecnico
                # cuando no existía el rol "tecnico" individual e insertaba
                # el departamento incorrectamente. Si un rol individual faltante no
                # no existe en la tabla roles, simplemente no lo insertamos
                # (lo vamos a crear en un paso previo de inicialización).
                if mid is None:
                    continue
                c.execute(insert_sql, (int(tidi), int(mid), int(tidi), int(mid)))
                if int(c.rowcount or 0) > 0:
                    inserted_rows += 1
                    changed = True
            if changed:
                fixed_tipos += 1

        conn.commit()
        return {"fixed_tipos": fixed_tipos, "inserted_rows": inserted_rows}
    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        log_sql_error(f"Error en repair_task_type_roles_missing_from_departments: {e}")
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def repair_task_types_without_any_roles():
    """Saneo de emergencia para backups EXCEL VIEJOS donde la tabla
    `tipos_tarea_roles` está TOTALMENTE VACÍA (0 filas) o quedaron tipos de
    tarea (filas en `tipos_tarea`) SIN NINGÚN rol asociado.

    En ese escenario:
      - migrate_task_type_department_roles NO hace nada (no hay dpto_*).
      - repair_task_type_roles_missing_from_departments NO hace nada (itera
        sobre tipos que ya tienen al menos 1 fila en tipos_tarea_roles).

    Resultado de no correr esto: todos los usuarios ven 0 tipos en dropdown
    "Tipo de Tarea" -> warning "No hay datos suficientes..." + "No results".

    Solución (conservadora / compatible):
      1. Listar todos los roles INDIVIDUALES existentes (no dpto_*).
      2. Por cada id_tipo EN tipos_tarea que NO TIENE NINGÚN registro en
         tipos_tarea_roles -> insertar 1 fila POR CADA rol individual.
      3. Idempotente (WHERE NOT EXISTS) y retorna stats.
    """
    conn = None
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'tipos_tarea_roles'
            )
        """)
        if not c.fetchone()[0]:
            return {"orphan_tipos": 0, "inserted_rows": 0}

        c.execute("SELECT id_rol, nombre FROM roles")
        all_roles = c.fetchall()
        # Filtramos SOLO roles INDIVIDUALES (no dpto_*)
        individual_role_ids = []
        depto_names_lower = {
            str(k or "").strip().lower()
            for k in (DEPARTMENT_EXPANSION_MAP or {}).keys()
        }
        for rid, name in all_roles:
            try:
                ridi = int(rid)
            except (TypeError, ValueError):
                continue
            rname = str(name or "").strip().lower()
            if not rname:
                continue
            if rname in depto_names_lower or rname.startswith("dpto_"):
                continue
            individual_role_ids.append(ridi)
        if not individual_role_ids:
            return {"orphan_tipos": 0, "inserted_rows": 0}

        # Tipos en tipos_tarea SIN NINGÚN registro en tipos_tarea_roles
        c.execute("""
            SELECT t.id
            FROM tipos_tarea t
            WHERE NOT EXISTS (
                SELECT 1 FROM tipos_tarea_roles r WHERE r.id_tipo = t.id
            )
        """)
        orphan_rows = c.fetchall()
        orphan_ids = []
        for row in orphan_rows:
            try:
                orphan_ids.append(int(row[0]))
            except (TypeError, ValueError):
                continue
        if not orphan_ids:
            return {"orphan_tipos": 0, "inserted_rows": 0}

        insert_sql = """
            INSERT INTO tipos_tarea_roles (id_tipo, id_rol)
            SELECT %s, %s
            WHERE NOT EXISTS (
                SELECT 1 FROM tipos_tarea_roles
                WHERE id_tipo = %s AND id_rol = %s
            )
        """
        inserted_rows = 0
        for tidi in orphan_ids:
            for ridi in individual_role_ids:
                c.execute(insert_sql, (tidi, ridi, tidi, ridi))
                try:
                    if int(c.rowcount or 0) > 0:
                        inserted_rows += 1
                except Exception:
                    pass

        conn.commit()
        return {
            "orphan_tipos": len(orphan_ids),
            "inserted_rows": inserted_rows,
            "individual_roles": len(individual_role_ids),
        }
    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        log_sql_error(f"Error en repair_task_types_without_any_roles: {e}")
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def migrate_task_type_department_roles():

    conn = None
    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'tipos_tarea_roles'
            )
        """)
        if not c.fetchone()[0]:
            return None

        def _norm(s):
            return re.sub(r"[^a-z0-9]+", "_", str(s or "").strip().lower()).strip("_")

        c.execute("SELECT id_rol, nombre FROM roles")
        all_roles = c.fetchall()
        id_to_normname = {}
        normname_to_id = {}
        for rid, name in all_roles:
            try:
                ridi = int(rid)
            except (TypeError, ValueError):
                continue
            oname = str(name or "").strip()
            nname = _norm(oname)
            id_to_normname[rid] = nname
            if nname:
                normname_to_id[nname] = rid

        # Expansión normalizada: dpto_norm -> set indiv_norm_names.
        expansion_norm = {
            _norm(k): {_norm(v) for v in vs}
            for k, vs in (DEPARTMENT_EXPANSION_MAP or {}).items()
        }

        c.execute("SELECT DISTINCT id_rol FROM tipos_tarea_roles")
        referenced_role_ids = [int(row[0]) for row in c.fetchall()]

        dept_rows = []
        for rid in referenced_role_ids:
            try:
                ridi = int(rid)
            except (TypeError, ValueError):
                continue
            norm = id_to_normname.get(ridi)
            if not norm:
                continue
            expanded_norms = expansion_norm.get(norm)
            if expanded_norms is None and norm.startswith("dpto_"):
                core = norm[len("dpto_"):]
                derived = {f"adm_{core}", core}
                # Solo los que realmente existen en la tabla roles
                expanded_norms = {n for n in derived if n in normname_to_id}
            if expanded_norms:
                dept_rows.append((ridi, norm, expanded_norms))

        if not dept_rows:
            conn.commit()
            return {"migrated": 0, "removed_dept_rows": 0}

        insert_sql = """
            INSERT INTO tipos_tarea_roles (id_tipo, id_rol)
            SELECT %s, %s
            WHERE NOT EXISTS (
                SELECT 1 FROM tipos_tarea_roles
                WHERE id_tipo = %s AND id_rol = %s
            )
        """

        c.execute("SELECT id_tipo, id_rol FROM tipos_tarea_roles")
        existing_tipo_rol = set(
            (int(t), int(r)) for t, r in c.fetchall()
            if t is not None and r is not None
        )

        inserted_new = 0
        dept_rows_to_delete = []
        for dept_rid, _dept_norm, expanded_norms in dept_rows:
            c.execute("SELECT id_tipo FROM tipos_tarea_roles WHERE id_rol = %s", (int(dept_rid),))
            tipo_ids_dept = [int(row[0]) for row in c.fetchall() if row and row[0] is not None]
            target_ids = []
            for target_norm in expanded_norms:
                target_rid = normname_to_id.get(target_norm)
                if target_rid is not None:
                    target_ids.append(int(target_rid))
            for tid in tipo_ids_dept:
                for target_rid in target_ids:
                    if (tid, target_rid) in existing_tipo_rol:
                        continue
                    c.execute(insert_sql, (int(tid), int(target_rid), int(tid), int(target_rid)))
                    inserted_new += int(c.rowcount or 0)
                    existing_tipo_rol.add((tid, target_rid))
            dept_rows_to_delete.append(int(dept_rid))

        deleted_dept = 0
        if dept_rows_to_delete:
            c.execute(
                f"DELETE FROM tipos_tarea_roles WHERE id_rol IN ({','.join(['%s'] * len(dept_rows_to_delete))})",
                tuple(dept_rows_to_delete),
            )
            deleted_dept = int(c.rowcount or 0)

        conn.commit()
        return {"migrated": inserted_new, "removed_dept_rows": deleted_dept}
    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        log_sql_error(f"Error en migrate_task_type_department_roles: {e}")
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass



def bootstrap_missing_roles_and_users():
    """Asegura la existencia de roles individuales mínimos en la tabla `roles`.

    Política (IMPORTANTE):
      - Los roles individuales `tecnico`, `comercial`, `compras` existen EXCLUSIVAMENTE
        para ser usados en la tabla `tipos_tarea_roles` (asignación de tipos de tarea).
      - NUNCA deben ser asignados directamente a `usuarios.rol_id`; los usuarios
        siguen usando roles `dpto_*` (su departamento), `adm_*` (jefatura) o
        `admin`/`hipervisor` tal cual en producción.

    Por lo tanto esta función:
      - Crea `tecnico` / `comercial` / `compras` si faltan.
      - NO modifica `usuarios.rol_id` en absoluto.

    Idempotente. Retorna dict de stats.
    """
    import re as _re

    def _norm(s):
        return _re.sub(r"[^a-z0-9]+", "_", str(s or "").strip().lower()).strip("_")

    MUST_EXIST_ROLES = [
        # (nombre, descripcion, view_type)
        # Importante: estos 3 son roles individuales para la tabla
        # `tipos_tarea_roles` (asignación de tipos de tarea). NO son
        # departamentos ni jefaturas, y NUNCA deben usarse como
        # `usuarios.rol_id` ni tienen `view_type` asignado (debe ser NULL).
        ("tecnico", "Rol técnico individual. Pertenencia a dpto_tecnico.", None),
        ("comercial", "Rol comercial individual. Pertenencia a dpto_comercial.", None),
        ("compras", "Rol de compras individual. Pertenencia a dpto_compras.", None),
    ]

    conn = get_connection()
    c = conn.cursor()
    stats = {"roles_creados": [], "already_ok": True}

    try:
        c.execute("SELECT id_rol, nombre, is_hidden FROM roles ORDER BY id_rol")
        existing_rows = [
            (int(rid), str(n or "").strip(), bool(h)) for rid, n, h in c.fetchall()
        ]
        existing_by_norm = {
            _norm(n): (rid, n, h) for rid, n, h in existing_rows
        }

        for rol_name, rol_desc, view_type in MUST_EXIST_ROLES:
            rn = _norm(rol_name)
            if rn in existing_by_norm:
                continue
            c.execute(
                """
                INSERT INTO roles (nombre, descripcion, is_hidden, view_type)
                VALUES (%s, %s, FALSE, %s)
                RETURNING id_rol
                """,
                (rol_name, rol_desc, view_type),
            )
            new_id = c.fetchone()[0]
            stats["roles_creados"].append((rol_name, int(new_id)))
            existing_by_norm[rn] = (int(new_id), rol_name, False)

        if stats["roles_creados"]:
            stats["already_ok"] = False
        conn.commit()
        return stats
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_sql_error(f"Error bootstrap_missing_roles_and_users: {e}")
        stats["error"] = str(e)
        stats["already_ok"] = False
        return stats
    finally:
        try:
            conn.close()
        except Exception:
            pass

def add_task_type(descripcion):
    """Agrega un nuevo tipo de tarea a la base de datos con validación de duplicados"""
    # Normalizar la descripción: eliminar espacios extra y convertir a formato título
    descripcion_normalizada = ' '.join(descripcion.strip().split()).title()
    
    conn = get_connection()
    c = conn.cursor()
    try:
        # Verificar si ya existe un tipo similar (insensible a mayúsculas/minúsculas y espacios)
        c.execute("SELECT id_tipo FROM tipos_tarea WHERE LOWER(TRIM(descripcion)) = LOWER(TRIM(%s))", 
                 (descripcion_normalizada,))
        existing = c.fetchone()
        
        if existing:
            return False  # Ya existe un tipo similar
        
        c.execute("INSERT INTO tipos_tarea (descripcion) VALUES (%s)", (descripcion_normalizada,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def add_client(nombre):
    """Agrega un nuevo cliente a la base de datos"""
    try:
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO clientes (nombre) VALUES (%s)", (nombre,))
            conn.commit()
            return True
    except Exception:
        return False  # Ya existe un cliente con ese nombre

def add_client_full(nombre, organizacion=None, telefono=None, email=None, cuit=None, celular=None, web=None, notes=None, alias=None):
    try:
        with db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'clientes'")
            existing_cols = {r[0] for r in c.fetchall()}
            fields = ["nombre"]
            values = [nombre]
            placeholders = ["%s"]
            optional_map = {
                "alias": (alias or "").strip(),
                "direccion": organizacion or "",
                "organizacion": organizacion or "",
                "telefono": telefono or "",
                "email": email or "",
                "cuit": normalize_cuit(cuit),
                "celular": celular or "",
                "web": normalize_web(web),
                "notes": notes or "",
            }
            for col, val in optional_map.items():
                if col in existing_cols:
                    fields.append(col)
                    values.append(val)
                    placeholders.append("%s")
            query = f"INSERT INTO clientes ({', '.join(fields)}) VALUES ({', '.join(placeholders)}) RETURNING id_cliente"
            c.execute(query, tuple(values))
            row = c.fetchone()
            conn.commit()
            return int(row[0]) if row else None
    except Exception:
        return None

def check_client_duplicate(cuit, nombre, exclude_id=None):
    """
    Verifica si existe un cliente duplicado por CUIT o Nombre (normalizado).
    Retorna (True, mensaje_error) si existe, o (False, None) si no.
    """
    from .utils import normalize_text
    
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # 1. Verificar por CUIT si existe
        if cuit and str(cuit).strip():
            clean_cuit = normalize_cuit(cuit)
            query = "SELECT id_cliente, nombre FROM clientes WHERE cuit = %s"
            params = [clean_cuit]
            if exclude_id:
                query += " AND id_cliente != %s"
                params.append(exclude_id)
                
            c.execute(query, tuple(params))
            row = c.fetchone()
            if row:
                return True, f"Ya existe un cliente con el CUIT {clean_cuit} ({row[1]})."

        # 2. Verificar por Nombre (normalizado)
        if nombre and str(nombre).strip():
            nombre_norm = normalize_text(nombre)
            
            # Traer todos los clientes para comparar normalizado
            c.execute("SELECT id_cliente, nombre FROM clientes")
            rows = c.fetchall()
            
            for cid, cnombre in rows:
                if exclude_id and cid == exclude_id:
                    continue
                    
                if normalize_text(cnombre) == nombre_norm:
                    return True, f"Ya existe un cliente con el nombre '{cnombre}' (similar a '{nombre}')."
                    
        return False, None
        
    finally:
        conn.close()

def add_cliente_solicitud(nombre, organizacion=None, telefono=None, requested_by=None, email=None, cuit=None, celular=None, web=None, tipo=None, temp_cliente_id=None, notes=None, raise_on_error=False):
    """Crea una solicitud de cliente pendiente de aprobación.
    Campos opcionales soportados: cuit, celular, web, tipo.
    """
    ensure_projects_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        try:
            c.execute('''
                CREATE TABLE IF NOT EXISTS cliente_solicitudes (
                    id SERIAL PRIMARY KEY,
                    nombre VARCHAR(200) NOT NULL,
                    organizacion VARCHAR(300),
                    telefono VARCHAR(50),
                    email VARCHAR(100),
                    cuit VARCHAR(32),
                    celular VARCHAR(50),
                    web VARCHAR(300),
                    tipo VARCHAR(50),
                    requested_by INTEGER NOT NULL REFERENCES usuarios(id),
                    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    temp_cliente_id INTEGER,
                    notes TEXT
                )
            ''')
            # Asegurar columna email si la tabla existía previamente sin ella
            try:
                c.execute("ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS email VARCHAR(100)")
            except Exception:
                pass
            # Asegurar nuevas columnas si no existían
            for ddl in [
                "ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS cuit VARCHAR(32)",
                "ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS celular VARCHAR(50)",
                "ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS web VARCHAR(300)",
                "ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS tipo VARCHAR(50)",
            "ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS temp_cliente_id INTEGER",
            "ALTER TABLE cliente_solicitudes ADD COLUMN IF NOT EXISTS notes TEXT"
        ]:
                try:
                    c.execute(ddl)
                except Exception:
                    pass
            for ddl in [
                "ALTER TABLE cliente_solicitudes ALTER COLUMN telefono TYPE VARCHAR(50)",
                "ALTER TABLE cliente_solicitudes ALTER COLUMN celular TYPE VARCHAR(50)",
            ]:
                try:
                    c.execute(ddl)
                except Exception:
                    pass
        except Exception as e:
            log_sql_error(f"No se pudo asegurar tabla cliente_solicitudes: {e}")
        c.execute(
            """
            INSERT INTO cliente_solicitudes (nombre, organizacion, telefono, email, cuit, celular, web, tipo, requested_by, temp_cliente_id, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (nombre, organizacion or '', telefono or '', email or '', normalize_cuit(cuit) or '', celular or '', normalize_web(web) or '', tipo or '', int(requested_by), temp_cliente_id, notes or '')
        )
        new_id_row = c.fetchone()
        new_id = int(new_id_row[0]) if new_id_row else None
        if new_id is not None:
            try:
                ensure_notifications_schema()
            except Exception:
                pass
            try:
                _queue_notification_event_in_connection(
                    conn,
                    'cliente_solicitud_creada',
                    {
                        'solicitud_id': new_id,
                        'requested_by': int(requested_by) if requested_by is not None else None,
                        'cliente': nombre or '',
                        'nombre': nombre or '',
                        'organizacion': organizacion or '',
                        'telefono': telefono or '',
                        'email': email or '',
                        'cuit': normalize_cuit(cuit) or '',
                        'celular': celular or '',
                        'web': normalize_web(web) or '',
                        'tipo': tipo or '',
                        'detalle': notes or '',
                    },
                    dedupe_key=f"cliente_solicitud_creada:{new_id}"
                )
            except Exception as e:
                log_sql_error(f"No se pudo encolar notificación de solicitud creada: {e}")
        conn.commit()
        return new_id
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error creando solicitud de cliente: {e}")
        if raise_on_error:
            raise
        return None
    finally:
        conn.close()

def get_cliente_solicitudes_df(estado='pendiente'):
    """Obtiene solicitudes de clientes como DataFrame"""
    ensure_projects_schema()
    engine = get_engine()
    try:
        q = text("SELECT id, nombre, organizacion, telefono, email, cuit, celular, web, tipo, requested_by, estado, created_at, notes FROM cliente_solicitudes WHERE estado = :estado ORDER BY created_at DESC")
        return pd.read_sql_query(q, con=engine, params={"estado": estado})
    except Exception as e:
        log_sql_error(f"Error listando solicitudes de clientes: {e}")
        return pd.DataFrame()

def approve_cliente_solicitud(solicitud_id):
    """Aprueba solicitud: crea cliente y marca como aprobada"""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT nombre, organizacion, telefono, email, cuit, celular, web, notes, requested_by FROM cliente_solicitudes WHERE id = %s", (int(solicitud_id),))
        row = c.fetchone()
        if not row:
            return False, "Solicitud no encontrada"
        nombre, organizacion, telefono, email, cuit, celular, web, notes, requested_by = row
        
        # Limpieza básica de datos y Normalización de CUIT
        cuit = "".join(filter(str.isdigit, str(cuit))) if cuit else ""
        web = (web or "").strip()
        if web and not (web.startswith("http://") or web.startswith("https://")):
             # Intentar arreglar web si no tiene protocolo
             web = "https://" + web

        # Detectar columnas existentes para armar el INSERT dinámicamente
        c.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'clientes'")
        existing_cols = {r[0] for r in c.fetchall()}

        # Campos obligatorios/base
        insert_fields = ["nombre"]
        insert_values = [nombre]
        insert_placeholders = ["%s"]

        # Campos opcionales (mapeo: nombre_columna -> valor)
        optional_map = {
            "organizacion": organizacion or '',
            "telefono": telefono or '',
            "email": email or '',
            "cuit": cuit,
            "celular": celular or '',
            "web": web,
            "notes": notes or '',
            # Solo intentamos insertar en 'direccion' si existe la columna, usando 'organizacion' como fallback si se desea,
            # o simplemente lo omitimos si el usuario prefiere no inventar datos.
            # Según instrucción del usuario: "si no existe que no intente guardar nada".
            # Así que solo guardamos si existe, y usamos 'organizacion' como valor por defecto legacy (o string vacío).
            "direccion": organizacion or '' 
        }

        # Verificar si ya existe el cliente (por CUIT o Nombre)
        existing_client_id = None
        
        # 1. Buscar por CUIT si está presente
        if cuit:
            # Asegurarse que la columna cuit existe antes de consultar
            if "cuit" in existing_cols:
                c.execute("SELECT id_cliente FROM clientes WHERE cuit = %s", (cuit,))
                row_exist = c.fetchone()
                if row_exist:
                    existing_client_id = row_exist[0]
        
        # 2. Si no encontró por CUIT, buscar por Nombre (case insensitive)
        if not existing_client_id and nombre:
            c.execute("SELECT id_cliente FROM clientes WHERE LOWER(nombre) = LOWER(%s)", (nombre.strip(),))
            row_exist = c.fetchone()
            if row_exist:
                existing_client_id = row_exist[0]

        if existing_client_id:
            # ACTUALIZAR existente
            update_assignments = []
            update_values = []
            
            for col, val in optional_map.items():
                # Solo actualizamos si la columna existe y el valor no está vacío
                # Esto permite completar datos faltantes sin borrar los existentes
                if col in existing_cols and val:
                    update_assignments.append(f"{col} = %s")
                    update_values.append(val)
            
            if update_assignments:
                query = f"UPDATE clientes SET {', '.join(update_assignments)} WHERE id_cliente = %s"
                update_values.append(existing_client_id)
                c.execute(query, tuple(update_values))
        else:
            # INSERTAR nuevo
            insert_fields = ["nombre"]
            insert_values = [nombre]
            insert_placeholders = ["%s"]

            for col, val in optional_map.items():
                if col in existing_cols:
                    insert_fields.append(col)
                    insert_values.append(val)
                    insert_placeholders.append("%s")

            query = f"""
                INSERT INTO clientes ({', '.join(insert_fields)}) 
                VALUES ({', '.join(insert_placeholders)}) 
            """
            # Crear cliente
            c.execute(query, tuple(insert_values))
        
        # Marcar solicitud
        c.execute("UPDATE cliente_solicitudes SET estado = 'aprobada' WHERE id = %s", (int(solicitud_id),))
        try:
            ensure_notifications_schema()
        except Exception:
            pass
        try:
            _queue_notification_event_in_connection(
                conn,
                'cliente_solicitud_aprobada',
                {
                    'solicitud_id': int(solicitud_id),
                    'requested_by': int(requested_by) if requested_by is not None else None,
                    'cliente': nombre or '',
                    'nombre': nombre or '',
                    'telefono': telefono or '',
                    'email': email or '',
                    'cuit': cuit or '',
                    'detalle': notes or 'La solicitud fue aprobada y el cliente quedó disponible para operar.',
                    'fecha': datetime.now().strftime("%d/%m/%Y %H:%M"),
                },
                dedupe_key=f"cliente_solicitud_aprobada:{int(solicitud_id)}"
            )
        except Exception as e:
            log_sql_error(f"No se pudo encolar notificación de solicitud aprobada: {e}")
        conn.commit()
        return True, "Cliente aprobado exitosamente"
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error aprobando solicitud de cliente: {e}")
        return False, str(e)
    finally:
        conn.close()

def reject_cliente_solicitud(solicitud_id):
    """Rechaza solicitud. Si tiene cliente temporal asociado, elimina también ese cliente y sus datos."""
    conn = get_connection()
    try:
        c = conn.cursor()
        
        # 1. Obtener solicitud y cliente temporal asociado (si existe)
        c.execute(
            """
            SELECT nombre, organizacion, telefono, email, cuit, web, notes, requested_by, temp_cliente_id
            FROM cliente_solicitudes
            WHERE id = %s
            """,
            (int(solicitud_id),)
        )
        row = c.fetchone()
        
        if row:
            nombre, organizacion, telefono, email, cuit, web, notes, requested_by, temp_cliente_id = row
            
            if temp_cliente_id is not None:
                client_id = int(temp_cliente_id)
                
                # 2. Eliminar datos asociados al cliente temporal
                # Orden importante: primero tablas que referencian a clientes
                c.execute("DELETE FROM registros WHERE id_cliente = %s", (client_id,))
                c.execute("DELETE FROM proyectos WHERE cliente_id = %s", (client_id,))
                c.execute("DELETE FROM contactos WHERE etiqueta_tipo = 'cliente' AND etiqueta_id = %s", (client_id,))
                c.execute("DELETE FROM clientes_puntajes WHERE id_cliente = %s", (client_id,))
                c.execute("DELETE FROM clientes WHERE id_cliente = %s", (client_id,))
            try:
                ensure_notifications_schema()
            except Exception:
                pass
            try:
                _queue_notification_event_in_connection(
                    conn,
                    'cliente_solicitud_rechazada',
                    {
                        'solicitud_id': int(solicitud_id),
                        'requested_by': int(requested_by) if requested_by is not None else None,
                        'cliente': nombre or '',
                        'nombre': nombre or '',
                        'organizacion': organizacion or '',
                        'telefono': telefono or '',
                        'email': email or '',
                        'cuit': cuit or '',
                        'web': web or '',
                        'detalle': notes or 'La solicitud fue rechazada durante la revisión administrativa.',
                        'fecha': datetime.now().strftime("%d/%m/%Y %H:%M"),
                    },
                    dedupe_key=f"cliente_solicitud_rechazada:{int(solicitud_id)}"
                )
            except Exception as e:
                log_sql_error(f"No se pudo encolar notificación de solicitud rechazada: {e}")
        
        # 3. Eliminar la solicitud
        c.execute("DELETE FROM cliente_solicitudes WHERE id = %s", (int(solicitud_id),))
        
        conn.commit()
        return True, "Solicitud rechazada y datos limpiados correctamente"
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error rechazando solicitud de cliente: {e}")
        return False, str(e)
    finally:
        conn.close()

def add_tecnico(nombre):
    """Agrega un nuevo técnico a la base de datos"""
    return get_or_create_tecnico(nombre)

def add_modalidad(modalidad):
    """Agrega una nueva modalidad a la base de datos"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO modalidades_tarea (descripcion) VALUES (%s)", (modalidad,))
        conn.commit()
        return True
    except Exception:
        return False  # Ya existe una modalidad con ese nombre
    finally:
        conn.close()

def get_or_create_tecnico(nombre, conn=None):
    """Obtiene el ID de un técnico o lo crea si no existe"""
    from .utils import normalize_text  # Importar la función de normalización
    
    # Mapeo de nombres antiguos a nuevos para mantener consistencia
    KNOWN_ALIASES = {
        "ignacio sosa": "Ignacio martin Sosa",
        "danel giorgio": "Danel Dario Giorgio",
        "daniel vieira": "Daniel alejandro Vieira maia",
        "leandro torres": "Leandro ivan Torres sogno",
        "luciano torres": "Luciano jose Torres sogno",
        "lucas chavez": "Lucas fabian Chavez",
        "lucas chávez": "Lucas fabian Chavez",
        "sergio colgue": "Sergio gabriel Colque huarachi"
    }

    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    
    # Normalizar el nombre para búsqueda
    nombre_normalizado = normalize_text(nombre)
    
    # Verificar si es un alias conocido
    if nombre_normalizado in KNOWN_ALIASES:
        # Usar el nombre correcto en lugar del alias
        nombre = KNOWN_ALIASES[nombre_normalizado]
        nombre_normalizado = normalize_text(nombre)
    
    # Buscar técnico existente por nombre normalizado
    c.execute("SELECT id_tecnico, nombre FROM tecnicos")
    tecnicos = c.fetchall()
    
    for tecnico_id, tecnico_nombre in tecnicos:
        if normalize_text(tecnico_nombre) == nombre_normalizado:
            if close_conn:
                conn.close()
            return tecnico_id
    
    # Si no se encontró, crear nuevo técnico con el nombre (posiblemente corregido)
    try:
        c.execute("INSERT INTO tecnicos (nombre) VALUES (%s) RETURNING id_tecnico", (nombre,))
        tecnico_id = c.fetchone()[0]
        conn.commit()
        if close_conn:
            conn.close()
        return tecnico_id
    except Exception as e:
        if close_conn:
            conn.close()
        raise e


def repair_tecnicos_known_aliases():
    from .utils import normalize_text
    alias_map = {
        "danel giorgio": "Danel Dario Giorgio",
        "ignacio sosa": "Ignacio martin Sosa",
        "daniel vieira": "Daniel alejandro Vieira maia",
        "leandro torres": "Leandro ivan Torres sogno",
        "luciano torres": "Luciano jose Torres sogno",
        "lucas chavez": "Lucas fabian Chavez",
        "lucas chávez": "Lucas fabian Chavez",
        "sergio colgue": "Sergio gabriel Colque huarachi",
    }

    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id_tecnico, nombre FROM tecnicos")
        rows = [(int(r[0]), str(r[1] or "")) for r in c.fetchall()]
        if not rows:
            return 0

        name_by_id = {tid: tname for tid, tname in rows}
        id_by_norm = {}
        for tid, tname in rows:
            n = normalize_text(tname)
            if not n:
                continue
            id_by_norm.setdefault(n, []).append(tid)

        updated = 0
        for alias_raw, canonical_raw in alias_map.items():
            alias_norm = normalize_text(alias_raw)
            canonical_id = int(get_or_create_tecnico(canonical_raw, conn=conn))
            for alias_id in id_by_norm.get(alias_norm, []):
                if alias_id == canonical_id:
                    continue
                c.execute(
                    "UPDATE registros SET id_tecnico = %s WHERE id_tecnico = %s",
                    (canonical_id, int(alias_id)),
                )
                updated += int(c.rowcount or 0)
                c.execute("SELECT 1 FROM registros WHERE id_tecnico = %s LIMIT 1", (int(alias_id),))
                if not c.fetchone():
                    c.execute("DELETE FROM tecnicos WHERE id_tecnico = %s", (int(alias_id),))

        conn.commit()
        return updated
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_app_error(e, module="database", function="repair_tecnicos_known_aliases")
        return 0
    finally:
        conn.close()


def repair_registros_usuario_assignment():
    """
    Re-sincroniza registros.usuario_id usando el tecnico asociado al registro.
    Esto corrige cruces históricos cuando un registro cambia de técnico y el
    usuario asignado no se actualiza en la misma operación.
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            UPDATE registros r
            SET usuario_id = u.id
            FROM tecnicos t
            JOIN usuarios u
              ON LOWER(TRIM(regexp_replace(u.nombre || ' ' || u.apellido, '\\s+', ' ', 'g')))
               = LOWER(TRIM(regexp_replace(t.nombre, '\\s+', ' ', 'g')))
            WHERE r.id_tecnico = t.id_tecnico
              AND (r.usuario_id IS NULL OR r.usuario_id <> u.id)
            """
        )
        updated = int(c.rowcount or 0)
        conn.commit()
        return updated
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_app_error(e, module="database", function="repair_registros_usuario_assignment")
        return 0
    finally:
        conn.close()


def repair_registros_fecha_consistency():
    """
    Normaliza registros.fecha a formato ISO (YYYY-MM-DD) y completa fechas vacías.

    Estrategia para completar vacíos:
    - Forward-fill por grupo (usuario_id si existe, sino id_tecnico) en orden de id.
    - Si un grupo no tiene ninguna fecha válida, usa created_at::date.
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            WITH parsed AS (
                SELECT
                    r.id,
                    COALESCE(r.usuario_id, -r.id_tecnico) AS k,
                    r.created_at,
                    CASE
                        WHEN btrim(COALESCE(r.fecha, '')) = '' THEN NULL
                        WHEN r.fecha ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN
                            CASE
                                WHEN r.created_at IS NOT NULL
                                 AND substring(r.fecha from 6 for 2)::int <= 12
                                 AND substring(r.fecha from 9 for 2)::int <= 12
                                 AND make_date(
                                        substring(r.fecha from 1 for 4)::int,
                                        substring(r.fecha from 9 for 2)::int,
                                        substring(r.fecha from 6 for 2)::int
                                     ) = r.created_at::date
                                 AND substring(r.fecha from 1 for 10)::date <> r.created_at::date
                                THEN
                                    make_date(
                                        substring(r.fecha from 1 for 4)::int,
                                        substring(r.fecha from 9 for 2)::int,
                                        substring(r.fecha from 6 for 2)::int
                                    )
                                ELSE
                                    substring(r.fecha from 1 for 10)::date
                            END
                        WHEN r.fecha ~ '^[0-9]{2}/[0-9]{2}/[0-9]{2}$' THEN to_date(r.fecha, 'DD/MM/YY')
                        WHEN r.fecha ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$' THEN to_date(r.fecha, 'DD/MM/YYYY')
                        ELSE NULL
                    END AS fecha_d
                FROM registros r
            ),
            grp AS (
                SELECT
                    id,
                    k,
                    created_at,
                    fecha_d,
                    SUM(CASE WHEN fecha_d IS NOT NULL THEN 1 ELSE 0 END)
                        OVER (PARTITION BY k ORDER BY id) AS g
                FROM parsed
            ),
            filled AS (
                SELECT
                    id,
                    COALESCE(
                        MAX(fecha_d) OVER (PARTITION BY k, g),
                        MIN(fecha_d) OVER (PARTITION BY k),
                        created_at::date,
                        CURRENT_DATE
                    ) AS fecha_fill
                FROM grp
            )
            UPDATE registros r
            SET fecha = to_char(f.fecha_fill, 'YYYY-MM-DD')
            FROM filled f
            WHERE r.id = f.id
              AND (
                    btrim(COALESCE(r.fecha, '')) = ''
                    OR r.fecha !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                    OR (
                        r.fecha ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                        AND r.created_at IS NOT NULL
                        AND substring(r.fecha from 6 for 2)::int <= 12
                        AND substring(r.fecha from 9 for 2)::int <= 12
                        AND make_date(
                                substring(r.fecha from 1 for 4)::int,
                                substring(r.fecha from 9 for 2)::int,
                                substring(r.fecha from 6 for 2)::int
                            ) = r.created_at::date
                        AND substring(r.fecha from 1 for 10)::date <> r.created_at::date
                    )
                  )
            """
        )
        updated = int(c.rowcount or 0)
        conn.commit()
        return updated
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_app_error(e, module="database", function="repair_registros_fecha_consistency")
        return 0
    finally:
        conn.close()

def get_or_create_cliente(nombre, conn=None):
    """Obtiene el ID de un cliente o lo crea si no existe (con búsqueda robusta)"""
    nombre_str = str(nombre).strip()
    if not nombre_str:
        return None

    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True

    try:
        c = conn.cursor()
        
        # 1. Búsqueda Exacta
        c.execute("SELECT id_cliente FROM clientes WHERE nombre = %s", (nombre_str,))
        result = c.fetchone()
        if result:
            return result[0]
            
        # 2. Búsqueda insensible a case y espacios (PostgreSQL)
        # Normalizamos el input a un solo espacio y lowercase en Python
        nombre_clean = " ".join(nombre_str.split()).lower()
        
        # Buscamos en DB normalizando también el campo nombre (quita espacios extra, tabs, newlines)
        c.execute("""
            SELECT id_cliente FROM clientes 
            WHERE LOWER(TRIM(regexp_replace(nombre, '\\s+', ' ', 'g'))) = %s
        """, (nombre_clean,))
        result = c.fetchone()
        if result:
            return result[0]
            
        # 3. Búsqueda ignorando puntuación común (.,) para casos como S.R.L vs SRL
        nombre_nopunct = nombre_clean.replace('.', '').replace(',', '')
        c.execute("""
            SELECT id_cliente FROM clientes 
            WHERE LOWER(TRIM(regexp_replace(replace(replace(nombre, '.', ''), ',', ''), '\\s+', ' ', 'g'))) = %s
        """, (nombre_nopunct,))
        result = c.fetchone()
        if result:
            return result[0]

        # 4. Crear nuevo cliente si no existe
        c.execute("INSERT INTO clientes (nombre) VALUES (%s) RETURNING id_cliente", (nombre_str,))
        cliente_id = c.fetchone()[0]
        
        # Si la conexión es nuestra, hacemos commit. 
        # Si es externa, dejamos que el caller haga commit (pero hacemos commit parcial aquí para devolver ID válido inmediatamente)
        # OJO: Si es transacción externa, commit aquí confirmaría todo lo anterior.
        # Mejor: Solo commit si should_close es True.
        if should_close:
            conn.commit()
            
        return cliente_id
    except Exception as e:
        if should_close:
            conn.rollback()
        # Re-raise o loggear? Mejor re-raise para que el caller sepa
        raise e
    finally:
        if should_close:
            conn.close()

def get_empleado_rol_id(nombre_empleado, conn=None):
    """Obtiene el rol_id de un empleado basándose en su nombre y la coincidencia con usuarios o nómina"""
    from .utils import normalize_text
    import re

    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    c = conn.cursor()

    try:
        empleado_normalizado = normalize_text(nombre_empleado)
        if not empleado_normalizado:
            if close_conn:
                conn.close()
            return None

        stopwords = {"de", "del", "la", "las", "los", "y", "e", "san", "santa", "da", "do", "das", "dos"}
        def tokens(s):
            return [t for t in re.split(r"\s+", normalize_text(s)) if t and t not in stopwords]

        emp_tokens = tokens(empleado_normalizado)
        if not emp_tokens:
            if close_conn:
                conn.close()
            return None

        # Heurística: últimos 2 tokens como apellidos, resto como nombres
        surname_tokens = emp_tokens[-2:] if len(emp_tokens) >= 2 else emp_tokens[-1:]
        name_tokens = emp_tokens[:-2] if len(emp_tokens) >= 3 else (emp_tokens[:-1] if len(emp_tokens) == 2 else [])

        c.execute("""
            SELECT u.id, u.nombre, u.apellido, u.rol_id
            FROM usuarios u
            WHERE u.nombre IS NOT NULL AND u.apellido IS NOT NULL
        """)
        usuarios = c.fetchall()

        best = None  # (score, rol_id)
        for _, nombre, apellido, rol_id in usuarios:
            user_name_tokens = tokens(nombre)
            user_surname_tokens = tokens(apellido)

            surname_match = sum(1 for t in surname_tokens if t in user_surname_tokens)
            name_match = sum(1 for t in name_tokens if t in user_name_tokens)
            global_intersection = len(set(emp_tokens) & (set(user_name_tokens) | set(user_surname_tokens)))

            # Ponderar apellidos + bonus por 3+ tokens en común
            score = (2 * surname_match) + name_match + (1 if global_intersection >= 3 else 0)

            # Umbral: al menos 1 apellido y 1 nombre, o 2 apellidos, o intersección global fuerte
            passes = (surname_match >= 2) or (surname_match >= 1 and name_match >= 1) or (global_intersection >= 3)
            if passes:
                if best is None or score > best[0]:
                    best = (score, rol_id)

        if best is not None:
            if close_conn:
                conn.close()
            return best[1]

        # Fallback: buscar en nómina con la misma heurística y mapear a rol por departamento/cargo
        c.execute("""
            SELECT nombre, apellido, departamento, cargo
            FROM nomina
            WHERE activo = true
        """)
        nomina_results = c.fetchall()

        best_nomina = None  # (score, departamento, cargo)
        for nombre, apellido, departamento, cargo in nomina_results:
            n_tokens = tokens(nombre)
            a_tokens = tokens(apellido)

            surname_match = sum(1 for t in surname_tokens if t in a_tokens)
            name_match = sum(1 for t in name_tokens if t in n_tokens)
            global_intersection = len(set(emp_tokens) & (set(n_tokens) | set(a_tokens)))
            score = (2 * surname_match) + name_match + (1 if global_intersection >= 3 else 0)

            passes = (surname_match >= 2) or (surname_match >= 1 and name_match >= 1) or (global_intersection >= 3)
            if passes:
                if best_nomina is None or score > best_nomina[0]:
                    best_nomina = (score, departamento, cargo)

        if best_nomina is not None:
            departamento, cargo = best_nomina[1], best_nomina[2]
            if departamento and departamento.strip() and departamento.lower() != "falta dato":
                c.execute("SELECT id_rol FROM roles WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(%s))", (departamento,))
                r = c.fetchone()
                if r:
                    if close_conn:
                        conn.close()
                    return r[0]
            if cargo and cargo.strip() and cargo.lower() != "falta dato":
                c.execute("SELECT id_rol FROM roles WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(%s))", (cargo,))
                r = c.fetchone()
                if r:
                    if close_conn:
                        conn.close()
                    return r[0]

        if close_conn:
            conn.close()
        return None
    except Exception:
        if close_conn:
            conn.close()
        return None

def get_tecnico_rol_id(tecnico_nombre, conn=None):
    """Obtiene el rol_id de un técnico basándose en su nombre y la coincidencia con usuarios"""
    # Mantener compatibilidad hacia atrás llamando a la nueva función
    return get_empleado_rol_id(tecnico_nombre, conn)

def get_or_create_tipo_tarea(descripcion, conn=None, empleado_nombre=None, tecnico_nombre=None):
    """Obtiene el ID de un tipo de tarea o lo crea si no existe (con validación de duplicados)
    Si se crea un nuevo tipo de tarea y se proporciona empleado_nombre o tecnico_nombre, lo asocia automáticamente al rol del empleado"""
    # Normalizar la descripción
    descripcion_normalizada = ' '.join(descripcion.strip().split()).title()
    
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    
    # Buscar tipo de tarea existente (insensible a mayúsculas/minúsculas)
    c.execute("SELECT id_tipo FROM tipos_tarea WHERE LOWER(TRIM(descripcion)) = LOWER(TRIM(%s))", 
             (descripcion_normalizada,))
    result = c.fetchone()
    
    if result:
        if close_conn:
            conn.close()
        return result[0]
    else:
        # Crear nuevo tipo de tarea
        try:
            c.execute("INSERT INTO tipos_tarea (descripcion) VALUES (%s) RETURNING id_tipo", (descripcion_normalizada,))
            tipo_id = c.fetchone()[0]
            
            # Determinar qué nombre usar (priorizar empleado_nombre sobre tecnico_nombre)
            nombre_a_usar = empleado_nombre or tecnico_nombre
            
            # Si se proporciona el nombre del empleado/técnico, asociar automáticamente al rol
            if nombre_a_usar:
                rol_id = get_empleado_rol_id(nombre_a_usar, conn)
                if rol_id:
                    # Verificar si ya existe la asociación
                    c.execute("SELECT COUNT(*) FROM tipos_tarea_roles WHERE id_tipo = %s AND id_rol = %s", 
                             (tipo_id, rol_id))
                    if c.fetchone()[0] == 0:
                        # Crear la asociación tipo_tarea -> rol
                        c.execute("INSERT INTO tipos_tarea_roles (id_tipo, id_rol) VALUES (%s, %s)", 
                                 (tipo_id, rol_id))
            
            conn.commit()
            if close_conn:
                conn.close()
            return tipo_id
        except Exception as e:
            if close_conn:
                conn.close()
            raise e

def get_or_create_modalidad(modalidad, conn=None):
    """Obtiene el ID de una modalidad o la crea si no existe"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    
    # Buscar modalidad existente
    c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE descripcion = %s", (modalidad,))
    result = c.fetchone()
    
    if result:
        if close_conn:
            conn.close()
        return result[0]
    else:
        # Crear nueva modalidad
        try:
            c.execute("INSERT INTO modalidades_tarea (descripcion) VALUES (%s) RETURNING id_modalidad", (modalidad,))
            modalidad_id = c.fetchone()[0]
            conn.commit()
            if close_conn:
                conn.close()
            return modalidad_id
        except Exception as e:
            if close_conn:
                conn.close()
            raise e

def get_unassigned_records_for_user(user_id):
    """Obtiene registros sin asignar que podrían pertenecer a un usuario basándose en el nombre del técnico"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT nombre, apellido FROM usuarios WHERE id = %s", (user_id,))
        user_data = c.fetchone()
        
        if not user_data or not user_data[0] or not user_data[1]:
            conn.close()
            return pd.DataFrame()  # Usuario sin nombre completo
        
        nombre_completo = f"{user_data[0]} {user_data[1]}"
        conn.close()
        
        query = '''
            SELECT r.id, r.fecha, t.nombre as tecnico, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.descripcion as modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.es_hora_extra, r.descripcion, r.mes
            FROM registros r
            JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            JOIN clientes c ON r.id_cliente = c.id_cliente
            JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
            WHERE r.usuario_id IS NULL AND t.nombre = :nombre
            ORDER BY r.id DESC
        '''
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine, params={"nombre": nombre_completo})
        
        # Procesar fechas y meses
        df = process_registros_df(df)
        
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo registros sin asignar para usuario: {e}")
        return pd.DataFrame()

def get_user_rol_id(user_id):
    """Obtiene el rol_id del usuario"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT rol_id FROM usuarios WHERE id = %s", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def check_record_duplicate(fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, tiempo, exclude_id=None, es_hora_extra=False):
    """
    Verifica si existe un registro duplicado
    
    Args:
        fecha: Fecha del registro
        id_tecnico: ID del técnico
        id_cliente: ID del cliente
        id_tipo: ID del tipo de tarea
        id_modalidad: ID de la modalidad
        tarea_realizada: Descripción de la tarea
        tiempo: Tiempo empleado
        exclude_id: ID del registro a excluir (para ediciones)
        es_hora_extra: Si es hora extra o no
    
    Returns:
        bool: True si existe duplicado, False si no
    """
    with db_connection() as conn:
        c = conn.cursor()
        
        # Asegurar que es_hora_extra sea booleano
        es_hora_extra = bool(es_hora_extra)
        fecha_iso = format_registro_date_iso(fecha)
        if not fecha_iso:
            return False
        
        if exclude_id:
            # Para ediciones - excluir el registro actual
            c.execute('''
                SELECT COUNT(*) FROM registros 
                WHERE (
                    CASE
                        WHEN fecha ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN to_date(fecha, 'YYYY-MM-DD')
                        WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{2}$' THEN to_date(fecha, 'DD/MM/YY')
                        WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{4}$' THEN to_date(fecha, 'DD/MM/YYYY')
                        ELSE NULL
                    END
                ) = %s::date
                AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s 
                AND id_modalidad = %s AND tarea_realizada = %s AND tiempo = %s AND es_hora_extra = %s AND id != %s
            ''', (fecha_iso, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, tiempo, es_hora_extra, exclude_id))
        else:
            # Para nuevos registros
            c.execute('''
                SELECT COUNT(*) FROM registros 
                WHERE (
                    CASE
                        WHEN fecha ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN to_date(fecha, 'YYYY-MM-DD')
                        WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{2}$' THEN to_date(fecha, 'DD/MM/YY')
                        WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{4}$' THEN to_date(fecha, 'DD/MM/YYYY')
                        ELSE NULL
                    END
                ) = %s::date
                AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s 
                AND id_modalidad = %s AND tarea_realizada = %s AND tiempo = %s AND es_hora_extra = %s
            ''', (fecha_iso, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, tiempo, es_hora_extra))
        
        return c.fetchone()[0] > 0

def check_registro_duplicate(fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, tiempo, registro_id=None, es_hora_extra=False):
    """Verifica si existe un registro duplicado
    
    Args:
        registro_id: Si se proporciona, excluye este registro de la verificación (útil para actualizaciones)
    
    Returns:
        bool: True si existe un duplicado, False en caso contrario
    """
    # Llamar a la nueva función con los parámetros correctos
    return check_record_duplicate(fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea, tiempo, registro_id, es_hora_extra)

def get_registros_by_rol_with_date_filter(rol_id, filter_type='all_time', custom_month=None, custom_year=None, start_date=None, end_date=None, use_created_at=False):
    """
    Obtiene registros filtrados por rol y fecha
    
    Args:
        rol_id: ID del rol
        filter_type: 'current_month', 'custom_month', 'custom_range', 'all_time'
        custom_month: Mes personalizado (1-12)
        custom_year: Año personalizado
        start_date: fecha inicio (date) para período de tiempo
        end_date: fecha fin (date) para período de tiempo
        use_created_at: Si es True, usa created_at para filtrar. Si es False, usa fecha (con fallback a created_at)
    
    Returns:
        DataFrame con los registros filtrados
    """
    # DEBUG LOGGING
    try:
        if False: # with open("debug_db_log_v2.txt", "a") as f:
            f.write(f"\\n--- Call at {datetime.now()} ---\\n")
            f.write(f"rol_id: {rol_id} (type: {type(rol_id)})\\n")
            f.write(f"filter_type: {filter_type}\\n")
            f.write(f"use_created_at: {use_created_at}\\n")
    except:
        pass

    try:
        if rol_id is not None:
            rol_id = int(rol_id)

        conn = get_connection()
        
        # Obtener el nombre del rol actual
        c = conn.cursor()
        c.execute("SELECT nombre FROM roles WHERE id_rol = %s", (rol_id,))
        rol_result = c.fetchone()
        if not rol_result:
            conn.close()
            return pd.DataFrame()  # Retornar DataFrame vacío si el rol no existe
        
        rol_nombre = rol_result[0]
        conn.close()
        
        # Preparar parámetros y filtro de fecha (usando binds de SQLAlchemy)
        params = {}
        date_filter = ""
        
        if filter_type == 'current_month':
            # Filtro para el mes actual
            from datetime import datetime
            current_month = datetime.now().month
            current_year = datetime.now().year
            
            if use_created_at:
                # Filtrar puramente por created_at (timestamp) - SQL es eficiente y seguro aquí
                date_filter = """
                    AND (EXTRACT(MONTH FROM r.created_at) = :month_int AND EXTRACT(YEAR FROM r.created_at) = :year_int)
                """
                params.update({
                    "month_int": current_month,
                    "year_int": current_year
                })
            else:
                # Filtro por fecha string: Hacemos el filtrado en Python para mayor robustez
                # Evitamos lógica SQL frágil con SUBSTRING para formatos de fecha variables
                pass
            
        elif filter_type == 'custom_month' and custom_month and custom_year:
            if use_created_at:
                date_filter = """
                    AND (EXTRACT(MONTH FROM r.created_at) = :month_int AND EXTRACT(YEAR FROM r.created_at) = :year_int)
                """
                params.update({
                    "month_int": int(custom_month),
                    "year_int": int(custom_year)
                })
            else:
                # Filtro por fecha string: Hacemos el filtrado en Python
                pass
                
        elif filter_type == 'custom_range' and start_date and end_date:
            if use_created_at:
                date_filter = "AND r.created_at::date BETWEEN :start_date AND :end_date"
            else:
                date_filter = """
                    AND (
                        COALESCE(
                            CASE
                                WHEN r.fecha IS NULL THEN NULL
                                WHEN r.fecha ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN to_date(substring(r.fecha from 1 for 10), 'YYYY-MM-DD')
                                WHEN r.fecha ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$' THEN to_date(r.fecha, 'DD/MM/YYYY')
                                WHEN r.fecha ~ '^[0-9]{2}/[0-9]{2}/[0-9]{2}$' THEN to_date(r.fecha, 'DD/MM/YY')
                                ELSE NULL
                            END,
                            r.created_at::date
                        ) BETWEEN :start_date AND :end_date
                    )
                """
            params.update({"start_date": start_date, "end_date": end_date})
        
        # Para 'all_time' no agregamos filtro de fecha
        
        # Lógica de consulta según el rol
        engine = get_engine()
        
        # Query base común
        select_clause = '''
            SELECT r.fecha, t.nombre as tecnico, r.grupo, c.nombre as cliente, 
                   tt.descripcion as tipo_tarea, mt.descripcion as modalidad, r.tarea_realizada, 
                   r.numero_ticket, r.tiempo, r.es_hora_extra, r.descripcion, r.mes, r.id,
                   r.created_at as "Fecha Creación"
        '''
        
        from_clause = '''
            FROM registros r
            LEFT JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
            LEFT JOIN clientes c ON r.id_cliente = c.id_cliente
            LEFT JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
            LEFT JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
        '''
        
        if rol_nombre == SYSTEM_ROLES['ADMIN']:
            # Para admin, mostrar TODOS los registros
            query = f'''
                {select_clause}
                {from_clause}
                WHERE 1=1
                {date_filter}
                ORDER BY r.id DESC
            '''
            # Note: Removed .replace("AND", "", 1) logic because we use WHERE 1=1
            
            df = pd.read_sql_query(text(query), con=engine, params=params if params else None)
        else:
            # Para cualquier otro rol, mostrar SOLO registros asignados
            query = f'''
                {select_clause}
                {from_clause}
                WHERE r.usuario_id IN (
                    SELECT id FROM usuarios 
                    WHERE rol_id = :rol_id
                )
                {date_filter}
                ORDER BY r.id DESC
            '''
            params_with_rol = {"rol_id": rol_id, **params}
            df = pd.read_sql_query(text(query), con=engine, params=params_with_rol if params_with_rol else None)
        
        # Procesar fechas y meses
        df = process_registros_df(df)
        
        # Aplicar filtrado por fecha en Python si se omitió en SQL (para mayor robustez con fechas string)
        if not use_created_at and not df.empty:
            if filter_type == 'current_month':
                # Filtramos por el mes y año actuales
                from datetime import datetime
                now = datetime.now()
                # Asegurar que la columna fecha es datetime (process_registros_df ya lo hace)
                if pd.api.types.is_datetime64_any_dtype(df['fecha']):
                    df = df[(df['fecha'].dt.month == now.month) & (df['fecha'].dt.year == now.year)]
            
            elif filter_type == 'custom_month' and custom_month and custom_year:
                # Filtramos por el mes y año personalizados
                if pd.api.types.is_datetime64_any_dtype(df['fecha']):
                    df = df[(df['fecha'].dt.month == int(custom_month)) & (df['fecha'].dt.year == int(custom_year))]
        
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo registros por rol con filtro de fecha: {e}")
        return pd.DataFrame()

def get_nomina_dataframe():
    """Obtiene un DataFrame con todos los registros de nómina"""
    query = """SELECT * FROM nomina ORDER BY nombre"""
    engine = get_engine()
    df = pd.read_sql_query(query, con=engine)
    return df

def get_nomina_dataframe_expanded():
    """Obtiene un DataFrame expandido con formato de vista completa para nómina"""
    query = """SELECT * FROM nomina"""
    engine = get_engine()
    df = pd.read_sql_query(query, con=engine)
    if df.empty:
        return df
    
    from datetime import datetime
    
    def calcular_edad(fecha_nacimiento):
        if not fecha_nacimiento or pd.isna(fecha_nacimiento):
            return ''
        try:
            fecha_nac = datetime.strptime(str(fecha_nacimiento), '%Y-%m-%d')
            hoy = datetime.now()
            edad = hoy.year - fecha_nac.year
            if hoy.month < fecha_nac.month or (hoy.month == fecha_nac.month and hoy.day < fecha_nac.day):
                edad -= 1
            return str(edad)
        except:
            return ''
    
    def calcular_antiguedad(fecha_ingreso):
        if not fecha_ingreso or pd.isna(fecha_ingreso):
            return ''
        try:
            fecha_ing = datetime.strptime(str(fecha_ingreso), '%Y-%m-%d')
            hoy = datetime.now()
            años = hoy.year - fecha_ing.year
            meses = hoy.month - fecha_ing.month
            
            if meses < 0:
                años -= 1
                meses += 12
            
            if años > 0:
                return f"{años} años, {meses} meses"
            else:
                return f"{meses} meses"
        except:
            return ''
    
    # Función para separar categoria y funcion del campo cargo
    def separar_cargo(cargo_str):
        if not cargo_str or pd.isna(cargo_str) or cargo_str == '':
            return 'falta dato', 'falta dato'
        
        cargo_str = str(cargo_str).strip()
        
        # Si contiene " - ", separar
        if ' - ' in cargo_str:
            partes = cargo_str.split(' - ', 1)
            categoria = partes[0].strip()
            funcion = partes[1].strip()
            
            # Si alguna parte es 'falta dato' o está vacía, mostrar 'falta dato'
            if categoria.lower() == 'falta dato' or categoria == '':
                categoria = 'falta dato'
            if funcion.lower() == 'falta dato' or funcion == '':
                funcion = 'falta dato'
                
            return categoria, funcion
        else:
            # Si no contiene " - ", es solo una categoría
            if cargo_str.lower() == 'falta dato':
                return 'falta dato', 'falta dato'
            return cargo_str, 'falta dato'
    
    # Aplicar la separación
    categorias_funciones = df['cargo'].apply(separar_cargo)
    
    # CORREGIDO: Crear DataFrame expandido con campos intercambiados para mostrar correctamente
    # Campo 'nombre' de BD = apellido real → columna "APELLIDO"
    # Campo 'apellido' de BD = nombre real → columna "NOMBRE"
    expanded_df = pd.DataFrame({
        'APELLIDO': df['nombre'].apply(lambda x: str(x).title() if pd.notna(x) and str(x).strip() != '' else 'falta dato'),
        'NOMBRE': df['apellido'].apply(lambda x: str(x).title() if pd.notna(x) and str(x).strip() != '' else 'falta dato'),
        'MAIL': df['email'].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() != '' and str(x).strip().lower() != 'nan' else 'falta dato'),
        'Celular': df['documento'].apply(lambda x: str(x) if pd.notna(x) and str(x).strip() != '' and not str(x).startswith('AUTO_') else 'falta dato'),
        'Categoria': [cat for cat, func in categorias_funciones],
        'Funcion': [func for cat, func in categorias_funciones],
        'Sector': df['departamento'].apply(lambda x: 'falta dato' if pd.isna(x) or str(x).strip() == '' or str(x).lower() == 'falta dato' else str(x)),
        'Fecha ingreso': df['fecha_ingreso'].apply(lambda x: str(x) if pd.notna(x) and str(x).strip() != '' else 'falta dato'),
        'Fecha Nacimiento': df['fecha_nacimiento'].apply(lambda x: str(x) if pd.notna(x) and str(x).strip() != '' else 'falta dato') if 'fecha_nacimiento' in df.columns else 'falta dato',
        'Edad': df['fecha_nacimiento'].apply(calcular_edad) if 'fecha_nacimiento' in df.columns else 'falta dato',
        'Antigüedad': df['fecha_ingreso'].apply(calcular_antiguedad)
        # Removido 'ACTIVO' para que no se muestre en la vista
    })
    
    return expanded_df

def empleado_existe(nombre, apellido):
    """Verifica si un empleado ya existe en la nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        query = "SELECT COUNT(*) FROM nomina WHERE LOWER(nombre) = LOWER(%s) AND LOWER(apellido) = LOWER(%s)"
        c.execute(query, (nombre.strip(), apellido.strip()))
        count = c.fetchone()[0]
        return count > 0
    except Exception as e:
        log_sql_error(e, "empleado_existe")
        return False
    finally:
        conn.close()

def add_empleado_nomina(nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento=''):
    """Añade un nuevo empleado a la nómina solo si no existe"""
    
    # Verificar si el empleado ya existe
    if empleado_existe(nombre, apellido):
        print(f"⚠️  Empleado ya existe: {apellido}, {nombre} - Saltando inserción")
        return True, "Empleado ya existe"  # Retornamos True porque no es un error, solo ya existe
    
    conn = get_connection()
    c = conn.cursor()
    try:
        # Manejar fechas vacías para evitar errores de tipo DATE con strings vacíos o valores inválidos
        def clean_date(date_val):
            if not date_val:
                return None
            s = str(date_val).strip().lower()
            if s == '' or s == 'nan' or s == 'nat' or s == 'none':
                return None
            return date_val

        fecha_ingreso = clean_date(fecha_ingreso)
        fecha_nacimiento = clean_date(fecha_nacimiento)

        # Crear rol basado en el departamento si es válido
        if departamento and departamento.strip() != '' and departamento.lower() != 'falta dato':
            get_or_create_role_from_sector(departamento)
        
        # Crear rol basado en el cargo si es válido
        # COMENTADO: El usuario reportó que esto genera pestañas indeseadas en el dashboard
        # if cargo and cargo.strip() != '' and cargo.lower() != 'falta dato':
        #     # Truncar cargo para rol (max 100 caracteres)
        #     cargo_role_name = cargo[:100]
        #     
        #     # Verificar si ya existe un rol con este cargo
        #     c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (cargo_role_name,))
        #     if not c.fetchone():
        #         c.execute("""
        #             INSERT INTO roles (nombre, descripcion, is_hidden) 
        #             VALUES (%s, %s, %s)
        #         """, (cargo_role_name, f'Rol generado automáticamente para el cargo: {cargo_role_name}', False))
        
        # Insertar el empleado
        # Truncar campos de texto para evitar errores de longitud
        nombre_db = nombre[:100] if nombre else nombre
        apellido_db = apellido[:100] if apellido else apellido
        email_db = email[:100] if email else email
        documento_db = documento[:50] if documento else documento
        cargo_db = cargo[:150] if cargo else cargo
        departamento_db = departamento[:100] if departamento else departamento

        query = """INSERT INTO nomina (nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento, activo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)"""
        params = (nombre_db, apellido_db, email_db, documento_db, cargo_db, departamento_db, fecha_ingreso, fecha_nacimiento)
        c.execute(query, params)
        conn.commit()
        
        return True, "Guardado exitosamente"
    except Exception as e:
        print(f"Error de integridad al insertar {apellido}, {nombre}: {str(e)}")
        log_sql_error(e, query="INSERT INTO nomina", params=(nombre, apellido, email, documento))
        return False, str(e)
    except Exception as e:
        print(f"Error general al insertar {apellido}, {nombre}: {str(e)}")
        log_sql_error(e, query="INSERT INTO nomina", params=(nombre, apellido, email, documento))
        return False, str(e)
    finally:
        conn.close()

def update_empleado_nomina(id_empleado, nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento='', activo=True):
    """Actualiza un empleado existente en la nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Convertir activo a booleano si es necesario
        if isinstance(activo, int):
            activo = bool(activo)
        
        # Manejar fechas vacías
        def clean_date(date_val):
            if not date_val:
                return None
            s = str(date_val).strip().lower()
            if s == '' or s == 'nan' or s == 'nat' or s == 'none':
                return None
            return date_val

        fecha_ingreso = clean_date(fecha_ingreso)
        fecha_nacimiento = clean_date(fecha_nacimiento)
        
        # Truncar campos de texto para evitar errores de longitud
        nombre_db = nombre[:100] if nombre else nombre
        apellido_db = apellido[:100] if apellido else apellido
        email_db = email[:100] if email else email
        documento_db = documento[:50] if documento else documento
        cargo_db = cargo[:150] if cargo else cargo
        departamento_db = departamento[:100] if departamento else departamento

        c.execute("""
            UPDATE nomina 
            SET nombre = %s, apellido = %s, email = %s, documento = %s, cargo = %s, 
                departamento = %s, fecha_ingreso = %s, fecha_nacimiento = %s, activo = %s
            WHERE id = %s
        """, (nombre_db, apellido_db, email_db, documento_db, cargo_db, departamento_db, fecha_ingreso, fecha_nacimiento, activo, id_empleado))
        conn.commit()
        return True
    except Exception as e:
        # Error de integridad u otro error
        log_sql_error(e, "update_empleado_nomina")
        return False
    except Exception as e:
        log_sql_error(e, "update_empleado_nomina")
        raise e
    finally:
        conn.close()

def delete_empleado_nomina(id_empleado):
    """Elimina un empleado de la nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM nomina WHERE id = %s", (id_empleado,))
        conn.commit()
        return True
    except Exception as e:
        log_sql_error(e, "delete_empleado_nomina")
        raise e
    finally:
        conn.close()

def process_nomina_excel(excel_df):
    """Procesa un DataFrame de Excel y guarda los empleados en la nómina"""
    success_count = 0
    error_count = 0
    duplicate_count = 0
    error_details = []
    duplicate_details = []  # Lista de empleados duplicados
    success_details = []    # Lista de empleados creados exitosamente
    filtered_inactive_count = 0  # Contador para empleados inactivos filtrados
    
    # Hacer una copia del DataFrame para no modificar el original
    df = excel_df.copy()
    
    # Eliminar filas donde todas las columnas son NaN (por si no se hizo antes)
    df = df.dropna(how='all')
    
    # Eliminar columnas donde todas las filas son NaN (por si no se hizo antes)
    df = df.dropna(axis=1, how='all')
    
    # DETECCIÓN INTELIGENTE DE COLUMNAS
    def detect_column_mapping(df_columns):
        """Detecta automáticamente qué columnas corresponden a nombres y apellidos"""
        column_mapping = {}
        
        # Patrones para detectar columnas de nombres
        nombre_patterns = ['NOMBRE', 'NAME', 'FIRST_NAME', 'FIRSTNAME', 'NOMBRES']
        apellido_patterns = ['APELLIDO', 'APELLIDOS', 'LASTNAME', 'LAST_NAME', 'SURNAME']
        
        # Buscar columnas que contengan nombres
        for col in df_columns:
            col_upper = col.upper().strip()
            
            # Detectar columna de nombres
            for pattern in nombre_patterns:
                if pattern in col_upper:
                    column_mapping['NOMBRE'] = col
                    break
            
            # Detectar columna de apellidos
            for pattern in apellido_patterns:
                if pattern in col_upper:
                    column_mapping['APELLIDO'] = col
                    break
        
        return column_mapping
    
    # Detectar mapeo de columnas automáticamente
    auto_column_mapping = detect_column_mapping(df.columns)
    
    # Crear un diccionario para mapear columnas insensibles a mayúsculas
    column_map = {}
    for col in df.columns:
        col_upper = col.upper()
        column_map[col_upper] = col
    
    # Agregar mapeo automático detectado
    for key, value in auto_column_mapping.items():
        column_map[key] = value
    
    # Función auxiliar para obtener valor de columna insensible a mayúsculas
    def get_column_value(row, column_name):
        actual_column = column_map.get(column_name.upper())
        if actual_column and actual_column in df.columns:
            return row[actual_column]
        return None
    
    # Mostrar información de detección de columnas
    print("🔍 Detección automática de columnas:")
    for key, value in auto_column_mapping.items():
        print(f"   {key} → {value}")
    
    # VALIDACIÓN INTELIGENTE DE CONTENIDO
    def validate_name_content(df, nombre_col, apellido_col):
        """Valida si las columnas detectadas realmente contienen nombres/apellidos"""
        if not nombre_col or not apellido_col:
            return True  # Si no hay ambas columnas, usar lógica existente
        
        # 1. Confiar en los encabezados explícitos si están claros (Prioridad Alta)
        nombre_header = str(nombre_col).upper()
        apellido_header = str(apellido_col).upper()
        
        # Si los encabezados contienen explícitamente NOMBRE y APELLIDO, confiar en ellos
        # Esto evita que la heurística de contenido anule una detección clara por encabezado
        is_explicit_nombre = 'NOMBRE' in nombre_header or 'NAME' in nombre_header
        is_explicit_apellido = 'APELLIDO' in apellido_header or 'LAST' in apellido_header or 'SURNAME' in apellido_header
        
        if is_explicit_nombre and is_explicit_apellido:
            print(f"✅ Confiando en encabezados explícitos: {nombre_col} y {apellido_col}")
            return True

        # Tomar una muestra de 5 filas para validar
        sample_size = min(5, len(df))
        sample_rows = df.head(sample_size)
        
        nombre_seems_correct = 0
        apellido_seems_correct = 0
        
        for _, row in sample_rows.iterrows():
            nombre_val = str(row[nombre_col]).strip() if pd.notna(row[nombre_col]) else ""
            apellido_val = str(row[apellido_col]).strip() if pd.notna(row[apellido_col]) else ""
            
            # Heurística relajada: permitir hasta 4 palabras (antes era 2) para cubrir nombres compuestos
            if nombre_val and not ',' in nombre_val and len(nombre_val.split()) <= 4:
                nombre_seems_correct += 1
            
            if apellido_val and not ',' in apellido_val and len(apellido_val.split()) <= 4:
                apellido_seems_correct += 1
        
        # Si más del 60% de la muestra parece correcta, mantener el mapeo
        confidence_threshold = 0.6
        nombre_confidence = nombre_seems_correct / sample_size
        apellido_confidence = apellido_seems_correct / sample_size
        
        print(f"📊 Confianza en detección: NOMBRE={nombre_confidence:.1%}, APELLIDO={apellido_confidence:.1%}")
        
        # Si la confianza es baja, NO invertir automáticamente a menos que estemos seguros
        # Es preferible mantener el mapeo detectado por nombre de columna que adivinar y equivocarse
        if nombre_confidence < confidence_threshold and apellido_confidence < confidence_threshold:
            print("⚠️  Baja confianza en heurística de contenido. Manteniendo mapeo original por seguridad.")
            return True
        
        return True
    
    # Validar contenido si se detectaron ambas columnas
    nombre_col = auto_column_mapping.get('NOMBRE')
    apellido_col = auto_column_mapping.get('APELLIDO')
    
    if nombre_col and apellido_col:
        content_valid = validate_name_content(df, nombre_col, apellido_col)
        if not content_valid:
            print("🔄 Intercambiando columnas detectadas debido a baja confianza...")
            # Intercambiar en el mapeo
            column_map['NOMBRE'] = apellido_col
            column_map['APELLIDO'] = nombre_col
            auto_column_mapping['NOMBRE'] = apellido_col
            auto_column_mapping['APELLIDO'] = nombre_col
    
    
    # CREAR ROLES Y GRUPOS BÁSICOS AL INICIO DEL PROCESAMIENTO
    with db_connection() as conn:
        c = conn.cursor()
        

        has_view_type = True
        try:
            c.execute("SELECT view_type FROM roles LIMIT 1")
        except Exception:
            has_view_type = False
            try:
                conn.rollback()
            except Exception:
                pass
        
        
        # 2. Crear grupo "General" si no existe
        c.execute("SELECT id_grupo FROM grupos WHERE nombre = %s", ('General',))
        if not c.fetchone():
            c.execute("""
                INSERT INTO grupos (nombre, descripcion) 
                VALUES (%s, %s)
            """, ('General', 'Grupo por defecto para usuarios'))
            print("✅ Grupo 'General' creado automáticamente")
        
        # 3. Pre-crear roles basados en departamentos únicos del Excel
        # Obtener departamentos únicos del Excel
        departamentos_unicos = set()
        cargos_unicos = set()
        sector_label_by_core = {}
        from .utils import clean_role_name
        
        for index, row in df.iterrows():
            # Obtener departamento
            sector_val = get_column_value(row, 'SECTOR')
            if sector_val and not pd.isna(sector_val):
                departamento = str(sector_val).strip()
                if departamento and departamento.lower() != 'falta dato':
                    cleaned_dept = clean_role_name(departamento)
                    if cleaned_dept:
                        if cleaned_dept.startswith('dpto_'):
                            core = cleaned_dept[5:]
                        elif cleaned_dept.startswith('adm_'):
                            core = cleaned_dept[4:]
                        else:
                            core = cleaned_dept
                        if core:
                            departamentos_unicos.add(core)
                            if core not in sector_label_by_core:
                                sector_label_by_core[core] = departamento
            
            # Obtener cargo (combinación de categoría y función)
            categoria_val = get_column_value(row, 'CATEGORIA')
            funcion_val = get_column_value(row, 'FUNCION')
            
            categoria = str(categoria_val).strip() if categoria_val and not pd.isna(categoria_val) else ''
            funcion = str(funcion_val).strip() if funcion_val and not pd.isna(funcion_val) else ''
            
            if categoria and funcion:
                cargo = f"{categoria} - {funcion}"
            elif categoria:
                cargo = categoria
            elif funcion:
                cargo = funcion
            else:
                cargo = ''
            
            if cargo and cargo.lower() != 'falta dato':
                cargos_unicos.add(cargo)
        
        # Crear roles para departamentos únicos (NORMALIZADOS)
        roles_departamentos_creados = 0
        
        c.execute("SELECT id_rol, nombre FROM roles")
        existing_roles = c.fetchall()
        existing_names_lower = set()
        existing_dept_cores = set()
        existing_admin_cores = set()
        for _, r_name in existing_roles:
            r_name_str = str(r_name or "")
            existing_names_lower.add(r_name_str.lower())
            cleaned = clean_role_name(r_name_str)
            if cleaned:
                cleaned = cleaned.lower()
                if cleaned.startswith('adm_'):
                    existing_admin_cores.add(cleaned[4:])
                elif cleaned.startswith('dpto_'):
                    existing_dept_cores.add(cleaned[5:])
                else:
                    existing_dept_cores.add(cleaned)

        def _derive_dept_and_admin(core_name):
            core_name = str(core_name or "").strip().lower()
            if not core_name:
                return None
            if core_name in ['admin', 'sin_rol', 'sin rol', 'hipervisor', 'general', 'visor']:
                return None
            if core_name == 'comercial':
                dept_role = 'dpto_comercial'
                admin_role = 'adm_comercial'
            elif core_name == 'tecnico':
                dept_role = 'dpto_tecnico'
                admin_role = 'adm_tecnico'
            elif core_name == 'administracion':
                dept_role = 'dpto_administracion'
                admin_role = 'adm_administracion'
            else:
                dept_role = f"dpto_{core_name}"
                admin_role = f"adm_{core_name}"

            if dept_role.startswith('dpto_'):
                dept_view_type = dept_role.replace('dpto_', '')
            elif dept_role.startswith('adm_'):
                dept_view_type = dept_role.replace('adm_', 'admin_')
            else:
                dept_view_type = dept_role

            admin_view_type = 'admin_comercial' if core_name == 'comercial' else f"admin_{core_name}"
            return dept_role, admin_role, dept_view_type, admin_view_type

        def _insert_role(nombre, descripcion, is_hidden, view_type):
            if has_view_type:
                c.execute(
                    "INSERT INTO roles (nombre, descripcion, is_hidden, view_type) VALUES (%s, %s, %s, %s)",
                    (nombre, descripcion, is_hidden, view_type),
                )
            else:
                c.execute(
                    "INSERT INTO roles (nombre, descripcion, is_hidden) VALUES (%s, %s, %s)",
                    (nombre, descripcion, is_hidden),
                )

        for core in sorted(departamentos_unicos):
            derived = _derive_dept_and_admin(core)
            if not derived:
                continue
            dept_role, admin_role, dept_view_type, admin_view_type = derived
            label = sector_label_by_core.get(core, core)

            if core not in existing_dept_cores and dept_role.lower() not in existing_names_lower:
                try:
                    _insert_role(dept_role, f'Rol generado automáticamente para el departamento: {label}', False, dept_view_type)
                    roles_departamentos_creados += 1
                    existing_names_lower.add(dept_role.lower())
                    if dept_role.startswith('dpto_'):
                        existing_dept_cores.add(dept_role[5:])
                    elif dept_role.startswith('adm_'):
                        existing_admin_cores.add(dept_role[4:])
                    else:
                        existing_dept_cores.add(dept_role)
                except Exception as e:
                    print(f"Error creando rol departamento {label}: {e}")

            if admin_role != dept_role and core not in existing_admin_cores and admin_role.lower() not in existing_names_lower:
                try:
                    _insert_role(admin_role, f'Departamento administrador para: {label}', False, admin_view_type)
                    roles_departamentos_creados += 1
                    existing_names_lower.add(admin_role.lower())
                    existing_admin_cores.add(core)
                except Exception as e:
                    print(f"Error creando rol admin para {label}: {e}")
        
        # Crear roles para cargos únicos
        roles_cargos_creados = 0
        # COMENTADO: El usuario reportó que esto genera pestañas indeseadas en el dashboard
        # for cargo in cargos_unicos:
        #     c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (cargo,))
        #     if not c.fetchone():
        #         c.execute("""
        #             INSERT INTO roles (nombre, descripcion, is_hidden) 
        #             VALUES (%s, %s, %s)
        #         """, (cargo, f'Rol generado automáticamente para el cargo: {cargo}', False))
        #         roles_cargos_creados += 1
        
        conn.commit()
        
        if roles_departamentos_creados > 0:
            print(f"✅ {roles_departamentos_creados} roles de departamentos creados automáticamente")
        if roles_cargos_creados > 0:
            print(f"✅ {roles_cargos_creados} roles de cargos creados automáticamente")
    
    # Función para formatear nombres y apellidos
    def format_name(name):
        if not name or pd.isna(name):
            return ''
        name_str = str(name).strip()
        if not name_str:
            return ''
        # Primera letra de cada palabra en mayúscula
        return name_str.title()
    
    # Crear lista para almacenar filas de vista previa
    preview_rows = []
    
    # Verificar columnas requeridas
    required_columns = ['NOMBRE']  # Solo NOMBRE es obligatorio
    for col in required_columns:
        if not any(c.upper() == col for c in df.columns):
            raise ValueError(f"Columna requerida '{col}' no encontrada en el archivo")
    
    # Obtener conexión a la base de datos
    with db_connection() as conn:
        
        # Procesar cada fila del DataFrame
        for index, row in df.iterrows():
            try:
                # Verificar si el empleado está activo
                activo_val = get_column_value(row, 'ACTIVO')
                
                # Si ACTIVO es 0 o FALSE, ignorar este empleado
                if activo_val is not None and not pd.isna(activo_val):
                    activo_str = str(activo_val).strip().upper()
                    if activo_str == 'FALSE' or activo_str == 'NO' or activo_str == '0' or activo_str == 'F':
                        filtered_inactive_count += 1
                        continue
                
                # Obtener valores básicos
                nombre_val = get_column_value(row, 'NOMBRE')
                apellido_val = get_column_value(row, 'APELLIDO')
                celular_val = get_column_value(row, 'CELULAR')
                
                # Asegurarse de que al menos hay un nombre
                if pd.isna(nombre_val) or not nombre_val:
                    continue
                    
                # Rellenar valores faltantes
                nombre_str = str(nombre_val).strip() if not pd.isna(nombre_val) else "falta dato"
                apellido_str = str(apellido_val).strip() if not pd.isna(apellido_val) else "falta dato"
                celular_str = str(celular_val).strip() if not pd.isna(celular_val) else "falta dato"
                
        
                # Procesar celular - si no hay valor válido, usar "falta dato"
                if celular_str != "falta dato":
                    documento = celular_str  # Usar celular directamente
                else:
                    documento = "falta dato"  # En lugar de generar AUTO_
                
                # Procesar el campo NOMBRE que puede venir en formato "APELLIDO, NOMBRE"
                nombre_completo = str(nombre_val).strip()
                apellido_from_col = get_column_value(row, 'APELLIDO')
                apellido_from_col = str(apellido_from_col).strip() if apellido_from_col and not pd.isna(apellido_from_col) else ''
                
                # Extraer apellido y nombre
                nombre = ''
                apellido = ''
                
                if apellido_from_col:
                    apellido = format_name(apellido_from_col)  # Columna APELLIDO = apellidos
                    nombre = format_name(nombre_completo)     # Columna NOMBRE = nombres
                elif ',' in nombre_completo:
                    # Formato "APELLIDO, NOMBRE"
                    partes = nombre_completo.split(',', 1)
                    apellido = format_name(partes[0].strip())
                    nombre = format_name(partes[1].strip())
                else:
                    # No tiene formato con coma, usar la última palabra como apellido
                    partes = nombre_completo.rsplit(' ', 1)
                    if len(partes) == 2:
                        nombre = format_name(partes[0].strip())
                        apellido = format_name(partes[1].strip())
                    else:
                        nombre = format_name(nombre_completo)
                
                # Guardar el email en una variable separada
                email_val = get_column_value(row, 'MAIL')
                email = str(email_val).strip() if email_val and not pd.isna(email_val) else ''
                
                # Si no se pudo extraer un apellido del nombre, usar parte del email como apellido
                if not apellido and email:
                    # Intentar extraer apellido del email (parte antes del @)
                    if '@' in email:
                        apellido = format_name(email.split('@')[0])
                    else:
                        apellido = format_name(email)
                
                # Determinar categoria y funcion por separado para la vista previa
                categoria_val = get_column_value(row, 'CATEGORIA')
                categoria = str(categoria_val).strip() if categoria_val and not pd.isna(categoria_val) else ''
                
                funcion_val = get_column_value(row, 'FUNCION')
                funcion = str(funcion_val).strip() if funcion_val and not pd.isna(funcion_val) else ''
                
                # Para la base de datos, combinar categoria y funcion en cargo
                if categoria and funcion:
                    cargo = f"{categoria} - {funcion}"
                elif categoria:
                    cargo = categoria
                elif funcion:
                    cargo = funcion
                else:
                    cargo = ''
                
                sector_val = get_column_value(row, 'SECTOR')
                departamento = str(sector_val).strip() if sector_val and not pd.isna(sector_val) else ''
                
                # Procesar fecha de ingreso con parseo robusto
                fecha_ingreso_val = get_column_value(row, 'FECHA INGRESO')
                if not fecha_ingreso_val or pd.isna(fecha_ingreso_val):
                    fecha_ingreso_val = get_column_value(row, 'FECHA_INGRESO')
                
                fecha_ingreso = None
                if fecha_ingreso_val and not pd.isna(fecha_ingreso_val):
                    try:
                        # Intentar convertir a datetime usando pandas (maneja múltiples formatos)
                        # dayfirst=True para priorizar formatos tipo DD/MM/YYYY comunes en Latam
                        dt_ingreso = pd.to_datetime(fecha_ingreso_val, dayfirst=True, errors='coerce')
                        if not pd.isna(dt_ingreso):
                            fecha_ingreso = dt_ingreso.strftime('%Y-%m-%d')
                    except:
                        pass # Si falla, se queda en None
                
                # Procesar fecha de nacimiento con parseo robusto
                fecha_nacimiento_val = get_column_value(row, 'FECHA NACIMIENTO')
                if not fecha_nacimiento_val or pd.isna(fecha_nacimiento_val):
                    fecha_nacimiento_val = get_column_value(row, 'FECHA_NACIMIENTO')
                
                fecha_nacimiento = None
                if fecha_nacimiento_val and not pd.isna(fecha_nacimiento_val):
                    try:
                        dt_nacimiento = pd.to_datetime(fecha_nacimiento_val, dayfirst=True, errors='coerce')
                        if not pd.isna(dt_nacimiento):
                            fecha_nacimiento = dt_nacimiento.strftime('%Y-%m-%d')
                    except:
                        pass # Si falla, se queda en None
                
                # CALCULAR EDAD DINÁMICAMENTE basándose en fecha_nacimiento
                def calcular_edad(fecha_nacimiento_str):
                    if not fecha_nacimiento_str or fecha_nacimiento_str == '':
                        return ''
                    try:
                        from datetime import datetime
                        fecha_nac = datetime.strptime(fecha_nacimiento_str, '%Y-%m-%d')
                        hoy = datetime.now()
                        edad = hoy.year - fecha_nac.year
                        if hoy.month < fecha_nac.month or (hoy.month == fecha_nac.month and hoy.day < fecha_nac.day):
                            edad -= 1
                        return str(edad)
                    except:
                        return ''
                
                # CALCULAR ANTIGÜEDAD DINÁMICAMENTE basándose en fecha_ingreso
                def calcular_antiguedad(fecha_ingreso_str):
                    if not fecha_ingreso_str or fecha_ingreso_str == '':
                        return ''
                    try:
                        from datetime import datetime
                        fecha_ing = datetime.strptime(fecha_ingreso_str, '%Y-%m-%d')
                        hoy = datetime.now()
                        años = hoy.year - fecha_ing.year
                        meses = hoy.month - fecha_ing.month
                        
                        if meses < 0:
                            años -= 1
                            meses += 12
                        
                        if años > 0:
                            return f"{años} años, {meses} meses"
                        else:
                            return f"{meses} meses"
                    except:
                        return ''
                
                edad = calcular_edad(fecha_nacimiento)
                antiguedad = calcular_antiguedad(fecha_ingreso)
                
                # Añadir fila al DataFrame de vista previa (SIN la columna ACTIVO)
                preview_row = {
                    'NOMBRE': nombre,
                    'Apellido': apellido,
                    'MAIL': email,
                    'Celular': celular_str,
                    'Categoria': categoria,
                    'Funcion': funcion,
                    'Sector': departamento,
                    'Fecha ingreso': fecha_ingreso,
                    'Fecha Nacimiento': fecha_nacimiento,
                    'Edad': edad,
                    'Antigüedad': antiguedad
                    # Removido 'ACTIVO': '1' para que no se muestre en la vista
                }
                # Asegurarse de que no haya valores None o NaN
                for key in preview_row:
                    if pd.isna(preview_row[key]) or preview_row[key] is None:
                        preview_row[key] = ''
                    elif not isinstance(preview_row[key], str):
                        preview_row[key] = str(preview_row[key])  # Convertir todos los valores a string
                        
                preview_rows.append(preview_row)
                
                # Verificar si el empleado ya existe (duplicado)
                if empleado_existe(nombre, apellido):
                    duplicate_count += 1
                    duplicate_details.append(f"{apellido}, {nombre}")
                    print(f"🔄 Empleado duplicado (no guardado): {apellido}, {nombre}")
                    continue
                
                # Añadir empleado a la base de datos
                print(f"Procesando empleado {index+1}: {apellido}, {nombre}")
                resultado, mensaje = add_empleado_nomina(nombre, apellido, email, documento, cargo, departamento, fecha_ingreso, fecha_nacimiento)
                if resultado:
                    success_count += 1
                    success_details.append(f"{apellido}, {nombre}")
                    print(f"✅ Guardado exitoso: {apellido}, {nombre}")
                else:
                    error_count += 1
                    error_details.append(f"{apellido}, {nombre}: {mensaje}")
                    print(f"❌ Error al guardar: {apellido}, {nombre} - {mensaje}")
            
            except Exception as e:
                error_count += 1
                error_details.append(f"Error SQL en fila {index+1}: {str(e)}")
                print(f"❌ Error SQL en fila {index+1}: {str(e)}")
                log_sql_error(e, query="process_nomina_excel", params=f"fila {index+1}")
            
            except Exception as e:
                error_count += 1
                error_details.append(f"Error general en fila {index+1}: {str(e)}")
                print(f"❌ Error general en fila {index+1}: {str(e)}")
    
    # Crear DataFrame de vista previa
    preview_df = pd.DataFrame(preview_rows) if preview_rows else pd.DataFrame()
    
    # Estadísticas de procesamiento
    stats = {
        'success_count': success_count,
        'error_count': error_count,
        'duplicate_count': duplicate_count,
        'filtered_inactive_count': filtered_inactive_count,
        'total_processed': success_count + error_count + duplicate_count + filtered_inactive_count,
        'error_details': error_details,
        'duplicate_details': duplicate_details,
        'success_details': success_details,
        'preview_df': preview_df
    }
    
    return stats

def get_user_info(user_id):
    """Obtiene información completa del usuario por ID"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT nombre, apellido, username, email FROM usuarios WHERE id = %s', (user_id,))
    user_info = c.fetchone()
    conn.close()
    
    if user_info:
        return {
            'nombre': user_info[0] if user_info[0] else '',
            'apellido': user_info[1] if user_info[1] else '',
            'username': user_info[2],
            'email': user_info[3] if user_info[3] else ''
        }
    return None


def get_or_create_role_from_sector(sector):
    """Obtiene o crea un rol basado en el sector de nómina
    
    Args:
        sector (str): Nombre del sector
        
    Returns:
        int: ID del rol creado o existente
        bool: True si el rol fue creado, False si ya existía
    """
    from .utils import clean_role_name

    if not sector or pd.isna(sector) or str(sector).strip() == '' or str(sector).strip().lower() == 'falta dato':
        return None, False

    sector_raw = str(sector).strip()
    sector_clean = clean_role_name(sector_raw)
    if not sector_clean:
        return None, False

    if sector_clean in ['admin', 'sin_rol', 'sin rol', 'hipervisor', 'general', 'visor']:
        return None, False

    if sector_clean.startswith('dpto_'):
        core_name = sector_clean[5:]
    elif sector_clean.startswith('adm_'):
        core_name = sector_clean[4:]
    else:
        core_name = sector_clean

    if not core_name:
        return None, False

    if core_name == 'comercial':
        dept_role = 'dpto_comercial'
        admin_role = 'adm_comercial'
    elif core_name == 'tecnico':
        dept_role = 'dpto_tecnico'
        admin_role = 'adm_tecnico'
    elif core_name == 'administracion':
        dept_role = 'dpto_administracion'
        admin_role = 'adm_administracion'
    else:
        dept_role = f"dpto_{core_name}"
        admin_role = f"adm_{core_name}"

    if dept_role.startswith('dpto_'):
        dept_view_type = dept_role.replace('dpto_', '')
    elif dept_role.startswith('adm_'):
        dept_view_type = dept_role.replace('adm_', 'admin_')
    else:
        dept_view_type = dept_role

    admin_view_type = 'admin_comercial' if core_name == 'comercial' else f"admin_{core_name}"

    conn = get_connection()
    c = conn.cursor()
    try:
        has_view_type = True
        try:
            c.execute("SELECT view_type FROM roles LIMIT 1")
        except Exception:
            has_view_type = False
            try:
                conn.rollback()
            except Exception:
                pass

        c.execute("SELECT id_rol, nombre FROM roles")
        rows = c.fetchall()
        by_lower_name = {str(n or '').lower(): int(rid) for rid, n in rows}

        created_any = False

        def ensure_role(nombre, descripcion, view_type):
            nonlocal created_any
            key = str(nombre).lower()
            if key in by_lower_name:
                return by_lower_name[key], False
            if has_view_type:
                c.execute(
                    "INSERT INTO roles (nombre, descripcion, is_hidden, view_type) VALUES (%s, %s, %s, %s) RETURNING id_rol",
                    (nombre, descripcion, False, view_type),
                )
            else:
                c.execute(
                    "INSERT INTO roles (nombre, descripcion, is_hidden) VALUES (%s, %s, %s) RETURNING id_rol",
                    (nombre, descripcion, False),
                )
            new_id = int(c.fetchone()[0])
            by_lower_name[key] = new_id
            created_any = True
            return new_id, True

        dept_id, _ = ensure_role(dept_role, f"Rol generado automáticamente desde el sector: {sector_raw}", dept_view_type)
        if admin_role != dept_role:
            ensure_role(admin_role, f"Departamento administrador para: {sector_raw}", admin_view_type)

        conn.commit()
        return dept_id, created_any
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_or_create_role_ids_from_sector(sector):
    from .utils import clean_role_name

    if not sector or pd.isna(sector) or str(sector).strip() == '' or str(sector).strip().lower() == 'falta dato':
        return None, None, False, False

    sector_raw = str(sector).strip()
    sector_clean = clean_role_name(sector_raw)
    if not sector_clean:
        return None, None, False, False

    if sector_clean in ['admin', 'sin_rol', 'sin rol', 'hipervisor', 'general', 'visor']:
        return None, None, False, False

    input_is_admin = sector_clean.startswith('adm_')

    if sector_clean.startswith('dpto_'):
        core_name = sector_clean[5:]
    elif sector_clean.startswith('adm_'):
        core_name = sector_clean[4:]
    else:
        core_name = sector_clean

    if not core_name:
        return None, None, False, input_is_admin

    if core_name == 'comercial':
        dept_role = 'dpto_comercial'
        admin_role = 'adm_comercial'
    elif core_name == 'tecnico':
        dept_role = 'dpto_tecnico'
        admin_role = 'adm_tecnico'
    elif core_name == 'administracion':
        dept_role = 'dpto_administracion'
        admin_role = 'adm_administracion'
    else:
        dept_role = f"dpto_{core_name}"
        admin_role = f"adm_{core_name}"

    dept_view_type = dept_role.replace('dpto_', '') if dept_role.startswith('dpto_') else (dept_role.replace('adm_', 'admin_') if dept_role.startswith('adm_') else dept_role)
    admin_view_type = 'admin_comercial' if core_name == 'comercial' else f"admin_{core_name}"

    conn = get_connection()
    c = conn.cursor()
    try:
        has_view_type = True
        try:
            c.execute("SELECT view_type FROM roles LIMIT 1")
        except Exception:
            has_view_type = False
            try:
                conn.rollback()
            except Exception:
                pass

        c.execute("SELECT id_rol, nombre FROM roles")
        rows = c.fetchall()
        by_lower_name = {str(n or '').lower(): int(rid) for rid, n in rows}

        created_any = False

        def ensure_role(nombre, descripcion, view_type):
            nonlocal created_any
            key = str(nombre).lower()
            if key in by_lower_name:
                return by_lower_name[key], False
            if has_view_type:
                c.execute(
                    "INSERT INTO roles (nombre, descripcion, is_hidden, view_type) VALUES (%s, %s, %s, %s) RETURNING id_rol",
                    (nombre, descripcion, False, view_type),
                )
            else:
                c.execute(
                    "INSERT INTO roles (nombre, descripcion, is_hidden) VALUES (%s, %s, %s) RETURNING id_rol",
                    (nombre, descripcion, False),
                )
            new_id = int(c.fetchone()[0])
            by_lower_name[key] = new_id
            created_any = True
            return new_id, True

        dept_id, _ = ensure_role(dept_role, f"Rol generado automáticamente desde el sector: {sector_raw}", dept_view_type)
        admin_id = None
        if admin_role == dept_role:
            admin_id = dept_id
        else:
            admin_id, _ = ensure_role(admin_role, f"Departamento administrador para: {sector_raw}", admin_view_type)

        conn.commit()
        return dept_id, admin_id, created_any, input_is_admin
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def ensure_system_roles():
    conn = get_connection()
    c = conn.cursor()
    try:
        from .utils import clean_role_name

        def merge_role_alias_inplace(source_id, target_id):
            if source_id == target_id:
                return
            try:
                c.execute("UPDATE usuarios SET rol_id = %s WHERE rol_id = %s", (target_id, source_id))
            except Exception:
                pass
            try:
                c.execute("UPDATE grupos_roles SET id_rol = %s WHERE id_rol = %s", (target_id, source_id))
            except Exception:
                pass
            try:
                c.execute("UPDATE tipos_tarea_roles SET id_rol = %s WHERE id_rol = %s", (target_id, source_id))
            except Exception:
                pass
            try:
                c.execute("UPDATE user_modalidad_schedule SET rol_id = %s WHERE rol_id = %s", (target_id, source_id))
            except Exception:
                pass
            c.execute("DELETE FROM roles WHERE id_rol = %s", (source_id,))

        c.execute("SELECT id_rol, nombre FROM roles")
        roles = [(int(rid), str(name or "")) for rid, name in c.fetchall()]

        norm_map = {}
        for rid, name in roles:
            norm = clean_role_name(name)
            if not norm:
                continue
            norm_map.setdefault(norm, []).append((rid, name))

        for role_key, role_desc in SYSTEM_ROLES.items():
            target_name = str(role_desc or "").strip()
            if not target_name:
                continue

            target_norm = clean_role_name(target_name)
            matches = norm_map.get(target_norm, [])

            is_hidden = True if role_key in ['SIN_ROL', 'VISOR', 'HIPERVISOR', 'ADM_COMERCIAL'] else False

            if not matches:
                c.execute(
                    "INSERT INTO roles (nombre, descripcion, is_hidden) VALUES (%s, %s, %s) RETURNING id_rol",
                    (target_name, f"Rol del sistema: {target_name}", is_hidden),
                )
                new_id = int(c.fetchone()[0])
                norm_map[target_norm] = [(new_id, target_name)]
                continue

            exact = next((rid for rid, name in matches if name == target_name), None)
            if exact is None:
                chosen_id, chosen_name = matches[0]
                c.execute("UPDATE roles SET nombre = %s WHERE id_rol = %s", (target_name, chosen_id))
                exact = chosen_id
                norm_map[target_norm] = [(exact, target_name)] + [(rid, name) for rid, name in matches if rid != exact]

            for rid, name in list(norm_map.get(target_norm, [])):
                if rid != exact:
                    merge_role_alias_inplace(rid, exact)
            norm_map[target_norm] = [(exact, target_name)]

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.rollback()
        conn.close()
        return False

def ensure_roles_view_type_column():
    conn = get_connection()
    c = conn.cursor()
    try:
        try:
            c.execute("ALTER TABLE roles ADD COLUMN IF NOT EXISTS view_type VARCHAR(64)")
        except Exception:
            pass
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.rollback()
        conn.close()
        return False

def fix_administracion_department_role():
    conn = get_connection()
    c = conn.cursor()
    try:
        from .utils import clean_role_name
        dept_id, _ = get_or_create_role_from_sector("Administracion")
        if not dept_id:
            conn.close()
            return False

        c.execute("SELECT id_rol, nombre FROM roles")
        rows = [(int(rid), str(name or "")) for rid, name in c.fetchall()]
        by_lower = {name.lower(): rid for rid, name in rows}

        adm_admin_id = by_lower.get("adm_administracion")
        dpto_admin_id = by_lower.get("dpto_administracion")

        if dpto_admin_id is None:
            conn.close()
            return False

        if adm_admin_id is not None:
            c.execute(
                "UPDATE usuarios SET rol_id = %s WHERE is_admin = false AND rol_id = %s",
                (dpto_admin_id, adm_admin_id),
            )

        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.rollback()
        conn.close()
        return False

def merge_role_alias(source_name, target_name):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (target_name,))
        target = c.fetchone()
        c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (source_name,))
        source = c.fetchone()
        if not source:
            conn.close()
            return False
        source_id = int(source[0])
        if not target:
            c.execute("UPDATE roles SET nombre = %s WHERE id_rol = %s", (target_name, source_id))
            conn.commit()
            conn.close()
            return True
        target_id = int(target[0])
        try:
            c.execute("UPDATE usuarios SET rol_id = %s WHERE rol_id = %s", (target_id, source_id))
        except Exception:
            pass
        try:
            c.execute("UPDATE grupos_roles SET id_rol = %s WHERE id_rol = %s", (target_id, source_id))
        except Exception:
            pass
        try:
            c.execute("UPDATE tipos_tarea_roles SET id_rol = %s WHERE id_rol = %s", (target_id, source_id))
        except Exception:
            pass
        try:
            c.execute("UPDATE user_modalidad_schedule SET rol_id = %s WHERE rol_id = %s", (target_id, source_id))
        except Exception:
            pass
        c.execute("DELETE FROM roles WHERE id_rol = %s", (source_id,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.rollback()
        conn.close()
        return False

def migrate_nomina_remove_unique_constraint():
    """Migra la tabla nomina para remover la restricción UNIQUE del campo documento"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # En PostgreSQL, simplemente eliminar la restricción si existe
        c.execute("""
            ALTER TABLE nomina 
            DROP CONSTRAINT IF EXISTS nomina_documento_key
        """)
        
        conn.commit()
        conn.close()
        print("✅ Migración completada: restricción UNIQUE removida del campo documento")
        return True
        
    except Exception as e:
        print(f"❌ Error en migración: {str(e)}")
        conn.rollback()
        conn.close()
        return False



def clean_duplicate_task_types():
    """Limpia tipos de tarea duplicados, manteniendo solo uno de cada tipo"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Obtener todos los tipos de tarea con duplicados
        c.execute("""
            SELECT descripcion, COUNT(*) as count, MIN(id_tipo) as keep_id
            FROM tipos_tarea 
            GROUP BY LOWER(TRIM(descripcion))
            HAVING COUNT(*) > 1
        """)
        
        duplicates = c.fetchall()
        deleted_count = 0
        
        for descripcion, count, keep_id in duplicates:
            # Obtener todos los IDs de este tipo duplicado
            c.execute("SELECT id_tipo FROM tipos_tarea WHERE LOWER(TRIM(descripcion)) = LOWER(TRIM(%s))", (descripcion,))
            all_ids = [row[0] for row in c.fetchall()]
            
            # IDs a eliminar (todos excepto el que vamos a mantener)
            ids_to_delete = [id_tipo for id_tipo in all_ids if id_tipo != keep_id]
            
            for id_to_delete in ids_to_delete:
                # Actualizar registros que usan este tipo
                c.execute("UPDATE registros SET id_tipo = %s WHERE id_tipo = %s", (keep_id, id_to_delete))
                
                # Eliminar relaciones con roles
                c.execute("DELETE FROM tipos_tarea_roles WHERE id_tipo = %s", (id_to_delete,))
                
                # Eliminar puntajes asociados
                c.execute("DELETE FROM tipos_tarea_puntajes WHERE id_tipo = %s", (id_to_delete,))
                
                # Eliminar el tipo duplicado
                c.execute("DELETE FROM tipos_tarea WHERE id_tipo = %s", (id_to_delete,))
                
                deleted_count += 1
        
        conn.commit()
        return deleted_count, len(duplicates)
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def update_tecnico_from_user(old_nombre_completo, nuevo_nombre_completo):
    """Actualiza o crea un técnico basado en el cambio de nombre de usuario"""
    if not nuevo_nombre_completo:
        return
        
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Si cambió el nombre, actualizar el técnico existente
        if old_nombre_completo and nuevo_nombre_completo != old_nombre_completo:
            c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = %s', (old_nombre_completo,))
            old_tecnico = c.fetchone()
            if old_tecnico:
                c.execute('UPDATE tecnicos SET nombre = %s WHERE nombre = %s', 
                            (nuevo_nombre_completo, old_nombre_completo))
        
        # Verificar si el técnico ya existe con el nuevo nombre
        c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = %s', (nuevo_nombre_completo,))
        tecnico = c.fetchone()
        if not tecnico:
            # Crear el técnico si no existe
            c.execute('INSERT INTO tecnicos (nombre) VALUES (%s)', (nuevo_nombre_completo,))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        log_sql_error(e, "update_tecnico_from_user")
        return False
    finally:
        conn.close()

def update_user_profile_complete(user_id, nombre=None, apellido=None, email=None):
    """Actualiza el perfil de usuario y gestiona los técnicos asociados"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        c.execute('SELECT nombre, apellido FROM usuarios WHERE id = %s', (user_id,))
        old_user_info = c.fetchone()
        old_nombre = old_user_info[0] if old_user_info[0] else ''
        old_apellido = old_user_info[1] if old_user_info[1] else ''
        old_nombre_completo = f"{old_nombre} {old_apellido}".strip()
        
        # Capitalizar nombre y apellido
        nuevo_nombre_cap = nombre.strip().title() if nombre else ''
        nuevo_apellido_cap = apellido.strip().title() if apellido else ''
        
        c.execute('UPDATE usuarios SET nombre = %s, apellido = %s, email = %s WHERE id = %s',
                    (nuevo_nombre_cap, nuevo_apellido_cap, email.strip() if email else None, user_id))
        
        nuevo_nombre_completo = f"{nuevo_nombre_cap} {nuevo_apellido_cap}".strip()
        
        # Actualizar o crear técnico usando la función auxiliar
        update_tecnico_from_user(old_nombre_completo, nuevo_nombre_completo)
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        log_sql_error(e, "update_user_profile_complete")
        return False
    finally:
        conn.close()

def get_cliente_puntaje(id_cliente):
    """Obtiene el puntaje de un cliente específico"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT puntaje FROM clientes_puntajes WHERE id_cliente = %s", (id_cliente,))
    resultado = c.fetchone()
    conn.close()
    return resultado[0] if resultado else 0

def get_cliente_puntaje_by_nombre(nombre_cliente):
    """Obtiene el puntaje de un cliente por su nombre"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT cp.puntaje 
        FROM clientes_puntajes cp
        JOIN clientes c ON cp.id_cliente = c.id_cliente
        WHERE c.nombre = %s
    """, (nombre_cliente,))
    resultado = c.fetchone()
    conn.close()
    return resultado[0] if resultado else 0

def set_cliente_puntaje(id_cliente, puntaje):
    """Establece el puntaje para un cliente específico"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Intentar actualizar si ya existe
        c.execute("""
            INSERT INTO clientes_puntajes (id_cliente, puntaje) 
            VALUES (%s, %s)
            ON CONFLICT(id_cliente) 
            DO UPDATE SET puntaje = %s
        """, (id_cliente, puntaje, puntaje))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error al establecer puntaje: {e}")
        return False
    finally:
        conn.close()

def set_cliente_puntaje_by_nombre(nombre_cliente, puntaje):
    """Establece el puntaje para un cliente por su nombre"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Obtener el ID del cliente
        c.execute("SELECT id_cliente FROM clientes WHERE nombre = %s", (nombre_cliente,))
        resultado = c.fetchone()
        if not resultado:
            return False  # El cliente no existe
        
        id_cliente = resultado[0]
        return set_cliente_puntaje(id_cliente, puntaje)
    except Exception as e:
        print(f"Error al establecer puntaje por nombre: {e}")
        return False
    finally:
        conn.close()

def get_clientes_puntajes_dataframe(only_active=False):
    """Obtiene un DataFrame con todos los clientes y sus puntajes"""
    query = """
    SELECT c.id_cliente, c.nombre, 
           COALESCE(cp.puntaje, 0) as puntaje
    FROM clientes c
    LEFT JOIN clientes_puntajes cp ON c.id_cliente = cp.id_cliente
    """
    if only_active:
        query += " WHERE c.activo IS TRUE"
    
    query += " ORDER BY c.nombre"
    
    engine = get_engine()
    df = pd.read_sql_query(query, con=engine)
    
    return df

def get_grupos_dataframe():
    """Obtiene DataFrame de grupos con sus roles asignados"""
    query = """
    SELECT g.id_grupo, g.nombre, 
           STRING_AGG(r.nombre, ', ') as roles_asignados,
           g.descripcion
    FROM grupos g
    LEFT JOIN grupos_roles gr ON g.id_grupo = gr.id_grupo
    LEFT JOIN roles r ON gr.id_rol = r.id_rol
    GROUP BY g.id_grupo, g.nombre, g.descripcion
    ORDER BY g.nombre
    """
    
    engine = get_engine()
    df = pd.read_sql_query(text(query), con=engine)
    
    # Reemplazar valores None con cadena vacía para mejor visualización
    df['roles_asignados'] = df['roles_asignados'].fillna('')
    df['descripcion'] = df['descripcion'].fillna('')
    
    return df

def get_grupo_puntaje(id_grupo):
    """Obtiene el puntaje de un grupo específico"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT puntaje FROM grupos_puntajes WHERE id_grupo = %s", (id_grupo,))
    resultado = c.fetchone()
    conn.close()
    return resultado[0] if resultado else 0

def get_grupo_puntaje_by_nombre(nombre_grupo):
    """Obtiene el puntaje de un grupo por su nombre"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT gp.puntaje 
        FROM grupos_puntajes gp
        JOIN grupos g ON gp.id_grupo = g.id_grupo
        WHERE g.nombre = %s
    """, (nombre_grupo,))
    resultado = c.fetchone()
    conn.close()
    return resultado[0] if resultado else 0

def set_grupo_puntaje(id_grupo, puntaje):
    """Establece el puntaje para un grupo específico"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Intentar actualizar si ya existe
        c.execute("""
            INSERT INTO grupos_puntajes (id_grupo, puntaje) 
            VALUES (%s, %s)
            ON CONFLICT(id_grupo) 
            DO UPDATE SET puntaje = %s
        """, (id_grupo, puntaje, puntaje))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error al establecer puntaje: {e}")
        return False
    finally:
        conn.close()

def set_grupo_puntaje_by_nombre(nombre_grupo, puntaje):
    """Establece el puntaje para un grupo por su nombre"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Obtener el ID del grupo
        c.execute("SELECT id_grupo FROM grupos WHERE nombre = %s", (nombre_grupo,))
        resultado = c.fetchone()
        if not resultado:
            return False  # El grupo no existe
        
        id_grupo = resultado[0]
        return set_grupo_puntaje(id_grupo, puntaje)
    except Exception as e:
        print(f"Error al establecer puntaje por nombre: {e}")
        return False
    finally:
        conn.close()

def get_grupos_puntajes_dataframe():
    """Obtiene un DataFrame con todos los grupos y sus puntajes"""
    query = """
    SELECT g.id_grupo, g.nombre, g.descripcion, 
           COALESCE(MAX(gp.puntaje), 0) as puntaje,
           STRING_AGG(r.nombre, ', ') as roles_asignados
    FROM grupos g
    LEFT JOIN grupos_puntajes gp ON g.id_grupo = gp.id_grupo
    LEFT JOIN grupos_roles gr ON g.id_grupo = gr.id_grupo
    LEFT JOIN roles r ON gr.id_rol = r.id_rol
    GROUP BY g.id_grupo, g.nombre, g.descripcion
    ORDER BY g.nombre
    """
    engine = get_engine()
    df = pd.read_sql_query(text(query), con=engine)
    
    # Reemplazar valores None con cadena vacía para mejor visualización
    df['roles_asignados'] = df['roles_asignados'].fillna('')
    df['descripcion'] = df['descripcion'].fillna('')
    
    return df

def registrar_actividad(usuario_id, username, tipo_actividad, descripcion):
    """Registra una actividad de usuario en la base de datos
    
    Args:
        usuario_id: ID del usuario (puede ser None para usuarios no autenticados)
        username: Nombre de usuario
        tipo_actividad: Tipo de actividad (login, creacion, edicion, eliminacion)
        descripcion: Descripción detallada de la actividad
    """
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO actividades_usuarios (usuario_id, username, tipo_actividad, descripcion)
            VALUES (%s, %s, %s, %s)
        ''', (usuario_id, username, tipo_actividad, descripcion))
        conn.commit()
        conn.close()
    except Exception as e:
        log_sql_error(e, "INSERT INTO actividades_usuarios", 
                     f"usuario_id: {usuario_id}, username: {username}, tipo: {tipo_actividad}")

def registrar_login(usuario_id, username):
    """Registra un inicio de sesión exitoso"""
    registrar_actividad(usuario_id, username, "login", "Inicio de sesión exitoso")

def registrar_creacion(usuario_id, username, entidad, detalles):
    """Registra la creación de un registro"""
    registrar_actividad(usuario_id, username, "creacion", f"Creación de {entidad}: {detalles}")

def registrar_edicion(usuario_id, username, entidad, detalles):
    """Registra la edición de un registro"""
    registrar_actividad(usuario_id, username, "edicion", f"Edición de {entidad}: {detalles}")

def registrar_eliminacion(usuario_id, username, entidad, detalles):
    """Registra la eliminación de un registro"""
    registrar_actividad(usuario_id, username, "eliminacion", f"Eliminación de {entidad}: {detalles}")

def get_actividades_dataframe(limit=1000):
    """Obtiene un DataFrame con las actividades de usuarios
    
    Args:
        limit: Número máximo de registros a devolver
    
    Returns:
        DataFrame con las actividades de usuarios
    """
    try:
        query = '''
            SELECT 
                a.id, 
                a.usuario_id, 
                a.username, 
                a.tipo_actividad, 
                a.descripcion, 
                a.fecha_hora,
                u.nombre,
                u.apellido
            FROM actividades_usuarios a
            LEFT JOIN usuarios u ON a.usuario_id = u.id
            ORDER BY a.fecha_hora DESC
            LIMIT :limit
        '''
        engine = get_engine()
        df = pd.read_sql_query(text(query), con=engine, params={"limit": int(limit)})
        
        if not df.empty and 'fecha_hora' in df.columns:
            df['fecha_hora'] = pd.to_datetime(df['fecha_hora'])
            
        return df
    except Exception as e:
        log_sql_error(e, query, limit)
        return pd.DataFrame()

def get_tipo_puntaje(id_tipo):
    """Obtiene el puntaje de un tipo de tarea específico"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT puntaje FROM tipos_tarea_puntajes WHERE id_tipo = %s", (id_tipo,))
    resultado = c.fetchone()
    conn.close()
    return resultado[0] if resultado else 0


def get_tipo_puntaje_by_descripcion(descripcion_tipo):
    """Obtiene el puntaje de un tipo de tarea por su descripción"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT tp.puntaje 
        FROM tipos_tarea_puntajes tp
        JOIN tipos_tarea t ON tp.id_tipo = t.id_tipo
        WHERE t.descripcion = %s
    """, (descripcion_tipo,))
    resultado = c.fetchone()
    conn.close()
    return resultado[0] if resultado else 0


def set_tipo_puntaje(id_tipo, puntaje):
    """Establece el puntaje para un tipo de tarea específico"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Intentar actualizar si ya existe
        c.execute("""
            INSERT INTO tipos_tarea_puntajes (id_tipo, puntaje) 
            VALUES (%s, %s)
            ON CONFLICT(id_tipo) 
            DO UPDATE SET puntaje = %s
        """, (id_tipo, puntaje, puntaje))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error al establecer puntaje: {e}")
        return False
    finally:
        conn.close()


def set_tipo_puntaje_by_descripcion(descripcion_tipo, puntaje):
    """Establece el puntaje para un tipo de tarea por su descripción"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Obtener el ID del tipo de tarea
        c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = %s", (descripcion_tipo,))
        resultado = c.fetchone()
        if not resultado:
            return False  # El tipo de tarea no existe
        
        id_tipo = resultado[0]
        return set_tipo_puntaje(id_tipo, puntaje)
    except Exception as e:
        print(f"Error al establecer puntaje por descripción: {e}")
        return False
    finally:
        conn.close()


def get_tipos_puntajes_dataframe():
    """Obtiene un DataFrame con todos los tipos de tarea y sus puntajes"""
    query = """
    SELECT t.id_tipo, t.descripcion, 
           COALESCE(MAX(tp.puntaje), 0) as puntaje,
           STRING_AGG(r.nombre, ', ') as roles_asociados
    FROM tipos_tarea t
    LEFT JOIN tipos_tarea_puntajes tp ON t.id_tipo = tp.id_tipo
    LEFT JOIN tipos_tarea_roles tr ON t.id_tipo = tr.id_tipo
    LEFT JOIN roles r ON tr.id_rol = r.id_rol
    GROUP BY t.id_tipo, t.descripcion
    ORDER BY t.descripcion
    """
    engine = get_engine()
    df = pd.read_sql_query(text(query), con=engine)
    
    # Reemplazar valores None con cadena vacía para mejor visualización
    df['roles_asociados'] = df['roles_asociados'].fillna('')
    return df

def add_grupo(nombre, descripcion=None):
    """Agrega un nuevo grupo a la base de datos"""
    from .utils import normalize_text
    
    conn = get_connection()
    c = conn.cursor()
    try:
        # Verificar si ya existe un grupo con el mismo nombre normalizado
        c.execute("SELECT id_grupo FROM grupos")
        grupos = c.fetchall()
        
        nombre_normalizado = normalize_text(nombre)
        for grupo_id in grupos:
            grupo = get_grupo_by_id(grupo_id[0])
            if normalize_text(grupo[1]) == nombre_normalizado:
                return False  # Ya existe un grupo con ese nombre normalizado
        
        # Si no existe, insertar el nuevo grupo con el nombre original
        c.execute("INSERT INTO grupos (nombre, descripcion) VALUES (%s, %s) RETURNING id_grupo", 
                 (nombre, descripcion))
        nuevo_grupo_id = c.fetchone()[0]
        
        # Si es el grupo "General", asociarlo automáticamente a todos los roles existentes
        if nombre.lower() == 'general':
            c.execute("SELECT id_rol FROM roles WHERE nombre != 'admin'")
            roles_existentes = c.fetchall()
            
            roles_asociados = 0
            for rol_tuple in roles_existentes:
                rol_id = rol_tuple[0]
                try:
                    c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (%s, %s)", 
                             (nuevo_grupo_id, rol_id))
                    roles_asociados += 1
                except Exception:
                    # Ya existe esta relación, no es un error
                    pass
            
            if roles_asociados > 0:
                print(f"✅ Grupo 'General' asociado automáticamente a {roles_asociados} roles existentes")
        
        conn.commit()
        return True
    except Exception:
        return False  # Ya existe un grupo con ese nombre exacto
    finally:
        conn.close()

def get_grupo_by_id(grupo_id):
    """Obtiene un grupo por su ID"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM grupos WHERE id_grupo = %s", (grupo_id,))
        grupo = c.fetchone()
        return grupo
    except Exception as e:
        log_sql_error(e, "get_grupo_by_id")
        return None
    finally:
        conn.close()

def get_roles_by_grupo(grupo_id):
    """Obtiene los roles asociados a un grupo específico"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""SELECT r.id_rol, r.nombre 
                   FROM roles r
                   JOIN grupos_roles gr ON r.id_rol = gr.id_rol
                   WHERE gr.id_grupo = %s""", (grupo_id,))
        roles = c.fetchall()
        return roles
    except Exception as e:
        log_sql_error(e, "get_roles_by_grupo")
        return []
    finally:
        conn.close()

def get_grupos_by_rol(rol_id):
    """Obtiene los grupos asociados a un rol específico"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""SELECT g.id_grupo, g.nombre 
                   FROM grupos g
                   JOIN grupos_roles gr ON g.id_grupo = gr.id_grupo
                   WHERE gr.id_rol = %s""", (rol_id,))
        grupos = c.fetchall()
        return grupos
    except Exception as e:
        log_sql_error(e, "get_grupos_by_rol")
        return []
    finally:
        conn.close()

def assign_grupo_to_rol(grupo_id, rol_id):
    """Asigna un grupo a un rol específico"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (%s, %s)", (grupo_id, rol_id))
        conn.commit()
        return True
    except Exception:
        return False  # Ya existe esta relación
    except Exception as e:
        log_sql_error(e, "assign_grupo_to_rol")
        return False
    finally:
        conn.close()

def remove_grupo_from_rol(grupo_id, rol_id):
    """Elimina la asignación de un grupo a un rol"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM grupos_roles WHERE id_grupo = %s AND id_rol = %s", (grupo_id, rol_id))
        conn.commit()
        return True
    except Exception as e:
        log_sql_error(e, "remove_grupo_from_rol")
        return False
    finally:
        conn.close()

def update_grupo_roles(grupo_id, rol_ids):
    """Actualiza los roles asignados a un grupo"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Eliminar todas las asignaciones actuales
        c.execute("DELETE FROM grupos_roles WHERE id_grupo = %s", (grupo_id,))
        
        # Insertar las nuevas asignaciones
        for rol_id in rol_ids:
            c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (%s, %s)", (grupo_id, rol_id))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        log_sql_error(e, "update_grupo_roles")
        return False
    finally:
        conn.close()

def get_departamentos_list():
    """Obtiene lista única de departamentos desde nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT DISTINCT departamento FROM nomina WHERE departamento IS NOT NULL AND departamento != '' ORDER BY departamento")
        departamentos = [row[0] for row in c.fetchall()]
        return departamentos
    except Exception as e:
        log_sql_error(e, f"Error al obtener departamentos: {e}")
        return []
    finally:
        conn.close()

def generate_standard_password(apellido_completo):
    """Genera contraseña estándar basada en el primer apellido"""
    # Extraer solo el primer apellido (primera palabra)
    primer_apellido = apellido_completo.strip().split()[0]
    
    # Primer apellido con primera letra mayúscula + año actual + punto
    from datetime import datetime
    year = datetime.now().year
    apellido_formatted = primer_apellido.capitalize()
    return f"{apellido_formatted}{year}."

def generate_users_from_nomina(enable_users=False):
    """Genera usuarios desde los datos de nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Obtener TODOS los empleados activos de nómina (sin filtrar duplicados aquí)
        c.execute("""
            SELECT n.id, n.nombre, n.apellido, n.email, n.departamento, n.cargo
            FROM nomina n
            WHERE n.activo = true
            ORDER BY n.nombre, n.apellido
        """)
        
        empleados = c.fetchall()
        stats = {
            'total_empleados': len(empleados),
            'usuarios_creados': 0,
            'tecnicos_creados': 0,
            'roles_creados': 0,
            'usuarios_sin_email': 0,
            'empleados_sin_email': [],
            'usuarios_duplicados': 0,
            'empleados_duplicados': [],
            'usuarios_generados': [], 
            'errores': []
        }
        
        # Obtener rol "sin_rol" del sistema para asignar por defecto
        c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (SYSTEM_ROLES['SIN_ROL'],))
        sin_rol_result = c.fetchone()
        sin_rol_id = sin_rol_result[0] if sin_rol_result else None
        
        # Obtener grupo "General" para asignar por defecto (crear si no existe)
        c.execute("SELECT id_grupo FROM grupos WHERE nombre = %s", ('General',))
        general_grupo_result = c.fetchone()
        if not general_grupo_result:
            # Crear grupo "General" si no existe
            c.execute("""
                INSERT INTO grupos (nombre, descripcion) 
                VALUES (%s, %s) RETURNING id_grupo
            """, ('General', 'Grupo por defecto para usuarios'))
            general_grupo_id = c.fetchone()[0]
        else:
            general_grupo_id = general_grupo_result[0]
        
        # Verificar que tenemos los elementos necesarios
        if not sin_rol_id:
            stats['errores'].append("No se encontró el rol 'sin_rol' del sistema")
            return stats
        
        if not general_grupo_id:
            stats['errores'].append("No se pudo crear o encontrar el grupo 'General'")
            return stats
        
        for empleado in empleados:
            id_empleado, nombre_bd, apellido_bd, email, departamento, cargo = empleado
            
            # Usar los datos tal como vienen de la base de datos de nómina
            nombre = nombre_bd
            apellido = apellido_bd
            
            # Verificar si el email es válido
            if not email or email.strip() == '' or email.lower() == 'falta dato' or '@' not in email:
                stats['usuarios_sin_email'] += 1
                stats['empleados_sin_email'].append(f"{apellido}, {nombre}")
                continue  # Saltar este empleado y no crear usuario
            
            try:
                # Verificar si ya existe un usuario para este empleado (AQUÍ detectamos duplicados)
                c.execute("""
                    SELECT COUNT(*) FROM usuarios 
                    WHERE (nombre = %s AND apellido = %s)
                    OR email = %s
                """, (nombre, apellido, email))
                
                if c.fetchone()[0] > 0:
                    # Ya existe un usuario similar, registrar como duplicado
                    stats['usuarios_duplicados'] += 1
                    stats['empleados_duplicados'].append(f"{apellido}, {nombre}")
                    continue
                
                # Generar username basándose en el email
                base_username = email.split('@')[0].lower()
                
                username = base_username
                counter = 1
                
                while True:
                    c.execute("SELECT id FROM usuarios WHERE username = %s", (username,))
                    if not c.fetchone():
                        break
                    username = f"{base_username}{counter}"
                    counter += 1
                
                # Generar contraseña estándar
                password = generate_standard_password(apellido)
                
                # Hashear la contraseña antes de insertarla
                from .auth import hash_password
                password_hash = hash_password(password)
                
                # Convertir el hash a string si es bytes (CORRECCIÓN)
                if isinstance(password_hash, bytes):
                    password_hash = password_hash.decode('utf-8')
                
                # Determinar el rol basándose en el departamento o cargo
                rol_asignado = sin_rol_id  # Por defecto
                
                # Primero intentar buscar rol por departamento
                if departamento and departamento.strip() != '' and departamento.lower() != 'falta dato':
                    try:
                        dept_id, admin_id, _, input_is_admin = get_or_create_role_ids_from_sector(departamento.strip())
                        if input_is_admin and admin_id:
                            rol_asignado = admin_id
                        elif dept_id:
                            rol_asignado = dept_id
                    except Exception:
                        pass
                
                # Si no se encontró por departamento, intentar por cargo
                if rol_asignado == sin_rol_id and cargo and cargo.strip() != '' and cargo.lower() != 'falta dato':
                    c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (cargo.strip(),))
                    rol_cargo = c.fetchone()
                    if rol_cargo:
                        rol_asignado = rol_cargo[0]
                
                # Crear usuario con el rol determinado
                c.execute("""
                    INSERT INTO usuarios (username, password_hash, nombre, apellido, email, 
                                        is_admin, is_active, rol_id) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (username, password_hash, nombre, apellido, email, False, enable_users, rol_asignado))
                
                # Agregar información del usuario generado
                stats['usuarios_generados'].append({
                    'nombre': nombre,
                    'apellido': apellido,
                    'username': username,
                    'password': password,  # Contraseña sin hashear para mostrar
                    'email': email,
                    'activo': 'Sí' if enable_users else 'No'
                })
                
                stats['usuarios_creados'] += 1
                
                # Crear técnico correspondiente con nombre completo
                nombre_completo_tecnico = f"{nombre} {apellido}"
                c.execute("SELECT 1 FROM tecnicos WHERE nombre = %s LIMIT 1", (nombre_completo_tecnico,))
                tecnico_existed = bool(c.fetchone())
                tecnico_id = get_or_create_tecnico(nombre_completo_tecnico, conn=conn)
                if tecnico_id and not tecnico_existed:
                    stats['tecnicos_creados'] += 1
                
                # Actualizar registros existentes para asociar al usuario
                c.execute("""
                    UPDATE registros SET usuario_id = (
                        SELECT id FROM usuarios WHERE username = %s
                    )
                    WHERE id_tecnico = (
                        SELECT id_tecnico FROM tecnicos WHERE nombre = %s
                    )
                """, (username, nombre_completo_tecnico))
                
            except Exception as e:
                error_msg = f"Error procesando {nombre} {apellido}: {str(e)}"
                stats['errores'].append(error_msg)
                log_sql_error(e, error_msg)
        
        conn.commit()
        return stats
        
    except Exception as e:
        log_sql_error(e, f"Error en generate_users_from_nomina: {e}")
        return {
            'total_empleados': 0,
            'usuarios_creados': 0,
            'tecnicos_creados': 0,
            'roles_creados': 0,
            'usuarios_sin_email': 0,
            'empleados_sin_email': [],
            'usuarios_generados': [],
            'errores': [str(e)]
        }
    finally:
        conn.close()

def get_user_departamento_from_nomina(user_id, conn=None):
    """Obtiene el departamento del usuario desde la tabla nomina basándose en nombre y apellido"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    try:
        # Obtener nombre y apellido del usuario
        c.execute("SELECT nombre, apellido FROM usuarios WHERE id = %s", (user_id,))
        user_data = c.fetchone()
        
        if not user_data or not user_data[0] or not user_data[1]:
            if close_conn:
                conn.close()
            return None
        
        nombre_completo = f"{user_data[0]} {user_data[1]}"
        
        # Buscar el departamento en la tabla nomina
        c.execute("""
            SELECT departamento 
            FROM nomina 
            WHERE LOWER(TRIM(CONCAT(nombre, ' ', apellido))) = LOWER(TRIM(%s))
            AND activo = true
            AND departamento IS NOT NULL 
            AND departamento != ''
            AND LOWER(departamento) != 'falta dato'
            LIMIT 1
        """, (nombre_completo,))
        
        result = c.fetchone()
        departamento = result[0] if result else None
        
        if close_conn:
            conn.close()
        return departamento
        
    except Exception as e:
        if close_conn:
            conn.close()
        log_sql_error(e, "get_user_departamento_from_nomina")
        return None

def get_or_create_grupo_with_department_association(nombre_grupo, user_id=None, conn=None):
    """Obtiene o crea un grupo por nombre y lo asocia automáticamente al departamento del usuario"""
    from .utils import normalize_text
    
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    try:
        # Buscar grupo existente por nombre normalizado
        c.execute("SELECT id_grupo, nombre FROM grupos")
        grupos = c.fetchall()
        
        nombre_normalizado = normalize_text(nombre_grupo)
        for grupo_id, grupo_nombre in grupos:
            if normalize_text(grupo_nombre) == nombre_normalizado:
                # Si el grupo existe y tenemos user_id, asociar al departamento del usuario
                if user_id:
                    asociar_grupo_a_departamento_usuario(grupo_id, user_id, conn)
                if close_conn:
                    conn.close()
                return grupo_id
        
        # Si no existe, crear nuevo grupo
        c.execute("""
            INSERT INTO grupos (nombre, descripcion) 
            VALUES (%s, %s) RETURNING id_grupo
        """, (nombre_grupo, f'Grupo creado automáticamente desde registros: {nombre_grupo}'))
        
        grupo_id = c.fetchone()[0]
        
        # Asociar automáticamente al departamento del usuario si se proporciona user_id
        if user_id:
            asociar_grupo_a_departamento_usuario(grupo_id, user_id, conn)
        
        conn.commit()
        
        if close_conn:
            conn.close()
        return grupo_id
        
    except Exception as e:
        if close_conn:
            conn.close()
        raise e

def asociar_grupo_a_departamento_usuario(grupo_id, user_id, conn=None):
    """Asocia un grupo al departamento del usuario que lo está creando/usando"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    try:
        # Obtener el rol (departamento) del usuario
        c.execute("SELECT rol_id FROM usuarios WHERE id = %s", (user_id,))
        user_rol = c.fetchone()
        
        if user_rol and user_rol[0]:
            rol_id = user_rol[0]
            
            # Verificar si la asociación ya existe
            c.execute("SELECT COUNT(*) FROM grupos_roles WHERE id_grupo = %s AND id_rol = %s", 
                     (grupo_id, rol_id))
            
            if c.fetchone()[0] == 0:  # Si no existe la asociación
                # Crear la asociación
                c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (%s, %s)", 
                         (grupo_id, rol_id))
                
                # Obtener nombres para logging
                c.execute("SELECT nombre FROM grupos WHERE id_grupo = %s", (grupo_id,))
                grupo_nombre = c.fetchone()[0]
                
                c.execute("SELECT nombre FROM roles WHERE id_rol = %s", (rol_id,))
                rol_nombre = c.fetchone()[0]
                
                print(f"✅ Grupo '{grupo_nombre}' asociado automáticamente al departamento '{rol_nombre}'")
        
        if close_conn:
            conn.commit()
            conn.close()
            
    except Exception as e:
        if close_conn:
            conn.close()
        print(f"⚠️ Error al asociar grupo a departamento: {e}")


def get_departamento_by_tecnico_name(tecnico_nombre, conn=None):
    """Obtiene el departamento de un técnico basándose en su nombre desde la tabla nomina
    Versión mejorada que maneja múltiples nombres y apellidos"""
    from .utils import normalize_text
    
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    try:
        # Normalizar el nombre del técnico
        tecnico_normalizado = normalize_text(tecnico_nombre)
        
        # Dividir el nombre en palabras para análisis
        palabras_tecnico = [palabra for palabra in tecnico_normalizado.split() if len(palabra) > 1]
        
        if not palabras_tecnico:
            if close_conn:
                conn.close()
            return None
        
        # Obtener todos los empleados activos con sus departamentos
        c.execute("""
            SELECT nombre, apellido, departamento 
            FROM nomina 
            WHERE activo = true
            AND departamento IS NOT NULL 
            AND departamento != ''
            AND LOWER(departamento) != 'falta dato'
        """)
        
        empleados = c.fetchall()
        
        # Buscar coincidencias usando estrategias múltiples
        for nombre, apellido, departamento in empleados:
            if not nombre or not apellido:
                continue
                
            nombre_normalizado = normalize_text(nombre)
            apellido_normalizado = normalize_text(apellido)
            nombre_completo_normalizado = f"{nombre_normalizado} {apellido_normalizado}".strip()
            
            # Dividir nombres y apellidos en palabras individuales
            palabras_nombre = [p for p in nombre_normalizado.split() if len(p) > 1]
            palabras_apellido = [p for p in apellido_normalizado.split() if len(p) > 1]
            todas_palabras_empleado = palabras_nombre + palabras_apellido
            
            # Estrategia 1: Coincidencia exacta completa
            if nombre_completo_normalizado == tecnico_normalizado:
                if close_conn:
                    conn.close()
                return departamento
            
            # Estrategia 2: Todas las palabras del técnico están en el empleado
            if all(palabra in todas_palabras_empleado for palabra in palabras_tecnico):
                if close_conn:
                    conn.close()
                return departamento
            
            # Estrategia 3: Coincidencia por componentes individuales
            # Verificar si cada palabra del técnico coincide con alguna palabra del empleado
            coincidencias_exactas = 0
            coincidencias_parciales = 0
            
            for palabra_tecnico in palabras_tecnico:
                # Coincidencia exacta con alguna palabra del empleado
                if palabra_tecnico in todas_palabras_empleado:
                    coincidencias_exactas += 1
                # Coincidencia parcial (la palabra del técnico está contenida en alguna palabra del empleado)
                elif any(palabra_tecnico in palabra_empleado or palabra_empleado in palabra_tecnico 
                        for palabra_empleado in todas_palabras_empleado if len(palabra_empleado) > 2):
                    coincidencias_parciales += 1
            
            # Calcular porcentaje de coincidencia
            total_palabras_tecnico = len(palabras_tecnico)
            porcentaje_exacto = coincidencias_exactas / total_palabras_tecnico if total_palabras_tecnico > 0 else 0
            porcentaje_total = (coincidencias_exactas + coincidencias_parciales) / total_palabras_tecnico if total_palabras_tecnico > 0 else 0
            
            # Criterios de validación más estrictos
            if porcentaje_exacto >= 0.8:  # 80% de coincidencias exactas
                if close_conn:
                    conn.close()
                return departamento
            elif porcentaje_total >= 0.9 and coincidencias_exactas >= 1:  # 90% total con al menos una exacta
                if close_conn:
                    conn.close()
                return departamento
            
            # Estrategia 4: Validación especial para casos complejos
            # Si el técnico tiene 2 palabras y el empleado tiene más de 2
            if len(palabras_tecnico) == 2 and len(todas_palabras_empleado) >= 2:
                # Verificar si las 2 palabras del técnico están en las primeras palabras del empleado
                if (palabras_tecnico[0] in palabras_nombre and 
                    palabras_tecnico[1] in (palabras_nombre + palabras_apellido[:2])):
                    if close_conn:
                        conn.close()
                    return departamento
                # O si están en nombre + primer apellido
                if (palabras_tecnico[0] in palabras_nombre and 
                    palabras_tecnico[1] in palabras_apellido):
                    if close_conn:
                        conn.close()
                    return departamento
        
        if close_conn:
            conn.close()
        return None
        
    except Exception as e:
        if close_conn:
            conn.close()
        log_sql_error(e, "get_departamento_by_tecnico_name")
        return None

def asociar_grupo_a_departamento_por_tecnico(grupo_id, tecnico_nombre, conn=None):
    """Asocia un grupo al departamento basándose en el técnico del registro"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    try:
        # Obtener el departamento del técnico desde la nómina
        departamento = get_departamento_by_tecnico_name(tecnico_nombre, conn)
        
        if not departamento:
            print(f"⚠️ No se encontró departamento para el técnico: {tecnico_nombre}")
            if close_conn:
                conn.close()
            return False
        
        rol_id, _ = get_or_create_role_from_sector(departamento)
        if not rol_id:
            print(f"⚠️ No se encontró rol para el departamento: {departamento}")
            if close_conn:
                conn.close()
            return False
        
        # Verificar si la asociación ya existe
        c.execute("SELECT COUNT(*) FROM grupos_roles WHERE id_grupo = %s AND id_rol = %s", 
                 (grupo_id, rol_id))
        
        if c.fetchone()[0] == 0:  # Si no existe la asociación
            # Crear la asociación
            c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (%s, %s)", 
                     (grupo_id, rol_id))
            
            # Obtener nombres para logging
            c.execute("SELECT nombre FROM grupos WHERE id_grupo = %s", (grupo_id,))
            grupo_nombre = c.fetchone()[0]
            
            print(f"✅ Grupo '{grupo_nombre}' asociado automáticamente al departamento '{departamento}' (basado en técnico: {tecnico_nombre})")
            
            if close_conn:
                conn.commit()
                conn.close()
            return True
        else:
            # La asociación ya existe, no hacer nada
            if close_conn:
                conn.close()
            return False
            
    except Exception as e:
        if close_conn:
            conn.close()
        print(f"⚠️ Error al asociar grupo a departamento por técnico: {e}")
        return False


# --- Funciones de Vacaciones ---

def get_vacaciones_activas():
    """Obtiene lista de usuarios actualmente de vacaciones"""
    engine = get_engine()
    today = datetime.now().date()
    try:
        query = """
        SELECT v.id, u.nombre, u.apellido, v.fecha_inicio, v.fecha_fin, v.tipo
        FROM vacaciones v
        JOIN usuarios u ON v.usuario_id = u.id
        WHERE v.fecha_inicio <= :today AND v.fecha_fin >= :today
        ORDER BY v.fecha_inicio
        """
        df = pd.read_sql_query(text(query), con=engine, params={"today": today})
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo vacaciones activas: {e}")
        return pd.DataFrame()

def get_user_vacaciones(user_id, year=None):
    """Obtiene historial de vacaciones de un usuario, opcionalmente filtrado por año"""
    engine = get_engine()
    try:
        params = {"uid": user_id}
        year_filter = ""
        if year:
            year_filter = "AND (EXTRACT(YEAR FROM fecha_inicio) = :year OR EXTRACT(YEAR FROM fecha_fin) = :year)"
            params["year"] = int(year)
            
        query = f"""
        SELECT id, fecha_inicio, fecha_fin, created_at, tipo, observaciones
        FROM vacaciones
        WHERE usuario_id = :uid
        {year_filter}
        ORDER BY fecha_inicio DESC
        """
        df = pd.read_sql_query(text(query), con=engine, params=params)
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo vacaciones de usuario: {e}")
        return pd.DataFrame()

def get_upcoming_vacaciones():
    """Obtiene todas las licencias futuras (fecha_inicio >= hoy)"""
    try:
        ensure_vacaciones_schema()
        query = """
            SELECT v.id, v.usuario_id, u.nombre, u.apellido, v.fecha_inicio, v.fecha_fin, v.tipo, v.observaciones
            FROM vacaciones v
            JOIN usuarios u ON v.usuario_id = u.id
            WHERE v.fecha_inicio > CURRENT_DATE
            ORDER BY v.fecha_inicio ASC
        """
        engine = get_engine()
        df = pd.read_sql_query(query, con=engine)
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo próximas licencias: {e}")
        return pd.DataFrame()

def get_vacaciones_by_users_and_range(user_ids, start_date, end_date):
    """Obtiene licencias/vacaciones de usuarios que se superponen con un rango de fechas"""
    if not user_ids:
        return pd.DataFrame(columns=["usuario_id", "fecha_inicio", "fecha_fin", "tipo"])
    try:
        ensure_vacaciones_schema()
        clean_ids = sorted({int(uid) for uid in user_ids if uid is not None})
        if not clean_ids:
            return pd.DataFrame(columns=["usuario_id", "fecha_inicio", "fecha_fin", "tipo"])

        conn = get_connection()
        try:
            c = conn.cursor()
            placeholders = ",".join(["%s"] * len(clean_ids))
            c.execute(f"""
                SELECT usuario_id, fecha_inicio, fecha_fin, tipo
                FROM vacaciones
                WHERE usuario_id IN ({placeholders})
                  AND fecha_inicio <= %s
                  AND fecha_fin >= %s
            """, tuple(clean_ids) + (end_date, start_date))
            rows = c.fetchall()
        finally:
            conn.close()

        if not rows:
            return pd.DataFrame(columns=["usuario_id", "fecha_inicio", "fecha_fin", "tipo"])
        return pd.DataFrame(rows, columns=["usuario_id", "fecha_inicio", "fecha_fin", "tipo"])
    except Exception as e:
        log_sql_error(f"Error obteniendo licencias por usuarios/rango: {e}")
        return pd.DataFrame(columns=["usuario_id", "fecha_inicio", "fecha_fin", "tipo"])

def restore_user_defaults_for_range(user_id, start_date, end_date, conn=None):
    """Restaura los defaults de planificación para un rango de fechas si no hay asignación"""
    try:
        # Obtener defaults
        defaults_df = get_user_default_schedule(user_id)
        if defaults_df.empty:
            return

        defaults_map = {}
        for _, row in defaults_df.iterrows():
            cliente_id = row['cliente_id']
            # Manejar NaN/None de pandas
            if pd.isna(cliente_id):
                cliente_id = None
            else:
                cliente_id = int(cliente_id)
                
            defaults_map[int(row['day_of_week'])] = (int(row['modalidad_id']), cliente_id)

        # Generar fechas en el rango
        current = start_date if isinstance(start_date, datetime) else datetime.strptime(str(start_date), '%Y-%m-%d').date() if isinstance(start_date, str) else start_date
        end = end_date if isinstance(end_date, datetime) else datetime.strptime(str(end_date), '%Y-%m-%d').date() if isinstance(end_date, str) else end_date
        
        # Asegurar objetos date
        if isinstance(current, datetime): current = current.date()
        if isinstance(end, datetime): end = end.date()

        close_conn = False
        if conn is None:
            conn = get_connection()
            close_conn = True

        c = conn.cursor()
        
        # Obtener rol del usuario para insertar correctamente
        c.execute("SELECT rol_id FROM usuarios WHERE id = %s", (user_id,))
        rol_res = c.fetchone()
        rol_id = rol_res[0] if rol_res else None
        
        if not rol_id:
             if close_conn: conn.close()
             return

        try:
            while current <= end:
                dow = current.weekday() # 0=Monday
                if dow in defaults_map:
                    mod_id, cli_id = defaults_map[dow]
                    
                    # Verificar si ya existe asignación para ese día
                    c.execute("SELECT id FROM user_modalidad_schedule WHERE user_id = %s AND fecha = %s", (user_id, current))
                    if not c.fetchone():
                        # Insertar default
                        c.execute("""
                            INSERT INTO user_modalidad_schedule (user_id, rol_id, fecha, modalidad_id, cliente_id)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (user_id, rol_id, current, mod_id, cli_id))
                
                current += timedelta(days=1)
            
            if close_conn:
                conn.commit()
        except Exception as e:
            if close_conn: conn.rollback()
            raise e
        finally:
            if close_conn:
                conn.close()

    except Exception as e:
        log_sql_error(f"Error restoring defaults for range: {e}")

def get_or_create_modalidad_vacaciones(conn=None):
    """Obtiene o crea la modalidad 'Vacaciones'"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    try:
        c = conn.cursor()
        c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE descripcion ILIKE 'Vacaciones'")
        res = c.fetchone()
        if res:
            mid = res[0]
            # Asegurar que esté oculta
            try:
                c.execute("UPDATE modalidades_tarea SET is_hidden = TRUE WHERE id_modalidad = %s", (mid,))
                conn.commit()
            except Exception:
                pass
        else:
            c.execute("INSERT INTO modalidades_tarea (descripcion, is_hidden) VALUES ('Vacaciones', TRUE) RETURNING id_modalidad")
            mid = c.fetchone()[0]
            conn.commit()
        return mid
    except Exception as e:
        log_sql_error(f"Error getting vacaciones modality: {e}")
        return None
    finally:
        if close_conn:
            conn.close()

def get_or_create_tipo_tarea_vacaciones(conn=None):
    """Obtiene o crea el tipo de tarea 'Vacaciones'"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    try:
        c = conn.cursor()
        # Buscar exacto primero
        c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = 'Vacaciones'")
        res = c.fetchone()
        if not res:
            c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion ILIKE 'Vacaciones'")
            res = c.fetchone()
            
        if res:
            tid = res[0]
            # Asegurar que esté oculta
            try:
                c.execute("UPDATE tipos_tarea SET hidden = TRUE WHERE id_tipo = %s", (tid,))
                conn.commit()
            except Exception:
                pass
        else:
            c.execute("INSERT INTO tipos_tarea (descripcion, hidden) VALUES ('Vacaciones', TRUE) RETURNING id_tipo")
            tid = c.fetchone()[0]
            conn.commit()
        return tid
    except Exception as e:
        log_sql_error(f"Error getting vacaciones task type: {e}")
        return None
    finally:
        if close_conn:
            conn.close()

def ensure_vacaciones_schema():
    """Asegura que la tabla vacaciones tenga columnas tipo y observaciones"""
    conn = get_connection()
    try:
        c = conn.cursor()
        try:
            c.execute("ALTER TABLE vacaciones ADD COLUMN IF NOT EXISTS tipo VARCHAR(50) DEFAULT 'vacaciones'")
            conn.commit()
        except Exception:
            conn.rollback()
        try:
            c.execute("ALTER TABLE vacaciones ADD COLUMN IF NOT EXISTS observaciones TEXT DEFAULT NULL")
            conn.commit()
        except Exception:
            conn.rollback()
    finally:
        conn.close()

def get_or_create_tipo_tarea_generic(descripcion, conn=None):
    """Obtiene o crea un tipo de tarea genérico (oculto)"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    try:
        c = conn.cursor()
        # Buscar exacto primero
        c.execute("SELECT id_tipo FROM tipos_tarea WHERE LOWER(descripcion) = LOWER(%s)", (descripcion,))
        res = c.fetchone()
            
        if res:
            tid = res[0]
            # Asegurar que esté oculta
            try:
                c.execute("UPDATE tipos_tarea SET hidden = TRUE WHERE id_tipo = %s", (tid,))
                if close_conn: conn.commit()
            except Exception:
                pass
        else:
            c.execute("INSERT INTO tipos_tarea (descripcion, hidden) VALUES (%s, TRUE) RETURNING id_tipo", (descripcion,))
            tid = c.fetchone()[0]
            if close_conn: conn.commit()
        return tid
    except Exception as e:
        log_sql_error(f"Error getting task type {descripcion}: {e}")
        return None
    finally:
        if close_conn:
            conn.close()

def get_or_create_modalidad_generic(descripcion, conn=None):
    """Obtiene o crea una modalidad genérica (oculta)"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    try:
        c = conn.cursor()
        c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE LOWER(descripcion) = LOWER(%s)", (descripcion,))
        res = c.fetchone()
        
        if res:
            mid = res[0]
             # Asegurar que esté oculta
            try:
                c.execute("UPDATE modalidades_tarea SET is_hidden = TRUE WHERE id_modalidad = %s", (mid,))
                if close_conn: conn.commit()
            except Exception:
                pass
        else:
            c.execute("INSERT INTO modalidades_tarea (descripcion, is_hidden) VALUES (%s, TRUE) RETURNING id_modalidad", (descripcion,))
            mid = c.fetchone()[0]
            if close_conn: conn.commit()
        return mid
    except Exception as e:
        log_sql_error(f"Error getting modality {descripcion}: {e}")
        return None
    finally:
        if close_conn:
            conn.close()

def save_vacaciones(user_id, start_date, end_date, tipo='vacaciones', observaciones=None):
    """Guarda vacaciones/licencias y genera registros.

    `observaciones` (opcional) se guarda en `vacaciones.observaciones` y además
    se anexa a `registros.tarea_realizada` y `registros.descripcion` para que
    el detalle sea visible en el dashboard técnico.
    """
    ok_rng, msg_rng = validate_vacaciones_range(start_date, end_date, tipo=tipo)
    if not ok_rng:
        raise ValueError(msg_rng or "Rango de período inválido.")

    # Normalizar observaciones: NULL si vacío
    obs = (str(observaciones).strip() if observaciones is not None else None) or None

    ensure_vacaciones_schema()
    conn = get_connection()
    try:
        c = conn.cursor()
        
        # 1. Insertar vacaciones (con observaciones)
        c.execute(
            "INSERT INTO vacaciones (usuario_id, fecha_inicio, fecha_fin, tipo, observaciones) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (user_id, start_date, end_date, tipo, obs)
        )
        vac_id = c.fetchone()[0]
        
        # 2. Obtener datos para registros
        
        # Get tecnico_id
        c.execute("SELECT nombre, apellido, email FROM usuarios WHERE id = %s", (user_id,))
        res_user = c.fetchone()
        if not res_user:
             conn.commit()
             return vac_id
             
        u_nom, u_ape, u_email = res_user
        
        id_tecnico = None
        if u_email:
             c.execute("SELECT id_tecnico FROM tecnicos WHERE email = %s", (u_email,))
             res = c.fetchone()
             if res: id_tecnico = res[0]
             
        if not id_tecnico:
             # Fallback nombre/apellido
             c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre ILIKE %s AND apellido ILIKE %s", (u_nom, u_ape))
             res = c.fetchone()
             if res: id_tecnico = res[0]
             
        if not id_tecnico:
             # Fallback 2: Buscar nombre completo en columna nombre (para casos donde apellido es null)
             # Caso: tecnicos.nombre = "Nombre Apellido"
             full_name = f"{u_nom} {u_ape}"
             c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre ILIKE %s", (full_name,))
             res = c.fetchone()
             if res: id_tecnico = res[0]
             
        if not id_tecnico:
             # Fallback 3: Buscar si nombre contiene partes del nombre y apellido
             c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre ILIKE %s AND nombre ILIKE %s", (f"%{u_nom}%", f"%{u_ape}%"))
             res = c.fetchone()
             if res: id_tecnico = res[0]
             
        if not id_tecnico:
            log_sql_error(f"Tecnico not found for user {user_id} during vacation generation")
            conn.commit()
            return vac_id

        # Get Systemscorp ID
        c.execute("SELECT id_cliente FROM clientes WHERE nombre ILIKE '%Systemscorp%' LIMIT 1")
        res_cli = c.fetchone()
        id_cliente = res_cli[0] if res_cli else 1 
        
        # Determinar descripción basada en tipo (helper centralizado)
        desc_tipo = vacaciones_tipo_to_desc_tipo(tipo)

        # Get Tipo ID
        id_tipo = get_or_create_tipo_tarea_generic(desc_tipo)
        if not id_tipo:
             # Fallback to Vacaciones if failed
             id_tipo = get_or_create_tipo_tarea_vacaciones()

        # Get Modality ID
        id_modalidad = get_or_create_modalidad_generic(desc_tipo)
        if not id_modalidad:
             # Fallback to Vacaciones if failed
             id_modalidad = get_or_create_modalidad_vacaciones()

        # Construir tarea_realizada y descripcion (con observaciones si existen)
        reg_label = desc_tipo
        if obs:
            # Limitar largo razonable (no truncamos, pero por las dudas)
            reg_label = f"{desc_tipo} — {obs}"

        # 3. Generate dates
        curr = start_date
        while curr <= end_date:
            if curr.weekday() < 5: # Mon-Fri
                curr_fecha = format_registro_date_iso(curr)
                # Check duplicate
                c.execute("""
                    SELECT id FROM registros 
                    WHERE (
                        CASE
                            WHEN fecha ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN to_date(fecha, 'YYYY-MM-DD')
                            WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{2}$' THEN to_date(fecha, 'DD/MM/YY')
                            WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{4}$' THEN to_date(fecha, 'DD/MM/YYYY')
                            ELSE NULL
                        END
                    ) = %s::date AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s
                """, (curr_fecha, id_tecnico, id_cliente, id_tipo))
                
                if not c.fetchone():
                    c.execute("""
                        INSERT INTO registros (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, numero_ticket, tiempo, mes, usuario_id, grupo, descripcion)
                        VALUES (%s, %s, %s, %s, %s, %s, 'N/A', 8, %s, %s, 'General', %s)
                    """, (curr_fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, reg_label, month_name_es(curr.month), user_id, reg_label))
            curr += timedelta(days=1)
            
        conn.commit()
        
        # 4. Actualizar planificación (user_modalidad_schedule)
        try:
            rol_id = get_user_rol_id(user_id)
            if rol_id:
                if id_modalidad:
                    curr = start_date
                    while curr <= end_date:
                        if curr.weekday() < 5: # Mon-Fri
                            upsert_user_modality_for_date(user_id, rol_id, curr, id_modalidad)
                        curr += timedelta(days=1)
        except Exception as e:
            log_sql_error(f"Error updating planning for vacations: {e}")

        # Limpiar caché de registros para que se actualice la UI inmediatamente
        try:
            clear_user_registros_cache(user_id)
        except:
            pass
            
        return vac_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def _parse_registros_fecha_sql(fecha_col_expr: str) -> str:
    """Devuelve una expresión SQL normalizada a DATE para la columna `fecha` de registros.

    La columna `registros.fecha` es texto y admite 3 formatos:
      - ISO:           2026-09-03  (YYYY-MM-DD)  ← el que usa user_dashboard al guardar
      - DD/MM/YY corto: 03/09/26
      - DD/MM/YYYY largo: 03/09/2026
    No se debe hardcodear un solo formato (ej: `to_date(fecha, 'DD/MM/YY')`)
    porque falla con los formatos ISO generando `Error al eliminar.` o resultados
    incorrectos en la limpieza de registros.
    """
    return f"""
    CASE
        WHEN {fecha_col_expr} ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$'
          THEN to_date({fecha_col_expr}, 'YYYY-MM-DD')
        WHEN {fecha_col_expr} ~ '^\\d{{2}}/\\d{{2}}/\\d{{2}}$'
          THEN to_date({fecha_col_expr}, 'DD/MM/YY')
        WHEN {fecha_col_expr} ~ '^\\d{{2}}/\\d{{2}}/\\d{{4}}$'
          THEN to_date({fecha_col_expr}, 'DD/MM/YYYY')
        ELSE NULL
    END
    """


def vacaciones_tipo_to_desc_tipo(tipo: str) -> str:
    """Mapea el nombre de período (vacaciones/licencia/cumpleaños/otros permisos) a la descripción
    del tipo de tarea usada en `tipos_tarea`. 100% pura, sin DB.

    Es exactamente la lógica que antes estaba inline en save/delete/update.
    """
    t_lower = (tipo or "").lower().strip()
    if "permiso" in t_lower or t_lower == "otros permisos":
        return "Otros permisos"
    if "licencia" in t_lower:
        return "Licencia"
    if "cumpleaños" in t_lower or "cumpleanos" in t_lower:
        return "Dia de Cumpleaños"
    return "Vacaciones"


def validate_vacaciones_range(start_date, end_date, tipo=None, min_date=None, max_future_days=730):
    """Validaciones puras para solicitud/edición de período de ausencia.

    Returns `(ok: bool, message: str)`.
    - `start_date` / `end_date`: acepta date, datetime o strings ISO / DD/MM/YY(YY).
    - `tipo`: se valida que no esté vacío.
    - `min_date`: date opcional, si es pasado estricto reporta error.
    - `max_future_days`: rango máximo permitido (default 2 años).
    """
    from datetime import date, datetime, timedelta
    import pandas as pd

    def to_date(v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, date):
            return v
        if isinstance(v, (str, bytes)):
            try:
                parsed = pd.to_datetime(v, dayfirst=True, errors="raise")
                if hasattr(parsed, "date"):
                    return parsed.date()
                return None
            except Exception:
                try:
                    parsed2 = pd.to_datetime(v, errors="raise")
                    if hasattr(parsed2, "date"):
                        return parsed2.date()
                except Exception:
                    return None
        return None

    sd = to_date(start_date)
    ed = to_date(end_date)
    if sd is None:
        return False, "Fecha de inicio inválida."
    if ed is None:
        return False, "Fecha de fin inválida."
    if sd > ed:
        return False, "La fecha de inicio no puede ser posterior a la fecha de fin."
    if (ed - sd).days > max_future_days:
        return False, f"El período no puede superar {max_future_days} días."
    if tipo is not None:
        tipo_stripped = (tipo or "").strip()
        if not tipo_stripped:
            return False, "El tipo de período es obligatorio."
    if min_date is not None:
        md = to_date(min_date)
        if md is not None and ed < md:
            return False, "El período finaliza antes de la fecha mínima permitida."
    return True, ""


def vacaciones_count_weekdays(start_date, end_date, feriados=None):
    """Cuenta días hábiles (Lu-Vi) en el rango [start_date, end_date] excluyendo
    los feriados opcionales. 100% pura (feriados es iterable de date/str)."""
    from datetime import date, datetime, timedelta
    import pandas as pd

    def to_date(v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, date):
            return v
        try:
            return pd.to_datetime(v, dayfirst=True, errors="raise").date()
        except Exception:
            try:
                return pd.to_datetime(v, errors="raise").date()
            except Exception:
                return None

    sd = to_date(start_date)
    ed = to_date(end_date)
    if sd is None or ed is None or sd > ed:
        return 0
    feriados_set = set()
    for f in (feriados or []):
        fd = to_date(f)
        if fd is not None:
            feriados_set.add(fd)
    total = 0
    cur = sd
    while cur <= ed:
        if cur.weekday() < 5 and cur not in feriados_set:
            total += 1
        cur += timedelta(days=1)
    return total


def delete_vacaciones(vac_id):
    """Elimina periodo de vacaciones/licencias y sus registros asociados.

    Limpia también todos los cachés de session_state relacionados con registros
    para que la UI no muestre data vieja después del safe_rerun.
    """
    conn = get_connection()
    user_id = None
    start_date = None
    end_date = None
    try:
        c = conn.cursor()

        # 1. Obtener detalles de la vacación antes de borrar
        try:
            c.execute("SELECT usuario_id, fecha_inicio, fecha_fin, tipo FROM vacaciones WHERE id = %s", (vac_id,))
            vac = c.fetchone()
        except Exception:
            conn.rollback()
            c.execute("SELECT usuario_id, fecha_inicio, fecha_fin FROM vacaciones WHERE id = %s", (vac_id,))
            res = c.fetchone()
            if res:
                vac = list(res) + ['vacaciones']
            else:
                vac = None

        if vac:
            user_id, start_date, end_date, tipo = vac

            desc_tipo = vacaciones_tipo_to_desc_tipo(tipo)

            # MISMA lógica que save_vacaciones: hallar el id_tipo EXACTO que se usó
            # para guardar los registros, no un LIKE cualquiera.
            id_tipo = None
            try:
                from .config import DEFAULT_VALUES
                default_tipo_id = None
                try:
                    default_tipo_id = int((DEFAULT_VALUES or {}).get(
                        'TIPO_ID_VACACIONES' if 'Vacaciones' in desc_tipo else
                        'TIPO_ID_LICENCIA' if 'Licencia' in desc_tipo else
                        'TIPO_ID_CUMPLEANOS'
                    ))
                except Exception:
                    default_tipo_id = None
                if default_tipo_id:
                    c.execute("SELECT id_tipo FROM tipos_tarea WHERE id_tipo = %s", (default_tipo_id,))
                    r = c.fetchone()
                    if r:
                        id_tipo = r[0]
            except Exception:
                pass
            if id_tipo is None:
                # Fallback: descripción EXACTA (no LIKE)
                c.execute(
                    "SELECT id_tipo FROM tipos_tarea WHERE TRIM(descripcion) ILIKE TRIM(%s) LIMIT 1",
                    (desc_tipo,),
                )
                r = c.fetchone()
                if r:
                    id_tipo = r[0]

            # Hallar también id_tecnico (igual que save_vacaciones) porque
            # los registros se insertan con ambas FKs (id_tecnico + usuario_id).
            id_tecnico = None
            if user_id:
                c.execute("SELECT nombre, apellido, email FROM usuarios WHERE id = %s", (user_id,))
                res_user = c.fetchone()
                if res_user:
                    u_nom, u_ape, u_email = res_user
                    if u_email:
                        c.execute("SELECT id_tecnico FROM tecnicos WHERE email = %s", (u_email,))
                        r = c.fetchone()
                        if r:
                            id_tecnico = r[0]
                    if id_tecnico is None:
                        c.execute(
                            "SELECT id_tecnico FROM tecnicos WHERE nombre ILIKE %s AND apellido ILIKE %s",
                            (u_nom, u_ape),
                        )
                        r = c.fetchone()
                        if r:
                            id_tecnico = r[0]
                    if id_tecnico is None:
                        full_name = f"{u_nom} {u_ape}"
                        c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre ILIKE %s", (full_name,))
                        r = c.fetchone()
                        if r:
                            id_tecnico = r[0]
                    if id_tecnico is None:
                        c.execute(
                            "SELECT id_tecnico FROM tecnicos WHERE nombre ILIKE %s AND nombre ILIKE %s",
                            (f"%{u_nom}%", f"%{u_ape}%"),
                        )
                        r = c.fetchone()
                        if r:
                            id_tecnico = r[0]

            # 2. Borrar registros asociados con múltiples criterios para cubrir
            #    variaciones históricas (tipos_tarea.id_tipo exacto, descripcion,
            #    tarea_realizada, id_tecnico y/o usuario_id + rango de fechas
            #    CON TOLERANCIA +/- 1 día por desfases de zona horaria / creación).
            fecha_as_date = _parse_registros_fecha_sql("fecha")

            where_clauses = [
                f"{fecha_as_date} >= (%s::date - INTERVAL '1 day')::date",
                f"{fecha_as_date} <= (%s::date + INTERVAL '1 day')::date",
            ]
            params = [start_date, end_date]

            # usuario_id e id_tecnico con OR, no AND (cubre casos históricos
            # donde una de las dos FKs es NULL).
            user_fk_parts = []
            if user_id:
                user_fk_parts.append("usuario_id = %s")
                params.append(user_id)
            if id_tecnico:
                user_fk_parts.append("id_tecnico = %s")
                params.append(id_tecnico)
            if user_fk_parts:
                where_clauses.append(f"({' OR '.join(user_fk_parts)})")

            # Match por id_tipo EXACTO (más confiable, si existe)
            or_sub = []
            if id_tipo is not None:
                or_sub.append("id_tipo = %s")
                params.append(id_tipo)
            # Match por descripcion de ausencia (cubre casos donde el tipo
            # tiene otro nombre ej: "Accesos" pero descripcion="Vacaciones").
            or_sub.append("(descripcion ILIKE %s OR tarea_realizada ILIKE %s)")
            params.extend([f"%{desc_tipo}%", f"%{desc_tipo}%"])

            where_clauses.append(f"({' OR '.join(or_sub)})")

            query = f"DELETE FROM registros WHERE {' AND '.join(where_clauses)}"
            c.execute(query, tuple(params))
            main_deleted = int(getattr(c, 'rowcount', -1) or -1)

            # 2b. FALLBACK HUÉRFANO: eliminar registros en rango +/- 7 días que
            #     matcheen por desc_tipo, incluso si la fecha está fuera del +/-1
            #     o si id_tipo no coincide. Cubrimos casos donde el período fue
            #     creado al día siguiente del registro manual.
            fb_deleted = 0
            try:
                fb_params = []
                fb_where = [
                    f"{fecha_as_date} >= (%s::date - INTERVAL '7 days')::date",
                    f"{fecha_as_date} <= (%s::date + INTERVAL '7 days')::date",
                    "(descripcion ILIKE %s OR tarea_realizada ILIKE %s)",
                ]
                fb_params.extend([start_date, end_date,
                                  f"%{desc_tipo}%", f"%{desc_tipo}%"])
                fb_user_parts = []
                if user_id:
                    fb_user_parts.append("usuario_id = %s")
                    fb_params.append(user_id)
                if id_tecnico:
                    fb_user_parts.append("id_tecnico = %s")
                    fb_params.append(id_tecnico)
                if fb_user_parts:
                    fb_where.append(f"({' OR '.join(fb_user_parts)})")
                fb_query = f"DELETE FROM registros WHERE {' AND '.join(fb_where)}"
                c.execute(fb_query, tuple(fb_params))
                fb_deleted = int(getattr(c, 'rowcount', -1) or -1)
            except Exception as fb_e:
                log_sql_error(f"Warning fallback delete vacaciones huérfanos: {fb_e}")

            # 2c. FALLBACK FINAL: si no se borró NINGÚN registro con los
            #     criterios restrictivos (+/- 1 y +/-7 días con FK de usuario),
            #     borrar CUALQUIER registro en rango +/- 14 días que matchee
            #     por tarea_realizada / descripcion, INDEPENDIENTEMENTE de
            #     usuario_id o id_tecnico. Cubre casos donde las FKs eran NULL
            #     o apuntaban a otro técnico por migraciones.
            if (main_deleted or 0) <= 0 and (fb_deleted or 0) <= 0:
                try:
                    final_params = [start_date, end_date,
                                    f"%{desc_tipo}%", f"%{desc_tipo}%"]
                    final_where = [
                        f"{fecha_as_date} >= (%s::date - INTERVAL '14 days')::date",
                        f"{fecha_as_date} <= (%s::date + INTERVAL '14 days')::date",
                        "(descripcion ILIKE %s OR tarea_realizada ILIKE %s)",
                    ]
                    final_query = (
                        f"DELETE FROM registros WHERE {' AND '.join(final_where)}"
                    )
                    c.execute(final_query, tuple(final_params))
                    final_deleted = int(getattr(c, 'rowcount', -1) or -1)
                except Exception as final_e:
                    log_sql_error(f"Warning final delete vacaciones: {final_e}")

            # Obtener modalidad asociada (antes del delete vacaciones)
            mod_id = None
            try:
                if desc_tipo == 'Vacaciones':
                    mod_id = get_or_create_modalidad_vacaciones(conn)
                else:
                    mod_id = get_or_create_modalidad_generic(desc_tipo, conn)
            except Exception as e:
                log_sql_error(f"Warning get modalidad para delete vacaciones {desc_tipo}: {e}")

        # 3. Borrar la entrada de vacaciones
        c.execute("DELETE FROM vacaciones WHERE id = %s", (vac_id,))
        vac_deleted = int(getattr(c, 'rowcount', -1) or -1)
        conn.commit()

        # 4. Limpiar planificación (user_modalidad_schedule) y restaurar defaults
        try:
            if user_id and start_date and end_date and mod_id:
                c.execute("""
                    DELETE FROM user_modalidad_schedule
                    WHERE user_id = %s
                    AND fecha BETWEEN %s AND %s
                    AND modalidad_id = %s
                """, (user_id, start_date, end_date, mod_id))

                restore_user_defaults_for_range(user_id, start_date, end_date, conn)
                conn.commit()
        except Exception as e:
            log_sql_error(f"Error cleaning planning for vacations: {e}")
            try:
                conn.commit()
            except Exception:
                pass

        # 5. Limpiar TODOS los cachés relacionados a registros del usuario
        #    (incluye week_offset, last_selected_date, cualquier key user_registros_*).
        if user_id:
            try:
                import streamlit as st
                keys_to_drop = []
                for key in st.session_state.keys():
                    if (
                        key == f"user_registros_{user_id}"
                        or key.startswith(f"user_registros_{user_id}_")
                        or key in {"week_offset", "last_selected_date", "chart_data_weekly"}
                        or str(key).startswith("chart_data_")
                    ):
                        keys_to_drop.append(key)
                for k in keys_to_drop:
                    try:
                        del st.session_state[k]
                    except Exception:
                        pass
                try:
                    clear_user_registros_cache(user_id)
                except Exception:
                    pass
            except Exception:
                pass

        return True
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_sql_error(f"Error deleting vacaciones: {e}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass

def update_vacaciones(vac_id, new_start_date, new_end_date, tipo=None, observaciones=None):
    """Actualiza periodo de vacaciones/licencias y regenera registros.

    Si `observaciones` es None se mantiene el valor previo; si es str vacío ("")
    se limpia a NULL (igual que en save_vacaciones).
    """
    if not vac_id:
        return False
    ok_rng, msg_rng = validate_vacaciones_range(
        new_start_date, new_end_date, tipo=tipo if tipo is not None else None
    )
    if not ok_rng:
        raise ValueError(msg_rng or "Rango de período inválido.")
    conn = get_connection()
    try:
        c = conn.cursor()
        
        # 1. Obtener datos actuales de la vacación (para saber qué registros borrar)
        try:
            c.execute("SELECT usuario_id, fecha_inicio, fecha_fin, tipo, observaciones FROM vacaciones WHERE id = %s", (vac_id,))
            vac = c.fetchone()
        except Exception:
            conn.rollback()
            c.execute("SELECT usuario_id, fecha_inicio, fecha_fin, NULL AS observaciones FROM vacaciones WHERE id = %s", (vac_id,))
            res = c.fetchone()
            if res:
                vac = list(res) + ['vacaciones']
            else:
                vac = None
        
        if not vac:
            return False
            
        if len(vac) >= 5:
            user_id, old_start_date, old_end_date, old_tipo, old_observaciones = vac
        else:
            user_id, old_start_date, old_end_date, old_tipo = vac
            old_observaciones = None
        
        # Resolver observaciones objetivo para este update:
        # None → mantener old (comportamiento backward compatible)
        # ""   → limpiar a NULL
        # str  → usarla (stripped)
        if observaciones is None:
            target_observaciones = (str(old_observaciones).strip() if old_observaciones else None) or None
        else:
            target_observaciones = (str(observaciones).strip() if observaciones else None) or None

        # Determinar descripción antigua basada en tipo (helper centralizado)
        old_desc_tipo = vacaciones_tipo_to_desc_tipo(old_tipo)
        
        # 2. Borrar registros asociados al periodo ANTERIOR con los mismos
        #    criterios robustos que delete_vacaciones (+/- 1 día, OR usuario/
        #    tecnico, match por id_tipo o descripcion/tarea_realizada LIKE,
        #    fallback huérfano +/- 7 días).
        c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion ILIKE %s", (f'%{old_desc_tipo}%',))
        tipos_ids = [row[0] for row in c.fetchall()]

        # Hallar id_tecnico para el match de OR con usuario_id
        c.execute("SELECT nombre, apellido, email FROM usuarios WHERE id = %s", (user_id,))
        res_user_upd = c.fetchone()
        id_tecnico_upd = None
        if res_user_upd:
            u_nom_up, u_ape_up, u_email_up = res_user_upd
            if u_email_up:
                c.execute("SELECT id_tecnico FROM tecnicos WHERE email = %s", (u_email_up,))
                r = c.fetchone()
                if r:
                    id_tecnico_upd = r[0]
            if id_tecnico_upd is None and (u_nom_up or u_ape_up):
                full_name_up = f"{u_nom_up} {u_ape_up}"
                c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre ILIKE %s", (full_name_up,))
                r = c.fetchone()
                if r:
                    id_tecnico_upd = r[0]

        fecha_as_date = _parse_registros_fecha_sql("fecha")

        where_upd = [
            f"{fecha_as_date} >= (%s::date - INTERVAL '1 day')::date",
            f"{fecha_as_date} <= (%s::date + INTERVAL '1 day')::date",
        ]
        params_upd = [old_start_date, old_end_date]

        user_fk_upd = []
        if user_id:
            user_fk_upd.append("usuario_id = %s")
            params_upd.append(user_id)
        if id_tecnico_upd:
            user_fk_upd.append("id_tecnico = %s")
            params_upd.append(id_tecnico_upd)
        if user_fk_upd:
            where_upd.append(f"({' OR '.join(user_fk_upd)})")

        or_upd_sub = []
        if tipos_ids:
            placeholders = ','.join(['%s'] * len(tipos_ids))
            or_upd_sub.append(f"id_tipo IN ({placeholders})")
            params_upd.extend(tipos_ids)
        or_upd_sub.append("(descripcion ILIKE %s OR tarea_realizada ILIKE %s)")
        params_upd.extend([f"%{old_desc_tipo}%", f"%{old_desc_tipo}%"])
        where_upd.append(f"({' OR '.join(or_upd_sub)})")

        query = f"DELETE FROM registros WHERE {' AND '.join(where_upd)}"
        c.execute(query, tuple(params_upd))

        # Fallback huérfano +/- 7 días para update (igual que delete)
        try:
            fb2_p = []
            fb2_w = [
                f"{fecha_as_date} >= (%s::date - INTERVAL '7 days')::date",
                f"{fecha_as_date} <= (%s::date + INTERVAL '7 days')::date",
                "(descripcion ILIKE %s OR tarea_realizada ILIKE %s)",
            ]
            fb2_p.extend([old_start_date, old_end_date,
                          f"%{old_desc_tipo}%", f"%{old_desc_tipo}%"])
            fb2_u = []
            if user_id:
                fb2_u.append("usuario_id = %s")
                fb2_p.append(user_id)
            if id_tecnico_upd:
                fb2_u.append("id_tecnico = %s")
                fb2_p.append(id_tecnico_upd)
            if fb2_u:
                fb2_w.append(f"({' OR '.join(fb2_u)})")
            c.execute(f"DELETE FROM registros WHERE {' AND '.join(fb2_w)}", tuple(fb2_p))
        except Exception as fb2_e:
            log_sql_error(f"Warning fallback update vacaciones huérfanos: {fb2_e}")
            
        # 3. Actualizar fechas/tipo/observaciones en tabla vacaciones
        if tipo:
            c.execute(
                "UPDATE vacaciones SET fecha_inicio = %s, fecha_fin = %s, tipo = %s, observaciones = %s WHERE id = %s",
                (new_start_date, new_end_date, tipo, target_observaciones, vac_id)
            )
            target_tipo = tipo
        else:
            c.execute(
                "UPDATE vacaciones SET fecha_inicio = %s, fecha_fin = %s, observaciones = %s WHERE id = %s",
                (new_start_date, new_end_date, target_observaciones, vac_id)
            )
            target_tipo = old_tipo

        # Commit intermedio para asegurar que update de fechas se guarde antes de llamar a save (si fuera reutilizado)
        # Pero aquí vamos a insertar registros manualmente igual que en save_vacaciones
                 
        # 4. Generar nuevos registros para el NUEVO periodo
        
        # Get tecnico_id
        c.execute("SELECT nombre, apellido, email FROM usuarios WHERE id = %s", (user_id,))
        res_user = c.fetchone()
        if res_user:
            u_nom, u_ape, u_email = res_user
            id_tecnico = None
            
            # Estrategia de búsqueda de técnico (simplificada pero robusta)
            if u_email:
                c.execute("SELECT id_tecnico FROM tecnicos WHERE email = %s", (u_email,))
                res = c.fetchone()
                if res: id_tecnico = res[0]
            
            if not id_tecnico:
                 c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre ILIKE %s", (f"{u_nom} {u_ape}",))
                 res = c.fetchone()
                 if res: id_tecnico = res[0]
                 
            if id_tecnico:
                # Get Systemscorp ID
                c.execute("SELECT id_cliente FROM clientes WHERE nombre ILIKE '%Systemscorp%' LIMIT 1")
                res_cli = c.fetchone()
                id_cliente = res_cli[0] if res_cli else 1 
                
                # Determinar descripción nueva basada en tipo (helper centralizado)
                new_desc_tipo = vacaciones_tipo_to_desc_tipo(target_tipo)

                # Get Tipo ID
                id_tipo = get_or_create_tipo_tarea_generic(new_desc_tipo, conn)
                if not id_tipo:
                     id_tipo = get_or_create_tipo_tarea_vacaciones(conn)

                # Get Modality ID
                id_modalidad = get_or_create_modalidad_generic(new_desc_tipo, conn)
                if not id_modalidad:
                     id_modalidad = get_or_create_modalidad_vacaciones(conn)

                # Construir tarea_realizada y descripcion (con observaciones si existen)
                new_reg_label = new_desc_tipo
                if target_observaciones:
                    new_reg_label = f"{new_desc_tipo} — {target_observaciones}"

                # Generate dates
                curr = new_start_date
                while curr <= new_end_date:
                    if curr.weekday() < 5: # Mon-Fri
                        curr_fecha = format_registro_date_iso(curr)
                        # Check duplicate
                        c.execute("""
                            SELECT id FROM registros 
                            WHERE (
                                CASE
                                    WHEN fecha ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN to_date(fecha, 'YYYY-MM-DD')
                                    WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{2}$' THEN to_date(fecha, 'DD/MM/YY')
                                    WHEN fecha ~ '^\\d{2}/\\d{2}/\\d{4}$' THEN to_date(fecha, 'DD/MM/YYYY')
                                    ELSE NULL
                                END
                            ) = %s::date AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s
                        """, (curr_fecha, id_tecnico, id_cliente, id_tipo))
                        
                        if not c.fetchone():
                            c.execute("""
                                INSERT INTO registros (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, numero_ticket, tiempo, mes, usuario_id, grupo, descripcion)
                                VALUES (%s, %s, %s, %s, %s, %s, 'N/A', 8, %s, %s, 'General', %s)
                            """, (curr_fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, new_reg_label, month_name_es(curr.month), user_id, new_reg_label))
                    curr += timedelta(days=1)

        conn.commit()
        
        # 5. Actualizar planificación (user_modalidad_schedule)
        try:
            # Primero limpiamos la planificación vieja
            if old_desc_tipo == 'Vacaciones':
                old_mod_id = get_or_create_modalidad_vacaciones(conn)
            else:
                old_mod_id = get_or_create_modalidad_generic(old_desc_tipo, conn)
                
            if old_mod_id:
                 c.execute("""
                    DELETE FROM user_modalidad_schedule 
                    WHERE user_id = %s 
                    AND fecha BETWEEN %s AND %s 
                    AND modalidad_id = %s
                """, (user_id, old_start_date, old_end_date, old_mod_id))
            
            # Restaurar defaults viejos
            restore_user_defaults_for_range(user_id, old_start_date, old_end_date, conn)
            conn.commit()

            # Ahora insertamos la nueva planificación
            rol_id = get_user_rol_id(user_id)
            if rol_id:
                if id_modalidad:
                    curr = new_start_date
                    while curr <= new_end_date:
                        if curr.weekday() < 5: # Mon-Fri
                            upsert_user_modality_for_date(user_id, rol_id, curr, id_modalidad)
                        curr += timedelta(days=1)
        except Exception as e:
            log_sql_error(f"Error updating planning for vacations: {e}")

        # Limpiar caché de registros para que se actualice la UI inmediatamente
        try:
            clear_user_registros_cache(user_id)
        except:
            pass
            
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def delete_registros_batch(registro_ids):
    """Elimina múltiples registros de horas en una sola transacción"""
    if not registro_ids:
        return True
        
    conn = get_connection()
    try:
        c = conn.cursor()
        
        # Convertir lista a tupla para la query IN
        ids_tuple = tuple(registro_ids)
        
        # Query de eliminación masiva
        query = f"DELETE FROM registros WHERE id IN %s"
        c.execute(query, (ids_tuple,))
        
        deleted_count = c.rowcount
        conn.commit()
        
        return deleted_count
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error deleting batch registros: {e}")
        return -1
    finally:
        conn.close()


def delete_role_safe(rol_id):
    """Elimina un rol/departamento limpiando primero todas las FKs dependientes.

    Devuelve `(ok: bool, mensaje: str)` para que la UI muestre algo user-friendly
    (no un traceback de psycopg2 ForeignKeyViolation).

    Orden de limpieza (toda en la misma transacción, rollback si algo falla):
      1. grupos_roles (asociaciones grupo-rol)
      2. tipos_tarea_roles (asociaciones tipo-tarea → rol) — ESTA era la que
         rompía el bug original: `DELETE FROM roles WHERE id_rol=14` porque
         tipos_tarea_roles tenía referencias.
      3. user_modalidad_schedule (planificación semanal: rol_id FK)
      4. Se ABORTA si hay usuarios con `usuarios.rol_id = rol_id` (no reasignamos
         en automático, lo hacemos manual por seguridad). Para roles individuales
         sin usuarios asignados pasa OK.
      5. DELETE FROM roles
    """
    if not rol_id:
        return False, "ID de rol inválido."
    try:
        rol_id_int = int(rol_id)
    except Exception:
        return False, "ID de rol debe ser numérico."

    conn = get_connection()
    try:
        c = conn.cursor()

        # Ver que exista
        c.execute("SELECT nombre, descripcion FROM roles WHERE id_rol = %s", (rol_id_int,))
        r = c.fetchone()
        if not r:
            return False, "El rol/departamento que intenta eliminar no existe."
        nombre, desc = r

        # 0. Protección extra: roles protegidos SYSTEM_ROLES y prefijos.
        try:
            from .config import SYSTEM_ROLES
            protected = {str(v).strip().lower() for v in (SYSTEM_ROLES or {}).values() if v}
        except Exception:
            protected = set()
        protected |= {"admin", "hipervisor", "visor", "sin_rol", "sin rol"}
        nombre_lower = str(nombre or "").strip().lower()
        desc_str = str(desc or "")
        if nombre_lower in protected or desc_str.startswith("Rol del sistema:"):
            return False, (
                f"No se puede eliminar el rol '{nombre}' porque es un rol protegido del sistema."
            )

        # 1. Verificación de usuarios ANTES de tocar nada (bloqueamos por seguridad)
        c.execute("SELECT COUNT(*) FROM usuarios WHERE rol_id = %s", (rol_id_int,))
        users_count = int(c.fetchone()[0] or 0)
        if users_count > 0:
            return False, (
                f"No se puede eliminar '{nombre}' porque está asignado a {users_count} usuario(s). "
                "Reasignalos primero a otro departamento desde Administrar Usuarios."
            )

        # 2. Limpiar asociaciones de grupos a este rol
        try:
            c.execute("DELETE FROM grupos_roles WHERE id_rol = %s", (rol_id_int,))
        except Exception as gr_e:
            # Algunas instalaciones no tienen grupos_roles; continuar.
            if "no existe la relación" not in str(gr_e).lower() and "does not exist" not in str(gr_e).lower():
                raise gr_e
            conn.rollback()  # reset tx por error
            c = conn.cursor()

        # 3. Limpiar asociaciones de Tipos de Tarea permitidos → este rol
        #    (era la FK que rompía el traceback del error del usuario)
        try:
            c.execute("DELETE FROM tipos_tarea_roles WHERE id_rol = %s", (rol_id_int,))
        except Exception as tt_e:
            if "no existe la relación" not in str(tt_e).lower() and "does not exist" not in str(tt_e).lower():
                raise tt_e
            conn.rollback()
            c = conn.cursor()

        # 4. Limpiar planificación semanal (user_modalidad_schedule.rol_id FK)
        try:
            c.execute("DELETE FROM user_modalidad_schedule WHERE rol_id = %s", (rol_id_int,))
        except Exception as um_e:
            if "no existe la relación" not in str(um_e).lower() and "does not exist" not in str(um_e).lower():
                raise um_e
            conn.rollback()
            c = conn.cursor()

        # 5. Eliminación final del rol
        c.execute("DELETE FROM roles WHERE id_rol = %s", (rol_id_int,))
        deleted = int(getattr(c, 'rowcount', -1) or -1)
        if deleted <= 0:
            conn.rollback()
            return False, (
                f"No se pudo eliminar el rol '{nombre}' (tal vez fue eliminado por otro usuario)."
            )

        conn.commit()

        # Invalidar cachés comunes en planificación / admins
        try:
            from . import admin_planning as _ap
            _ap.cached_get_users_by_rol.clear()
            _ap.cached_get_roles_dataframe.clear()
        except Exception:
            pass

        return True, f"Departamento / rol '{nombre}' eliminado exitosamente (id={rol_id_int})."

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log_sql_error(f"Error delete_role_safe id_rol={rol_id_int}: {e}")
        msg = str(e)
        if "ForeignKeyViolation" in type(e).__name__ or "llave foránea" in msg or "foreign key" in msg.lower():
            return False, (
                "No se puede eliminar el rol porque otras tablas lo siguen referenciando. "
                "Contactar administrador."
            )
        return False, f"Error al eliminar rol: {msg}"
    finally:
        try:
            conn.close()
        except Exception:
            pass

def get_or_create_grupo_with_tecnico_department_association(nombre_grupo, tecnico_nombre, conn=None):
    """Obtiene o crea un grupo por nombre y lo asocia automáticamente al departamento del técnico
    
    Optimizado para:
    - Evitar duplicados usando normalización de texto
    - Solo procesar asociación si es necesario
    - Retornar rápidamente si el grupo ya existe y está asociado
    """
    from .utils import normalize_text
    
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    
    c = conn.cursor()
    try:
        # Buscar grupo existente por nombre normalizado
        c.execute("SELECT id_grupo, nombre FROM grupos")
        grupos = c.fetchall()
        
        nombre_normalizado = normalize_text(nombre_grupo)
        grupo_existente_id = None
        
        # Verificar si ya existe un grupo con nombre normalizado similar
        for grupo_id, grupo_nombre in grupos:
            if normalize_text(grupo_nombre) == nombre_normalizado:
                grupo_existente_id = grupo_id
                break
        
        if grupo_existente_id:
            # El grupo ya existe, verificar si necesita asociación al departamento
            if tecnico_nombre:
                # Obtener departamento del técnico
                departamento = get_departamento_by_tecnico_name(tecnico_nombre, conn)
                if departamento:
                    # Verificar si ya está asociado
                    c.execute("""
                        SELECT COUNT(*) FROM grupos_roles gr
                        JOIN roles r ON gr.id_rol = r.id_rol
                        WHERE gr.id_grupo = %s AND r.nombre = %s
                    """, (grupo_existente_id, departamento))
                    
                    if c.fetchone()[0] == 0:
                        # No está asociado, hacer la asociación
                        asociar_grupo_a_departamento_por_tecnico(grupo_existente_id, tecnico_nombre, conn)
            
            if close_conn:
                conn.close()
            return grupo_existente_id
        
        # Si no existe, crear nuevo grupo
        c.execute("""
            INSERT INTO grupos (nombre, descripcion) 
            VALUES (%s, %s) RETURNING id_grupo
        """, (nombre_grupo, f'Grupo creado automáticamente desde registros: {nombre_grupo}'))
        
        grupo_id = c.fetchone()[0]
        
        # Asociar automáticamente al departamento del técnico
        if tecnico_nombre:
            asociar_grupo_a_departamento_por_tecnico(grupo_id, tecnico_nombre, conn)
        
        conn.commit()
        
        if close_conn:
            conn.close()
        return grupo_id
        
    except Exception as e:
        if close_conn:
            conn.close()
        raise e

def generate_roles_from_nomina():
    """Genera roles desde los cargos únicos en nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Obtener cargos únicos de nómina
        c.execute("SELECT DISTINCT cargo FROM nomina WHERE cargo IS NOT NULL AND cargo != ''")
        cargos = c.fetchall()
        
        # Solo estos roles deben estar ocultos por defecto
        roles_ocultos = ['hipervisor', 'visor']
        
        # Obtener o crear el grupo "General"
        c.execute("SELECT id_grupo FROM grupos WHERE nombre = %s", ('General',))
        general_grupo_result = c.fetchone()
        if not general_grupo_result:
            c.execute("INSERT INTO grupos (nombre, descripcion) VALUES (%s, %s) RETURNING id_grupo",
                     ('General', 'Grupo por defecto para usuarios'))
            general_grupo_id = c.fetchone()[0]
        else:
            general_grupo_id = general_grupo_result[0]
        
        # Mapa de roles existentes normalizados para evitar duplicados
        from .utils import clean_role_name
        c.execute("SELECT id_rol, nombre FROM roles")
        existing_roles_raw = c.fetchall()
        existing_role_map = {} # clean_name -> id_rol
        
        # Primero, aseguramos que los nombres existentes se mapeen en minúsculas y limpios
        for r_id, r_name in existing_roles_raw:
            # 1. Nombre original
            existing_role_map[r_name] = r_id
            
            # 2. Nombre en minúsculas
            existing_role_map[r_name.lower()] = r_id
            
            # 3. Nombre "limpio" (snake_case)
            cleaned = clean_role_name(r_name)
            if cleaned:
                existing_role_map[cleaned] = r_id
        
        stats = {
            'total_cargos': len(cargos),
            'roles_creados': 0,
            'nuevos_roles': [],
            'errores': []
        }
        
        # Mapeos específicos solicitados por el usuario
        ROLE_RENAMES = {
            'comercial': 'dpto_comercial',
            'tecnico': 'dpto_tecnico',
            'administracion': 'dpto_administracion',
        }
        
        for cargo_tuple in cargos:
            cargo = cargo_tuple[0]
            try:
                # 1. Limpiar el cargo de nómina (ej. "Comercial" -> "comercial")
                # clean_role_name devuelve snake_case (ej. adm_comercial)
                cargo_limpio = clean_role_name(cargo)
                
                # Roles ignorados
                if not cargo_limpio or cargo_limpio in ['admin', 'sin_rol', 'sin rol', 'hipervisor', 'general', 'visor']:
                    continue
                
                # 2. Aplicar renombres preferidos
                # Si es "comercial" -> "dpto_comercial"
                base_name = ROLE_RENAMES.get(cargo_limpio, cargo_limpio)
                
                # Asegurar snake_case y minúsculas (Defensa en profundidad)
                base_name = base_name.lower().strip().replace(' ', '_')
                
                # 3. Normalizar base_name para evitar prefijos dobles
                # Si base_name es "adm_comercial", NO debemos permitir que se convierta en "adm_adm_comercial"
                # Pero si base_name es "adm_administracion", es correcto que sea administrativo.
                
                # Determinar view_type
                if base_name.startswith('dpto_'):
                    view_type = base_name.replace('dpto_', '')
                elif base_name.startswith('adm_'):
                    view_type = base_name.replace('adm_', 'admin_')
                else:
                    view_type = base_name
                
                # --- GESTIONAR ROL BASE ---
                # Verificamos contra el mapa de existentes (que incluye lowercase y clean_name)
                if base_name not in existing_role_map and base_name.lower() not in existing_role_map:
                    is_hidden = cargo in roles_ocultos
                    
                    c.execute("""
                        INSERT INTO roles (nombre, descripcion, is_hidden, view_type) 
                        VALUES (%s, %s, %s, %s) 
                        RETURNING id_rol
                    """, (base_name, f"Rol generado automáticamente para el cargo: {cargo}", is_hidden, view_type))
                    new_role_id = c.fetchone()[0]
                    
                    # Actualizar mapa inmediatamente
                    existing_role_map[base_name] = new_role_id
                    existing_role_map[base_name.lower()] = new_role_id
                    
                    # Asociar al grupo General
                    try:
                        c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (%s, %s)", 
                                 (general_grupo_id, new_role_id))
                    except: pass
                    
                    stats['roles_creados'] += 1
                    stats['nuevos_roles'].append(base_name)
                
                # --- GESTIONAR ROL ADMINISTRATIVO ---
                # Si el rol base YA empieza con adm_, NO creamos otro administrativo
                if not base_name.startswith('adm_'):
                    # Construir nombre admin esperado
                    if base_name.startswith('dpto_'):
                         core_name = base_name.replace('dpto_', '')
                    else:
                         core_name = base_name
                         
                    # Evitar doble prefijo si core_name ya tiene adm_ (caso raro)
                    if core_name.startswith('adm_'):
                        core_name = core_name.replace('adm_', '')
                         
                    admin_name = f"adm_{core_name}"
                    admin_view_type = f"admin_{core_name}"
                    
                    # Verificar si existe (check map)
                    if admin_name not in existing_role_map and admin_name.lower() not in existing_role_map:
                        c.execute("""
                            INSERT INTO roles (nombre, descripcion, is_hidden, view_type)
                            VALUES (%s, %s, %s, %s)
                            RETURNING id_rol
                        """, (admin_name, f"Rol administrativo para {base_name}", False, admin_view_type))
                        new_admin_id = c.fetchone()[0]
                        
                        existing_role_map[admin_name] = new_admin_id
                        existing_role_map[admin_name.lower()] = new_admin_id
                        
                        try:
                            c.execute("INSERT INTO grupos_roles (id_grupo, id_rol) VALUES (%s, %s)", 
                                     (general_grupo_id, new_admin_id))
                        except: pass
                        
                        stats['roles_creados'] += 1
                        stats['nuevos_roles'].append(admin_name)
                    
            except Exception as e:
                error_msg = f"Error creando rol para cargo {cargo}: {str(e)}"
                stats['errores'].append(error_msg)
                log_sql_error(e, error_msg)
        
        conn.commit()
        return stats
        
    except Exception as e:
        log_sql_error(e, f"Error en generate_roles_from_nomina: {e}")
        return {
            'total_cargos': 0,
            'roles_creados': 0,
            'nuevos_roles': [],
            'errores': [str(e)]
        }
    finally:
        conn.close()

def generate_grupos_from_nomina():
    """Genera grupos desde los equipos únicos en nómina"""
    conn = get_connection()
    c = conn.cursor()
    try:
        # Obtener equipos únicos de nómina (usando el campo grupo que mapea tanto Sector como Equipo)
        c.execute("SELECT DISTINCT grupo FROM nomina WHERE grupo IS NOT NULL AND grupo != ''")
        equipos = c.fetchall()
        
        stats = {
            'total_equipos': len(equipos),
            'grupos_creados': 0,
            'nuevos_grupos': [],
            'errores': []
        }
        
        for equipo_tuple in equipos:
            equipo = equipo_tuple[0]
            try:
                # Verificar si el grupo ya existe
                c.execute("SELECT id_grupo FROM grupos WHERE nombre = %s", (equipo,))
                if not c.fetchone():
                    # Crear el grupo
                    c.execute("INSERT INTO grupos (nombre, descripcion) VALUES (%s, %s)",
                             (equipo, f"Grupo generado automáticamente para el equipo: {equipo}"))
                    stats['grupos_creados'] += 1
                    stats['nuevos_grupos'].append(equipo)
                    
            except Exception as e:
                error_msg = f"Error creando grupo para equipo {equipo}: {str(e)}"
                stats['errores'].append(error_msg)
                log_sql_error(e, error_msg)
        
        conn.commit()
        
        if stats['grupos_creados'] > 0:
            print(f"✅ {stats['grupos_creados']} grupos creados automáticamente desde equipos")
        
        return stats
        
    except Exception as e:
        log_sql_error(e, f"Error en generate_grupos_from_nomina: {e}")
        return {
            'total_equipos': 0,
            'grupos_creados': 0,
            'nuevos_grupos': [],
            'errores': [str(e)]
        }
    finally:
        conn.close()

def toggle_contacto_favorito(user_id, contacto_id):
    """Alterna el estado de favorito de un contacto para un usuario"""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS contactos_favoritos (
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                contacto_id INTEGER NOT NULL REFERENCES contactos(id_contacto) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, contacto_id)
            )
        """)
        
        c.execute("SELECT 1 FROM contactos_favoritos WHERE user_id = %s AND contacto_id = %s", (user_id, contacto_id))
        exists = c.fetchone()
        
        if exists:
            c.execute("DELETE FROM contactos_favoritos WHERE user_id = %s AND contacto_id = %s", (user_id, contacto_id))
            is_fav = False
        else:
            c.execute("INSERT INTO contactos_favoritos (user_id, contacto_id) VALUES (%s, %s)", (user_id, contacto_id))
            is_fav = True
            
        conn.commit()
        return is_fav
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error toggling favorite contact: {e}")
        return False
    finally:
        conn.close()

def get_contactos_favoritos(user_id):
    """Devuelve una lista de IDs de contactos favoritos para un usuario"""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS contactos_favoritos (
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                contacto_id INTEGER NOT NULL REFERENCES contactos(id_contacto) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, contacto_id)
            )
        """)
        c.execute("SELECT contacto_id FROM contactos_favoritos WHERE user_id = %s", (user_id,))
        rows = c.fetchall()
        return [r[0] for r in rows]
    except Exception as e:
        log_sql_error(f"Error getting favorite contacts: {e}")
        return []
    finally:
        conn.close()

def log_contacto_reciente(user_id, contacto_id):
    """Registra o actualiza el acceso reciente a un contacto"""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS contactos_recientes (
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                contacto_id INTEGER NOT NULL REFERENCES contactos(id_contacto) ON DELETE CASCADE,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, contacto_id)
            )
        """)
        
        c.execute("SELECT 1 FROM contactos_recientes WHERE user_id = %s AND contacto_id = %s", (user_id, contacto_id))
        if c.fetchone():
             c.execute("UPDATE contactos_recientes SET accessed_at = CURRENT_TIMESTAMP WHERE user_id = %s AND contacto_id = %s", (user_id, contacto_id))
        else:
             c.execute("INSERT INTO contactos_recientes (user_id, contacto_id) VALUES (%s, %s)", (user_id, contacto_id))
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error logging recent contact: {e}")
        return False
    finally:
        conn.close()

def get_contactos_recientes(user_id, limit=5):
    """Devuelve una lista de IDs de contactos recientes para un usuario"""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS contactos_recientes (
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                contacto_id INTEGER NOT NULL REFERENCES contactos(id_contacto) ON DELETE CASCADE,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, contacto_id)
            )
        """)
        c.execute("""
            SELECT contacto_id FROM contactos_recientes 
            WHERE user_id = %s 
            ORDER BY accessed_at DESC 
            LIMIT %s
        """, (user_id, limit))
        rows = c.fetchall()
        return [r[0] for r in rows]
    except Exception as e:
        log_sql_error(f"Error getting recent contacts: {e}")
        return []
    finally:
        conn.close()

def ensure_clientes_favoritos_exists(conn=None):
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS clientes_favoritos (
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                cliente_id INTEGER NOT NULL REFERENCES clientes(id_cliente) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, cliente_id)
            )
        """)
        conn.commit()
    finally:
        if close_conn:
            conn.close()

def toggle_cliente_favorito(user_id, cliente_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        ensure_clientes_favoritos_exists(conn)
        c.execute(
            "SELECT 1 FROM clientes_favoritos WHERE user_id = %s AND cliente_id = %s",
            (int(user_id), int(cliente_id))
        )
        exists = c.fetchone()
        if exists:
            c.execute(
                "DELETE FROM clientes_favoritos WHERE user_id = %s AND cliente_id = %s",
                (int(user_id), int(cliente_id))
            )
            is_fav = False
        else:
            c.execute(
                "INSERT INTO clientes_favoritos (user_id, cliente_id) VALUES (%s, %s)",
                (int(user_id), int(cliente_id))
            )
            is_fav = True
        conn.commit()
        return is_fav
    except Exception as e:
        conn.rollback()
        log_sql_error(f"Error toggling favorite client: {e}")
        return False
    finally:
        conn.close()

def get_clientes_favoritos(user_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        ensure_clientes_favoritos_exists(conn)
        c.execute("SELECT cliente_id FROM clientes_favoritos WHERE user_id = %s", (int(user_id),))
        rows = c.fetchall()
        return [int(r[0]) for r in rows]
    except Exception as e:
        log_sql_error(f"Error getting favorite clients: {e}")
        return []
    finally:
        conn.close()


def ensure_google_calendar_schema():
    """Asegura que exista la tabla para la configuración de Google Calendar"""
    conn = get_connection()
    try:
        conn.autocommit = True
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS google_calendar_config (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER REFERENCES usuarios(id) ON DELETE SET NULL
            )
        ''')
    except Exception as e:
        log_sql_error(f"Error asegurando esquema de Google Calendar: {e}")
    finally:
        conn.close()


def get_google_calendar_config(key: str) -> dict | None:
    """Obtiene un valor de configuración de Google Calendar"""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT value FROM google_calendar_config WHERE key = %s", (key,))
        row = c.fetchone()
        if row:
            import json
            return json.loads(row[0])
    except Exception as e:
        log_sql_error(f"Error obteniendo config de Google Calendar para '{key}': {e}")
    finally:
        conn.close()
    return None


def save_google_calendar_config(key: str, value: dict, user_id: int | None = None) -> bool:
    """Guarda o actualiza un valor de configuración de Google Calendar"""
    ensure_google_calendar_schema()
    conn = get_connection()
    try:
        import json
        value_str = json.dumps(value)
        c = conn.cursor()
        c.execute("""
            INSERT INTO google_calendar_config (key, value, updated_at, updated_by)
            VALUES (%s, %s, CURRENT_TIMESTAMP, %s)
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = EXCLUDED.updated_by
        """, (key, value_str, user_id))
        conn.commit()
        return True
    except Exception as e:
        log_sql_error(f"Error guardando config de Google Calendar para '{key}': {e}")
        return False
    finally:
        conn.close()


def delete_google_calendar_config(key: str) -> bool:
    """Elimina un valor de configuración de Google Calendar"""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM google_calendar_config WHERE key = %s", (key,))
        conn.commit()
        return True
    except Exception as e:
        log_sql_error(f"Error eliminando config de Google Calendar para '{key}': {e}")
        return False
    finally:
        conn.close()


def get_google_calendar_status() -> dict:
    """Obtiene el estado actual de la configuración de Google Calendar"""
    conn = get_connection()
    status = {
        'configured': False,
        'credentials_uploaded': False,
        'credentials_date': None,
        'credentials_user': None,
        'token_valid': False,
        'token_date': None,
    }
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("""
            SELECT g.key, g.updated_at, u.username as user_name
            FROM google_calendar_config g
            LEFT JOIN usuarios u ON g.updated_by = u.id
        """)
        rows = c.fetchall()
        for row in rows:
            if row['key'] == 'client_credentials':
                status['credentials_uploaded'] = True
                status['credentials_date'] = row['updated_at']
                status['credentials_user'] = row['user_name']
            elif row['key'] == 'oauth_token':
                status['token_valid'] = True
                status['token_date'] = row['updated_at']
        status['configured'] = status['credentials_uploaded'] and status['token_valid']
    except Exception as e:
        log_sql_error(f"Error al obtener estado de Google Calendar: {e}")
    finally:
        conn.close()
    return status

