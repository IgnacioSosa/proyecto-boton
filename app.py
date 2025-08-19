import streamlit as st
import os
import subprocess
from modules.database import init_db, get_user_rol_id, get_connection
from modules.auth import get_user_info
from modules.utils import apply_custom_css, initialize_session_state
from modules.ui_components import render_login_tabs, render_sidebar_profile
from modules.admin_panel import render_admin_panel
from modules.user_dashboard import render_user_dashboard
from modules.visor_dashboard import render_visor_dashboard

# Configuración inicial de la página
st.set_page_config(page_title="Sistema de Registro de Horas", layout="wide")

def check_and_regenerate_database():
    """Verifica si existe la base de datos y la regenera si es necesario"""
    if not os.path.exists('trabajo.db'):
        st.warning("⚠️ Base de datos no encontrada. Regenerando...")
        try:
            result = subprocess.run(['python', 'regenerate_database.py', '--auto'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                st.success("✅ Base de datos regenerada exitosamente")
            else:
                st.error(f"❌ Error al regenerar la base de datos: {result.stderr}")
                return False
        except Exception as e:
            st.error(f"❌ Error al ejecutar regeneración: {str(e)}")
            init_db()  # Fallback
    else:
        init_db()  # Inicialización normal
    return True

# Verificar y regenerar base de datos si es necesario
if not check_and_regenerate_database():
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
    user_info = get_user_info(st.session_state.user_id)
    
    if user_info is None:
        st.session_state.user_id = None
        st.session_state.is_admin = False
        st.rerun()
    
    nombre_actual = user_info[0] if user_info[0] else ''
    apellido_actual = user_info[1] if user_info[1] else ''
    nombre_completo_usuario = f"{nombre_actual} {apellido_actual}".strip()
    
    render_sidebar_profile(user_info)
    
    # Obtener el rol del usuario
    rol_id = get_user_rol_id(st.session_state.user_id)
    
    # Obtener el nombre del rol
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT nombre FROM roles WHERE id_rol = ?", (rol_id,))
    result = c.fetchone()
    rol_nombre = result[0] if result else None
    conn.close()
    
    # Renderizar el dashboard correspondiente según el rol
    if rol_nombre == 'hipervisor':
        render_visor_dashboard(st.session_state.user_id, nombre_completo_usuario)
    elif st.session_state.is_admin:
        render_admin_panel()
    else:
        render_user_dashboard(st.session_state.user_id, nombre_completo_usuario)

if __name__ == "__main__":
    main()