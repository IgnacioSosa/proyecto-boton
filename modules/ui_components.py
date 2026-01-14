import streamlit as st
import os
import base64
from .auth import (
    login_user,
    create_user,
    verify_2fa_code,
    enable_2fa,
    disable_2fa,
    is_2fa_enabled,
    make_signed_session_params,
    validate_password,
    hash_password,
    logout
)
from .config import get_app_version, reload_env
from .database import get_connection

def render_db_config_screen():
    """Renderiza una pantalla de configuración de base de datos cuando falla la conexión"""
    import psycopg2
    import subprocess
    import sys
    
    # Asegurar codificación UTF-8 para subprocesos
    env_vars = os.environ.copy()
    env_vars['PGCLIENTENCODING'] = 'UTF8'
    env_vars['PYTHONIOENCODING'] = 'utf-8'
    
    st.warning("⚠️ No se pudo conectar a la base de datos.")

    if st.button("⬅️ Volver al Login", key="btn_back_to_login_config"):
        st.session_state['force_db_config'] = False
        st.rerun()
    
    # Intentar leer valores actuales del .env
    env_path = ".env"
    current_config = {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "sigo-db",
        "POSTGRES_USER": "sigo",
        "POSTGRES_PASSWORD": ""
    }
    
    if os.path.exists(env_path):
        try:
            with open(env_path, "r") as f:
                for line in f:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        if key in current_config:
                            current_config[key] = value
        except Exception:
            pass

    # Función auxiliar para guardar
    def save_config_to_env(new_host, new_port, new_dbname, new_user, new_password):
        try:
            lines = []
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    lines = f.readlines()
            
            new_lines = []
            keys_updated = set()
            config_map = {
                "POSTGRES_HOST": new_host,
                "POSTGRES_PORT": new_port,
                "POSTGRES_DB": new_dbname,
                "POSTGRES_USER": new_user,
                "POSTGRES_PASSWORD": new_password
            }
            
            for line in lines:
                key = line.split("=")[0].strip() if "=" in line else None
                if key in config_map:
                    new_lines.append(f"{key}={config_map[key]}\n")
                    keys_updated.add(key)
                else:
                    new_lines.append(line)
            
            for key, val in config_map.items():
                if key not in keys_updated:
                    new_lines.append(f"{key}={val}\n")
            
            with open(env_path, "w") as f:
                f.writelines(new_lines)
            
            reload_env()
            return True, "Configuración guardada."
        except Exception as e:
            return False, str(e)

    tab_conn, tab_regen = st.tabs(["🔌 Conectar a Existente", "🆕 Instalación / Regenerar"])

    with tab_conn:
        st.info("Si la base de datos ya existe, verifica los datos de conexión aquí.")
        with st.container():
            col1, col2 = st.columns(2)
            with col1:
                host = st.text_input("Host", value=current_config["POSTGRES_HOST"], key="conn_host")
                port = st.text_input("Puerto", value=current_config["POSTGRES_PORT"], key="conn_port")
                dbname = st.text_input("Nombre de Base de Datos", value=current_config["POSTGRES_DB"], key="conn_db")
            with col2:
                user = st.text_input("Usuario", value=current_config["POSTGRES_USER"], key="conn_user")
                password = st.text_input("Contraseña", value=current_config["POSTGRES_PASSWORD"], type="password", key="conn_pass")
            
            if st.button("Guardar y Probar Conexión", type="primary", key="btn_save_conn"):
                success, msg = save_config_to_env(host, port, dbname, user, password)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    
    with tab_regen:
        st.error("⚠️ ¡CUIDADO! Esta opción eliminará y recreará la base de datos.")
        
        # Copia de seguridad de los mismos campos para regenerar
        col1r, col2r = st.columns(2)
        with col1r:
            host_r = st.text_input("Host (para regenerar)", value=current_config["POSTGRES_HOST"], key="conn_host_r")
            port_r = st.text_input("Puerto", value=current_config["POSTGRES_PORT"], key="conn_port_r")
            dbname_r = st.text_input("Nombre DB a crear", value=current_config["POSTGRES_DB"], key="conn_db_r")
        with col2r:
            user_r = st.text_input("Usuario Admin DB", value=current_config["POSTGRES_USER"], key="conn_user_r")
            password_r = st.text_input("Contraseña Admin DB", value=current_config["POSTGRES_PASSWORD"], type="password", key="conn_pass_r")

        if st.button("🚨 Destruir y Regenerar Base de Datos", type="primary", key="btn_regen_db"):
            # Guardar primero
            success, msg = save_config_to_env(host_r, port_r, dbname_r, user_r, password_r)
            if not success:
                st.error(f"No se pudo guardar la configuración: {msg}")
            else:
                try:
                    # Ejecutar script de regeneración
                    result = subprocess.run([sys.executable, "setup_database.py"], capture_output=True, text=True, env=env_vars)
                    if result.returncode == 0:
                        st.success("✅ Base de datos regenerada correctamente.")
                        st.session_state['connection_success'] = True
                        st.rerun()
                    else:
                        st.error(f"❌ Error al regenerar: {result.stderr}")
                except Exception as e:
                    st.error(f"❌ Error ejecutando script: {str(e)}")

def render_login_tabs():
    """Renderiza las pestañas de Login y Registro"""
    logo_path = "assets/Sigo_logo.png"
    if not os.path.exists(logo_path):
        logo_path = "assets/logo.png"

    if os.path.exists(logo_path):
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.image(logo_path, use_container_width=True)

        st.markdown(
            """
            <style>
            div[data-testid="stAppViewContainer"] .main .block-container { padding-top: 0.5rem !important; }
            .block-container { padding-top: 0.5rem !important; }
            div[data-testid="column"] { margin-bottom: -10px; padding-bottom: 0 !important; }
            div[data-testid="stImage"] { margin-top: -30px; margin-bottom: -60px; }
            .stTabs { margin-top: -50px; }
            </style>
            """,
            unsafe_allow_html=True,
        )

        version = get_app_version()
        st.markdown(
            f"""
            <div class="app-version-tag">Versión: {version}</div>
            <style>
            .app-version-tag {{
                position: fixed;
                right: 22px;
                bottom: 0;
                font-size: 12px;
                color: #9ca3af;
                z-index: 9999;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )

    tab_login, tab_register = st.tabs(["Iniciar Sesión", "Registrarse"])

    with tab_login:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Usuario", key="login_username")
            password = st.text_input("Contraseña", type="password", key="login_password")
            submitted = st.form_submit_button("Entrar", type="primary", use_container_width=True)

            if submitted:
                user_id, is_admin = login_user(username, password)
                if user_id:
                    st.session_state.user_id = user_id
                    st.session_state.is_admin = is_admin
                    st.session_state.username = username
                    st.session_state.mostrar_perfil = False
                    try:
                        signed = make_signed_session_params(user_id)
                        st.query_params.update(signed)
                    except Exception:
                        pass
                    st.success("Login exitoso!")
                    st.rerun()
                elif st.session_state.get('awaiting_2fa', False):
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos o la cuenta está pendiente de activación por un administrador.")

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("Usuario")
            new_email = st.text_input("Email")
            new_password = st.text_input("Contraseña", type="password")
            confirm_password = st.text_input("Confirmar Contraseña", type="password")

            reg_submitted = st.form_submit_button("Crear Cuenta", use_container_width=True)

            if reg_submitted:
                if new_password != confirm_password:
                    st.error("Las contraseñas no coinciden")
                else:
                    success, msg = create_user(new_username, new_password, new_email)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)

def render_sidebar_profile(user_info):
    """Renderiza el perfil de usuario en la barra lateral"""
    
    if not user_info:
        return

    nombre_actual = user_info.get('nombre', '') if user_info.get('nombre') else ''
    apellido_actual = user_info.get('apellido', '') if user_info.get('apellido') else ''
    current_username = user_info.get('username', '')
    email_actual = user_info.get('email', '') if user_info.get('email') else ''
    
    # Barra lateral para perfil y cierre de sesión
    with st.sidebar:
        logo_path = "assets/Sigo_logo.png"
        if not os.path.exists(logo_path):
            logo_path = "assets/logo.png"
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
            st.markdown(
                """
                <style>
                aside[data-testid="stSidebar"] .block-container {
                    position: relative;
                    padding-bottom: 40px;
                }
                .sigo-sidebar-logo {
                    position: absolute;
                    top: -90px;
                    left: 50%;
                    transform: translateX(-50%);
                    width: 200px;
                    z-index: 999;
                    opacity: 0.98;
                    pointer-events: none;
                }
                .sidebar-version {
                    position: absolute;
                    left: 16px;
                    bottom: 8px;
                    font-size: 12px;
                    color: #9ca3af;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<img src="data:image/png;base64,{data}" class="sigo-sidebar-logo" />',
                unsafe_allow_html=True,
            )
        st.sidebar.button("Cerrar Sesión", on_click=logout, type="primary", use_container_width=True)
        st.header("Editar Perfil")
        with st.expander("Datos Personales"):
            nuevo_nombre = st.text_input("Nombre", value=nombre_actual, key="sidebar_nombre")
            nuevo_apellido = st.text_input("Apellido", value=apellido_actual, key="sidebar_apellido")
            nuevo_email = st.text_input("Correo Electrónico", value=email_actual, key="sidebar_email")

        with st.expander("Cambiar Contraseña"):
            nueva_password = st.text_input("Nueva Contraseña", type="password", key="new_pass_sidebar")
            confirmar_password = st.text_input("Confirmar Nueva Contraseña", type="password", key="confirm_pass_sidebar")
            st.info("La contraseña debe tener al menos 8 caracteres, una letra mayúscula, una letra minúscula, un número y un carácter especial.")

        if st.button("Guardar Cambios", key="save_sidebar_profile", use_container_width=True):
            conn = get_connection()
            c = conn.cursor()
            
            c.execute('SELECT nombre, apellido FROM usuarios WHERE id = %s', (st.session_state.user_id,))
            old_user_info = c.fetchone()
            old_nombre = old_user_info[0] if old_user_info[0] else ''
            old_apellido = old_user_info[1] if old_user_info[1] else ''
            old_nombre_completo = f"{old_nombre} {old_apellido}".strip()
            
            # Capitalizar nombre y apellido
            nuevo_nombre_cap = nuevo_nombre.strip().capitalize() if nuevo_nombre else ''
            nuevo_apellido_cap = nuevo_apellido.strip().capitalize() if nuevo_apellido else ''
            
            c.execute('UPDATE usuarios SET nombre = %s, apellido = %s, email = %s WHERE id = %s',
                        (nuevo_nombre_cap, nuevo_apellido_cap, nuevo_email.strip(), st.session_state.user_id))
            
            nuevo_nombre_completo = f"{nuevo_nombre_cap} {nuevo_apellido_cap}".strip()
            
            if old_nombre_completo and nuevo_nombre_completo != old_nombre_completo:
                c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = %s', (old_nombre_completo,))
                old_tecnico = c.fetchone()
                if old_tecnico:
                    c.execute('UPDATE tecnicos SET nombre = %s WHERE nombre = %s', 
                                (nuevo_nombre_completo, old_nombre_completo))
            
            if nuevo_nombre_completo:
                c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = %s', (nuevo_nombre_completo,))
                tecnico = c.fetchone()
                if not tecnico:
                    c.execute('INSERT INTO tecnicos (nombre) VALUES (%s)', (nuevo_nombre_completo,))
            
            if nueva_password:
                if nueva_password == confirmar_password:
                    # Validar la contraseña
                    is_valid, messages = validate_password(nueva_password)
                    if is_valid:
                        hashed_password = hash_password(nueva_password)
                        c.execute('UPDATE usuarios SET password_hash = %s WHERE id = %s',
                                    (hashed_password, st.session_state.user_id))
                        st.toast("Contraseña actualizada.", icon="🔑")
                    else:
                        for message in messages:
                            st.error(message)
                        conn.close()
                        return
                else:
                    st.error("Las contraseñas no coinciden.")
                    conn.close()
                    return
            
            conn.commit()
            conn.close()
            st.success("Perfil actualizado.")
            st.rerun()

        version = get_app_version()
        st.markdown(
            f"<div class='sidebar-version'>Versión: {version}</div>",
            unsafe_allow_html=True,
        )

def render_no_view_dashboard(username):
    """Renderiza dashboard para usuarios sin rol específico"""
    st.header(f"Bienvenido, {username}")
    st.info("Tu usuario no tiene asignada una vista específica. Contacta al administrador.")
    
    if st.button("Cerrar Sesión"):
        logout()

def inject_project_card_css():
    st.markdown("""
    <style>
      .project-card {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        background: #1f2937;
        border: 1px solid #374151;
        color: #e5e7eb;
        padding: 20px 24px;
        border-radius: 14px;
        box-sizing: border-box;
        text-decoration: none;
        box-shadow: 0 4px 10px rgba(0,0,0,0.25);
        margin-bottom: 14px;
        cursor: pointer;
      }
      .project-card:hover {
        background: #111827;
        border-color: #2563eb;
        transform: translateY(-1px);
        transition: all .15s ease-in-out;
      }
      .project-card.selected {
        background:#0a1324;
        border-color:#2563eb;
        box-shadow:0 0 0 2px rgba(37,99,235,0.30) inset;
      }
      .project-info { display: flex; flex-direction: column; }
      .project-title {
        display: flex; align-items: center; gap: 10px;
        font-size: 1.2rem; font-weight: 700; color: #f3f4f6;
      }
      .project-sub { font-size: 0.9rem; color: #9ca3af; margin-bottom: 2px; }
      .project-sub2 { font-size: 0.85rem; color: #6b7280; }
      
      .status-pill {
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 500;
        white-space: nowrap;
        background: #374151;
        color: #d1d5db;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .status-pill.ganado { background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); }
      .status-pill.perdido { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
      .status-pill.prospecto { background: transparent; color: #60a5fa; border: 1px solid #60a5fa; }
      .status-pill.presupuestado { background: transparent; color: #34d399; border: 1px solid #34d399; }
      .status-pill.negociación { background: transparent; color: #8b5cf6; border: 1px solid #8b5cf6; }
      .status-pill.objeción { background: transparent; color: #fbbf24; border: 1px solid #fbbf24; }
      .status-pill.contact-cliente { background: rgba(96,165,250,0.15); color: #60a5fa; border: 1px solid rgba(96,165,250,0.6); }
      .status-pill.contact-marca { background: rgba(248,113,113,0.15); color: #fb923c; border: 1px solid rgba(248,113,113,0.6); }
      
      /* Overlay form button */
      .card-form {
        position: relative;
        display: block;
        margin-bottom: 12px;
      }
      .card-submit {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        opacity: 0;
        z-index: 10;
        cursor: pointer;
        border: none;
        background: transparent;
      }
      
      /* Admin specific additions */
      .hl-label { font-weight: 600; color: #9ca3af; margin-right: 4px; }
      .hl-val { color: #e5e7eb; }
      .hl-sep { margin: 0 8px; color: #4b5563; }
      .hl-val.client { color: #60a5fa; font-weight: 500; }
      .hl-val.bright { color: #f3f4f6; font-weight: 600; }
      .dot-left {
         display: inline-block; width: 8px; height: 8px; border-radius: 50%; background-color: #6b7280;
      }
      .dot-left.prospecto { background-color: #60a5fa; }
      .dot-left.presupuestado { background-color: #34d399; }
      .dot-left.negociación { background-color: #8b5cf6; }
      .dot-left.objeción { background-color: #fbbf24; }
      .dot-left.ganado { background-color: #22c55e; box-shadow: 0 0 8px rgba(34, 197, 94, 0.5); }
      .dot-left.perdido { background-color: #ef4444; }
      .dot-left.contact-cliente { background-color: #60a5fa; }
      .dot-left.contact-marca { background-color: #fb923c; }
    </style>
    """, unsafe_allow_html=True)
