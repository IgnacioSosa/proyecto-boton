import streamlit as st
from .database import get_clientes_dataframe, get_connection, check_client_duplicate
from .utils import show_success_message, validate_phone_number, normalize_cuit, safe_rerun, normalize_name, normalize_text
from .utils import show_ordered_dataframe_with_labels, normalize_web, excel_normalize_columns
import re
import pandas as pd
import io
import time
import difflib

def _process_bulk_upload(file, preloaded_df=None):
    try:
        if preloaded_df is not None:
            df = preloaded_df
        elif file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
    except Exception as e:
        st.error(f"Error leyendo el archivo: {e}")
        return

    col_map = {
        'cuit': 'cuit',
        'nombre (razón social)': 'nombre',
        'nombre (razon social)': 'nombre',
        'nombre': 'nombre',
        'razón social': 'nombre',
        'razon social': 'nombre',
        'email': 'email',
        'correo': 'email',
        'mail': 'email',
        'teléfono': 'telefono',
        'telefono': 'telefono',
        'celular': 'celular',
        'movil': 'celular',
        'whatsapp': 'celular',
        'web (url)': 'web',
        'web': 'web',
        'url': 'web',
        'sitio web': 'web',
        'website': 'web',
        'pagina web': 'web',
        'notas': 'notes',
        'nota': 'notes',
        'comentarios': 'notes',
        'observaciones': 'notes',
        'descripción': 'notes',
        'descripcion': 'notes'
    }
    df = excel_normalize_columns(df, col_map)
    
    # Verificar columnas mínimas requeridas
    # El usuario pide campos específicos que coinciden con la solicitud de cliente.
    # CUIT y Nombre son críticos. Email, Teléfono, Celular son importantes pero permitiremos vacíos para no romper.
    
    processed_count = 0
    updated_count = 0
    skipped_count = 0
    
    # Cargar clientes existentes para validación
    existing_df = get_clientes_dataframe()
    # CLEANUP: Asegurar que no haya columnas duplicadas en existing_df para evitar errores de Series ambigüas
    if not existing_df.empty:
        existing_df = existing_df.loc[:, ~existing_df.columns.duplicated()]

    cuit_lookup = {}
    name_lookup = {}
    fuzzy_lookup_list = []
    
    # Palabras comunes a ignorar en comparación difusa
    STOP_WORDS = {'de', 'del', 'la', 'el', 'las', 'los', 'y', 'o', 'sa', 'srl', 'sc', 'sociedad', 'anonima', 'limitada', 'asoc', 'asociacion', 'civil', 'ltd', 'inc', 'corp', 'group', 'grupo', 'holding', 'service', 'services', 'servicios'}

    if not existing_df.empty:
        for _, row in existing_df.iterrows():
            # Helpers para extracción segura
            raw_cuit = row.get('cuit', '')
            if isinstance(raw_cuit, pd.Series): raw_cuit = raw_cuit.iloc[0] if not raw_cuit.empty else ''
            
            raw_nombre = row.get('nombre', '')
            if isinstance(raw_nombre, pd.Series): raw_nombre = raw_nombre.iloc[0] if not raw_nombre.empty else ''

            c = "".join(filter(str.isdigit, str(raw_cuit or '')))
            # Normalización fuerte para matching (elimina puntos, espacios, etc.)
            n = normalize_name(raw_nombre)
            
            # Normalización suave para fuzzy matching (mantiene espacios, minúsculas)
            n_soft = normalize_text(raw_nombre)
            
            if c: cuit_lookup[c] = row
            if n: name_lookup[n] = row
            if n_soft: 
                # Pre-calcular tokens limpios para fuzzy matching
                tokens = [t for t in n_soft.split() if t not in STOP_WORDS]
                n_clean = " ".join(tokens)
                fuzzy_lookup_list.append({
                    'row': row,
                    'full': n_soft,
                    'clean': n_clean,
                    'tokens': set(tokens)
                })
            
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        for _, row in df.iterrows():
            # Función auxiliar para obtener valor o cadena vacía (no "Falta dato" para campos opcionales)
            def get_val(col, default=""):
                if col not in df.columns:
                    return default
                v = row.get(col)
                
                # FIX: Manejo defensivo si v es una Serie (posibles columnas duplicadas que sobrevivieron)
                if isinstance(v, pd.Series):
                    # Priorizar el primer valor no nulo encontrado
                    valid_vals = v.dropna()
                    if not valid_vals.empty:
                        v = valid_vals.iloc[0]
                    else:
                        v = default
                
                if pd.isna(v) or str(v).strip() == "":
                    return default
                return str(v).strip()
            
            # Extraer valores
            cuit_raw = get_val('cuit')
            nombre_raw = get_val('nombre')
            email = get_val('email')
            telefono = get_val('telefono')
            celular = get_val('celular')
            web = get_val('web')
            notes = get_val('notes')
            
            # Validaciones críticas: Nombre o CUIT deben existir para poder identificar/crear
            cuit_clean = "".join(filter(str.isdigit, cuit_raw))
            # Normalización fuerte para búsqueda
            nombre_clean = normalize_name(nombre_raw)
            # Nombre para display/guardado (respetando original pero limpio)
            nombre_display = nombre_raw.strip()
            if not nombre_display and nombre_clean:
                 nombre_display = nombre_clean
            
            # TRUNCATE: Ajustar a límites de base de datos para evitar errores
            # nombre: varchar(100), email: varchar(100), cuit: varchar(32)
            # telefono: varchar(50), celular: varchar(30), web: varchar(300)
            if len(nombre_display) > 100:
                nombre_display = nombre_display[:100]
            if len(cuit_raw) > 32:
                cuit_raw = cuit_raw[:32]
            if len(email) > 100:
                email = email[:100]
            if len(telefono) > 50:
                telefono = telefono[:50]
            if len(celular) > 30:
                celular = celular[:30]
            if len(web) > 300:
                web = web[:300]
            
            if not nombre_clean and not cuit_clean:
                skipped_count += 1
                continue
            
            # Buscar coincidencia
            match = None
            if cuit_clean and cuit_clean in cuit_lookup:
                match = cuit_lookup[cuit_clean]
            elif nombre_clean:
                if nombre_clean in name_lookup:
                    match = name_lookup[nombre_clean]
                else:
                    # 1. Lógica de coincidencia parcial (Prefix)
                    for existing_name in name_lookup:
                        # Ignorar nombres muy cortos para evitar falsos positivos (ej: "LA"), pero permitir "HP", "IK"
                        if len(existing_name) < 2 or len(nombre_clean) < 2:
                            continue
                        
                        # match: "OSPIM" y "OSPIMMOLINERA" (al estar normalizado sin espacios)
                        if existing_name.startswith(nombre_clean) or nombre_clean.startswith(existing_name):
                             match = name_lookup[existing_name]
                             break
                    
                    # 2. Lógica de coincidencia difusa (Fuzzy Match)
                    if match is None:
                        new_soft = normalize_text(nombre_raw)
                        new_tokens = [t for t in new_soft.split() if t not in STOP_WORDS]
                        new_clean = " ".join(new_tokens)
                        new_tokens_set = set(new_tokens)
                        
                        best_score = 0
                        best_candidate = None
                        
                        for candidate in fuzzy_lookup_list:
                            # Optimización: Si no comparten ningún token (palabra), saltar
                            # Salvo que sea muy corto y difflib lo salve, pero asumimos nombres significativos
                            if not new_tokens_set.intersection(candidate['tokens']):
                                continue
                                
                            # A. Ratio directo de difflib sobre texto limpio (sin stop words)
                            ratio = difflib.SequenceMatcher(None, new_clean, candidate['clean']).ratio()
                            
                            # B. Jaccard Index de tokens (overlap de palabras)
                            intersection = len(new_tokens_set.intersection(candidate['tokens']))
                            union = len(new_tokens_set.union(candidate['tokens']))
                            jaccard = intersection / union if union > 0 else 0
                            
                            # C. Subset Match (Si uno es subconjunto estricto del otro)
                            # Ej: "IKE" (sin CUIT) vs "IKE ASISTENCIA..."
                            subset_bonus = 0
                            if new_tokens_set and candidate['tokens']:
                                is_subset = new_tokens_set.issubset(candidate['tokens']) or candidate['tokens'].issubset(new_tokens_set)
                                if is_subset:
                                    # Verificar que el subset sea un prefijo del nombre completo para mayor seguridad
                                    # (Evita que "GAP" coincida con "THE GAP" si "THE" es stopword, pero "GAP" con "GAP SOLUTIONS" sí)
                                    s1, s2 = new_clean, candidate['clean']
                                    short_s, long_s = (s1, s2) if len(s1) < len(s2) else (s2, s1)
                                    if long_s.startswith(short_s):
                                        subset_bonus = 0.95 # Casi certeza
                            
                            # Score combinado
                            score = max(ratio, jaccard, subset_bonus)
                            
                            if score > best_score:
                                best_score = score
                                best_candidate = candidate['row']
                        
                        # Umbral de aceptación
                        if best_score > 0.8:
                            match = best_candidate

            if match is not None:
                # Lógica de actualización (Solo completar datos faltantes)
                # FIX: Si match es Series, asegurar acceso correcto
                if isinstance(match, pd.Series):
                    cid = match.get('id_cliente')
                else:
                    cid = match['id_cliente']
                    
                updates = []
                vals = []
                
                def should_update(db_key, new_val):
                    # Si el valor nuevo está vacío, no actualizamos nada
                    if not new_val: return False
                    
                    if isinstance(match, pd.Series):
                        raw_db = match.get(db_key, '')
                    else:
                        raw_db = match.get(db_key, '')
                        
                    if isinstance(raw_db, pd.Series):
                        valid = raw_db.dropna()
                        raw_db = valid.iloc[0] if not valid.empty else ''
                        
                    db_val = str(raw_db or '').strip()
                    # Si en DB falta (vacío, None), actualizamos
                    if db_val in ["", "None"]:
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
                if should_update('notes', notes):
                    updates.append("notes = %s"); vals.append(notes)
                
                # Si encontramos por CUIT y el nombre en DB está vacío, actualizamos nombre
                if should_update('nombre', nombre_display):
                    updates.append("nombre = %s"); vals.append(nombre_display)
                
                if updates:
                    sql = f"UPDATE clientes SET {', '.join(updates)} WHERE id_cliente = %s"
                    vals.append(cid)
                    cursor.execute(sql, tuple(vals))
                    updated_count += 1
            else:
                # Insertar nuevo
                # Nombre normalizado a mayúsculas si existe
                final_nombre = nombre_display if nombre_display else (cuit_raw if cuit_raw else "SIN NOMBRE")
                
                cursor.execute("""
                    INSERT INTO clientes (nombre, cuit, email, telefono, celular, web, notes, organizacion, direccion) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, '', '')
                """, (final_nombre, cuit_raw, email, telefono, celular, web, notes))
                processed_count += 1
                
                # Actualizar lookup para evitar duplicados dentro del mismo archivo
                if cuit_clean: cuit_lookup[cuit_clean] = {'id_cliente': 'new', 'cuit': cuit_raw, 'nombre': final_nombre, 'email': email, 'telefono': telefono, 'celular': celular, 'web': web, 'notes': notes}
                if nombre_clean: name_lookup[nombre_clean] = {'id_cliente': 'new', 'cuit': cuit_raw, 'nombre': final_nombre, 'email': email, 'telefono': telefono, 'celular': celular, 'web': web, 'notes': notes}

        conn.commit()
        msg = f"✅ Proceso completado. Clientes nuevos: {processed_count}, Actualizados: {updated_count}"
        if skipped_count > 0:
            msg += f", Omitidos (sin datos): {skipped_count}"
        
        # Guardamos mensaje en session state y forzamos reinicio para mostrarlo y colapsar
        st.session_state['client_upload_success'] = msg
        # Incrementamos versión para resetear uploader y asegurar colapso
        st.session_state['bulk_uploader_key_version'] = st.session_state.get('bulk_uploader_key_version', 0) + 1
        from .utils import safe_rerun
        safe_rerun()
        
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
    st.subheader("🏢 Clientes")
    clients_df = get_clientes_dataframe()
    if not clients_df.empty:
        df = clients_df.copy()
        df = df.loc[:, ~df.columns.duplicated()]
        
        # Normalizar valores vacíos o nulos para visualización consistente
        # Reemplaza tanto NaN/None como el string literal "None"
        df = df.fillna("")
        df = df.replace("None", "")
        
        def _is_empty_col(s):
            t = s.astype(str).str.strip()
            return (t == "").all()
            
        empty_cols = [c for c in df.columns if _is_empty_col(df[c])]
        exclude = list(set(empty_cols + ["activo", "id_cliente"]))
        rename_map = {
            "cuit": "CUIT",
            "nombre": "Nombre",
            "email": "Email",
            "telefono": "Teléfono",
            "celular": "Celular",
            "web": "Web (URL)"
        }
        show_ordered_dataframe_with_labels(df, ["cuit", "nombre", "email", "telefono", "celular", "web"], exclude, rename_map)
    else:
        st.info("No hay clientes registrados.")

def render_client_crud_management(is_wizard=False, on_continue=None):
    """Renderiza alta/edición/eliminación de clientes"""
    st.subheader("⚙️ Gestión de Clientes")
    clients_df = get_clientes_dataframe()

    # Mostrar tabla de clientes para revisión al principio
    render_client_management()
    
    # Botón de continuar (Solo en Wizard, solicitado entre la tabla y la carga masiva)
    if is_wizard and on_continue:
        st.write("") # Espaciado
        has_clients = not clients_df.empty
        col_btn, _ = st.columns([0.3, 0.7])
        with col_btn:
            if st.button("Continuar al siguiente paso ➡️", type="primary", key="continue_step_3_mid", disabled=not has_clients):
                on_continue()
            if not has_clients:
                st.caption("⚠️ Debes cargar al menos un cliente para continuar.")
    
    st.divider()
    
    # Manejo de mensajes de éxito tras carga masiva
    if 'client_upload_success' in st.session_state:
        st.success(st.session_state.pop('client_upload_success'))
    
    # En wizard, priorizamos la carga masiva expandiéndola por defecto (antes),
    # ahora por petición del usuario, por defecto colapsado.
    # Usamos una clave dinámica para forzar el redibujado y cierre si es necesario tras upload
    uploader_key_version = st.session_state.get('bulk_uploader_key_version', 0)
    bulk_expanded = False
    add_expanded = False
    
    with st.expander("📥 Carga Masiva de Clientes", expanded=bulk_expanded):
        st.markdown("""
        Sube una planilla **Excel (.xlsx)** o **CSV** con las siguientes columnas (el orden no importa):
        - **CUIT**
        - **Nombre** (o Razón Social)
        - **Email**
        - **Teléfono**
        - **Celular**
        - **Web** (URL)
        - **Notas** (Opcional: Comentarios, Observaciones)
        """)
        st.info("ℹ️ El sistema validará duplicados por CUIT y Nombre. Si encuentra un cliente existente con datos faltantes, los completará con la información del archivo.")
        
        # Implementación de render_excel_uploader para permitir selección de hoja
        from .utils import render_excel_uploader
        uploaded_file, df, selected_sheet = render_excel_uploader(
            label="Seleccionar archivo", 
            key=f"bulk_client_upload_v{uploader_key_version}", 
            enable_sheet_selection=True
        )
        
        if uploaded_file and df is not None:
            if st.button("Procesar Archivo", type="primary", key=f"process_bulk_btn_v{uploader_key_version}"):
                # Llamamos a _process_bulk_upload pero modificada para aceptar DF ya cargado
                # Ojo: _process_bulk_upload original lee el archivo. Necesitamos refactorizar o adaptar.
                # Mejor opción: Adaptar _process_bulk_upload para aceptar DataFrame o File
                _process_bulk_upload(uploaded_file, preloaded_df=df)

    with st.expander("Agregar Nuevo Cliente", expanded=add_expanded):
        new_client_cuit = st.text_input("CUIT", key="new_client_cuit")
        new_client_name = st.text_input("Nombre (Razón Social)", key="new_client_name")
        new_client_email = st.text_input("Email", key="new_client_email")
        new_client_phone = st.text_input("Teléfono", key="new_client_phone")
        new_client_cel = st.text_input("Celular", key="new_client_cel")
        new_client_web = st.text_input("Web (URL)", key="new_client_web")
        new_client_notes = st.text_area("Notas", key="new_client_notes")
        
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
            else:
                is_valid_phone, phone_msg_or_val = validate_phone_number(tel_val)
                if not is_valid_phone:
                    errors.append(f"Teléfono: {phone_msg_or_val}")
                else:
                    tel_val = phone_msg_or_val

            # Celular Validation
            cel_val = (new_client_cel or "").strip()
            if not cel_val:
                # errors.append("El celular es obligatorio.")
                cel_val = ""
            else:
                is_valid_cel, cel_msg_or_val = validate_phone_number(cel_val)
                if not is_valid_cel:
                    errors.append(f"Celular: {cel_msg_or_val}")
                else:
                    cel_val = cel_msg_or_val

                # Web Validation
            web_val = normalize_web(new_client_web)
            
            if errors:
                for e in errors:
                    st.error(e)
            else:
                cuit_norm_insert = normalize_cuit(new_client_cuit)
                # Verificar duplicados
                is_dup, dup_msg = check_client_duplicate(cuit_norm_insert, (new_client_name or "").strip())
                if is_dup:
                    st.error(dup_msg)
                else:
                    new_client_name_normalized = new_client_name.strip().upper()
                    conn = get_connection()
                c = conn.cursor()
                try:
                    # Intenta insertar con los nuevos campos. 
                    # Asumimos que la tabla tiene: nombre, cuit, email, telefono, celular, web, notes
                    # Si 'direccion' u 'organizacion' son requeridos, pasamos string vacío.
                    c.execute(
                        """
                        INSERT INTO clientes (nombre, cuit, email, telefono, celular, web, organizacion, direccion, notes) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, 
                        (
                            new_client_name_normalized, 
                            cuit_norm_insert,
                            email_val,
                            tel_val,
                            cel_val,
                            web_val,
                            "", # Organizacion vacía por defecto
                            "", # Direccion vacía por defecto
                            new_client_notes
                        )
                    )
                    conn.commit()
                    st.success(f"Cliente '{new_client_name_normalized}' agregado exitosamente.")
                    safe_rerun()
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
                curr_notes = client_row['notes'] if 'notes' in client_row else ""
                
                edit_cuit = st.text_input("CUIT", value=str(curr_cuit or ""), key="edit_client_cuit")
                edit_name = st.text_input("Nombre (Razón Social)", value=client_row['nombre'], key="edit_client_name")
                edit_email = st.text_input("Email", value=str(curr_email or ""), key="edit_client_email")
                edit_phone = st.text_input("Teléfono", value=str(curr_phone or ""), key="edit_client_phone")
                edit_cel = st.text_input("Celular", value=str(curr_cel or ""), key="edit_client_cel")
                edit_web = st.text_input("Web (URL)", value=str(curr_web or ""), key="edit_client_web")
                edit_notes = st.text_area("Notas", value=str(curr_notes or ""), key="edit_client_notes")
                
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
                    else:
                        is_valid_phone, phone_msg_or_val = validate_phone_number(tel_val)
                        if not is_valid_phone:
                            errors.append(f"Teléfono: {phone_msg_or_val}")
                        else:
                            tel_val = phone_msg_or_val

                    cel_val = (edit_cel or "").strip()
                    if not cel_val:
                        # errors.append("El celular es obligatorio.")
                        cel_val = ""
                    else:
                        is_valid_cel, cel_msg_or_val = validate_phone_number(cel_val)
                        if not is_valid_cel:
                            errors.append(f"Celular: {cel_msg_or_val}")
                        else:
                            cel_val = cel_msg_or_val

                    web_val = normalize_web(edit_web)

                    if errors:
                        for e in errors:
                            st.error(e)
                    else:
                        edit_name_normalized = edit_name.strip().upper()
                        from .utils import normalize_cuit, safe_rerun
                        cuit_normalized_edit = normalize_cuit(edit_cuit)
                        conn = get_connection()
                        c = conn.cursor()
                        try:
                            c.execute(
                                """
                                UPDATE clientes 
                                SET nombre = %s, cuit = %s, email = %s, telefono = %s, celular = %s, web = %s, notes = %s, activo = %s
                                WHERE id_cliente = %s
                                """, 
                                (
                                    edit_name_normalized, 
                                    cuit_normalized_edit,
                                    email_val,
                                    tel_val,
                                    cel_val,
                                    web_val,
                                    edit_notes,
                                    edit_active,
                                    client_id
                                )
                            )
                            conn.commit()
                            st.success(f"Cliente actualizado a '{edit_name_normalized}' exitosamente.")
                            safe_rerun()
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
                        # 1. Contar elementos relacionados para informar (opcional) o proceder con borrado en cascada
                        c.execute("SELECT COUNT(*) FROM registros WHERE id_cliente = %s", (client_id,))
                        registro_count = c.fetchone()[0]
                        
                        c.execute("SELECT COUNT(*) FROM proyectos WHERE cliente_id = %s", (client_id,))
                        proyectos_count = c.fetchone()[0]

                        # Mensaje de advertencia si tiene muchos datos
                        if registro_count > 0 or proyectos_count > 0:
                            st.warning(f"⚠️ Eliminando {registro_count} registros de horas y {proyectos_count} proyectos asociados...")

                        # 2. Borrado en Cascada Manual (Orden seguro)
                        # - Registros (Horas)
                        c.execute("DELETE FROM registros WHERE id_cliente = %s", (client_id,))
                        # - Proyectos (y sus dependencias si las hubiera, aunque proyectos suele ser padre)
                        c.execute("DELETE FROM proyectos WHERE cliente_id = %s", (client_id,))
                        # - Contactos asociados al cliente
                        c.execute("DELETE FROM contactos WHERE etiqueta_tipo = 'cliente' AND etiqueta_id = %s", (client_id,))
                        # - Puntajes
                        c.execute("DELETE FROM clientes_puntajes WHERE id_cliente = %s", (client_id,))
                        # - Solicitudes temporales (limpieza)
                        c.execute("DELETE FROM cliente_solicitudes WHERE temp_cliente_id = %s", (client_id,))

                        # 3. Finalmente eliminar el cliente
                        c.execute("DELETE FROM clientes WHERE id_cliente = %s", (client_id,))
                        conn.commit()
                        show_success_message(f"✅ Cliente '{client_row['nombre']}' y todos sus datos asociados fueron eliminados exitosamente.", 2)
                        from .utils import safe_rerun
                        safe_rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Error al eliminar cliente: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay clientes para eliminar.")
