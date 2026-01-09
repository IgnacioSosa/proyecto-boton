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
)
from .config import APP_VERSION, reload_env

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

    if st.button("⬅️ Volver al Login"):
        st.session_state['force_db_config'] = False
        st.rerun()
    
    # Intentar leer valores actuales del .env
    env_path = ".env"
    current_config = {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "trabajo_db",
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
            
            test_col, save_col = st.columns(2)
            with test_col:
                test_submitted = st.button("🔌 Probar Conexión", key="btn_test_conn")
            with save_col:
                save_submitted = st.button("💾 Guardar Configuración", key="btn_save_conn")

            if test_submitted:
                try:
                    conn = psycopg2.connect(
                        host=host,
                        port=port,
                        database=dbname,
                        user=user,
                        password=password
                    )
                    conn.close()
                    st.success("✅ Conexión exitosa!")
                    st.session_state['connection_success'] = True
                except Exception as e:
                    st.error(f"❌ No se pudo conectar a la DB: {e}")
                    st.session_state['connection_success'] = False

                    # Sección de recuperación: Crear usuario si no existe
                    st.divider()
                    with st.expander("🛠️ Solución de Problemas: Crear/Reparar Usuario de BD"):
                        st.warning(f"Si el usuario '{user}' no existe en PostgreSQL o la contraseña es incorrecta, puedes arreglarlo aquí usando un usuario con permisos (ej. 'postgres').")
                        with st.form("create_db_user_fix_form"):
                            st.write("Credenciales de Superusuario (habitualmente 'postgres')")
                            col_su1, col_su2 = st.columns(2)
                            with col_su1:
                                su_user = st.text_input("Superusuario", value="postgres", key="fix_su_user")
                            with col_su2:
                                su_pass = st.text_input("Contraseña de Superusuario", type="password", key="fix_su_pass")
                            
                            st.info(f"Acción: Se creará el usuario **'{user}'** con la contraseña **'{password}'** (o se actualizará si ya existe) y se le darán permisos sobre **'{dbname}'**.")
                            
                            btn_create_fix = st.form_submit_button("Reparar Usuario / Contraseña")
                            
                            if btn_create_fix:
                                try:
                                    # Conectar como superusuario a la base de datos 'postgres' (siempre existe)
                                    su_conn = psycopg2.connect(
                                        host=host,
                                        port=port,
                                        database="postgres",
                                        user=su_user,
                                        password=su_pass
                                    )
                                    su_conn.autocommit = True
                                    su_cursor = su_conn.cursor()
                                    
                                    # Validar nombre de usuario para evitar inyección SQL básica en identificadores
                                    import re
                                    if not re.match(r'^[a-zA-Z0-9_]+$', user):
                                        st.error("Nombre de usuario inválido.")
                                    else:
                                        # Verificar si existe
                                        su_cursor.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (user,))
                                        exists = su_cursor.fetchone()
                                        
                                        if exists:
                                            su_cursor.execute(f"ALTER USER {user} WITH PASSWORD %s", (password,))
                                            st.success(f"✅ Usuario '{user}' existía. Se actualizó su contraseña.")
                                        else:
                                            su_cursor.execute(f"CREATE USER {user} WITH PASSWORD %s CREATEDB", (password,))
                                            st.success(f"✅ Usuario '{user}' creado exitosamente.")
                                        
                                        # Intentar dar permisos sobre la base de datos objetivo
                                        try:
                                            # Verificar si la base de datos objetivo existe
                                            su_cursor.execute("SELECT 1 FROM pg_database WHERE datname=%s", (dbname,))
                                            if su_cursor.fetchone():
                                                su_cursor.execute(f"GRANT ALL PRIVILEGES ON DATABASE {dbname} TO {user}")
                                                st.success(f"✅ Permisos otorgados sobre '{dbname}'.")
                                            else:
                                                st.warning(f"⚠️ La base de datos '{dbname}' no existe aún (se creará al regenerar).")
                                        except Exception as perm_e:
                                            st.warning(f"No se pudieron asignar permisos automáticos: {perm_e}")
                                            
                                        st.success("Intenta presionar 'Probar Conexión' arriba ahora.")
                                    
                                    su_conn.close()
                                except Exception as su_e:
                                    st.error(f"❌ Error al intentar reparar: {su_e}")


            if save_submitted:
                success, msg = save_config_to_env(host, port, dbname, user, password)
                if success:
                    st.success(f"✅ {msg} Recargando...")
                    st.session_state['connection_success'] = True
                    st.rerun()
                else:
                    st.error(f"❌ Error al guardar .env: {msg}")

    with tab_regen:
        st.warning("⚠️ Esta acción eliminará TODOS los datos si la base de datos ya existe.")
        st.info("Utilice esta opción para una INSTALACIÓN NUEVA o si desea reiniciar el sistema completo.")
        
        st.markdown("#### Configuración para Nueva Instalación / Regeneración")
        st.caption("Si es una instalación nueva, ingrese las credenciales que desea utilizar (se guardarán en la configuración). Si la base ya existe, se usan los valores actuales por defecto.")

        # Inputs independientes para regeneración para permitir cambiar credenciales antes de regenerar
        # Pre-cargamos con lo actual para facilitar
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            r_host = st.text_input("Host", value=current_config["POSTGRES_HOST"], key="reg_host")
            r_port = st.text_input("Puerto", value=current_config["POSTGRES_PORT"], key="reg_port")
            r_dbname = st.text_input("Nombre de Base de Datos", value=current_config["POSTGRES_DB"], key="reg_db")
        with col_r2:
            r_user = st.text_input("Usuario (Nuevo/Admin)", value=current_config["POSTGRES_USER"], key="reg_user")
            r_password = st.text_input("Contraseña", value=current_config["POSTGRES_PASSWORD"], type="password", key="reg_pass")
            
        if st.button("🚀 Crear / Regenerar Base de Datos", type="primary", key="btn_regen_action"):
            # 1. Guardar la configuración elegida
            success_save, msg_save = save_config_to_env(r_host, r_port, r_dbname, r_user, r_password)
            
            if not success_save:
                st.error(f"❌ Error al guardar configuración: {msg_save}")
            else:
                # 2. Ejecutar script
                env_vars["POSTGRES_HOST"] = r_host
                env_vars["POSTGRES_PORT"] = r_port
                env_vars["POSTGRES_DB"] = r_dbname
                env_vars["POSTGRES_USER"] = r_user
                env_vars["POSTGRES_PASSWORD"] = r_password
                
                try:
                    with st.spinner("Regenerando base de datos... (Esto puede tardar unos segundos)"):
                        python_executable = sys.executable
                        process = subprocess.run(
                            [python_executable, 'regenerate_database.py', '--auto'],
                            capture_output=True,
                            text=True,
                            env=env_vars,
                            encoding='utf-8', 
                            errors='replace'
                        )
                        
                        if process.returncode == 0:
                            st.success("✅ Base de datos creada/regenerada correctamente.")
                            st.session_state['connection_success'] = True
                            # No hacemos rerun inmediato para que vea el mensaje, pero el flujo admin aparecerá abajo
                        else:
                            st.error("❌ Error al regenerar la base de datos.")
                            
                            # Intentar detectar si es error de conexión para pedir credenciales
                            err_out = process.stdout + "\n" + process.stderr
                            if "password authentication failed" in err_out or "Error de conexión" in err_out or "FATAL:  role" in err_out or "codec can't decode" in err_out or "Probable error de credenciales" in err_out:
                                st.warning("⚠️ Error de autenticación. Es posible que el usuario/contraseña sean incorrectos para la base existente.")
                                st.session_state['regen_auth_failed'] = True
                                st.session_state['regen_last_error'] = err_out
                            else:
                                st.code(err_out)

                except Exception as e:
                    st.error(f"❌ Error ejecutando script: {e}")

        # UI de Reintento fuera del bloque del botón para persistir
        if st.session_state.get('regen_auth_failed', False):
            st.divider()
            st.warning("🔄 Reintentar con otras credenciales:")
            with st.form("retry_regen_creds_form"):
                retry_user = st.text_input("Usuario PostgreSQL", value=r_user)
                retry_pass = st.text_input("Contraseña PostgreSQL", value="", type="password")
                if st.form_submit_button("Reintentar Regeneración"):
                    # Guardar y reintentar
                    s_save, s_msg = save_config_to_env(r_host, r_port, r_dbname, retry_user, retry_pass)
                    if s_save:
                        env_vars["POSTGRES_USER"] = retry_user
                        env_vars["POSTGRES_PASSWORD"] = retry_pass
                        try:
                            with st.spinner("Reintentando..."):
                                python_executable = sys.executable
                                process_retry = subprocess.run(
                                    [python_executable, 'regenerate_database.py', '--auto'],
                                    capture_output=True,
                                    text=True,
                                    env=env_vars,
                                    encoding='utf-8', 
                                    errors='replace'
                                )
                                if process_retry.returncode == 0:
                                    st.success("✅ Base de datos regenerada correctamente.")
                                    st.session_state['regen_auth_failed'] = False
                                    st.session_state['connection_success'] = True
                                    st.rerun()
                                else:
                                    st.error("❌ Falló nuevamente.")
                                    st.code(process_retry.stdout + "\n" + process_retry.stderr)
                        except Exception as ex:
                            st.error(f"Error: {ex}")

    # Nuevo flujo de verificación de admin (Común a ambos tabs)
    if st.session_state.get('connection_success', False):
        st.divider()
        st.subheader("🛡️ Verificación de Administrador")
        st.info("La conexión fue exitosa. Ingresa las credenciales de administrador para continuar.")
        
        with st.form("admin_verify_form"):
            admin_user = st.text_input("Usuario Administrador", value="admin")
            admin_pass = st.text_input("Contraseña Administrador", type="password")
            verify_btn = st.form_submit_button("Verificar e Iniciar")
            
        if verify_btn:
            try:
                # Usar los valores actuales del .env (o los últimos guardados)
                # Para asegurar que usamos los correctos, leemos de nuevo o usamos los de la sesión si pudiéramos.
                # Pero reload_env() actualiza POSTGRES_CONFIG en config.py, importémoslo o usemos los inputs si están disponibles.
                # Como estamos fuera del scope de los inputs del tab, leemos del .env recargado.
                from .config import POSTGRES_CONFIG
                
                conn = psycopg2.connect(**POSTGRES_CONFIG)
                c = conn.cursor()
                c.execute("SELECT id, password_hash FROM usuarios WHERE username = %s", (admin_user,))
                res = c.fetchone()
                conn.close()
                
                if res:
                    from .auth import verify_password
                    stored_hash = res[1]
                    if verify_password(admin_pass, stored_hash):
                        reload_env()
                        st.success("✅ Administrador verificado. Iniciando aplicación...")
                        st.rerun()
                    else:
                        st.error("❌ Contraseña de administrador incorrecta.")
                else:
                    st.error("❌ No se encontró el usuario administrador.")
                    st.session_state['admin_not_found'] = True
                    
            except Exception as e:
                # Detectar si el error es porque las tablas no existen (base de datos vacía)
                error_str = str(e)
                if "relation" in error_str and "does not exist" in error_str:
                    st.warning("⚠️ La base de datos existe pero parece estar vacía (faltan tablas).")
                    st.session_state['admin_not_found'] = True
                else:
                    st.error(f"❌ Error al verificar administrador: {e}")

        if st.session_state.get('admin_not_found', False):
            col_retry, col_regen = st.columns(2)
            with col_retry:
                if st.button("🔄 Probar nuevamente"):
                    st.session_state['admin_not_found'] = False
                    st.rerun()
            with col_regen:
                if st.button("🛠️ Inicializar Base de Datos (Crear Tablas y Admin)"):
                     # Redirigir al tab de regenerar o ejecutar directamente?
                     # Ejecutamos directamente por conveniencia
                     try:
                        with st.spinner("Regenerando base de datos..."):
                            python_executable = sys.executable
                            process = subprocess.run(
                                [python_executable, 'regenerate_database.py', '--auto'],
                                capture_output=True,
                                text=True,
                                env=env_vars,
                                encoding='utf-8', 
                                errors='replace'
                            )
                            if process.returncode == 0:
                                st.success("✅ Base de datos regenerada y admin creado.")
                                st.session_state['connection_success'] = True
                                st.session_state['admin_not_found'] = False
                                st.rerun()
                            else:
                                st.error("❌ Error al regenerar.")
                                st.code(process.stdout + "\n" + process.stderr)
                     except Exception as e:
                        st.error(f"❌ Error: {e}")

def render_login_tabs():
    """Renderiza las pestañas de login y registro"""
    # Si estamos esperando verificación 2FA
    if st.session_state.get('awaiting_2fa', False):
        render_2fa_verification()
        return
    
    # Mostrar logo si existe
    logo_path = "assets/Sigo_logo.png"
    if not os.path.exists(logo_path):
        logo_path = "assets/logo.png"

    if os.path.exists(logo_path):
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.image(logo_path, use_container_width=True)
            
        # CSS hack para reducir el espacio entre el logo y los tabs, y el espacio superior
        st.markdown("""
            <style>
            div[data-testid="stAppViewContainer"] .main .block-container { padding-top: 0.5rem !important; }
            .block-container { padding-top: 0.5rem !important; }
            div[data-testid="column"] { margin-bottom: -10px; padding-bottom: 0 !important; }
            div[data-testid="stImage"] { margin-top: -30px; margin-bottom: -60px; }
            .stTabs { margin-top: -50px; }
            </style>
        """, unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="app-version-tag">Version: {APP_VERSION}</div>
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
    
    tab1, tab2 = st.tabs(["Login", "Registro"])


    with tab1:
        st.header("Login")
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Usuario", key="login_username")
            password = st.text_input("Contraseña", type="password", key="login_password")
            submitted = st.form_submit_button("Ingresar")
            if submitted:
                user_id, is_admin = login_user(username, password)
                if user_id:
                    st.session_state.user_id = user_id
                    st.session_state.is_admin = is_admin
                    st.session_state.mostrar_perfil = False
                    # Persistir sesión en el URL con firma HMAC para sobrevivir recargas
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

    with tab2:
        st.header("Registro")
        new_username = st.text_input("Usuario", key="reg_username")
        new_email = st.text_input("Correo Electrónico", key="reg_email")
        new_password = st.text_input("Contraseña", type="password", key="reg_password")
        
        # Agregar información sobre los requisitos de contraseña
        st.info("La contraseña debe tener al menos 8 caracteres, una letra mayúscula, una letra minúscula, un número y un carácter especial.")
        
        if st.button("Registrarse"):
            if new_username and new_password and new_email:
                if create_user(new_username, new_password, email=new_email):
                    st.success("Usuario creado exitosamente! Por favor contacte al administrador para que active su cuenta.")
                # El mensaje de error ahora lo maneja la función create_user
            else:
                st.error("Usuario, correo electrónico y contraseña son obligatorios.")

def render_2fa_verification():
    """Renderiza la pantalla de verificación 2FA"""
    st.header("Verificación de Dos Factores")
    st.info("Por favor, ingrese el código de su aplicación de autenticación o un código de recuperación.")
    
    code = st.text_input("Código", key="2fa_code")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Verificar", key="verify_2fa"):
            if verify_2fa_code(code):
                st.success("Verificación exitosa!")
                st.rerun()
            else:
                st.error("Código inválido. Intente nuevamente.")
    
    with col2:
        if st.button("Cancelar", key="cancel_2fa"):
            # Limpiar variables de sesión relacionadas con 2FA
            for key in ['awaiting_2fa', 'temp_user_id', 'temp_username', 'temp_is_admin', 
                        'temp_nombre', 'temp_apellido', 'temp_rol_id', 'temp_grupo_id']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

def render_sidebar_profile(user_info):
    """Renderiza el perfil en la barra lateral"""
    from .auth import logout, hash_password, validate_password
    from .database import get_connection
    
    # Corregir: user_info es un diccionario, no una tupla
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
            st.toast("Perfil guardado.", icon="✅")
            st.rerun()
        # Sección de 2FA
        with st.expander("Autenticación de Dos Factores (2FA)"):
            if is_2fa_enabled(st.session_state.user_id):
                st.success("2FA está habilitado para tu cuenta.")
                if st.button("Deshabilitar 2FA", key="disable_2fa", use_container_width=True):
                    if disable_2fa(st.session_state.user_id):
                        st.success("2FA deshabilitado correctamente.")
                        st.rerun()
            else:
                st.warning("2FA no está habilitado para tu cuenta.")
                if st.button("Habilitar 2FA", key="enable_2fa", use_container_width=True):
                    secret, qr_code, recovery_codes = enable_2fa(st.session_state.user_id)
                    
                    # Mostrar QR
                    st.subheader("Escanea este código QR con tu aplicación de autenticación")
                    st.image(f"data:image/png;base64,{qr_code}", width=300)
                    
                    # Mostrar código secreto
                    st.subheader("O ingresa este código manualmente:")
                    st.code(secret)
                    
                    # Mostrar códigos de recuperación
                    st.subheader("Códigos de recuperación")
                    st.warning("Guarda estos códigos en un lugar seguro. Se mostrarán solo una vez.")
                    for code in recovery_codes:
                        st.code(code)
                    
                    st.info("Una vez que hayas configurado tu aplicación de autenticación, cierra sesión y vuelve a iniciar para probar la configuración.")
        st.markdown(
            f"""
            <div class="sidebar-version-badge">Version: {APP_VERSION}</div>
            <style>
            aside[data-testid="stSidebar"] .block-container {{ position: relative; min-height: 100vh; padding-bottom: 0 !important; display: flex; flex-direction: column; }}
            .sidebar-version-badge {{
                position: static;
                margin-top: auto;
                margin-left: 16px;
                margin-bottom: 0;
                font-size: 12px;
                color: #9ca3af;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )

def render_no_view_dashboard(nombre_completo):
    """Renderiza el dashboard para usuarios sin vista asignada"""
    st.header(f"Bienvenido, {nombre_completo}")
    
    st.markdown("""
    <div style="
        background-color: #f8d7da;
        color: #721c24;
        padding: 20px;
        border-radius: 5px;
        border: 1px solid #f5c6cb;
        margin-top: 20px;
        text-align: center;
    ">
        <h3>⚠️ Configuración Pendiente</h3>
        <p>No se configuraron parametros para su departamento.</p>
    </div>
    """, unsafe_allow_html=True)
