import sqlite3
import pandas as pd

# Conectar a la base de datos
conn = sqlite3.connect('trabajo.db')
cursor = conn.cursor()

# Crear tabla de técnicos
cursor.execute('''
CREATE TABLE IF NOT EXISTS tecnicos (
    id_tecnico INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
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

# Modificar la tabla de registros para usar las nuevas tablas como claves foráneas
cursor.execute('''
ALTER TABLE registros RENAME TO registros_old
''')

cursor.execute('''
CREATE TABLE registros (
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
    cursor.execute("INSERT INTO tecnicos (nombre) VALUES (?)", (tecnico,))

for cliente in clientes:
    cursor.execute("INSERT INTO clientes (nombre) VALUES (?)", (cliente,))

for tipo in tipos_tarea:
    cursor.execute("INSERT INTO tipos_tarea (descripcion) VALUES (?)", (tipo,))

for modalidad in modalidades:
    cursor.execute("INSERT INTO modalidades_tarea (modalidad) VALUES (?)", (modalidad,))

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
conn.close()

print("Tablas creadas y datos migrados exitosamente.")