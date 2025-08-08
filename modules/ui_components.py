import streamlit as st
from .auth import login_user, create_user

def render_login_tabs():
    """Renderiza las pestañas de login y registro"""
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

def render_sidebar_profile(user_info):
    """Renderiza el perfil en la barra lateral"""
    from .auth import logout, hash_password, validate_password
    from .database import get_connection
    
    nombre_actual = user_info[0] if user_info[0] else ''
    apellido_actual = user_info[1] if user_info[1] else ''
    current_username = user_info[2]
    email_actual = user_info[3] if user_info[3] else ''
    
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