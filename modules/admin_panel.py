import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import datetime
import calendar
from .database import (get_connection, get_registros_dataframe, get_tecnicos_dataframe,
                      get_clientes_dataframe, get_tipos_dataframe, get_modalidades_dataframe,
                      get_roles_dataframe, get_users_dataframe, get_tipos_dataframe_with_roles, 
                      get_grupos_dataframe, get_nomina_dataframe, test_connection,
                      get_registros_dataframe_with_date_filter, get_user_rol_id, 
                      get_user_registros_dataframe, get_user_info, add_empleado_nomina, 
                      update_empleado_nomina, empleado_existe, get_departamentos_list,
                      generate_users_from_nomina, generate_roles_from_nomina, 
                      get_or_create_tecnico, get_or_create_cliente, get_or_create_tipo_tarea, 
                      get_or_create_modalidad, registrar_actividad, add_client, add_grupo, 
                      get_roles_by_grupo, update_grupo_roles, get_registros_by_rol_with_date_filter,
                      get_tecnico_rol_id, get_or_create_grupo_with_department_association,
                      get_or_create_grupo_with_tecnico_department_association)
from .config import SYSTEM_ROLES, DEFAULT_VALUES, SYSTEM_LIMITS
from .nomina_management import render_nomina_edit_delete_forms
from .auth import create_user, validate_password, hash_password, is_2fa_enabled, unlock_user
from .utils import show_success_message, normalize_text, month_name_es
from .activity_logs import render_activity_logs

def render_admin_panel():
    """Renderiza el panel completo de administrador"""
    st.header("Panel de Administrador")
    tab_visualizacion, tab_gestion, tab_admin = st.tabs(["📊 Visualización de Datos", "⚙️ Gestión", "🛠️ Administración"])
    
    with tab_visualizacion:
        render_data_visualization()
    with tab_gestion:
        render_management_tabs()
    with tab_admin:
        render_admin_settings()

def render_data_visualization():
    """Renderiza la sección de visualización de datos organizada por roles"""
    from .admin_visualizations import render_data_visualization as _render_data_visualization
    return _render_data_visualization()

def render_role_visualizations(df, rol_id, rol_nombre):
    """Renderiza las visualizaciones específicas para un rol"""
    from .admin_visualizations import render_role_visualizations as _render_role_visualizations
    return _render_role_visualizations(df, rol_id, rol_nombre)

def render_client_hours_detail(horas_por_cliente):
    """Renderiza el detalle de horas por cliente"""
    st.subheader("Detalle de Horas por Cliente")
    
    # Crear un contenedor con borde para mejor visualización
    with st.container():
        # Dividir en columnas para mejor organización
        num_clientes = len(horas_por_cliente)
        if num_clientes > 0:
            # Crear columnas dinámicamente (máximo 3 por fila)
            cols_per_row = min(3, num_clientes)
            rows_needed = (num_clientes + cols_per_row - 1) // cols_per_row
            
            for row in range(rows_needed):
                cols = st.columns(cols_per_row)
                for col_idx in range(cols_per_row):
                    cliente_idx = row * cols_per_row + col_idx
                    if cliente_idx < num_clientes:
                        cliente_data = horas_por_cliente.iloc[cliente_idx]
                        with cols[col_idx]:
                            st.metric(
                                label=f"🏢 {cliente_data['cliente']}",
                                value=f"{cliente_data['tiempo']} hrs"
                            )

def render_excel_uploader(key="default_excel_uploader"):
    """Función reutilizable para cargar archivos Excel"""
    from .utils import render_excel_uploader as _render_excel_uploader
    uploaded_file, excel_df, selected_sheet = _render_excel_uploader(key=key)
    return uploaded_file, excel_df, selected_sheet

def render_records_management(df, role_id=None):
    """Renderiza la gestión de registros para administradores"""
    from .admin_records import render_records_management as _render_records_management
    return _render_records_management(df, role_id)

def render_admin_edit_form(registro_seleccionado, registro_id, role_id=None):
    """Renderiza el formulario de edición para administradores"""
    from .admin_records import render_admin_edit_form as _render_admin_edit_form
    return _render_admin_edit_form(registro_seleccionado, registro_id, role_id)

def render_admin_delete_form(registro_seleccionado, registro_id, role_id=None):
    """Renderiza el formulario de eliminación para administradores"""
    from .admin_records import render_admin_delete_form as _render_admin_delete_form
    return _render_admin_delete_form(registro_seleccionado, registro_id, role_id)

def render_management_tabs():
    """Renderiza las pestañas de gestión"""
    # Crear sub-pestañas para gestionar diferentes entidades
    subtab_usuarios, subtab_clientes, subtab_tipos, subtab_modalidades, subtab_roles, subtab_planning, subtab_grupos, subtab_nomina, subtab_marcas, subtab_registros = st.tabs([
        "👥 Usuarios", "🏢 Clientes", "📋 Tipos de Tarea", "🔄 Modalidades", "🏢 Departamentos", "📅 Planificación Semanal", "👪 Grupos", "🏠 Nómina", "🏷️ Marcas", "📝 Registros"
    ])
    
    # Gestión de Usuarios
    with subtab_usuarios:
        render_user_management()
    
    # Gestión de Clientes
    with subtab_clientes:
        # Agrupar vistas de clientes en subtabs
        tab_lista, tab_crud, tab_solicitudes = st.tabs(["📋 Lista", "⚙️ Gestión", "🟨 Solicitudes"])
        with tab_lista:
            render_client_management()
        with tab_crud:
            from .admin_clients import render_client_crud_management as _render_client_crud
            _render_client_crud()
        with tab_solicitudes:
            st.subheader("🟨 Solicitudes de Clientes")
            from .database import get_cliente_solicitudes_df, approve_cliente_solicitud, reject_cliente_solicitud, get_users_dataframe, check_client_duplicate
            req_df = get_cliente_solicitudes_df(estado='pendiente')
            if req_df.empty:
                st.info("No hay solicitudes pendientes.")
            else:
                users_df = get_users_dataframe()
                id_to_name = {int(r["id"]): f"{(r['nombre'] or '').strip()} {(r['apellido'] or '').strip()}".strip() for _, r in users_df.iterrows()}
                has_email = 'email' in req_df.columns
                has_cuit = 'cuit' in req_df.columns
                has_celular = 'celular' in req_df.columns
                has_web = 'web' in req_df.columns
                has_tipo = 'tipo' in req_df.columns
                st.markdown(
                    """
                    <style>
                      .req-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 10px 0 16px; }
                      .req-card { background: #111827; border: 1px solid #374151; border-radius: 12px; padding: 14px; }
                      .req-title { font-weight: 600; color: #9ca3af; margin-bottom: 6px; }
                      .req-value { color: #e5e7eb; }
                      @media (max-width: 768px) { .req-grid { grid-template-columns: 1fr; } }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )
                for _, r in req_df.iterrows():
                    rid = int(r["id"])
                    requester = id_to_name.get(int(r["requested_by"]), "Usuario")
                    with st.expander(f"{r['nombre']} — {r['organizacion'] or ''} ({requester})"):
                        email_val = r["email"] if has_email else None
                        cuit_val = r["cuit"] if has_cuit else None
                        celular_val = r["celular"] if has_celular else None
                        web_val = r["web"] if has_web else None
                        tipo_val = r["tipo"] if has_tipo else None
                        org_card = (
                            f"""
                              <div class='req-card'>
                                <div class='req-title'>Organización</div>
                                <div class='req-value'>{(r['organizacion'] or '-')}</div>
                              </div>
                            """
                        ) if (str(r.get('organizacion') or '').strip()) else ""
                        web_html = (
                            (f"<a href='{str(web_val)}' target='_blank'>{str(web_val)}</a>")
                            if str(web_val or '').strip() else '-'
                        )
                        grid_html = (
                            f"""
                            <div class='req-grid'>
                              <div class='req-card'>
                                <div class='req-title'>Nombre</div>
                                <div class='req-value'>{(r['nombre'] or '')}</div>
                              </div>
                              {org_card}
                              <div class='req-card'>
                                <div class='req-title'>Teléfono</div>
                                <div class='req-value'>{(r['telefono'] or '-')}</div>
                              </div>
                              <div class='req-card'>
                                <div class='req-title'>Email</div>
                                <div class='req-value'>{(email_val or '-')}</div>
                              </div>
                              <div class='req-card'>
                                <div class='req-title'>CUIT</div>
                                <div class='req-value'>{(cuit_val or '-')}</div>
                              </div>
                              <div class='req-card'>
                                <div class='req-title'>Celular</div>
                                <div class='req-value'>{(celular_val or '-')}</div>
                              </div>
                              <div class='req-card'>
                                <div class='req-title'>Web</div>
                                <div class='req-value'>{web_html}</div>
                              </div>

                            </div>
                            """
                        )
                        st.markdown(grid_html, unsafe_allow_html=True)
                        cols = st.columns([1,1,4])
                        with cols[0]:
                            if st.button("Aprobar", key=f"approve_client_req_{rid}"):
                                success, msg = approve_cliente_solicitud(rid)
                                if success:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(f"No se pudo aprobar la solicitud: {msg}")
                        with cols[1]:
                            if st.button("Rechazar", key=f"reject_client_req_{rid}"):
                                if reject_cliente_solicitud(rid):
                                    st.info("Solicitud rechazada.")
                                    st.rerun()
                                else:
                                    st.error("No se pudo rechazar la solicitud.")

    
    
    # Gestión de Tipos de Tarea
    with subtab_tipos:
        render_task_type_management()
    
    # Gestión de Modalidades
    with subtab_modalidades:
        render_modality_management()
        
    # Gestión de Departamentos
    with subtab_roles:
        render_department_management()
    
    # 📅 Planificación Semanal (nuevo)
    with subtab_planning:
        from .admin_planning import render_planning_management as _render_planning_management
        _render_planning_management()
    
    # Gestión de Grupos
    with subtab_grupos:
        render_grupo_management()
        
    # Gestión de Nómina
    with subtab_nomina:
        render_nomina_management()
    
    # Gestión de Marcas
    with subtab_marcas:
        from .admin_brands import render_brand_management as _render_brand_management
        _render_brand_management()
        
    # Registros de actividad
    with subtab_registros:
        try:
            render_activity_logs()
        except Exception as e:
            from .utils import log_app_error
            log_app_error(e, module="admin_panel", function="render_management_tabs")
            st.error(f"Error al mostrar los registros de actividad: {str(e)}")
            st.error(f"Error al mostrar los registros de actividad: {str(e)}")
def render_user_management():
    """Renderiza la gestión de usuarios"""
    from .admin_users import render_user_management as _render_user_management
    return _render_user_management()

def render_user_edit_form(users_df, roles_df):
    """Renderiza el formulario de edición de usuarios"""
    from .admin_users import render_user_edit_form as _render_user_edit_form
    return _render_user_edit_form(users_df, roles_df)

def render_user_delete_form(users_df):
    """Renderiza el formulario de eliminación de usuarios"""
    from .admin_users import render_user_delete_form as _render_user_delete_form
    return _render_user_delete_form(users_df)
def delete_user(user_id, username):
    """Elimina un usuario y sus registros asociados"""
    from .admin_users import delete_user as _delete_user
    return _delete_user(user_id, username)

def render_client_management():
    """Renderiza la gestión de clientes"""
    from .admin_clients import render_client_management as _render_client_management
    return _render_client_management()

def render_client_edit_delete_forms(clients_df):
    """Renderiza formularios de edición y eliminación de clientes"""
    from .admin_clients import render_client_edit_delete_forms as _render_client_edit_delete_forms
    return _render_client_edit_delete_forms(clients_df)

def clean_duplicate_task_types():
    """Limpia tipos de tarea duplicados manteniendo solo uno de cada tipo"""
    from .admin_task_types import clean_duplicate_task_types as _clean_duplicate_task_types
    return _clean_duplicate_task_types()

def render_task_type_management():
    """Renderiza la gestión de tipos de tarea"""
    from .admin_task_types import render_task_type_management as _render_task_type_management
    return _render_task_type_management()

def render_task_type_edit_delete_forms(tipos_df, roles_df):
    """Renderiza formularios de edición y eliminación de tipos de tarea"""
    from .admin_task_types import render_task_type_edit_delete_forms as _render_task_type_edit_delete_forms
    return _render_task_type_edit_delete_forms(tipos_df, roles_df)

def render_modality_management():
    """Renderiza la gestión de modalidades"""
    from .admin_modalities import render_modality_management as _render_modality_management
    return _render_modality_management()

def render_modality_edit_delete_forms(modalidades_df):
    """Renderiza formularios de edición y eliminación de modalidades"""
    from .admin_modalities import render_modality_edit_delete_forms as _render_modality_edit_delete_forms
    return _render_modality_edit_delete_forms(modalidades_df)

def render_department_management():
    """Renderiza la gestión de departamentos"""
    from .admin_departments import render_department_management as _render_department_management
    return _render_department_management()

def render_grupo_management():
    """Renderiza la gestión de grupos"""
    from .admin_groups import render_grupo_management as _render_grupo_management
    return _render_grupo_management()

def render_nomina_management():
    """Renderiza la gestión de nómina"""
    from .nomina_management import render_nomina_management as _render_nomina_management
    return _render_nomina_management()

def process_excel_data(excel_df):
    """Procesa y carga datos desde Excel con control de duplicados y estandarización"""
    import calendar
    import openpyxl  # Importar explícitamente openpyxl
    from datetime import datetime
    import unicodedata
    from .database import get_or_create_tecnico, get_or_create_cliente, get_or_create_tipo_tarea, get_or_create_modalidad, get_or_create_grupo_with_department_association
    import streamlit as st

    # Función auxiliar para verificar si un valor está vacío o es inválido
    def is_empty_or_invalid(value):
        """Verifica si un valor está vacío, es None, NaN o contiene solo espacios"""
        if value is None:
            return True
        if pd.isna(value):
            return True
        if str(value).strip() == '':
            return True
        return False

    # Verificar si existen usuarios no administradores antes de procesar
    conn = get_connection()
    c = conn.cursor()
    
    # Contar usuarios que no sean administradores
    c.execute("SELECT COUNT(*) FROM usuarios WHERE rol_id != 1")  # rol_id 1 es admin
    non_admin_users = c.fetchone()[0]
    
    if non_admin_users == 0:
        st.warning("⚠️ No existen usuarios en el sistema para asignar los registros.")
        conn.close()
        return 0, 0, 0
    
    # Obtener el usuario actual que está cargando la planilla
    current_user_id = st.session_state.get('user_id')

    # Función para normalizar nombres de columnas removiendo acentos y caracteres especiales
    def normalize_column_name(col):
        col = col.strip()
        # Remover acentos y caracteres especiales
        col = unicodedata.normalize('NFD', col)
        col = ''.join(char for char in col if unicodedata.category(char) != 'Mn')
        return col
    
    # Normalizar nombres de columnas del Excel
    normalized_columns = [normalize_column_name(col) for col in excel_df.columns]
    
    # Mapeo de columnas esperadas (normalizadas)
    column_mapping_normalized = {
        'Fecha': 'fecha',
        'Tecnico': 'tecnico',  # Sin acento
        'Cliente': 'cliente',
        'Tipo tarea': 'tipo_tarea',
        'Modalidad': 'modalidad',
        'N° de Ticket': 'numero_ticket',
        'Tiempo': 'tiempo',
        'Breve Descripcion': 'tarea_realizada',  # Sin acento
        'Sector': 'grupo',
        'Equipo': 'grupo'
    }
    
    # Validar que el DataFrame tenga las columnas requeridas (usando versiones normalizadas)
    required_columns_normalized = ['Fecha', 'Tecnico', 'Cliente', 'Tipo tarea', 'Modalidad']
    missing_columns = []
    
    for req_col in required_columns_normalized:
        if req_col not in normalized_columns:
            # Buscar la columna original correspondiente para mostrar en el error
            original_col = None
            for orig, norm in zip(original_columns, normalized_columns):
                if norm == req_col:
                    original_col = orig
                    break
            if not original_col:
                # Si no encontramos la columna, usar el nombre normalizado
                missing_columns.append(req_col)
    
    if missing_columns:
        st.error(f"❌ La planilla no tiene el formato correcto. Faltan las siguientes columnas: {', '.join(missing_columns)}")
        st.info("📋 **Formato esperado de la planilla:**")
        st.info("• Fecha")
        st.info("• Técnico (puede ser 'Tecnico' sin acento)")
        st.info("• Cliente")
        st.info("• Tipo tarea")
        st.info("• Modalidad")
        st.info("• N° de Ticket (opcional)")
        st.info("• Tiempo (opcional)")
        st.info("• Breve Descripción (opcional, puede ser sin acento)")
        st.info("• Sector o Equipo (opcional)")
        return 0, 0, 0
    
    # Crear DataFrame con columnas normalizadas
    excel_df_normalized = excel_df.copy()
    excel_df_normalized.columns = normalized_columns
    
    # Aplicar mapeo de columnas
    excel_df_mapped = excel_df_normalized.rename(columns=column_mapping_normalized)
    
    # Limpiar DataFrame: eliminar filas con fechas vacías
    excel_df_mapped = excel_df_mapped.dropna(subset=['fecha'])
    excel_df_mapped = excel_df_mapped[excel_df_mapped['fecha'] != '']
    
    if excel_df_mapped.empty:
        st.warning("No hay datos válidos para procesar después de filtrar fechas vacías.")
        return 0, 0, 0
    
    # Crear DataFrame con columnas normalizadas
    excel_df_normalized = excel_df.copy()
    excel_df_normalized.columns = normalized_columns
    
    # Aplicar mapeo de columnas
    excel_df_mapped = excel_df_normalized.rename(columns=column_mapping_normalized)
    
    # Limpiar DataFrame: eliminar filas con fechas vacías
    excel_df_mapped = excel_df_mapped.dropna(subset=['fecha'])
    excel_df_mapped = excel_df_mapped[excel_df_mapped['fecha'] != '']
    
    if excel_df_mapped.empty:
        st.warning("No hay datos válidos para procesar después de filtrar fechas vacías.")
        conn.close()
        return 0, 0, 0
    
    success_count = 0
    error_count = 0
    duplicate_count = 0
    created_entities = {
        'tecnicos': set(),
        'clientes': set(),
        'tipos_tarea': set(),
        'modalidades': set(),
        'grupos': set()  # Agregar grupos a las entidades creadas
    }
    
    # Nuevo: Registro de errores por tipo
    error_types = {
        'fecha_invalida': 0,
        'tecnico_vacio': 0,
        'cliente_vacio': 0,
        'tipo_tarea_vacio': 0,
        'modalidad_vacia': 0,
        'entidad_error': 0,
        'otros_errores': 0
    }
    
    # Mapear nombres de columnas de tu formato al formato esperado
    column_mapping = {
        'Fecha': 'fecha',
        'Técnico': 'tecnico', 
        'Cliente': 'cliente',
        'Tipo tarea': 'tipo_tarea',
        'Modalidad': 'modalidad',
        'N° de Ticket': 'numero_ticket',
        'Tiempo': 'tiempo',
        'Breve Descripción': 'tarea_realizada',
        'Sector': 'grupo',  # Mapeo existente para Sector
        'Equipo': 'grupo'   # Nuevo mapeo para Equipo
    }
    
    # Normalización más robusta de nombres de columnas
    import unicodedata
    
    def normalize_column_name(col):
        col = col.strip()
        return col
    
    excel_df.columns = [normalize_column_name(col) for col in excel_df.columns]
    
    # Renombrar columnas para que coincidan con el formato esperado
    excel_df_mapped = excel_df.rename(columns=column_mapping)
    
    # Obtener entidades existentes para evitar duplicados
    c.execute("SELECT nombre FROM tecnicos")
    existing_tecnicos = {row[0] for row in c.fetchall()}
    
    c.execute("SELECT nombre FROM clientes")
    existing_clientes = {row[0] for row in c.fetchall()}
    
    c.execute("SELECT descripcion FROM tipos_tarea")
    existing_tipos = {row[0] for row in c.fetchall()}
    
    c.execute("SELECT descripcion FROM modalidades_tarea")
    existing_modalidades = {row[0] for row in c.fetchall()}
    
    for index, row in excel_df_mapped.iterrows():
        try:
            # Validación temprana: omitir filas con campos críticos vacíos (sin reportar error)
            if (is_empty_or_invalid(row['fecha']) or 
                is_empty_or_invalid(row['tecnico']) or 
                is_empty_or_invalid(row['cliente']) or 
                is_empty_or_invalid(row['tipo_tarea']) or 
                is_empty_or_invalid(row['modalidad'])):
                continue  # Omitir silenciosamente
            
            # Estandarizar fecha
            fecha_str = str(row['fecha'])
            try:
                if '/' in fecha_str:
                    # Normalizar formato de fecha para manejar días con un solo dígito
                    partes = fecha_str.split('/')
                    # Asegurar que el día y mes tengan dos dígitos
                    if len(partes) == 3:
                        # Si el año tiene 2 dígitos
                        if len(partes[2]) == 2:
                            fecha_str = f"{int(partes[0]):02d}/{int(partes[1]):02d}/{partes[2]}"
                            fecha_obj = datetime.strptime(fecha_str, '%d/%m/%y')
                        else:  # Si el año tiene 4 dígitos
                            fecha_str = f"{int(partes[0]):02d}/{int(partes[1]):02d}/{partes[2]}"
                            fecha_obj = datetime.strptime(fecha_str, '%d/%m/%Y')
                    else:
                        # Si el formato no es el esperado, intentar con pandas
                        fecha_obj = pd.to_datetime(fecha_str)
                else:
                    fecha_obj = pd.to_datetime(fecha_str)
                fecha_formateada = fecha_obj.strftime('%d/%m/%y')
            except Exception as e:
                # Solo reportar error si la fecha no está vacía
                if not is_empty_or_invalid(row['fecha']):
                    error_types['fecha_invalida'] += 1
                    error_count += 1
                continue  # Omitir filas con fechas que no se pueden procesar
            
            # Obtener y crear entidades automáticamente (normalizadas)
            tecnico = ' '.join(str(row['tecnico']).strip().split()).title()
            cliente = ' '.join(str(row['cliente']).strip().split()).title()
            tipo_tarea = ' '.join(str(row['tipo_tarea']).strip().split()).title()
            modalidad = ' '.join(str(row['modalidad']).strip().split()).title()
            
            # Verificar si existe la columna grupo y obtener su valor (normalizado)
            grupo = "General"  # Valor predeterminado (primera letra mayúscula)
            usar_grupo_general = True  # Flag para saber si usar asociación general
            
            if 'grupo' in row and not is_empty_or_invalid(row['grupo']):
                grupo_valor = str(row['grupo']).strip()
                # Verificar que no sea un valor vacío o inválido
                if not is_empty_or_invalid(grupo_valor):
                    grupo = ' '.join(grupo_valor.split()).title()
                    usar_grupo_general = False
            
            # Usar get_or_create para obtener IDs (creando si no existen)
            try:
                id_tecnico = get_or_create_tecnico(tecnico, conn)
                if tecnico not in existing_tecnicos:
                    created_entities['tecnicos'].add(tecnico)
                    
                id_cliente = get_or_create_cliente(cliente, conn)
                if cliente not in existing_clientes:
                    created_entities['clientes'].add(cliente)
                    
                # Pasar el nombre del empleado (técnico) para asociación automática
                id_tipo = get_or_create_tipo_tarea(tipo_tarea, conn, empleado_nombre=tecnico)
                if tipo_tarea not in existing_tipos:
                    created_entities['tipos_tarea'].add(tipo_tarea)
                    
                id_modalidad = get_or_create_modalidad(modalidad, conn)
                if modalidad not in existing_modalidades:
                    created_entities['modalidades'].add(modalidad)
                    
                # Crear grupo con lógica diferente según si es "General" o específico
                if usar_grupo_general:
                    # Para grupo "General", usar la función original que asocia al usuario que sube la planilla
                    from .database import get_or_create_grupo_with_department_association
                    current_user_id = st.session_state.get('user_id')
                    id_grupo = get_or_create_grupo_with_department_association(grupo, current_user_id, conn)
                else:
                    # Para grupos específicos, usar la nueva función que asocia al departamento del técnico
                    id_grupo = get_or_create_grupo_with_tecnico_department_association(grupo, tecnico, conn)
                
                # Verificar si el grupo es nuevo para agregarlo a las entidades creadas
                c.execute("SELECT COUNT(*) FROM grupos WHERE nombre = %s", (grupo,))
                grupo_count = c.fetchone()[0]
                if grupo_count == 1:  # Si solo hay 1, significa que se acaba de crear
                    created_entities['grupos'].add(grupo)
                    
            except Exception as e:
                # Solo incrementar error si no es un problema de campos vacíos
                if not (is_empty_or_invalid(tecnico) or is_empty_or_invalid(cliente) or 
                       is_empty_or_invalid(tipo_tarea) or is_empty_or_invalid(modalidad)):
                    error_types['entidad_error'] += 1
                    error_count += 1
                continue
            
            # Validar otros campos (normalizados)
            tarea_realizada = ' '.join(str(row['tarea_realizada']).strip().split()) if not is_empty_or_invalid(row.get('tarea_realizada')) else 'N/A'
            numero_ticket = str(row['numero_ticket']).strip() if not is_empty_or_invalid(row.get('numero_ticket')) else 'N/A'
            
            # Validar tiempo (acepta "1,5", "1.5", "1,5 hs")
            raw_tiempo = row.get('tiempo')
            if is_empty_or_invalid(raw_tiempo):
                tiempo = 0.0
            else:
                try:
                    tiempo_str = str(raw_tiempo).strip().lower()
                    # Mantener solo dígitos y separadores decimal
                    tiempo_str = ''.join(ch for ch in tiempo_str if ch.isdigit() or ch in [',', '.'])
                    tiempo_str = tiempo_str.replace(',', '.')
                    tiempo = round(float(tiempo_str), 2)
                except Exception:
                    tiempo = 0.0
            descripcion = ' '.join(str(row.get('descripcion', '')).strip().split()) if not is_empty_or_invalid(row.get('descripcion')) else ''
            # Validar que el mes sea válido antes de convertir
            mes_num = fecha_obj.month
            if mes_num is None or mes_num < 1 or mes_num > 12:
                from datetime import datetime
                mes_num = datetime.now().month
            # Guardar número de mes; el nombre se resolverá al leer
            mes = mes_num
            # Verificar duplicados
            c.execute('''
                SELECT id, grupo FROM registros 
                WHERE fecha = %s AND id_tecnico = %s AND id_cliente = %s AND id_tipo = %s
                AND id_modalidad = %s AND tarea_realizada = %s AND tiempo = %s
            ''', (fecha_formateada, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, tiempo))
            
            registro_existente = c.fetchone()
            
            if registro_existente:
                registro_id, grupo_actual = registro_existente
                
                # Actualizar el grupo si ha cambiado
                if grupo != grupo_actual:
                    c.execute('''
                        UPDATE registros SET grupo = %s WHERE id = %s
                    ''', (grupo, registro_id))
                
                duplicate_count += 1
                continue
            
            # Insertar registro incluyendo el campo grupo
            c.execute('''
                INSERT INTO registros 
                (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
                 numero_ticket, tiempo, descripcion, mes, usuario_id, grupo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (fecha_formateada, id_tecnico, id_cliente, id_tipo, id_modalidad, 
                  tarea_realizada, numero_ticket, tiempo, descripcion, mes, None, grupo))
            
            success_count += 1
            
        except Exception as e:
            # Solo reportar errores que no sean por campos vacíos
            if not (is_empty_or_invalid(row.get('fecha')) and 
                   is_empty_or_invalid(row.get('tecnico')) and 
                   is_empty_or_invalid(row.get('cliente')) and 
                   is_empty_or_invalid(row.get('tipo_tarea')) and 
                   is_empty_or_invalid(row.get('modalidad'))):
                error_types['otros_errores'] += 1
                error_count += 1
            continue

    # Confirmar transacción y cerrar conexión
    conn.commit()
    conn.close()
    
    # Retornar los contadores de procesamiento
    return success_count, error_count, duplicate_count


def auto_assign_records_by_technician(conn):
    """Asigna automáticamente registros a usuarios basándose en el nombre del técnico"""
    from .admin_assignments import fix_existing_records_assignment_improved
    
    # Usar la función mejorada de asignación con umbral por defecto
    registros_asignados = fix_existing_records_assignment_improved(conn, umbral_minimo=70)
    
    return registros_asignados


def render_admin_settings():
    from .config import POSTGRES_CONFIG, UPLOADS_DIR, PROJECT_UPLOADS_DIR, update_env_values, reload_env
    st.subheader("Administración")
    subtab_conexiones, = st.tabs(["🔌 Conexiones"])

    with subtab_conexiones:
        with st.form("admin_connections_form", clear_on_submit=False):
            st.markdown("**PostgreSQL**")
            host = st.text_input("Host", value=POSTGRES_CONFIG['host'])
            port = st.text_input("Puerto", value=str(POSTGRES_CONFIG['port']))
            db   = st.text_input("Base de datos", value=POSTGRES_CONFIG['database'])
            user = st.text_input("Usuario", value=POSTGRES_CONFIG['user'])
            pwd  = st.text_input("Contraseña", value=POSTGRES_CONFIG['password'], type="password")

            st.divider()
            st.markdown("**Rutas de almacenamiento**")
            uploads = st.text_input("Carpeta base de uploads (UPLOADS_DIR)", value=UPLOADS_DIR)
            proj_uploads = st.text_input("Carpeta de proyectos (PROJECT_UPLOADS_DIR)", value=PROJECT_UPLOADS_DIR)

            submitted = st.form_submit_button("Guardar configuración", type="primary")

        if submitted:
            ok = update_env_values({
                "POSTGRES_HOST": host,
                "POSTGRES_PORT": port,
                "POSTGRES_DB": db,
                "POSTGRES_USER": user,
                "POSTGRES_PASSWORD": pwd,
                "UPLOADS_DIR": uploads,
                "PROJECT_UPLOADS_DIR": proj_uploads,
            })
            if ok:
                reload_env()
                st.success("Configuración guardada en .env. Reinicia/recarga la app para aplicar conexiones.")
            else:
                st.error("No se pudo escribir .env. Revisa permisos de archivo.")
