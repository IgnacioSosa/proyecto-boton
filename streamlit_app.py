import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import calendar
import time
import backend
import sqlite3  # Agregar esta línea

# Configuración inicial de la página
st.set_page_config(page_title="Sistema de Registro de Horas", layout="wide")

# Inyectar CSS para mejorar la visibilidad de los menús desplegables
st.markdown("""
<style>
    /* Contenedor del menú desplegable (popover) */
    div[data-baseweb="popover"] ul {
        background-color: #262730;
        border: 1px solid #F63366;
    }

    /* Opciones individuales en el menú */
    li[role="option"] {
        background-color: #262730;
        color: #FAFAFA;
    }

    /* Opción al pasar el mouse por encima (hover) */
    li[role="option"]:hover {
        background-color: #F63366;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Función principal de la aplicación
def main():
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
        st.session_state.is_admin = False

    if st.session_state.user_id is None:
        tab1, tab2 = st.tabs(["Login", "Registro"])
        
        with tab1:
            st.header("Login")
            username = st.text_input("Usuario", key="login_username")
            password = st.text_input("Contraseña", type="password", key="login_password")
            if st.button("Ingresar"):
                user_id, is_admin = backend.login_user(username, password)
    
                # Alrededor de la línea 50, después de iniciar sesión exitosamente
                if user_id:
                    st.session_state.user_id = user_id
                    st.session_state.is_admin = is_admin
                    st.session_state.mostrar_perfil = False
                    
                    # Limpiar el caché de usuarios para forzar una recarga fresca
                    if is_admin and 'users_df_cache' in st.session_state:
                        del st.session_state['users_df_cache']
                    
                    st.success("Login exitoso!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos o la cuenta está pendiente de activación por un administrador.")

        with tab2:
            st.header("Registro")
            new_username = st.text_input("Usuario", key="reg_username")
            new_email = st.text_input("Correo Electrónico", key="reg_email")
            new_password = st.text_input("Contraseña", type="password", key="reg_password")
            
            # Agregar información sobre los requisitos de contraseña
            st.info("La contraseña debe tener al menos 8 caracteres, una letra mayúscula, una letra minúscula, un número y un carácter especial.")
            
            if st.button("Registrarse"):
                if new_username and new_password and new_email:
                    success, messages = backend.create_user(new_username, new_password, email=new_email)
                    if success:
                        st.success(messages[0])
                    else:
                        for message in messages:
                            st.error(message)
                else:
                    st.error("Usuario, correo electrónico y contraseña son obligatorios.")

    else:
        # Función para desloguear y limpiar el estado
        def logout():
            st.session_state.user_id = None
            st.session_state.is_admin = False
            st.session_state.mostrar_perfil = False

        # Obtener información del usuario
        user_info = backend.get_user_info(st.session_state.user_id)
        
        # Si el usuario fue eliminado de la BD mientras estaba logueado, lo deslogueamos.
        if user_info is None:
            st.session_state.user_id = None
            st.session_state.is_admin = False
            st.rerun()

        nombre_actual = user_info['nombre']
        apellido_actual = user_info['apellido']
        current_username = user_info['username']
        email_actual = user_info['email']
        nombre_completo_usuario = f"{nombre_actual} {apellido_actual}".strip()

        # Barra lateral para perfil y cierre de sesión
        with st.sidebar:
            st.sidebar.button("Cerrar Sesión", on_click=logout, type="primary", use_container_width=True)
            st.header("Editar Perfil")
            with st.expander("Datos Personales"):
                nuevo_nombre = st.text_input("Nombre", value=nombre_actual, key="sidebar_nombre")
                nuevo_apellido = st.text_input("Apellido", value=apellido_actual, key="sidebar_apellido")
                nuevo_email = st.text_input("Correo Electrónico", value=email_actual, key="sidebar_email")

            with st.expander("Cambiar Contraseña"):
                nueva_password = st.text_input("Nueva Contraseña", type="password", key="new_pass_sidebar")
                confirmar_password = st.text_input("Confirmar Nueva Contraseña", type="password", key="confirm_pass_sidebar")
                st.info("La contraseña debe tener al menos 8 caracteres, una letra mayúscula, una letra minúscula, un número y un carácter especial.")

            if st.button("Guardar Cambios", key="save_sidebar_profile", use_container_width=True):
                # Actualizar perfil
                backend.update_user_profile(st.session_state.user_id, nuevo_nombre, nuevo_apellido, nuevo_email)
                
                # Actualizar contraseña si se proporcionó
                if nueva_password:
                    if nueva_password == confirmar_password:
                        success, messages = backend.update_user_password(st.session_state.user_id, nueva_password)
                        if success:
                            st.toast(messages[0], icon="🔑")
                        else:
                            for message in messages:
                                st.error(message)
                    else:
                        st.error("Las contraseñas no coinciden.")
                
                st.toast("Perfil guardado.", icon="✅")
                st.rerun()

        if st.session_state.is_admin:
            st.header("Panel de Administrador")
            
            # Crear pestañas principales del panel de administrador
            tab_visualizacion, tab_gestion = st.tabs(["📊 Visualización de Datos", "⚙️ Gestión"])
            
            with tab_visualizacion:
                df = backend.get_all_registros()

                if not df.empty:
                    # Calcular horas totales por cliente
                    horas_por_cliente = df.groupby('cliente')['tiempo'].sum().reset_index()
                    # Calcular horas totales por tipo de tarea
                    horas_por_tipo = df.groupby('tipo_tarea')['tiempo'].sum().reset_index()
                    # Calcular horas totales por técnico
                    horas_por_tecnico = df.groupby('tecnico')['tiempo'].sum().reset_index()
                    
                    # Crear pestañas para los diferentes gráficos
                    tab_clientes, tab_tipos, tab_tecnicos, tab_datos = st.tabs(["Clientes", "Tipos de Tarea", "Técnicos", "Tabla de Registros"])
                    
                    with tab_clientes:
                        # Gráfico de torta por cliente
                        fig1 = px.pie(df, names='cliente', title='Distribución por Cliente')
                        st.plotly_chart(fig1, use_container_width=True)
                        
                        # Listado detallado de horas por cliente con mejor presentación
                        st.subheader("Detalle de Horas por Cliente")
                        
                        # Crear un contenedor con borde para mejor visualización
                        with st.container():
                            # Dividir en columnas para mejor organización
                            num_clientes = len(horas_por_cliente)
                            if num_clientes > 0:
                                # Crear columnas dinámicamente (máximo 3 por fila)
                                cols_per_row = min(3, num_clientes)
                                
                                for i in range(0, num_clientes, cols_per_row):
                                    cols = st.columns(cols_per_row)
                                    
                                    for j in range(cols_per_row):
                                        if i + j < num_clientes:
                                            row = horas_por_cliente.iloc[i + j]
                                            with cols[j]:
                                                # Usar métricas para una presentación más limpia
                                                st.metric(
                                                    label=f"🏢 {row['cliente']}",
                                                    value=f"{row['tiempo']:.1f} horas"
                                                )
                            else:
                                st.info("No hay datos de clientes para mostrar.")
                    
                    with tab_tipos:
                        # Gráfico de torta por tipo de tarea
                        fig2 = px.pie(df, names='tipo_tarea', title='Distribución por Tipo de Tarea')
                        st.plotly_chart(fig2, use_container_width=True)
                        
                        # Listado detallado de horas por tipo de tarea con mejor presentación
                        st.subheader("Detalle de Horas por Tipo de Tarea")
                        
                        # Crear un contenedor con borde para mejor visualización
                        with st.container():
                            # Dividir en columnas para mejor organización
                            num_tipos = len(horas_por_tipo)
                            if num_tipos > 0:
                                # Crear columnas dinámicamente (máximo 2 por fila para tipos de tarea que pueden tener nombres más largos)
                                cols_per_row = min(2, num_tipos)
                                
                                for i in range(0, num_tipos, cols_per_row):
                                    cols = st.columns(cols_per_row)
                                    
                                    for j in range(cols_per_row):
                                        if i + j < num_tipos:
                                            row = horas_por_tipo.iloc[i + j]
                                            with cols[j]:
                                                # Usar métricas para una presentación más limpia
                                                st.metric(
                                                    label=f"⚙️ {row['tipo_tarea']}",
                                                    value=f"{row['tiempo']:.1f} horas"
                                                )
                            else:
                                st.info("No hay datos de tipos de tarea para mostrar.")
                    
                    # Continuar con las otras pestañas de visualización...
                    # (El resto del código de visualización se mantendría igual pero usando las funciones del backend)

            with tab_gestion:
                # Crear pestañas para las diferentes secciones de gestión
                tab_clientes, tab_tipos, tab_tecnicos, tab_roles, tab_registros = st.tabs(["Clientes", "Tipos de Tarea", "Técnicos", "Roles", "Tabla de Registros"])
                
                with tab_clientes:
                    st.subheader("Gestión de Clientes")
                    # Formulario para agregar nuevo cliente
                    with st.form("form_nuevo_cliente"):
                        nombre_cliente = st.text_input("Nombre del Cliente")
                        submitted = st.form_submit_button("Agregar Cliente")
                        
                        if submitted and nombre_cliente:
                            conn = sqlite3.connect('trabajo.db')
                            c = conn.cursor()
                            c.execute("INSERT INTO clientes (nombre) VALUES (?)", (nombre_cliente,))
                            conn.commit()
                            conn.close()
                            st.success(f"Cliente '{nombre_cliente}' agregado correctamente.")
                    
                    # Mostrar lista de clientes existentes
                    conn = sqlite3.connect('trabajo.db')
                    clientes_df = pd.read_sql("SELECT id_cliente, nombre FROM clientes ORDER BY nombre", conn)
                    conn.close()
                    
                    if not clientes_df.empty:
                        st.dataframe(clientes_df)
                    else:
                        st.info("No hay clientes registrados.")
                
                with tab_tipos:
                    st.subheader("Gestión de Tipos de Tarea")
                    # Formulario para agregar nuevo tipo de tarea
                    with st.form("form_nuevo_tipo"):
                        descripcion_tipo = st.text_input("Descripción del Tipo de Tarea")
                        submitted = st.form_submit_button("Agregar Tipo de Tarea")
                        
                        if submitted and descripcion_tipo:
                            conn = sqlite3.connect('trabajo.db')
                            c = conn.cursor()
                            c.execute("INSERT INTO tipos_tarea (descripcion) VALUES (?)", (descripcion_tipo,))
                            conn.commit()
                            conn.close()
                            st.success(f"Tipo de tarea '{descripcion_tipo}' agregado correctamente.")
                    
                    # Mostrar lista de tipos de tarea existentes
                    conn = sqlite3.connect('trabajo.db')
                    tipos_df = pd.read_sql("SELECT id_tipo, descripcion FROM tipos_tarea ORDER BY descripcion", conn)
                    conn.close()
                    
                    if not tipos_df.empty:
                        st.dataframe(tipos_df)
                    else:
                        st.info("No hay tipos de tarea registrados.")
                
                with tab_tecnicos:
                    st.subheader("Gestión de Técnicos")
                    # Mostrar lista de técnicos existentes
                    conn = sqlite3.connect('trabajo.db')
                    tecnicos_df = pd.read_sql("""
                        SELECT t.id_tecnico, t.nombre
                        FROM tecnicos t 
                        ORDER BY t.nombre
                    """, conn)
                    conn.close()
                    
                    if not tecnicos_df.empty:
                        st.dataframe(tecnicos_df)
                        
                        # Formulario para agregar nuevo técnico
                        with st.form("form_nuevo_tecnico"):
                            st.subheader("Agregar Nuevo Técnico")
                            nombre_tecnico = st.text_input("Nombre del Técnico")
                            submitted = st.form_submit_button("Agregar Técnico")
                            
                            if submitted and nombre_tecnico:
                                conn = sqlite3.connect('trabajo.db')
                                c = conn.cursor()
                                try:
                                    c.execute("INSERT INTO tecnicos (nombre) VALUES (?)", (nombre_tecnico,))
                                    conn.commit()
                                    st.success(f"Técnico '{nombre_tecnico}' agregado correctamente.")
                                except sqlite3.IntegrityError:
                                    st.error(f"El técnico '{nombre_tecnico}' ya existe.")
                                finally:
                                    conn.close()
                        
                        # Formulario para activar/desactivar usuarios
                        with st.form("form_activar_usuario"):
                            st.subheader("Activar/Desactivar Usuario")
                            username = st.text_input("Nombre de Usuario")
                            activar = st.checkbox("Activar Usuario")
                            submitted = st.form_submit_button("Actualizar Estado")
                            
                            if submitted and username:
                                conn = sqlite3.connect('trabajo.db')
                                c = conn.cursor()
                                c.execute("UPDATE usuarios SET is_active = ? WHERE username = ?", (1 if activar else 0, username))
                                if c.rowcount > 0:
                                    conn.commit()
                                    st.success(f"Usuario '{username}' {'activado' if activar else 'desactivado'} correctamente.")
                                else:
                                    st.error(f"No se encontró el usuario '{username}'.")
                                conn.close()
                    else:
                        st.info("No hay técnicos registrados.")
                
                with tab_roles:
                    st.subheader("Gestión de Roles")
                    # Formulario para agregar nuevo rol
                    with st.form("form_nuevo_rol"):
                        nombre_rol = st.text_input("Nombre del Rol")
                        descripcion_rol = st.text_area("Descripción del Rol")
                        submitted = st.form_submit_button("Agregar Rol")
                        
                        if submitted and nombre_rol:
                            # Verificar que no sea un rol protegido
                            if nombre_rol.lower() == 'admin':
                                st.error("No se puede crear un rol con el nombre 'admin' ya que es un rol protegido.")
                            else:
                                conn = sqlite3.connect('trabajo.db')
                                c = conn.cursor()
                                try:
                                    c.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", (nombre_rol, descripcion_rol))
                                    conn.commit()
                                    st.success(f"Rol '{nombre_rol}' agregado correctamente.")
                                except sqlite3.IntegrityError:
                                    st.error("Este rol ya existe.")
                                finally:
                                    conn.close()
                    
                    # Mostrar lista de roles existentes
                    conn = sqlite3.connect('trabajo.db')
                    roles_df = pd.read_sql("SELECT id_rol, nombre, descripcion FROM roles ORDER BY nombre", conn)
                    conn.close()
                    
                    if not roles_df.empty:
                        st.dataframe(roles_df)
                    else:
                        st.info("No hay roles registrados.")
                    
                    # Formulario para editar roles
                    with st.expander("Editar Rol"):
                        if not roles_df.empty:
                            # Filtrar roles protegidos para edición
                            roles_editables_df = roles_df[~roles_df['nombre'].str.lower().isin(['admin'])]
                            
                            if not roles_editables_df.empty:
                                rol_options = [f"{row['id_rol']} - {row['nombre']}" for _, row in roles_editables_df.iterrows()]
                                selected_rol = st.selectbox("Seleccionar Rol para Editar", options=rol_options, key="select_rol_edit")
                                
                                if selected_rol:
                                    rol_id = int(selected_rol.split(' - ')[0])
                                    rol_actual = roles_editables_df[roles_editables_df['id_rol'] == rol_id].iloc[0]
                                    
                                    nuevo_nombre = st.text_input("Nuevo Nombre", value=rol_actual['nombre'])
                                    nueva_descripcion = st.text_area("Nueva Descripción", value=rol_actual['descripcion'] if pd.notna(rol_actual['descripcion']) else "")
                                    
                                    if st.button("Guardar Cambios", key="save_rol_edit"):
                                        if nuevo_nombre:
                                            conn = sqlite3.connect('trabajo.db')
                                            c = conn.cursor()
                                            try:
                                                c.execute("UPDATE roles SET nombre = ?, descripcion = ? WHERE id_rol = ?", 
                                                        (nuevo_nombre, nueva_descripcion, rol_id))
                                                conn.commit()
                                                st.success(f"Rol actualizado correctamente.")
                                            except sqlite3.IntegrityError:
                                                st.error("Ya existe un rol con ese nombre.")
                                            finally:
                                                conn.close()
                                        else:
                                            st.error("El nombre del rol no puede estar vacío.")
                            else:
                                st.info("No hay roles disponibles para editar (los roles protegidos no se pueden modificar).")
                        else:
                            st.info("No hay roles para editar.")
                    
                    # Formulario para eliminar roles
                    with st.expander("Eliminar Rol"):
                        if not roles_df.empty:
                            # Filtrar roles protegidos para eliminación
                            # Filtrar roles protegidos para eliminación
                            # Filtrar roles protegidos para eliminación
                            roles_eliminables_df = roles_df[~roles_df['nombre'].str.lower().isin(['admin', 'sin_rol'])]
                            
                            if not roles_eliminables_df.empty:
                                rol_options = [f"{row['id_rol']} - {row['nombre']}" for _, row in roles_eliminables_df.iterrows()]
                                selected_rol = st.selectbox("Seleccionar Rol para Eliminar", options=rol_options, key="select_rol_delete")
                                
                                if selected_rol:
                                    rol_id = int(selected_rol.split(' - ')[0])
                                    
                                    if st.button("Eliminar Rol", key="delete_rol_btn"):
                                        # Verificar si el rol está siendo usado por usuarios
                                        conn = sqlite3.connect('trabajo.db')
                                        c = conn.cursor()
                                        c.execute("SELECT COUNT(*) FROM usuarios WHERE rol_id = ?", (rol_id,))
                                        count = c.fetchone()[0]
                                        
                                        if count > 0:
                                            st.error(f"No se puede eliminar el rol porque está asignado a {count} usuarios.")
                                        else:
                                            c.execute("DELETE FROM roles WHERE id_rol = ?", (rol_id,))
                                            conn.commit()
                                            st.success("Rol eliminado exitosamente.")
                                        conn.close()
                            else:
                                st.info("No hay roles disponibles para eliminar (los roles protegidos no se pueden eliminar).")
                        else:
                            st.info("No hay roles para eliminar.")
                
                with tab_registros:
                    st.subheader("Gestión de Registros")
                    # Usar la función reutilizable para cargar Excel
                    from modules.utils import render_excel_uploader
                    uploaded_file, df_excel = render_excel_uploader(
                        label="Selecciona un archivo Excel (.xlsx)",
                        key="registros_excel_upload"
                    )
                    
                    if uploaded_file is not None and df_excel is not None:
                        if st.button("Importar Datos"):
                            # Aquí iría el código para procesar e importar los datos
                            # Este es un ejemplo simplificado
                            st.success("Datos importados correctamente.")
                    
                    # Mostrar todos los registros
                    st.subheader("Todos los registros")
                    df = backend.get_all_registros()
                    if not df.empty:
                        st.dataframe(df)
                    else:
                        st.info("No hay registros guardados.")
        else:
            # Interfaz para usuarios no administradores
            # Crear pestañas para las diferentes secciones
            tab_cargar, tab_ver = st.tabs(["📝 Cargar Registro", "📊 Ver Mis Registros"])
            
            with tab_cargar:
                st.subheader("Cargar nuevo registro de trabajo")
                
                # Formulario para cargar un nuevo registro
                with st.form("formulario_registro"):
                    # Fecha
                    fecha = st.date_input("Fecha", value=datetime.now().date())
                
                # Obtener listas de opciones desde la base de datos
                conn = sqlite3.connect('trabajo.db')
                tecnicos_df = pd.read_sql("SELECT id_tecnico, nombre FROM tecnicos ORDER BY nombre", conn)
                clientes_df = pd.read_sql("SELECT id_cliente, nombre FROM clientes ORDER BY nombre", conn)
                tipos_df = pd.read_sql("SELECT id_tipo, descripcion FROM tipos_tarea ORDER BY descripcion", conn)
                modalidades_df = pd.read_sql("SELECT id_modalidad, modalidad FROM modalidades_tarea ORDER BY modalidad", conn)
                conn.close()
                
                # Seleccionar técnico (por defecto el usuario actual)
                tecnico_actual_id = None
                for i, row in tecnicos_df.iterrows():
                    if row['nombre'] == nombre_completo_usuario:
                        tecnico_actual_id = row['id_tecnico']
                        break
                
                tecnico_index = 0
                if tecnico_actual_id is not None:
                    for i, row in tecnicos_df.iterrows():
                        if row['id_tecnico'] == tecnico_actual_id:
                            tecnico_index = i
                            break
                
                tecnico = st.selectbox(
                    "Técnico",
                    options=tecnicos_df['id_tecnico'].tolist(),
                    format_func=lambda x: tecnicos_df.loc[tecnicos_df['id_tecnico'] == x, 'nombre'].iloc[0],
                    index=tecnico_index
                )
                
                # Seleccionar cliente
                cliente = st.selectbox(
                    "Cliente",
                    options=clientes_df['id_cliente'].tolist(),
                    format_func=lambda x: clientes_df.loc[clientes_df['id_cliente'] == x, 'nombre'].iloc[0]
                )
                
                # Seleccionar tipo de tarea
                tipo_tarea = st.selectbox(
                    "Tipo de Tarea",
                    options=tipos_df['id_tipo'].tolist(),
                    format_func=lambda x: tipos_df.loc[tipos_df['id_tipo'] == x, 'descripcion'].iloc[0]
                )
                
                # Seleccionar modalidad
                modalidad = st.selectbox(
                    "Modalidad",
                    options=modalidades_df['id_modalidad'].tolist(),
                    format_func=lambda x: modalidades_df.loc[modalidades_df['id_modalidad'] == x, 'modalidad'].iloc[0]
                )
                
                # Campos adicionales
                tarea_realizada = st.text_input("Tarea Realizada")
                numero_ticket = st.text_input("Número de Ticket")
                tiempo = st.number_input("Tiempo (horas)", min_value=0.0, step=0.5)
                descripcion = st.text_area("Descripción")
                
                # Botón para enviar el formulario
                submitted = st.form_submit_button("Guardar Registro")
                
                if submitted:
                    if tarea_realizada and numero_ticket and tiempo > 0:
                        # Calcular el mes a partir de la fecha
                        mes = fecha.strftime("%Y-%m")
                        
                        # Guardar el registro en la base de datos
                        conn = sqlite3.connect('trabajo.db')
                        c = conn.cursor()
                        c.execute('''
                            INSERT INTO registros 
                            (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
                            numero_ticket, tiempo, descripcion, mes, usuario_id) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            fecha.strftime("%Y-%m-%d"), tecnico, cliente, tipo_tarea, modalidad,
                            tarea_realizada, numero_ticket, tiempo, descripcion, mes, st.session_state.user_id
                        ))
                        conn.commit()
                        conn.close()
                        st.success("Registro guardado correctamente.")
                    else:
                        st.error("Por favor complete todos los campos obligatorios.")
            
            with tab_ver:
                st.subheader("Mis registros de trabajo")
                
                # Obtener los registros del usuario
                conn = sqlite3.connect('trabajo.db')
                query = '''
                    SELECT r.id, r.fecha, t.nombre as tecnico, c.nombre as cliente, 
                           tt.descripcion as tipo_tarea, mt.modalidad, r.tarea_realizada, 
                           r.numero_ticket, r.tiempo, r.descripcion, r.mes
                    FROM registros r
                    JOIN tecnicos t ON r.id_tecnico = t.id_tecnico
                    JOIN clientes c ON r.id_cliente = c.id_cliente
                    JOIN tipos_tarea tt ON r.id_tipo = tt.id_tipo
                    JOIN modalidades_tarea mt ON r.id_modalidad = mt.id_modalidad
                    WHERE r.usuario_id = ?
                    ORDER BY r.fecha DESC
                '''
                user_registros = pd.read_sql_query(query, conn, params=(st.session_state.user_id,))
                conn.close()
                
                if not user_registros.empty:
                    # Mostrar los registros en una tabla
                    st.dataframe(user_registros)
                    
                    # Calcular estadísticas
                    total_horas = user_registros['tiempo'].sum()
                    st.metric("Total de horas registradas", f"{total_horas:.1f} horas")
                    
                    # Gráfico de horas por cliente
                    horas_por_cliente = user_registros.groupby('cliente')['tiempo'].sum().reset_index()
                    fig = px.bar(horas_por_cliente, x='cliente', y='tiempo', title='Horas por Cliente')
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No tienes registros de trabajo guardados.")

# Ejecutar la aplicación
if __name__ == "__main__":
    main()