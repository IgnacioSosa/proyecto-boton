"""
Configuración centralizada de la aplicación
"""

# Base de datos
DATABASE_PATH = 'trabajo.db'

# Usuarios por defecto
DEFAULT_ADMIN_USERNAME = 'admin'
DEFAULT_ADMIN_PASSWORD = 'admin'

# Roles del sistema
SYSTEM_ROLES = {
    'ADMIN': 'admin',
    'SIN_ROL': 'sin_rol',
    'HIPERVISOR': 'hipervisor',
    'VISOR': 'visor'
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

# Valores por defecto
DEFAULT_VALUES = {
    'GROUP': 'General',
    'ROLE': 'sin_rol'
}

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
        'ADMIN_MAIN': ["📊 Visualización de Datos", "⚙️ Gestión"],
        'MANAGEMENT': ["👥 Usuarios", "🏢 Clientes", "📋 Tipos de Tarea", "🔄 Modalidades", "🔑 Roles", "👪 Grupos", "🏠 Nómina", "📝 Registros"],
        'DASHBOARD': ["Clientes", "Tipos de Tarea", "Técnicos", "Tabla de Registros"]
    }
}