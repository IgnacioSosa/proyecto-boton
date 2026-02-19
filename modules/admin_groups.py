import streamlit as st
import pandas as pd

from .database import (
    get_roles_dataframe,
    add_grupo,
    get_grupos_dataframe,
    get_roles_by_grupo,
    update_grupo_roles,
    get_connection,
)
from .utils import show_success_message, normalize_text, show_ordered_dataframe_with_labels


def render_grupo_management():
    """Renderiza la gestión de grupos"""
    st.header("Gestión de Grupos")

    roles_df = get_roles_dataframe()

    with st.expander("Agregar Nuevo Grupo", expanded=False):
        nombre_grupo = st.text_input("Nombre del Grupo", key="new_grupo_nombre")
        descripcion_grupo = st.text_area("Descripción (opcional)", key="new_grupo_desc", max_chars=250)

        selected_roles = st.multiselect(
            "Departamentos asignados a este grupo",
            options=roles_df['id_rol'].tolist(),
            format_func=lambda x: roles_df.loc[roles_df['id_rol'] == x, 'nombre'].iloc[0],
            key="new_grupo_roles",
        )

        if st.button("Agregar Grupo", key="add_grupo_btn"):
            if nombre_grupo:
                if add_grupo(nombre_grupo, descripcion_grupo):
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute("SELECT id_grupo FROM grupos WHERE nombre = %s", (nombre_grupo,))
                    nuevo_grupo_id = c.fetchone()[0]
                    conn.close()

                    update_grupo_roles(nuevo_grupo_id, selected_roles)
                    show_success_message(f"✅ Grupo '{nombre_grupo}' agregado exitosamente.", 1.5)
                else:
                    st.error("Ya existe un grupo con ese nombre.")
            else:
                st.error("El nombre del grupo es obligatorio.")

    grupos_df = get_grupos_dataframe()
    if not grupos_df.empty:
        st.subheader("Grupos Existentes")
        rename_map = {"nombre": "Nombre", "descripcion": "Descripción"}
        show_ordered_dataframe_with_labels(grupos_df, ["nombre", "descripcion"], ["id_grupo"], rename_map)

        render_grupo_edit_delete_forms(grupos_df)
    else:
        st.info("No hay grupos registrados.")


def render_grupo_edit_delete_forms(grupos_df):
    """Renderiza formularios de edición y eliminación de grupos"""
    roles_df = get_roles_dataframe(exclude_admin=True, exclude_sin_rol=True)

    with st.expander("Editar Grupo"):
        if not grupos_df.empty:
            grupo_ids = grupos_df['id_grupo'].tolist()
            grupo_nombres = grupos_df['nombre'].tolist()
            grupo_options = [f"{gid} - {gnombre}" for gid, gnombre in zip(grupo_ids, grupo_nombres)]

            selected_grupo_edit = st.selectbox("Seleccionar Grupo para Editar", options=grupo_options, key="select_grupo_edit")
            if selected_grupo_edit:
                grupo_id = int(selected_grupo_edit.split(' - ')[0])
                grupo_row = grupos_df[grupos_df['id_grupo'] == grupo_id].iloc[0]

                edit_grupo_nombre = st.text_input("Nombre del Grupo", value=grupo_row['nombre'], key="edit_grupo_nombre")
                edit_grupo_desc = st.text_area("Descripción", value=grupo_row['descripcion'] if pd.notna(grupo_row['descripcion']) else "", key="edit_grupo_desc", max_chars=250)

                current_roles = get_roles_by_grupo(grupo_id)
                current_role_ids = [r[0] for r in current_roles]
                
                # Filtrar current_role_ids para que solo incluya roles disponibles en las opciones
                available_role_ids = roles_df['id_rol'].tolist()
                filtered_current_role_ids = [role_id for role_id in current_role_ids if role_id in available_role_ids]

                edit_selected_roles = st.multiselect(
                    "Departamentos asignados a este grupo",
                    options=available_role_ids,
                    default=filtered_current_role_ids,
                    format_func=lambda x: roles_df.loc[roles_df['id_rol'] == x, 'nombre'].iloc[0],
                    key="edit_grupo_roles",
                )

                if st.button("Guardar Cambios de Grupo", key="save_grupo_edit"):
                    if edit_grupo_nombre:
                        conn = get_connection()
                        c = conn.cursor()
                        try:
                            c.execute("SELECT id_grupo, nombre FROM grupos WHERE id_grupo != %s", (grupo_id,))
                            existing_grupos = c.fetchall()
                            nombre_normalizado = normalize_text(edit_grupo_nombre)

                            duplicado = any(normalize_text(existing_nombre) == nombre_normalizado for existing_id, existing_nombre in existing_grupos)

                            if not duplicado:
                                c.execute(
                                    "UPDATE grupos SET nombre = %s, descripcion = %s WHERE id_grupo = %s",
                                    (edit_grupo_nombre, edit_grupo_desc, grupo_id),
                                )
                                conn.commit()
                                update_grupo_roles(grupo_id, edit_selected_roles)
                                st.success("Grupo actualizado exitosamente.")
                                from .utils import safe_rerun
                                safe_rerun()
                            else:
                                st.error("Ya existe otro grupo con ese nombre.")
                        except Exception as e:
                            st.error(f"Error al actualizar grupo: {str(e)}")
                        finally:
                            conn.close()
                    else:
                        st.error("El nombre del grupo es obligatorio.")
        else:
            st.info("No hay grupos para editar.")

    with st.expander("Eliminar Grupo"):
        if not grupos_df.empty:
            grupo_ids = grupos_df['id_grupo'].tolist()
            grupo_nombres = grupos_df['nombre'].tolist()
            grupo_options = [f"{gid} - {gnombre}" for gid, gnombre in zip(grupo_ids, grupo_nombres)]

            selected_grupo_delete = st.selectbox("Seleccionar Grupo para Eliminar", options=grupo_options, key="select_grupo_delete")
            if selected_grupo_delete:
                grupo_id = int(selected_grupo_delete.split(' - ')[0])
                grupo_row = grupos_df[grupos_df['id_grupo'] == grupo_id].iloc[0]

                st.warning(f"Vas a eliminar el grupo: {grupo_row['nombre']}")
                if st.button("Eliminar Grupo", key="delete_grupo_btn"):
                    try:
                        conn = get_connection()
                        c = conn.cursor()
                        c.execute("DELETE FROM grupos WHERE id_grupo = %s", (grupo_id,))
                        conn.commit()
                        st.success("Grupo eliminado exitosamente.")
                        from .utils import safe_rerun
                        safe_rerun()
                    except Exception as e:
                        st.error(f"Error al eliminar grupo: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay grupos para eliminar.")
