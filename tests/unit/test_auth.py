import pytest
from modules.auth import validate_password, hash_password, verify_password

def test_validate_password():
    # Test para contraseña válida con formato estándar
    is_valid, messages = validate_password("Password1!")
    assert is_valid == True
    assert messages == ["Contraseña válida"]
    
    # Test para contraseña válida con formato Nombre_Apellido.
    is_valid, messages = validate_password("Nombre_Apellido.1")
    assert is_valid == True
    assert messages == ["Contraseña válida"]
    
    # Test para contraseña inválida (muy corta)
    is_valid, messages = validate_password("pass")
    assert is_valid == False
    assert "La contraseña debe tener al menos 8 caracteres." in messages

def test_hash_and_verify_password():
    password = "TestPassword123!"
    hashed = hash_password(password)
    
    # Verificar que el hash no es igual a la contraseña original
    assert hashed != password.encode('utf-8')
    
    # Verificar que verify_password funciona correctamente
    assert verify_password(password, hashed) == True
    assert verify_password("WrongPassword", hashed) == False
