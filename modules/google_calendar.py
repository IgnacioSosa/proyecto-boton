"""
Servicio de integración con la API de Google Calendar v3.

Nota: las dependencias google-auth / google-api-python-client son opcionales.
Si no están instaladas el módulo igual importa correctamente, marca
google_calendar_available = False y expone stubs de las funciones públicas que
devolverán None/False mostrando un warning por logging. Así la app no crashea
en entornos sin estas librerías.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from .database import get_google_calendar_config, save_google_calendar_config, delete_google_calendar_config
from .logging_utils import log_app_error

logger = logging.getLogger(__name__)

_GOOGLE_AUTH_MODULES = None
google_calendar_available = False


def _ensure_google_deps():
    """Carga de forma lazy las dependencias de Google (si están instaladas).

    Retorna True si están disponibles, False en caso contrario.
    """
    global _GOOGLE_AUTH_MODULES, google_calendar_available
    if _GOOGLE_AUTH_MODULES is not None:
        return google_calendar_available
    try:
        from google.auth.transport.requests import Request  # noqa: F401
        from google.oauth2.credentials import Credentials  # noqa: F401
        from google_auth_oauthlib.flow import Flow  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
        from googleapiclient.errors import HttpError  # noqa: F401

        _GOOGLE_AUTH_MODULES = {
            "Request": Request,
            "Credentials": Credentials,
            "Flow": Flow,
            "build": build,
            "HttpError": HttpError,
        }
        google_calendar_available = True
    except Exception as exc:  # pragma: no cover - entorno sin dependencias
        logger.warning(
            "Google Calendar no disponible: faltan dependencias google-auth/google-api-python-client. "
            "Error original: %s",
            exc,
        )
        _GOOGLE_AUTH_MODULES = False
        google_calendar_available = False
    return google_calendar_available


def _require_google(caller: str):
    if not _ensure_google_deps():
        logger.warning(
            "%s omitido: dependencias de Google Calendar no instaladas. "
            "Instalar con: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client",
            caller,
        )
        return None
    return _GOOGLE_AUTH_MODULES


def _google_requests():
    return _require_google("_google_requests")


# Scope requerido para leer y escribir en calendarios
SCOPES = ['https://www.googleapis.com/auth/calendar']
OAUTH_STATE_KEY = 'oauth_pending_state'
OAUTH_STATE_TTL_SECONDS = 600


def _normalize_query_param(value):
    """Normaliza parámetros de URL que Streamlit puede devolver como lista."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def save_oauth_state(state: str, user_id: int | None = None, code_verifier: str | None = None) -> bool:
    """Persiste el state OAuth y el code_verifier PKCE en BD para sobrevivir al redirect."""
    payload = {
        "state": state,
        "user_id": user_id,
        "code_verifier": code_verifier,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return save_google_calendar_config(OAUTH_STATE_KEY, payload, user_id)


def validate_oauth_state(state: str) -> dict | None:
    """
    Valida el state recibido en el callback contra el almacenado en BD.
    Retorna el payload guardado si es válido y no expiró; None en caso contrario.
    """
    saved = get_google_calendar_config(OAUTH_STATE_KEY)
    if not saved or not isinstance(saved, dict):
        return None
    if saved.get("state") != state:
        return None

    created_at_str = saved.get("created_at")
    if created_at_str:
        try:
            created_at = datetime.fromisoformat(created_at_str)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - created_at > timedelta(seconds=OAUTH_STATE_TTL_SECONDS):
                return None
        except ValueError:
            pass

    return saved


def clear_oauth_state() -> None:
    """Elimina el state OAuth pendiente tras usarlo o ante un error."""
    delete_google_calendar_config(OAUTH_STATE_KEY)

def get_oauth_flow(redirect_uri: str, state: str = None, code_verifier: str = None):
    """
    Construye el flujo de OAuth 2.0 a partir de las credenciales cargadas de la base de datos.
    """
    deps = _require_google("get_oauth_flow")
    if deps is None:
        return None
    Flow = deps["Flow"]
    client_config = get_google_calendar_config('client_credentials')
    if not client_config:
        return None
    try:
        flow = Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            state=state,
            code_verifier=code_verifier,
            autogenerate_code_verifier=code_verifier is None,
        )
        flow.redirect_uri = redirect_uri
        return flow
    except Exception as e:
        log_app_error(e, module="google_calendar", function="get_oauth_flow")
        return None


def build_oauth_authorization_url(redirect_uri: str, user_id: int | None = None) -> str | None:
    """
    Genera la URL de autorización de Google y persiste state + code_verifier PKCE en BD.
    Reutiliza un flujo pendiente válido tanto en st.session_state como en BD para evitar
    invalidar el state en cada rerun de Streamlit.
    """
    import uuid
    import streamlit as st

    session_cache_key = "google_calendar_oauth_pending"
    cached = st.session_state.get(session_cache_key)
    if cached and isinstance(cached, dict):
        cached_state = cached.get("state")
        cached_verifier = cached.get("code_verifier")
        cached_url = cached.get("auth_url")
        if cached_state and cached_verifier and cached_url and validate_oauth_state(cached_state):
            return cached_url

    saved = get_google_calendar_config(OAUTH_STATE_KEY)
    if saved and saved.get("state") and saved.get("code_verifier"):
        if validate_oauth_state(saved["state"]):
            flow = get_oauth_flow(
                redirect_uri,
                state=saved["state"],
                code_verifier=saved["code_verifier"],
            )
            if flow:
                auth_url, _ = flow.authorization_url(prompt='select_account', access_type='offline')
                st.session_state[session_cache_key] = {
                    "state": saved["state"],
                    "code_verifier": saved["code_verifier"],
                    "auth_url": auth_url,
                }
                return auth_url

    oauth_state = str(uuid.uuid4())
    flow = get_oauth_flow(redirect_uri, state=oauth_state)
    if not flow:
        return None

    auth_url, _ = flow.authorization_url(prompt='select_account', access_type='offline')
    save_oauth_state(oauth_state, user_id=user_id, code_verifier=flow.code_verifier)
    st.session_state[session_cache_key] = {
        "state": oauth_state,
        "code_verifier": flow.code_verifier,
        "auth_url": auth_url,
    }
    return auth_url

def get_credentials(user_id: int | None = None):
    """
    Carga las credenciales de la base de datos y renueva automáticamente el token si ha expirado.
    Actualiza la base de datos con el nuevo token tras la renovación.
    """
    deps = _require_google("get_credentials")
    if deps is None:
        return None
    Credentials = deps["Credentials"]
    Request = deps["Request"]

    token_info = get_google_calendar_config('oauth_token')
    client_config = get_google_calendar_config('client_credentials')
    
    if not client_config:
        return None
        
    creds = None
    if token_info:
        try:
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
        except Exception as e:
            log_app_error(e, module="google_calendar", function="get_credentials_load_token")
            return None
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Guardar el nuevo token renovado de forma segura en la base de datos
                token_data = json.loads(creds.to_json())
                save_google_calendar_config('oauth_token', token_data, user_id)
            except Exception as e:
                log_app_error(e, module="google_calendar", function="get_credentials_refresh")
                return None
        else:
            return None
            
    return creds

def get_calendar_service(user_id: int | None = None):
    """
    Construye y retorna el servicio cliente de Google Calendar.
    """
    deps = _require_google("get_calendar_service")
    if deps is None:
        return None
    build = deps["build"]
    creds = get_credentials(user_id)
    if not creds:
        return None
    try:
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        log_app_error(e, module="google_calendar", function="get_calendar_service")
        return None

def get_user_calendar(calendar_id: str = 'primary', user_id: int | None = None) -> dict:
    """
    Obtiene los metadatos del calendario del usuario autenticado.
    """
    deps = _require_google("get_user_calendar")
    HttpError = deps["HttpError"] if deps else None
    service = get_calendar_service(user_id)
    if not service:
        raise ValueError("Google Calendar no está configurado o autorizado.")
    try:
        return service.calendars().get(calendarId=calendar_id).execute()
    except HttpError as e:
        log_app_error(e, module="google_calendar", function="get_user_calendar")
        raise Exception(f"Error de Google Calendar API: {e.reason}")
    except Exception as e:
        log_app_error(e, module="google_calendar", function="get_user_calendar")
        raise

def check_availability(start_time: datetime, end_time: datetime, calendar_id: str = 'primary', user_id: int | None = None) -> dict:
    """
    Consulta la disponibilidad de eventos (freebusy) en un rango de tiempo.
    """
    deps = _require_google("check_availability")
    HttpError = deps["HttpError"] if deps else None
    service = get_calendar_service(user_id)
    if not service:
        raise ValueError("Google Calendar no está configurado o autorizado.")
        
    try:
        start_iso = start_time.isoformat() + 'Z' if not start_time.isoformat().endswith('Z') else start_time.isoformat()
        end_iso = end_time.isoformat() + 'Z' if not end_time.isoformat().endswith('Z') else end_time.isoformat()
        
        body = {
            "timeMin": start_iso,
            "timeMax": end_iso,
            "items": [{"id": calendar_id}]
        }
        
        return service.freebusy().query(body=body).execute()
    except HttpError as e:
        log_app_error(e, module="google_calendar", function="check_availability")
        raise Exception(f"Error de disponibilidad de Google: {e.reason}")
    except Exception as e:
        log_app_error(e, module="google_calendar", function="check_availability")
        raise

def get_events(start_time: datetime = None, end_time: datetime = None, max_results: int = 10, calendar_id: str = 'primary', user_id: int | None = None) -> list:
    """
    Obtiene los eventos registrados en el calendario en el rango especificado.
    """
    deps = _require_google("get_events")
    HttpError = deps["HttpError"] if deps else None
    service = get_calendar_service(user_id)
    if not service:
        raise ValueError("Google Calendar no está configurado o autorizado.")
        
    try:
        time_min = None
        if start_time:
            time_min = start_time.isoformat() + 'Z' if not start_time.isoformat().endswith('Z') else start_time.isoformat()
            
        time_max = None
        if end_time:
            time_max = end_time.isoformat() + 'Z' if not end_time.isoformat().endswith('Z') else end_time.isoformat()
            
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        return events_result.get('items', [])
    except HttpError as e:
        log_app_error(e, module="google_calendar", function="get_events")
        raise Exception(f"Error al obtener eventos de Google: {e.reason}")
    except Exception as e:
        log_app_error(e, module="google_calendar", function="get_events")
        raise

def create_event(event_data: dict, calendar_id: str = 'primary', user_id: int | None = None) -> dict:
    """
    Crea un nuevo evento en el calendario.
    """
    deps = _require_google("create_event")
    HttpError = deps["HttpError"] if deps else None
    service = get_calendar_service(user_id)
    if not service:
        raise ValueError("Google Calendar no está configurado o autorizado.")
        
    try:
        return service.events().insert(calendarId=calendar_id, body=event_data).execute()
    except HttpError as e:
        log_app_error(e, module="google_calendar", function="create_event")
        raise Exception(f"Error al crear evento en Google: {e.reason}")
    except Exception as e:
        log_app_error(e, module="google_calendar", function="create_event")
        raise

def update_event(event_id: str, event_data: dict, calendar_id: str = 'primary', user_id: int | None = None) -> dict:
    """
    Modifica un evento existente en el calendario.
    """
    deps = _require_google("update_event")
    HttpError = deps["HttpError"] if deps else None
    service = get_calendar_service(user_id)
    if not service:
        raise ValueError("Google Calendar no está configurado o autorizado.")
        
    try:
        return service.events().update(calendarId=calendar_id, eventId=event_id, body=event_data).execute()
    except HttpError as e:
        log_app_error(e, module="google_calendar", function="update_event")
        raise Exception(f"Error al modificar evento en Google: {e.reason}")
    except Exception as e:
        log_app_error(e, module="google_calendar", function="update_event")
        raise

def delete_event(event_id: str, calendar_id: str = 'primary', user_id: int | None = None) -> None:
    """
    Elimina un evento del calendario.
    """
    deps = _require_google("delete_event")
    HttpError = deps["HttpError"] if deps else None
    service = get_calendar_service(user_id)
    if not service:
        raise ValueError("Google Calendar no está configurado o autorizado.")
        
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    except HttpError as e:
        log_app_error(e, module="google_calendar", function="delete_event")
        raise Exception(f"Error al eliminar evento en Google: {e.reason}")
    except Exception as e:
        log_app_error(e, module="google_calendar", function="delete_event")
        raise

def handle_oauth_callback():
    """
    Intercepta y procesa el callback de redirección OAuth de Google.
    Intercambia el código de autorización por tokens de acceso y actualización,
    guardando el resultado en la base de datos, limpiando la URL y volviendo a cargar.
    """
    import streamlit as st
    import time
    from .database import get_user_info_safe
    from .utils import safe_rerun

    qp = st.query_params
    code = _normalize_query_param(qp.get('code'))
    state = _normalize_query_param(qp.get('state'))

    if not code or not state:
        return

    notice_key = "google_calendar_callback_notice"
    saved_payload = validate_oauth_state(state)
    if not saved_payload:
        clear_oauth_state()
        st.session_state.pop("google_calendar_oauth_pending", None)
        st.session_state[notice_key] = {
            "level": "error",
            "message": "❌ Error de seguridad: el parámetro de estado (state) de OAuth no coincide o expiró. Vuelva a intentar la vinculación.",
        }
    else:
        user_id = st.session_state.get('user_id') or saved_payload.get('user_id')
        user_info = get_user_info_safe(user_id) if user_id else None
        if not user_info or not user_info.get('is_admin'):
            clear_oauth_state()
            st.session_state.pop("google_calendar_oauth_pending", None)
            st.session_state[notice_key] = {
                "level": "error",
                "message": "❌ Solo un administrador puede vincular Google Calendar.",
            }
        elif not saved_payload.get('code_verifier'):
            clear_oauth_state()
            st.session_state.pop("google_calendar_oauth_pending", None)
            st.session_state[notice_key] = {
                "level": "error",
                "message": "❌ La sesión de autorización expiró. Vuelva a hacer clic en «Vincular Cuenta de Google».",
            }
        else:
            try:
                host = st.context.headers.get("host", "localhost:8501")
                proto = st.context.headers.get("x-forwarded-proto", "http")
                redirect_uri = f"{proto}://{host}/"

                flow = get_oauth_flow(
                    redirect_uri,
                    state=state,
                    code_verifier=saved_payload.get('code_verifier'),
                )
                if flow:
                    flow.fetch_token(code=code)
                    credentials = flow.credentials
                    token_data = json.loads(credentials.to_json())

                    if save_google_calendar_config('oauth_token', token_data, user_id):
                        clear_oauth_state()
                        st.session_state.pop('google_calendar_oauth_state', None)
                        st.session_state.pop("google_calendar_oauth_pending", None)
                        st.session_state[notice_key] = {
                            "level": "success",
                            "message": "✅ ¡Google Calendar autorizado y vinculado con éxito!",
                        }
                    else:
                        st.session_state[notice_key] = {
                            "level": "error",
                            "message": "❌ Error al guardar el token de Google Calendar en la base de datos.",
                        }
                else:
                    st.session_state[notice_key] = {
                        "level": "error",
                        "message": "❌ No se pudo iniciar el flujo de autenticación. Verifique las credenciales de cliente.",
                    }
            except Exception as e:
                log_app_error(e, module="google_calendar", function="handle_oauth_callback")
                st.session_state[notice_key] = {
                    "level": "error",
                    "message": f"❌ Error al completar la autorización de Google Calendar: {str(e)}",
                }

    st.query_params.clear()
    st.query_params["adm_main"] = "admin"
    st.query_params["admin_active_tab"] = "⚙️ Google Calendar"
    safe_rerun()


# Auto-detección de dependencias al importar el módulo (una sola vez).
# Si están instaladas: google_calendar_available = True.
# Si faltan: google_calendar_available = False y warning por logger.
_ensure_google_deps()
