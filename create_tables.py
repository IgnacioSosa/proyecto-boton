import sqlite3
import pandas as pd

# Importar la función init_db para inicializar la base de datos
from modules.database import init_db

# Inicializar la base de datos (esto creará la tabla usuarios)
init_db()

# Conectar a la base de datos
conn = sqlite3.connect('trabajo.db')
cursor = conn.cursor()

# Crear tabla de roles
cursor.execute('''
CREATE TABLE IF NOT EXISTS roles (
    id_rol INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    descripcion TEXT
)
''')

# Crear tabla de técnicos
cursor.execute('''
CREATE TABLE IF NOT EXISTS tecnicos (
    id_tecnico INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    usuario_id INTEGER REFERENCES usuarios(id)
)
''')

# Crear tabla de clientes
cursor.execute('''
CREATE TABLE IF NOT EXISTS clientes (
    id_cliente INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
)
''')

# Crear tabla de tipos de tarea
cursor.execute('''
CREATE TABLE IF NOT EXISTS tipos_tarea (
    id_tipo INTEGER PRIMARY KEY,
    descripcion TEXT NOT NULL UNIQUE
)
''')

# Crear tabla de modalidades de tarea
cursor.execute('''
CREATE TABLE IF NOT EXISTS modalidades_tarea (
    id_modalidad INTEGER PRIMARY KEY,
    modalidad TEXT NOT NULL UNIQUE
)
''')

# Crear tabla de relación entre tipos de tarea y roles
cursor.execute('''
CREATE TABLE IF NOT EXISTS tipos_tarea_roles (
    id INTEGER PRIMARY KEY,
    id_tipo INTEGER NOT NULL,
    id_rol INTEGER NOT NULL,
    FOREIGN KEY (id_tipo) REFERENCES tipos_tarea (id_tipo),
    FOREIGN KEY (id_rol) REFERENCES roles (id_rol),
    UNIQUE(id_tipo, id_rol)
)
''')

# Verificar si la columna rol_id ya existe en la tabla usuarios
cursor.execute("PRAGMA table_info(usuarios)")
columnas_usuarios = cursor.fetchall()
columna_rol_existe = any(col[1] == 'rol_id' for col in columnas_usuarios)

# Añadir la columna rol_id a la tabla usuarios si no existe
if not columna_rol_existe:
    cursor.execute('''
    ALTER TABLE usuarios ADD COLUMN rol_id INTEGER DEFAULT NULL
    REFERENCES roles(id_rol)
    ''')

# Verificar si la columna usuario_id ya existe en la tabla tecnicos
cursor.execute("PRAGMA table_info(tecnicos)")
columnas_tecnicos = cursor.fetchall()
columna_usuario_id_existe = any(col[1] == 'usuario_id' for col in columnas_tecnicos)

# Añadir la columna usuario_id a la tabla tecnicos si no existe
if not columna_usuario_id_existe:
    cursor.execute("ALTER TABLE tecnicos ADD COLUMN usuario_id INTEGER REFERENCES usuarios(id)")
    
    # Actualizar los técnicos existentes con sus usuarios correspondientes
    cursor.execute("SELECT id, nombre, apellido FROM usuarios WHERE nombre IS NOT NULL OR apellido IS NOT NULL")
    usuarios = cursor.fetchall()
    
    for user_id, nombre, apellido in usuarios:
        nombre_completo = f"{nombre or ''} {apellido or ''}".strip()
        if nombre_completo:
            cursor.execute("UPDATE tecnicos SET usuario_id = ? WHERE nombre = ?", (user_id, nombre_completo))

# Insertar roles predeterminados
cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'admin'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('admin', 'Administrador con acceso completo'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'tecnico'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('tecnico', 'Técnico con acceso a registros'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'sin_rol'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('sin_rol', 'Usuario sin acceso'))

# Actualizar usuarios administradores existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'admin') 
    WHERE is_admin = 1 AND rol_id IS NULL
''')

# Actualizar usuarios técnicos existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico') 
    WHERE is_admin = 0 AND rol_id IS NULL
''')

# Verificar si existe la tabla registros_old
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='registros_old'")
tabla_registros_old_existe = cursor.fetchone() is not None

# Solo realizar la migración si existe la tabla registros_old
if tabla_registros_old_existe:
    # Modificar la tabla de registros para usar las nuevas tablas como claves foráneas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS registros (
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
    )
    ''')

    # Obtener datos existentes
    cursor.execute("SELECT * FROM registros_old")
    registros = cursor.fetchall()

    # Extraer valores únicos para cada tabla
    tecnicos = set()
    clientes = set()
    tipos_tarea = set()
    modalidades = set()

    for registro in registros:
        tecnicos.add(registro[2])  # tecnico
        clientes.add(registro[3])  # cliente
        tipos_tarea.add(registro[5])  # tarea_realizada
        modalidades.add(registro[4])  # tipo_tarea (que ahora será modalidad)

    # Insertar valores únicos en las nuevas tablas
    for tecnico in tecnicos:
        try:
            cursor.execute("INSERT INTO tecnicos (nombre) VALUES (?)", (tecnico,))
        except sqlite3.IntegrityError:
            # El técnico ya existe, ignorar
            pass

    for cliente in clientes:
        try:
            cursor.execute("INSERT INTO clientes (nombre) VALUES (?)", (cliente,))
        except sqlite3.IntegrityError:
            # El cliente ya existe, ignorar
            pass

    for tipo in tipos_tarea:
        try:
            cursor.execute("INSERT INTO tipos_tarea (descripcion) VALUES (?)", (tipo,))
        except sqlite3.IntegrityError:
            # El tipo ya existe, ignorar
            pass

    for modalidad in modalidades:
        try:
            cursor.execute("INSERT INTO modalidades_tarea (modalidad) VALUES (?)", (modalidad,))
        except sqlite3.IntegrityError:
            # La modalidad ya existe, ignorar
            pass

    # Migrar datos a la nueva tabla de registros
    for registro in registros:
        # Obtener IDs de las tablas relacionadas
        cursor.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (registro[2],))
        id_tecnico = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (registro[3],))
        id_cliente = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (registro[5],))
        id_tipo = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (registro[4],))
        id_modalidad = cursor.fetchone()[0]
        
        # Insertar en la nueva tabla
        cursor.execute('''
        INSERT INTO registros 
        (id, fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
         numero_ticket, tiempo, descripcion, mes, usuario_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            registro[0],  # id
            registro[1],  # fecha
            id_tecnico,
            id_cliente,
            id_tipo,
            id_modalidad,
            registro[5],  # tarea_realizada
            registro[6],  # numero_ticket
            registro[7],  # tiempo
            registro[8],  # descripcion
            registro[9],  # mes
            registro[10]  # usuario_id
        ))

    # Eliminar la tabla antigua
    cursor.execute("DROP TABLE registros_old")

# Guardar cambios y cerrar conexión
conn.commit()

print("Tablas creadas y datos migrados exitosamente.")
print("Roles y columnas adicionales configurados correctamente.")

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'admin'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('admin', 'Administrador con acceso completo'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'tecnico'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('tecnico', 'Técnico con acceso a registros'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'sin_rol'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('sin_rol', 'Usuario sin acceso'))

# Actualizar usuarios administradores existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'admin') 
    WHERE is_admin = 1 AND rol_id IS NULL
''')

# Actualizar usuarios técnicos existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico') 
    WHERE is_admin = 0 AND rol_id IS NULL
''')

# Verificar si existe la tabla registros_old
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='registros_old'")
tabla_registros_old_existe = cursor.fetchone() is not None

# Solo realizar la migración si existe la tabla registros_old
if tabla_registros_old_existe:
    # Modificar la tabla de registros para usar las nuevas tablas como claves foráneas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS registros (
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
    )
    ''')

    # Obtener datos existentes
    cursor.execute("SELECT * FROM registros_old")
    registros = cursor.fetchall()

    # Extraer valores únicos para cada tabla
    tecnicos = set()
    clientes = set()
    tipos_tarea = set()
    modalidades = set()

    for registro in registros:
        tecnicos.add(registro[2])  # tecnico
        clientes.add(registro[3])  # cliente
        tipos_tarea.add(registro[5])  # tarea_realizada
        modalidades.add(registro[4])  # tipo_tarea (que ahora será modalidad)

    # Insertar valores únicos en las nuevas tablas
    for tecnico in tecnicos:
        try:
            cursor.execute("INSERT INTO tecnicos (nombre) VALUES (?)", (tecnico,))
        except sqlite3.IntegrityError:
            # El técnico ya existe, ignorar
            pass

    for cliente in clientes:
        try:
            cursor.execute("INSERT INTO clientes (nombre) VALUES (?)", (cliente,))
        except sqlite3.IntegrityError:
            # El cliente ya existe, ignorar
            pass

    for tipo in tipos_tarea:
        try:
            cursor.execute("INSERT INTO tipos_tarea (descripcion) VALUES (?)", (tipo,))
        except sqlite3.IntegrityError:
            # El tipo ya existe, ignorar
            pass

    for modalidad in modalidades:
        try:
            cursor.execute("INSERT INTO modalidades_tarea (modalidad) VALUES (?)", (modalidad,))
        except sqlite3.IntegrityError:
            # La modalidad ya existe, ignorar
            pass

    # Migrar datos a la nueva tabla de registros
    for registro in registros:
        # Obtener IDs de las tablas relacionadas
        cursor.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (registro[2],))
        id_tecnico = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (registro[3],))
        id_cliente = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (registro[5],))
        id_tipo = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (registro[4],))
        id_modalidad = cursor.fetchone()[0]
        
        # Insertar en la nueva tabla
        cursor.execute('''
        INSERT INTO registros 
        (id, fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
         numero_ticket, tiempo, descripcion, mes, usuario_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            registro[0],  # id
            registro[1],  # fecha
            id_tecnico,
            id_cliente,
            id_tipo,
            id_modalidad,
            registro[5],  # tarea_realizada
            registro[6],  # numero_ticket
            registro[7],  # tiempo
            registro[8],  # descripcion
            registro[9],  # mes
            registro[10]  # usuario_id
        ))

    # Eliminar la tabla antigua
    cursor.execute("DROP TABLE registros_old")

# Guardar cambios y cerrar conexión
conn.commit()

print("Tablas creadas y datos migrados exitosamente.")
print("Roles y columnas adicionales configurados correctamente.")

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'admin'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('admin', 'Administrador con acceso completo'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'tecnico'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('tecnico', 'Técnico con acceso a registros'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'sin_rol'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('sin_rol', 'Usuario sin acceso'))

# Actualizar usuarios administradores existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'admin') 
    WHERE is_admin = 1 AND rol_id IS NULL
''')

# Actualizar usuarios técnicos existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico') 
    WHERE is_admin = 0 AND rol_id IS NULL
''')

# Verificar si existe la tabla registros_old
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='registros_old'")
tabla_registros_old_existe = cursor.fetchone() is not None

# Solo realizar la migración si existe la tabla registros_old
if tabla_registros_old_existe:
    # Modificar la tabla de registros para usar las nuevas tablas como claves foráneas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS registros (
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
    )
    ''')

    # Obtener datos existentes
    cursor.execute("SELECT * FROM registros_old")
    registros = cursor.fetchall()

    # Extraer valores únicos para cada tabla
    tecnicos = set()
    clientes = set()
    tipos_tarea = set()
    modalidades = set()

    for registro in registros:
        tecnicos.add(registro[2])  # tecnico
        clientes.add(registro[3])  # cliente
        tipos_tarea.add(registro[5])  # tarea_realizada
        modalidades.add(registro[4])  # tipo_tarea (que ahora será modalidad)

    # Insertar valores únicos en las nuevas tablas
    for tecnico in tecnicos:
        try:
            cursor.execute("INSERT INTO tecnicos (nombre) VALUES (?)", (tecnico,))
        except sqlite3.IntegrityError:
            # El técnico ya existe, ignorar
            pass

    for cliente in clientes:
        try:
            cursor.execute("INSERT INTO clientes (nombre) VALUES (?)", (cliente,))
        except sqlite3.IntegrityError:
            # El cliente ya existe, ignorar
            pass

    for tipo in tipos_tarea:
        try:
            cursor.execute("INSERT INTO tipos_tarea (descripcion) VALUES (?)", (tipo,))
        except sqlite3.IntegrityError:
            # El tipo ya existe, ignorar
            pass

    for modalidad in modalidades:
        try:
            cursor.execute("INSERT INTO modalidades_tarea (modalidad) VALUES (?)", (modalidad,))
        except sqlite3.IntegrityError:
            # La modalidad ya existe, ignorar
            pass

    # Migrar datos a la nueva tabla de registros
    for registro in registros:
        # Obtener IDs de las tablas relacionadas
        cursor.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (registro[2],))
        id_tecnico = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (registro[3],))
        id_cliente = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (registro[5],))
        id_tipo = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (registro[4],))
        id_modalidad = cursor.fetchone()[0]
        
        # Insertar en la nueva tabla
        cursor.execute('''
        INSERT INTO registros 
        (id, fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
         numero_ticket, tiempo, descripcion, mes, usuario_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            registro[0],  # id
            registro[1],  # fecha
            id_tecnico,
            id_cliente,
            id_tipo,
            id_modalidad,
            registro[5],  # tarea_realizada
            registro[6],  # numero_ticket
            registro[7],  # tiempo
            registro[8],  # descripcion
            registro[9],  # mes
            registro[10]  # usuario_id
        ))

    # Eliminar la tabla antigua
    cursor.execute("DROP TABLE registros_old")

# Guardar cambios y cerrar conexión
conn.commit()

print("Tablas creadas y datos migrados exitosamente.")
print("Roles y columnas adicionales configurados correctamente.")

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'admin'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('admin', 'Administrador con acceso completo'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'tecnico'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('tecnico', 'Técnico con acceso a registros'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'sin_rol'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('sin_rol', 'Usuario sin acceso'))

# Actualizar usuarios administradores existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'admin') 
    WHERE is_admin = 1 AND rol_id IS NULL
''')

# Actualizar usuarios técnicos existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico') 
    WHERE is_admin = 0 AND rol_id IS NULL
''')

# Verificar si existe la tabla registros_old
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='registros_old'")
tabla_registros_old_existe = cursor.fetchone() is not None

# Solo realizar la migración si existe la tabla registros_old
if tabla_registros_old_existe:
    # Modificar la tabla de registros para usar las nuevas tablas como claves foráneas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS registros (
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
    )
    ''')

    # Obtener datos existentes
    cursor.execute("SELECT * FROM registros_old")
    registros = cursor.fetchall()

    # Extraer valores únicos para cada tabla
    tecnicos = set()
    clientes = set()
    tipos_tarea = set()
    modalidades = set()

    for registro in registros:
        tecnicos.add(registro[2])  # tecnico
        clientes.add(registro[3])  # cliente
        tipos_tarea.add(registro[5])  # tarea_realizada
        modalidades.add(registro[4])  # tipo_tarea (que ahora será modalidad)

    # Insertar valores únicos en las nuevas tablas
    for tecnico in tecnicos:
        try:
            cursor.execute("INSERT INTO tecnicos (nombre) VALUES (?)", (tecnico,))
        except sqlite3.IntegrityError:
            # El técnico ya existe, ignorar
            pass

    for cliente in clientes:
        try:
            cursor.execute("INSERT INTO clientes (nombre) VALUES (?)", (cliente,))
        except sqlite3.IntegrityError:
            # El cliente ya existe, ignorar
            pass

    for tipo in tipos_tarea:
        try:
            cursor.execute("INSERT INTO tipos_tarea (descripcion) VALUES (?)", (tipo,))
        except sqlite3.IntegrityError:
            # El tipo ya existe, ignorar
            pass

    for modalidad in modalidades:
        try:
            cursor.execute("INSERT INTO modalidades_tarea (modalidad) VALUES (?)", (modalidad,))
        except sqlite3.IntegrityError:
            # La modalidad ya existe, ignorar
            pass

    # Migrar datos a la nueva tabla de registros
    for registro in registros:
        # Obtener IDs de las tablas relacionadas
        cursor.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (registro[2],))
        id_tecnico = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (registro[3],))
        id_cliente = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (registro[5],))
        id_tipo = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (registro[4],))
        id_modalidad = cursor.fetchone()[0]
        
        # Insertar en la nueva tabla
        cursor.execute('''
        INSERT INTO registros 
        (id, fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
         numero_ticket, tiempo, descripcion, mes, usuario_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            registro[0],  # id
            registro[1],  # fecha
            id_tecnico,
            id_cliente,
            id_tipo,
            id_modalidad,
            registro[5],  # tarea_realizada
            registro[6],  # numero_ticket
            registro[7],  # tiempo
            registro[8],  # descripcion
            registro[9],  # mes
            registro[10]  # usuario_id
        ))

    # Eliminar la tabla antigua
    cursor.execute("DROP TABLE registros_old")

# Guardar cambios pero NO cerrar la conexión todavía
conn.commit()

print("Tablas creadas y datos migrados exitosamente.")
print("Roles y columnas adicionales configurados correctamente.")

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'admin'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('admin', 'Administrador con acceso completo'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'tecnico'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('tecnico', 'Técnico con acceso a registros'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'sin_rol'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('sin_rol', 'Usuario sin acceso'))

# Actualizar usuarios administradores existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'admin') 
    WHERE is_admin = 1 AND rol_id IS NULL
''')

# Actualizar usuarios técnicos existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico') 
    WHERE is_admin = 0 AND rol_id IS NULL
''')

# Verificar si existe la tabla registros_old
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='registros_old'")
tabla_registros_old_existe = cursor.fetchone() is not None

# Solo realizar la migración si existe la tabla registros_old
if tabla_registros_old_existe:
    # Modificar la tabla de registros para usar las nuevas tablas como claves foráneas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS registros (
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
    )
    ''')

    # Obtener datos existentes
    cursor.execute("SELECT * FROM registros_old")
    registros = cursor.fetchall()

    # Extraer valores únicos para cada tabla
    tecnicos = set()
    clientes = set()
    tipos_tarea = set()
    modalidades = set()

    for registro in registros:
        tecnicos.add(registro[2])  # tecnico
        clientes.add(registro[3])  # cliente
        tipos_tarea.add(registro[5])  # tarea_realizada
        modalidades.add(registro[4])  # tipo_tarea (que ahora será modalidad)

    # Insertar valores únicos en las nuevas tablas
    for tecnico in tecnicos:
        try:
            cursor.execute("INSERT INTO tecnicos (nombre) VALUES (?)", (tecnico,))
        except sqlite3.IntegrityError:
            # El técnico ya existe, ignorar
            pass

    for cliente in clientes:
        try:
            cursor.execute("INSERT INTO clientes (nombre) VALUES (?)", (cliente,))
        except sqlite3.IntegrityError:
            # El cliente ya existe, ignorar
            pass

    for tipo in tipos_tarea:
        try:
            cursor.execute("INSERT INTO tipos_tarea (descripcion) VALUES (?)", (tipo,))
        except sqlite3.IntegrityError:
            # El tipo ya existe, ignorar
            pass

    for modalidad in modalidades:
        try:
            cursor.execute("INSERT INTO modalidades_tarea (modalidad) VALUES (?)", (modalidad,))
        except sqlite3.IntegrityError:
            # La modalidad ya existe, ignorar
            pass

    # Migrar datos a la nueva tabla de registros
    for registro in registros:
        # Obtener IDs de las tablas relacionadas
        cursor.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (registro[2],))
        id_tecnico = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (registro[3],))
        id_cliente = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (registro[5],))
        id_tipo = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (registro[4],))
        id_modalidad = cursor.fetchone()[0]
        
        # Insertar en la nueva tabla
        cursor.execute('''
        INSERT INTO registros 
        (id, fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
         numero_ticket, tiempo, descripcion, mes, usuario_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            registro[0],  # id
            registro[1],  # fecha
            id_tecnico,
            id_cliente,
            id_tipo,
            id_modalidad,
            registro[5],  # tarea_realizada
            registro[6],  # numero_ticket
            registro[7],  # tiempo
            registro[8],  # descripcion
            registro[9],  # mes
            registro[10]  # usuario_id
        ))

    # Eliminar la tabla antigua
    cursor.execute("DROP TABLE registros_old")

# Guardar cambios y cerrar conexión
conn.commit()

print("Tablas creadas y datos migrados exitosamente.")
print("Roles y columnas adicionales configurados correctamente.")

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'admin'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('admin', 'Administrador con acceso completo'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'tecnico'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('tecnico', 'Técnico con acceso a registros'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'sin_rol'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('sin_rol', 'Usuario sin acceso'))

# Actualizar usuarios administradores existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'admin') 
    WHERE is_admin = 1 AND rol_id IS NULL
''')

# Actualizar usuarios técnicos existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico') 
    WHERE is_admin = 0 AND rol_id IS NULL
''')

# Verificar si existe la tabla registros_old
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='registros_old'")
tabla_registros_old_existe = cursor.fetchone() is not None

# Solo realizar la migración si existe la tabla registros_old
if tabla_registros_old_existe:
    # Modificar la tabla de registros para usar las nuevas tablas como claves foráneas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS registros (
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
    )
    ''')

    # Obtener datos existentes
    cursor.execute("SELECT * FROM registros_old")
    registros = cursor.fetchall()

    # Extraer valores únicos para cada tabla
    tecnicos = set()
    clientes = set()
    tipos_tarea = set()
    modalidades = set()

    for registro in registros:
        tecnicos.add(registro[2])  # tecnico
        clientes.add(registro[3])  # cliente
        tipos_tarea.add(registro[5])  # tarea_realizada
        modalidades.add(registro[4])  # tipo_tarea (que ahora será modalidad)

    # Insertar valores únicos en las nuevas tablas
    for tecnico in tecnicos:
        try:
            cursor.execute("INSERT INTO tecnicos (nombre) VALUES (?)", (tecnico,))
        except sqlite3.IntegrityError:
            # El técnico ya existe, ignorar
            pass

    for cliente in clientes:
        try:
            cursor.execute("INSERT INTO clientes (nombre) VALUES (?)", (cliente,))
        except sqlite3.IntegrityError:
            # El cliente ya existe, ignorar
            pass

    for tipo in tipos_tarea:
        try:
            cursor.execute("INSERT INTO tipos_tarea (descripcion) VALUES (?)", (tipo,))
        except sqlite3.IntegrityError:
            # El tipo ya existe, ignorar
            pass

    for modalidad in modalidades:
        try:
            cursor.execute("INSERT INTO modalidades_tarea (modalidad) VALUES (?)", (modalidad,))
        except sqlite3.IntegrityError:
            # La modalidad ya existe, ignorar
            pass

    # Migrar datos a la nueva tabla de registros
    for registro in registros:
        # Obtener IDs de las tablas relacionadas
        cursor.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (registro[2],))
        id_tecnico = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (registro[3],))
        id_cliente = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (registro[5],))
        id_tipo = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (registro[4],))
        id_modalidad = cursor.fetchone()[0]
        
        # Insertar en la nueva tabla
        cursor.execute('''
        INSERT INTO registros 
        (id, fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
         numero_ticket, tiempo, descripcion, mes, usuario_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            registro[0],  # id
            registro[1],  # fecha
            id_tecnico,
            id_cliente,
            id_tipo,
            id_modalidad,
            registro[5],  # tarea_realizada
            registro[6],  # numero_ticket
            registro[7],  # tiempo
            registro[8],  # descripcion
            registro[9],  # mes
            registro[10]  # usuario_id
        ))

    # Eliminar la tabla antigua
    cursor.execute("DROP TABLE registros_old")

# Guardar cambios y cerrar conexión
conn.commit()

print("Tablas creadas y datos migrados exitosamente.")
print("Roles y columnas adicionales configurados correctamente.")

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'admin'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('admin', 'Administrador con acceso completo'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'tecnico'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('tecnico', 'Técnico con acceso a registros'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'sin_rol'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('sin_rol', 'Usuario sin acceso'))

# Actualizar usuarios administradores existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'admin') 
    WHERE is_admin = 1 AND rol_id IS NULL
''')

# Actualizar usuarios técnicos existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico') 
    WHERE is_admin = 0 AND rol_id IS NULL
''')

# Verificar si existe la tabla registros_old
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='registros_old'")
tabla_registros_old_existe = cursor.fetchone() is not None

# Solo realizar la migración si existe la tabla registros_old
if tabla_registros_old_existe:
    # Modificar la tabla de registros para usar las nuevas tablas como claves foráneas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS registros (
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
    )
    ''')

    # Obtener datos existentes
    cursor.execute("SELECT * FROM registros_old")
    registros = cursor.fetchall()

    # Extraer valores únicos para cada tabla
    tecnicos = set()
    clientes = set()
    tipos_tarea = set()
    modalidades = set()

    for registro in registros:
        tecnicos.add(registro[2])  # tecnico
        clientes.add(registro[3])  # cliente
        tipos_tarea.add(registro[5])  # tarea_realizada
        modalidades.add(registro[4])  # tipo_tarea (que ahora será modalidad)

    # Insertar valores únicos en las nuevas tablas
    for tecnico in tecnicos:
        try:
            cursor.execute("INSERT INTO tecnicos (nombre) VALUES (?)", (tecnico,))
        except sqlite3.IntegrityError:
            # El técnico ya existe, ignorar
            pass

    for cliente in clientes:
        try:
            cursor.execute("INSERT INTO clientes (nombre) VALUES (?)", (cliente,))
        except sqlite3.IntegrityError:
            # El cliente ya existe, ignorar
            pass

    for tipo in tipos_tarea:
        try:
            cursor.execute("INSERT INTO tipos_tarea (descripcion) VALUES (?)", (tipo,))
        except sqlite3.IntegrityError:
            # El tipo ya existe, ignorar
            pass

    for modalidad in modalidades:
        try:
            cursor.execute("INSERT INTO modalidades_tarea (modalidad) VALUES (?)", (modalidad,))
        except sqlite3.IntegrityError:
            # La modalidad ya existe, ignorar
            pass

    # Migrar datos a la nueva tabla de registros
    for registro in registros:
        # Obtener IDs de las tablas relacionadas
        cursor.execute("SELECT id_tecnico FROM tecnicos WHERE nombre = ?", (registro[2],))
        id_tecnico = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_cliente FROM clientes WHERE nombre = ?", (registro[3],))
        id_cliente = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_tipo FROM tipos_tarea WHERE descripcion = ?", (registro[5],))
        id_tipo = cursor.fetchone()[0]
        
        cursor.execute("SELECT id_modalidad FROM modalidades_tarea WHERE modalidad = ?", (registro[4],))
        id_modalidad = cursor.fetchone()[0]
        
        # Insertar en la nueva tabla
        cursor.execute('''
        INSERT INTO registros 
        (id, fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, 
         numero_ticket, tiempo, descripcion, mes, usuario_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            registro[0],  # id
            registro[1],  # fecha
            id_tecnico,
            id_cliente,
            id_tipo,
            id_modalidad,
            registro[5],  # tarea_realizada
            registro[6],  # numero_ticket
            registro[7],  # tiempo
            registro[8],  # descripcion
            registro[9],  # mes
            registro[10]  # usuario_id
        ))

    # Eliminar la tabla antigua
    cursor.execute("DROP TABLE registros_old")

# Guardar cambios y cerrar conexión
conn.commit()

print("Tablas creadas y datos migrados exitosamente.")
print("Roles y columnas adicionales configurados correctamente.")

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'admin'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('admin', 'Administrador con acceso completo'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'tecnico'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('tecnico', 'Técnico con acceso a registros'))

cursor.execute("SELECT COUNT(*) FROM roles WHERE nombre = 'sin_rol'")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO roles (nombre, descripcion) VALUES (?, ?)", 
                  ('sin_rol', 'Usuario sin acceso'))

# Actualizar usuarios administradores existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'admin') 
    WHERE is_admin = 1 AND rol_id IS NULL
''')

# Actualizar usuarios técnicos existentes
cursor.execute('''
    UPDATE usuarios 
    SET rol_id = (SELECT id_rol FROM roles WHERE nombre = 'tecnico') 
    WHERE is_admin = 0 AND rol_id IS NULL
''')

print("Roles y columnas adicionales configurados correctamente.")
# Guardar cambios y cerrar conexión
conn.commit()

# Después de todas las operaciones SQL, cerrar la conexión
conn.close()