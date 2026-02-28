import pytest
import psycopg2
from modules import database as db

def test_get_connection():
    """Prueba que la función get_connection devuelve una conexión válida"""
    if not db.test_connection():
        pytest.skip("No hay conexión disponible a PostgreSQL para ejecutar este test.")
    conn = db.get_connection()
    assert isinstance(conn, psycopg2.extensions.connection)
    conn.close()

def test_init_db():
    """Prueba que la función init_db crea las tablas necesarias"""
    if not db.test_connection():
        pytest.skip("No hay conexión disponible a PostgreSQL para ejecutar este test.")
    # Inicializar la base de datos
    db.init_db()
    
    # Verificar que las tablas existen
    conn = db.get_connection()
    c = conn.cursor()
    
    # Consultar las tablas existentes
    c.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
    """)
    tables = [row[0] for row in c.fetchall()]
    
    # Verificar que las tablas principales existen
    assert 'usuarios' in tables
    assert 'roles' in tables
    assert 'grupos' in tables
    
    conn.close()
