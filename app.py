import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import bcrypt
import calendar
import time 

# Configuración inicial de la página
st.set_page_config(page_title="Sistema de Registro de Horas", layout="wide")

# Crear la base de datos y tablas
def init_db():
    conn = sqlite3.connect('trabajo.db')
    c = conn.cursor()
    
    # Tabla de usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            nombre TEXT,
            apellido TEXT,
            is_admin BOOLEAN NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT 1
        )
    ''')
    
    # Tabla de técnicos
    c.execute('''
        CREATE TABLE IF NOT EXISTS tecnicos (
            id_tecnico INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL UNIQUE
        )
    ''')
    
    # Tabla de clientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id_cliente INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL UNIQUE
        )
    ''')
    
    # Tabla de tipos de tarea
    c.execute('''
        CREATE TABLE IF NOT EXISTS tipos_tarea (
            id_tipo INTEGER PRIMARY KEY,
            descripcion TEXT NOT NULL UNIQUE
        )
    ''')
    
    # Tabla de modalidades de tarea
    c.execute('''
        CREATE TABLE IF NOT EXISTS modalidades_tarea (
            id_modalidad INTEGER PRIMARY KEY,
            modalidad TEXT NOT NULL UNIQUE
        )
    ''')
    
    # Tabla de registros de trabajo
    c.execute('''CREATE TABLE IF NOT EXISTS registros (
        id INTEGER PRIMARY KEY,
        fecha TEXT NOT NULL,
        id_tecnico INTEGER NOT NULL,
        id_cliente INTEGER NOT NULL,
        id_tipo INTEGER NOT NULL,
        id_modalidad INTEGER NOT NULL,
        tarea_realizada TEXT NOT NULL,
        numero_ticket TEXT NOT NULL,
        tiempo INTEGER NOT NULL,
        descripcion TEXT,
        mes TEXT NOT NULL,
        usuario_id INTEGER,
        FOREIGN KEY (id_tecnico) REFERENCES tecnicos (id_tecnico),
        FOREIGN KEY (id_cliente) REFERENCES clientes (id_cliente),
        FOREIGN KEY (id_tipo) REFERENCES tipos_tarea (id_tipo),
        FOREIGN KEY (id_modalidad) REFERENCES modalidades_tarea (id_modalidad),
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
    )''')
    
    # Verificar si el usuario admin existe, si no, crearlo
    c.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not c.fetchone():
        c.execute('INSERT INTO usuarios (username, password, is_admin, is_active) VALUES (?, ?, ?, ?)',
                  ('admin', bcrypt.hashpw('admin'.encode('utf-8'), bcrypt.gensalt()), 1, 1))
    
    conn.commit()
    conn.close()

# Inicializar la base de datos
init_db()

# Función de autenticación
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

def create_user(username, password):
    conn = sqlite3.connect('trabajo.db')
    c = conn.cursor()
    try:
        hashed_password = hash_password(password)
        # Convertir el username a minúsculas antes de guardarlo
        username = username.lower()
        c.execute('INSERT INTO usuarios (username, password) VALUES (?, ?)',
                  (username, hashed_password))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def login_user(username, password):
    conn = sqlite3.connect('trabajo.db')
    c = conn.cursor()
    # Convertir el username a minúsculas antes de buscar
    username = username.lower()
    c.execute('SELECT id, password, is_admin, is_active FROM usuarios WHERE username = ?', (username,))
    user = c.fetchone()
    
    if user and verify_password(password, user[1]):
        if user[3]: # is_active
            # Obtener el nombre y apellido del usuario
            c.execute('SELECT nombre, apellido FROM usuarios WHERE id = ?', (user[0],))
            user_info = c.fetchone()
            
            # Si el usuario tiene nombre y apellido, verificar si existe como técnico
            if user_info and (user_info[0] or user_info[1]):
                nombre_completo = f"{user_info[0] or ''} {user_info[1] or ''}".strip()
                if nombre_completo:
                    # Verificar si el técnico ya existe
                    c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = ?', (nombre_completo,))
                    tecnico = c.fetchone()
                    if not tecnico:
                        # Crear el técnico si no existe
                        c.execute('INSERT INTO tecnicos (nombre) VALUES (?)', (nombre_completo,))
                        conn.commit()
            
            conn.close()
            return user[0], user[2] # user_id, is_admin
    conn.close()
    return None, None

# Función principal de la aplicación
def main():
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
                user_id, is_admin = login_user(username, password)
                if user_id:
                    st.session_state.user_id = user_id
                    st.session_state.is_admin = is_admin
                    st.success("Login exitoso!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos o la cuenta está deshabilitada.")

        with tab2:
            st.header("Registro")
            new_username = st.text_input("Usuario", key="reg_username")
            new_password = st.text_input("Contraseña", type="password", key="reg_password")
            if st.button("Registrarse"):
                if create_user(new_username, new_password):
                    st.success("Usuario creado exitosamente!")
                else:
                    st.error("El usuario ya existe")

    else:
        # Obtener información del usuario
        conn = sqlite3.connect('trabajo.db')
        c = conn.cursor()
        c.execute('SELECT nombre, apellido, username FROM usuarios WHERE id = ?', (st.session_state.user_id,))
        user_info = c.fetchone()
        conn.close()

        # Si el usuario fue eliminado de la BD mientras estaba logueado, lo deslogueamos.
        if user_info is None:
            st.session_state.user_id = None
            st.session_state.is_admin = False
            st.rerun()

        nombre_actual = user_info[0] if user_info[0] else ''
        apellido_actual = user_info[1] if user_info[1] else ''
        current_username = user_info[2]

        # Crear contenedor en la esquina superior derecha para el perfil
        with st.container():
            col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
            with col4:
                if st.button("✏️ Editar Perfil"):
                    st.session_state.mostrar_perfil = True

        # Mostrar modal de perfil
        if 'mostrar_perfil' not in st.session_state:
            st.session_state.mostrar_perfil = False

        if st.session_state.mostrar_perfil:
            with st.sidebar:
                st.header("Editar Perfil")
                nuevo_nombre = st.text_input("Nombre", value=nombre_actual)
                nuevo_apellido = st.text_input("Apellido", value=apellido_actual)
                
                st.subheader("Cambiar Contraseña")
                nueva_password = st.text_input("Nueva Contraseña", type="password", key="new_pass")
                confirmar_password = st.text_input("Confirmar Nueva Contraseña", type="password", key="confirm_pass")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Guardar"):
                        conn = sqlite3.connect('trabajo.db')
                        c = conn.cursor()
                        
                        # Obtener el nombre y apellido actuales antes de actualizar
                        c.execute('SELECT nombre, apellido FROM usuarios WHERE id = ?', (st.session_state.user_id,))
                        old_user_info = c.fetchone()
                        old_nombre = old_user_info[0] if old_user_info[0] else ''
                        old_apellido = old_user_info[1] if old_user_info[1] else ''
                        old_nombre_completo = f"{old_nombre} {old_apellido}".strip()
                        
                        # Actualizar el usuario
                        c.execute('UPDATE usuarios SET nombre = ?, apellido = ? WHERE id = ?',
                                 (nuevo_nombre, nuevo_apellido, st.session_state.user_id))
                        
                        # Crear el nuevo nombre completo
                        nuevo_nombre_completo = f"{nuevo_nombre} {nuevo_apellido}".strip()
                        
                        # Si el nombre completo ha cambiado y el viejo nombre existía como técnico
                        if old_nombre_completo and nuevo_nombre_completo != old_nombre_completo:
                            c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = ?', (old_nombre_completo,))
                            old_tecnico = c.fetchone()
                            if old_tecnico:
                                # Actualizar el nombre del técnico
                                c.execute('UPDATE tecnicos SET nombre = ? WHERE nombre = ?', 
                                         (nuevo_nombre_completo, old_nombre_completo))
                        
                        # Si el nombre completo es nuevo, verificar si existe como técnico
                        if nuevo_nombre_completo:
                            c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = ?', (nuevo_nombre_completo,))
                            tecnico = c.fetchone()
                            if not tecnico:
                                # Crear el técnico si no existe
                                c.execute('INSERT INTO tecnicos (nombre) VALUES (?)', (nuevo_nombre_completo,))
                        
                        if nueva_password:
                            if nueva_password == confirmar_password:
                                hashed_password = hash_password(nueva_password)
                                c.execute('UPDATE usuarios SET password = ? WHERE id = ?',
                                         (hashed_password, st.session_state.user_id))
                                st.success("Contraseña actualizada exitosamente.")
                            else:
                                st.error("Las contraseñas no coinciden.")
                        
                        conn.commit()
                        conn.close()
                        st.session_state.mostrar_perfil = False
                        st.rerun()
                with col2:
                    if st.button("Cancelar"):
                        st.session_state.mostrar_perfil = False
                        st.rerun()

        st.sidebar.button("Cerrar Sesión", on_click=lambda: setattr(st.session_state, 'user_id', None) or setattr(st.session_state, 'is_admin', False))

        if st.session_state.is_admin:
            st.header("Panel de Administrador")
            
            # Crear pestañas principales del panel de administrador
            tab_visualizacion, tab_gestion = st.tabs(["📊 Visualización de Datos", "⚙️ Gestión"])
            
            with tab_visualizacion:
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
                '''
                df = pd.read_sql_query(query, conn)
                conn.close()

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
                        
                        # Listado detallado de horas por cliente
                        st.subheader("Detalle de Horas por Cliente")
                        for _, row in horas_por_cliente.iterrows():
                            st.write(f"**{row['cliente']}**: {row['tiempo']} horas")
                    
                    with tab_tipos:
                        # Gráfico de torta por tipo de tarea
                        fig2 = px.pie(df, names='tipo_tarea', title='Distribución por Tipo de Tarea')
                        st.plotly_chart(fig2, use_container_width=True)
                        
                        # Listado detallado de horas por tipo de tarea
                        st.subheader("Detalle de Horas por Tipo de Tarea")
                        for _, row in horas_por_tipo.iterrows():
                            st.write(f"**{row['tipo_tarea']}**: {row['tiempo']} horas")
                    
                    with tab_tecnicos:
                        # Gráfico de barras para horas por técnico
                        fig3 = px.bar(horas_por_tecnico, x='tecnico', y='tiempo',
                                     title='Horas Trabajadas por Técnico',
                                     labels={'tecnico': 'Técnico', 'tiempo': 'Horas Totales'})
                        st.plotly_chart(fig3, use_container_width=True)
                        
                        # Listado detallado de horas por técnico
                        st.subheader("Detalle de Horas por Técnico")
                        for _, row in horas_por_tecnico.iterrows():
                            st.write(f"**{row['tecnico']}**: {row['tiempo']} horas")
                    
                    with tab_datos:
                        # Mostrar datos en tabla
                        st.dataframe(df)
                else:
                    st.info("No hay datos para mostrar")
            
            with tab_gestion:
                # Crear pestañas para gestión de usuarios y gestión de clientes/tareas
                tab_usuarios, tab_clientes_tareas = st.tabs(["👥 Gestión de Usuarios", "🏢 Gestión de Clientes y Tareas"])
                
                with tab_usuarios:
                    conn = sqlite3.connect('trabajo.db')
                    users_df = pd.read_sql_query("SELECT id, username, nombre, apellido, is_active, is_admin FROM usuarios", conn)
                    conn.close()
                    
                    st.dataframe(users_df)

                    col1, col2 = st.columns(2)
                    with col1:
                        user_to_manage = st.selectbox("Seleccionar Usuario", options=users_df['username'])

                    # Obtener detalles del usuario seleccionado
                    selected_user_details = users_df[users_df['username'] == user_to_manage].iloc[0]

                    with col2:
                        if user_to_manage == 'admin':
                            st.selectbox("Acción", [], label_visibility="hidden")
                            st.info("El usuario 'admin' no puede ser modificado.")
                        else:
                            actions = []
                            if selected_user_details['is_active']:
                                actions.append("Deshabilitar")
                            else:
                                actions.append("Habilitar")

                            if selected_user_details['is_admin']:
                                actions.append("Quitar Administrador")
                            else:
                                actions.append("Convertir en Administrador")
                            
                            actions.append("Eliminar")
                            action = st.selectbox("Acción", actions)

                    execute_button_disabled = (user_to_manage == 'admin')
                    if st.button("Ejecutar", type="primary", use_container_width=True, disabled=execute_button_disabled):
                        if user_to_manage == current_username:
                            st.error("No puedes realizar acciones sobre tu propio usuario.")
                        else:
                            conn = sqlite3.connect('trabajo.db')
                            c = conn.cursor()
                            if action == "Habilitar":
                                c.execute('UPDATE usuarios SET is_active = 1 WHERE username = ?', (user_to_manage,))
                            elif action == "Deshabilitar":
                                c.execute('UPDATE usuarios SET is_active = 0 WHERE username = ?', (user_to_manage,))
                            elif action == "Convertir en Administrador":
                                c.execute('UPDATE usuarios SET is_admin = 1 WHERE username = ?', (user_to_manage,))
                            elif action == "Quitar Administrador":
                                c.execute('UPDATE usuarios SET is_admin = 0 WHERE username = ?', (user_to_manage,))
                            elif action == "Eliminar":
                                c.execute('DELETE FROM usuarios WHERE username = ?', (user_to_manage,))
                            conn.commit()
                            conn.close()
                            st.success(f"Acción '{action}' ejecutada para el usuario '{user_to_manage}'.")
                            st.rerun()
                
                with tab_clientes_tareas:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("Añadir nuevo cliente")
                        new_client = st.text_input("Nombre del Cliente")
                        if st.button("Añadir Cliente"):
                            if not new_client.strip():
                                st.error("El nombre del cliente no puede estar vacío.")
                            else:
                                conn = sqlite3.connect('trabajo.db')
                                c = conn.cursor()
                                try:
                                    c.execute('INSERT INTO clientes (nombre) VALUES (?)', (new_client,))
                                    conn.commit()
                                    st.success(f"Cliente '{new_client}' añadido.", icon="✅")
                                    time.sleep(2)
                                    st.rerun()
                                except sqlite3.IntegrityError:
                                    st.error(f"El cliente '{new_client}' ya existe en la base de datos.")
                                finally:
                                    conn.close()

                    with col2:
                        st.write("Añadir nuevo tipo de tarea")
                        new_task_type = st.text_input("Descripción de la Tarea")
                        if st.button("Añadir Tipo de Tarea"):
                            if not new_task_type.strip():
                                st.error("La descripción de la tarea no puede estar vacía.")
                            else:
                                conn = sqlite3.connect('trabajo.db')
                                c = conn.cursor()
                                try:
                                    c.execute('INSERT INTO tipos_tarea (descripcion) VALUES (?)', (new_task_type,))
                                    conn.commit()
                                    st.success(f"Tipo de tarea '{new_task_type}' añadido.", icon="✅")
                                    time.sleep(2)
                                    st.rerun()
                                except sqlite3.IntegrityError:
                                    st.error(f"El tipo de tarea '{new_task_type}' ya existe en la base de datos.")
                                finally:
                                    conn.close()
        else:
            tab1, tab2 = st.tabs(["Registro de Horas", "Visualización"])

            with tab1:
                st.header("Registro de Horas de Trabajo")
                
                col1, col2 = st.columns(2)
                
                # Obtener datos para los selectbox
                conn = sqlite3.connect('trabajo.db')
                c = conn.cursor()
                
                # Obtener técnicos
                c.execute('SELECT id_tecnico, nombre FROM tecnicos')
                tecnicos_data = c.fetchall()
                tecnicos_options = [t[1] for t in tecnicos_data]
                tecnicos_dict = {t[1]: t[0] for t in tecnicos_data}
                
                # Obtener clientes
                c.execute('SELECT id_cliente, nombre FROM clientes')
                clientes_data = c.fetchall()
                clientes_options = [c[1] for c in clientes_data]
                clientes_dict = {c[1]: c[0] for c in clientes_data}
                
                # Obtener tipos de tarea
                c.execute('SELECT id_tipo, descripcion FROM tipos_tarea')
                tipos_data = c.fetchall()
                tipos_options = [t[1] for t in tipos_data]
                tipos_dict = {t[1]: t[0] for t in tipos_data}
                
                # Obtener modalidades
                c.execute('SELECT id_modalidad, modalidad FROM modalidades_tarea')
                modalidades_data = c.fetchall()
                modalidades_options = [m[1] for m in modalidades_data]
                modalidades_dict = {m[1]: m[0] for m in modalidades_data}
                
                conn.close()
                
                # Si no hay datos en las tablas, agregar opciones por defecto
                if not tecnicos_options:
                    nombre_completo = f"{nombre_actual} {apellido_actual}".strip()
                    tecnicos_options = [nombre_completo]
                    
                if not clientes_options:
                    clientes_options = ["Systemscorp"]
                    
                if not tipos_options:
                    tipos_options = ["Soporte a usuarios finales", "Relevamiento"]
                    
                if not modalidades_options:
                    modalidades_options = ["Presencial", "Remoto"]
                
                with col1:
                    fecha = st.date_input("Fecha", format="DD/MM/YYYY")
                    # Autocompletar el campo de técnico con el nombre completo
                    nombre_completo = f"{nombre_actual} {apellido_actual}".strip()
                    tecnico_seleccionado = st.selectbox("Técnico", options=tecnicos_options, index=tecnicos_options.index(nombre_completo) if nombre_completo in tecnicos_options else 0)
                    cliente_seleccionado = st.selectbox("Cliente", options=clientes_options)
                    modalidad_seleccionada = st.selectbox("Modalidad de tarea", options=modalidades_options)
                    
                with col2:
                    tipo_tarea_seleccionado = st.selectbox("Tipo de tarea", options=tipos_options)
                    numero_ticket = st.text_input("N° de Ticket")
                    tiempo = st.slider("Tiempo (horas)", min_value=0.5, max_value=12.0, value=1.0, step=0.5)
                    descripcion = st.text_area("Breve Descripción")
                tarea_realizada = st.text_input("Tarea Realizada")
                
                if st.button("Guardar Registro"):
                    conn = sqlite3.connect('trabajo.db')
                    c = conn.cursor()
                    
                    mes = calendar.month_name[fecha.month]
                    
                    # Verificar si el técnico ya existe, si no, agregarlo
                    c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = ?', (tecnico_seleccionado,))
                    tecnico_id = c.fetchone()
                    if not tecnico_id:
                        c.execute('INSERT INTO tecnicos (nombre) VALUES (?)', (tecnico_seleccionado,))
                        tecnico_id = (c.lastrowid,)
                    
                    # Verificar si el cliente ya existe, si no, agregarlo
                    c.execute('SELECT id_cliente FROM clientes WHERE nombre = ?', (cliente_seleccionado,))
                    cliente_id = c.fetchone()
                    if not cliente_id:
                        c.execute('INSERT INTO clientes (nombre) VALUES (?)', (cliente_seleccionado,))
                        cliente_id = (c.lastrowid,)
                    
                    # Verificar si el tipo de tarea ya existe, si no, agregarlo
                    c.execute('SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?', (tipo_tarea_seleccionado,))
                    tipo_id = c.fetchone()
                    if not tipo_id:
                        c.execute('INSERT INTO tipos_tarea (descripcion) VALUES (?)', (tipo_tarea_seleccionado,))
                        tipo_id = (c.lastrowid,)
                    
                    # Verificar si la modalidad ya existe, si no, agregarla
                    c.execute('SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?', (modalidad_seleccionada,))
                    modalidad_id = c.fetchone()
                    if not modalidad_id:
                        c.execute('INSERT INTO modalidades_tarea (modalidad) VALUES (?)', (modalidad_seleccionada,))
                        modalidad_id = (c.lastrowid,)
                    
                    c.execute('''
                        INSERT INTO registros 
                        (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
                         numero_ticket, tiempo, descripcion, mes, usuario_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        fecha.strftime('%d/%m/%y'), 
                        tecnico_id[0], 
                        cliente_id[0], 
                        tipo_id[0], 
                        modalidad_id[0],
                        tarea_realizada, 
                        numero_ticket, 
                        tiempo, 
                        descripcion,
                        mes, 
                        st.session_state.user_id
                    ))
                    
                    conn.commit()
                    conn.close()
                    st.success("Registro guardado exitosamente!")

            with tab2:
                st.header("Visualización de Datos")
                
                conn = sqlite3.connect('trabajo.db')
                
                # Consulta con JOIN para obtener los nombres en lugar de los IDs
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
                '''
                
                df = pd.read_sql_query(query, conn, params=(st.session_state.user_id,))
                conn.close()

                if not df.empty:
                    # Gráfico de torta por modalidad
                    fig1 = px.pie(df, names='modalidad', title='Distribución por Modalidad de Tarea')
                    st.plotly_chart(fig1)

                    # Gráfico de torta por tipo de tarea
                    fig2 = px.pie(df, names='tipo_tarea', title='Distribución por Tipo de Tarea')
                    st.plotly_chart(fig2)
                    
                    # Gráfico de torta por cliente
                    fig3 = px.pie(df, names='cliente', title='Distribución por Cliente')
                    st.plotly_chart(fig3)

                    # Mostrar datos en tabla
                    st.subheader("Registros")
                    st.dataframe(df)
                else:
                    st.info("No hay datos para mostrar")

if __name__ == "__main__":
    main()