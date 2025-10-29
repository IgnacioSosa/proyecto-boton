import pandas as pd
import streamlit as st
from .database import (
    get_connection, get_tecnicos_dataframe, get_clientes_dataframe,
    get_tipos_dataframe, get_modalidades_dataframe, check_record_duplicate,
    get_or_create_tecnico, get_or_create_cliente, get_or_create_tipo_tarea, 
    get_or_create_modalidad
)
from .utils import show_success_message, month_name_es, render_excel_uploader


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
        st.rerun()
    
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
                    
                    success_count, error_count, duplicate_count = process_excel_data(excel_df)
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
                    if success_count > 0 or duplicate_count > 0:
                        st.session_state["records_processed_success"] = True
                        st.info("🔄 La página se recargará automáticamente para mostrar los nuevos registros.")
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al procesar el archivo: {str(e)}")

def render_records_management(df, role_id=None):
        st.subheader("📋 Tabla de Registros")
        
        if df is None:
            df = pd.DataFrame()
        
        if 'id' in df.columns:
            other_columns = [col for col in df.columns if col != 'id']
            df = df[['id'] + other_columns]
        
        if df.empty:
            st.info("📝 No hay registros disponibles. Puedes importar datos usando la funcionalidad de carga de Excel arriba.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Edición de registros directamente debajo de la tabla
        st.divider()
        st.subheader("✏️ Editar o Eliminar Registro")
        
        if not df.empty:
            registro_ids = df['id'].tolist()
            registro_fechas = df['fecha'].tolist()
            registro_tecnicos = df['tecnico'].tolist()
            registro_clientes = df['cliente'].tolist()
            registro_tareas = df['tarea_realizada'].tolist()
            registro_tiempos = df['tiempo'].tolist()
            registro_tipos = df['tipo_tarea'].tolist()
            registro_options = [
                f"ID: {rid} | {rfecha} | {rtecnico} | {rcliente} | {rtipo} | {rtarea[:30]}{'...' if len(rtarea) > 30 else ''} | {rtiempo}h" 
                for rid, rfecha, rtecnico, rcliente, rtipo, rtarea, rtiempo in 
                zip(registro_ids, registro_fechas, registro_tecnicos, registro_clientes, registro_tipos, registro_tareas, registro_tiempos)
            ]
            
            selected_registro_admin = st.selectbox(
                "Seleccionar Registro", 
                options=registro_options, 
                key=f"select_registro_admin_{role_id if role_id else 'default'}",
                help="Formato: ID | Fecha | Técnico | Cliente | Tipo | Tarea | Tiempo"
            )
            
            if selected_registro_admin:
                registro_id_admin = int(selected_registro_admin.split(' | ')[0].replace('ID: ', ''))
                registro_seleccionado_admin = df[df['id'] == registro_id_admin].iloc[0]
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✏️ Editar Registro", key=f"edit_btn_admin_{role_id if role_id else 'default'}"):
                        render_admin_edit_form(registro_seleccionado_admin, registro_id_admin, role_id)
                with col2:
                    if st.button("🗑️ Eliminar Registro", key=f"delete_btn_admin_{role_id if role_id else 'default'}"):
                        render_admin_delete_form(registro_seleccionado_admin, registro_id_admin, role_id)
        else:
            st.info("No hay registros disponibles para editar o eliminar.")

def render_admin_edit_form(registro_seleccionado, registro_id, role_id=None):
    """Renderiza el formulario de edición de registros para administradores"""
    st.subheader("✏️ Editar Registro")
    tecnicos_df = get_tecnicos_dataframe()
    clientes_df = get_clientes_dataframe()
    tipos_df = get_tipos_dataframe()
    modalidades_df = get_modalidades_dataframe()

    with st.form(key=f"edit_form_admin_{registro_id}_{role_id if role_id else 'default'}"):
        col1, col2 = st.columns(2)
        with col1:
            fecha_actual = pd.to_datetime(registro_seleccionado['fecha'], format='%d/%m/%y').date()
            nueva_fecha = st.date_input("Fecha", value=fecha_actual)
            tecnico_actual = registro_seleccionado['tecnico']
            tecnico_index = tecnicos_df[tecnicos_df['nombre'] == tecnico_actual].index
            tecnico_index = tecnico_index[0] if len(tecnico_index) > 0 else 0
            nuevo_tecnico = st.selectbox("Técnico", tecnicos_df['nombre'].tolist(), index=tecnico_index)
            cliente_actual = registro_seleccionado['cliente']
            cliente_index = clientes_df[clientes_df['nombre'] == cliente_actual].index
            cliente_index = cliente_index[0] if len(cliente_index) > 0 else 0
            nuevo_cliente = st.selectbox("Cliente", clientes_df['nombre'].tolist(), index=cliente_index)
            with col2:
                tipo_actual = registro_seleccionado['tipo_tarea']
                tipo_index = tipos_df[tipos_df['descripcion'] == tipo_actual].index
                tipo_index = tipo_index[0] if len(tipo_index) > 0 else 0
                nuevo_tipo = st.selectbox("Tipo de Tarea", tipos_df['descripcion'].tolist(), index=tipo_index)
                modalidad_actual = registro_seleccionado['modalidad']
                modalidad_index = modalidades_df[modalidades_df['descripcion'] == modalidad_actual].index
                modalidad_index = modalidad_index[0] if len(modalidad_index) > 0 else 0
                nueva_modalidad = st.selectbox("Modalidad", modalidades_df['descripcion'].tolist(), index=modalidad_index)
                tiempo_actual = float(registro_seleccionado['tiempo'])
                nuevo_tiempo = st.number_input("Tiempo (horas)", min_value=0.5, max_value=24.0, value=tiempo_actual, step=0.5)

        nueva_tarea = st.text_area("Tarea Realizada", value=registro_seleccionado['tarea_realizada'], height=100)
        nuevo_ticket = st.text_input("Número de Ticket", value=registro_seleccionado.get('numero_ticket', 'N/A'))
        nueva_descripcion = st.text_area("Descripción", value=registro_seleccionado.get('descripcion', ''), height=80)

        submitted = st.form_submit_button("💾 Guardar Cambios")
        if submitted:
            if not nueva_tarea:
                st.error("La tarea realizada es obligatoria.")
            elif nuevo_tiempo < 0.5:
                st.error("El tiempo mínimo debe ser de 0.5 horas (30 minutos).")
            else:
                try:
                        conn = get_connection()
                        c = conn.cursor()
                        id_tecnico_admin = tecnicos_df[tecnicos_df['nombre'] == nuevo_tecnico]['id_tecnico'].iloc[0]
                        id_cliente_admin = clientes_df[clientes_df['nombre'] == nuevo_cliente]['id_cliente'].iloc[0]
                        id_tipo_admin = tipos_df[tipos_df['descripcion'] == nuevo_tipo]['id_tipo'].iloc[0]
                        id_modalidad_admin = modalidades_df[modalidades_df['descripcion'] == nueva_modalidad]['id_modalidad'].iloc[0]
                        fecha_formateada = nueva_fecha.strftime('%d/%m/%y')
                        mes_num = nueva_fecha.month if 1 <= nueva_fecha.month <= 12 else pd.Timestamp.now().month
                        mes = month_name_es(mes_num)
                        if not check_record_duplicate(
                            fecha_formateada, id_tecnico_admin, id_cliente_admin, 
                            id_tipo_admin, id_modalidad_admin, nueva_tarea, int(nuevo_tiempo), registro_id
                        ):
                            c.execute(
                                '''
                                UPDATE registros
                                SET fecha = %s, id_tecnico = %s, id_cliente = %s, id_tipo = %s,
                                    id_modalidad = %s, tarea_realizada = %s, numero_ticket = %s,
                                    tiempo = %s, descripcion = %s, mes = %s
                                WHERE id = %s
                                ''',
                                (
                                    fecha_formateada, id_tecnico_admin, id_cliente_admin, id_tipo_admin,
                                    id_modalidad_admin, nueva_tarea, nuevo_ticket, int(nuevo_tiempo),
                                    nueva_descripcion, mes, registro_id
                                )
                            )
                            conn.commit()
                            conn.close()
                            show_success_message("✅ Registro actualizado exitosamente")
                            st.rerun()
                        else:
                            st.error("❌ Ya existe un registro idéntico. No se puede actualizar.")
                except Exception as e:
                        st.error(f"❌ Error al actualizar el registro: {str(e)}")

def render_admin_delete_form(registro_seleccionado, registro_id, role_id=None):
    """Renderiza el formulario de eliminación de registros para administradores"""
    st.subheader("🗑️ Eliminar Registro")
    st.warning("⚠️ **¡ATENCIÓN!** Esta acción no se puede deshacer.")
    st.info(f"""
    **Registro a eliminar:**
    - **ID:** {registro_id}
    - **Fecha:** {registro_seleccionado['fecha']}
    - **Técnico:** {registro_seleccionado['tecnico']}
                    - **Cliente:** {registro_seleccionado['cliente']}
                    - **Tipo:** {registro_seleccionado['tipo_tarea']}
                    - **Modalidad:** {registro_seleccionado['modalidad']}
                    - **Tiempo:** {registro_seleccionado['tiempo']}h
    - **Tarea:** {registro_seleccionado['tarea_realizada'][:50]}{'...' if len(registro_seleccionado['tarea_realizada']) > 50 else ''}
    """)
    
    confirmacion = st.checkbox("Confirmo que deseo eliminar este registro permanentemente")
    if confirmacion:
        if st.button("🗑️ ELIMINAR REGISTRO", type="primary"):
            try:
                conn = get_connection()
                c = conn.cursor()
                c.execute("DELETE FROM registros WHERE id = %s", (registro_id,))
                conn.commit()
                conn.close()
                show_success_message("✅ Registro eliminado exitosamente")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al eliminar el registro: {str(e)}")

# Alias para compatibilidad con admin_visualizations.py
render_records_table = render_records_management
