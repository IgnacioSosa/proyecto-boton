import streamlit as st
import os
import time
import subprocess
from modules.database import get_connection, test_connection, ensure_system_roles, merge_role_alias, get_user_info_safe, process_automatic_notifications
from modules.utils import apply_custom_css, initialize_session_state, safe_rerun
from modules.ui_components import render_login_tabs, render_sidebar_profile, render_no_view_dashboard, render_db_config_screen
from modules.cookie_auth import check_auth_cookie, init_cookie_manager
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

# Verificar conexión a la base de datos
if not check_database_connection():
    st.stop()

def main():
    """Función principal de la aplicación"""
    apply_custom_css()
    initialize_session_state()

    # Initialize cookie manager ONCE per run
    init_cookie_manager()

    # Check for persisted session via cookie
    # This renders the component and attempts to restore session
    check_auth_cookie()

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
        from modules.database import ensure_clientes_schema, ensure_projects_schema, ensure_contactos_schema, ensure_cliente_solicitudes_schema
        ensure_clientes_schema()
        ensure_projects_schema()
        ensure_contactos_schema()
        ensure_cliente_solicitudes_schema()
    except Exception:
        pass
    try:
        merge_role_alias('Sin Rol', 'sin_rol')
    except Exception:
        pass
    try:
        from modules.database import fix_administracion_department_role
        fix_administracion_department_role()
    except Exception:
        pass

    try:
        current_ts = time.time()
        last_notification_run = float(st.session_state.get("automatic_notification_last_run", 0.0) or 0.0)
        if current_ts - last_notification_run >= 60:
            process_automatic_notifications()
            st.session_state["automatic_notification_last_run"] = current_ts
    except Exception as e:
        log_app_error(e, module="app", function="main.process_automatic_notifications")


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
        safe_rerun()
    
    # Asegurar que el username esté en session_state
    st.session_state.username = user_info['username']

    # Restaurar paso del wizard desde URL si es necesario (para persistencia entre recargas por cambios en .env)
    if 'onboarding_step' not in st.session_state and "onboarding_step" in st.query_params:
        try:
            step_val = st.query_params["onboarding_step"]
            # Manejar si es lista o valor único
            if isinstance(step_val, list):
                step_val = step_val[0]
            st.session_state.onboarding_step = int(step_val)
        except Exception:
            pass
    
    nombre_actual = user_info['nombre'] if user_info['nombre'] else ''
    apellido_actual = user_info['apellido'] if user_info['apellido'] else ''
    nombre_completo_usuario = f"{nombre_actual} {apellido_actual}".strip()
    
    
    render_sidebar_profile(user_info)
    
    # Obtener el rol del usuario
    rol_id = user_info['rol_id']
    
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
            st.session_state.onboarding_step = 0
            
        step = st.session_state.onboarding_step
        
        if step == 0:
            # CSS para centrar verticalmente el contenido de las columnas (alinear texto con botones grandes)
            st.markdown("""
            <style>
            div[data-testid="column"] {
                display: flex;
                flex-direction: column;
                justify-content: center;
            }
            </style>
            """, unsafe_allow_html=True)

            st.title("Bienvenido al Asistente de Configuración")
            st.write("Este asistente te guiará en la configuración inicial del sistema.")
            st.write("---")
            
            if st.session_state.get('show_restore_wizard', False):
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.button("🚀 Nuevo Despliegue", type="primary", use_container_width=True, disabled=True)
                    
                    st.write("")
                    st.button("🔄 Restaurar Backup", type="primary", use_container_width=True, disabled=True)
                
                with col2:
                    st.subheader("Restaurar Copia de Seguridad")
                    st.warning("⚠️ Esta acción reemplazará toda la base de datos actual con el contenido del backup.")
                    
                    uploaded_file = st.file_uploader("Subir archivo de respaldo (.xlsx)", type=["xlsx"], key="restore_wizard_uploader")
                    
                    if uploaded_file:
                        if st.button("Confirmar Restauración", type="primary", use_container_width=True):
                            from modules.backup_utils import restore_full_backup_excel
                            with st.spinner("Restaurando base de datos..."):
                                success, msg = restore_full_backup_excel(uploaded_file)
                                if success:
                                    from modules.utils import show_success_message
                                    show_success_message(msg, 2)
                                    st.session_state.wizard_completed = True
                                    if 'onboarding_step' in st.session_state:
                                        del st.session_state.onboarding_step
                                    # Limpiar query params
                                    if "onboarding_step" in st.query_params:
                                        try:
                                            st.query_params.clear()
                                        except:
                                            pass
                                    safe_rerun()
                                else:
                                    st.error(msg)
                    
                    if st.button("Cancelar"):
                        st.session_state.show_restore_wizard = False
                        safe_rerun()
            else:
                col1, col2 = st.columns([1, 2])
                with col1:
                    if st.button("🚀 Nuevo Despliegue", type="primary", use_container_width=True):
                        st.session_state.onboarding_step = 1
                        st.session_state.show_restore_wizard = False
                        safe_rerun()
                with col2:
                    st.info("Selecciona esta opción para configurar el sistema desde cero (importar nómina, generar usuarios, etc.)")
                
                st.write("")
                
                col1, col2 = st.columns([1, 2])
                with col1:
                    if st.button("🔄 Restaurar Backup", type="primary", use_container_width=True):
                        st.session_state.show_restore_wizard = True
                        safe_rerun()
                with col2:
                    st.info("Selecciona esta opción para restaurar el sistema a partir de un archivo de respaldo (.xlsx).")
                
        else:
            st.header("Configuración inicial")
            st.caption("Paso 1: Subir planilla de nómina • Paso 2: Generar usuarios • Paso 3: Gestión de Clientes • Paso 4: Rutas de almacenamiento • Paso 5: Subir registros")
            
            if step == 1:
                from modules.nomina_management import render_nomina_management
                render_nomina_management(is_wizard=True)
            elif step == 2:
                st.subheader("Generar usuarios desde nómina")
                
                if st.session_state.get('last_generation_stats'):
                    stats = st.session_state.last_generation_stats
                    st.success(f"Proceso completado. Usuarios creados: {stats.get('usuarios_creados', 0)}")
                    
                    if stats.get('usuarios_generados'):
                        import pandas as pd
                        df_creds = pd.DataFrame(stats['usuarios_generados'])
                        cols_to_show = [c for c in ['nombre', 'apellido', 'username', 'password', 'email', 'activo'] if c in df_creds.columns]
                        df_creds = df_creds[cols_to_show]
                        
                        csv = df_creds.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label="📥 Descargar Planilla de Credenciales",
                            data=csv,
                            file_name="credenciales_generadas.csv",
                            mime="text/csv",
                        )
                    
                    if st.button("Continuar al siguiente paso ➡️", type="primary"):
                        del st.session_state.last_generation_stats
                        st.session_state.onboarding_step = 3
                        st.query_params["onboarding_step"] = "3"
                        safe_rerun()
                else:
                    enable_users = st.checkbox("Habilitar usuarios al crear", value=False)
                    
                    # Ajuste de columnas para responsividad en monitores pequeños
                    # Usamos st.columns(2) para dividir el espacio equitativamente (50% cada uno)
                    # Esto asegura que en resoluciones bajas ambos botones tengan el máximo espacio disponible
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if st.button("🚀 Iniciar Generación de Usuarios", use_container_width=True):
                            from modules.database import generate_users_from_nomina
                            with st.spinner("Generando usuarios..."):
                                stats = generate_users_from_nomina(enable_users=enable_users)
                            
                            st.session_state.last_generation_stats = stats
                            safe_rerun()
                    
                    with col2:
                        if st.button("No deseo generar usuarios", use_container_width=True):
                            st.session_state.skipped_user_generation = True
                            st.session_state.onboarding_step = 3
                            st.query_params["onboarding_step"] = "3"
                            safe_rerun()
                        
                    if counts['usuarios'] > 0:
                        st.caption(f"Actualmente hay {counts['usuarios']} usuarios en el sistema.")

            elif step == 3:
                # Paso 3: Gestión de Clientes (Nuevo)
                from modules.admin_clients import render_client_crud_management
                
                def go_to_step_4():
                    st.session_state.onboarding_step = 4
                    st.query_params["onboarding_step"] = "4"
                    safe_rerun()

                render_client_crud_management(is_wizard=True, on_continue=go_to_step_4)

            elif step == 4:
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
                        st.session_state.onboarding_step = 5
                        st.query_params["onboarding_step"] = "5"
                        safe_rerun()
                    else:
                        st.error("Error al guardar la configuración en .env")
                            
            elif step == 5:
                st.subheader("Cargar registros")
                
                # Checkbox para saltar este paso
                # Por defecto desmarcado para que el usuario siempre vea la opción de cargar,
                # independientemente de si generó usuarios o no.
                default_skip = False
                skip_records = st.checkbox("Prefiero cargarlos más tarde", value=default_skip)
                
                if not skip_records:
                    from modules.admin_records import render_records_import
                    render_records_import()
                
                counts = get_counts()
                
                # Mostrar botón finalizar si hay registros cargados O si el usuario decide saltar este paso
                if counts['registros'] > 0 or skip_records:
                    st.divider()
                    if st.button("Finalizar y Ir al Panel", type="primary"):
                         st.session_state.wizard_completed = True
                         if 'onboarding_step' in st.session_state:
                             del st.session_state.onboarding_step
                         if "onboarding_step" in st.query_params:
                             try:
                                 st.query_params.clear()
                             except:
                                 pass
                         safe_rerun()
                    if counts['registros'] > 0:
                        st.success("Configuración inicial completada con registros cargados")
                    else:
                        st.info("Configuración inicial completada (sin carga inicial de registros)")

    
    # Renderizar el dashboard correspondiente según el rol
    if st.session_state.is_admin:
        counts = get_counts()
        # Mostrar wizard si faltan datos o si estamos explícitamente en el paso 3 o 4
        # A menos que se haya marcado como completado en esta sesión
        wizard_completed = st.session_state.get('wizard_completed', False)
        show_wizard = (counts['nomina'] == 0 or counts['usuarios'] == 0) and not wizard_completed
        
        if 'onboarding_step' in st.session_state and st.session_state.onboarding_step > 0:
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
