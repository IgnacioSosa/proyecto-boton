import pandas as pd
import streamlit as st
from .database import (
    get_connection, get_tecnicos_dataframe, get_clientes_dataframe,
    get_tipos_dataframe, get_modalidades_dataframe, check_record_duplicate,
    get_or_create_tecnico, get_or_create_cliente, get_or_create_tipo_tarea, 
    get_or_create_modalidad, delete_registros_batch
)
from .utils import show_success_message, month_name_es, render_excel_uploader, safe_rerun


def render_records_import(role_id=None):
    """Renderiza la gestión de registros con funcionalidad completa de carga Excel"""
    
    # NUEVO: Limpiar el archivo cargado si se procesó exitosamente en la ejecución anterior
    if st.session_state.get("records_processed_success", False):
        # Limpiar el estado del uploader
        uploader_key = f"records_excel_upload_{role_id if role_id else 'default'}"
        sheet_selector_key = f"{uploader_key}_sheet_selector"
        
        if uploader_key in st.session_state:
            del st.session_state[uploader_key]
        if sheet_selector_key in st.session_state:
            del st.session_state[sheet_selector_key]
        
        # Limpiar el flag de procesamiento exitoso
        del st.session_state["records_processed_success"]
        
        # Mostrar mensaje de confirmación
        st.success("✅ Archivo eliminado después del procesamiento exitoso")
        safe_rerun()
    
    # Funcionalidad de carga de Excel
    st.subheader("📊 Importar Registros desde Excel")
    uploaded_file, excel_df, selected_sheet = render_excel_uploader(
        label="Selecciona un archivo Excel con registros de actividad (.xls o .xlsx)",
        key=f"records_excel_upload_{role_id if role_id else 'default'}",
        expanded=False,
        enable_sheet_selection=True
    )
    if uploaded_file is not None and excel_df is not None:
        if st.button("🚀 Procesar y Cargar Datos", key=f"process_excel_{role_id if role_id else 'default'}"):
            with st.spinner("Procesando archivo Excel..."):
                try:
                    # Importar aquí para evitar importación circular
                    from .admin_panel import process_excel_data
                    
                    success_count, error_count, duplicate_count, missing_clients = process_excel_data(excel_df)
                    registros_asignados = 0
                    if success_count > 0:
                        from .admin_panel import auto_assign_records_by_technician
                        conn = get_connection()
                        with st.spinner("Asignando registros a usuarios..."):
                            registros_asignados = auto_assign_records_by_technician(conn)
                        conn.close()
                    mensaje_resumen = f"✅ **Procesamiento completado:** {success_count} registros procesados"
                    if registros_asignados > 0:
                        mensaje_resumen += f", {registros_asignados} asignados automáticamente a usuarios"
                    st.success(mensaje_resumen)
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Registros procesados", success_count, delta=success_count if success_count > 0 else None)
                    with col2:
                        if duplicate_count > 0:
                            st.info(f"🔄 **{duplicate_count} registros no se procesaron por ser duplicados**")
                        else:
                            st.metric("Duplicados encontrados", duplicate_count, delta=None)
                    with col3:
                        st.metric("Errores", error_count, delta=f"-{error_count}" if error_count > 0 else None)
                        
                    if missing_clients:
                        missing_list_str = ", ".join(sorted(missing_clients))
                        if len(missing_clients) <= 5:
                            st.warning(f"⚠️ **{len(missing_clients)} clientes no fueron encontrados** y sus registros fueron omitidos: **{missing_list_str}**. Debes crearlos primero en la sección de 'Gestión de Clientes'.")
                        else:
                            st.warning(f"⚠️ **{len(missing_clients)} clientes no fueron encontrados** y sus registros fueron omitidos. Debes crearlos primero en la sección de 'Gestión de Clientes'.")
                            with st.expander("Ver lista de clientes faltantes"):
                                st.write(missing_list_str)
                        
                    if success_count > 0 or duplicate_count > 0:
                        st.session_state["records_processed_success"] = True
                        st.info("🔄 La página se recargará automáticamente para mostrar los nuevos registros.")
                        safe_rerun()
                except Exception as e:
                    st.error(f"❌ Error al procesar el archivo: {str(e)}")

def render_records_management(df, role_id=None, show_header=True):
    # Mostrar/ocultar solo el encabezado interno
    if show_header:
        st.subheader("📋 Tabla de Registros")
    # Normalizar el dataframe aunque no se muestre el encabezado
    if df is None:
        df = pd.DataFrame()
    
    if 'id' in df.columns:
        other_columns = [col for col in df.columns if col != 'id']
        df = df[['id'] + other_columns]
    
    display_df = df
    if df.empty:
        st.info("📝 No hay registros disponibles. Puedes importar datos usando la funcionalidad de carga de Excel arriba.")
    else:
        tecnicos = sorted([t for t in df['tecnico'].dropna().unique()])
        tecnico_options = ["Todos los registros"] + tecnicos
        selected_tecnico = st.selectbox(
            "Técnico",
            options=tecnico_options,
            index=0,
            key=f"select_tecnico_admin_{role_id if role_id else 'default'}",
        )
        display_df = df if selected_tecnico == "Todos los registros" else df[df['tecnico'] == selected_tecnico]
        
        # Asegurar que la fecha es datetime para correcto ordenamiento en Streamlit
        if not display_df.empty and 'fecha' in display_df.columns:
            try:
                # Crear una copia para evitar SettingWithCopyWarning
                display_df = display_df.copy()
                # Convertir a datetime, manejando errores y formatos mixtos
                display_df['fecha'] = pd.to_datetime(display_df['fecha'], dayfirst=True, errors='coerce')
            except Exception:
                pass

        st.dataframe(
            display_df, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "fecha": st.column_config.DateColumn(
                    "Fecha",
                    format="DD/MM/YYYY",
                ),
            }
        )
    
    st.divider()
    st.subheader("🛠️ Gestión de Registros")
    
    if not display_df.empty:
        registro_ids = display_df['id'].tolist()
        registro_fechas = display_df['fecha'].tolist()
        registro_tecnicos = display_df['tecnico'].tolist()
        registro_clientes = display_df['cliente'].tolist()
        registro_tareas = display_df['tarea_realizada'].tolist()
        registro_tiempos = display_df['tiempo'].tolist()
        registro_tipos = display_df['tipo_tarea'].tolist()
        
        # Formatear fechas para el dropdown si son datetimes
        def format_date_for_display(d):
            if pd.isna(d): return "Sin fecha"
            if hasattr(d, 'strftime'): return d.strftime('%d/%m/%y')
            return str(d)

        registro_options = [
            f"ID: {rid} | {format_date_for_display(rfecha)} | {rtecnico} | {rcliente} | {rtipo} | {rtarea[:30]}{'...' if len(rtarea) > 30 else ''} | {rtiempo}h" 
            for rid, rfecha, rtecnico, rcliente, rtipo, rtarea, rtiempo in 
            zip(registro_ids, registro_fechas, registro_tecnicos, registro_clientes, registro_tipos, registro_tareas, registro_tiempos)
        ]
        
        # Opción 1: Edición/Eliminación Individual
        with st.expander("✏️ Editar o Eliminar Individualmente", expanded=True):
            selected_registro_admin = st.selectbox(
                "Seleccionar Registro", 
                options=registro_options, 
                key=f"select_registro_admin_{role_id if role_id else 'default'}",
                help="Formato: ID | Fecha | Técnico | Cliente | Tipo | Tarea | Tiempo"
            )
            
            if selected_registro_admin:
                registro_id_admin = int(selected_registro_admin.split(' | ')[0].replace('ID: ', ''))
                registro_seleccionado_admin = display_df[display_df['id'] == registro_id_admin].iloc[0]
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✏️ Editar Registro", key=f"edit_btn_admin_{role_id if role_id else 'default'}"):
                        render_admin_edit_form(registro_seleccionado_admin, registro_id_admin, role_id)
                with col2:
                    if st.button("🗑️ Eliminar Registro", key=f"delete_btn_admin_{role_id if role_id else 'default'}"):
                        render_admin_delete_form(registro_seleccionado_admin, registro_id_admin, role_id)

        # Opción 2: Eliminación Masiva
        with st.expander("🔥 Eliminar Múltiples Registros", expanded=False):
            st.warning("⚠️ Cuidado: Esta acción eliminará permanentemente TODOS los registros seleccionados.")
            
            selected_registros_batch = st.multiselect(
                "Selecciona los registros a eliminar:",
                options=registro_options,
                key=f"select_registro_batch_delete_admin_{role_id if role_id else 'default'}"
            )
            
            if selected_registros_batch:
                count = len(selected_registros_batch)
                if st.button(f"🗑️ Eliminar {count} Registros Seleccionados", type="primary", key=f"btn_batch_delete_admin_{role_id if role_id else 'default'}"):
                    # Extraer IDs
                    ids_to_delete = [int(opt.split(' | ')[0].replace('ID: ', '')) for opt in selected_registros_batch]
                    
                    deleted_count = delete_registros_batch(ids_to_delete)
                    
                    if deleted_count >= 0:
                        show_success_message(f"✅ Se han eliminado {deleted_count} registros exitosamente.", 2)
                        safe_rerun()
                    else:
                        st.error("Hubo un error al intentar eliminar los registros.")
    else:
        st.info("No hay registros disponibles para editar o eliminar.")

def render_admin_edit_form(registro_seleccionado, registro_id, role_id=None):
    """Renderiza el formulario de edición de registros para administradores"""
    st.subheader("✏️ Editar Registro")
    
    with st.form(key=f"form_edit_registro_admin_{registro_id}"):
        # Pre-procesamiento de valores actuales
        try:
            fecha_val = registro_seleccionado['fecha']
            if hasattr(fecha_val, 'date'):
                fecha_actual = fecha_val.date()
            else:
                fecha_actual = pd.to_datetime(fecha_val, format='%d/%m/%y').date()
        except:
            fecha_actual = pd.to_datetime(registro_seleccionado['fecha']).date()
            
        nueva_fecha = st.date_input("Fecha", value=fecha_actual)
        
        # Tecnico (solo lectura o editable si es necesario, aquí lo dejamos editable)
        tecnicos_df = get_tecnicos_dataframe()
        tecnicos_lista = tecnicos_df['nombre'].tolist() if not tecnicos_df.empty else []
        tecnico_actual = registro_seleccionado['tecnico']
        if tecnico_actual not in tecnicos_lista:
            tecnicos_lista.append(tecnico_actual)
        nuevo_tecnico = st.selectbox("Técnico", options=tecnicos_lista, index=tecnicos_lista.index(tecnico_actual))
        
        # Cliente
        clientes_df = get_clientes_dataframe(only_active=True)
        clientes_lista = clientes_df['nombre'].tolist() if not clientes_df.empty else []
        cliente_actual = registro_seleccionado['cliente']
        if cliente_actual not in clientes_lista:
            clientes_lista.append(cliente_actual)
        nuevo_cliente = st.selectbox("Cliente", options=clientes_lista, index=clientes_lista.index(cliente_actual))
        
        # Tipo de Tarea
        tipos_df = get_tipos_dataframe()
        tipos_lista = tipos_df['descripcion'].tolist() if not tipos_df.empty else []
        tipo_actual = registro_seleccionado['tipo_tarea']
        if tipo_actual not in tipos_lista:
            tipos_lista.append(tipo_actual)
        nuevo_tipo = st.selectbox("Tipo de Tarea", options=tipos_lista, index=tipos_lista.index(tipo_actual))
        
        # Modalidad
        modalidades_df = get_modalidades_dataframe()
        modalidades_lista = modalidades_df['descripcion'].tolist() if not modalidades_df.empty else []
        modalidad_actual = registro_seleccionado.get('modalidad', 'Presencial') # Default a Presencial si no existe
        if modalidad_actual not in modalidades_lista:
            modalidades_lista.append(modalidad_actual)
        nueva_modalidad = st.selectbox("Modalidad", options=modalidades_lista, index=modalidades_lista.index(modalidad_actual) if modalidad_actual in modalidades_lista else 0)
        
        nueva_tarea = st.text_area("Tarea Realizada", value=registro_seleccionado['tarea_realizada'], max_chars=100)
        
        # Manejo de valores nulos para campos opcionales
        val_ticket = registro_seleccionado.get('numero_ticket', '')
        if pd.isna(val_ticket): val_ticket = ""
        nuevo_ticket = st.text_input("Número de Ticket", value=str(val_ticket), max_chars=20)
        
        val_desc = registro_seleccionado.get('descripcion', '')
        if pd.isna(val_desc): val_desc = ""
        nueva_descripcion = st.text_area("Descripción", value=str(val_desc), max_chars=250)
        
        nuevo_tiempo = st.number_input("Tiempo (horas)", value=float(registro_seleccionado['tiempo']), min_value=0.1, step=0.5)
        nuevo_es_hora_extra = st.checkbox("Hora extra", value=bool(registro_seleccionado.get('es_hora_extra', False)))

        col1, col2 = st.columns(2)
        with col1:
            submit_button = st.form_submit_button("💾 Guardar Cambios", type="primary")
        with col2:
            if st.form_submit_button("❌ Cancelar"):
                safe_rerun()

        if submit_button:
            # Validaciones básicas
            if not nueva_tarea:
                st.error("La descripción de la tarea es obligatoria.")
            else:
                # Actualizar en BD
                conn = get_connection()
                cursor = conn.cursor()
                
                # Obtener IDs foráneos (similar a add_registro)
                tecnico_id = get_or_create_tecnico(cursor, nuevo_tecnico)
                cliente_id = get_or_create_cliente(cursor, nuevo_cliente)
                tipo_id = get_or_create_tipo_tarea(cursor, nuevo_tipo)
                modalidad_id = get_or_create_modalidad(cursor, nueva_modalidad)
                
                try:
                    cursor.execute("""
                        UPDATE registros 
                        SET fecha = %s, tecnico_id = %s, cliente_id = %s, tipo_id = %s, 
                            tarea_realizada = %s, numero_ticket = %s, descripcion = %s,
                            tiempo = %s, es_hora_extra = %s, modalidad_id = %s
                        WHERE id = %s
                    """, (nueva_fecha, tecnico_id, cliente_id, tipo_id, nueva_tarea, nuevo_ticket, nueva_descripcion, nuevo_tiempo, nuevo_es_hora_extra, modalidad_id, registro_id))
                    conn.commit()
                    show_success_message("Registro actualizado correctamente", 2)
                    safe_rerun()
                except Exception as e:
                    st.error(f"Error al actualizar: {e}")
                finally:
                    conn.close()

def render_admin_delete_form(registro_seleccionado, registro_id, role_id=None):
    """Renderiza confirmación de eliminación"""
    st.warning(f"¿Estás seguro que deseas eliminar este registro?")
    
    # Manejo defensivo de fecha para visualización
    fecha_str = "Fecha desconocida"
    try:
        val = registro_seleccionado['fecha']
        if hasattr(val, 'strftime'):
            fecha_str = val.strftime('%d/%m/%Y')
        else:
            fecha_str = str(val)
    except:
        pass

    st.markdown(f"""
    **Detalles del registro a eliminar:**
    - **Fecha:** {fecha_str}
    - **Técnico:** {registro_seleccionado['tecnico']}
    - **Cliente:** {registro_seleccionado['cliente']}
    - **Tarea:** {registro_seleccionado['tarea_realizada']}
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Sí, Eliminar", key=f"confirm_delete_{registro_id}", type="primary"):
            conn = get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM registros WHERE id = %s", (registro_id,))
                conn.commit()
                show_success_message("Registro eliminado correctamente", 2)
                safe_rerun()
            except Exception as e:
                st.error(f"Error al eliminar: {e}")
            finally:
                conn.close()
    with col2:
        if st.button("❌ No, Cancelar", key=f"cancel_delete_{registro_id}"):
            safe_rerun()

# Alias para compatibilidad con visualizaciones
render_records_table = render_records_management
