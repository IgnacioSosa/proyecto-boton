import streamlit as st
import os
import subprocess
from modules.database import get_connection, test_connection, ensure_system_roles, merge_role_alias
from modules.utils import apply_custom_css, initialize_session_state
from modules.auth import verify_signed_session_params
from modules.ui_components import render_login_tabs, render_sidebar_profile, render_no_view_dashboard, render_db_config_screen
from modules.config import update_env_values, UPLOADS_DIR, PROJECT_UPLOADS_DIR
from modules.admin_panel import render_admin_panel
from modules.user_dashboard import render_user_dashboard
from modules.visor_dashboard import render_visor_dashboard
from modules.logging_utils import log_app_error

# Configuración inicial de la página
st.set_page_config(page_title="Sistema de Registro de Horas", layout="wide", initial_sidebar_state="collapsed")

def check_database_connection():
    """Verifica la conexión a PostgreSQL y la existencia de tablas básicas"""
    try:
        # Usar la función test_connection que es más segura
        if test_connection():
            # Verificar si la tabla usuarios existe
            try:
                conn = get_connection()
                c = conn.cursor()
                c.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'usuarios'")
                exists = c.fetchone()
                
                if not exists:
                    conn.close()
                    # Conexión ok pero sin tablas -> Mostrar pantalla de configuración/inicialización
                    st.warning("⚠️ La base de datos está conectada pero vacía.")
                    st.session_state['connection_success'] = True
                    st.session_state['admin_not_found'] = True
                    render_db_config_screen()
                    return False
                
                # Verificar si existe al menos un administrador
                c.execute("SELECT 1 FROM usuarios WHERE is_admin = TRUE LIMIT 1")
                admin_exists = c.fetchone()
                conn.close()

                if not admin_exists:
                    st.warning("⚠️ No se detectó ningún usuario administrador.")
                    st.session_state['connection_success'] = True
                    st.session_state['admin_not_found'] = True
                    render_db_config_screen()
                    return False

                return True
            except Exception as e:
                # Si falla la verificación de tablas/admin, asumir problema y mostrar config
                log_app_error(e, module="app", function="check_database_connection")
                render_db_config_screen()
                return False
        else:
            # Mostrar pantalla de configuración en lugar de regenerar automáticamente
            render_db_config_screen()
            return False
    except Exception as e:
        st.error(f"❌ Error de conexión a la base de datos: {str(e)}")
        render_db_config_screen()
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
    try:
        ensure_system_roles()
    except Exception:
        pass
    try:
        from modules.database import ensure_roles_view_type_column
        ensure_roles_view_type_column()
    except Exception:
        pass
    try:
        merge_role_alias('sin_rol', 'Sin Rol')
    except Exception:
        pass
    # Rehidratar sesión firmada desde el URL
    try:
        params = st.query_params
        if st.session_state.user_id is None:
            # Helper to safely get param value (string)
            def get_param(key):
                val = params.get(key)
                if val is None: return None
                if isinstance(val, list): return val[0]
                return val

            uid = get_param("uid")
            uexp = get_param("uexp")
            usig = get_param("usig")

            if uid and uexp and usig:
                if verify_signed_session_params(uid, uexp, usig):
                    user_info = get_user_info_safe(int(uid))
                    if user_info:
                        st.session_state.user_id = user_info['id']
                        st.session_state.is_admin = bool(user_info['is_admin'])
                else:
                    # Firma inválida
                    pass
    except Exception as e:
        log_app_error(e, module="app", function="session_rehydration")
    
    # Rehidratar sesión desde el URL si hay uid
    try:
        params = st.query_params
        if st.session_state.user_id is None and "uid" in params:
            raw = params["uid"]
            uid_str = raw[0] if isinstance(raw, list) else raw
            uid = int(uid_str)
            info = get_user_info_safe(uid)
            if info:
                st.session_state.user_id = info["id"]
                st.session_state.is_admin = bool(info["is_admin"])
    except Exception:
        pass

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
        st.session_state.username = None
        st.rerun()
    
    # Asegurar que el username esté en session_state
    st.session_state.username = user_info['username']
    
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
        c.execute("SELECT nombre, view_type FROM roles WHERE id_rol = %s", (rol_id,))
        result = c.fetchone()
        rol_nombre = result[0] if result else None
        rol_view = result[1] if result else None
        conn.close()
    except Exception as e:
        log_app_error(e, module="app", function="render_authenticated_app")
        rol_nombre = None
        rol_view = None
    
    def get_counts():
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM nomina WHERE activo = TRUE")
            nomina_count = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM usuarios WHERE is_admin = FALSE")
            usuarios_count = c.fetchone()[0]
            try:
                c.execute("SELECT COUNT(*) FROM registros")
                registros_count = c.fetchone()[0]
            except Exception:
                registros_count = 0
            conn.close()
            return {'nomina': nomina_count, 'usuarios': usuarios_count, 'registros': registros_count}
        except Exception:
            return {'nomina': 0, 'usuarios': 0, 'registros': 0}
    
    def render_onboarding_wizard():
        counts = get_counts()
        if 'onboarding_step' not in st.session_state:
            st.session_state.onboarding_step = 1
        st.header("Configuración inicial")
        st.caption("Paso 1: Subir planilla de nómina • Paso 2: Generar usuarios • Paso 3: Rutas de almacenamiento • Paso 4: Subir registros")
        step = st.session_state.onboarding_step
        if step == 1:
            from modules.nomina_management import render_nomina_management
            render_nomina_management(is_wizard=True)
        elif step == 2:
            st.subheader("Generar usuarios desde nómina")
            enable_users = st.checkbox("Habilitar usuarios al crear", value=False)
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🚀 Iniciar Generación de Usuarios"):
                    from modules.database import generate_users_from_nomina
                    with st.spinner("Generando usuarios..."):
                        stats = generate_users_from_nomina(enable_users=enable_users)
                    st.success(f"Usuarios creados: {stats.get('usuarios_creados', 0)}")
                    if stats.get('usuarios_creados', 0) > 0:
                        st.session_state.onboarding_step = 3
                        st.rerun()
            with col2:
                if counts['usuarios'] > 0:
                    if st.button("Siguiente: Rutas de almacenamiento ➡️", type="primary"):
                        st.session_state.onboarding_step = 3
                        st.rerun()

        elif step == 3:
            st.subheader("Definir rutas de almacenamiento")
            
            # Obtener valores actuales (prioridad: os.environ > config > default)
            current_uploads = os.getenv('UPLOADS_DIR', UPLOADS_DIR)
            current_projects = os.getenv('PROJECT_UPLOADS_DIR', PROJECT_UPLOADS_DIR)
            
            new_uploads = st.text_input("Carpeta base de uploads (UPLOADS_DIR)", value=current_uploads)
            new_projects = st.text_input("Carpeta de proyectos (PROJECT_UPLOADS_DIR)", value=current_projects)
            
            if st.button("Guardar y Continuar ➡️", type="primary"):
                # Actualizar .env
                if update_env_values({'UPLOADS_DIR': new_uploads, 'PROJECT_UPLOADS_DIR': new_projects}):
                    # Actualizar variables en memoria para la sesión actual
                    os.environ['UPLOADS_DIR'] = new_uploads
                    os.environ['PROJECT_UPLOADS_DIR'] = new_projects
                    import modules.config
                    modules.config.UPLOADS_DIR = new_uploads
                    modules.config.PROJECT_UPLOADS_DIR = new_projects
                    
                    st.success("Rutas actualizadas correctamente")
                    st.session_state.onboarding_step = 4
                    st.rerun()
                else:
                    st.error("Error al guardar la configuración en .env")
                        
        elif step == 4:
            st.subheader("Cargar registros")
            
            # Checkbox para saltar este paso
            skip_records = st.checkbox("Prefiero cargarlos más tarde")
            
            if not skip_records:
                from modules.admin_records import render_records_import
                render_records_import()
            
            counts = get_counts()
            
            # Mostrar botón finalizar si hay registros cargados O si el usuario decide saltar este paso
            if counts['registros'] > 0 or skip_records:
                st.divider()
                if st.button("Finalizar y Ir al Panel", type="primary"):
                     if 'onboarding_step' in st.session_state:
                         del st.session_state.onboarding_step
                     st.rerun()
                if counts['registros'] > 0:
                    st.success("Configuración inicial completada con registros cargados")
                else:
                    st.info("Configuración inicial completada (sin carga inicial de registros)")

    
    # Renderizar el dashboard correspondiente según el rol
    if st.session_state.is_admin:
        counts = get_counts()
        # Mostrar wizard si faltan datos o si estamos explícitamente en el paso 3 o 4
        show_wizard = (counts['nomina'] == 0 or counts['usuarios'] == 0)
        
        if 'onboarding_step' in st.session_state and st.session_state.onboarding_step in [3, 4]:
            show_wizard = True
            
        if show_wizard:
            render_onboarding_wizard()
        else:
            render_admin_panel()
    else:
        if rol_view == 'hipervisor':
            render_visor_dashboard(st.session_state.user_id, nombre_completo_usuario)
        elif rol_view == 'admin_tecnico':
            from modules.visor_dashboard import render_visor_only_dashboard
            render_visor_only_dashboard()
        elif rol_view == 'admin_comercial' or (rol_nombre == 'adm_comercial' and not rol_view):
            from modules.visor_dashboard import render_adm_comercial_dashboard
            render_adm_comercial_dashboard(st.session_state.user_id)
        elif rol_view == 'comercial':
            from modules.commercial_projects import render_commercial_projects
            render_commercial_projects(st.session_state.user_id, nombre_completo_usuario)
        elif rol_view == 'tecnico':
            render_user_dashboard(st.session_state.user_id, nombre_completo_usuario)
        else:
            render_no_view_dashboard(nombre_completo_usuario)

if __name__ == "__main__":
    main()
