import streamlit as st
from .database import get_connection, get_tipos_dataframe_with_roles, get_roles_dataframe
from .utils import show_success_message, safe_rerun

def render_task_type_management():
    """Renderiza la gestión de tipos de tarea (extraído)"""
    st.subheader("Gestión de Tipos de Tarea")
    
    if "task_type_counter" not in st.session_state:
        st.session_state.task_type_counter = 0
    
    roles_df = get_roles_dataframe(exclude_admin=True, exclude_sin_rol=True)
    
    with st.expander("Agregar Tipo de Tarea"):
        new_task_type = st.text_input(
            "Descripción del Tipo de Tarea", 
            key=f"new_task_type_{st.session_state.task_type_counter}"
        )
        
        selected_roles = st.multiselect(
            "Departamentos que pueden acceder a este tipo de tarea",
            options=roles_df['id_rol'].tolist(),
            format_func=lambda x: roles_df.loc[roles_df['id_rol'] == x, 'nombre'].iloc[0],
            key=f"new_task_type_roles_{st.session_state.task_type_counter}"
        )
        
        if st.button("Agregar Tipo de Tarea", key="add_task_type_btn"):
            if new_task_type:
                new_task_type_normalized = ' '.join(new_task_type.strip().split()).title()
                conn = get_connection()
                c = conn.cursor()
                try:
                    c.execute("SELECT id_tipo FROM tipos_tarea WHERE LOWER(TRIM(descripcion)) = LOWER(TRIM(%s))", 
                             (new_task_type_normalized,))
                    existing = c.fetchone()
                    
                    if existing:
                        st.error(f"⚠️ Ya existe un tipo de tarea similar: '{new_task_type_normalized}'")
                    else:
                        c.execute("INSERT INTO tipos_tarea (descripcion) VALUES (%s) RETURNING id_tipo", (new_task_type_normalized,))
                        tipo_id = c.fetchone()[0]
                        
                        for rol_id in selected_roles:
                            c.execute("INSERT INTO tipos_tarea_roles (id_tipo, id_rol) VALUES (%s, %s)", (tipo_id, rol_id))
                        
                        conn.commit()
                        st.success(f"✅ Tipo de tarea '{new_task_type_normalized}' agregado exitosamente.")
                        st.session_state.task_type_counter += 1
                        safe_rerun()
                except Exception as e:
                    st.error(f"❌ Error al agregar tipo de tarea: {str(e)}")
                finally:
                    conn.close()
            else:
                st.error("La descripción del tipo de tarea es obligatoria.")
    
    tipos_df = get_tipos_dataframe_with_roles()
    st.subheader("Tipos de Tarea Existentes")
    if not tipos_df.empty:
        if 'id_tipo' in tipos_df.columns:
            st.dataframe(tipos_df.drop(columns=['id_tipo']), use_container_width=True)
        else:
            st.dataframe(tipos_df, use_container_width=True)
    else:
        st.info("No hay tipos de tarea registrados.")
    
    render_task_type_edit_delete_forms(tipos_df, roles_df)

def render_task_type_edit_delete_forms(tipos_df, roles_df):
    """Formularios de edición y eliminación de tipos de tarea (extraído)"""
    with st.expander("Editar Tipo de Tarea"):
        if not tipos_df.empty:
            tipo_ids = tipos_df['id_tipo'].tolist()
            tipo_descriptions = tipos_df['descripcion'].tolist()
            tipo_options = [f"{tid} - {tdesc}" for tid, tdesc in zip(tipo_ids, tipo_descriptions)]
            
            selected_tipo_edit = st.selectbox("Seleccionar Tipo de Tarea para Editar", 
                                             options=tipo_options, key="select_tipo_edit")
            if selected_tipo_edit:
                tipo_id = int(selected_tipo_edit.split(' - ')[0])
                tipo_row = tipos_df[tipos_df['id_tipo'] == tipo_id].iloc[0]
                
                edit_tipo_desc = st.text_input("Descripción del Tipo de Tarea", value=tipo_row['descripcion'], key="edit_tipo_desc")
                
                # Roles existentes asociados al tipo
                conn = get_connection()
                c = conn.cursor()
                try:
                    c.execute("SELECT id_rol FROM tipos_tarea_roles WHERE id_tipo = %s", (tipo_id,))
                    existing_role_ids = [row[0] for row in c.fetchall()]
                finally:
                    conn.close()
                
                all_role_ids = roles_df['id_rol'].tolist()
                existing_role_ids = [rid for rid in existing_role_ids if rid in all_role_ids]
                
                selected_roles = st.multiselect(
                    "Departamentos permitidos para este tipo",
                    options=all_role_ids,
                    format_func=lambda x: roles_df.loc[roles_df['id_rol'] == x, 'nombre'].iloc[0],
                    default=existing_role_ids,
                    key="edit_task_type_roles"
                )
                
                if st.button("Guardar Cambios de Tipo de Tarea", key="save_tipo_edit"):
                    if edit_tipo_desc:
                        edit_tipo_desc_normalized = ' '.join(edit_tipo_desc.strip().split()).title()
                        conn = get_connection()
                        c = conn.cursor()
                        try:
                            # Actualizar descripción
                            c.execute("UPDATE tipos_tarea SET descripcion = %s WHERE id_tipo = %s", (edit_tipo_desc_normalized, tipo_id))
                            # Reasignar roles: borrar asociaciones previas y crear nuevas
                            c.execute("DELETE FROM tipos_tarea_roles WHERE id_tipo = %s", (tipo_id,))
                            for rol_id in selected_roles:
                                c.execute("INSERT INTO tipos_tarea_roles (id_tipo, id_rol) VALUES (%s, %s)", (tipo_id, rol_id))
                            conn.commit()
                            st.success("Tipo de tarea actualizado exitosamente.")
                            safe_rerun()
                        except Exception as e:
                            st.error(f"Error al actualizar tipo de tarea: {str(e)}")
                        finally:
                            conn.close()
                    else:
                        st.error("La descripción del tipo de tarea es obligatoria.")
        else:
            st.info("No hay tipos de tarea para editar.")
    
    with st.expander("Eliminar Tipo de Tarea"):
        if not tipos_df.empty:
            tipo_ids = tipos_df['id_tipo'].tolist()
            tipo_descriptions = tipos_df['descripcion'].tolist()
            tipo_options = [f"{tid} - {tdesc}" for tid, tdesc in zip(tipo_ids, tipo_descriptions)]
            
            selected_tipo_delete = st.selectbox("Seleccionar Tipo de Tarea para Eliminar", 
                                               options=tipo_options, key="select_tipo_delete")
            if selected_tipo_delete:
                tipo_id = int(selected_tipo_delete.split(' - ')[0])
                tipo_row = tipos_df[tipos_df['id_tipo'] == tipo_id].iloc[0]
                
                st.warning("¿Estás seguro de que deseas eliminar este tipo de tarea? Esta acción no se puede deshacer.")
                st.info(f"**Tipo de tarea a eliminar:** {tipo_row['descripcion']}")
                
                if st.button("Eliminar Tipo de Tarea", key="delete_tipo_btn", type="primary"):
                    conn = get_connection()
                    c = conn.cursor()
                    try:
                        c.execute("SELECT COUNT(*) FROM registros WHERE id_tipo = %s", (tipo_id,))
                        registro_count = c.fetchone()[0]
                        
                        if registro_count > 0:
                            st.error(f"No se puede eliminar el tipo de tarea porque tiene {registro_count} registros asociados.")
                        else:
                            c.execute("DELETE FROM tipos_tarea_roles WHERE id_tipo = %s", (tipo_id,))
                            c.execute("DELETE FROM tipos_tarea_puntajes WHERE id_tipo = %s", (tipo_id,))
                            c.execute("DELETE FROM tipos_tarea WHERE id_tipo = %s", (tipo_id,))
                            conn.commit()
                            show_success_message(f"✅ Tipo de tarea '{tipo_row['descripcion']}' eliminado exitosamente.", 1.5)
                            safe_rerun()
                    except Exception as e:
                        st.error(f"Error al eliminar tipo de tarea: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay tipos de tarea para eliminar.")

def clean_duplicate_task_types():
    """Limpia tipos de tarea duplicados manteniendo solo uno de cada tipo (extraído)"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT id_tipo, descripcion FROM tipos_tarea ORDER BY id_tipo")
        tipos = c.fetchall()
        
        grupos_duplicados = {}
        for id_tipo, descripcion in tipos:
            desc_normalizada = ' '.join(descripcion.strip().split()).lower()
            grupos_duplicados.setdefault(desc_normalizada, []).append((id_tipo, descripcion))
        
        duplicados_a_eliminar = []
        grupos_con_duplicados = 0
        
        for desc_norm, grupo in grupos_duplicados.items():
            if len(grupo) > 1:
                grupos_con_duplicados += 1
                for id_tipo, descripcion in grupo[1:]:
                    duplicados_a_eliminar.append(id_tipo)
        
        deleted_count = 0
        for id_tipo in duplicados_a_eliminar:
            c.execute("SELECT COUNT(*) FROM registros WHERE id_tipo = %s", (id_tipo,))
            registro_count = c.fetchone()[0]
            if registro_count == 0:
                c.execute("DELETE FROM tipos_tarea_roles WHERE id_tipo = %s", (id_tipo,))
                c.execute("DELETE FROM tipos_tarea WHERE id_tipo = %s", (id_tipo,))
                deleted_count += 1
        
        conn.commit()
        return deleted_count, grupos_con_duplicados
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
