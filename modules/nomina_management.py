import streamlit as st
import pandas as pd
import time  
from datetime import datetime, date
from .database import (
    get_nomina_dataframe, get_nomina_dataframe_expanded,
    add_empleado_nomina, update_empleado_nomina, delete_empleado_nomina,
    get_departamentos_list  # Agregar esta importación
)
from .utils import show_success_message

def render_nomina_edit_delete_forms(nomina_df):
    """Renderiza formularios de agregar, edición y eliminación de empleados de nómina"""
    
    # Formulario para agregar empleado
    with st.expander("➕ Agregar Empleado"):
        col1, col2 = st.columns(2)
        with col1:
            new_nombre = st.text_input("Nombre", key="new_empleado_nombre")
            new_apellido = st.text_input("Apellido", key="new_empleado_apellido")
            new_email = st.text_input("Email", key="new_empleado_email")
            new_celular = st.text_input("Celular", key="new_empleado_celular")
        with col2:
            new_cargo = st.text_input("Cargo", key="new_empleado_cargo")
            
            # Obtener departamentos existentes
            departamentos_existentes = get_departamentos_list()
            
            # Selectbox para departamento (sin la opción "Otro")
            departamento_seleccionado = st.selectbox(
                "Departamento", 
                options=departamentos_existentes,
                index=None,
                placeholder="Selecciona un departamento",
                key="select_departamento"
            )
            
            new_departamento = departamento_seleccionado
            
            # Para fecha de ingreso, permitir desde 1950 hasta fechas futuras razonables
            new_fecha_ingreso = st.date_input(
                "Fecha de Ingreso", 
                min_value=date(1950, 1, 1),
                max_value=date(2050, 12, 31),
                key="new_empleado_fecha_ingreso"
            )
            # Fecha de Nacimiento (ahora obligatoria)
            new_fecha_nacimiento = st.date_input(
                "Fecha de Nacimiento", 
                value=None, 
                min_value=date(1900, 1, 1),
                max_value=date.today(),
                key="new_empleado_fecha_nacimiento"
            )
        
        # Botón para agregar empleado
        if st.button("Agregar Empleado", key="add_empleado_btn"):
            # Usar None (NULL) para campos vacíos
            celular_final = new_celular if new_celular else None
            cargo_final = new_cargo if new_cargo else None
            
            # Validación: todos los campos obligatorios deben estar completos
            if new_nombre and new_apellido and new_departamento and new_fecha_ingreso and new_fecha_nacimiento:
                fecha_nacimiento_str = new_fecha_nacimiento.strftime('%Y-%m-%d')
                fecha_ingreso_str = new_fecha_ingreso.strftime('%Y-%m-%d')
                
                if add_empleado_nomina(new_nombre, new_apellido, new_email, celular_final, 
                                     cargo_final, new_departamento, fecha_ingreso_str, fecha_nacimiento_str):
                    show_success_message(f"✅ Empleado '{new_nombre} {new_apellido}' agregado exitosamente.", 3)
                else:
                    st.error("Error al agregar empleado. El celular puede ya existir.")
            else:
                st.error("Los campos obligatorios son: Nombre, Apellido, Departamento, Fecha de Ingreso y Fecha de Nacimiento.")
    
    # Formulario para editar empleado
    with st.expander("✏️ Editar Empleado"):
        if not nomina_df.empty:
            empleado_ids = nomina_df['id'].tolist()
            empleado_names = [f"{row['nombre']} {row['apellido']} - {row['documento']}" for _, row in nomina_df.iterrows()]
            empleado_options = [f"{eid} - {ename}" for eid, ename in zip(empleado_ids, empleado_names)]
            
            selected_empleado_edit = st.selectbox("Seleccionar Empleado para Editar", 
                                                 options=empleado_options, key="select_empleado_edit")
            if selected_empleado_edit:
                empleado_id = int(selected_empleado_edit.split(' - ')[0])
                empleado_row = nomina_df[nomina_df['id'] == empleado_id].iloc[0]
                
                col1, col2 = st.columns(2)
                with col1:
                    # Limpiar valores 'falta dato' al cargar - usar la misma lógica que en crear empleado
                    nombre_inicial = empleado_row['nombre'] if empleado_row['nombre'] and str(empleado_row['nombre']).lower() != 'falta dato' else ''
                    apellido_inicial = empleado_row['apellido'] if empleado_row['apellido'] and str(empleado_row['apellido']).lower() != 'falta dato' else ''
                    email_inicial = empleado_row['email'] if empleado_row['email'] and str(empleado_row['email']).lower() != 'falta dato' else ''
                    celular_inicial = empleado_row['documento'] if empleado_row['documento'] and str(empleado_row['documento']).lower() != 'falta dato' else ''
                    
                    edit_nombre = st.text_input("Nombre", value=nombre_inicial, key="edit_empleado_nombre")
                    edit_apellido = st.text_input("Apellido", value=apellido_inicial, key="edit_empleado_apellido")
                    edit_email = st.text_input("Email (opcional)", value=email_inicial, key="edit_empleado_email")
                    edit_celular = st.text_input("Celular (opcional)", value=celular_inicial, key="edit_empleado_celular")
                    
                    # Manejar fecha de nacimiento
                    fecha_nacimiento_actual = None
                    if 'fecha_nacimiento' in empleado_row.index and empleado_row['fecha_nacimiento'] and str(empleado_row['fecha_nacimiento']).lower() != 'falta dato':
                        try:
                            if pd.notna(empleado_row['fecha_nacimiento']):
                                fecha_nacimiento_actual = datetime.strptime(str(empleado_row['fecha_nacimiento']), '%Y-%m-%d').date()
                        except:
                            try:
                                # Intentar otros formatos de fecha
                                fecha_nacimiento_actual = pd.to_datetime(empleado_row['fecha_nacimiento']).date()
                            except:
                                pass
                    
                    # Fecha de Nacimiento
                    edit_fecha_nacimiento = st.date_input(
                        "Fecha de Nacimiento", 
                        value=fecha_nacimiento_actual, 
                        min_value=date(1900, 1, 1),
                        max_value=date.today(),
                        key="edit_empleado_fecha_nacimiento"
                    )
                    
                with col2:
                    # Limpiar valores 'falta dato' al cargar - usar la misma lógica que en crear empleado
                    cargo_inicial = empleado_row['cargo'] if empleado_row['cargo'] and str(empleado_row['cargo']).lower() != 'falta dato' else ''
                    departamento_inicial = empleado_row['departamento'] if empleado_row['departamento'] and str(empleado_row['departamento']).lower() != 'falta dato' else ''
                    
                    edit_cargo = st.text_input("Cargo (opcional)", value=cargo_inicial, key="edit_empleado_cargo")
                    
                    # Obtener departamentos existentes para el selectbox
                    departamentos_existentes = get_departamentos_list()
                    
                    # Determinar el índice inicial del selectbox
                    if departamento_inicial and departamento_inicial in departamentos_existentes:
                        departamento_index = departamentos_existentes.index(departamento_inicial)
                    else:
                        departamento_index = 0 if departamentos_existentes else None
                    
                    # Selectbox para departamento
                    edit_departamento = st.selectbox(
                        "Departamento", 
                        options=departamentos_existentes,
                        index=departamento_index,
                        placeholder="Selecciona un departamento",
                        key="edit_select_departamento"
                    )
                    
                    # Manejar fecha de ingreso
                    try:
                        fecha_ingreso_actual = datetime.strptime(empleado_row['fecha_ingreso'], '%Y-%m-%d').date()
                    except:
                        fecha_ingreso_actual = datetime.now().date()
                    edit_fecha_ingreso = st.date_input("Fecha de Ingreso", value=fecha_ingreso_actual, key="edit_empleado_fecha_ingreso")
                    
                    edit_activo = st.checkbox("Empleado Activo", value=bool(empleado_row.get('activo', 1)), key="edit_empleado_activo")
                
                # Reemplazar la validación en la línea 133 (aproximadamente)
                if st.button("Guardar Cambios de Empleado", key="save_empleado_edit"):
                    # Validar campos obligatorios (igual que en agregar empleado)
                    nombre_valido = edit_nombre and edit_nombre.strip() != '' and edit_nombre.strip().lower() != 'falta dato'
                    apellido_valido = edit_apellido and edit_apellido.strip() != '' and edit_apellido.strip().lower() != 'falta dato'
                    departamento_valido = edit_departamento and edit_departamento.strip() != '' and edit_departamento.strip().lower() != 'falta dato'
                    fecha_ingreso_valida = edit_fecha_ingreso is not None
                    fecha_nacimiento_valida = edit_fecha_nacimiento is not None
                    
                    # Validar email (opcional pero si se proporciona debe ser válido)
                    email_valido = True
                    if edit_email and edit_email.strip() != '':
                        import re
                        patron_email = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                        email_valido = re.match(patron_email, edit_email.strip()) is not None
                        if not email_valido:
                            st.error("El formato del email no es válido.")
                    
                    # Verificar todos los campos obligatorios incluyendo fecha de nacimiento
                    if nombre_valido and apellido_valido and departamento_valido and fecha_ingreso_valida and fecha_nacimiento_valida and email_valido:
                        # Usar None (NULL) para campos vacíos - igual que en crear empleado
                        email_final = edit_email.strip() if edit_email and edit_email.strip() != '' else None
                        celular_final = edit_celular.strip() if edit_celular and edit_celular.strip() != '' else None
                        cargo_final = edit_cargo.strip() if edit_cargo and edit_cargo.strip() != '' else None
                        
                        fecha_nacimiento_str = edit_fecha_nacimiento.strftime('%Y-%m-%d')
                        fecha_ingreso_str = edit_fecha_ingreso.strftime('%Y-%m-%d')
                        activo_val = 1 if edit_activo else 0
                        
                        if update_empleado_nomina(empleado_id, edit_nombre, edit_apellido, email_final, celular_final,
                                                cargo_final, edit_departamento, fecha_ingreso_str, fecha_nacimiento_str, activo_val):
                            show_success_message("✅ Empleado actualizado exitosamente.", 3)
                        else:
                            st.error("Error al actualizar empleado. El celular puede ya existir para otro empleado.")
                    else:
                        # Mensaje de error actualizado para incluir fecha de nacimiento
                        campos_faltantes = []
                        if not nombre_valido:
                            campos_faltantes.append("Nombre")
                        if not apellido_valido:
                            campos_faltantes.append("Apellido")
                        if not departamento_valido:
                            campos_faltantes.append("Departamento")
                        if not fecha_ingreso_valida:
                            campos_faltantes.append("Fecha de Ingreso")
                        if not fecha_nacimiento_valida:
                            campos_faltantes.append("Fecha de Nacimiento")
                        
                        st.error(f"Los campos obligatorios son: Nombre, Apellido, Departamento, Fecha de Ingreso y Fecha de Nacimiento.")
        else:
            st.info("No hay empleados para editar.")
    
    # Formulario para eliminar empleado
    with st.expander("🗑️ Eliminar Empleado"):
        if not nomina_df.empty:
            empleado_ids = nomina_df['id'].tolist()
            empleado_names = [f"{row['nombre']} {row['apellido']} - {row['documento']}" for _, row in nomina_df.iterrows()]
            empleado_options = [f"{eid} - {ename}" for eid, ename in zip(empleado_ids, empleado_names)]
            
            selected_empleado_delete = st.selectbox("Seleccionar Empleado para Eliminar", 
                                                   options=empleado_options, key="select_empleado_delete")
            if selected_empleado_delete:
                empleado_id = int(selected_empleado_delete.split(' - ')[0])
                empleado_row = nomina_df[nomina_df['id'] == empleado_id].iloc[0]
                
                st.warning("¿Estás seguro de que deseas eliminar este empleado? Esta acción no se puede deshacer.")
                st.info(f"**Empleado a eliminar:** {empleado_row['nombre']} {empleado_row['apellido']} - {empleado_row['documento']}")
                
                if st.button("Eliminar Empleado", key="delete_empleado_btn", type="primary"):
                    if delete_empleado_nomina(empleado_id):
                        show_success_message(f"✅ Empleado '{empleado_row['nombre']} {empleado_row['apellido']}' eliminado exitosamente.", 1.5)
                    else:
                        st.error("Error al eliminar empleado.")
        else:
            st.info("No hay empleados para eliminar.")

def render_nomina_management(is_wizard=False):
    """Renderiza la gestión completa de nómina
    Args:
        is_wizard (bool): Si es True, muestra controles específicos para el asistente de configuración
    """
    st.subheader("Gestión de Nómina")
    
    # AGREGAR: Funcionalidad de carga de Excel para nómina
    st.subheader("📊 Importar Empleados desde Excel")
    
    from .utils import render_excel_uploader
    from .database import process_nomina_excel, get_connection
    
    # Verificar si se debe mostrar mensaje de éxito (NO limpiar archivo para mantener estabilidad de UI)
    if st.session_state.get("nomina_processed_success", False):
        st.session_state["nomina_processed_success"] = False
        
        # Recuperar estadísticas guardadas si existen
        stats = st.session_state.get("last_nomina_stats", {})
        
        success_count = stats.get('success_count', 0)
        duplicate_count = stats.get('duplicate_count', 0)
        filtered_inactive_count = stats.get('filtered_inactive_count', 0)
        error_count = stats.get('error_count', 0)
        
        # Mostrar resumen
        if success_count > 0:
            st.success(f"✅ {success_count} empleados procesados exitosamente")
        if duplicate_count > 0:
            st.warning(f"⚠️ {duplicate_count} empleados ya existían (duplicados omitidos)")
        if filtered_inactive_count > 0:
            st.info(f"ℹ️ {filtered_inactive_count} empleados inactivos fueron filtrados")
        if error_count > 0:
            st.error(f"❌ {error_count} errores durante el procesamiento")

    uploaded_file, excel_df, selected_sheet = render_excel_uploader(
        key="nomina_excel_upload",
        label="Selecciona un archivo Excel con datos de empleados (.xls o .xlsx)",
        expanded=False,
        enable_sheet_selection=True
    )
    
    # Determinar si mostrar el botón de siguiente
    show_next_btn = False
    if is_wizard:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM nomina")
        nomina_count = c.fetchone()[0]
        conn.close()
        
        if nomina_count > 0:
            show_next_btn = True
    
    # Lógica de renderizado de botones
    buttons_placeholder = st.empty()
    can_process = (uploaded_file is not None and excel_df is not None)
    process_btn = False
    
    with buttons_placeholder.container():
        if show_next_btn:
            # Usar siempre columnas para mantener estabilidad en el DOM y evitar duplicación visual
            col1, col2 = st.columns([1, 1])
            
            with col1:
                if can_process:
                    process_btn = st.button("🚀 Procesar y Cargar Empleados", key="process_nomina_excel")
                else:
                    # Placeholder vacío para mantener la estructura
                    st.empty()
                
            with col2:
                # Clave estable única para el botón "Siguiente"
                if st.button("Siguiente: Generar Usuarios ➡️", type="primary", key="continue_wizard_btn_stable"):
                    st.session_state.onboarding_step = 2
                    st.rerun()
        elif can_process:
            # Solo mostrar botón de procesar si no hay botón siguiente
            process_btn = st.button("🚀 Procesar y Cargar Empleados", key="process_nomina_excel")
            
    if process_btn:
        with st.spinner("Procesando archivo Excel de nómina..."):
            try:
                # La función ahora devuelve un diccionario con estadísticas
                stats = process_nomina_excel(excel_df)
                
                success_count = stats['success_count']
                error_count = stats['error_count']
                duplicate_count = stats['duplicate_count']
                filtered_inactive_count = stats['filtered_inactive_count']
                error_details = stats['error_details']
                duplicate_details = stats['duplicate_details']
                success_details = stats['success_details']
                
                # Mostrar resultados
                if success_count > 0:
                    st.success(f"✅ {success_count} empleados procesados exitosamente")
                    if success_details:
                        with st.expander("Ver empleados creados"):
                            for detail in success_details:
                                st.write(f"• {detail}")
                
                if duplicate_count > 0:
                    st.warning(f"⚠️ {duplicate_count} empleados ya existían (duplicados omitidos)")
                    if duplicate_details:
                        with st.expander("Ver empleados duplicados"):
                            for detail in duplicate_details:
                                st.write(f"• {detail}")
                
                if filtered_inactive_count > 0:
                    st.info(f"ℹ️ {filtered_inactive_count} empleados inactivos fueron filtrados")
                
                if error_count > 0:
                    st.error(f"❌ {error_count} errores durante el procesamiento")
                    if error_details:
                        with st.expander("Ver detalles de errores"):
                            for detail in error_details:
                                st.write(f"• {detail}")
                
                # NUEVO: Marcar para limpiar archivo en el próximo rerun si hubo procesamiento exitoso
                if success_count > 0 or duplicate_count > 0:
                    # Guardar estadísticas para mostrarlas después del rerun
                    st.session_state["last_nomina_stats"] = stats
                    st.session_state["nomina_processed_success"] = True
                    st.rerun()
                    
            except Exception as e:
                st.error(f"Error al procesar el archivo: {str(e)}")
    
    # Obtener datos de nómina
    nomina_df = get_nomina_dataframe_expanded()
    
    # Mostrar tabla de empleados
    if not nomina_df.empty:
        st.subheader("Lista de Empleados")
        
        # Seleccionar columnas para mostrar (incluyendo Edad y Antigüedad)
        columns_to_display = [
            'APELLIDO', 'NOMBRE', 'MAIL', 'Celular', 'Categoria', 'Funcion', 
            'Sector', 'Fecha ingreso', 'Fecha Nacimiento', 'Edad', 'Antigüedad'
        ]
        
        # Filtrar solo las columnas que existen en el DataFrame
        available_columns = [col for col in columns_to_display if col in nomina_df.columns]
        
        if available_columns:
            display_df = nomina_df[available_columns].copy()
            
            # Renombrar columnas para mejor visualización
            column_rename_map = {
                'APELLIDO': 'Apellido',
                'NOMBRE': 'Nombre', 
                'MAIL': 'Email',
                'Celular': 'Celular',
                'Categoria': 'Categoría',
                'Funcion': 'Función',
                'Sector': 'Departamento',
                'Fecha ingreso': 'Fecha Ingreso',
                'Fecha Nacimiento': 'Fecha Nacimiento',
                'Edad': 'Edad',
                'Antigüedad': 'Antigüedad'
            }
            
            # Solo renombrar las columnas que existen
            rename_dict = {k: v for k, v in column_rename_map.items() if k in display_df.columns}
            display_df = display_df.rename(columns=rename_dict)
            
            st.dataframe(display_df, use_container_width=True)
        else:
            st.warning("No se encontraron columnas válidas para mostrar.")
        
        # Mostrar estadísticas
        nomina_original_df = get_nomina_dataframe()
        if not nomina_original_df.empty and 'activo' in nomina_original_df.columns:
            empleados_activos = len(nomina_original_df[nomina_original_df['activo'] == 1])
            empleados_inactivos = len(nomina_original_df[nomina_original_df['activo'] == 0])
            
            # Crear columnas dinámicamente según si hay empleados inactivos
            if empleados_inactivos > 0:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Empleados", len(nomina_df))
                with col2:
                    st.metric("Empleados Activos", empleados_activos)
                with col3:
                    st.metric("Empleados Inactivos", empleados_inactivos)
            else:
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Empleados", len(nomina_df))
                with col2:
                    st.metric("Empleados Activos", empleados_activos)
                # No mostrar "Empleados Inactivos" cuando es 0
        else:
            st.metric("Total Empleados", len(nomina_df))
    
    # Formularios de gestión - usar el DataFrame original para los formularios
    nomina_original_df = get_nomina_dataframe()
    render_nomina_edit_delete_forms(nomina_original_df)