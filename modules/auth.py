import streamlit as st
import bcrypt
import pyotp
import qrcode
from io import BytesIO
import base64
import random
import string
from .database import get_connection, registrar_login
from .config import SYSTEM_ROLES, PASSWORD_CONFIG

def hash_password(password):
    """Hashea una contraseña usando bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def verify_password(password, hashed):
    """Verifica una contraseña contra su hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

def validate_password(password):
    """Valida que la contraseña cumpla con los requisitos"""
    if len(password) < PASSWORD_CONFIG['MIN_LENGTH']:
        return False, f"La contraseña debe tener al menos {PASSWORD_CONFIG['MIN_LENGTH']} caracteres"
    
    if PASSWORD_CONFIG['REQUIRE_UPPERCASE'] and not any(c.isupper() for c in password):
        return False, "La contraseña debe contener al menos una letra mayúscula"
    
    if PASSWORD_CONFIG['REQUIRE_LOWERCASE'] and not any(c.islower() for c in password):
        return False, "La contraseña debe contener al menos una letra minúscula"
    
    if PASSWORD_CONFIG['REQUIRE_DIGIT'] and not any(c.isdigit() for c in password):
        return False, "La contraseña debe contener al menos un número"
    
    if PASSWORD_CONFIG['REQUIRE_SPECIAL'] and not any(c in PASSWORD_CONFIG['SPECIAL_CHARS'] for c in password):
        return False, f"La contraseña debe contener al menos uno de estos caracteres especiales: {PASSWORD_CONFIG['SPECIAL_CHARS']}"
    
    return True, "Contraseña válida"

def create_user(username, password, nombre=None, apellido=None, email=None, rol_id=None, grupo_id=None, is_active=True):
    """Crea un nuevo usuario en la base de datos"""
    # Validar contraseña
    is_valid, message = validate_password(password)
    if not is_valid:
        return False, message
    
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Verificar si el usuario ya existe
        c.execute('SELECT id FROM usuarios WHERE username = ?', (username,))
        if c.fetchone():
            conn.close()
            return False, "El nombre de usuario ya existe"
        
        # Hashear la contraseña
        hashed_password = hash_password(password)
        
        # Si no se especifica rol, asignar 'sin_rol'
        if rol_id is None:
            c.execute('SELECT id_rol FROM roles WHERE nombre = ?', (SYSTEM_ROLES['SIN_ROL'],))
            rol_result = c.fetchone()
            if rol_result:
                rol_id = rol_result[0]
        
        # Si no se especifica grupo, buscar el grupo por defecto
        if grupo_id is None:
            # Buscar si existe un grupo por defecto o crear uno
            c.execute('SELECT id_grupo FROM grupos WHERE nombre = ?', ('General',))
            grupo_result = c.fetchone()
            if not grupo_result:
                # Crear grupo por defecto si no existe
                c.execute('INSERT INTO grupos (nombre, descripcion) VALUES (?, ?)', 
                         ('General', 'Grupo por defecto'))
                grupo_id = c.lastrowid
            else:
                grupo_id = grupo_result[0]
        
        # Insertar el nuevo usuario
        c.execute('''INSERT INTO usuarios (username, password, nombre, apellido, email, rol_id, grupo_id, is_active) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (username, hashed_password, nombre, apellido, email, rol_id, grupo_id, is_active))
        
        conn.commit()
        conn.close()
        return True, "Usuario creado exitosamente"
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Error al crear usuario: {str(e)}"

def login_user(username, password):
    """Autentica un usuario y devuelve su información si es válido"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Buscar usuario por username e incluir is_active e is_admin
        c.execute('SELECT id, password, nombre, apellido, is_active, is_admin FROM usuarios WHERE username = ?', (username,))
        user = c.fetchone()
        
        if user and verify_password(password, user[1]):
            # Verificar si el usuario está activo
            if not user[4]:  # is_active está en el índice 4
                conn.close()
                return False, False
            
            user_id = user[0]
            is_admin = bool(user[5])  # is_admin está en el índice 5
            
            # Registrar el login exitoso (solo 2 parámetros)
            registrar_login(user_id, username)
            
            conn.close()
            return user_id, is_admin
        else:
            # No registrar intentos fallidos por ahora
            conn.close()
            return False, False
            
    except Exception as e:
        conn.close()
        return False, False
        return False, "Credenciales inválidas"
            
    except Exception as e:
        conn.close()
        return False, f"Error en el login: {str(e)}"

def verify_2fa_code(code):
    """Verifica el código 2FA del usuario actual"""
    if 'temp_user_id' not in st.session_state:
        return False
    
    user_id = st.session_state.temp_user_id
    
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Obtener el secret del usuario
        c.execute('SELECT totp_secret FROM usuarios WHERE id = ?', (user_id,))
        result = c.fetchone()
        
        if not result or not result[0]:
            conn.close()
            return False
        
        secret = result[0]
        totp = pyotp.TOTP(secret)
        
        # Verificar el código (con ventana de tiempo)
        is_valid = totp.verify(code, valid_window=1)
        
        # También verificar si es un código de recuperación
        if not is_valid:
            c.execute('SELECT code FROM recovery_codes WHERE user_id = ? AND used = 0', (user_id,))
            recovery_codes = [row[0] for row in c.fetchall()]
            
            if code in recovery_codes:
                # Marcar el código de recuperación como usado
                c.execute('UPDATE recovery_codes SET used = 1 WHERE user_id = ? AND code = ?', 
                         (user_id, code))
                conn.commit()
                is_valid = True
        
        conn.close()
        return is_valid
        
    except Exception as e:
        conn.close()
        return False

def complete_login_after_2fa():
    """Completa el proceso de login después de verificar 2FA"""
    if 'temp_user_id' not in st.session_state or 'temp_username' not in st.session_state:
        return False
    
    user_id = st.session_state.temp_user_id
    username = st.session_state.temp_username
    
    # Obtener información completa del usuario
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT nombre, apellido FROM usuarios WHERE id = ?', (user_id,))
    user_info = c.fetchone()
    conn.close()
    
    # Establecer sesión completa
    st.session_state.authenticated = True
    st.session_state.user_id = user_id
    st.session_state.username = username
    st.session_state.nombre = user_info[0] if user_info else ''
    st.session_state.apellido = user_info[1] if user_info else ''
    
    # Limpiar variables temporales
    del st.session_state.temp_user_id
    del st.session_state.temp_username
    if 'awaiting_2fa' in st.session_state:
        del st.session_state.awaiting_2fa
    
    return True

def generate_recovery_codes(user_id, count=10):
    """Genera códigos de recuperación para un usuario"""
    codes = []
    for _ in range(count):
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        codes.append(code)
    
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Eliminar códigos existentes
        c.execute('DELETE FROM recovery_codes WHERE user_id = ?', (user_id,))
        
        # Insertar nuevos códigos
        for code in codes:
            c.execute('INSERT INTO recovery_codes (user_id, code) VALUES (?, ?)', (user_id, code))
        
        conn.commit()
        conn.close()
        return codes
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return []

def enable_2fa(user_id):
    """Habilita 2FA para un usuario y devuelve el QR code"""
    # Generar secret
    secret = pyotp.random_base32()
    
    # Obtener información del usuario
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT username FROM usuarios WHERE id = ?', (user_id,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        return None, None
    
    username = result[0]
    
    # Crear TOTP
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=username,
        issuer_name="Sistema de Registro"
    )
    
    # Generar QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convertir a base64 para mostrar en Streamlit
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    # Guardar secret en la base de datos
    try:
        c.execute('UPDATE usuarios SET totp_secret = ? WHERE id = ?', (secret, user_id))
        conn.commit()
        conn.close()
        
        # Generar códigos de recuperación
        recovery_codes = generate_recovery_codes(user_id)
        
        return img_str, recovery_codes
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return None, None

def disable_2fa(user_id):
    """Deshabilita 2FA para un usuario"""
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Eliminar secret y códigos de recuperación
        c.execute('UPDATE usuarios SET totp_secret = NULL WHERE id = ?', (user_id,))
        c.execute('DELETE FROM recovery_codes WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return False

def is_2fa_enabled(user_id):
    """Verifica si un usuario tiene 2FA habilitado"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT totp_secret FROM usuarios WHERE id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    
    return result and result[0] is not None

def logout():
    """Función para desloguear y limpiar el estado"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]