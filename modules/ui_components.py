import streamlit as st
import os
import time
import base64
from modules.cookie_auth import set_session_cookie
from .auth import (
    login_user,
    create_user,
    verify_2fa_code,
    enable_2fa,
    disable_2fa,
    is_2fa_enabled,
    validate_password,
    hash_password,
    logout
)
from .config import get_app_version, reload_env, update_env_values
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
        if 'db_connection_verified' in st.session_state:
            del st.session_state.db_connection_verified
        st.rerun()
    
    # Intentar leer valores actuales del .env
    env_path = ".env"
    current_config = {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "sigo-db",
        "POSTGRES_USER": "postgres",
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


    # Inicializar estado de verificación
    if 'db_connection_verified' not in st.session_state:
        st.session_state.db_connection_verified = False

    # --- PHASE 1: CONNECTION ---
    if not st.session_state.db_connection_verified:
        st.info("Ingrese las credenciales del servidor PostgreSQL para continuar.")
        
        col1, col2 = st.columns(2)
        with col1:
            host = st.text_input("Host", value=current_config["POSTGRES_HOST"], key="conn_host")
            port = st.text_input("Puerto", value=current_config["POSTGRES_PORT"], key="conn_port")
        with col2:
            # Default user to what's in env or postgres
            user_val = current_config["POSTGRES_USER"] if current_config["POSTGRES_USER"] else "postgres"
            user = st.text_input("Usuario PostgreSQL", value=user_val, key="conn_user")
            password = st.text_input("Contraseña PostgreSQL", value=current_config["POSTGRES_PASSWORD"], type="password", key="conn_pass")

        if st.button("Conectar y Verificar", type="primary"):
            try:
                # Try connecting to 'postgres' db to verify credentials
                conn = psycopg2.connect(
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database="postgres"
                )
                conn.close()
                
                # Store valid credentials in session state
                st.session_state.db_config_temp = {
                    "host": host,
                    "port": port,
                    "user": user,
                    "password": password
                }
                st.session_state.db_connection_verified = True
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error de conexión: {e}")

    # --- PHASE 2: SELECTION ---
    else:
        config = st.session_state.db_config_temp
        st.success(f"✅ Conectado a PostgreSQL en {config['host']}:{config['port']} como {config['user']}")
        
        st.subheader("Seleccione una acción")
        
        col_new, col_exist = st.columns(2)
        
        with col_new:
            with st.container(border=True):
                st.markdown("### 🆕 Instalación Nueva")
                st.markdown("Crea la base de datos `sigo_db` desde cero. **⚠️ Borrará cualquier dato existente.**")
                
                if st.button("Iniciar Instalación", type="primary", use_container_width=True):
                    # Save config to .env first
                    update_env_values({
                        "POSTGRES_HOST": config['host'],
                        "POSTGRES_PORT": config['port'],
                        "POSTGRES_DB": "sigo_db",
                        "POSTGRES_USER": config['user'],
                        "POSTGRES_PASSWORD": config['password']
                    })
                    reload_env()
                    
                    # Run regenerate script with progress bar
                    progress_bar = st.progress(0, text="Iniciando instalación...")
                    status_log = st.empty()
                    
                    try:
                        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        # Force unbuffered output
                        env_vars['PYTHONUNBUFFERED'] = '1'
                        
                        process = subprocess.Popen(
                            [sys.executable, "regenerate_database.py", "--auto"],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            env=env_vars,
                            cwd=project_root,
                            bufsize=1,
                            universal_newlines=True
                        )
                        
                        full_output = []
                        
                        while True:
                            line = process.stdout.readline()
                            if not line and process.poll() is not None:
                                break
                            
                            if line:
                                line = line.strip()
                                full_output.append(line)
                                
                                # Update progress based on log messages
                                if "Iniciando configuración" in line:
                                    progress_bar.progress(10, text="Configurando conexión...")
                                elif "Eliminando tablas" in line:
                                    progress_bar.progress(30, text="Limpiando base de datos anterior...")
                                elif "Creando nueva estructura" in line:
                                    progress_bar.progress(50, text="Creando tablas y esquemas...")
                                elif "Corrigiendo hash" in line:
                                    progress_bar.progress(70, text="Configurando seguridad...")
                                elif "Configurando datos" in line:
                                    progress_bar.progress(85, text="Insertando datos iniciales...")
                                elif "regenerada exitosamente" in line:
                                    progress_bar.progress(100, text="¡Finalizando!")
                                
                                # Show meaningful log lines
                                if line.startswith("[") or len(line) > 10:
                                    status_log.text(f"📋 {line}")

                        if process.returncode == 0:
                            progress_bar.progress(100, text="✅ ¡Instalación completada!")
                            st.success("✅ Instalación completada exitosamente.")
                            time.sleep(1) # Give user a moment to see success
                            st.session_state.db_connection_verified = False
                            st.session_state['connection_success'] = True
                            reload_env()
                            st.rerun()
                        else:
                            st.error("❌ Error en la instalación:")
                            with st.expander("Ver detalles del error"):
                                st.code("\n".join(full_output))
                    except Exception as e:
                        st.error(f"❌ Error ejecutando script: {str(e)}")

        with col_exist:
            with st.container(border=True):
                st.markdown("### 🔌 Conectar a Existente")
                st.markdown("Se conecta a la base de datos `sigo_db` existente.")
                
                if st.button("Conectar a 'sigo_db'", use_container_width=True):
                    try:
                        # Verify connection to sigo_db
                        conn = psycopg2.connect(
                            host=config['host'],
                            port=config['port'],
                            user=config['user'],
                            password=config['password'],
                            database="sigo_db"
                        )
                        conn.close()
                        
                        # Save config
                        update_env_values({
                            "POSTGRES_HOST": config['host'],
                            "POSTGRES_PORT": config['port'],
                            "POSTGRES_DB": "sigo_db",
                            "POSTGRES_USER": config['user'],
                            "POSTGRES_PASSWORD": config['password']
                        })
                        reload_env()
                        
                        st.success("✅ Conexión exitosa a 'sigo_db'.")
                        st.session_state.db_connection_verified = False
                        st.session_state['connection_success'] = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ No se pudo conectar a 'sigo_db': {e}")
                        st.info("Asegúrese de que la base de datos existe. Si no, use la opción de Instalación Nueva.")

        st.markdown("---")
        if st.button("⬅️ Cambiar credenciales"):
            st.session_state.db_connection_verified = False
            st.rerun()

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
            
            /* Aumentar tamaño de fuente de mensajes de alerta (Login) */
            div[data-testid="stAlert"] {
                font-size: 1.1rem !important;
                padding: 1rem !important;
            }
            div[data-testid="stAlert"] p {
                font-size: 1.1rem !important;
                line-height: 1.5 !important;
            }
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
                bottom: 12px;
                font-size: 13px;
                font-weight: 600;
                color: var(--text-color);
                background-color: var(--secondary-background-color);
                padding: 4px 10px;
                border-radius: 6px;
                border: 1px solid rgba(128, 128, 128, 0.2);
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
                    
                    # Set persistent session cookie
                    set_session_cookie(user_id)
                    
                    st.success("Login exitoso!")
                    st.rerun()
                elif st.session_state.get('awaiting_2fa', False):
                    st.rerun()
                # El manejo de errores se hace dentro de login_user para evitar duplicados

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
                    font-weight: 600;
                    color: var(--text-color);
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
            f"<div style='margin-top: 20px; font-size: 12px; font-weight: 600; color: var(--text-color);'>Versión: {version}</div>",
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
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        color: var(--text-color);
        padding: 20px 24px;
        border-radius: 14px;
        box-sizing: border-box;
        text-decoration: none;
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        margin-bottom: 14px;
        cursor: pointer;
        transition: all 0.2s ease;
      }
      .project-card:hover {
        border-color: var(--primary-color);
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
      }
      .project-card.selected {
        border-color: var(--primary-color);
        box-shadow: 0 0 0 1px var(--primary-color) inset;
      }
      .project-info { display: flex; flex-direction: column; }
      .project-title {
        display: flex; align-items: center; gap: 10px;
        font-size: 1.2rem; font-weight: 700;
        color: var(--text-color);
      }
      .project-sub { font-size: 0.9rem; opacity: 0.8; margin-bottom: 2px; }
      .project-sub2 { font-size: 0.85rem; opacity: 0.6; }
      
      .status-pill {
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 500;
        white-space: nowrap;
        display: flex;
        align-items: center;
        justify-content: center;
        /* Default fallback */
        background: rgba(128, 128, 128, 0.1);
        color: var(--text-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
      }
      /* Specific pill colors preserved but using rgba for adaptability */
      .status-pill.ganado { background: rgba(34, 197, 94, 0.15); color: #22c55e; border-color: rgba(34, 197, 94, 0.3); }
      .status-pill.perdido { background: rgba(239, 68, 68, 0.15); color: #ef4444; border-color: rgba(239, 68, 68, 0.3); }
      .status-pill.prospecto { background: transparent; color: #60a5fa; border: 1px solid #60a5fa; }
      .status-pill.presupuestado { background: transparent; color: #34d399; border: 1px solid #34d399; }
      .status-pill.negociación { background: transparent; color: #8b5cf6; border: 1px solid #8b5cf6; }
      .status-pill.objeción { background: transparent; color: #fbbf24; border: 1px solid #fbbf24; }
      .status-pill.contact-cliente { background: rgba(96,165,250,0.1); color: #60a5fa; border-color: rgba(96,165,250,0.4); }
      .status-pill.contact-marca { background: rgba(248,113,113,0.1); color: #fb923c; border-color: rgba(248,113,113,0.4); }
      
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
      .hl-label { font-weight: 600; opacity: 0.7; margin-right: 4px; color: var(--text-color); }
      .hl-val { color: var(--text-color); }
      .hl-sep { margin: 0 8px; opacity: 0.4; }
      .hl-val.client { color: #60a5fa; font-weight: 500; }
      .hl-val.bright { font-weight: 600; }
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

      /* Estilos para tarjeta "Hoy en la oficina" (Office Card) */
      .office-card {
        border: 1px solid rgba(128, 128, 128, 0.2);
        background-color: var(--secondary-background-color);
        color: var(--text-color);
        padding: 12px 16px;
        border-radius: 10px;
        margin-bottom: 10px;
      }
      .office-card-title {
        font-weight: 600;
        color: var(--primary-color);
        margin-bottom: 6px;
      }
      .office-chip {
        padding: 4px 12px;
        border-radius: 9999px;
        display: inline-flex;
        align-items: center;
        margin: 4px 6px 4px 0;
        font-size: 0.85rem;
        font-weight: 500;
        /* Default/Fallback */
        background-color: rgba(150, 150, 150, 0.1);
        color: var(--text-color);
        border: 1px solid rgba(128, 128, 128, 0.3);
      }
      .office-chip-empty {
        opacity: 0.6;
        color: var(--text-color);
      }

      /* Estilos para detalles de contacto (Contact Detail Box) */
      .contact-detail-box {
        background-color: var(--secondary-background-color);
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
        border: 1px solid rgba(128, 128, 128, 0.2);
      }
      .contact-detail-label {
        color: var(--text-color);
        opacity: 0.7;
        font-size: 0.8em;
        margin-bottom: 4px;
      }
      .contact-detail-value {
        color: var(--text-color);
        font-size: 1em;
        font-weight: 500;
      }

      /* Estilos para Client Card (Create Project) - Version Definitiva Simplificada */
      .client-card {
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 12px;
        padding: 12px;
      }
      .client-title { font-weight:600; color:var(--text-color); opacity: 0.8; margin-bottom:6px; }
      .client-value { color:var(--text-color); }

      /* TEMA OSCURO (Selector de data-theme="dark") */
      [data-theme="dark"] .client-card {
           background-color: #111827 !important;
           border-color: #374151 !important;
      }
      [data-theme="dark"] .client-title { color: #9ca3af !important; opacity: 1; }
      [data-theme="dark"] .client-value { color: #e5e7eb !important; }
      [data-theme="dark"] .office-chip {
           background-color: #334155 !important;
           border-color: #475569 !important;
           color: #f8fafc !important;
      }

      /* TEMA CLARO (Selector de data-theme="light") */
      [data-theme="light"] .project-card, 
      [data-theme="light"] .office-card, 
      [data-theme="light"] .contact-detail-box,
      [data-theme="light"] .client-card {
            background-color: #f3f4f6 !important;
            border-color: #9ca3af !important;
      }
      
      [data-theme="light"] .client-card .client-title { color: #4b5563 !important; }
      [data-theme="light"] .client-card .client-value { color: #111827 !important; }
      [data-theme="light"] .office-chip {
            background-color: #e2e8f0 !important;
            border-color: #cbd5e1 !important;
            color: #0f172a !important;
      }

      /* TEMA CLARO: Ajustes de Hover (evitar oscurecimiento excesivo) */
      [data-theme="light"] .project-card:hover,
      [data-theme="light"] .client-card:hover {
          background-color: #ffffff !important; /* Se aclara al pasar el mouse */
          box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.01) !important;
          border-color: var(--primary-color) !important;
      }

      /* TEMA CLARO: Dropdowns (st.selectbox) y Widgets */
      [data-theme="light"] div[data-baseweb="select"] > div,
      [data-theme="light"] div[data-baseweb="base-input"] {
          background-color: #ffffff !important;
          border-color: #d1d5db !important;
          color: #111827 !important;
      }
      [data-theme="light"] div[data-baseweb="select"] span {
          color: #111827 !important;
      }
      [data-theme="light"] div[data-baseweb="select"] svg {
          fill: #6b7280 !important;
      }
      /* Opciones del menú (Popover) */
      [data-theme="light"] div[data-baseweb="popover"] div[data-baseweb="menu"] {
          background-color: #ffffff !important;
      }
      [data-theme="light"] div[data-baseweb="popover"] li {
          color: #111827 !important;
      }
      [data-theme="light"] div[data-baseweb="popover"] li:hover {
          background-color: #f3f4f6 !important;
      }

      /* FALLBACK: Si no hay data-theme, usar media query del sistema (smart fallback) */
      @media (prefers-color-scheme: light) {
          :root:not([data-theme="dark"]) .project-card, 
          :root:not([data-theme="dark"]) .office-card, 
          :root:not([data-theme="dark"]) .contact-detail-box,
          :root:not([data-theme="dark"]) .client-card {
              background-color: #f3f4f6 !important;
              border-color: #9ca3af !important;
          }
          :root:not([data-theme="dark"]) .client-card .client-title { color: #4b5563 !important; }
          :root:not([data-theme="dark"]) .client-card .client-value { color: #111827 !important; }
          
          :root:not([data-theme="dark"]) .office-chip {
              background-color: #e2e8f0 !important;
              border-color: #cbd5e1 !important;
              color: #0f172a !important;
          }
          
          /* Fallback Hover */
          :root:not([data-theme="dark"]) .project-card:hover {
              background-color: #ffffff !important;
              box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05) !important;
          }
          
          /* Fallback Dropdowns */
          :root:not([data-theme="dark"]) div[data-baseweb="select"] > div {
              background-color: #ffffff !important;
              color: #111827 !important;
              border-color: #d1d5db !important;
          }
          :root:not([data-theme="dark"]) div[data-baseweb="select"] span {
              color: #111827 !important;
          }
      }
    </style>
    """, unsafe_allow_html=True)
