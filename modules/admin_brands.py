import streamlit as st
import pandas as pd

from .database import get_marcas_dataframe, add_marca, update_marca, delete_marca


def render_brand_management():
    st.subheader("Gestión de Marcas")

    with st.expander("Agregar Marca"):
        if "brand_add_success" in st.session_state:
            st.success(st.session_state.brand_add_success)
            del st.session_state.brand_add_success

        def add_brand_callback():
            nombre = st.session_state.get("new_brand_name", "").strip()
            if nombre:
                new_id = add_marca(nombre)
                if new_id:
                    st.session_state.brand_add_success = "Marca agregada correctamente"
                    st.session_state["new_brand_name"] = ""
                else:
                    st.session_state.brand_add_error = "No se pudo agregar la marca"
            else:
                st.session_state.brand_add_error = "Ingrese un nombre válido"

        if "brand_add_error" in st.session_state:
            st.error(st.session_state.brand_add_error)
            del st.session_state.brand_add_error

        st.text_input("Nombre de Marca", key="new_brand_name")
        st.button("Agregar Marca", key="add_brand_btn", on_click=add_brand_callback)

    marcas_df = get_marcas_dataframe()
    if not marcas_df.empty:
        st.dataframe(marcas_df.drop(columns=[col for col in ['id_marca'] if col in marcas_df.columns]), use_container_width=True)
    else:
        st.info("No hay marcas registradas.")

    st.subheader("Editar / Eliminar Marcas")

    with st.expander("Editar Marca"):
        if not marcas_df.empty:
            brand_options = [f"{int(r['id_marca'])} - {r['nombre']}" for _, r in marcas_df.iterrows()]
            selected_brand = st.selectbox("Seleccionar Marca", options=brand_options, key="select_brand_edit")
            if selected_brand:
                brand_id = int(selected_brand.split(' - ')[0])
                brand_row = marcas_df[marcas_df['id_marca'] == brand_id].iloc[0]
                
                # Check if 'activa' column exists (migration support)
                is_active = True
                if 'activa' in brand_row:
                    is_active = bool(brand_row['activa'])
                
                col_a, col_b = st.columns([4, 1])
                with col_a:
                    nuevo_nombre = st.text_input("Nombre", value=brand_row['nombre'], key="edit_brand_name")
                    nueva_activa = st.checkbox("Habilitada", value=is_active, key="edit_brand_active")
                with col_b:
                    st.write("") # Spacer
                    st.write("") # Spacer
                    if st.button("Guardar", key="save_brand_edit"):
                        ok = update_marca(brand_id, nuevo_nombre, nueva_activa)
                        if ok:
                            st.success("Actualizado")
                            st.rerun()
                        else:
                            st.error("No se pudo actualizar")
        else:
            st.info("No hay marcas para editar.")

    with st.expander("Eliminar Marca"):
        if not marcas_df.empty:
            brand_options = [f"{int(r['id_marca'])} - {r['nombre']}" for _, r in marcas_df.iterrows()]
            selected_brand_del = st.selectbox("Seleccionar Marca", options=brand_options, key="select_brand_delete")
            if selected_brand_del:
                brand_id = int(selected_brand_del.split(' - ')[0])
                brand_row = marcas_df[marcas_df['id_marca'] == brand_id].iloc[0]
                st.warning("¿Estás seguro de que deseas eliminar esta marca? Esta acción no se puede deshacer.")
                st.info(f"Marca a eliminar: {brand_row['nombre']}")
                colc1, colc2 = st.columns([5, 1])
                with colc2:
                    if st.button("Eliminar", key="delete_brand_btn"):
                        ok = delete_marca(brand_id)
                        if ok:
                            st.success("Eliminado")
                            st.rerun()
                        else:
                            st.error("No se pudo eliminar")
        else:
            st.info("No hay marcas para eliminar.")