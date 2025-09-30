import streamlit as st
from .auth import login_user, create_user, verify_2fa_code, enable_2fa, disable_2fa, is_2fa_enabled

def render_login_tabs():
    """Renderiza las pestañas de login y registro"""
    # Si estamos esperando verificación 2FA
    if st.session_state.get('awaiting_2fa', False):
        render_2fa_verification()
        return
    
    tab1, tab2 = st.tabs(["Login", "Registro"])
    
    with tab1:
        st.header("Login")
        username = st.text_input("Usuario", key="login_username")
        password = st.text_input("Contraseña", type="password", key="login_password")
        if st.button("Ingresar"):
            user_id, is_admin = login_user(username, password)
            if user_id:
                st.session_state.user_id = user_id
                st.session_state.is_admin = is_admin
                st.session_state.mostrar_perfil = False
                st.success("Login exitoso!")
                st.rerun()
            elif st.session_state.get('awaiting_2fa', False):
                st.rerun()  # Recargar para mostrar la pantalla de 2FA
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
            
            c.execute('SELECT nombre, apellido FROM usuarios WHERE id = ?', (st.session_state.user_id,))
            old_user_info = c.fetchone()
            old_nombre = old_user_info[0] if old_user_info[0] else ''
            old_apellido = old_user_info[1] if old_user_info[1] else ''
            old_nombre_completo = f"{old_nombre} {old_apellido}".strip()
            
            # Capitalizar nombre y apellido
            nuevo_nombre_cap = nuevo_nombre.strip().capitalize() if nuevo_nombre else ''
            nuevo_apellido_cap = nuevo_apellido.strip().capitalize() if nuevo_apellido else ''
            
            c.execute('UPDATE usuarios SET nombre = ?, apellido = ?, email = ? WHERE id = ?',
                        (nuevo_nombre_cap, nuevo_apellido_cap, nuevo_email.strip(), st.session_state.user_id))
            
            nuevo_nombre_completo = f"{nuevo_nombre_cap} {nuevo_apellido_cap}".strip()
            
            if old_nombre_completo and nuevo_nombre_completo != old_nombre_completo:
                c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = ?', (old_nombre_completo,))
                old_tecnico = c.fetchone()
                if old_tecnico:
                    c.execute('UPDATE tecnicos SET nombre = ? WHERE nombre = ?', 
                                (nuevo_nombre_completo, old_nombre_completo))
            
            if nuevo_nombre_completo:
                c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = ?', (nuevo_nombre_completo,))
                tecnico = c.fetchone()
                if not tecnico:
                    c.execute('INSERT INTO tecnicos (nombre) VALUES (?)', (nuevo_nombre_completo,))
            
            if nueva_password:
                if nueva_password == confirmar_password:
                    # Validar la contraseña
                    is_valid, messages = validate_password(nueva_password)
                    if is_valid:
                        hashed_password = hash_password(nueva_password)
                        c.execute('UPDATE usuarios SET password = ? WHERE id = ?',
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