import bcrypt
import streamlit as st
from .database import get_connection
from .config import SYSTEM_ROLES, PASSWORD_CONFIG

def hash_password(password):
    """Genera hash de contraseña usando bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, hashed):
    """Verifica contraseña contra hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def registrar_login(usuario_id, username):
    """Registra un login exitoso en la base de datos PostgreSQL"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO activity_logs (user_id, action, details, timestamp)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        """, (usuario_id, 'LOGIN', f'Usuario {username} inició sesión'))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error registrando login: {e}")

def validate_password(password):
    """Valida que la contraseña cumpla con los requisitos de seguridad"""
    if len(password) < PASSWORD_CONFIG['MIN_LENGTH']:
        return False, f"La contraseña debe tener al menos {PASSWORD_CONFIG['MIN_LENGTH']} caracteres"
    
    if PASSWORD_CONFIG['REQUIRE_UPPERCASE'] and not any(c.isupper() for c in password):
        return False, "La contraseña debe contener al menos una letra mayúscula"
    
    if PASSWORD_CONFIG['REQUIRE_LOWERCASE'] and not any(c.islower() for c in password):
        return False, "La contraseña debe contener al menos una letra minúscula"
    
    if PASSWORD_CONFIG['REQUIRE_DIGIT'] and not any(c.isdigit() for c in password):
        return False, "La contraseña debe contener al menos un número"
    
    if PASSWORD_CONFIG['REQUIRE_SPECIAL'] and not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        return False, "La contraseña debe contener al menos un carácter especial"
    
    return True, "Contraseña válida"

def create_user(username, password, nombre=None, apellido=None, email=None, rol_id=None, is_active=True):
    """Crea un nuevo usuario en la base de datos"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Verificar si el usuario ya existe
        c.execute('SELECT id FROM usuarios WHERE username = %s', (username,))
        if c.fetchone():
            conn.close()
            st.error("El nombre de usuario ya existe")
            return False
        
        # Hashear la contraseña
        hashed_password = hash_password(password)
        
        # Si no se especifica rol, asignar 'sin_rol'
        if rol_id is None:
            c.execute('SELECT id_rol FROM roles WHERE nombre = %s', (SYSTEM_ROLES['SIN_ROL'],))
            rol_result = c.fetchone()
            if rol_result:
                rol_id = rol_result[0]
        
        # Insertar el nuevo usuario sin grupo_id
        c.execute('''INSERT INTO usuarios (username, password_hash, nombre, apellido, email, rol_id, is_active) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                  (username, hashed_password, nombre, apellido, email, rol_id, is_active))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        conn.rollback()
        conn.close()
        st.error(f"Error al crear usuario: {str(e)}")
        return False

def login_user(username, password):
    """Autentica un usuario y devuelve su información si es válido"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Buscar usuario por username e incluir is_active e is_admin
        # CORREGIDO: Usar solo las columnas que existen en la tabla
        c.execute('SELECT id, password_hash, is_active, is_admin FROM usuarios WHERE username = %s', (username,))
        user = c.fetchone()
        
        if user and verify_password(password, user[1]):
            # Verificar si el usuario está activo
            if not user[2]:  # is_active está en el índice 2
                conn.close()
                return False, False
            
            user_id = user[0]
            is_admin = bool(user[3])  # is_admin está en el índice 3
            
            # Registrar el login exitoso usando la función de database.py
            from .database import registrar_login
            registrar_login(user_id, username)
            
            conn.close()
            return user_id, is_admin
        else:
            # No registrar intentos fallidos por ahora
            conn.close()
            return False, False
            
    except Exception as e:
        print(f"Error en login_user: {e}")
        conn.close()
        return False, False

# Funciones 2FA simplificadas (deshabilitadas temporalmente)
def verify_2fa_code(code):
    """Verifica el código 2FA - versión simplificada (siempre retorna True)"""
    return True

def enable_2fa(user_id):
    """Habilita 2FA - versión simplificada (retorna valores dummy)"""
    # Retornar valores dummy para que no falle la UI
    return "DUMMY_SECRET", "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", []

def disable_2fa(user_id):
    """Deshabilita 2FA - versión simplificada (siempre retorna True)"""
    return True

def is_2fa_enabled(user_id):
    """Verifica si un usuario tiene 2FA habilitado - versión simplificada"""
    return False  # Por ahora deshabilitamos 2FA

def logout():
    """Función para desloguear y limpiar el estado"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]