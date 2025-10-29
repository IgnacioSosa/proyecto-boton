import streamlit as st
import os
import subprocess
from modules.database import get_connection, test_connection 
from modules.utils import apply_custom_css, initialize_session_state
from modules.ui_components import render_login_tabs, render_sidebar_profile
from modules.admin_panel import render_admin_panel
from modules.user_dashboard import render_user_dashboard
from modules.visor_dashboard import render_visor_dashboard
from modules.logging_utils import log_app_error

# Configuración inicial de la página
st.set_page_config(page_title="Sistema de Registro de Horas", layout="wide", initial_sidebar_state="collapsed")

def check_database_connection():
    """Verifica la conexión a PostgreSQL de manera simple"""
    try:
        # Usar la función test_connection que es más segura
        if test_connection():
            return True
        else:
            st.warning("⚠️ No se puede conectar a PostgreSQL. Ejecuta regenerate_database.py primero.")
            st.code("python regenerate_database.py")
            st.stop()
            return False
    except Exception as e:
        st.error(f"❌ Error de conexión a la base de datos: {str(e)}")
        st.warning("🔧 Solución: Ejecuta el script de reset:")
        st.code("python regenerate_database.py")
        st.stop()
        return False

def get_user_info_safe(user_id):
    """Obtiene información del usuario de manera segura"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT id, username, is_admin, rol_id, nombre, apellido, email
            FROM usuarios 
            WHERE id = %s AND is_active = TRUE
        """, (user_id,))
        result = c.fetchone()
        conn.close()
        
        if result:
            return {
                'id': result[0],
                'username': result[1],
                'is_admin': result[2],
                'rol_id': result[3],
                'nombre': result[4] or '',
                'apellido': result[5] or '',
                'email': result[6] or ''
            }
        return None
    except Exception as e:
        log_app_error(e, module="app", function="get_user_info_safe")
        return None

def get_user_rol_id_safe(user_id):
    """Obtiene el rol del usuario de manera segura"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT rol_id FROM usuarios WHERE id = %s", (user_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        log_app_error(e, module="app", function="get_user_rol_id_safe")
        return None

# Verificar conexión a la base de datos
if not check_database_connection():
    st.stop()

def main():
    """Función principal de la aplicación"""
    apply_custom_css()
    initialize_session_state()
    
    if st.session_state.user_id is None:
        render_login_tabs()
    else:
        render_authenticated_app()

def render_authenticated_app():
    """Renderiza la aplicación para usuarios autenticados"""
    user_info = get_user_info_safe(st.session_state.user_id)
    
    if user_info is None:
        st.session_state.user_id = None
        st.session_state.is_admin = False
        st.rerun()
    
    nombre_actual = user_info['nombre'] if user_info['nombre'] else ''
    apellido_actual = user_info['apellido'] if user_info['apellido'] else ''
    nombre_completo_usuario = f"{nombre_actual} {apellido_actual}".strip()
    
    
    render_sidebar_profile(user_info)
    
    # Obtener el rol del usuario
    rol_id = get_user_rol_id_safe(st.session_state.user_id)
    
    # Obtener el nombre del rol de manera segura
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT nombre FROM roles WHERE id_rol = %s", (rol_id,))
        result = c.fetchone()
        rol_nombre = result[0] if result else None
        conn.close()
    except Exception as e:
        log_app_error(e, module="app", function="render_authenticated_app")
        rol_nombre = None
    
    # Renderizar el dashboard correspondiente según el rol
    if rol_nombre == 'hipervisor':
        render_visor_dashboard(st.session_state.user_id, nombre_completo_usuario)
    elif rol_nombre == 'visor':
        from modules.visor_dashboard import render_visor_only_dashboard
        render_visor_only_dashboard()
    elif st.session_state.is_admin:
        render_admin_panel()
    else:
        render_user_dashboard(st.session_state.user_id, nombre_completo_usuario)

if __name__ == "__main__":
    main()
