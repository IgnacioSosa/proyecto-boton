import extra_streamlit_components as stx
import streamlit as st
from modules.auth import verify_signed_session_params, make_signed_session_params
from modules.database import get_user_info_safe
from datetime import datetime, timedelta

# Singleton for CookieManager
def init_cookie_manager():
    """Initializes the cookie manager component. Must be called once per script run."""
    st.session_state['_auth_cookie_manager'] = stx.CookieManager(key="auth_cookie_manager")

def get_cookie_manager():
    """Returns the initialized cookie manager instance."""
    if '_auth_cookie_manager' not in st.session_state:
        # Fallback if init wasn't called (shouldn't happen with correct usage)
        init_cookie_manager()
    return st.session_state['_auth_cookie_manager']

def get_session_cookie():
    cookie_manager = get_cookie_manager()
    # "get" triggers a rerun if value is not yet available in frontend
    return cookie_manager.get("user_session")

def set_session_cookie(user_id):
    cookie_manager = get_cookie_manager()
    # Create signed token
    # 30 days expiration
    params = make_signed_session_params(user_id, ttl_seconds=30 * 24 * 60 * 60)
    
    # Value format: uid.uexp.usig
    cookie_value = f"{params['uid']}.{params['uexp']}.{params['usig']}"
    
    # Set cookie with 30 days expiry
    expires_at = datetime.now() + timedelta(days=30)
    cookie_manager.set("user_session", cookie_value, expires_at=expires_at)

def delete_session_cookie():
    cookie_manager = get_cookie_manager()
    try:
        cookie_manager.delete("user_session")
    except Exception:
        # Ignorar error si la cookie ya no existe
        pass

def check_auth_cookie():
    """
    Checks for a valid session cookie and restores session state if found.
    Returns True if session restored or already valid, False otherwise.
    """
    if st.session_state.get("user_id") is not None:
        return True # Already logged in

    # Si estamos en proceso de logout, no intentar restaurar sesión
    if st.session_state.get('logout_in_progress', False):
        return False

    token = get_session_cookie()
    
    if token:
        try:
            parts = token.split('.')
            if len(parts) == 3:
                uid, uexp, usig = parts
                if verify_signed_session_params(uid, uexp, usig):
                    # Valid token!
                    user_id = int(uid)
                    
                    # Verify user still exists and get details
                    user_info = get_user_info_safe(user_id)
                    
                    if user_info:
                        st.session_state.user_id = user_info['id']
                        st.session_state.is_admin = bool(user_info['is_admin'])
                        st.session_state.username = user_info['username']
                        st.session_state.mostrar_perfil = False
                        return True
                    else:
                        # User not found (deleted?), delete cookie
                        delete_session_cookie()
        except Exception as e:
            print(f"Cookie validation error: {e}")
            pass
            
    return False
