import streamlit as st
from .database import get_clientes_dataframe, get_connection, ensure_clientes_schema, check_client_duplicate
from .utils import show_success_message
import re
import pandas as pd
import io

def _process_bulk_upload(file):
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
    except Exception as e:
        st.error(f"Error leyendo el archivo: {e}")
        return

    # Normalizar columnas (lowercase y strip)
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    # Mapeo flexible de columnas
    col_map = {
        'cuit': 'cuit',
        'nombre (razón social)': 'nombre',
        'nombre (razon social)': 'nombre',
        'nombre': 'nombre',
        'razón social': 'nombre',
        'razon social': 'nombre',
        'email': 'email',
        'teléfono': 'telefono',
        'telefono': 'telefono',
        'celular': 'celular',
        'web (url)': 'web',
        'web': 'web',
        'url': 'web'
    }
    
    df.rename(columns=col_map, inplace=True)
    
    # Verificar columnas mínimas requeridas?
    # El usuario pide campos específicos. Si no están, no podemos procesar bien.
    # Pero intentaremos leer lo que haya.
    
    processed_count = 0
    updated_count = 0
    
    # Cargar clientes existentes para validación
    existing_df = get_clientes_dataframe()
    cuit_lookup = {}
    name_lookup = {}
    
    if not existing_df.empty:
        for _, row in existing_df.iterrows():
            c = "".join(filter(str.isdigit, str(row.get('cuit', '') or '')))
            n = str(row.get('nombre', '') or '').strip().upper()
            if c: cuit_lookup[c] = row
            if n: name_lookup[n] = row
            
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        for _, row in df.iterrows():
            # Función auxiliar para obtener valor o "Falta dato"
            def get_val(col):
                v = row.get(col)
                if pd.isna(v) or str(v).strip() == "":
                    return "Falta dato"
                return str(v).strip()
            
            # Extraer valores
            cuit_raw = get_val('cuit')
            nombre_raw = get_val('nombre')
            email = get_val('email')
            telefono = get_val('telefono')
            celular = get_val('celular')
            web = get_val('web')
            
            # Normalizar claves para búsqueda
            cuit_clean = "".join(filter(str.isdigit, cuit_raw)) if cuit_raw != "Falta dato" else ""
            nombre_clean = nombre_raw.upper() if nombre_raw != "Falta dato" else ""
            
            if not nombre_clean and not cuit_clean:
                continue
            
            # Buscar coincidencia
            match = None
            if cuit_clean and cuit_clean in cuit_lookup:
                match = cuit_lookup[cuit_clean]
            elif nombre_clean and nombre_clean in name_lookup:
                match = name_lookup[nombre_clean]
                
            if match:
                # Lógica de actualización (Solo completar datos faltantes)
                cid = match['id_cliente']
                updates = []
                vals = []
                
                def should_update(db_key, new_val):
                    # Si el valor nuevo es "Falta dato", no actualizamos nada
                    if new_val == "Falta dato": return False
                    
                    db_val = str(match.get(db_key, '') or '').strip()
                    # Si en DB falta (vacío, None, o "Falta dato"), actualizamos
                    if db_val in ["", "None", "Falta dato"]:
                        return True
                    return False
                
                # Revisar cada campo
                if should_update('cuit', cuit_raw):
                    updates.append("cuit = %s"); vals.append(cuit_raw)
                if should_update('email', email):
                    updates.append("email = %s"); vals.append(email)
                if should_update('telefono', telefono):
                    updates.append("telefono = %s"); vals.append(telefono)
                if should_update('celular', celular):
                    updates.append("celular = %s"); vals.append(celular)
                if should_update('web', web):
                    updates.append("web = %s"); vals.append(web)
                
                # Si encontramos por CUIT y el nombre en DB es "Falta dato" (raro pero posible), actualizamos nombre
                if should_update('nombre', nombre_raw):
                    updates.append("nombre = %s"); vals.append(nombre_clean) # Nombre siempre mayúsculas?
                
                if updates:
                    sql = f"UPDATE clientes SET {', '.join(updates)} WHERE id_cliente = %s"
                    vals.append(cid)
                    cursor.execute(sql, tuple(vals))
                    updated_count += 1
            else:
                # Insertar nuevo
                # Nombre normalizado a mayúsculas si existe
                final_nombre = nombre_clean if nombre_clean else (cuit_raw if cuit_raw != "Falta dato" else "SIN NOMBRE")
                
                cursor.execute("""
                    INSERT INTO clientes (nombre, cuit, email, telefono, celular, web, organizacion, direccion) 
                    VALUES (%s, %s, %s, %s, %s, %s, '', '')
                """, (final_nombre, cuit_raw, email, telefono, celular, web))
                processed_count += 1
                
                # Actualizar lookup para evitar duplicados dentro del mismo archivo
                if cuit_clean: cuit_lookup[cuit_clean] = {'id_cliente': 'new', 'cuit': cuit_raw, 'nombre': final_nombre, 'email': email, 'telefono': telefono, 'celular': celular, 'web': web}
                if nombre_clean: name_lookup[nombre_clean] = {'id_cliente': 'new', 'cuit': cuit_raw, 'nombre': final_nombre, 'email': email, 'telefono': telefono, 'celular': celular, 'web': web}

        conn.commit()
        show_success_message(f"✅ Proceso completado. Clientes nuevos: {processed_count}, Actualizados: {updated_count}", 3)
        st.rerun()
        
    except Exception as e:
        conn.rollback()
        st.error(f"Error al procesar el archivo: {str(e)}")
    finally:
        conn.close()

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
    
    with st.expander("📥 Carga Masiva de Clientes"):
        st.markdown("""
        Sube una planilla **Excel (.xlsx)** o **CSV** con las siguientes columnas (el orden no importa):
        - **CUIT**
        - **Nombre** (o Razón Social)
        - **Email**
        - **Teléfono**
        - **Celular**
        - **Web** (URL)
        """)
        st.info("ℹ️ El sistema validará duplicados por CUIT y Nombre. Si encuentra un cliente existente con datos faltantes, los completará con la información del archivo.")
        
        uploaded_file = st.file_uploader("Seleccionar archivo", type=["xlsx", "xls", "csv"], key="bulk_client_upload")
        
        if uploaded_file:
            if st.button("Procesar Archivo", type="primary", key="process_bulk_btn"):
                _process_bulk_upload(uploaded_file)

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
                
                # Checkbox Activo
                curr_active = bool(client_row['activo']) if 'activo' in client_row else True
                edit_active = st.checkbox("Activo", value=curr_active, key="edit_client_active")
                
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
                                SET nombre = %s, cuit = %s, email = %s, telefono = %s, celular = %s, web = %s, activo = %s
                                WHERE id_cliente = %s
                                """, 
                                (
                                    edit_name_normalized, 
                                    (edit_cuit or "").strip(),
                                    email_val,
                                    tel_val,
                                    (edit_cel or "").strip(),
                                    web_val,
                                    edit_active,
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