import sqlite3
import pytest
from modules import database

def test_create_connection():
    conn = sqlite3.connect(":memory:")
    assert conn is not None
    conn.close()

def test_insert_and_query():
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE test (id INTEGER, name TEXT)")
    cursor.execute("INSERT INTO test VALUES (1, 'Ignacio')")
    conn.commit()

    cursor.execute("SELECT name FROM test WHERE id=1")
    result = cursor.fetchone()
    assert result[0] == "Ignacio"
    conn.close()