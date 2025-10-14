import streamlit as st
from .database import get_clientes_dataframe, get_connection
from .utils import show_success_message

def render_client_management():
    """Renderiza la gestión de clientes (extraído desde admin_panel.py)"""
    st.subheader("🏢 Gestión de Clientes")
    
    clients_df = get_clientes_dataframe()
    
    if not clients_df.empty:
        st.subheader("Clientes Existentes")
        st.dataframe(clients_df, use_container_width=True)
    else:
        st.info("No hay clientes registrados.")
    
    with st.expander("Agregar Nuevo Cliente"):
        new_client_name = st.text_input("Nombre del Cliente", key="new_client_name")
        new_client_address = st.text_input("Dirección (opcional)", key="new_client_address")
        new_client_phone = st.text_input("Teléfono (opcional)", key="new_client_phone")
        new_client_email = st.text_input("Email (opcional)", key="new_client_email")
        
        if st.button("Agregar Cliente", key="add_client_btn", type="primary"):
            if new_client_name:
                new_client_name_normalized = ' '.join(new_client_name.strip().split()).title()
                
                conn = get_connection()
                c = conn.cursor()
                try:
                    c.execute(
                        "INSERT INTO clientes (nombre, direccion, telefono, email) VALUES (%s, %s, %s, %s)", 
                        (new_client_name_normalized, new_client_address or '', new_client_phone or '', new_client_email or '')
                    )
                    conn.commit()
                    st.success(f"Cliente '{new_client_name_normalized}' agregado exitosamente.")
                    st.rerun()
                except Exception as e:
                    if "UNIQUE constraint failed" in str(e) or "duplicate key value" in str(e):
                        st.error(f"Ya existe un cliente con ese nombre: '{new_client_name_normalized}'")
                    else:
                        st.error(f"Error al agregar cliente: {str(e)}")
                finally:
                    conn.close()
            else:
                st.error("El nombre del cliente es obligatorio.")
    
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
                
                edit_client_name = st.text_input("Nombre del Cliente", value=client_row['nombre'], key="edit_client_name")
                
                if st.button("Guardar Cambios de Cliente", key="save_client_edit"):
                    if edit_client_name:
                        edit_client_name_normalized = ' '.join(edit_client_name.strip().split()).title()
                        
                        conn = get_connection()
                        c = conn.cursor()
                        try:
                            c.execute("UPDATE clientes SET nombre = %s WHERE id_cliente = %s", (edit_client_name_normalized, client_id))
                            conn.commit()
                            st.success(f"Cliente actualizado a '{edit_client_name_normalized}' exitosamente.")
                            st.rerun()
                        except Exception as e:
                            if "UNIQUE constraint failed" in str(e) or "duplicate key value" in str(e):
                                st.error(f"Ya existe un cliente con ese nombre: '{edit_client_name_normalized}'")
                            else:
                                st.error(f"Error al actualizar cliente: {str(e)}")
                        finally:
                            conn.close()
                    else:
                        st.error("El nombre del cliente es obligatorio.")
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