import streamlit as st
import re
from modules import database as db
from modules.auth import make_signed_session_params
from modules.utils import validate_phone_number
import math
import pandas as pd
import html
from modules.ui_components import inject_project_card_css

def render_shared_contacts_management(username, is_admin=False, key_prefix="shared_contacts"):
    inject_project_card_css()
    st.title("Contactos")

    # --- Pre-fetch Data for Names (Needed for List & Detail View) ---
    clientes_df_all = db.get_clientes_dataframe()
    marcas_df_all = db.get_marcas_dataframe()
    
    # Create maps for quick lookup: ID -> Name
    clientes_map = dict(zip(clientes_df_all['id_cliente'], clientes_df_all['nombre']))
    marcas_map = dict(zip(marcas_df_all['id_marca'], marcas_df_all['nombre']))

    def get_entity_name(ctype, cid):
        if not ctype or not cid: return None
        try:
            cid = int(cid)
        except:
            return None
            
        if ctype.lower() == 'cliente':
            return clientes_map.get(cid)
        elif ctype.lower() == 'marca':
            return marcas_map.get(cid)
        return None
    
    # --- Funciones Helper (Callbacks) ---
    # open_create_modal removed as we handle it directly
        
    def select_contact(contact_dict):
        # Convert all values to native Python types to ensure serialization
        safe_dict = {}
        for k, v in contact_dict.items():
            if pd.isna(v):
                safe_dict[k] = None
            else:
                safe_dict[k] = v
        st.session_state[f"{key_prefix}_selected_contact"] = safe_dict
        
        # Update URL param to prevent override by auto-selection logic
        if safe_dict.get('id_contacto'):
            st.query_params["contactid"] = str(safe_dict['id_contacto'])
        
        # Sincronizar filtros con la selección
        etype = (safe_dict.get('etiqueta_tipo') or '').lower()
        eid = safe_dict.get('etiqueta_id')
        
        if etype == 'cliente' and eid:
            cname = clientes_map.get(int(eid))
            if cname:
                st.session_state[f"{key_prefix}_filter_type"] = "cliente"
                st.session_state[f"{key_prefix}_filter_value"] = cname
        elif etype == 'marca' and eid:
            mname = marcas_map.get(int(eid))
            if mname:
                st.session_state[f"{key_prefix}_filter_type"] = "marca"
                st.session_state[f"{key_prefix}_filter_value"] = mname
        
        # Ensure create modal flag is off (though we consume it, this is safety)
        st.session_state[f"{key_prefix}_show_create_modal"] = False
        
        # Log recent access
        uid = st.session_state.get('user_id')
        if uid and safe_dict.get('id_contacto'):
            try:
                db.log_contacto_reciente(uid, int(safe_dict['id_contacto']))
            except Exception:
                pass
        
    def clear_selection():
        st.session_state[f"{key_prefix}_selected_contact"] = None
        # Limpiar también el query param para evitar re-selección automática al recargar
        if "contactid" in st.query_params:
            try:
                st.query_params.pop("contactid")
            except:
                pass

    def delete_selected_contact(contact_id):
        if db.delete_contacto(contact_id):
             st.session_state[f"{key_prefix}_selected_contact"] = None
             st.success("Contacto eliminado")
        else:
             st.error("Error al eliminar")

    # --- Inicialización de Estado ---
    if f"{key_prefix}_show_create_modal" not in st.session_state:
        st.session_state[f"{key_prefix}_show_create_modal"] = False
    if f"{key_prefix}_selected_contact" not in st.session_state:
        st.session_state[f"{key_prefix}_selected_contact"] = None
    if f"{key_prefix}_page" not in st.session_state:
        st.session_state[f"{key_prefix}_page"] = 1

    # --- Generar Params de Sesión para Persistencia en GET Form ---
    session_inputs = ""
    user_id = st.session_state.get('user_id')
    if user_id:
        try:
            # Ensure user_id is int
            s_params = make_signed_session_params(int(user_id))
            for k, v in s_params.items():
                session_inputs += f'<input type="hidden" name="{k}" value="{v}" />'
        except Exception as e:
            print(f"Error generating session params: {e}")
            pass

    # --- Manejo de Query Params (Selección vía URL) ---
    # Esto permite que la selección persista o se active vía recarga (form submission)
    qp = st.query_params
    qp_cid = qp.get("contactid")
    if qp_cid:
        # Intentar seleccionar el contacto si no está seleccionado o es diferente
        # (O simplemente forzar la selección)
        try:
            cid_int = int(qp_cid)
            # Solo buscar si no es el actual para ahorrar queries, o siempre para asegurar consistencia
            current_sel = st.session_state.get(f"{key_prefix}_selected_contact")
            if not current_sel or int(current_sel['id_contacto']) != cid_int:
                c_obj = db.get_contacto(cid_int)
                if c_obj:
                    select_contact(c_obj)
        except Exception:
            pass

    # --- Favoritos y Recientes ---
    current_uid = st.session_state.get('user_id')
    if current_uid:
        # Favoritos
        fav_ids = db.get_contactos_favoritos(current_uid)
        rec_ids = db.get_contactos_recientes(current_uid)
        
        if fav_ids or rec_ids:
            with st.expander("⭐ Favoritos y Recientes", expanded=False):
                col_fav, col_rec = st.columns(2)
                
                with col_fav:
                    st.markdown("**Favoritos**")
                    if fav_ids:
                        for fid in fav_ids:
                            c = db.get_contacto(fid)
                            if c:
                                # Resolve details
                                ent_name = get_entity_name(c.get('etiqueta_tipo'), c.get('etiqueta_id')) or ""
                                full_label = f"**{c['nombre']} {c.get('apellido') or ''}**"
                                sub_label = f"{c.get('puesto') or 'Sin puesto'} · {ent_name}"
                                
                                # Use columns for layout: [Info] [Button]
                                c1, c2 = st.columns([0.85, 0.15])
                                with c1:
                                    st.markdown(f"{full_label}<br><span style='color:#888; font-size:0.8em'>{sub_label}</span>", unsafe_allow_html=True)
                                with c2:
                                    if st.button("👁️", key=f"{key_prefix}_fav_{fid}", help="Ver detalle"):
                                        select_contact(c)
                                        st.rerun()
                                st.markdown("---")
                    else:
                        st.caption("No tienes favoritos aún.")

                with col_rec:
                    st.markdown("**Recientes**")
                    if rec_ids:
                        for rid in rec_ids:
                            c = db.get_contacto(rid)
                            if c:
                                # Resolve details
                                ent_name = get_entity_name(c.get('etiqueta_tipo'), c.get('etiqueta_id')) or ""
                                full_label = f"**{c['nombre']} {c.get('apellido') or ''}**"
                                sub_label = f"{c.get('puesto') or 'Sin puesto'} · {ent_name}"
                                
                                # Use columns for layout
                                c1, c2 = st.columns([0.85, 0.15])
                                with c1:
                                    st.markdown(f"{full_label}<br><span style='color:#888; font-size:0.8em'>{sub_label}</span>", unsafe_allow_html=True)
                                with c2:
                                    if st.button("👁️", key=f"{key_prefix}_rec_{rid}", help="Ver detalle"):
                                        select_contact(c)
                                        st.rerun()
                                st.markdown("---")
                    else:
                        st.caption("No hay historial reciente.")
            st.write("") # Spacer

    # --- Modal de creación ---
    @st.dialog("Crear Nuevo Contacto")
    def create_contact_dialog():
        with st.form(key=f"{key_prefix}_create_contact_form"):
            nombre = st.text_input("Nombre *")
            apellido = st.text_input("Apellido *")
            puesto = st.text_input("Puesto *")
            email = st.text_input("Email *")
            telefono = st.text_input("Teléfono *")
            # direccion = st.text_input("Dirección") # Eliminado
            
            # Logic for pre-filling client from "Create Project" redirection
            prefill_cid = st.query_params.get("prefill_client_id")
            
            # Fetch Data for Unified Selector
            clientes_df = db.get_clientes_dataframe(only_active=True)
            marcas_df = db.get_marcas_dataframe(only_active=True)
            
            entity_options = []
            default_idx = 0
            
            # Process Clients
            for _, row in clientes_df.iterrows():
                # tuple: (type, id, name)
                opt = ('cliente', int(row['id_cliente']), row['nombre'])
                entity_options.append(opt)
                
                if prefill_cid:
                    try:
                        if int(row['id_cliente']) == int(prefill_cid):
                            default_idx = len(entity_options) - 1
                    except:
                        pass

            # Process Brands
            for _, row in marcas_df.iterrows():
                opt = ('marca', int(row['id_marca']), row['nombre'])
                entity_options.append(opt)
            
            entidad_sel = st.selectbox(
                "Cliente *", 
                entity_options, 
                index=default_idx,
                format_func=lambda x: x[2]
            )
            
            etiqueta = None
            etiqueta_id = None
            
            if entidad_sel:
                etiqueta = entidad_sel[0]
                etiqueta_id = entidad_sel[1]
            
            submitted = st.form_submit_button("Guardar")
            
            if submitted:
                errors = []
                
                # Validaciones
                if not nombre:
                    errors.append("El Nombre es obligatorio.")
                elif any(char.isdigit() for char in nombre):
                    errors.append("El Nombre no puede contener números.")
                    
                if not apellido:
                    errors.append("El Apellido es obligatorio.")
                elif any(char.isdigit() for char in apellido):
                    errors.append("El Apellido no puede contener números.")
                    
                if not puesto:
                    errors.append("El Puesto es obligatorio.")
                    
                if not email:
                    errors.append("El Email es obligatorio.")
                elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    errors.append("El formato del Email no es válido.")
                    
                if not telefono:
                    errors.append("El Teléfono es obligatorio.")
                else:
                    is_valid_phone, phone_msg_or_val = validate_phone_number(telefono)
                    if not is_valid_phone:
                        errors.append(f"Teléfono: {phone_msg_or_val}")
                    else:
                        telefono_save = phone_msg_or_val

                if not etiqueta_id:
                    errors.append("El Cliente es obligatorio.")

                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    # Usar el teléfono validado y formateado
                    # telefono_save ya tiene el valor correcto
                    
                    new_id = db.add_contacto(nombre, apellido, puesto, telefono_save, email, "", etiqueta.lower(), etiqueta_id)
                    st.session_state[f"{key_prefix}_show_create_modal"] = False
                    
                    # Return to Create Project if prefilled or explicitly requested
                    return_to = st.query_params.get("return_to")
                    if st.query_params.get("prefill_client_id") or return_to == "create_project":
                        # Restore form data
                        if "temp_form_data" in st.session_state:
                            for k, v in st.session_state["temp_form_data"].items():
                                st.session_state[k] = v
                            del st.session_state["temp_form_data"]
                        
                        # Set the new contact as selected
                        if new_id:
                            st.session_state["create_contacto_id"] = new_id
                        
                        # Redirect back
                        if is_admin:
                            st.session_state["force_adm_tab"] = "🆕 Nuevo Trato"
                            st.query_params["adm_tab"] = "nuevo_trato"
                        else:
                            st.session_state["force_proj_tab"] = "🆕 Nuevo Trato"
                            st.query_params["ptab"] = "nuevo_trato"
                            
                        # Clean params
                        if "prefill_client_id" in st.query_params:
                            st.query_params.pop("prefill_client_id")
                        if "return_to" in st.query_params:
                            st.query_params.pop("return_to")
                            
                        st.rerun()
                    else:
                        st.rerun()

    # --- Botón Nuevo Contacto ---
    if st.button("Nuevo contacto", key=f"{key_prefix}_new_contact"):
        create_contact_dialog()

    # --- External Trigger Check ---
    if st.session_state.get(f"{key_prefix}_show_create_modal", False):
        create_contact_dialog()
        # Reset flag to prevent zombie modal
        st.session_state[f"{key_prefix}_show_create_modal"] = False

    # --- Filtros ---
    col1, col2 = st.columns([1, 3])
    with col1:
        filter_type = st.selectbox(
            "Ver por",
            ["cliente", "marca"],
            key=f"{key_prefix}_filter_type",
            on_change=clear_selection
        )
    
    contacts_df = pd.DataFrame()
    
    with col2:
        if filter_type == "cliente":
            clientes_df = db.get_clientes_dataframe(only_active=True)
            options = clientes_df['nombre'].tolist()
            if not options:
                st.warning("No hay clientes registrados.")
                filter_value = None
            else:
                filter_value = st.selectbox("Cliente", options, key=f"{key_prefix}_filter_value", on_change=clear_selection)
            
            if filter_value:
                # Get ID
                c_row = clientes_df[clientes_df['nombre'] == filter_value].iloc[0]
                contacts_df = db.get_contactos_por_cliente(c_row['id_cliente'])
        else:
            marcas_df = db.get_marcas_dataframe()
            options = marcas_df['nombre'].tolist()
            if not options:
                st.warning("No hay marcas registradas.")
                filter_value = None
            else:
                filter_value = st.selectbox("Marca", options, key=f"{key_prefix}_filter_value", on_change=clear_selection)
            
            if filter_value:
                m_row = marcas_df[marcas_df['nombre'] == filter_value].iloc[0]
                contacts_df = db.get_contactos_por_marca(m_row['id_marca'])

    # --- Paginación ---
    if not contacts_df.empty:
        items_per_page = 10
        total_items = len(contacts_df)
        total_pages = math.ceil(total_items / items_per_page)
        
        if st.session_state[f"{key_prefix}_page"] > total_pages:
            st.session_state[f"{key_prefix}_page"] = max(1, total_pages)
        
        current_page = st.session_state[f"{key_prefix}_page"]
        
        start_idx = (current_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        contacts_to_show = contacts_df.iloc[start_idx:end_idx]

        # --- Renderizado de Lista ---
        for idx, contact_row in contacts_to_show.iterrows():
            contact = contact_row.to_dict()
            
            # Check selection status
            is_selected = False
            sel_c = st.session_state.get(f"{key_prefix}_selected_contact")
            if sel_c and str(sel_c.get('id_contacto')) == str(contact['id_contacto']):
                is_selected = True
            
            selected_class = " selected" if is_selected else ""
            
            full_name = f"{contact['nombre']} {contact.get('apellido') or ''}".strip()
            puesto = contact.get('puesto') or "Sin puesto"
            email = contact.get('email') or ""
            telefono = contact.get('telefono') or ""
            
            e_name = get_entity_name(contact.get('etiqueta_tipo'), contact.get('etiqueta_id')) or "Desconocido"
            
            # Escape HTML
            full_name_esc = html.escape(full_name)
            puesto_esc = html.escape(puesto)
            email_esc = html.escape(email)
            tel_esc = html.escape(telefono)
            e_name_esc = html.escape(e_name)
            
            # Entity string logic
            entidad_str = f"{filter_type.capitalize()}: {e_name_esc}"

            etq_type = (contact.get('etiqueta_tipo') or filter_type or "").lower()
            if etq_type == "marca":
                contact_type_class = "contact-marca"
            else:
                contact_type_class = "contact-cliente"
            
            hidden_val = contact['id_contacto']
            
            # Preserve ptab if exists
            ptab_val = st.query_params.get("ptab")
            ptab_input = f'<input type="hidden" name="ptab" value="{html.escape(ptab_val)}" />' if ptab_val else ''

            # Preserve adm_tab if exists (for admin dashboard)
            adm_tab_val = st.query_params.get("adm_tab")
            adm_tab_input = f'<input type="hidden" name="adm_tab" value="{html.escape(adm_tab_val)}" />' if adm_tab_val else ''

            st.markdown(
                f"""
                <form method="get" class="card-form" action="">
                  {session_inputs}
                  <input type="hidden" name="contactid" value="{hidden_val}" />
                  {ptab_input}
                  {adm_tab_input}
                  <div class="project-card{selected_class}">
                    <div class="project-info">
                      <div class="project-title">
                        <span class="dot-left {contact_type_class}"></span>
                        <span>{full_name_esc}</span>
                      </div>
                      <div class="project-sub">{puesto_esc} {f'· {email_esc}' if email else ''}</div>
                      <div class="project-sub2">{tel_esc} {f'· {entidad_str}' if e_name else ''}</div>
                    </div>
                    <span class="status-pill {contact_type_class}">Contacto</span>
                  </div>
                  <button type="submit" class="card-submit"></button>
                </form>
                """,
                unsafe_allow_html=True
            )

        count_text = f"Mostrando elementos {start_idx + 1}-{min(end_idx, total_items)} de {total_items}"

        def prev_page():
            st.session_state[f"{key_prefix}_page"] = max(1, current_page - 1)

        def next_page():
            st.session_state[f"{key_prefix}_page"] = min(total_pages, current_page + 1)

        col_text, col_spacer, col_prev, col_sep, col_next = st.columns([3, 3, 1, 0.5, 1])

        with col_text:
            st.markdown(
                f"<div style='display:flex; align-items:center; height:100%; color:#888;'>{count_text}</div>",
                unsafe_allow_html=True,
            )
        with col_prev:
            st.button(
                "Anterior",
                key=f"{key_prefix}_prev",
                disabled=current_page == 1,
                on_click=prev_page,
                use_container_width=True,
            )
        with col_next:
            st.button(
                "Siguiente",
                key=f"{key_prefix}_next",
                disabled=current_page == total_pages,
                on_click=next_page,
                use_container_width=True,
            )

        # --- Vista de Detalle (Abajo) ---
        selected_contact = st.session_state.get(f"{key_prefix}_selected_contact")
        
        if selected_contact:
            st.write("")
            st.write("")
            
            with st.container(border=True):
                # Cabecera
                # Use [3, 1] ratio to give space for buttons
                head_col1, head_col2 = st.columns([3, 1])
                with head_col1:
                    full_name_sel = f"{selected_contact['nombre']} {selected_contact.get('apellido') or ''}".strip()
                    
                    # Favorite Logic
                    uid = st.session_state.get('user_id')
                    is_fav = False
                    if uid:
                         favs = db.get_contactos_favoritos(uid)
                         is_fav = selected_contact['id_contacto'] in favs
                    
                    c_name, c_fav = st.columns([0.8, 0.2])
                    with c_name:
                         st.subheader(full_name_sel)
                    with c_fav:
                         if uid:
                             fav_icon = "⭐" if is_fav else "☆"
                             if st.button(fav_icon, key=f"{key_prefix}_toggle_fav_btn", help="Alternar Favorito"):
                                 db.toggle_contacto_favorito(uid, selected_contact['id_contacto'])
                                 st.rerun()
                
                with head_col2:
                    # Nested columns for buttons side-by-side
                    b_edit, b_del = st.columns(2)
                    
                    # --- Lógica de Edición y Eliminación ---
                    @st.dialog("Editar Contacto")
                    def edit_contact_dialog(contact):
                        with st.form(key=f"{key_prefix}_edit_contact_form_{contact['id_contacto']}"):
                            nombre = st.text_input("Nombre *", value=contact.get('nombre', ''))
                            apellido = st.text_input("Apellido *", value=contact.get('apellido', ''))
                            puesto = st.text_input("Puesto *", value=contact.get('puesto', ''))
                            email = st.text_input("Email *", value=contact.get('email', ''))
                            telefono = st.text_input("Teléfono *", value=contact.get('telefono', ''))
                            # direccion = st.text_input("Dirección", value=contact.get('direccion', '')) # Eliminado
                            
                            # Unified Entity Logic
                            clientes_df = db.get_clientes_dataframe(only_active=True)
                            marcas_df = db.get_marcas_dataframe()
                            
                            entity_options = []
                            default_idx = 0
                            
                            current_type = (contact.get('etiqueta_tipo') or '').lower()
                            current_id = contact.get('etiqueta_id')
                            
                            # Clients
                            for _, row in clientes_df.iterrows():
                                opt = ('cliente', int(row['id_cliente']), row['nombre'])
                                entity_options.append(opt)
                                
                                if current_type == 'cliente' and current_id and int(current_id) == int(row['id_cliente']):
                                    default_idx = len(entity_options) - 1
                                    
                            # Brands
                            for _, row in marcas_df.iterrows():
                                opt = ('marca', int(row['id_marca']), row['nombre'])
                                entity_options.append(opt)
                                
                                if current_type == 'marca' and current_id and int(current_id) == int(row['id_marca']):
                                    default_idx = len(entity_options) - 1
                            
                            entidad_sel = st.selectbox(
                                "Cliente *", 
                                entity_options, 
                                index=default_idx,
                                format_func=lambda x: x[2]
                            )
                            
                            etiqueta = None
                            etiqueta_id = None
                            
                            if entidad_sel:
                                etiqueta = entidad_sel[0]
                                etiqueta_id = entidad_sel[1]
                            
                            submitted = st.form_submit_button("Guardar Cambios")
                            
                            if submitted:
                                errors = []
                                
                                # Validaciones
                                if not nombre:
                                    errors.append("El Nombre es obligatorio.")
                                elif any(char.isdigit() for char in nombre):
                                    errors.append("El Nombre no puede contener números.")
                                    
                                if not apellido:
                                    errors.append("El Apellido es obligatorio.")
                                elif any(char.isdigit() for char in apellido):
                                    errors.append("El Apellido no puede contener números.")
                                    
                                if not puesto:
                                    errors.append("El Puesto es obligatorio.")
                                    
                                if not email:
                                    errors.append("El Email es obligatorio.")
                                elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                                    errors.append("El formato del Email no es válido.")
                                    
                                if not telefono:
                                    errors.append("El Teléfono es obligatorio.")
                                else:
                                    is_valid_phone, phone_msg_or_val = validate_phone_number(telefono)
                                    if not is_valid_phone:
                                        errors.append(f"Teléfono: {phone_msg_or_val}")
                                    else:
                                        telefono_save = phone_msg_or_val
                                
                                if not etiqueta_id:
                                    errors.append("La Entidad (Cliente/Marca) es obligatoria.")

                                if errors:
                                    for e in errors:
                                        st.error(e)
                                else:
                                    # telefono_save ya fue asignado en la validación

                                    
                                    if db.update_contacto(
                                        contact['id_contacto'], 
                                        nombre=nombre, 
                                        apellido=apellido, 
                                        puesto=puesto, 
                                        telefono=telefono_save, 
                                        email=email, 
                                        direccion="", 
                                        etiqueta_tipo=etiqueta.lower(), 
                                        etiqueta_id=etiqueta_id
                                    ):
                                        st.success("Contacto actualizado")
                                        # Update session state with new values to reflect changes immediately
                                        updated_contact = contact.copy()
                                        updated_contact.update({
                                            'nombre': nombre, 'apellido': apellido, 'puesto': puesto,
                                            'telefono': telefono_save, 'email': email, 'direccion': "",
                                            'etiqueta_tipo': etiqueta.lower(), 'etiqueta_id': etiqueta_id
                                        })
                                        # Recalculate safe dict just in case
                                        select_contact(updated_contact) 
                                        st.rerun()
                                    else:
                                        st.error("Error actualizando contacto")

                    @st.dialog("Confirmar Eliminación")
                    def delete_contact_dialog(contact):
                        st.write(f"¿Está seguro que desea eliminar al contacto **{contact['nombre']} {contact.get('apellido') or ''}**?")
                        st.warning("Esta acción no se puede deshacer.")
                        col_d1, col_d2 = st.columns(2)
                        with col_d1:
                            if st.button("Sí, Eliminar", type="primary", key=f"{key_prefix}_confirm_del"):
                                delete_selected_contact(contact['id_contacto'])
                                st.rerun()
                        with col_d2:
                            if st.button("Cancelar", key=f"{key_prefix}_cancel_del"):
                                st.rerun()

                    with b_edit:
                        if st.button("✏️ Editar", key=f"{key_prefix}_btn_edit_detail", use_container_width=True):
                             edit_contact_dialog(selected_contact)
                    with b_del:
                        if st.button("🗑️ Eliminar", 
                                 key=f"{key_prefix}_btn_delete_detail", 
                                 type="primary",
                                 use_container_width=True):
                             delete_contact_dialog(selected_contact)

                st.markdown("---")
                
                # Grid de información
                def render_detail_box(label, value):
                    val_str = str(value) if value is not None and str(value).strip() != "" else "-"
                    st.markdown(f"""
                    <div class="contact-detail-box">
                        <div class="contact-detail-label">{label}</div>
                        <div class="contact-detail-value">{val_str}</div>
                    </div>
                    """, unsafe_allow_html=True)

                g1, g2 = st.columns(2)
                
                with g1:
                    render_detail_box("Puesto", selected_contact.get('puesto'))
                    render_detail_box("Mail", selected_contact.get('email'))
                    render_detail_box("Etiqueta", selected_contact.get('etiqueta_tipo').capitalize() if selected_contact.get('etiqueta_tipo') else "-")
                
                with g2:
                    render_detail_box("Teléfono", selected_contact.get('telefono'))
                    # render_detail_box("Dirección", selected_contact.get('direccion')) # Eliminado
                    
                    # Resolve Entity Name
                    ent_name = get_entity_name(selected_contact.get('etiqueta_tipo'), selected_contact.get('etiqueta_id'))
                    ent_label = selected_contact.get('etiqueta_tipo', 'Entidad').capitalize() if selected_contact.get('etiqueta_tipo') else "Entidad"
                    render_detail_box(ent_label, ent_name)
