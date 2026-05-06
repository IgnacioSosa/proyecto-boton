import streamlit as st
import pandas as pd
from datetime import datetime

from .database import (
    get_roles_dataframe,
    get_users_dataframe,
    get_connection,
    generate_users_from_nomina,
)
from .config import SYSTEM_ROLES
from .auth import create_user, validate_password, hash_password, is_2fa_enabled, unlock_user
from .utils import show_success_message, show_ordered_dataframe_with_labels, safe_rerun

def _is_valid_email(value: str) -> bool:
    email = str(value or "").strip()
    if not email:
        return True
    if " " in email:
        return False
    if "@" not in email:
        return False
    local, _, domain = email.partition("@")
    if not local or not domain:
        return False
    if "." not in domain:
        return False
    return True

def render_user_management():
    """Renderiza la gestión de usuarios (extraída de admin_panel.py)"""
    st.subheader("Gestión de Usuarios")
    
    # Obtener roles disponibles
    roles_df = get_roles_dataframe(exclude_hidden=False) 
    
    # Inicializar estado de generación de usuarios si no existe
    if 'generating_users' not in st.session_state:
        st.session_state.generating_users = False
    
    # Botón para generar usuarios automáticamente desde la nómina
    with st.expander("👤 Generar Usuarios desde Nómina", expanded=False):
        st.info("Esta función creará usuarios automáticamente para los empleados en la nómina que aún no tienen usuario asociado.")
        
        # Deshabilitar checkbox si se está generando usuarios
        enable_users_on_creation = st.checkbox(
            "Habilitar usuarios durante creación", 
            value=False, 
            help="Si está marcado, los usuarios creados estarán activos inmediatamente. Si no está marcado, los usuarios se crearán deshabilitados.",
            disabled=st.session_state.generating_users  # Bloquear durante generación
        )
        
        # Mostrar mensaje de estado si se está procesando
        if st.session_state.generating_users:
            st.warning("🔄 Generación de usuarios en proceso... Por favor espere.")
        
        # Deshabilitar botón si ya se está procesando
        generate_button_disabled = st.session_state.generating_users
        
        if st.button("🔄 Generar Usuarios", 
                    type="primary", 
                    key="generate_users_user_tab",
                    disabled=generate_button_disabled):
            
            # Activar estado de generación
            st.session_state.generating_users = True
            
            try:
                with st.spinner("Generando usuarios..."):
                    stats = generate_users_from_nomina(enable_users=enable_users_on_creation)
                    
                    if stats["total_empleados"] == 0:
                        st.error("⚠️ NO SE DETECTARON NUEVOS USUARIOS PARA GENERAR. Todos los empleados en la nómina ya tienen usuarios asociados o no hay empleados en la nómina.")
                    else:
                        if stats["usuarios_creados"] > 0:
                            st.success(f"✅ Se crearon {stats['usuarios_creados']} nuevos usuarios")
                            st.info(f"📊 También se crearon {stats['tecnicos_creados']} técnicos asociados")
                            
                            if stats.get('usuarios_generados'):
                                st.subheader("👥 Usuarios Generados")
                                df_usuarios = pd.DataFrame(stats['usuarios_generados'])
                                st.dataframe(df_usuarios, use_container_width=True)
                                csv = df_usuarios.to_csv(index=False)
                                st.download_button(
                                    label="📥 Descargar lista de usuarios (CSV)",
                                    data=csv,
                                    file_name=f"usuarios_generados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                    mime="text/csv"
                                )
                        
                        if stats["usuarios_sin_email"] > 0:
                            st.warning(f"⚠️ No se generaron {stats['usuarios_sin_email']} usuarios por falta de correo electrónico")
                            with st.expander("Ver empleados sin correo"):
                                for empleado in stats["empleados_sin_email"]:
                                    st.write(f"• {empleado}")
                        
                        if stats["usuarios_duplicados"] > 0:
                            st.info(f"ℹ️ Se omitieron {stats['usuarios_duplicados']} usuarios duplicados")
                            with st.expander("Ver empleados duplicados omitidos"):
                                for empleado in stats["empleados_duplicados"]:
                                    st.write(f"• {empleado}")
                        
                        if stats["errores"]:
                            st.error(f"❌ Ocurrieron {len(stats['errores'])} errores durante la creación de usuarios")
                            with st.expander("Ver errores"):
                                for error in stats["errores"]:
                                    st.error(error)
            
            except Exception as e:
                st.error(f"❌ Error inesperado durante la generación de usuarios: {str(e)}")
            
            finally:
                # Desactivar estado de generación al finalizar (exitoso o con error)
                st.session_state.generating_users = False
                # Forzar recarga para actualizar la interfaz
                safe_rerun()
    
    # Formulario para crear usuarios 
    with st.expander("Crear Usuario"):
        new_user_username = st.text_input("Usuario", key="new_user_username")
        new_user_password = st.text_input("Contraseña", type="password", key="new_user_password")
        new_user_nombre = st.text_input("Nombre", key="new_user_nombre")
        new_user_apellido = st.text_input("Apellido", key="new_user_apellido")
        new_user_email = st.text_input("Email", key="new_user_email")
        
        rol_options = [f"{row['id_rol']} - {row['nombre']}" for _, row in roles_df.iterrows()]
        default_index = 0
        for i, option in enumerate(rol_options):
            if SYSTEM_ROLES['SIN_ROL'] in option.lower():
                default_index = i
                break
        
        selected_rol = st.selectbox("Departamento", options=rol_options, index=default_index, key="new_user_rol")
        
        if selected_rol is not None:
            rol_id = int(selected_rol.split(' - ')[0])
        else:
            st.error("Por favor selecciona un rol")
            rol_id = None
        
        st.info("La contraseña debe tener al menos 8 caracteres, una letra mayúscula, una letra minúscula, un número y un carácter especial.")
        
        if st.button("Crear Usuario", key="create_user_btn"):
            if new_user_username and new_user_password:
                if not _is_valid_email(new_user_email):
                    st.error("Email inválido.")
                    return
                email_value = (new_user_email or "").strip() or None
                if create_user(new_user_username, new_user_password, 
                               new_user_nombre, new_user_apellido, email_value, rol_id):
                    st.success(f"Usuario {new_user_username} creado exitosamente.")
                    safe_rerun()
            else:
                st.error("Usuario y contraseña son obligatorios.")
    
    st.subheader("Usuarios Existentes")
    users_df = get_users_dataframe()
    
    rename_map = {
        "username": "Usuario",
        "nombre": "Nombre",
        "apellido": "Apellido",
        "email": "Email",
        "rol_id": "Departamento",
        "is_active": "Activo"
    }
    show_ordered_dataframe_with_labels(users_df, ["username", "nombre", "apellido", "email", "rol_id", "is_active"], ["id"], rename_map)
    
    render_user_edit_delete_forms(users_df, roles_df)

def render_user_edit_delete_forms(users_df, roles_df):
    """Agrupa edición y eliminación como en el archivo original"""
    render_user_edit_form(users_df, roles_df)
    render_user_delete_form(users_df)

def render_user_edit_form(users_df, roles_df):
    """Renderiza el formulario de edición de usuarios"""
    with st.expander("Editar Usuario"):
        if not users_df.empty:
            user_ids = users_df['id'].tolist()
            user_usernames = users_df['username'].tolist()
            id_to_username = {uid: uname for uid, uname in zip(user_ids, user_usernames)}
            
            selected_user_edit = st.selectbox(
                "Seleccionar Usuario para Editar",
                options=user_ids,
                format_func=lambda uid: id_to_username.get(uid, str(uid)),
                key="select_user_edit"
            )
            if selected_user_edit:
                user_id = int(selected_user_edit)
                user_row = users_df[users_df['id'] == user_id].iloc[0]
                
                disable_critical_fields = user_id == st.session_state.user_id
                if disable_critical_fields:
                    st.warning("Editando tu propio usuario. Algunos campos están restringidos.")
                
                edit_nombre = st.text_input("Nombre", value=user_row['nombre'] or "", key="edit_user_nombre")
                edit_apellido = st.text_input("Apellido", value=user_row['apellido'] or "", key="edit_user_apellido")
                current_email_raw = user_row.get('email', '')
                current_email = "" if str(current_email_raw).strip().lower() in {"none", "nan"} else str(current_email_raw or "").strip()
                edit_email = st.text_input("Email", value=current_email, key="edit_user_email")
                
                conn = get_connection()
                c = conn.cursor()
                c.execute("SELECT rol_id FROM usuarios WHERE id = %s", (user_id,))
                current_rol_id = c.fetchone()
                conn.close()
                
                if user_row['username'].lower() == 'admin':
                    admin_rol = roles_df[roles_df['nombre'].str.lower() == 'admin']
                    if not admin_rol.empty:
                        admin_rol_id = admin_rol.iloc[0]['id_rol']
                        rol_options = [f"{admin_rol_id} - admin"]
                        selected_rol = rol_options[0]
                        rol_id = admin_rol_id
                        st.info("El usuario 'admin' debe mantener el rol de administrador.")
                else:
                    rol_options = [f"{row['id_rol']} - {row['nombre']}" for _, row in roles_df.iterrows()]
                    default_index = 0
                    if current_rol_id and current_rol_id[0]:
                        for i, option in enumerate(rol_options):
                            if option.startswith(f"{current_rol_id[0]} -"):
                                default_index = i
                                break
                    
                    selected_rol = st.selectbox("Departamento", options=rol_options, 
                                                index=default_index, key="edit_user_rol",
                                                disabled=disable_critical_fields)
                    rol_id = int(selected_rol.split(' - ')[0])
                
                edit_is_active = st.checkbox("Usuario Activo", value=bool(user_row['is_active']), 
                                             key="edit_user_is_active", disabled=disable_critical_fields)
                
                is_2fa_enabled_db = is_2fa_enabled(user_id)
                edit_is_2fa_enabled = st.checkbox("Autenticación de dos factores (2FA)", 
                                                  value=is_2fa_enabled_db,
                                                  key="edit_user_2fa",
                                                  help="Habilita o deshabilita la autenticación de dos factores para este usuario")
                
                try:
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute("SELECT failed_attempts, lockout_until FROM usuarios WHERE id = %s", (user_id,))
                    lock_row = c.fetchone()
                    conn.close()
                except Exception as e:
                    from .logging_utils import log_app_error
                    log_app_error(e, module="admin_users", function="render_user_edit_form")
                    lock_row = None

                failed_attempts = int(lock_row[0] or 0) if lock_row else 0
                lockout_until = lock_row[1] if lock_row else None

                now = datetime.utcnow()
                locked = bool(lockout_until and now < lockout_until)
                if locked:
                    remaining_minutes = max(0, int((lockout_until - now).total_seconds() // 60) + 1)
                    st.warning(f"Este usuario está bloqueado por intentos fallidos. Tiempo restante ~{remaining_minutes} minuto(s).")
                else:
                    st.info("El usuario no está bloqueado actualmente.")

                clicked = st.button(
                    "Desbloquear Usuario",
                    key=f"unlock_user_{user_id}",
                    type="primary",
                    use_container_width=True,
                    disabled=not locked
                )
                if clicked and locked:
                    if unlock_user(user_row['username']):
                        st.success("Usuario desbloqueado correctamente.")
                        safe_rerun()
                    else:
                        st.error("No se pudo desbloquear el usuario.")
                
                change_password = st.checkbox("Cambiar Contraseña", key="change_password_check")
                new_password = ""
                if change_password:
                    new_password = st.text_input("Nueva Contraseña", type="password", key="edit_user_password")
                    st.info("La contraseña debe tener al menos 8 caracteres, una letra mayúscula, una letra minúscula, un número y un carácter especial.")
                
                if st.button("Guardar Cambios de Usuario", key="save_user_edit"):
                    conn = get_connection()
                    c = conn.cursor()
                    
                    try:
                        if not _is_valid_email(edit_email):
                            st.error("Email inválido.")
                            conn.close()
                            return
                        email_value = (edit_email or "").strip() or None
                        c.execute('SELECT nombre FROM roles WHERE id_rol = %s', (rol_id,))
                        rol_nombre = c.fetchone()
                        is_admin = bool(rol_nombre and rol_nombre[0].lower() == 'admin')
                        
                        c.execute(
                            """
                            UPDATE usuarios
                            SET nombre = %s,
                                apellido = %s,
                                email = %s,
                                is_admin = %s,
                                is_active = %s,
                                rol_id = %s,
                                is_2fa_enabled = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                            """,
                            (
                                edit_nombre,
                                edit_apellido,
                                email_value,
                                is_admin,
                                edit_is_active,
                                rol_id,
                                edit_is_2fa_enabled,
                                user_id,
                            ),
                        )
                        
                        if change_password and new_password:
                            is_valid, messages = validate_password(new_password)
                            if is_valid:
                                hashed_password = hash_password(new_password)
                                c.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s", 
                                         (hashed_password, user_id))
                            else:
                                for message in messages:
                                    st.error(message)
                                conn.close()
                                return
                        
                        conn.commit()
                        st.success("Usuario actualizado exitosamente.")
                        try:
                            from . import admin_planning as _admin_planning
                            _admin_planning.cached_get_users_by_rol.clear()
                            _admin_planning.cached_get_users_dataframe.clear()
                        except Exception:
                            pass
                        safe_rerun()
                    except Exception as e:
                        st.error(f"Error al actualizar usuario: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay usuarios para editar.")

def render_user_delete_form(users_df):
    """Renderiza el formulario de eliminación de usuarios"""
    with st.expander("Eliminar Usuario"):
        if not users_df.empty:
            user_ids = users_df['id'].tolist()
            user_usernames = users_df['username'].tolist()
            id_to_username = {uid: uname for uid, uname in zip(user_ids, user_usernames)}
            
            selected_user_delete = st.selectbox(
                "Seleccionar Usuario para Eliminar",
                options=user_ids,
                format_func=lambda uid: id_to_username.get(uid, str(uid)),
                key="select_user_delete"
            )
            if selected_user_delete:
                user_id = int(selected_user_delete)
                user_row = users_df[users_df['id'] == user_id].iloc[0]
                
                if user_id == st.session_state.user_id:
                    st.error("No puedes eliminar tu propio usuario.")
                else:
                    st.warning("¿Estás seguro de que deseas eliminar este usuario? Esta acción no se puede deshacer.")
                    
                    st.info(f"**Usuario a eliminar:**\n"
                            f"- **ID:** {user_row['id']}\n"
                            f"- **Usuario:** {user_row['username']}\n"
                            f"- **Nombre:** {user_row['nombre'] or 'N/A'}\n"
                            f"- **Apellido:** {user_row['apellido'] or 'N/A'}\n"
                            f"- **Es Admin:** {'Sí' if user_row['is_admin'] else 'No'}\n"
                            f"- **Activo:** {'Sí' if user_row['is_active'] else 'No'}")
                    
                    if st.button("Eliminar Usuario", key="delete_user_btn", type="primary"):
                        delete_user(user_id, user_row['username'])
        else:
            st.info("No hay usuarios para eliminar.")

def delete_user(user_id, username):
    """Elimina un usuario y sus registros asociados"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) FROM registros WHERE usuario_id = %s", (user_id,))
        registro_count = c.fetchone()[0]
        
        if registro_count > 0:
            c.execute("DELETE FROM registros WHERE usuario_id = %s", (user_id,))
            st.info(f"Se eliminaron {registro_count} registros asociados al usuario.")
        
        c.execute("DELETE FROM usuarios WHERE id = %s", (user_id,))
        conn.commit()
        try:
            from . import admin_planning as _admin_planning
            _admin_planning.cached_get_users_by_rol.clear()
            _admin_planning.cached_get_users_dataframe.clear()
        except Exception:
            pass
        
        if registro_count > 0:
            show_success_message(f"✅ Usuario '{username}' y sus {registro_count} registros eliminados exitosamente.", 1.5)
        else:
            show_success_message(f"✅ Usuario '{username}' eliminado exitosamente.", 1.5)
        safe_rerun()
    except Exception as e:
        st.error(f"Error al eliminar usuario: {str(e)}")
    finally:
        conn.close()
