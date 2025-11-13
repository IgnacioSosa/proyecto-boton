import streamlit as st
import pandas as pd

from .database import get_marcas_dataframe, add_marca, update_marca, delete_marca


def render_brand_management():
    st.subheader("Gestión de Marcas")

    with st.expander("Agregar Marca"):
        nombre = st.text_input("Nombre de Marca", key="new_brand_name")
        if st.button("Agregar Marca", key="add_brand_btn"):
            if nombre and nombre.strip():
                new_id = add_marca(nombre.strip())
                if new_id:
                    st.success("Marca agregada correctamente")
                else:
                    st.error("No se pudo agregar la marca")
            else:
                st.error("Ingrese un nombre válido")

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
                col_a, col_b = st.columns([4, 1])
                with col_a:
                    nuevo_nombre = st.text_input("Nombre", value=brand_row['nombre'], key="edit_brand_name")
                with col_b:
                    if st.button("Guardar", key="save_brand_edit"):
                        ok = update_marca(brand_id, nuevo_nombre)
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