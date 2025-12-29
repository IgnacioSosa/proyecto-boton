import streamlit as st
from .database import get_clientes_dataframe, get_connection, ensure_clientes_schema
from .utils import show_success_message
import re

def _validate_cuit(c):
    c = "".join(filter(str.isdigit, str(c)))
    if len(c) != 11: return False
    base = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    aux = 0
    for i in range(10): aux += int(c[i]) * base[i]
    aux = 11 - (aux % 11)
    if aux == 11: aux = 0
    elif aux == 10: aux = 9
    return int(c[10]) == aux

def render_client_management():
    """Renderiza solo la vista de clientes existentes"""
    ensure_clientes_schema()
    st.subheader("🏢 Clientes")
    clients_df = get_clientes_dataframe()
    if not clients_df.empty:
        st.dataframe(clients_df, use_container_width=True)
    else:
        st.info("No hay clientes registrados.")

def render_client_crud_management():
    """Renderiza alta/edición/eliminación de clientes"""
    ensure_clientes_schema()
    st.subheader("⚙️ Gestión de Clientes")
    clients_df = get_clientes_dataframe()
    with st.expander("Agregar Nuevo Cliente", expanded=True):
        new_client_cuit = st.text_input("CUIT", key="new_client_cuit")
        new_client_name = st.text_input("Nombre (Razón Social)", key="new_client_name")
        new_client_email = st.text_input("Email", key="new_client_email")
        new_client_phone = st.text_input("Teléfono", key="new_client_phone")
        new_client_cel = st.text_input("Celular", key="new_client_cel")
        new_client_web = st.text_input("Web (URL)", key="new_client_web")
        
        if st.button("Agregar Cliente", key="add_client_btn", type="primary"):
            errors = []
            
            # CUIT Validation
            if not (new_client_cuit or "").strip():
                errors.append("El CUIT es obligatorio.")
            elif not _validate_cuit(new_client_cuit):
                errors.append("El CUIT no es válido (verifique 11 dígitos y dígito verificador).")
            
            # Nombre Validation
            if not (new_client_name or "").strip():
                errors.append("El nombre es obligatorio.")
            
            # Email Validation
            email_val = (new_client_email or "").strip()
            if not email_val:
                errors.append("El email es obligatorio.")
            elif not re.match(r"[^@]+@[^@]+\.[^@]+", email_val):
                errors.append("El formato del email no es válido.")
            
            # Teléfono Validation
            tel_val = (new_client_phone or "").strip()
            if not tel_val:
                errors.append("El teléfono es obligatorio.")
            elif not tel_val.isdigit():
                 errors.append("El teléfono debe contener solo números.")
            
            # Celular Validation
            if not (new_client_cel or "").strip():
                errors.append("El celular es obligatorio.")

            # Web Validation
            web_val = (new_client_web or "").strip()
            if web_val:
                web_ok = web_val.lower().startswith("http://") or web_val.lower().startswith("https://")
                if not web_ok:
                    errors.append("La web debe ser una URL válida (http/https).")
            
            if errors:
                for e in errors:
                    st.error(e)
            else:
                # Verificar duplicados
                is_dup, dup_msg = check_client_duplicate((new_client_cuit or "").strip(), (new_client_name or "").strip())
                if is_dup:
                    st.error(dup_msg)
                else:
                    new_client_name_normalized = new_client_name.strip().upper()
                    conn = get_connection()
                c = conn.cursor()
                try:
                    # Intenta insertar con los nuevos campos. 
                    # Asumimos que la tabla tiene: nombre, cuit, email, telefono, celular, web
                    # Si 'direccion' u 'organizacion' son requeridos, pasamos string vacío.
                    c.execute(
                        """
                        INSERT INTO clientes (nombre, cuit, email, telefono, celular, web, organizacion, direccion) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, 
                        (
                            new_client_name_normalized, 
                            (new_client_cuit or "").strip(),
                            email_val,
                            tel_val,
                            (new_client_cel or "").strip(),
                            web_val,
                            "", # Organizacion vacía por defecto
                            ""  # Direccion vacía por defecto
                        )
                    )
                    conn.commit()
                    st.success(f"Cliente '{new_client_name_normalized}' agregado exitosamente.")
                    st.rerun()
                except Exception as e:
                    if "UNIQUE constraint failed" in str(e) or "duplicate key value" in str(e):
                        st.error(f"Ya existe un cliente con ese nombre o CUIT.")
                    elif "column" in str(e) and "does not exist" in str(e):
                        # Fallback si columnas no existen (aunque deberían)
                        st.error(f"Error de base de datos (columnas faltantes): {str(e)}")
                    else:
                        st.error(f"Error al agregar cliente: {str(e)}")
                finally:
                    conn.close()
    
    render_client_edit_delete_forms(clients_df)

def render_client_edit_delete_forms(clients_df):
    """Formularios de edición y eliminación de clientes (extraído)"""
    with st.expander("Editar Cliente"):
        if not clients_df.empty:
            client_ids = clients_df['id_cliente'].tolist()
            client_names = clients_df['nombre'].tolist()
            client_options = [f"{cid} - {cname}" for cid, cname in zip(client_ids, client_names)]
            
            selected_client_edit = st.selectbox("Seleccionar Cliente para Editar", 
                                               options=client_options, key="select_client_edit")
            if selected_client_edit:
                client_id = int(selected_client_edit.split(' - ')[0])
                client_row = clients_df[clients_df['id_cliente'] == client_id].iloc[0]
                
                # Obtener valores actuales (con fallback seguro)
                curr_cuit = client_row['cuit'] if 'cuit' in client_row else ""
                curr_email = client_row['email'] if 'email' in client_row else ""
                curr_phone = client_row['telefono'] if 'telefono' in client_row else ""
                curr_cel = client_row['celular'] if 'celular' in client_row else ""
                curr_web = client_row['web'] if 'web' in client_row else ""
                
                edit_cuit = st.text_input("CUIT", value=str(curr_cuit or ""), key="edit_client_cuit")
                edit_name = st.text_input("Nombre (Razón Social)", value=client_row['nombre'], key="edit_client_name")
                edit_email = st.text_input("Email", value=str(curr_email or ""), key="edit_client_email")
                edit_phone = st.text_input("Teléfono", value=str(curr_phone or ""), key="edit_client_phone")
                edit_cel = st.text_input("Celular", value=str(curr_cel or ""), key="edit_client_cel")
                edit_web = st.text_input("Web (URL)", value=str(curr_web or ""), key="edit_client_web")
                
                if st.button("Guardar Cambios de Cliente", key="save_client_edit"):
                    errors = []
                    # Validations (Same as Create)
                    if not (edit_cuit or "").strip():
                        errors.append("El CUIT es obligatorio.")
                    elif not _validate_cuit(edit_cuit):
                        errors.append("El CUIT no es válido.")
                    
                    if not (edit_name or "").strip():
                        errors.append("El nombre es obligatorio.")
                        
                    email_val = (edit_email or "").strip()
                    if not email_val:
                        errors.append("El email es obligatorio.")
                    elif not re.match(r"[^@]+@[^@]+\.[^@]+", email_val):
                        errors.append("El formato del email no es válido.")
                        
                    tel_val = (edit_phone or "").strip()
                    if not tel_val:
                        errors.append("El teléfono es obligatorio.")
                    elif not tel_val.isdigit():
                         errors.append("El teléfono debe contener solo números.")

                    if not (edit_cel or "").strip():
                        errors.append("El celular es obligatorio.")

                    web_val = (edit_web or "").strip()
                    if web_val:
                        web_ok = web_val.lower().startswith("http://") or web_val.lower().startswith("https://")
                        if not web_ok:
                            errors.append("La web debe ser una URL válida.")

                    if errors:
                        for e in errors:
                            st.error(e)
                    else:
                        edit_name_normalized = edit_name.strip().upper()
                        conn = get_connection()
                        c = conn.cursor()
                        try:
                            c.execute(
                                """
                                UPDATE clientes 
                                SET nombre = %s, cuit = %s, email = %s, telefono = %s, celular = %s, web = %s
                                WHERE id_cliente = %s
                                """, 
                                (
                                    edit_name_normalized, 
                                    (edit_cuit or "").strip(),
                                    email_val,
                                    tel_val,
                                    (edit_cel or "").strip(),
                                    web_val,
                                    client_id
                                )
                            )
                            conn.commit()
                            st.success(f"Cliente actualizado a '{edit_name_normalized}' exitosamente.")
                            st.rerun()
                        except Exception as e:
                            if "UNIQUE constraint failed" in str(e) or "duplicate key value" in str(e):
                                st.error(f"Ya existe un cliente con ese nombre o CUIT.")
                            else:
                                st.error(f"Error al actualizar cliente: {str(e)}")
                        finally:
                            conn.close()
        else:
            st.info("No hay clientes para editar.")
    
    with st.expander("Eliminar Cliente"):
        if not clients_df.empty:
            client_ids = clients_df['id_cliente'].tolist()
            client_names = clients_df['nombre'].tolist()
            client_options = [f"{cid} - {cname}" for cid, cname in zip(client_ids, client_names)]
            
            selected_client_delete = st.selectbox("Seleccionar Cliente para Eliminar", 
                                                 options=client_options, key="select_client_delete")
            if selected_client_delete:
                client_id = int(selected_client_delete.split(' - ')[0])
                client_row = clients_df[clients_df['id_cliente'] == client_id].iloc[0]
                
                st.warning("¿Estás seguro de que deseas eliminar este cliente? Esta acción no se puede deshacer.")
                st.info(f"**Cliente a eliminar:** {client_row['nombre']}")
                
                if st.button("Eliminar Cliente", key="delete_client_btn", type="primary"):
                    conn = get_connection()
                    c = conn.cursor()
                    try:
                        c.execute("SELECT COUNT(*) FROM registros WHERE id_cliente = %s", (client_id,))
                        registro_count = c.fetchone()[0]
                        
                        if registro_count > 0:
                            st.error(f"No se puede eliminar el cliente porque tiene {registro_count} registros asociados.")
                        else:
                            c.execute("DELETE FROM clientes WHERE id_cliente = %s", (client_id,))
                            conn.commit()
                            show_success_message(f"✅ Cliente '{client_row['nombre']}' eliminado exitosamente.", 1.5)
                    except Exception as e:
                        st.error(f"Error al eliminar cliente: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay clientes para eliminar.")