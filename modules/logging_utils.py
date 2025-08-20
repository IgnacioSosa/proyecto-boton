import logging
import os
from datetime import datetime

# Asegurar que los directorios de logs existan
os.makedirs('logs/sql', exist_ok=True)
os.makedirs('logs/app', exist_ok=True)

# Configurar el logger para errores SQL
sql_logger = logging.getLogger('sql_errors')
sql_logger.setLevel(logging.ERROR)

# Crear un manejador de archivo para errores SQL
sql_handler = logging.FileHandler('logs/sql/sql_errors.log')
sql_handler.setLevel(logging.ERROR)

# Configurar el formato para los logs SQL
sql_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
sql_handler.setFormatter(sql_formatter)
sql_logger.addHandler(sql_handler)

# Configurar el logger para errores de aplicación
app_logger = logging.getLogger('app_errors')
app_logger.setLevel(logging.ERROR)

# Crear un manejador de archivo para errores de aplicación
app_handler = logging.FileHandler('logs/app/app_errors.log')
app_handler.setLevel(logging.ERROR)

# Configurar el formato para los logs de aplicación
app_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
app_handler.setFormatter(app_formatter)
app_logger.addHandler(app_handler)

# Función para registrar errores SQL
def log_sql_error(error, query=None, params=None):
    """Registra errores relacionados con SQL
    
    Args:
        error: El error capturado
        query: La consulta SQL que causó el error (opcional)
        params: Los parámetros de la consulta (opcional)
    """
    error_msg = f"Error SQL: {str(error)}"
    if query:
        error_msg += f"\nConsulta: {query}"
    if params:
        error_msg += f"\nParámetros: {params}"
    
    sql_logger.error(error_msg)
    return error_msg

# Función para registrar errores de aplicación
def log_app_error(error, module=None, function=None):
    """Registra errores generales de la aplicación
    
    Args:
        error: El error capturado
        module: El módulo donde ocurrió el error (opcional)
        function: La función donde ocurrió el error (opcional)
    """
    error_msg = f"Error de aplicación: {str(error)}"
    if module:
        error_msg += f"\nMódulo: {module}"
    if function:
        error_msg += f"\nFunción: {function}"
    
    app_logger.error(error_msg)
    return error_msg