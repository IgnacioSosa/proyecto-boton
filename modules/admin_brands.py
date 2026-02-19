import streamlit as st
import pandas as pd
from .utils import show_ordered_dataframe, normalize_cuit, normalize_web

from .database import get_marcas_dataframe, add_marca, update_marca, delete_marca


def render_brand_management():
    st.subheader("Gestión de Marcas")

    with st.expander("Agregar Marca"):
        if "brand_add_success" in st.session_state:
            st.success(st.session_state.brand_add_success)
            del st.session_state.brand_add_success

        def add_brand_callback():
            nombre = st.session_state.get("new_brand_name", "").strip()
            cuit = normalize_cuit(st.session_state.get("new_brand_cuit", "").strip())
            email = st.session_state.get("new_brand_email", "").strip()
            telefono = st.session_state.get("new_brand_tel", "").strip()
            celular = st.session_state.get("new_brand_cel", "").strip()
            web = normalize_web(st.session_state.get("new_brand_web", "").strip())
            if nombre:
                new_id = add_marca(nombre, cuit=cuit, email=email, telefono=telefono, celular=celular, web=web)
                if new_id:
                    st.session_state.brand_add_success = "Marca agregada correctamente"
                    st.session_state["new_brand_name"] = ""
                    st.session_state["new_brand_cuit"] = ""
                    st.session_state["new_brand_email"] = ""
                    st.session_state["new_brand_tel"] = ""
                    st.session_state["new_brand_cel"] = ""
                    st.session_state["new_brand_web"] = ""
                else:
                    st.session_state.brand_add_error = "No se pudo agregar la marca"
            else:
                st.session_state.brand_add_error = "Ingrese un nombre válido"

        if "brand_add_error" in st.session_state:
            st.error(st.session_state.brand_add_error)
            del st.session_state.brand_add_error

        st.text_input("CUIT", key="new_brand_cuit")
        st.text_input("Nombre de Marca", key="new_brand_name")
        st.text_input("Email", key="new_brand_email")
        st.text_input("Teléfono", key="new_brand_tel")
        st.text_input("Celular", key="new_brand_cel")
        st.text_input("Web (URL)", key="new_brand_web")
        st.button("Agregar Marca", key="add_brand_btn", on_click=add_brand_callback)

    marcas_df = get_marcas_dataframe()
    if not marcas_df.empty:
        show_ordered_dataframe(marcas_df, ["cuit", "nombre", "email", "telefono", "celular", "web"], ["id_marca", "activa"])
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
                
                nuevo_nombre = st.text_input("Nombre", value=brand_row['nombre'], key="edit_brand_name")
                nuevo_cuit = st.text_input("CUIT", value=str(brand_row.get('cuit') or ''), key="edit_brand_cuit")
                nuevo_email = st.text_input("Email", value=str(brand_row.get('email') or ''), key="edit_brand_email")
                nuevo_tel = st.text_input("Teléfono", value=str(brand_row.get('telefono') or ''), key="edit_brand_tel")
                nuevo_cel = st.text_input("Celular", value=str(brand_row.get('celular') or ''), key="edit_brand_cel")
                nuevo_web = st.text_input("Web (URL)", value=str(brand_row.get('web') or ''), key="edit_brand_web")
                nueva_activa = st.checkbox("Habilitada", value=is_active, key="edit_brand_active")
                if st.button("Guardar cambios", key="save_brand_edit", type="primary"):
                    ok = update_marca(
                        brand_id,
                        nuevo_nombre,
                        nueva_activa,
                        cuit=normalize_cuit(nuevo_cuit),
                        email=nuevo_email,
                        telefono=nuevo_tel,
                        celular=nuevo_cel,
                        web=normalize_web(nuevo_web)
                    )
                    if ok:
                        st.success("Actualizado")
                        from .utils import safe_rerun
                        safe_rerun()
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
                            from .utils import safe_rerun
                            safe_rerun()
                        else:
                            st.error("No se pudo eliminar")
        else:
            st.info("No hay marcas para eliminar.")
