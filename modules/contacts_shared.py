import streamlit as st
import re
from modules import database as db
from modules.utils import validate_phone_number, safe_rerun
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
        # if safe_dict.get('id_contacto'):
        #    st.query_params["contactid"] = str(safe_dict['id_contacto'])
        
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
    # DEPRECATED: Session handled by st.session_state
    session_inputs = ""

    # --- Manejo de Query Params (Selección vía URL) ---
    # Esto permite que la selección persista o se active vía recarga (form submission)
    qp = st.query_params
    qp_cid = qp.get("contactid")
    
    if qp_cid:
        # Consumir el parámetro: leerlo una vez y limpiar la URL
        try:
            cid_int = int(qp_cid)
            # Forzar actualización si es distinto
            current_sel = st.session_state.get(f"{key_prefix}_selected_contact")
            if not current_sel or int(current_sel['id_contacto']) != cid_int:
                c_obj = db.get_contacto(cid_int)
                if c_obj:
                    select_contact(c_obj)
            
            if "contactid" in qp:
                st.query_params.pop("contactid")
            
            # Marcar para mantener abierto en esta carga inicial
            st.session_state[f"{key_prefix}_keep_dialog_open"] = True
                
        except Exception:
            pass

    # --- Lógica de Persistencia del Diálogo ---
    # Si no hay señal de mantener abierto (interacción o carga inicial) y no hay URL param, cerramos.
    # Esto soluciona el problema de que el diálogo se reabra al cambiar de pestaña o cerrar con X.
    keep_open_key = f"{key_prefix}_keep_dialog_open"
    should_keep_open = st.session_state.get(keep_open_key, False)
    
    # Resetear flag para la próxima (salvo que una interacción lo vuelva a activar)
    st.session_state[keep_open_key] = False
    
    if not should_keep_open and not qp_cid:
        st.session_state[f"{key_prefix}_selected_contact"] = None

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
                                        safe_rerun()
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
                                        safe_rerun()
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
            puesto = st.text_input("Puesto")
            email = st.text_input("Email *")
            telefono = st.text_input("Teléfono")
            notes = st.text_area("Notas")
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
                    puesto = "Sin dato"
                    
                if not email:
                    errors.append("El Email es obligatorio.")
                elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    errors.append("El formato del Email no es válido.")
                    
                if not telefono:
                    telefono_save = "Sin dato"
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
                    
                    from .utils import safe_rerun
                    nombre_title = " ".join(str(nombre or "").strip().split()).title()
                    apellido_title = " ".join(str(apellido or "").strip().split()).title()
                    new_id = db.add_contacto(nombre_title, apellido_title, puesto, telefono_save, email, "", etiqueta.lower(), etiqueta_id, notes=notes)
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
                            
                        safe_rerun()
                    else:
                        safe_rerun()

    # --- Botones y Acciones ---
    if is_admin:
        col_new, col_bulk = st.columns([0.2, 0.8])
        with col_new:
            if st.button("Nuevo contacto", key=f"{key_prefix}_new_contact"):
                create_contact_dialog()
        
        # El bloque de carga masiva se movió al final de la función
    else:
        # Solo botón normal para no admin
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

            # Preserve admin panel state keys (for admin_panel.py navigation)
            adm_main_val = st.query_params.get("adm_main")
            adm_sub_val = st.query_params.get("adm_sub")
            adm_cli_val = st.query_params.get("adm_cli")
            
            adm_panel_inputs = ""
            if adm_main_val:
                adm_panel_inputs += f'<input type="hidden" name="adm_main" value="{html.escape(adm_main_val)}" />'
            if adm_sub_val:
                adm_panel_inputs += f'<input type="hidden" name="adm_sub" value="{html.escape(adm_sub_val)}" />'
            if adm_cli_val:
                adm_panel_inputs += f'<input type="hidden" name="adm_cli" value="{html.escape(adm_cli_val)}" />'

            st.markdown(
                f"""
                <form method="get" class="card-form" action="">
                  {session_inputs}
                  <input type="hidden" name="contactid" value="{hidden_val}" />
                  {ptab_input}
                  {adm_tab_input}
                  {adm_panel_inputs}
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
            
            # Use native Streamlit button for selection to avoid full page reload
            # card_key = f"{key_prefix}_sel_{contact['id_contacto']}"
            
            # Create a container for the card
            # with st.container():
                # Render the card visual which triggers the button click
                # Using a clever CSS hack to overlay the button invisibly over the card
                
                # First, render the button but make it invisible and covering the area?
                # No, st.button cannot contain other elements.
                
                # We will use the approach of:
                # 1. Render the Card HTML.
                # 2. Render a button with a unique key.
                # 3. Use JS/CSS to make the card click trigger the button.
                
                # Create the button first (hidden via CSS)
                # We use a unique label content to find it easily in JS
                # btn_label = f"select_{contact['id_contacto']}"
                # if st.button(btn_label, key=card_key):
                #     select_contact(contact)
                #     st.rerun()

                # st.markdown(
                #     f"""
                #     <style>
                #     /* Hide the button with the specific label text */
                #     /* Note: This is a bit fragile if Streamlit changes DOM structure, but works for now */
                #     /* We look for buttons that contain the specific text */
                #     p:contains('{btn_label}'), div:contains('{btn_label}'), span:contains('{btn_label}') {{
                #         /* display: none; - DON'T hide the container, just the button text if possible */
                #     }}
                    
                #     /* Better: Hide the button element itself based on the text content inside it? 
                #        CSS 4 has :has(), but for now we rely on the JS below to click it. 
                #        We can hide it visually but keep it in DOM. */
                       
                #     /* Hiding the button wrapper in Streamlit */
                #     div.stButton > button {{
                #         /* We can't target specific button easily with CSS only without :has */
                #     }}
                #     </style>
                    
                #     <div class="project-card{selected_class}" style="cursor: pointer;" 
                #          onclick="
                #             // Find all buttons
                #             var buttons = window.parent.document.querySelectorAll('button');
                #             for (var i = 0; i < buttons.length; i++) {{
                #                 // Check if button text matches our unique label
                #                 if (buttons[i].innerText === '{btn_label}') {{
                #                     buttons[i].click();
                #                     break;
                #                 }}
                #             }}
                #          ">
                #         <div class="project-info">
                #           <div class="project-title">
                #             <span class="dot-left {contact_type_class}"></span>
                #             <span>{full_name_esc}</span>
                #           </div>
                #           <div class="project-sub">{puesto_esc} {f'· {email_esc}' if email else ''}</div>
                #           <div class="project-sub2">{tel_esc} {f'· {entidad_str}' if e_name else ''}</div>
                #         </div>
                #         <span class="status-pill {contact_type_class}">Contacto</span>
                #     </div>
                    
                #     <script>
                #         // Optional: Hide the button programmatically to be safe
                #         var buttons = window.parent.document.querySelectorAll('button');
                #         for (var i = 0; i < buttons.length; i++) {{
                #             if (buttons[i].innerText === '{btn_label}') {{
                #                 buttons[i].style.display = 'none';
                #             }}
                #         }}
                #     </script>
                #     """,
                #     unsafe_allow_html=True
                # )

        count_text = f"Mostrando elementos {start_idx + 1}-{min(end_idx, total_items)} de {total_items}"

        def prev_page():
            st.session_state[f"{key_prefix}_page"] = max(1, current_page - 1)
            clear_selection()

        def next_page():
            st.session_state[f"{key_prefix}_page"] = min(total_pages, current_page + 1)
            clear_selection()

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

        # --- Vista de Detalle (Modal) ---
        selected_contact = st.session_state.get(f"{key_prefix}_selected_contact")
        
        if selected_contact:
            @st.dialog(f"👤 {selected_contact['nombre']} {selected_contact.get('apellido') or ''}")
            def show_contact_dialog(contact):
                # Helper to signal that dialog should remain open
                def keep_open():
                    st.session_state[f"{key_prefix}_keep_dialog_open"] = True

                # Edit Mode Toggle
                edit_mode_key = f"{key_prefix}_edit_mode_{contact['id_contacto']}"
                if edit_mode_key not in st.session_state:
                    st.session_state[edit_mode_key] = False
                
                is_edit_mode = st.session_state[edit_mode_key]

                # Header with Fav
                c_head1, c_head2 = st.columns([0.8, 0.2])
                with c_head2:
                    uid = st.session_state.get('user_id')
                    is_fav = False
                    if uid:
                         favs = db.get_contactos_favoritos(uid)
                         is_fav = contact['id_contacto'] in favs
                    
                    fav_icon = "⭐" if is_fav else "☆"
                    if st.button(fav_icon, key=f"{key_prefix}_modal_fav", on_click=keep_open):
                        db.toggle_contacto_favorito(uid, contact['id_contacto'])
                        # Flag manually because rerun kills the flag set by callback if logic runs after?
                        # No, callback runs before rerun. But next run needs it.
                        st.session_state[f"{key_prefix}_keep_dialog_open"] = True
                        st.rerun()

                if not is_edit_mode:
                    # --- Read Only View ---
                    # Resolve Entity Name
                    ent_name = "Desconocido"
                    ctype = (contact.get('etiqueta_tipo') or '').lower()
                    cid = contact.get('etiqueta_id')
                    
                    if ctype == 'cliente' and cid:
                        c_obj = clientes_map.get(int(cid))
                        if c_obj: ent_name = c_obj
                    elif ctype == 'marca' and cid:
                        m_obj = marcas_map.get(int(cid))
                        if m_obj: ent_name = m_obj

                    st.markdown("### 📋 Información Personal")
                    
                    col_info1, col_info2 = st.columns(2)
                    
                    with col_info1:
                        st.markdown(f"**👤 Nombre:**")
                        st.markdown(f"{contact.get('nombre', '')} {contact.get('apellido', '')}")
                        
                        st.markdown(f"**📧 Email:**")
                        st.markdown(f"{contact.get('email', '')}")
                        
                        st.markdown(f"**📞 Teléfono:**")
                        st.markdown(f"{contact.get('telefono', '')}")

                    with col_info2:
                        st.markdown(f"**🏢 Cliente/Marca:**")
                        st.markdown(f"{ent_name} ({ctype.capitalize()})")
                        
                        st.markdown(f"**💼 Puesto:**")
                        st.markdown(f"{contact.get('puesto', '')}")

                    if contact.get('notes'):
                        st.markdown("---")
                        st.markdown("**📝 Notas:**")
                        st.info(contact['notes'])
                    
                    st.markdown("---")
                    
                    # Buttons Row
                    c_edit, c_del = st.columns([1, 1])
                    with c_edit:
                        if st.button("✏️ Editar", key=f"{key_prefix}_btn_edit_start", on_click=keep_open):
                            st.session_state[edit_mode_key] = True
                            st.session_state[f"{key_prefix}_keep_dialog_open"] = True
                            st.rerun()
                    
                    with c_del:
                        if st.button("🗑️ Eliminar", key=f"{key_prefix}_del_init", type="secondary", on_click=keep_open):
                            st.session_state[f"confirm_del_{contact['id_contacto']}"] = True
                            st.session_state[f"{key_prefix}_keep_dialog_open"] = True
                            st.rerun()

                    # Delete Confirmation (Outside columns to span full width if needed)
                    if st.session_state.get(f"confirm_del_{contact['id_contacto']}"):
                        st.warning("¿Confirmar eliminación?")
                        cd1, cd2 = st.columns(2)
                        with cd1:
                            if st.button("Sí, Eliminar", key=f"{key_prefix}_del_yes", type="primary"):
                                delete_selected_contact(contact['id_contacto'])
                                st.rerun()
                        with cd2:
                            if st.button("Cancelar", key=f"{key_prefix}_del_no", on_click=keep_open):
                                st.session_state[f"confirm_del_{contact['id_contacto']}"] = False
                                st.session_state[f"{key_prefix}_keep_dialog_open"] = True
                                st.rerun()

                else:
                    # --- Edit Form View ---
                    with st.form(key=f"{key_prefix}_modal_form_{contact['id_contacto']}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            nombre = st.text_input("Nombre *", value=contact.get('nombre', ''))
                            email = st.text_input("Email *", value=contact.get('email', ''))
                            
                            # Entity Select
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
                            
                            entidad_sel = st.selectbox("Cliente/Marca *", entity_options, index=default_idx, format_func=lambda x: x[2])

                        with c2:
                            apellido = st.text_input("Apellido *", value=contact.get('apellido', ''))
                            telefono = st.text_input("Teléfono", value=contact.get('telefono', ''))
                            puesto = st.text_input("Puesto", value=contact.get('puesto', ''))
                        
                        notes = st.text_area("Notas", value=contact.get('notes', ''))
                        
                        etiqueta = None
                        etiqueta_id = None
                        if entidad_sel:
                            etiqueta = entidad_sel[0]
                            etiqueta_id = entidad_sel[1]
                        
                        st.write("")
                        
                        cf1, cf2 = st.columns([1, 1])
                        with cf1:
                            if st.form_submit_button("Cancelar", type="secondary", use_container_width=True, on_click=keep_open):
                                st.session_state[edit_mode_key] = False
                                st.session_state[f"{key_prefix}_keep_dialog_open"] = True
                                st.rerun()
                                
                        with cf2:
                            submitted = st.form_submit_button("Guardar Cambios", type="primary", use_container_width=True, on_click=keep_open)
                        
                        if submitted:
                            errors = []
                            if not nombre: errors.append("Nombre obligatorio")
                            if not apellido: errors.append("Apellido obligatorio")
                            if not email: errors.append("Email obligatorio")
                            if not puesto: puesto = "Sin dato"
                            
                            # Phone validation
                            telefono_save = telefono
                            if not telefono:
                                telefono_save = "Sin dato"
                            else:
                                is_valid, msg = validate_phone_number(telefono)
                                if not is_valid: errors.append(f"Teléfono: {msg}")
                                else: telefono_save = msg
                            
                            if errors:
                                for e in errors: st.error(e)
                            else:
                                nombre_title = " ".join(str(nombre).strip().split()).title()
                                apellido_title = " ".join(str(apellido).strip().split()).title()
                                
                                if db.update_contacto(
                                    contact['id_contacto'], 
                                    nombre=nombre_title, 
                                    apellido=apellido_title, 
                                    puesto=puesto, 
                                    telefono=telefono_save, 
                                    email=email, 
                                    direccion="", 
                                    etiqueta_tipo=etiqueta.lower(), 
                                    etiqueta_id=etiqueta_id, 
                                    notes=notes
                                ):
                                    st.success("Guardado!")
                                    # Update session state
                                    updated = contact.copy()
                                    updated.update({
                                        'nombre': nombre_title, 'apellido': apellido_title, 
                                        'puesto': puesto, 'telefono': telefono_save, 'email': email,
                                        'etiqueta_tipo': etiqueta.lower(), 'etiqueta_id': etiqueta_id,
                                        'notes': notes
                                    })
                                    select_contact(updated)
                                    st.session_state[edit_mode_key] = False # Exit edit mode
                                    st.session_state[f"{key_prefix}_keep_dialog_open"] = True
                                    st.rerun()
                                else:
                                    st.error("Error al guardar")

            show_contact_dialog(selected_contact)

    # --- Bloque de Carga Masiva (Al final de todo) ---
    if is_admin:
        st.markdown("---")
        
        # Determine initial expansion state based on whether a file is already uploaded
        # Use session_state to check if the uploader key has a value
        bulk_uploader_key = f"{key_prefix}_bulk_upload"
        is_expanded = st.session_state.get(bulk_uploader_key) is not None
        
        with st.expander("📂 Carga Masiva (Excel)", expanded=is_expanded):
            st.markdown("""
            **Instrucciones:**
            Suba un archivo Excel (.xlsx) con las siguientes columnas exactas:
            - `Organización` (Debe coincidir con un Cliente o Marca existente)
            - `Nombre`
            - `Apellidos`
            - `Puesto`
            - `Correo electrónico - Trabajo`
            - `Teléfono - Trabajo`
            - `Teléfono - Celular`
            - `Notas`
            """)
            
            uploaded_file = st.file_uploader("Seleccionar archivo", type=["xlsx"], key=f"{key_prefix}_bulk_upload")
            
            if uploaded_file:
                # Obtener hojas del Excel
                sheet_names = []
                try:
                    excel_file = pd.ExcelFile(uploaded_file)
                    sheet_names = excel_file.sheet_names
                except Exception as e:
                    st.error(f"Error leyendo archivo Excel: {e}")
                
                selected_sheet = None
                if sheet_names:
                    selected_sheet = st.selectbox(
                        "Seleccionar hoja", 
                        options=sheet_names,
                        key=f"{key_prefix}_bulk_sheet_select"
                    )

                if selected_sheet and st.button("Procesar Carga", key=f"{key_prefix}_process_bulk"):
                    try:
                        df = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
                        
                        # Normalizar nombres de columnas (strip y replace dashes)
                        def normalize_col(col_name):
                            s = str(col_name).strip()
                            s = s.replace('–', '-').replace('—', '-') # Normalize dashes
                            s = " ".join(s.split()) # Normalize spaces
                            return s

                        df.columns = [normalize_col(c) for c in df.columns]
                        
                        required_cols = [
                            "Organización", "Nombre", "Apellidos", "Puesto", 
                            "Correo electrónico - Trabajo", "Teléfono - Trabajo", 
                            "Teléfono - Celular", "Notas"
                        ]
                        
                        # Check columns using normalized names
                        missing = [c for c in required_cols if c not in df.columns]
                        
                        if missing:
                            st.error(f"Faltan las columnas: {', '.join(missing)}")
                            st.info(f"Columnas detectadas: {', '.join(df.columns)}")
                        else:
                            # Preparar mapas de búsqueda (Nombre -> ID)
                            # Usar solo activos para evitar asignar a entidades eliminadas
                            c_df = db.get_clientes_dataframe(only_active=True)
                            m_df = db.get_marcas_dataframe(only_active=True)
                            
                            # Mapas case-insensitive con normalización extra
                            def normalize_for_match(name):
                                if not isinstance(name, str):
                                    return ""
                                # Reemplazar acentos y caracteres especiales comunes
                                s = name.strip().lower()
                                s = s.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
                                s = s.replace('´', "'").replace('`', "'").replace('’', "'")
                                s = s.replace('.', '').replace(',', '') # Eliminar puntuación
                                s = " ".join(s.split()) # Normalizar espacios
                                return s
                            
                            client_map = {normalize_for_match(n): i for n, i in zip(c_df['nombre'], c_df['id_cliente'])}
                            brand_map = {normalize_for_match(n): i for n, i in zip(m_df['nombre'], m_df['id_marca'])}
                            
                            success_count = 0
                            errors = []
                            
                            # Mostrar spinner durante el procesamiento
                            with st.spinner("Procesando archivo, por favor espere..."):
                                for idx, row in df.iterrows():
                                    row_num = idx + 2 # Header is 1
                                    try:
                                        # Extraer valores
                                        def get_val(col):
                                            val = row.get(col)
                                            if pd.isna(val) or str(val).lower() == 'nan':
                                                return ""
                                            return str(val).strip()

                                        org = get_val("Organización")
                                        nombre = get_val("Nombre")
                                        apellido = get_val("Apellidos")
                                        puesto = get_val("Puesto")
                                        email = get_val("Correo electrónico - Trabajo")
                                        tel_work = get_val("Teléfono - Trabajo")
                                        tel_cell = get_val("Teléfono - Celular")
                                        notas = get_val("Notas")
                                        
                                        if not org and not nombre:
                                            continue # Fila vacía
                                            
                                        # Validar Organización
                                        org_norm = normalize_for_match(org)
                                        etype = None
                                        eid = None
                                        
                                        if org_norm in client_map:
                                            etype = 'cliente'
                                            eid = client_map[org_norm]
                                        elif org_norm in brand_map:
                                            etype = 'marca'
                                            eid = brand_map[org_norm]
                                        else:
                                            # Búsqueda difusa / substring
                                            # Intentamos encontrar el cliente/marca que mejor coincida
                                            best_match = None
                                            # Longitud del match para priorizar coincidencias más largas
                                            best_len = 0 
                                            
                                            # Revisar Clientes
                                            for c_name, c_id in client_map.items():
                                                # Evitar coincidencias muy cortas (ej. "SA", "EL")
                                                if len(c_name) < 3: continue
                                                
                                                # Caso 1: Nombre en DB es substring del Excel (ej. "DLS" en "DLS Argentina...")
                                                if c_name in org_norm:
                                                    if len(c_name) > best_len:
                                                        best_match = ('cliente', c_id)
                                                        best_len = len(c_name)
                                                # Caso 2: Nombre en Excel es substring del DB (ej. "Nacion Seguros" en "Nacion Seguros S.A.")
                                                elif org_norm in c_name:
                                                    # En este caso la coincidencia es todo el string del excel
                                                    if len(org_norm) > best_len:
                                                        best_match = ('cliente', c_id)
                                                        best_len = len(org_norm)
                                                        
                                            # Revisar Marcas (si no hay un match muy fuerte de cliente)
                                            for b_name, b_id in brand_map.items():
                                                if len(b_name) < 3: continue
                                                
                                                if b_name in org_norm:
                                                    if len(b_name) > best_len:
                                                        best_match = ('marca', b_id)
                                                        best_len = len(b_name)
                                                elif org_norm in b_name:
                                                    if len(org_norm) > best_len:
                                                        best_match = ('marca', b_id)
                                                        best_len = len(org_norm)
                                            
                                            if best_match:
                                                etype, eid = best_match
                                            else:
                                                # Último intento: Coincidencia de primera palabra (para casos como OSPIM con sufijos distintos)
                                                first_token = org_norm.split()[0] if org_norm else ""
                                                if len(first_token) >= 4: # Mínimo 4 letras para evitar falsos positivos
                                                    for c_name, c_id in client_map.items():
                                                        if c_name.startswith(first_token):
                                                            etype = 'cliente'
                                                            eid = c_id
                                                            break
                                                    if not etype:
                                                        for b_name, b_id in brand_map.items():
                                                            if b_name.startswith(first_token):
                                                                etype = 'marca'
                                                                eid = b_id
                                                                break
                                            
                                            if not etype:
                                                errors.append({"Fila": row_num, "Error": f"Organización '{org}' no encontrada en Clientes ni Marcas activos."})
                                                continue
                                        
                                        # Validar Campos Obligatorios
                                        missing_fields = []
                                        if not nombre: missing_fields.append("Nombre")
                                        
                                        if missing_fields:
                                            errors.append({"Fila": row_num, "Error": f"Faltan campos: {', '.join(missing_fields)}"})
                                            continue
                                            
                                        # Rellenar campos faltantes con "Sin dato" según solicitud del usuario
                                        # Excepción: Apellido debe quedar vacío si no hay dato, no "Sin dato"
                                        if not apellido: apellido = ""
                                        if not puesto: puesto = "Sin dato"
                                        if not email: email = "Sin dato"
                                        if not tel_work and not tel_cell: tel_work = "Sin dato"
                                            
                                        # Intentar insertar
                                        # Usamos title() para nombres
                                        db.add_contacto(
                                            nombre=nombre.title(),
                                            apellido=apellido.title(),
                                            puesto=puesto,
                                            telefono=tel_work,
                                            celular=tel_cell,
                                            email=email,
                                            direccion="", 
                                            etiqueta_tipo=etype,
                                            etiqueta_id=eid,
                                            notes=notas
                                        )
                                        success_count += 1
                                        
                                    except Exception as e:
                                        errors.append({"Fila": row_num, "Error": f"Error inesperado: {str(e)}"})
                            
                            if success_count > 0:
                                st.success(f"✅ Se importaron {success_count} contactos correctamente.")
                                if errors:
                                    st.warning(f"⚠️ Se encontraron errores en {len(errors)} filas.")
                                    with st.expander("Ver Detalles de Errores", expanded=False):
                                        st.dataframe(pd.DataFrame(errors), hide_index=True, use_container_width=True)
                                else:
                                    # Recargar para ver los cambios
                                    from modules.utils import safe_rerun
                                    safe_rerun() 
                                    
                            elif errors:
                                st.error(f"❌ No se importaron contactos. Se encontraron errores en {len(errors)} filas.")
                                with st.expander("Ver Detalles de Errores", expanded=True):
                                    st.dataframe(pd.DataFrame(errors), hide_index=True, use_container_width=True)
                                        
                    except Exception as e:
                        st.error(f"Error procesando el archivo: {e}")
