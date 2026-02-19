import streamlit as st
from .database import get_modalidades_dataframe, get_connection
from .utils import show_success_message, show_ordered_dataframe_with_labels, safe_rerun

def render_modality_management():
    """Renderiza la gestión de modalidades (extraído)"""
    st.subheader("Gestión de Modalidades")
    
    with st.expander("Agregar Modalidad"):
        new_modality = st.text_input("Nombre de la Modalidad", key="new_modality")
        
        if st.button("Agregar Modalidad", key="add_modality_btn"):
            if new_modality:
                new_modality_normalized = ' '.join(new_modality.strip().split()).title()
                conn = get_connection()
                c = conn.cursor()
                try:
                    c.execute("INSERT INTO modalidades_tarea (descripcion) VALUES (%s)", (new_modality_normalized,))
                    conn.commit()
                    st.success(f"Modalidad '{new_modality_normalized}' agregada exitosamente.")
                    safe_rerun()
                except Exception as e:
                    if "UNIQUE constraint failed" in str(e):
                        st.error(f"Esta modalidad ya existe: '{new_modality_normalized}'")
                    else:
                        st.error(f"Error al agregar modalidad: {str(e)}")
                finally:
                    conn.close()
            else:
                st.error("El nombre de la modalidad es obligatorio.")
    
    st.subheader("Modalidades Existentes")
    modalidades_df = get_modalidades_dataframe()
    if not modalidades_df.empty:
        rename_map = {"descripcion": "Modalidad"}
        show_ordered_dataframe_with_labels(modalidades_df, ["descripcion"], ["id_modalidad"], rename_map)
    else:
        rename_map = {"descripcion": "Modalidad"}
        show_ordered_dataframe_with_labels(modalidades_df, ["descripcion"], ["id_modalidad"], rename_map)
    
    render_modality_edit_delete_forms(modalidades_df)

def render_modality_edit_delete_forms(modalidades_df):
    """Formularios de edición y eliminación de modalidades (extraído)"""
    with st.expander("Editar Modalidad"):
        if not modalidades_df.empty:
            modalidad_ids = modalidades_df['id_modalidad'].tolist()
            modalidad_names = modalidades_df['descripcion'].tolist()
            modalidad_options = [f"{mid} - {mname}" for mid, mname in zip(modalidad_ids, modalidad_names)]
            
            selected_modalidad_edit = st.selectbox("Seleccionar Modalidad para Editar", 
                                                   options=modalidad_options, key="select_modalidad_edit")
            if selected_modalidad_edit:
                modalidad_id = int(selected_modalidad_edit.split(' - ')[0])
                modalidad_row = modalidades_df[modalidades_df['id_modalidad'] == modalidad_id].iloc[0]
                
                edit_modalidad_name = st.text_input("Nombre de la Modalidad", value=modalidad_row['descripcion'], key="edit_modalidad_name")
                
                if st.button("Guardar Cambios de Modalidad", key="save_modalidad_edit"):
                    if edit_modalidad_name:
                        edit_modalidad_name_normalized = ' '.join(edit_modalidad_name.strip().split()).title()
                        conn = get_connection()
                        c = conn.cursor()
                        try:
                            c.execute("UPDATE modalidades_tarea SET descripcion = %s WHERE id_modalidad = %s", (edit_modalidad_name_normalized, modalidad_id))
                            conn.commit()
                            st.success(f"Modalidad actualizada a '{edit_modalidad_name_normalized}' exitosamente.")
                            safe_rerun()
                        except Exception as e:
                            if "UNIQUE constraint failed" in str(e):
                                st.error(f"Ya existe una modalidad con ese nombre: '{edit_modalidad_name_normalized}'")
                            else:
                                st.error(f"Error al actualizar modalidad: {str(e)}")
                        finally:
                            conn.close()
                    else:
                        st.error("El nombre de la modalidad es obligatorio.")
        else:
            st.info("No hay modalidades para editar.")
    
    with st.expander("Eliminar Modalidad"):
        if not modalidades_df.empty:
            modalidad_ids = modalidades_df['id_modalidad'].tolist()
            modalidad_names = modalidades_df['descripcion'].tolist()
            modalidad_options = [f"{mid} - {mname}" for mid, mname in zip(modalidad_ids, modalidad_names)]
            
            selected_modalidad_delete = st.selectbox("Seleccionar Modalidad para Eliminar", 
                                                     options=modalidad_options, key="select_modalidad_delete")
            if selected_modalidad_delete:
                modalidad_id = int(selected_modalidad_delete.split(' - ')[0])
                modalidad_row = modalidades_df[modalidades_df['id_modalidad'] == modalidad_id].iloc[0]
                
                st.warning("¿Estás seguro de que deseas eliminar esta modalidad? Esta acción no se puede deshacer.")
                st.info(f"**Modalidad a eliminar:** {modalidad_row['descripcion']}")
                
                if st.button("Eliminar Modalidad", key="delete_modalidad_btn", type="primary"):
                    conn = get_connection()
                    c = conn.cursor()
                    try:
                        c.execute("SELECT COUNT(*) FROM registros WHERE id_modalidad = %s", (modalidad_id,))
                        registro_count = c.fetchone()[0]
                        
                        if registro_count > 0:
                            st.error(f"No se puede eliminar la modalidad porque tiene {registro_count} registros asociados.")
                        else:
                            c.execute("DELETE FROM modalidades_tarea WHERE id_modalidad = %s", (modalidad_id,))
                            conn.commit()
                            show_success_message(f"✅ Modalidad '{modalidad_row['descripcion']}' eliminada exitosamente.", 1.5)
                    except Exception as e:
                        st.error(f"Error al eliminar modalidad: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay modalidades para eliminar.")
