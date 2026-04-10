"""
Configuración centralizada de la aplicación
"""
import base64
import json
import os
from dotenv import load_dotenv

# Cargar variables de entorno
ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(dotenv_path=ENV_PATH)

def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'si', 'on')

def _env_multiline(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).replace("\\n", "\n")

def encode_env_multiline(value: str) -> str:
    return str(value or '').replace('\r\n', '\n').replace('\n', '\\n')

DEFAULT_NOTIFICATION_TEMPLATE_BODY = (
    "Hola {nombre},\n\n"
    "Tienes una nueva notificación en SIGO.\n\n"
    "Detalle: {detalle}\n\n"
    "Saludos,\n"
    "{empresa}"
)

NOTIFICATION_TEMPLATE_DEFINITIONS = {
    'default': {
        'label': 'Plantilla por defecto',
        'description': 'Se usa como respaldo cuando un evento no tiene una plantilla específica.',
        'placeholders': ['{nombre}', '{usuario}', '{email}', '{evento}', '{detalle}', '{fecha}', '{empresa}'],
        'subject': 'Nueva notificación de SIGO',
        'body': DEFAULT_NOTIFICATION_TEMPLATE_BODY,
    },
    'cliente_solicitud_creada': {
        'label': 'Solicitud de cliente creada',
        'description': 'Aviso para revisión de una nueva solicitud de cliente.',
        'placeholders': ['{nombre}', '{solicitante}', '{cliente}', '{cuit}', '{telefono}', '{detalle}', '{fecha}', '{empresa}'],
        'subject': 'Nueva solicitud de cliente: {cliente}',
        'body': (
            "Hola {nombre},\n\n"
            "{solicitante} registró una nueva solicitud de cliente en SIGO.\n\n"
            "Cliente: {cliente}\n"
            "CUIT: {cuit}\n"
            "Teléfono: {telefono}\n"
            "Detalle: {detalle}\n"
            "Fecha: {fecha}\n\n"
            "Saludos,\n"
            "{empresa}"
        ),
    },
    'cliente_solicitud_aprobada': {
        'label': 'Solicitud de cliente aprobada',
        'description': 'Confirma al solicitante que su cliente fue aprobado.',
        'placeholders': ['{nombre}', '{cliente}', '{aprobador}', '{fecha}', '{detalle}', '{empresa}'],
        'subject': 'Solicitud aprobada: {cliente}',
        'body': (
            "Hola {nombre},\n\n"
            "La solicitud del cliente {cliente} fue aprobada.\n\n"
            "Aprobador: {aprobador}\n"
            "Fecha: {fecha}\n"
            "Detalle: {detalle}\n\n"
            "Saludos,\n"
            "{empresa}"
        ),
    },
    'cliente_solicitud_rechazada': {
        'label': 'Solicitud de cliente rechazada',
        'description': 'Informa al solicitante que su alta fue rechazada.',
        'placeholders': ['{nombre}', '{cliente}', '{aprobador}', '{fecha}', '{detalle}', '{empresa}'],
        'subject': 'Solicitud rechazada: {cliente}',
        'body': (
            "Hola {nombre},\n\n"
            "La solicitud del cliente {cliente} fue rechazada.\n\n"
            "Revisó: {aprobador}\n"
            "Fecha: {fecha}\n"
            "Detalle: {detalle}\n\n"
            "Saludos,\n"
            "{empresa}"
        ),
    },
    'dia_pendiente_carga': {
        'label': 'Día pendiente de carga',
        'description': 'Resumen operativo de días con carga incompleta para un usuario.',
        'placeholders': ['{nombre}', '{usuario}', '{periodo}', '{cantidad_alertas}', '{resumen_alertas}', '{detalle}', '{fecha}', '{empresa}'],
        'subject': 'Carga incompleta detectada: {cantidad_alertas} día(s) pendiente(s)',
        'body': (
            "Hola {nombre},\n\n"
            "Detectamos días con carga incompleta en {periodo}.\n\n"
            "Cantidad de alertas: {cantidad_alertas}\n"
            "Detalle:\n"
            "{resumen_alertas}\n\n"
            "Observación: {detalle}\n"
            "Fecha de envío: {fecha}\n\n"
            "Saludos,\n"
            "{empresa}"
        ),
    },
    'trato_por_vencer': {
        'label': 'Trato por vencer',
        'description': 'Recordatorio previo al vencimiento de un trato comercial.',
        'placeholders': ['{nombre}', '{trato}', '{cliente}', '{fecha_cierre}', '{dias_restantes}', '{estado}', '{empresa}'],
        'subject': 'Trato por vencer: {trato}',
        'body': (
            "Hola {nombre},\n\n"
            "El trato {trato} del cliente {cliente} está próximo a vencer.\n\n"
            "Fecha de cierre: {fecha_cierre}\n"
            "Días restantes: {dias_restantes}\n"
            "Estado actual: {estado}\n\n"
            "Saludos,\n"
            "{empresa}"
        ),
    },
    'trato_vencido': {
        'label': 'Trato vencido',
        'description': 'Alerta para informar que un trato ya superó su fecha de cierre.',
        'placeholders': ['{nombre}', '{trato}', '{cliente}', '{fecha_cierre}', '{dias_vencido}', '{estado}', '{empresa}'],
        'subject': 'Trato vencido: {trato}',
        'body': (
            "Hola {nombre},\n\n"
            "El trato {trato} del cliente {cliente} se encuentra vencido.\n\n"
            "Fecha de cierre: {fecha_cierre}\n"
            "Días vencido: {dias_vencido}\n"
            "Estado actual: {estado}\n\n"
            "Saludos,\n"
            "{empresa}"
        ),
    },
}

def _default_notification_templates() -> dict:
    return {
        key: {
            'enabled': True,
            'subject': meta['subject'],
            'body': meta['body'],
        }
        for key, meta in NOTIFICATION_TEMPLATE_DEFINITIONS.items()
    }

def _normalize_notification_templates(raw_templates) -> dict:
    templates = _default_notification_templates()
    if not isinstance(raw_templates, dict):
        return templates
    for key, template in raw_templates.items():
        if key not in templates or not isinstance(template, dict):
            continue
        default_template = templates[key]
        subject = " ".join(str(template.get('subject') or default_template['subject']).split()).strip()
        body = str(template.get('body') or default_template['body']).strip()
        templates[key] = {
            'enabled': bool(template.get('enabled', default_template['enabled'])),
            'subject': subject,
            'body': body,
        }
    return templates

def encode_notification_templates(templates: dict) -> str:
    normalized = _normalize_notification_templates(templates)
    serialized = json.dumps(normalized, ensure_ascii=False, separators=(',', ':'))
    return base64.urlsafe_b64encode(serialized.encode('utf-8')).decode('ascii')

def _decode_notification_templates(value: str):
    raw_value = str(value or '').strip()
    if not raw_value:
        return {}
    try:
        decoded = base64.urlsafe_b64decode(raw_value.encode('ascii')).decode('utf-8')
        return json.loads(decoded)
    except Exception:
        try:
            return json.loads(raw_value)
        except Exception:
            return {}

def _load_notification_templates() -> dict:
    env_templates = _decode_notification_templates(
        os.getenv('NOTIFY_TEMPLATES', '') or os.getenv('NOTIFY_TEMPLATES_JSON', '')
    )
    if env_templates:
        return _normalize_notification_templates(env_templates)
    return _normalize_notification_templates({
        'default': {
            'enabled': True,
            'subject': os.getenv('NOTIFY_TEMPLATE_SUBJECT', 'Nueva notificación de SIGO'),
            'body': _env_multiline('NOTIFY_TEMPLATE_BODY', DEFAULT_NOTIFICATION_TEMPLATE_BODY),
        }
    })

def get_notification_template(event_key: str) -> dict:
    key = str(event_key or '').strip()
    template = NOTIFICATION_TEMPLATES_CONFIG.get(key) or NOTIFICATION_TEMPLATES_CONFIG.get('default') or {}
    return {
        'enabled': bool(template.get('enabled', True)),
        'subject': str(template.get('subject') or ''),
        'body': str(template.get('body') or ''),
    }

NOTIFICATION_POLICY_DEFINITIONS = {
    'cliente_solicitud_creada': {
        'label': 'Solicitud de cliente creada',
        'description': 'Notifica a revisión administrativa cuando se crea una nueva solicitud.',
        'allowed_frequencies': ['immediate', 'daily'],
        'default': {
            'enabled': True,
            'email_enabled': True,
            'frequency': 'immediate',
            'send_time': '09:00',
            'weekday': 'monday',
        },
    },
    'cliente_solicitud_aprobada': {
        'label': 'Solicitud de cliente aprobada',
        'description': 'Confirma al solicitante la aprobación sin demoras.',
        'allowed_frequencies': ['immediate', 'daily'],
        'default': {
            'enabled': True,
            'email_enabled': True,
            'frequency': 'immediate',
            'send_time': '09:00',
            'weekday': 'monday',
        },
    },
    'cliente_solicitud_rechazada': {
        'label': 'Solicitud de cliente rechazada',
        'description': 'Informa al solicitante el rechazo y permite configurar reenvío agrupado si se necesitara.',
        'allowed_frequencies': ['immediate', 'daily'],
        'default': {
            'enabled': True,
            'email_enabled': True,
            'frequency': 'immediate',
            'send_time': '09:00',
            'weekday': 'monday',
        },
    },
    'dia_pendiente_carga': {
        'label': 'Día pendiente de carga',
        'description': 'Resume por correo los días del mes con carga incompleta para evitar spam por cada jornada.',
        'allowed_frequencies': ['daily', 'weekly'],
        'default': {
            'enabled': True,
            'email_enabled': True,
            'frequency': 'daily',
            'send_time': '17:00',
            'weekday': 'friday',
        },
    },
    'trato_por_vencer': {
        'label': 'Trato por vencer',
        'description': 'Recordatorio operativo para dueños de tratos próximos a vencer.',
        'allowed_frequencies': ['immediate', 'daily', 'weekly'],
        'default': {
            'enabled': True,
            'email_enabled': True,
            'frequency': 'daily',
            'send_time': '09:00',
            'weekday': 'monday',
        },
    },
    'trato_vencido': {
        'label': 'Trato vencido',
        'description': 'Alerta sobre tratos ya vencidos con opción de agrupar envíos periódicos.',
        'allowed_frequencies': ['immediate', 'daily', 'weekly'],
        'default': {
            'enabled': True,
            'email_enabled': True,
            'frequency': 'daily',
            'send_time': '09:00',
            'weekday': 'monday',
        },
    },
}

NOTIFICATION_POLICY_FREQUENCIES = {
    'immediate': 'inmediata',
    'daily': 'diaria',
    'weekly': 'semanal',
}

NOTIFICATION_POLICY_WEEKDAYS = {
    'monday': 'lunes',
    'tuesday': 'martes',
    'wednesday': 'miércoles',
    'thursday': 'jueves',
    'friday': 'viernes',
}

def _default_notification_policies() -> dict:
    return {
        key: dict(meta['default'])
        for key, meta in NOTIFICATION_POLICY_DEFINITIONS.items()
    }

def _normalize_notification_send_time(value: str, default: str) -> str:
    raw_value = str(value or '').strip()
    if len(raw_value) == 5 and raw_value[2] == ':' and raw_value.replace(':', '').isdigit():
        hours, minutes = raw_value.split(':', 1)
        if 0 <= int(hours) <= 23 and 0 <= int(minutes) <= 59:
            return f"{int(hours):02d}:{int(minutes):02d}"
    return default

def _normalize_notification_policies(raw_policies) -> dict:
    policies = _default_notification_policies()
    if not isinstance(raw_policies, dict):
        return policies
    for key, policy in raw_policies.items():
        if key not in policies or not isinstance(policy, dict):
            continue
        definition = NOTIFICATION_POLICY_DEFINITIONS[key]
        default_policy = dict(definition['default'])
        allowed_frequencies = definition['allowed_frequencies']
        frequency = str(policy.get('frequency') or default_policy['frequency']).strip().lower()
        if frequency not in allowed_frequencies:
            frequency = default_policy['frequency']
        weekday = str(policy.get('weekday') or default_policy['weekday']).strip().lower()
        if weekday not in NOTIFICATION_POLICY_WEEKDAYS:
            weekday = default_policy['weekday']
        policies[key] = {
            'enabled': bool(policy.get('enabled', default_policy['enabled'])),
            'email_enabled': bool(policy.get('email_enabled', default_policy['email_enabled'])),
            'frequency': frequency,
            'send_time': _normalize_notification_send_time(policy.get('send_time'), default_policy['send_time']),
            'weekday': weekday,
        }
    return policies

def encode_notification_policies(policies: dict) -> str:
    normalized = _normalize_notification_policies(policies)
    serialized = json.dumps(normalized, ensure_ascii=False, separators=(',', ':'))
    return base64.urlsafe_b64encode(serialized.encode('utf-8')).decode('ascii')

def _decode_notification_policies(value: str):
    raw_value = str(value or '').strip()
    if not raw_value:
        return {}
    try:
        decoded = base64.urlsafe_b64decode(raw_value.encode('ascii')).decode('utf-8')
        return json.loads(decoded)
    except Exception:
        try:
            return json.loads(raw_value)
        except Exception:
            return {}

def _load_notification_policies() -> dict:
    env_policies = _decode_notification_policies(
        os.getenv('NOTIFY_POLICIES', '') or os.getenv('NOTIFY_POLICIES_JSON', '')
    )
    return _normalize_notification_policies(env_policies)

def get_notification_policy(event_key: str) -> dict:
    key = str(event_key or '').strip()
    definition = NOTIFICATION_POLICY_DEFINITIONS.get(key)
    if definition is None:
        return {
            'enabled': False,
            'email_enabled': False,
            'frequency': 'daily',
            'send_time': '09:00',
            'weekday': 'monday',
        }
    default_policy = dict(definition['default'])
    policy = NOTIFICATION_POLICIES_CONFIG.get(key) or default_policy
    frequency = str(policy.get('frequency') or default_policy['frequency']).strip().lower()
    if frequency not in definition['allowed_frequencies']:
        frequency = default_policy['frequency']
    weekday = str(policy.get('weekday') or default_policy['weekday']).strip().lower()
    if weekday not in NOTIFICATION_POLICY_WEEKDAYS:
        weekday = default_policy['weekday']
    return {
        'enabled': bool(policy.get('enabled', default_policy['enabled'])),
        'email_enabled': bool(policy.get('email_enabled', default_policy['email_enabled'])),
        'frequency': frequency,
        'send_time': _normalize_notification_send_time(policy.get('send_time'), default_policy['send_time']),
        'weekday': weekday,
    }

# Configuración PostgreSQL
POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'sigo_db'),
    'user': os.getenv('POSTGRES_USER', 'sigo'),
    'password': os.getenv('POSTGRES_PASSWORD', 'sigo')
}

# Rutas configurables
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
UPLOADS_DIR = os.getenv('UPLOADS_DIR', os.path.join(BASE_DIR, 'uploads'))
PROJECT_UPLOADS_DIR = os.getenv('PROJECT_UPLOADS_DIR', os.path.join(UPLOADS_DIR, 'projects'))
SMTP_CONFIG = {
    'enabled': _env_flag('SMTP_ENABLED', False),
    'host': os.getenv('SMTP_HOST', 'smtp.gmail.com'),
    'port': os.getenv('SMTP_PORT', '587'),
    'user': os.getenv('SMTP_USER', ''),
    'password': os.getenv('SMTP_PASSWORD', ''),
    'from_email': os.getenv('SMTP_FROM_EMAIL', ''),
    'from_name': os.getenv('SMTP_FROM_NAME', 'SIGO'),
    'security': os.getenv('SMTP_SECURITY', 'tls').strip().lower() or 'tls',
}
NOTIFICATION_POLICIES_CONFIG = _load_notification_policies()
NOTIFICATION_TEMPLATES_CONFIG = _load_notification_templates()
NOTIFICATION_TEMPLATE_CONFIG = dict(get_notification_template('default'))

def update_env_values(values: dict) -> bool:
    env_path = os.path.join(BASE_DIR, '.env')
    try:
        existing = {}
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    existing[k.strip()] = v.strip()
        existing.update({k: str(v) for k, v in values.items() if v is not None})
        with open(env_path, 'w', encoding='utf-8') as f:
            for k, v in existing.items():
                f.write(f"{k}={v}\n")
        return True
    except Exception:
        return False

def reload_env():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    POSTGRES_CONFIG.update({
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': os.getenv('POSTGRES_PORT', '5432'),
        'database': os.getenv('POSTGRES_DB', 'postgres'),
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', 'postgres')
    })
    SMTP_CONFIG.update({
        'enabled': _env_flag('SMTP_ENABLED', False),
        'host': os.getenv('SMTP_HOST', 'smtp.gmail.com'),
        'port': os.getenv('SMTP_PORT', '587'),
        'user': os.getenv('SMTP_USER', ''),
        'password': os.getenv('SMTP_PASSWORD', ''),
        'from_email': os.getenv('SMTP_FROM_EMAIL', ''),
        'from_name': os.getenv('SMTP_FROM_NAME', 'SIGO'),
        'security': os.getenv('SMTP_SECURITY', 'tls').strip().lower() or 'tls',
    })
    policies = _load_notification_policies()
    NOTIFICATION_POLICIES_CONFIG.clear()
    NOTIFICATION_POLICIES_CONFIG.update(policies)
    templates = _load_notification_templates()
    NOTIFICATION_TEMPLATES_CONFIG.clear()
    NOTIFICATION_TEMPLATES_CONFIG.update(templates)
    NOTIFICATION_TEMPLATE_CONFIG.clear()
    NOTIFICATION_TEMPLATE_CONFIG.update(get_notification_template('default'))

# Usuarios por defecto
DEFAULT_ADMIN_USERNAME = 'admin'
DEFAULT_ADMIN_PASSWORD = 'admin'
APP_SESSION_SECRET = os.getenv('APP_SESSION_SECRET', 'change-me')

# Roles del sistema
SYSTEM_ROLES = {
    'ADMIN': 'admin',
    'SIN_ROL': 'sin_rol',
    'HIPERVISOR': 'hipervisor',
    'ADM_COMERCIAL': 'adm_comercial',
    'DPTO_COMERCIAL': 'dpto_comercial'
}

# Validación de contraseñas
PASSWORD_CONFIG = {
    'MIN_LENGTH': 8,
    'SPECIAL_CHARS': "!@#$%^&*()-_=+[]{}|;:'\",.<>/?`~",
    'REQUIRE_UPPERCASE': True,
    'REQUIRE_LOWERCASE': True,
    'REQUIRE_DIGIT': True,
    'REQUIRE_SPECIAL': True
}

# Límites del sistema
SYSTEM_LIMITS = {
    'MAX_DUPLICATE_ATTEMPTS': 99,
    'MAX_SEARCH_RESULTS': 50
}

# Umbrales de bloqueo por intentos fallidos
FAILED_LOGIN_MAX_ATTEMPTS = 5           # Usuarios normales: intentos permitidos
LOCKOUT_MINUTES = 15                    # Usuarios normales: minutos de bloqueo

ADMIN_FAILED_LOGIN_MAX_ATTEMPTS = 5     # Admin: intentos permitidos
ADMIN_LOCKOUT_MINUTES = 30              # Admin: minutos de bloqueo

# Valores por defecto
DEFAULT_VALUES = {
    'GROUP': 'General',
    'ROLE': SYSTEM_ROLES['SIN_ROL']
}

# Estados de proyectos comerciales (fuente única)
PROYECTO_ESTADOS = [
    "Prospecto",
    "Presupuestado",
    "Negociación",
    "Objeción",
    "Ganado",
    "Perdido",
]

PROYECTO_TIPOS_VENTA = [
    "Venta de equipo",
    "Licencia",
    "Soporte y mantenimiento",
    "Servicios",
    "Contratos",
]

# Versión de la aplicación
APP_VERSION = '1.2.80'

def get_app_version() -> str:
    try:
        from dotenv import dotenv_values
        values = dotenv_values(ENV_PATH, encoding='utf-8')
        file_v = values.get('APP_VERSION') or values.get('app_version')
        if file_v:
            return str(file_v).strip()
    except Exception:
        pass
    v = os.getenv('APP_VERSION') or os.getenv('app_version')
    return v if v is not None else APP_VERSION

# Mensajes del sistema
MESSAGES = {
    'PASSWORD_REQUIREMENTS': "La contraseña debe tener al menos 8 caracteres, una letra mayúscula, una letra minúscula, un número y un carácter especial.",
    'DUPLICATE_RECORD': "Ya existe un registro con estos mismos datos. No se puede crear un duplicado.",
    'PASSWORDS_DONT_MATCH': "Las contraseñas no coinciden.",
    'PROFILE_UPDATED': "Perfil guardado.",
    'PASSWORD_UPDATED': "Contraseña actualizada.",
    'RECORD_CREATED': "✅ Registro creado exitosamente.",
    'RECORD_UPDATED': "✅ Registro actualizado exitosamente.",
    'REQUIRED_FIELDS': "Todos los campos marcados con * son obligatorios."
}

# Configuración de UI
UI_CONFIG = {
    'TABS': {
        'ADMIN_MAIN': ["📊 Visualización de Datos", "⚙️ Gestión", "🛠️ Administración"],
        'MANAGEMENT': ["👥 Usuarios", "🏢 Clientes", "📋 Tipos de Tarea", "🔄 Modalidades", "🔑 Roles", "👪 Grupos", "🏠 Nómina", "📝 Registros"],
        'DASHBOARD': ["Clientes", "Tipos de Tarea", "Técnicos", "Tabla de Registros"]
    }
}
