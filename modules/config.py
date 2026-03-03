"""
Configuración centralizada de la aplicación
"""
import os
from dotenv import load_dotenv

# Cargar variables de entorno
ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(dotenv_path=ENV_PATH)

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
    # Actualizar la configuración de PostgreSQL en tiempo real
    POSTGRES_CONFIG.update({
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': os.getenv('POSTGRES_PORT', '5432'),
        'database': os.getenv('POSTGRES_DB', 'postgres'),
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', 'postgres')
    })

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
APP_VERSION = '1.2.73'

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
