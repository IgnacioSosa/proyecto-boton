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
    'TECNICO': 'tecnico', 
    'SIN_ROL': 'sin_rol',
    'HIPERVISOR': 'hipervisor'
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

# Mensajes del sistema (ya tienes algunos en constants.py)
MESSAGES = {
    'PASSWORD_REQUIREMENTS': "La contraseña debe tener al menos 8 caracteres, una letra mayúscula, una letra minúscula, un número y un carácter especial.",
    'DUPLICATE_RECORD': "Ya existe un registro con estos mismos datos. No se puede crear un duplicado.",
    'PASSWORDS_DONT_MATCH': "Las contraseñas no coinciden."
}