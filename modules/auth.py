import streamlit as st
import bcrypt
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
    c.execute("SELECT id, password, is_admin, nombre, apellido, rol_id, grupo_id, is_active FROM usuarios WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    
    if user and user[7] == 1:  # Verificar que el usuario esté activo
        stored_password = user[1]
        if verify_password(password, stored_password):
            # Establecer variables de sesión
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
            
            # Devolver user_id e is_admin como una tupla
            return user[0], bool(user[2])
    return None, False  # Devolver None, False si el login falla
    c.execute('SELECT id, password, is_admin, is_active FROM usuarios WHERE username = ?', (username,))
    user = c.fetchone()
    
    if user and verify_password(password, user[1]):
        if user[3]: # is_active
            # Obtener el nombre y apellido del usuario
            c.execute('SELECT nombre, apellido FROM usuarios WHERE id = ?', (user[0],))
            user_info = c.fetchone()
            
            # Si el usuario tiene nombre y apellido, verificar si existe como técnico
            if user_info and (user_info[0] or user_info[1]):
                nombre_completo = f"{user_info[0] or ''} {user_info[1] or ''}".strip()
                if nombre_completo:
                    # Verificar si el técnico ya existe
                    c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = ?', (nombre_completo,))
                    tecnico = c.fetchone()
                    if not tecnico:
                        # Crear el técnico si no existe
                        c.execute('INSERT INTO tecnicos (nombre) VALUES (?)', (nombre_completo,))
                        conn.commit()
            
            conn.close()
            return user[0], user[2] # user_id, is_admin
    conn.close()
    return None, None

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
    st.session_state.user_id = None
    st.session_state.is_admin = False
    st.session_state.mostrar_perfil = False