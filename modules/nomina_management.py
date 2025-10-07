import streamlit as st
import pandas as pd
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