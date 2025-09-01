import pytest
import sqlite3
from modules.database import get_connection, DB_PATH, init_db

def test_get_connection():
    """Prueba que la función get_connection devuelve una conexión válida"""
    conn = get_connection()
    assert isinstance(conn, sqlite3.Connection)
    conn.close()

def test_init_db():
    """Prueba que la función init_db crea las tablas necesarias"""
    # Inicializar la base de datos
    init_db()
    
    # Verificar que las tablas existen
    conn = get_connection()
    c = conn.cursor()
    
    # Consultar las tablas existentes
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in c.fetchall()]
    
    # Verificar que las tablas principales existen
    assert 'usuarios' in tables
    assert 'roles' in tables
    assert 'grupos' in tables
    
    conn.close()