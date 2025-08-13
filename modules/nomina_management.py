import streamlit as st
import pandas as pd
from datetime import datetime
from .database import (
    get_nomina_dataframe, get_nomina_dataframe_expanded,
    add_empleado_nomina, update_empleado_nomina, delete_empleado_nomina
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
            new_departamento = st.text_input("Departamento", key="new_empleado_departamento")
            new_fecha_ingreso = st.date_input("Fecha de Ingreso", key="new_empleado_fecha_ingreso")
            new_fecha_nacimiento = st.date_input("Fecha de Nacimiento (opcional)", value=None, key="new_empleado_fecha_nacimiento")
        
        if st.button("Agregar Empleado", key="add_empleado_btn"):
            if new_nombre and new_apellido and new_celular and new_cargo and new_departamento and new_fecha_ingreso:
                fecha_nacimiento_str = new_fecha_nacimiento.strftime('%Y-%m-%d') if new_fecha_nacimiento else ''
                fecha_ingreso_str = new_fecha_ingreso.strftime('%Y-%m-%d')
                
                # Usar new_celular como documento (ya que el campo documento almacena el celular)
                if add_empleado_nomina(new_nombre, new_apellido, new_email, new_celular, 
                                     new_cargo, new_departamento, fecha_ingreso_str, fecha_nacimiento_str):
                    st.success(f"Empleado '{new_nombre} {new_apellido}' agregado exitosamente.")
                    st.rerun()
                else:
                    st.error("Error al agregar empleado. El celular puede ya existir.")
            else:
                st.error("Todos los campos obligatorios deben ser completados (Nombre, Apellido, Celular, Cargo, Departamento, Fecha de Ingreso).")
    
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
                    edit_nombre = st.text_input("Nombre", value=empleado_row['nombre'], key="edit_empleado_nombre")
                    edit_apellido = st.text_input("Apellido", value=empleado_row['apellido'], key="edit_empleado_apellido")
                    edit_email = st.text_input("Email", value=empleado_row['email'] or '', key="edit_empleado_email")
                    edit_celular = st.text_input("Celular", value=empleado_row['documento'], key="edit_empleado_celular")
                with col2:
                    edit_cargo = st.text_input("Cargo", value=empleado_row['cargo'], key="edit_empleado_cargo")
                    edit_departamento = st.text_input("Departamento", value=empleado_row['departamento'], key="edit_empleado_departamento")
                    
                    # Manejar fecha de ingreso
                    try:
                        fecha_ingreso_actual = datetime.strptime(empleado_row['fecha_ingreso'], '%Y-%m-%d').date()
                    except:
                        fecha_ingreso_actual = datetime.now().date()
                    edit_fecha_ingreso = st.date_input("Fecha de Ingreso", value=fecha_ingreso_actual, key="edit_empleado_fecha_ingreso")
                    
                    # Manejar fecha de nacimiento
                    fecha_nacimiento_actual = None
                    if empleado_row.get('fecha_nacimiento') and empleado_row['fecha_nacimiento']:
                        try:
                            fecha_nacimiento_actual = datetime.strptime(empleado_row['fecha_nacimiento'], '%Y-%m-%d').date()
                        except:
                            pass
                    edit_fecha_nacimiento = st.date_input("Fecha de Nacimiento (opcional)", value=fecha_nacimiento_actual, key="edit_empleado_fecha_nacimiento")
                    
                    edit_activo = st.checkbox("Empleado Activo", value=bool(empleado_row.get('activo', 1)), key="edit_empleado_activo")
                
                if st.button("Guardar Cambios de Empleado", key="save_empleado_edit"):
                    if edit_nombre and edit_apellido and edit_celular and edit_cargo and edit_departamento and edit_fecha_ingreso:
                        fecha_nacimiento_str = edit_fecha_nacimiento.strftime('%Y-%m-%d') if edit_fecha_nacimiento else ''
                        fecha_ingreso_str = edit_fecha_ingreso.strftime('%Y-%m-%d')
                        activo_val = 1 if edit_activo else 0
                        
                        # Usar edit_celular como documento (ya que el campo documento almacena el celular)
                        if update_empleado_nomina(empleado_id, edit_nombre, edit_apellido, edit_email, edit_celular,
                                                edit_cargo, edit_departamento, fecha_ingreso_str, fecha_nacimiento_str, activo_val):
                            st.success("Empleado actualizado exitosamente.")
                            st.rerun()
                        else:
                            st.error("Error al actualizar empleado. El celular puede ya existir para otro empleado.")
                    else:
                        st.error("Todos los campos obligatorios deben ser completados.")
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