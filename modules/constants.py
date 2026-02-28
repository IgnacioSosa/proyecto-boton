from .config import MESSAGES, PASSWORD_CONFIG

# Mensajes de error
ERROR_MESSAGES = {
    'DUPLICATE_RECORD': MESSAGES['DUPLICATE_RECORD'],
    'PASSWORDS_DONT_MATCH': MESSAGES['PASSWORDS_DONT_MATCH'],
    'INVALID_CREDENTIALS': "Credenciales inválidas. Por favor, verifica tu usuario y contraseña.",
    'USER_NOT_FOUND': "Usuario no encontrado.",
    'USER_INACTIVE': "Usuario inactivo. Contacta al administrador.",
    'INVALID_2FA_CODE': "Código de autenticación de dos factores inválido.",
    'INVALID_RECOVERY_CODE': "Código de recuperación inválido o ya utilizado.",
    'INVALID_PASSWORD': "Contraseña inválida.",
    'USER_ALREADY_EXISTS': "El usuario ya existe.",
    'INVALID_EMAIL': "Email inválido.",
    'INVALID_ROLE': "Rol inválido.",
    'INVALID_GROUP': "Grupo inválido.",
    'INVALID_DATE': "Fecha inválida.",
    'INVALID_TIME': "Tiempo inválido.",
    'INVALID_TASK': "Tarea inválida.",
    'INVALID_CLIENT': "Cliente inválido.",
    'INVALID_TECH': "Técnico inválido.",
    'INVALID_TYPE': "Tipo de tarea inválido.",
    'INVALID_MODALITY': "Modalidad inválida.",
    'INVALID_TICKET': "Número de ticket inválido.",
    'INVALID_DESCRIPTION': "Descripción inválida.",
    'INVALID_MONTH': "Mes inválido.",
    'INVALID_GROUP_NAME': "Nombre de grupo inválido.",
    'INVALID_FILE': "Archivo inválido.",
    'FILE_NOT_FOUND': "Archivo no encontrado.",
    'UPLOAD_ERROR': "Error al subir el archivo.",
    'PROCESSING_ERROR': "Error al procesar los datos.",
    'DATABASE_ERROR': "Error de base de datos.",
    'PERMISSION_DENIED': "Permisos insuficientes.",
    'SESSION_EXPIRED': "Sesión expirada. Por favor, inicia sesión nuevamente.",
    'MAINTENANCE_MODE': "Sistema en mantenimiento. Intenta más tarde."
}

# Mensajes de éxito
SUCCESS_MESSAGES = {
    'USER_CREATED': "Usuario creado exitosamente.",
    'USER_UPDATED': "Usuario actualizado exitosamente.",
    'USER_DELETED': "Usuario eliminado exitosamente.",
    'RECORD_CREATED': "Registro creado exitosamente.",
    'RECORD_UPDATED': "Registro actualizado exitosamente.",
    'RECORD_DELETED': "Registro eliminado exitosamente.",
    'FILE_UPLOADED': "Archivo subido exitosamente.",
    'DATA_PROCESSED': "Datos procesados exitosamente.",
    'SETTINGS_SAVED': "Configuración guardada exitosamente.",
    'PASSWORD_CHANGED': "Contraseña cambiada exitosamente.",
    'PROFILE_UPDATED': "Perfil actualizado exitosamente.",
    'LOGIN_SUCCESS': "Inicio de sesión exitoso.",
    'LOGOUT_SUCCESS': "Sesión cerrada exitosamente.",
    '2FA_ENABLED': "Autenticación de dos factores habilitada.",
    '2FA_DISABLED': "Autenticación de dos factores deshabilitada.",
    'BACKUP_CREATED': "Respaldo creado exitosamente.",
    'DATA_IMPORTED': "Datos importados exitosamente.",
    'DATA_EXPORTED': "Datos exportados exitosamente."
}

# Mensajes informativos
INFO_MESSAGES = {
    'PASSWORD_REQUIREMENTS': MESSAGES['PASSWORD_REQUIREMENTS'],
    'LOADING': "Cargando...",
    'NO_DATA': "No hay datos disponibles.",
    'SELECT_OPTION': "Selecciona una opción.",
    'CONFIRM_ACTION': "¿Estás seguro de realizar esta acción?",
    'UNSAVED_CHANGES': "Tienes cambios sin guardar.",
    'MAINTENANCE_SCHEDULED': "Mantenimiento programado para esta noche.",
    'NEW_FEATURES': "Nuevas funcionalidades disponibles.",
    'BACKUP_RECOMMENDED': "Se recomienda hacer un respaldo.",
    'UPDATE_AVAILABLE': "Actualización disponible."
}

ERROR_DUPLICATE_RECORD = ERROR_MESSAGES['DUPLICATE_RECORD']
ERROR_PASSWORDS_DONT_MATCH = ERROR_MESSAGES['PASSWORDS_DONT_MATCH']
ERROR_REQUIRED_FIELDS = MESSAGES['REQUIRED_FIELDS']

SUCCESS_PROFILE_UPDATED = MESSAGES['PROFILE_UPDATED']
SUCCESS_PASSWORD_UPDATED = MESSAGES['PASSWORD_UPDATED']
SUCCESS_RECORD_CREATED = MESSAGES['RECORD_CREATED']
SUCCESS_RECORD_UPDATED = MESSAGES['RECORD_UPDATED']

INFO_PASSWORD_REQUIREMENTS = INFO_MESSAGES['PASSWORD_REQUIREMENTS']
