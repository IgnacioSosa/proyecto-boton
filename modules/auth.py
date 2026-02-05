import bcrypt
import streamlit as st
from .database import get_connection
from .config import SYSTEM_ROLES, PASSWORD_CONFIG
from .config import APP_SESSION_SECRET
import hmac, hashlib, time

def hash_password(password):
    """Genera hash de contraseña usando bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, hashed):
    """Verifica contraseña contra hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def make_signed_session_params(user_id: int, ttl_seconds: int = 24 * 60 * 60):
    """Genera parámetros firmados para persistir sesión en el URL.
    Retorna dict con 'uid', 'uexp', 'usig'.
    """
    try:
        exp = int(time.time()) + int(ttl_seconds)
    except Exception:
        exp = int(time.time()) + 24 * 60 * 60
    payload = f"{int(user_id)}.{exp}"
    sig = hmac.new(APP_SESSION_SECRET.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return {"uid": str(int(user_id)), "uexp": str(exp), "usig": sig}

def verify_signed_session_params(uid: str, uexp: str, usig: str) -> bool:
    """Valida que 'uid' en el URL corresponda a una firma HMAC válida y no esté expirado."""
    try:
        uid_i = int(uid)
        exp_i = int(uexp)
    except Exception:
        return False
    if exp_i < int(time.time()):
        return False
    payload = f"{uid_i}.{exp_i}"
    expected = hmac.new(APP_SESSION_SECRET.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(str(usig or ''), expected)
    except Exception:
        return False

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
    """Autentica un usuario y, si tiene 2FA, prepara la verificación TOTP. Aplica bloqueo por intentos fallidos."""
    from datetime import datetime, timedelta
    from .config import (
        FAILED_LOGIN_MAX_ATTEMPTS,
        LOCKOUT_MINUTES,
        ADMIN_FAILED_LOGIN_MAX_ATTEMPTS,
        ADMIN_LOCKOUT_MINUTES,
    )
    conn = get_connection()
    c = conn.cursor()
    
    try:
        # Normalizar identificador: aceptar username o email (cualquier dominio)
        raw_identifier = (username or "").strip()
        canonical_username = raw_identifier.split("@")[0].strip() if "@" in raw_identifier else raw_identifier

        # Búsqueda case-insensitive por username (normalizado) o email (exacto)
        c.execute('''
            SELECT id, password_hash, is_active, is_admin, is_2fa_enabled,
                   nombre, apellido, email, rol_id, username,
                   failed_attempts, lockout_until
            FROM usuarios
            WHERE LOWER(username) = LOWER(%s)
               OR LOWER(email) = LOWER(%s)
        ''', (canonical_username, raw_identifier))
        user = c.fetchone()
        
        if not user:
            st.error("Usuario o contraseña incorrectos.")
            conn.close()
            return False, False
        
        user_id = user[0]
        password_hash = user[1]
        is_active = bool(user[2])
        is_admin = bool(user[3])
        is_2fa = bool(user[4])
        failed_attempts = int(user[10] or 0)
        lockout_until = user[11]  # Puede ser None o datetime
        
        # Rechazar si está bloqueado por tiempo
        now = datetime.utcnow()
        if lockout_until and now < lockout_until:
            remaining = int((lockout_until - now).total_seconds() // 60) + 1
            st.error(f"La cuenta está temporalmente bloqueada. Intenta nuevamente en ~{remaining} minuto(s).")
            conn.close()
            return False, False
        
        # Validar contraseña
        if user and verify_password(password, password_hash):
            if not is_active:
                st.error("La cuenta está pendiente de activación por un administrador.")
                conn.close()
                return False, False
            
            # Al éxito, limpiar intentos y bloqueo
            c.execute('''
                UPDATE usuarios
                SET failed_attempts = 0, lockout_until = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (user_id,))
            conn.commit()
            
            if is_2fa:
                st.session_state['awaiting_2fa'] = True
                st.session_state['temp_user_id'] = user_id
                st.session_state['temp_is_admin'] = is_admin
                st.session_state['temp_username'] = user[9]
                st.session_state['temp_nombre'] = user[5] or ''
                st.session_state['temp_apellido'] = user[6] or ''
                st.session_state['temp_email'] = user[7] or ''
                st.session_state['temp_rol_id'] = user[8]
                conn.close()
                return False, False
            else:
                conn.close()
                return user_id, is_admin
        else:
            # Contraseña incorrecta: incrementar intentos y evaluar bloqueo
            failed_attempts += 1
            max_attempts = ADMIN_FAILED_LOGIN_MAX_ATTEMPTS if is_admin else FAILED_LOGIN_MAX_ATTEMPTS
            lock_minutes = ADMIN_LOCKOUT_MINUTES if is_admin else LOCKOUT_MINUTES
            
            if failed_attempts >= max_attempts:
                new_lockout_until = now + timedelta(minutes=lock_minutes)
                c.execute('''
                    UPDATE usuarios
                    SET failed_attempts = 0, lockout_until = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (new_lockout_until, user_id))
                conn.commit()
                st.error(f"Demasiados intentos fallidos. La cuenta queda bloqueada por {lock_minutes} minuto(s).")
            else:
                c.execute('''
                    UPDATE usuarios
                    SET failed_attempts = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (failed_attempts, user_id))
                conn.commit()
                st.error(f"Usuario o contraseña incorrectos. Intentos fallidos: {failed_attempts}/{max_attempts}.")
            
            conn.close()
            return False, False
    except Exception as e:
        print(f"Error en login_user: {e}")
        conn.close()
        return False, False

# Funciones 2FA simplificadas (deshabilitadas temporalmente)
def verify_2fa_code(code):
    """Verifica el código TOTP y completa el login si es correcto"""
    import pyotp
    try:
        temp_user_id = st.session_state.get('temp_user_id')
        if not temp_user_id:
            return False
        
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT totp_secret, is_admin, username, nombre, apellido, email, rol_id FROM usuarios WHERE id = %s", (temp_user_id,))
        row = c.fetchone()
        conn.close()
        if not row or not row[0]:
            return False
        
        secret = row[0]
        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            return False
        
        # Completar login
        st.session_state.user_id = temp_user_id
        st.session_state.is_admin = bool(row[1])
        st.session_state.username = row[2]  # Guardar username en sesión
        st.session_state.mostrar_perfil = False

        # Persistir sesión firmada en el URL
        try:
            signed = make_signed_session_params(temp_user_id)
            st.query_params.update(signed)
        except Exception:
            pass
        
        # Limpiar flags temporales
        for key in ['awaiting_2fa', 'temp_user_id', 'temp_username', 'temp_is_admin',
                    'temp_nombre', 'temp_apellido', 'temp_email', 'temp_rol_id']:
            if key in st.session_state:
                del st.session_state[key]
        return True
    except Exception as e:
        st.error(f"Error verificando 2FA: {e}")
        return False

def enable_2fa(user_id):
    """Habilita 2FA: genera secreto TOTP, guarda en DB y retorna QR en base64"""
    import pyotp, qrcode, io, base64
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT username FROM usuarios WHERE id = %s", (user_id,))
        row = c.fetchone()
        username = row[0] if row else f"user_{user_id}"
        
        # Generar secreto y URI de aprovisionamiento
        secret = pyotp.random_base32()
        uri = pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="Sistema Registro de Horas")
        
        # Generar QR en base64
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        
        # Guardar en DB y habilitar 2FA
        c.execute("UPDATE usuarios SET is_2fa_enabled = TRUE, totp_secret = %s WHERE id = %s", (secret, user_id))
        conn.commit()
        conn.close()
        
        # (Opcional) Códigos de recuperación: de momento retornamos lista vacía
        recovery_codes = []
        return secret, qr_b64, recovery_codes
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except:
            pass
        st.error(f"Error habilitando 2FA: {e}")
        return "ERROR", "", []

def disable_2fa(user_id):
    """Deshabilita 2FA: limpia el secreto y desactiva el flag"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE usuarios SET is_2fa_enabled = FALSE, totp_secret = NULL WHERE id = %s", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except:
            pass
        st.error(f"Error deshabilitando 2FA: {e}")
        return False

def is_2fa_enabled(user_id):
    """Verifica si un usuario tiene 2FA habilitado (lectura real de DB)"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT is_2fa_enabled FROM usuarios WHERE id = %s", (user_id,))
        row = c.fetchone()
        conn.close()
        return bool(row[0]) if row else False
    except Exception as e:
        st.error(f"Error consultando 2FA: {e}")
        return False

def unlock_user(username: str) -> bool:
    """Desbloquea manualmente un usuario: limpia failed_attempts y lockout_until. Usar desde panel o script."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT id FROM usuarios WHERE username = %s', (username,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False
        user_id = row[0]
        c.execute('''
            UPDATE usuarios
            SET failed_attempts = 0, lockout_until = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except:
            pass
        print(f"Error desbloqueando usuario {username}: {e}")
        return False

def logout():
    """Función para desloguear y limpiar el estado"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    # Limpiar parámetros de sesión del URL
    try:
        st.query_params.pop("uid", None)
        st.query_params.pop("uexp", None)
        st.query_params.pop("usig", None)
        # También limpiar selección de tarjetas
        st.query_params.pop("myproj", None)
        st.query_params.pop("sharedproj", None)
    except Exception:
        pass
    # Limpiar uid y selección de tarjetas del URL
    try:
        st.query_params.pop("uid", None)
        st.query_params.pop("myproj", None)
        st.query_params.pop("sharedproj", None)
    except Exception:
        pass