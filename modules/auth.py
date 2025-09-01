import streamlit as st
import bcrypt
import pyotp
import qrcode
from io import BytesIO
import base64
import random
import string
from .database import get_connection, registrar_login

def hash_password(password):
    """Hashea una contraseña"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def verify_password(password, hashed):
    """Verifica una contraseña"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

def validate_password(password):
    """Valida que la contraseña cumpla con los requisitos de seguridad"""
    # Verificar si la contraseña sigue el formato Nombre_Apellido.
    import re
    if re.match(r'^[A-Z][a-z]+_[A-Z][a-z]+\.$', password):
        return True, ["Contraseña válida"]
    
    # Si no sigue el formato especial, verificar los requisitos estándar
    requisitos_faltantes = []
    
    if len(password) < 8:
        requisitos_faltantes.append("La contraseña debe tener al menos 8 caracteres.")
    
    if not any(c.isupper() for c in password):
        requisitos_faltantes.append("La contraseña debe tener al menos una letra mayúscula.")
    
    if not any(c.islower() for c in password):
        requisitos_faltantes.append("La contraseña debe tener al menos una letra minúscula.")
    
    if not any(c.isdigit() for c in password):
        requisitos_faltantes.append("La contraseña debe tener al menos un número.")
    
    if not any(c in "!@#$%^&*()-_=+[]{}|;:'\",.<>/?`~" for c in password):
        requisitos_faltantes.append("La contraseña debe tener al menos un carácter especial.")
    
    if requisitos_faltantes:
        return False, requisitos_faltantes
    
    return True, ["Contraseña válida"]

def create_user(username, password, nombre=None, apellido=None, email=None, rol_id=None, grupo_id=None):
    """Crea un nuevo usuario"""
    # Validar la contraseña
    is_valid, messages = validate_password(password)
    if not is_valid:
        for message in messages:
            st.error(message)
        return False
    
    conn = get_connection()
    c = conn.cursor()
    
    # Convertir el username a minúsculas
    username = username.lower()
    
    # Capitalizar nombre y apellido si existen
    if nombre:
        nombre = nombre.strip().capitalize()
    if apellido:
        apellido = apellido.strip().capitalize()
    
    # Verificar si el usuario ya existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', (username,))
    if c.fetchone():
        conn.close()
        st.error("El nombre de usuario ya existe.")
        return False
    
    # Si no se proporciona un rol, asignar 'sin_rol' por defecto
    if not rol_id:
        c.execute('SELECT id_rol FROM roles WHERE nombre = ?', ('sin_rol',))
        rol_result = c.fetchone()
        if rol_result:
            rol_id = rol_result[0]
    
    # Verificar que el grupo solo se asigne a usuarios con rol de técnico
    if grupo_id is not None:
        c.execute('SELECT nombre FROM roles WHERE id_rol = ?', (rol_id,))
        rol_nombre = c.fetchone()
        if not rol_nombre or rol_nombre[0].lower() != 'tecnico':
            conn.close()
            st.error("El grupo solo puede asignarse a usuarios con rol de técnico.")
            return False
    
    # Determinar si es admin basado en el rol
    c.execute('SELECT nombre FROM roles WHERE id_rol = ?', (rol_id,))
    rol_nombre = c.fetchone()
    is_admin = False
    if rol_nombre and rol_nombre[0].lower() == 'admin':
        is_admin = True
    
    # Crear el nuevo usuario (deshabilitado por defecto)
    hashed_password = hash_password(password)
    c.execute('INSERT INTO usuarios (username, password, nombre, apellido, email, is_admin, is_active, rol_id, grupo_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
              (username, hashed_password, nombre, apellido, email, is_admin, False, rol_id, grupo_id))
    
    conn.commit()
    conn.close()
    return True

def login_user(username, password):
    """Autentica a un usuario y establece la sesión"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, password, is_admin, nombre, apellido, rol_id, grupo_id, is_active, is_2fa_enabled, totp_secret FROM usuarios WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    
    if not user or not user[7]:  # Verificar que el usuario exista y esté activo
        return None, None
    
    stored_password = user[1]
    if not verify_password(password, stored_password):
        return None, None
    
    # Si el usuario tiene 2FA habilitado, no completar el login todavía
    if user[8] == 1:  # is_2fa_enabled
        # Guardar información temporal para la verificación 2FA
        st.session_state.temp_user_id = user[0]
        st.session_state.temp_username = username
        st.session_state.temp_is_admin = bool(user[2])
        st.session_state.temp_nombre = user[3]
        st.session_state.temp_apellido = user[4]
        st.session_state.temp_rol_id = user[5]
        st.session_state.temp_grupo_id = user[6]
        st.session_state.awaiting_2fa = True
        return None, None
    
    # Si no tiene 2FA, completar el login normalmente
    st.session_state.logged_in = True
    st.session_state.username = username
    st.session_state.user_id = user[0]
    st.session_state.is_admin = bool(user[2])
    st.session_state.nombre = user[3]
    st.session_state.apellido = user[4]
    st.session_state.rol_id = user[5]
    st.session_state.grupo_id = user[6]
    
    # Registrar el inicio de sesión exitoso
    registrar_login(user[0], username)
    
    return user[0], bool(user[2])

def verify_2fa_code(code):
    """Verifica el código 2FA ingresado"""
    if not st.session_state.get('temp_user_id'):
        return False
    
    user_id = st.session_state.temp_user_id
    
    # Verificar si es un código TOTP válido
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT totp_secret FROM usuarios WHERE id = ?", (user_id,))
    result = c.fetchone()
    
    if not result or not result[0]:
        conn.close()
        return False
    
    totp_secret = result[0]
    
    # Verificar el código TOTP
    totp = pyotp.TOTP(totp_secret)
    if totp.verify(code):
        complete_login_after_2fa()
        conn.close()
        return True
    
    # Si no es un código TOTP válido, verificar si es un código de recuperación
    c.execute("SELECT id FROM recovery_codes WHERE user_id = ? AND code = ? AND used = 0", (user_id, code))
    recovery_code = c.fetchone()
    
    if recovery_code:
        # Marcar el código de recuperación como usado
        c.execute("UPDATE recovery_codes SET used = 1 WHERE id = ?", (recovery_code[0],))
        conn.commit()
        complete_login_after_2fa()
        conn.close()
        return True
    
    conn.close()
    return False

def complete_login_after_2fa():
    """Completa el proceso de login después de la verificación 2FA"""
    st.session_state.logged_in = True
    st.session_state.user_id = st.session_state.temp_user_id
    st.session_state.username = st.session_state.temp_username
    st.session_state.is_admin = st.session_state.temp_is_admin
    st.session_state.nombre = st.session_state.temp_nombre
    st.session_state.apellido = st.session_state.temp_apellido
    st.session_state.rol_id = st.session_state.temp_rol_id
    st.session_state.grupo_id = st.session_state.temp_grupo_id
    st.session_state.awaiting_2fa = False
    
    # Limpiar variables temporales
    for key in ['temp_user_id', 'temp_username', 'temp_is_admin', 'temp_nombre', 
                'temp_apellido', 'temp_rol_id', 'temp_grupo_id']:
        if key in st.session_state:
            del st.session_state[key]
    
    # Registrar el inicio de sesión exitoso
    registrar_login(st.session_state.user_id, st.session_state.username)

def generate_recovery_codes(user_id, count=10):
    """Genera códigos de recuperación para un usuario"""
    conn = get_connection()
    c = conn.cursor()
    
    # Eliminar códigos anteriores
    c.execute("DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))
    
    # Generar nuevos códigos
    codes = []
    for _ in range(count):
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        c.execute("INSERT INTO recovery_codes (user_id, code, used) VALUES (?, ?, 0)", (user_id, code))
        codes.append(code)
    
    conn.commit()
    conn.close()
    return codes

def enable_2fa(user_id):
    """Habilita 2FA para un usuario y devuelve el secreto y QR"""
    # Generar un nuevo secreto TOTP
    totp_secret = pyotp.random_base32()
    
    # Guardar en la base de datos
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE usuarios SET totp_secret = ?, is_2fa_enabled = 1 WHERE id = ?", (totp_secret, user_id))
    conn.commit()
    
    # Obtener información del usuario para el QR
    c.execute("SELECT username FROM usuarios WHERE id = ?", (user_id,))
    username = c.fetchone()[0]
    conn.close()
    
    # Generar URI para el QR
    totp = pyotp.TOTP(totp_secret)
    uri = totp.provisioning_uri(username, issuer_name="Sistema de Registro de Horas")
    
    # Generar códigos de recuperación
    recovery_codes = generate_recovery_codes(user_id)
    
    # Generar imagen QR
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convertir imagen a base64 para mostrar en Streamlit
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return totp_secret, img_str, recovery_codes

def disable_2fa(user_id):
    """Deshabilita 2FA para un usuario"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE usuarios SET totp_secret = NULL, is_2fa_enabled = 0 WHERE id = ?", (user_id,))
    
    # Eliminar códigos de recuperación
    c.execute("DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))
    
    conn.commit()
    conn.close()
    return True

def is_2fa_enabled(user_id):
    """Verifica si el usuario tiene 2FA habilitado"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT is_2fa_enabled FROM usuarios WHERE id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    return result and result[0] == 1

def get_user_info(user_id):
    """Obtiene información del usuario"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT nombre, apellido, username, email FROM usuarios WHERE id = ?', (user_id,))
    user_info = c.fetchone()
    conn.close()
    return user_info

def logout():
    """Función para desloguear y limpiar el estado"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]