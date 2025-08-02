import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
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
            email TEXT,
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

def validate_password(password):
    """Valida que la contraseña cumpla con los requisitos de seguridad y devuelve una lista de mensajes."""
    requisitos_faltantes = []
    
    if len(password) < 8:
        requisitos_faltantes.append("La contraseña debe tener al menos 8 caracteres.")
    
    if not any(c.isupper() for c in password):
        requisitos_faltantes.append("La contraseña debe tener al menos una letra mayúscula.")
    
    if not any(c.islower() for c in password):
        requisitos_faltantes.append("La contraseña debe tener al menos una letra minúscula.")
    
    if not any(c.isdigit() for c in password):
        requisitos_faltantes.append("La contraseña debe tener al menos un número.")
    
    if not any(c in "!@#$%^&*()-_=+[]{}|;:'\",.<>/?`~" for c in password):
        requisitos_faltantes.append("La contraseña debe tener al menos un carácter especial.")
    
    if requisitos_faltantes:
        return False, requisitos_faltantes
    
    return True, ["Contraseña válida"]

def create_user(username, password, nombre=None, apellido=None, email=None, is_admin=False):
    # Validar la contraseña
    is_valid, messages = validate_password(password)
    if not is_valid:
        for message in messages:
            st.error(message)
        return False
    
    conn = sqlite3.connect('trabajo.db')
    c = conn.cursor()
    
    # Convertir el username a minúsculas
    username = username.lower()
    
    # Capitalizar nombre y apellido si existen
    if nombre:
        nombre = nombre.strip().capitalize()
    if apellido:
        apellido = apellido.strip().capitalize()
    
    # Verificar si el usuario ya existe
    c.execute('SELECT * FROM usuarios WHERE username = ?', (username,))
    if c.fetchone():
        conn.close()
        st.error("El nombre de usuario ya existe.")
        return False
    
    # Crear el nuevo usuario (deshabilitado por defecto)
    hashed_password = hash_password(password)
    c.execute('INSERT INTO usuarios (username, password, nombre, apellido, email, is_admin, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)',
              (username, hashed_password, nombre, apellido, email, is_admin, False))
    
    conn.commit()
    conn.close()
    return True

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
                    st.session_state.mostrar_perfil = False
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
                    if create_user(new_username, new_password, email=new_email):
                        st.success("Usuario creado exitosamente! Por favor contacte al administrador para que active su cuenta.")
                    # El mensaje de error ahora lo maneja la función create_user
                else:
                    st.error("Usuario, correo electrónico y contraseña son obligatorios.")

    else:
        # Función para desloguear y limpiar el estado
        def logout():
            st.session_state.user_id = None
            st.session_state.is_admin = False
            st.session_state.mostrar_perfil = False

        # Obtener información del usuario
        conn = sqlite3.connect('trabajo.db')
        c = conn.cursor()
        c.execute('SELECT nombre, apellido, username, email FROM usuarios WHERE id = ?', (st.session_state.user_id,))
        user_info = c.fetchone()
        
        # Si el usuario fue eliminado de la BD mientras estaba logueado, lo deslogueamos.
        if user_info is None:
            st.session_state.user_id = None
            st.session_state.is_admin = False
            st.rerun()

        nombre_actual = user_info[0] if user_info[0] else ''
        apellido_actual = user_info[1] if user_info[1] else ''
        current_username = user_info[2]
        email_actual = user_info[3] if user_info[3] else ''
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
                conn = sqlite3.connect('trabajo.db')
                c = conn.cursor()
                
                c.execute('SELECT nombre, apellido FROM usuarios WHERE id = ?', (st.session_state.user_id,))
                old_user_info = c.fetchone()
                old_nombre = old_user_info[0] if old_user_info[0] else ''
                old_apellido = old_user_info[1] if old_user_info[1] else ''
                old_nombre_completo = f"{old_nombre} {old_apellido}".strip()
                
                # Capitalizar nombre y apellido
                nuevo_nombre_cap = nuevo_nombre.strip().capitalize() if nuevo_nombre else ''
                nuevo_apellido_cap = nuevo_apellido.strip().capitalize() if nuevo_apellido else ''
                
                c.execute('UPDATE usuarios SET nombre = ?, apellido = ?, email = ? WHERE id = ?',
                            (nuevo_nombre_cap, nuevo_apellido_cap, nuevo_email.strip(), st.session_state.user_id))
                
                nuevo_nombre_completo = f"{nuevo_nombre_cap} {nuevo_apellido_cap}".strip()
                
                if old_nombre_completo and nuevo_nombre_completo != old_nombre_completo:
                    c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = ?', (old_nombre_completo,))
                    old_tecnico = c.fetchone()
                    if old_tecnico:
                        c.execute('UPDATE tecnicos SET nombre = ? WHERE nombre = ?', 
                                    (nuevo_nombre_completo, old_nombre_completo))
                
                if nuevo_nombre_completo:
                    c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = ?', (nuevo_nombre_completo,))
                    tecnico = c.fetchone()
                    if not tecnico:
                        c.execute('INSERT INTO tecnicos (nombre) VALUES (?)', (nuevo_nombre_completo,))
                
                if nueva_password:
                    if nueva_password == confirmar_password:
                        # Validar la contraseña
                        is_valid, messages = validate_password(nueva_password)
                        if is_valid:
                            hashed_password = hash_password(nueva_password)
                            c.execute('UPDATE usuarios SET password = ? WHERE id = ?',
                                        (hashed_password, st.session_state.user_id))
                            st.toast("Contraseña actualizada.", icon="🔑")
                        else:
                            for message in messages:
                                st.error(message)
                            conn.close()
                            return
                    else:
                        st.error("Las contraseñas no coinciden.")
                        conn.close()
                        return
                
                conn.commit()
                conn.close()
                st.toast("Perfil guardado.", icon="✅")
                st.rerun()

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
                                     color='tecnico',
                                     title='Horas Trabajadas por Técnico',
                                     labels={'tecnico': 'Técnico', 'tiempo': 'Horas Totales'})
                        st.plotly_chart(fig3, use_container_width=True)
                        
                        # Listado detallado de horas por técnico
                        st.subheader("Detalle de Horas por Técnico")
                        for _, row in horas_por_tecnico.iterrows():
                            st.write(f"**{row['tecnico']}**: {row['tiempo']} horas")
                    
                    with tab_datos:
                        # Añadir funcionalidad para cargar archivos Excel
                        st.subheader("Cargar datos desde archivo Excel")
                        uploaded_file = st.file_uploader("Selecciona un archivo Excel (.xlsx)", type=["xlsx"])
                        
                        if uploaded_file is not None:
                            try:
                                # Leer el archivo Excel
                                excel_data = pd.read_excel(uploaded_file)
                                
                                # Mostrar una vista previa de los datos
                                st.write("Vista previa de los datos:")
                                st.dataframe(excel_data.head())
                                
                                # Verificar que las columnas necesarias estén presentes
                                required_columns = ["Fecha", "Técnico", "Cliente", "Tipo tarea", 
                                                   "Tarea Realizada de manera:", "N° de Ticket", "Tiempo:", 
                                                   "Breve Descripción", "Mes"]
                                
                                missing_columns = [col for col in required_columns if col not in excel_data.columns]
                                
                                if missing_columns:
                                    st.error(f"Faltan las siguientes columnas en el archivo: {', '.join(missing_columns)}")
                                else:
                                    # Botón para importar los datos
                                    if st.button("Importar datos", key="import_excel_data"):
                                        conn = sqlite3.connect('trabajo.db')
                                        c = conn.cursor()
                                        
                                        # Contador de registros importados
                                        imported_count = 0
                                        error_count = 0
                                        
                                        # Diccionario para convertir números de mes a nombres
                                        meses_dict = {
                                            1: "January", 2: "February", 3: "March", 4: "April",
                                            5: "May", 6: "June", 7: "July", 8: "August",
                                            9: "September", 10: "October", 11: "November", 12: "December"
                                        }
                                        
                                        for index, row in excel_data.iterrows():
                                            try:
                                                # Verificar si la fecha es válida
                                                if pd.isna(row["Fecha"]) or pd.isnull(row["Fecha"]):
                                                    st.warning(f"Fila {index + 2}: Fecha vacía o inválida, saltando registro.")
                                                    error_count += 1
                                                    continue
                                                
                                                # Verificar si el técnico ya existe, si no, agregarlo
                                                tecnico_nombre = str(row["Técnico"]).strip()
                                                if not tecnico_nombre or tecnico_nombre == 'nan':
                                                    st.warning(f"Fila {index + 2}: Técnico vacío, saltando registro.")
                                                    error_count += 1
                                                    continue
                                                    
                                                c.execute('SELECT id_tecnico FROM tecnicos WHERE nombre = ?', (tecnico_nombre,))
                                                tecnico_id = c.fetchone()
                                                if not tecnico_id:
                                                    c.execute('INSERT INTO tecnicos (nombre) VALUES (?)', (tecnico_nombre,))
                                                    tecnico_id = (c.lastrowid,)
                                                
                                                # Verificar si el cliente ya existe, si no, agregarlo
                                                cliente_nombre = str(row["Cliente"]).strip()
                                                if not cliente_nombre or cliente_nombre == 'nan':
                                                    st.warning(f"Fila {index + 2}: Cliente vacío, saltando registro.")
                                                    error_count += 1
                                                    continue
                                                    
                                                c.execute('SELECT id_cliente FROM clientes WHERE nombre = ?', (cliente_nombre,))
                                                cliente_id = c.fetchone()
                                                if not cliente_id:
                                                    c.execute('INSERT INTO clientes (nombre) VALUES (?)', (cliente_nombre,))
                                                    cliente_id = (c.lastrowid,)
                                                
                                                # Verificar si el tipo de tarea ya existe, si no, agregarlo
                                                tipo_tarea = str(row["Tipo tarea"]).strip()
                                                if not tipo_tarea or tipo_tarea == 'nan':
                                                    st.warning(f"Fila {index + 2}: Tipo de tarea vacío, saltando registro.")
                                                    error_count += 1
                                                    continue
                                                    
                                                c.execute('SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?', (tipo_tarea,))
                                                tipo_id = c.fetchone()
                                                if not tipo_id:
                                                    c.execute('INSERT INTO tipos_tarea (descripcion) VALUES (?)', (tipo_tarea,))
                                                    tipo_id = (c.lastrowid,)
                                                
                                                # Verificar si la modalidad ya existe, si no, agregarla
                                                modalidad = str(row["Tarea Realizada de manera:"]).strip()
                                                if not modalidad or modalidad == 'nan':
                                                    st.warning(f"Fila {index + 2}: Modalidad vacía, saltando registro.")
                                                    error_count += 1
                                                    continue
                                                    
                                                c.execute('SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?', (modalidad,))
                                                modalidad_id = c.fetchone()
                                                if not modalidad_id:
                                                    c.execute('INSERT INTO modalidades_tarea (modalidad) VALUES (?)', (modalidad,))
                                                    modalidad_id = (c.lastrowid,)
                                                
                                                # Preparar los datos para insertar
                                                fecha_valor = row["Fecha"]
                                                
                                                # Convertir la fecha al formato correcto (dd/mm/yy)
                                                try:
                                                    # Si es un timestamp de pandas, convertirlo a datetime
                                                    if hasattr(fecha_valor, 'to_pydatetime'):
                                                        fecha_obj = fecha_valor.to_pydatetime()
                                                    elif isinstance(fecha_valor, datetime):
                                                        fecha_obj = fecha_valor
                                                    else:
                                                        # Intentar parsear como string
                                                        fecha_str = str(fecha_valor)
                                                        try:
                                                            fecha_obj = datetime.strptime(fecha_str, "%d/%m/%Y")
                                                        except ValueError:
                                                            try:
                                                                fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d")
                                                            except ValueError:
                                                                try:
                                                                    fecha_obj = datetime.strptime(fecha_str, "%d/%m/%y")
                                                                except ValueError:
                                                                    # Intentar con formato ISO
                                                                    fecha_obj = datetime.fromisoformat(fecha_str.split('T')[0])
                                                    
                                                    fecha_formateada = fecha_obj.strftime('%d/%m/%y')
                                                except Exception as e:
                                                    st.warning(f"Fila {index + 2}: Error al procesar la fecha '{fecha_valor}': {str(e)}")
                                                    error_count += 1
                                                    continue
                                                
                                                # Convertir el número del mes a nombre del mes
                                                try:
                                                    if pd.isna(row["Mes"]) or pd.isnull(row["Mes"]):
                                                        st.warning(f"Fila {index + 2}: Mes vacío, saltando registro.")
                                                        error_count += 1
                                                        continue
                                                        
                                                    mes_numero = int(row["Mes"])
                                                    if mes_numero in meses_dict:
                                                        mes = meses_dict[mes_numero]
                                                    else:
                                                        st.warning(f"Fila {index + 2}: Número de mes inválido: {mes_numero}")
                                                        error_count += 1
                                                        continue
                                                except (ValueError, TypeError):
                                                    st.warning(f"Fila {index + 2}: Error al convertir el mes: {row['Mes']}")
                                                    error_count += 1
                                                    continue
                                                
                                                # Obtener el resto de los datos
                                                tarea_realizada = str(row.get("Tarea Realizada", "")) if pd.notna(row.get("Tarea Realizada", "")) else ""
                                                numero_ticket = str(row["N° de Ticket"]) if pd.notna(row["N° de Ticket"]) else "NA"
                                                
                                                # Validar tiempo
                                                try:
                                                    if pd.isna(row["Tiempo:"]) or pd.isnull(row["Tiempo:"]):
                                                        tiempo = 0
                                                    else:
                                                        tiempo = float(row["Tiempo:"])
                                                except (ValueError, TypeError):
                                                    tiempo = 0
                                                    st.warning(f"Fila {index + 2}: Tiempo inválido, usando 0")
                                                
                                                descripcion = str(row["Breve Descripción"]) if pd.notna(row["Breve Descripción"]) else ""
                                                
                                                # Verificar si ya existe un registro con los mismos datos (para evitar duplicados)
                                                c.execute('''
                                                    SELECT COUNT(*) FROM registros 
                                                    WHERE fecha = ? AND id_tecnico = ? AND id_cliente = ? AND id_tipo = ? 
                                                    AND id_modalidad = ? AND tarea_realizada = ? AND tiempo = ?
                                                ''', (fecha_formateada, tecnico_id[0], cliente_id[0], tipo_id[0], 
                                                      modalidad_id[0], tarea_realizada, tiempo))
                                                
                                                duplicate_count = c.fetchone()[0]
                                                if duplicate_count > 0:
                                                    st.warning(f"Fila {index + 2}: Ya existe un registro con estos mismos datos. Se omitirá para evitar duplicados.")
                                                    error_count += 1
                                                    continue
                                                
                                                # Insertar el registro en la base de datos
                                                c.execute('''
                                                    INSERT INTO registros 
                                                    (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
                                                     numero_ticket, tiempo, descripcion, mes, usuario_id)
                                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                                ''', (
                                                    fecha_formateada, 
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
                                                
                                                st.success(f"Fila {index + 2}: Registro importado exitosamente.")
                                                imported_count += 1
                                            except Exception as e:
                                                error_count += 1
                                                st.error(f"Error al importar fila {index + 2}: {str(e)}")
                                        
                                        conn.commit()
                                        conn.close()
                                        
                                        if imported_count > 0:
                                            st.success(f"Se importaron {imported_count} registros exitosamente.")
                                            if error_count > 0:
                                                st.warning(f"No se pudieron importar {error_count} registros debido a errores.")
                                            # Recargar la página para mostrar los nuevos datos
                                            st.rerun()
                                        else:
                                            st.error("No se pudo importar ningún registro.")
                            except Exception as e:
                                st.error(f"Error al procesar el archivo Excel: {str(e)}")
                        
                        # Mostrar datos en tabla (código existente)
                        st.dataframe(df)
                        
                        # Funcionalidad para editar y eliminar registros (solo para administradores)
                        if not df.empty:
                            st.subheader("Gestión de Registros")
                            
                            # Crear lista de opciones para seleccionar registro
                            registro_ids = df['id'].tolist()
                            registro_fechas = df['fecha'].tolist()
                            registro_tareas = df['tarea_realizada'].tolist()
                            registro_tecnicos = df['tecnico'].tolist()
                            
                            registro_options = [f"{rid} - {rfecha} - {rtecnico} - {rtarea}" for rid, rfecha, rtecnico, rtarea in zip(registro_ids, registro_fechas, registro_tecnicos, registro_tareas)]
                            
                            selected_registro_admin = st.selectbox("Seleccionar Registro para Editar/Eliminar", 
                                                                   options=registro_options, key="select_registro_admin_edit_delete")
                            
                            if selected_registro_admin:
                                registro_id_admin = int(selected_registro_admin.split(' - ')[0])
                                
                                # Obtener datos del registro seleccionado
                                registro_seleccionado_admin = df[df['id'] == registro_id_admin].iloc[0]
                                
                                # Crear pestañas para editar o eliminar
                                edit_tab_admin, delete_tab_admin = st.tabs(["Editar Registro", "Eliminar Registro"])
                                
                                with edit_tab_admin:
                                    st.subheader("Editar Registro")
                                    
                                    # Formulario para editar el registro
                                    fecha_str_admin = registro_seleccionado_admin['fecha']
                                    try:
                                        fecha_obj_admin = datetime.strptime(fecha_str_admin, '%d/%m/%y')
                                    except ValueError:
                                        try:
                                            fecha_obj_admin = datetime.strptime(fecha_str_admin, '%d/%m/%Y')
                                        except ValueError:
                                            fecha_obj_admin = datetime.now()
                                    
                                    fecha_edit_admin = st.date_input("Fecha", value=fecha_obj_admin, key="admin_edit_fecha")
                                    fecha_formateada_edit_admin = fecha_edit_admin.strftime('%d/%m/%y')
                                    
                                    # Obtener listas de técnicos, clientes, tipos y modalidades
                                    conn = sqlite3.connect('trabajo.db')
                                    tecnicos_df_admin = pd.read_sql_query("SELECT * FROM tecnicos", conn)
                                    clientes_df_admin = pd.read_sql_query("SELECT * FROM clientes", conn)
                                    tipos_df_admin = pd.read_sql_query("SELECT * FROM tipos_tarea", conn)
                                    modalidades_df_admin = pd.read_sql_query("SELECT * FROM modalidades_tarea", conn)
                                    conn.close()
                                    
                                    # Selección de técnico (administrador puede cambiar cualquier técnico)
                                    tecnico_options_admin = tecnicos_df_admin['nombre'].tolist()
                                    tecnico_index_admin = tecnico_options_admin.index(registro_seleccionado_admin['tecnico']) if registro_seleccionado_admin['tecnico'] in tecnico_options_admin else 0
                                    tecnico_selected_edit_admin = st.selectbox("Técnico", options=tecnico_options_admin, index=tecnico_index_admin, key="admin_edit_tecnico")
                                    
                                    # Selección de cliente
                                    cliente_options_admin = clientes_df_admin['nombre'].tolist()
                                    cliente_index_admin = cliente_options_admin.index(registro_seleccionado_admin['cliente']) if registro_seleccionado_admin['cliente'] in cliente_options_admin else 0
                                    cliente_selected_edit_admin = st.selectbox("Cliente", options=cliente_options_admin, index=cliente_index_admin, key="admin_edit_cliente")
                                    
                                    # Selección de tipo de tarea
                                    tipo_options_admin = tipos_df_admin['descripcion'].tolist()
                                    tipo_index_admin = tipo_options_admin.index(registro_seleccionado_admin['tipo_tarea']) if registro_seleccionado_admin['tipo_tarea'] in tipo_options_admin else 0
                                    tipo_selected_edit_admin = st.selectbox("Tipo de Tarea", options=tipo_options_admin, index=tipo_index_admin, key="admin_edit_tipo")
                                    
                                    # Selección de modalidad
                                    modalidad_options_admin = modalidades_df_admin['modalidad'].tolist()
                                    modalidad_index_admin = modalidad_options_admin.index(registro_seleccionado_admin['modalidad']) if registro_seleccionado_admin['modalidad'] in modalidad_options_admin else 0
                                    modalidad_selected_edit_admin = st.selectbox("Modalidad", options=modalidad_options_admin, index=modalidad_index_admin, key="admin_edit_modalidad")
                                    
                                    # Campos adicionales
                                    tarea_realizada_edit_admin = st.text_input("Tarea Realizada", value=registro_seleccionado_admin['tarea_realizada'], key="admin_edit_tarea")
                                    numero_ticket_edit_admin = st.text_input("Número de Ticket", value=registro_seleccionado_admin['numero_ticket'], key="admin_edit_ticket")
                                    tiempo_edit_admin = st.number_input("Tiempo (horas)", min_value=0.0, step=0.5, value=float(registro_seleccionado_admin['tiempo']), key="admin_edit_tiempo")
                                    descripcion_edit_admin = st.text_area("Descripción", value=registro_seleccionado_admin['descripcion'] if pd.notna(registro_seleccionado_admin['descripcion']) else "", key="admin_edit_descripcion")
                                    
                                    # Mes (automático basado en la fecha)
                                    mes_edit_admin = calendar.month_name[fecha_edit_admin.month]
                                    
                                    # Botón para guardar cambios
                                    if st.button("Guardar Cambios", key="admin_save_registro_edit"):
                                        if not tarea_realizada_edit_admin:
                                            st.error("La tarea realizada es obligatoria.")
                                        elif tiempo_edit_admin <= 0:
                                            st.error("El tiempo debe ser mayor que cero.")
                                        else:
                                            conn = sqlite3.connect('trabajo.db')
                                            c = conn.cursor()
                                            
                                            # Obtener IDs de las entidades seleccionadas
                                            c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (tecnico_selected_edit_admin,))
                                            id_tecnico_admin = c.fetchone()[0]
                                            
                                            c.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (cliente_selected_edit_admin,))
                                            id_cliente_admin = c.fetchone()[0]
                                            
                                            c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (tipo_selected_edit_admin,))
                                            id_tipo_admin = c.fetchone()[0]
                                            
                                            c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (modalidad_selected_edit_admin,))
                                            id_modalidad_admin = c.fetchone()[0]
                                            
                                            # Verificar si ya existe un registro con los mismos datos (excluyendo el registro actual)
                                            c.execute('''
                                                SELECT COUNT(*) FROM registros 
                                                WHERE fecha = ? AND id_tecnico = ? AND id_cliente = ? AND id_tipo = ? 
                                                AND id_modalidad = ? AND tarea_realizada = ? AND tiempo = ? AND id != ?
                                            ''', (fecha_formateada_edit_admin, id_tecnico_admin, id_cliente_admin, id_tipo_admin, 
                                                  id_modalidad_admin, tarea_realizada_edit_admin, tiempo_edit_admin, registro_id_admin))
                                            
                                            duplicate_count_admin = c.fetchone()[0]
                                            if duplicate_count_admin > 0:
                                                st.error("Ya existe un registro con estos mismos datos. No se puede crear un duplicado.")
                                            else:
                                                # Actualizar registro
                                                c.execute('''
                                                    UPDATE registros SET 
                                                    fecha = ?, id_tecnico = ?, id_cliente = ?, id_tipo = ?, id_modalidad = ?,
                                                    tarea_realizada = ?, numero_ticket = ?, tiempo = ?, descripcion = ?, mes = ?
                                                    WHERE id = ?
                                                ''', (fecha_formateada_edit_admin, id_tecnico_admin, id_cliente_admin, id_tipo_admin, 
                                                      id_modalidad_admin, tarea_realizada_edit_admin, numero_ticket_edit_admin, 
                                                      tiempo_edit_admin, descripcion_edit_admin, mes_edit_admin, registro_id_admin))
                                                
                                                conn.commit()
                                                st.success(f"✅ Registro actualizado exitosamente. Se ha verificado que no existen duplicados.")
                                                time.sleep(1.5)
                                                st.rerun()
                                            
                                            conn.close()
                                
                                with delete_tab_admin:
                                    st.subheader("Eliminar Registro")
                                    st.warning("¿Estás seguro de que deseas eliminar este registro? Esta acción no se puede deshacer.")
                                    
                                    # Mostrar información del registro a eliminar
                                    st.info(f"**Registro a eliminar:**\n\n"
                                            f"- **ID:** {registro_seleccionado_admin['id']}\n"
                                            f"- **Fecha:** {registro_seleccionado_admin['fecha']}\n"
                                            f"- **Técnico:** {registro_seleccionado_admin['tecnico']}\n"
                                            f"- **Cliente:** {registro_seleccionado_admin['cliente']}\n"
                                            f"- **Tarea:** {registro_seleccionado_admin['tarea_realizada']}\n"
                                            f"- **Tiempo:** {registro_seleccionado_admin['tiempo']} horas")
                                    
                                    if st.button("Eliminar Registro", key="admin_delete_registro_btn", type="primary"):
                                        conn = sqlite3.connect('trabajo.db')
                                        c = conn.cursor()
                                        
                                        # Eliminar el registro (administrador puede eliminar cualquier registro)
                                        c.execute("DELETE FROM registros WHERE id = ?", (registro_id_admin,))
                                        conn.commit()
                                        conn.close()
                                        
                                        st.success(f"✅ Registro eliminado exitosamente. La entrada ha sido completamente removida del sistema.")
                                        time.sleep(1.5)
                                        st.rerun()
                        else:
                            st.info("No hay registros para gestionar.")
                else:
                    st.info("No hay datos para mostrar")
            
            with tab_gestion:
                # Crear sub-pestañas para gestionar diferentes entidades
                subtab_usuarios, subtab_clientes, subtab_tipos, subtab_modalidades = st.tabs([
                    "👥 Usuarios", "🏢 Clientes", "📋 Tipos de Tarea", "🔄 Modalidades"
                ])
                
                # Gestión de Usuarios
                with subtab_usuarios:
                    st.subheader("Gestión de Usuarios")
                    
                    # Formulario para crear/editar usuarios
                    with st.expander("Crear Usuario"):
                        # Campos para el formulario
                        new_user_username = st.text_input("Usuario", key="new_user_username")
                        new_user_password = st.text_input("Contraseña", type="password", key="new_user_password")
                        new_user_nombre = st.text_input("Nombre", key="new_user_nombre")
                        new_user_apellido = st.text_input("Apellido", key="new_user_apellido")
                        new_user_is_admin = st.checkbox("Es Administrador", key="new_user_is_admin")
                        
                        # Información sobre requisitos de contraseña
                        st.info("La contraseña debe tener al menos 8 caracteres, una letra mayúscula, una letra minúscula, un número y un carácter especial.")
                        
                        # Botón para crear usuario
                        if st.button("Crear Usuario", key="create_user_btn"):
                            if new_user_username and new_user_password:
                                if create_user(new_user_username, new_user_password, 
                                              new_user_nombre, new_user_apellido, new_user_is_admin):
                                    st.success(f"Usuario {new_user_username} creado exitosamente.")
                                    st.rerun()
                                # El mensaje de error ahora lo maneja la función create_user
                            else:
                                st.error("Usuario y contraseña son obligatorios.")
                    
                    # Tabla de usuarios existentes
                    st.subheader("Usuarios Existentes")
                    conn = sqlite3.connect('trabajo.db')
                    users_df = pd.read_sql_query(
                        "SELECT id, username, nombre, apellido, is_admin, is_active FROM usuarios", conn)
                    conn.close()
                    
                    # Mostrar tabla de usuarios
                    st.dataframe(users_df)
                    
                  # Formulario para editar usuarios
                    with st.expander("Editar Usuario"):
                        if not users_df.empty:
                            user_ids = users_df['id'].tolist()
                            user_usernames = users_df['username'].tolist()
                            user_options = [f"{uid} - {uname}" for uid, uname in zip(user_ids, user_usernames)]
                            
                            selected_user_edit = st.selectbox("Seleccionar Usuario para Editar", 
                                                             options=user_options, key="select_user_edit")
                            if selected_user_edit:
                                user_id = int(selected_user_edit.split(' - ')[0])
                                user_row = users_df[users_df['id'] == user_id].iloc[0]
                                
                                # No permitir editar al propio usuario completamente
                                if user_id == st.session_state.user_id:
                                    st.warning("Editando tu propio usuario. Algunos campos están restringidos.")
                                    disable_critical_fields = True
                                else:
                                    disable_critical_fields = False
                                
                                # Campos editables
                                edit_nombre = st.text_input("Nombre", value=user_row['nombre'] or "", 
                                                           key="edit_user_nombre")
                                edit_apellido = st.text_input("Apellido", value=user_row['apellido'] or "", 
                                                            key="edit_user_apellido")
                                edit_is_admin = st.checkbox("Es Administrador", value=bool(user_row['is_admin']), 
                                                           key="edit_user_is_admin", disabled=disable_critical_fields)
                                edit_is_active = st.checkbox("Usuario Activo", value=bool(user_row['is_active']), 
                                                            key="edit_user_is_active", disabled=disable_critical_fields)
                                
                                # Opción para cambiar contraseña
                                change_password = st.checkbox("Cambiar Contraseña", key="change_password_check")
                                new_password = ""
                                if change_password:
                                    new_password = st.text_input("Nueva Contraseña", type="password", 
                                                                key="edit_user_password")
                                    st.info("La contraseña debe tener al menos 8 caracteres, una letra mayúscula, una letra minúscula, un número y un carácter especial.")
                                
                                if st.button("Guardar Cambios de Usuario", key="save_user_edit"):
                                    conn = sqlite3.connect('trabajo.db')
                                    c = conn.cursor()
                                    
                                    try:
                                        # Actualizar información básica
                                        c.execute("""UPDATE usuarios SET nombre = ?, apellido = ?, is_admin = ?, is_active = ? 
                                                     WHERE id = ?""", 
                                                 (edit_nombre, edit_apellido, edit_is_admin, edit_is_active, user_id))
                                        
                                        # Cambiar contraseña si se solicitó
                                        if change_password and new_password:
                                            # Validar la contraseña
                                            is_valid, messages = validate_password(new_password)
                                            if is_valid:
                                                hashed_password = hash_password(new_password)
                                                c.execute("UPDATE usuarios SET password = ? WHERE id = ?", 
                                                         (hashed_password, user_id))
                                            else:
                                                for message in messages:
                                                    st.error(message)
                                                conn.close()
                                                return
                                        
                                        conn.commit()
                                        st.success("Usuario actualizado exitosamente.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error al actualizar usuario: {str(e)}")
                                    finally:
                                        conn.close()
                        else:
                            st.info("No hay usuarios para editar.")
                    
                    # Formulario para eliminar usuarios
                    with st.expander("Eliminar Usuario"):
                        if not users_df.empty:
                            user_ids = users_df['id'].tolist()
                            user_usernames = users_df['username'].tolist()
                            user_options = [f"{uid} - {uname}" for uid, uname in zip(user_ids, user_usernames)]
                            
                            selected_user_delete = st.selectbox("Seleccionar Usuario para Eliminar", 
                                                               options=user_options, key="select_user_delete")
                            if selected_user_delete:
                                user_id = int(selected_user_delete.split(' - ')[0])
                                user_row = users_df[users_df['id'] == user_id].iloc[0]
                                
                                # No permitir eliminar al propio usuario
                                if user_id == st.session_state.user_id:
                                    st.error("No puedes eliminar tu propio usuario.")
                                else:
                                    st.warning("¿Estás seguro de que deseas eliminar este usuario? Esta acción no se puede deshacer.")
                                    
                                    # Mostrar información del usuario a eliminar
                                    st.info(f"**Usuario a eliminar:**\n\n"
                                            f"- **ID:** {user_row['id']}\n"
                                            f"- **Usuario:** {user_row['username']}\n"
                                            f"- **Nombre:** {user_row['nombre'] or 'N/A'}\n"
                                            f"- **Apellido:** {user_row['apellido'] or 'N/A'}\n"
                                            f"- **Es Admin:** {'Sí' if user_row['is_admin'] else 'No'}\n"
                                            f"- **Activo:** {'Sí' if user_row['is_active'] else 'No'}")
                                    
                                    if st.button("Eliminar Usuario", key="delete_user_btn", type="primary"):
                                        conn = sqlite3.connect('trabajo.db')
                                        c = conn.cursor()
                                        
                                        try:
                                            # Verificar si el usuario tiene registros asociados
                                            c.execute("SELECT COUNT(*) FROM registros WHERE usuario_id = ?", (user_id,))
                                            registro_count = c.fetchone()[0]
                                            
                                            # Eliminar primero todos los registros del usuario
                                            if registro_count > 0:
                                                c.execute("DELETE FROM registros WHERE usuario_id = ?", (user_id,))
                                                st.info(f"Se eliminaron {registro_count} registros asociados al usuario.")
                                            
                                            # Eliminar el usuario
                                            c.execute("DELETE FROM usuarios WHERE id = ?", (user_id,))
                                            conn.commit()
                                            
                                            if registro_count > 0:
                                                st.success(f"✅ Usuario '{user_row['username']}' y sus {registro_count} registros eliminados exitosamente.")
                                            else:
                                                st.success(f"✅ Usuario '{user_row['username']}' eliminado exitosamente.")
                                            time.sleep(1.5)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Error al eliminar usuario: {str(e)}")
                                        finally:
                                            conn.close()
                        else:
                            st.info("No hay usuarios para eliminar.")
                
                # Gestión de Clientes
                with subtab_clientes:
                    st.subheader("Gestión de Clientes")
                    
                    # Formulario para agregar clientes
                    with st.expander("Agregar Cliente"):
                        new_client_name = st.text_input("Nombre del Cliente", key="new_client_name")
                        
                        if st.button("Agregar Cliente", key="add_client_btn"):
                            if new_client_name:
                                conn = sqlite3.connect('trabajo.db')
                                c = conn.cursor()
                                try:
                                    c.execute("INSERT INTO clientes (nombre) VALUES (?)", (new_client_name,))
                                    conn.commit()
                                    st.success(f"Cliente {new_client_name} agregado exitosamente.")
                                    st.rerun()
                                except sqlite3.IntegrityError:
                                    st.error("Este cliente ya existe.")
                                finally:
                                    conn.close()
                            else:
                                st.error("El nombre del cliente es obligatorio.")
                    
                    # Tabla de clientes existentes
                    st.subheader("Clientes Existentes")
                    conn = sqlite3.connect('trabajo.db')
                    clients_df = pd.read_sql_query("SELECT * FROM clientes", conn)
                    conn.close()
                    
                    st.dataframe(clients_df)
                    
                    # Formulario para editar clientes
                    with st.expander("Editar Cliente"):
                        if not clients_df.empty:
                            client_ids = clients_df['id_cliente'].tolist()
                            client_names = clients_df['nombre'].tolist()
                            client_options = [f"{cid} - {cname}" for cid, cname in zip(client_ids, client_names)]
                            
                            selected_client_edit = st.selectbox("Seleccionar Cliente para Editar", 
                                                               options=client_options, key="select_client_edit")
                            if selected_client_edit:
                                client_id = int(selected_client_edit.split(' - ')[0])
                                current_name = selected_client_edit.split(' - ', 1)[1]
                                
                                new_client_name = st.text_input("Nuevo Nombre del Cliente", 
                                                               value=current_name, key="edit_client_name")
                                
                                if st.button("Guardar Cambios", key="save_client_edit"):
                                    if new_client_name and new_client_name != current_name:
                                        conn = sqlite3.connect('trabajo.db')
                                        c = conn.cursor()
                                        try:
                                            c.execute("UPDATE clientes SET nombre = ? WHERE id_cliente = ?", 
                                                     (new_client_name, client_id))
                                            conn.commit()
                                            st.success(f"Cliente actualizado de '{current_name}' a '{new_client_name}'.")
                                            st.rerun()
                                        except sqlite3.IntegrityError:
                                            st.error("Ya existe un cliente con ese nombre.")
                                        finally:
                                            conn.close()
                                    elif new_client_name == current_name:
                                        st.info("No se detectaron cambios.")
                                    else:
                                        st.error("El nombre del cliente no puede estar vacío.")
                        else:
                            st.info("No hay clientes para editar.")
                    
                    # Formulario para eliminar clientes
                    with st.expander("Eliminar Cliente"):
                        if not clients_df.empty:
                            client_ids = clients_df['id_cliente'].tolist()
                            client_names = clients_df['nombre'].tolist()
                            client_options = [f"{cid} - {cname}" for cid, cname in zip(client_ids, client_names)]
                            
                            selected_client = st.selectbox("Seleccionar Cliente", options=client_options, key="select_client_delete")
                            if selected_client:
                                client_id = int(selected_client.split(' - ')[0])
                                
                                if st.button("Eliminar Cliente", key="delete_client_btn"):
                                    # Verificar si el cliente está siendo usado en registros
                                    conn = sqlite3.connect('trabajo.db')
                                    c = conn.cursor()
                                    c.execute("SELECT COUNT(*) FROM registros WHERE id_cliente = ?", (client_id,))
                                    count = c.fetchone()[0]
                                    
                                    if count > 0:
                                        st.error(f"No se puede eliminar el cliente porque está siendo usado en {count} registros.")
                                    else:
                                        c.execute("DELETE FROM clientes WHERE id_cliente = ?", (client_id,))
                                        conn.commit()
                                        st.success("Cliente eliminado exitosamente.")
                                        time.sleep(1)
                                        st.rerun()
                                    conn.close()
                        else:
                            st.info("No hay clientes para eliminar.")
                
                # Gestión de Tipos de Tarea
                # Gestión de Tipos de Tarea
                with subtab_tipos:
                    st.subheader("Gestión de Tipos de Tarea")
                    
                    # Formulario para agregar tipos de tarea
                    with st.expander("Agregar Tipo de Tarea"):
                        new_task_type = st.text_input("Descripción del Tipo de Tarea", key="new_task_type")
                        
                        if st.button("Agregar Tipo de Tarea", key="add_task_type_btn"):
                            if new_task_type:
                                conn = sqlite3.connect('trabajo.db')
                                c = conn.cursor()
                                try:
                                    c.execute("INSERT INTO tipos_tarea (descripcion) VALUES (?)", (new_task_type,))
                                    conn.commit()
                                    st.success(f"Tipo de tarea {new_task_type} agregado exitosamente.")
                                    time.sleep(2)
                                    st.rerun()
                                except sqlite3.IntegrityError:
                                    st.error("Este tipo de tarea ya existe.")
                                finally:
                                    conn.close()
                            else:
                                st.error("La descripción del tipo de tarea es obligatoria.")
                    
                    # Tabla de tipos de tarea existentes
                    st.subheader("Tipos de Tarea Existentes")
                    conn = sqlite3.connect('trabajo.db')
                    task_types_df = pd.read_sql_query("SELECT * FROM tipos_tarea", conn)
                    conn.close()
                    
                    st.dataframe(task_types_df)
                    
                    # Formulario para editar tipos de tarea
                    with st.expander("Editar Tipo de Tarea"):
                        if not task_types_df.empty:
                            type_ids = task_types_df['id_tipo'].tolist()
                            type_descs = task_types_df['descripcion'].tolist()
                            type_options = [f"{tid} - {tdesc}" for tid, tdesc in zip(type_ids, type_descs)]
                            
                            selected_type_edit = st.selectbox("Seleccionar Tipo de Tarea para Editar", 
                                                             options=type_options, key="select_type_edit")
                            if selected_type_edit:
                                type_id = int(selected_type_edit.split(' - ')[0])
                                current_desc = selected_type_edit.split(' - ', 1)[1]
                                
                                new_task_desc = st.text_input("Nueva Descripción del Tipo de Tarea", 
                                                             value=current_desc, key="edit_task_desc")
                                
                                if st.button("Guardar Cambios", key="save_type_edit"):
                                    if new_task_desc and new_task_desc != current_desc:
                                        conn = sqlite3.connect('trabajo.db')
                                        c = conn.cursor()
                                        try:
                                            c.execute("UPDATE tipos_tarea SET descripcion = ? WHERE id_tipo = ?", 
                                                     (new_task_desc, type_id))
                                            conn.commit()
                                            st.success(f"Tipo de tarea actualizado de '{current_desc}' a '{new_task_desc}'.")
                                            time.sleep(2)
                                            st.rerun()
                                        except sqlite3.IntegrityError:
                                            st.error("Ya existe un tipo de tarea con esa descripción.")
                                        finally:
                                            conn.close()
                                    elif new_task_desc == current_desc:
                                        st.info("No se detectaron cambios.")
                                    else:
                                        st.error("La descripción del tipo de tarea no puede estar vacía.")
                        else:
                            st.info("No hay tipos de tarea para editar.")
                    
                    # Formulario para eliminar tipos de tarea (mantener el existente)
                    with st.expander("Eliminar Tipo de Tarea"):
                        if not task_types_df.empty:
                            type_ids = task_types_df['id_tipo'].tolist()
                            type_descs = task_types_df['descripcion'].tolist()
                            type_options = [f"{tid} - {tdesc}" for tid, tdesc in zip(type_ids, type_descs)]
                            
                            selected_type = st.selectbox("Seleccionar Tipo de Tarea", options=type_options, key="select_type_delete")
                            if selected_type:
                                type_id = int(selected_type.split(' - ')[0])
                                
                                if st.button("Eliminar Tipo de Tarea", key="delete_type_btn"):
                                    # Verificar si el tipo está siendo usado en registros
                                    conn = sqlite3.connect('trabajo.db')
                                    c = conn.cursor()
                                    c.execute("SELECT COUNT(*) FROM registros WHERE id_tipo = ?", (type_id,))
                                    count = c.fetchone()[0]
                                    
                                    if count > 0:
                                        st.error(f"No se puede eliminar el tipo porque está siendo usado en {count} registros.")
                                    else:
                                        c.execute("DELETE FROM tipos_tarea WHERE id_tipo = ?", (type_id,))
                                        conn.commit()
                                        st.success("Tipo de tarea eliminado exitosamente.")
                                        time.sleep(1)
                                        st.rerun()
                                    conn.close()
                        else:
                            st.info("No hay tipos de tarea para eliminar.")
                
                # Gestión de Modalidades
                with subtab_modalidades:
                    st.subheader("Gestión de Modalidades")
                    
                    # Formulario para agregar modalidades
                    with st.expander("Agregar Modalidad"):
                        new_modality = st.text_input("Nombre de la Modalidad", key="new_modality")
                        
                        if st.button("Agregar Modalidad", key="add_modality_btn"):
                            if new_modality:
                                conn = sqlite3.connect('trabajo.db')
                                c = conn.cursor()
                                try:
                                    c.execute("INSERT INTO modalidades_tarea (modalidad) VALUES (?)", (new_modality,))
                                    conn.commit()
                                    st.success(f"Modalidad {new_modality} agregada exitosamente.")
                                    time.sleep(1)
                                    st.rerun()
                                except sqlite3.IntegrityError:
                                    st.error("Esta modalidad ya existe.")
                                finally:
                                    conn.close()
                            else:
                                st.error("El nombre de la modalidad es obligatorio.")
                    
                    # Tabla de modalidades existentes
                    st.subheader("Modalidades Existentes")
                    conn = sqlite3.connect('trabajo.db')
                    modalities_df = pd.read_sql_query("SELECT * FROM modalidades_tarea", conn)
                    conn.close()
                    
                    st.dataframe(modalities_df)
                    
                    # Formulario para editar modalidades
                    with st.expander("Editar Modalidad"):
                        if not modalities_df.empty:
                            modality_ids = modalities_df['id_modalidad'].tolist()
                            modality_names = modalities_df['modalidad'].tolist()
                            modality_options = [f"{mid} - {mname}" for mid, mname in zip(modality_ids, modality_names)]
                            
                            selected_modality_edit = st.selectbox("Seleccionar Modalidad para Editar", 
                                                                 options=modality_options, key="select_modality_edit")
                            if selected_modality_edit:
                                modality_id = int(selected_modality_edit.split(' - ')[0])
                                current_name = selected_modality_edit.split(' - ', 1)[1]
                                
                                new_modality_name = st.text_input("Nuevo Nombre de la Modalidad", 
                                                                 value=current_name, key="edit_modality_name")
                                
                                if st.button("Guardar Cambios", key="save_modality_edit"):
                                    if new_modality_name and new_modality_name != current_name:
                                        conn = sqlite3.connect('trabajo.db')
                                        c = conn.cursor()
                                        try:
                                            c.execute("UPDATE modalidades_tarea SET modalidad = ? WHERE id_modalidad = ?", 
                                                     (new_modality_name, modality_id))
                                            conn.commit()
                                            st.success(f"Modalidad actualizada de '{current_name}' a '{new_modality_name}'.")
                                            time.sleep(1)
                                            st.rerun()
                                        except sqlite3.IntegrityError:
                                            st.error("Ya existe una modalidad con ese nombre.")
                                        finally:
                                            conn.close()
                                    elif new_modality_name == current_name:
                                        st.info("No se detectaron cambios.")
                                    else:
                                        st.error("El nombre de la modalidad no puede estar vacío.")
                        else:
                            st.info("No hay modalidades para editar.")
                    
                    # Formulario para eliminar modalidades
                    with st.expander("Eliminar Modalidad"):
                        if not modalities_df.empty:
                            modality_ids = modalities_df['id_modalidad'].tolist()
                            modality_names = modalities_df['modalidad'].tolist()
                            modality_options = [f"{mid} - {mname}" for mid, mname in zip(modality_ids, modality_names)]
                            
                            selected_modality = st.selectbox("Seleccionar Modalidad", options=modality_options, key="select_modality_delete")
                            if selected_modality:
                                modality_id = int(selected_modality.split(' - ')[0])
                                
                                if st.button("Eliminar Modalidad", key="delete_modality_btn"):
                                    # Verificar si la modalidad está siendo usada en registros
                                    conn = sqlite3.connect('trabajo.db')
                                    c = conn.cursor()
                                    c.execute("SELECT COUNT(*) FROM registros WHERE id_modalidad = ?", (modality_id,))
                                    count = c.fetchone()[0]
                                    
                                    if count > 0:
                                        st.error(f"No se puede eliminar la modalidad porque está siendo usada en {count} registros.")
                                    else:
                                        c.execute("DELETE FROM modalidades_tarea WHERE id_modalidad = ?", (modality_id,))
                                        conn.commit()
                                        st.success("Modalidad eliminada exitosamente.")
                                        time.sleep(1)
                                        st.rerun()
                                    conn.close()
                        else:
                            st.info("No hay modalidades para eliminar.")
        else:
            # Interfaz para usuarios normales
            st.header("Sistema de Registro de Horas")
            
            # Crear pestañas para las diferentes funcionalidades
            tab_registro, tab_mis_registros = st.tabs(["📝 Registro de Horas", "📊 Mis Registros"])
            
            with tab_registro:
                st.subheader("Registrar Horas de Trabajo")
                
                # Formulario para registrar horas
                with st.form("registro_form"):
                    # Fecha
                    fecha = st.date_input("Fecha", value=datetime.today())
                    fecha_formateada = fecha.strftime('%d/%m/%y')
                    
                    # Obtener listas de técnicos, clientes, tipos y modalidades
                    conn = sqlite3.connect('trabajo.db')
                    tecnicos_df = pd.read_sql_query("SELECT * FROM tecnicos", conn)
                    clientes_df = pd.read_sql_query("SELECT * FROM clientes", conn)
                    tipos_df = pd.read_sql_query("SELECT * FROM tipos_tarea", conn)
                    modalidades_df = pd.read_sql_query("SELECT * FROM modalidades_tarea", conn)
                    conn.close()
                    
                    if tecnicos_df.empty or clientes_df.empty or tipos_df.empty or modalidades_df.empty:
                        st.warning("Faltan datos maestros. Contacta al administrador para que configure técnicos, clientes, tipos de tarea y modalidades.")
                        st.stop()
                    
                    # Selección de técnico
                    tecnico_options = tecnicos_df['nombre'].tolist()
                    
                    # Preseleccionar el técnico que coincide con el nombre del usuario actual
                    default_index = 0
                    if nombre_completo_usuario in tecnico_options:
                        default_index = tecnico_options.index(nombre_completo_usuario)
                    
                    tecnico_selected = st.selectbox("Técnico", options=tecnico_options, index=default_index)
                    
                    # Selección de cliente
                    cliente_options = clientes_df['nombre'].tolist()
                    cliente_selected = st.selectbox("Cliente", options=cliente_options)
                    
                    # Selección de tipo de tarea
                    tipo_options = tipos_df['descripcion'].tolist()
                    tipo_selected = st.selectbox("Tipo de Tarea", options=tipo_options)
                    
                    # Selección de modalidad
                    modalidad_options = modalidades_df['modalidad'].tolist()
                    modalidad_selected = st.selectbox("Modalidad", options=modalidad_options)
                    
                    # Campos adicionales
                    tarea_realizada = st.text_input("Tarea Realizada")
                    numero_ticket = st.text_input("Número de Ticket", value="NA")
                    tiempo = st.number_input("Tiempo (horas)", min_value=0.0, step=0.5)
                    descripcion = st.text_area("Descripción")
                    
                    # Mes (automático basado en la fecha)
                    mes = calendar.month_name[fecha.month]
                    
                    # Botón de envío
                    submitted = st.form_submit_button("Registrar Horas")
                    
                    if submitted:
                        if not tarea_realizada:
                            st.error("La tarea realizada es obligatoria.")
                        elif tiempo <= 0:
                            st.error("El tiempo debe ser mayor que cero.")
                        else:
                            conn = sqlite3.connect('trabajo.db')
                            c = conn.cursor()
                            
                            # Obtener IDs
                            c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (tecnico_selected,))
                            id_tecnico = c.fetchone()[0]
                            
                            c.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (cliente_selected,))
                            id_cliente = c.fetchone()[0]
                            
                            c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (tipo_selected,))
                            id_tipo = c.fetchone()[0]
                            
                            c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (modalidad_selected,))
                            id_modalidad = c.fetchone()[0]
                            
                            # Verificar si ya existe un registro con los mismos datos (para evitar duplicados)
                            c.execute('''
                                SELECT COUNT(*) FROM registros 
                                WHERE fecha = ? AND id_tecnico = ? AND id_cliente = ? AND id_tipo = ? 
                                AND id_modalidad = ? AND tarea_realizada = ? AND tiempo = ?
                            ''', (fecha_formateada, id_tecnico, id_cliente, id_tipo, id_modalidad, 
                                  tarea_realizada, tiempo))
                            
                            duplicate_count = c.fetchone()[0]
                            if duplicate_count > 0:
                                st.error("Ya existe un registro con estos mismos datos. No se puede crear un duplicado.")
                                conn.close()
                            else:
                                # Insertar registro
                                c.execute('''
                                    INSERT INTO registros 
                                    (fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
                                    numero_ticket, tiempo, descripcion, mes, usuario_id)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (
                                    fecha_formateada, id_tecnico, id_cliente, id_tipo, id_modalidad,
                                    tarea_realizada, numero_ticket, tiempo, descripcion, mes, st.session_state.user_id
                                ))
                                
                                conn.commit()
                                conn.close()
                                st.success("Horas registradas exitosamente.")
                                time.sleep(1)
                                st.rerun()
            
            with tab_mis_registros:
                st.subheader("Mis Registros de Horas")
                
                if nombre_completo_usuario:
                    # Obtener registros donde el técnico coincide con el nombre del usuario
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
                        WHERE t.nombre = ?
                    '''
                    user_registros_df = pd.read_sql_query(query, conn, params=(nombre_completo_usuario,))
                    conn.close()
                else:
                    # Si el usuario no tiene nombre/apellido, no puede tener registros como técnico.
                    st.warning("Por favor, completa tu nombre y apellido en tu perfil para ver tus registros.")
                    user_registros_df = pd.DataFrame()
                
                if not user_registros_df.empty:
                    # Mostrar estadísticas
                    total_horas = user_registros_df['tiempo'].sum()
                    st.metric("Total de Horas Registradas", f"{total_horas:.1f}")
                    
                    # --- Gráfico de horas por semana con navegación ---

                    # Inicializar el estado de la semana si no existe
                    if 'week_offset' not in st.session_state:
                        st.session_state.week_offset = 0

                    # Convertir la columna de fecha a datetime para poder filtrar
                    user_registros_df['fecha_dt'] = pd.to_datetime(user_registros_df['fecha'], format='%d/%m/%y', errors='coerce')
                    user_registros_df.dropna(subset=['fecha_dt'], inplace=True)

                    # --- Lógica de navegación ---
                    today = datetime.today()
                    start_of_this_week = today - timedelta(days=today.weekday())

                    def update_week_offset_from_calendar():
                        # Callback para el date_input que se ejecuta cuando cambia la fecha
                        selected_date = st.session_state.date_selector
                        start_of_selected_week_from_cal = selected_date - timedelta(days=selected_date.weekday())
                        
                        # Calcular el nuevo offset en semanas
                        new_offset = (start_of_selected_week_from_cal - start_of_this_week.date()).days // 7
                        st.session_state.week_offset = new_offset

                    # Calcular las fechas de inicio y fin de la semana a mostrar
                    start_of_selected_week = start_of_this_week + timedelta(weeks=st.session_state.week_offset)
                    end_of_selected_week = start_of_selected_week + timedelta(days=6)
                    
                    # Título dinámico para la semana
                    week_range_str = f"Semana del {start_of_selected_week.strftime('%d/%m/%Y')} al {end_of_selected_week.strftime('%d/%m/%Y')}"

                    # --- UI de navegación y título ---
                    st.subheader("Horas Trabajadas por Día de la Semana")

                    # Controles de navegación en una sola área
                    # Se ajustan las columnas para agrupar los botones y el texto
                    nav_cols = st.columns([2, 0.5, 1, 2.5, 1, 4], vertical_alignment="bottom")

                    with nav_cols[0]:
                        st.date_input(
                            "Ir a la semana de:",
                            value=start_of_selected_week,
                            key="date_selector",
                            on_change=update_week_offset_from_calendar,
                            max_value=today  # No permitir seleccionar fechas futuras
                        )
                    # nav_cols[1] es un espaciador

                    with nav_cols[2]:
                        if st.button("⬅️ Ant.", use_container_width=True, help="Semana Anterior"):
                            st.session_state.week_offset -= 1
                            st.rerun()

                    with nav_cols[3]:
                        st.markdown(f"<p style='text-align: center; font-weight: bold;'>{week_range_str}</p>", unsafe_allow_html=True)

                    with nav_cols[4]:
                        disable_next = st.session_state.week_offset == 0
                        if st.button("Sig. ➡️", disabled=disable_next, use_container_width=True, help="Semana Siguiente"):
                            st.session_state.week_offset += 1
                            st.rerun()

                    # Filtrar los registros para la semana seleccionada
                    weekly_df = user_registros_df[
                        (user_registros_df['fecha_dt'].dt.date >= start_of_selected_week.date()) &
                        (user_registros_df['fecha_dt'].dt.date <= end_of_selected_week.date())
                    ]

                    if not weekly_df.empty:
                        # Preparar datos para el gráfico
                        dias_es = {'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles', 'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'}
                        weekly_df['dia_semana'] = weekly_df['fecha_dt'].dt.day_name().map(dias_es)
                        horas_por_dia = weekly_df.groupby('dia_semana')['tiempo'].sum().reset_index()
                        
                        # Asegurar que todos los días de la semana estén presentes y en orden
                        dias_ordenados = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
                        dias_completos_df = pd.DataFrame({'dia_semana': dias_ordenados})
                        horas_por_dia_final = pd.merge(dias_completos_df, horas_por_dia, on='dia_semana', how='left').fillna(0)
                        
                        fig = px.bar(horas_por_dia_final, x='dia_semana', y='tiempo', labels={'dia_semana': 'Día de la Semana', 'tiempo': 'Horas Totales'})
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay registros para la semana seleccionada.")
                    
                    # Mostrar tabla de registros con opciones para editar/eliminar
                    st.subheader("Detalle de Registros")
                    st.dataframe(user_registros_df.drop(columns=['fecha_dt']))
                    
                    # Agregar funcionalidad para editar o eliminar registros
                    with st.expander("Editar o Eliminar Registro"):
                        if not user_registros_df.empty:
                            registro_ids = user_registros_df['id'].tolist()
                            registro_fechas = user_registros_df['fecha'].tolist()
                            registro_tareas = user_registros_df['tarea_realizada'].tolist()
                            registro_options = [f"{rid} - {rfecha} - {rtarea}" for rid, rfecha, rtarea in zip(registro_ids, registro_fechas, registro_tareas)]
                            
                            selected_registro = st.selectbox("Seleccionar Registro", options=registro_options, key="select_registro_edit_delete")
                            if selected_registro:
                                registro_id = int(selected_registro.split(' - ')[0])
                                
                                # Obtener datos del registro seleccionado
                                registro_seleccionado = user_registros_df[user_registros_df['id'] == registro_id].iloc[0]
                                
                                # Crear pestañas para editar o eliminar
                                edit_tab, delete_tab = st.tabs(["Editar", "Eliminar"])
                                
                                with edit_tab:
                                    # Formulario para editar el registro
                                    fecha_str = registro_seleccionado['fecha']
                                    try:
                                        fecha_obj = datetime.strptime(fecha_str, '%d/%m/%y')
                                    except ValueError:
                                        try:
                                            fecha_obj = datetime.strptime(fecha_str, '%d/%m/%Y')
                                        except ValueError:
                                            fecha_obj = datetime.today()
                                    
                                    fecha_edit = st.date_input("Fecha", value=fecha_obj, key="edit_fecha")
                                    fecha_formateada_edit = fecha_edit.strftime('%d/%m/%y')
                                    
                                    # Obtener listas de técnicos, clientes, tipos y modalidades
                                    conn = sqlite3.connect('trabajo.db')
                                    tecnicos_df = pd.read_sql_query("SELECT * FROM tecnicos", conn)
                                    clientes_df = pd.read_sql_query("SELECT * FROM clientes", conn)
                                    tipos_df = pd.read_sql_query("SELECT * FROM tipos_tarea", conn)
                                    modalidades_df = pd.read_sql_query("SELECT * FROM modalidades_tarea", conn)
                                    conn.close()
                                    
                                    # Selección de técnico (solo permitir el propio técnico para usuarios normales)
                                    tecnico_options = tecnicos_df['nombre'].tolist()
                                    if st.session_state.is_admin:
                                        tecnico_index = tecnico_options.index(registro_seleccionado['tecnico']) if registro_seleccionado['tecnico'] in tecnico_options else 0
                                        tecnico_selected_edit = st.selectbox("Técnico", options=tecnico_options, index=tecnico_index, key="edit_tecnico")
                                    else:
                                        # Para usuarios normales, solo pueden editar sus propios registros
                                        tecnico_selected_edit = nombre_completo_usuario
                                        st.info(f"Técnico: {tecnico_selected_edit} (no se puede cambiar)")
                                    
                                    # Selección de cliente
                                    cliente_options = clientes_df['nombre'].tolist()
                                    cliente_index = cliente_options.index(registro_seleccionado['cliente']) if registro_seleccionado['cliente'] in cliente_options else 0
                                    cliente_selected_edit = st.selectbox("Cliente", options=cliente_options, index=cliente_index, key="edit_cliente")
                                    
                                    # Selección de tipo de tarea
                                    tipo_options = tipos_df['descripcion'].tolist()
                                    tipo_index = tipo_options.index(registro_seleccionado['tipo_tarea']) if registro_seleccionado['tipo_tarea'] in tipo_options else 0
                                    tipo_selected_edit = st.selectbox("Tipo de Tarea", options=tipo_options, index=tipo_index, key="edit_tipo")
                                    
                                    # Selección de modalidad
                                    modalidad_options = modalidades_df['modalidad'].tolist()
                                    modalidad_index = modalidad_options.index(registro_seleccionado['modalidad']) if registro_seleccionado['modalidad'] in modalidad_options else 0
                                    modalidad_selected_edit = st.selectbox("Modalidad", options=modalidad_options, index=modalidad_index, key="edit_modalidad")
                                    
                                    # Campos adicionales
                                    tarea_realizada_edit = st.text_input("Tarea Realizada", value=registro_seleccionado['tarea_realizada'], key="edit_tarea")
                                    numero_ticket_edit = st.text_input("Número de Ticket", value=registro_seleccionado['numero_ticket'], key="edit_ticket")
                                    tiempo_edit = st.number_input("Tiempo (horas)", min_value=0.0, step=0.5, value=float(registro_seleccionado['tiempo']), key="edit_tiempo")
                                    descripcion_edit = st.text_area("Descripción", value=registro_seleccionado['descripcion'] if pd.notna(registro_seleccionado['descripcion']) else "", key="edit_descripcion")
                                    
                                    # Mes (automático basado en la fecha)
                                    mes_edit = calendar.month_name[fecha_edit.month]
                                    
                                    if st.button("Guardar Cambios", key="save_registro_edit"):
                                        if not tarea_realizada_edit:
                                            st.error("La tarea realizada es obligatoria.")
                                        elif tiempo_edit <= 0:
                                            st.error("El tiempo debe ser mayor que cero.")
                                        else:
                                            conn = sqlite3.connect('trabajo.db')
                                            c = conn.cursor()
                                            
                                            # Obtener IDs
                                            c.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (tecnico_selected_edit,))
                                            id_tecnico = c.fetchone()[0]
                                            
                                            c.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (cliente_selected_edit,))
                                            id_cliente = c.fetchone()[0]
                                            
                                            c.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (tipo_selected_edit,))
                                            id_tipo = c.fetchone()[0]
                                            
                                            c.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (modalidad_selected_edit,))
                                            id_modalidad = c.fetchone()[0]
                                            
                                            # Verificar si ya existe un registro con los mismos datos (para evitar duplicados)
                                            c.execute('''
                                                SELECT COUNT(*) FROM registros 
                                                WHERE fecha = ? AND id_tecnico = ? AND id_cliente = ? AND id_tipo = ? 
                                                AND id_modalidad = ? AND tarea_realizada = ? AND tiempo = ? AND id != ?
                                            ''', (fecha_formateada_edit, id_tecnico, id_cliente, id_tipo, id_modalidad, 
                                                  tarea_realizada_edit, tiempo_edit, registro_id))
                                            
                                            duplicate_count = c.fetchone()[0]
                                            if duplicate_count > 0:
                                                st.error("Ya existe un registro con estos mismos datos. No se puede crear un duplicado.")
                                            else:
                                                # Actualizar registro
                                                c.execute('''
                                                    UPDATE registros SET 
                                                    fecha = ?, id_tecnico = ?, id_cliente = ?, id_tipo = ?, id_modalidad = ?, 
                                                    tarea_realizada = ?, numero_ticket = ?, tiempo = ?, descripcion = ?, mes = ?
                                                    WHERE id = ?
                                                ''', (
                                                    fecha_formateada_edit, id_tecnico, id_cliente, id_tipo, id_modalidad,
                                                    tarea_realizada_edit, numero_ticket_edit, tiempo_edit, descripcion_edit, mes_edit, registro_id
                                                ))
                                                
                                                conn.commit()
                                                # Mostrar mensaje de éxito inmediatamente
                                                st.success(f"✅ Registro actualizado exitosamente. Se ha verificado que no existen duplicados.")
                                                # Esperar un momento antes de recargar para que el usuario vea el mensaje
                                                time.sleep(1)
                                                st.rerun()
                                            
                                            conn.close()
                                
                                with delete_tab:
                                    st.warning("¿Estás seguro de que deseas eliminar este registro? Esta acción no se puede deshacer.")
                                    if st.button("Eliminar Registro", key="delete_registro_btn"):
                                        conn = sqlite3.connect('trabajo.db')
                                        c = conn.cursor()
                                        
                                        # Verificar si el usuario tiene permiso para eliminar este registro
                                        if st.session_state.is_admin or registro_seleccionado['tecnico'] == nombre_completo_usuario:
                                            c.execute("DELETE FROM registros WHERE id = ?", (registro_id,))
                                            conn.commit()
                                            # Mostrar mensaje de éxito inmediatamente
                                            st.success(f"✅ Registro eliminado exitosamente. La entrada ha sido completamente removida del sistema.")
                                            # Esperar un momento antes de recargar para que el usuario vea el mensaje
                                            time.sleep(1.5)
                                            st.rerun()
                                        else:
                                            st.error("No tienes permiso para eliminar este registro.")
                                        
                                        conn.close()
                        else:
                            st.info("No hay registros para editar o eliminar.")
                else:
                    st.info("No tienes registros de horas todavía.")

if __name__ == "__main__":
    main()