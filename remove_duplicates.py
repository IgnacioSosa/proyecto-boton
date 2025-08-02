import sqlite3
import pandas as pd

# Conectar a la base de datos
conn = sqlite3.connect('trabajo.db')

# Identificar registros duplicados
query = '''
SELECT id, fecha, id_tecnico, id_cliente, id_tipo, id_modalidad, tarea_realizada, tiempo
FROM registros
'''

# Cargar los datos en un DataFrame
df = pd.read_sql_query(query, conn)

# Mostrar el número total de registros antes de eliminar duplicados
total_antes = len(df)
print(f"Total de registros antes: {total_antes}")

# Identificar duplicados basados en todos los campos excepto el ID
duplicados = df.duplicated(subset=['fecha', 'id_tecnico', 'id_cliente', 'id_tipo', 'id_modalidad', 'tarea_realizada', 'tiempo'], keep='first')

# Obtener los IDs de los registros duplicados que se eliminarán
ids_a_eliminar = df[duplicados]['id'].tolist()

# Mostrar cuántos duplicados se encontraron
print(f"Registros duplicados encontrados: {len(ids_a_eliminar)}")

# Eliminar los duplicados de la base de datos
if ids_a_eliminar:
    # Crear una lista de IDs para la consulta SQL
    placeholders = ','.join(['?' for _ in ids_a_eliminar])
    
    # Ejecutar la consulta DELETE
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM registros WHERE id IN ({placeholders})", ids_a_eliminar)
    conn.commit()
    
    print(f"Se eliminaron {cursor.rowcount} registros duplicados.")
else:
    print("No se encontraron registros duplicados para eliminar.")

# Verificar el número total de registros después de eliminar duplicados
df_despues = pd.read_sql_query("SELECT COUNT(*) as total FROM registros", conn)
total_despues = df_despues['total'][0]
print(f"Total de registros después: {total_despues}")

# Cerrar la conexión
conn.close()

print("Proceso completado.")