import pytest
from modules import constants

def test_error_messages_exist():
    # Verificar que los mensajes de error existen
    assert isinstance(constants.ERROR_DUPLICATE_RECORD, str)
    assert isinstance(constants.ERROR_PASSWORDS_DONT_MATCH, str)
    assert isinstance(constants.ERROR_REQUIRED_FIELDS, str)
    
def test_success_messages_exist():
    # Verificar que los mensajes de éxito existen
    assert isinstance(constants.SUCCESS_PROFILE_UPDATED, str)
    assert isinstance(constants.SUCCESS_PASSWORD_UPDATED, str)
    assert isinstance(constants.SUCCESS_RECORD_CREATED, str)
    assert isinstance(constants.SUCCESS_RECORD_UPDATED, str)

def test_info_messages_exist():
    # Verificar que los mensajes de información existen
    assert isinstance(constants.INFO_PASSWORD_REQUIREMENTS, str)