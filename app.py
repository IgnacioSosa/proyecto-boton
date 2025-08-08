import streamlit as st
from modules.database import init_db
from modules.auth import get_user_info
from modules.utils import apply_custom_css, initialize_session_state
from modules.ui_components import render_login_tabs, render_sidebar_profile
from modules.admin_panel import render_admin_panel
from modules.user_dashboard import render_user_dashboard

# Configuración inicial de la página
st.set_page_config(page_title="Sistema de Registro de Horas", layout="wide")

# Inicializar la base de datos
init_db()

def main():
    """Función principal de la aplicación"""
    # Aplicar CSS personalizado
    apply_custom_css()
    
    # Inicializar estado de sesión
    initialize_session_state()
    
    if st.session_state.user_id is None:
        # Usuario no autenticado - mostrar login/registro
        render_login_tabs()
    else:
        # Usuario autenticado - mostrar aplicación principal
        render_authenticated_app()

def render_authenticated_app():
    """Renderiza la aplicación para usuarios autenticados"""
    # Obtener información del usuario
    user_info = get_user_info(st.session_state.user_id)
    
    # Si el usuario fue eliminado de la BD mientras estaba logueado, lo deslogueamos
    if user_info is None:
        st.session_state.user_id = None
        st.session_state.is_admin = False
        st.rerun()
    
    nombre_actual = user_info[0] if user_info[0] else ''
    apellido_actual = user_info[1] if user_info[1] else ''
    nombre_completo_usuario = f"{nombre_actual} {apellido_actual}".strip()
    
    # Renderizar perfil en barra lateral
    render_sidebar_profile(user_info)
    
    # Renderizar contenido principal según el tipo de usuario
    if st.session_state.is_admin:
        render_admin_panel()
    else:
        render_user_dashboard(st.session_state.user_id, nombre_completo_usuario)

if __name__ == "__main__":
    main()