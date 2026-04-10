import pytest
import psycopg2
from datetime import datetime
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


def test_notification_policy_due_now_daily():
    policy = {"frequency": "daily", "send_time": "09:30"}
    assert db._notification_policy_due_now(policy, datetime(2026, 3, 27, 9, 30)) is True
    assert db._notification_policy_due_now(policy, datetime(2026, 3, 27, 9, 29)) is False


def test_notification_policy_due_now_weekly():
    policy = {"frequency": "weekly", "send_time": "17:00", "weekday": "friday"}
    assert db._notification_policy_due_now(policy, datetime(2026, 3, 27, 17, 0)) is True
    assert db._notification_policy_due_now(policy, datetime(2026, 3, 26, 17, 0)) is False


def test_send_test_notification_email_uses_smtp_account(monkeypatch):
    captured = {}

    monkeypatch.setitem(db.SMTP_CONFIG, "enabled", True)
    monkeypatch.setitem(db.SMTP_CONFIG, "host", "smtp.gmail.com")
    monkeypatch.setitem(db.SMTP_CONFIG, "port", "587")
    monkeypatch.setitem(db.SMTP_CONFIG, "security", "tls")
    monkeypatch.setitem(db.SMTP_CONFIG, "from_email", "remitente@example.com")
    monkeypatch.setitem(db.SMTP_CONFIG, "user", "admin@example.com")

    def fake_send_email(recipient_email, subject, body):
        captured["recipient_email"] = recipient_email
        captured["subject"] = subject
        captured["body"] = body

    monkeypatch.setattr(db, "_notification_send_email", fake_send_email)

    recipient = db.send_test_notification_email()

    assert recipient == "admin@example.com"
    assert captured["recipient_email"] == "admin@example.com"
    assert "Prueba de correo SMTP" in captured["subject"]
    assert "SIGO" in captured["body"]
