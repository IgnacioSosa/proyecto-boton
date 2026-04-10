import pytest
from modules import constants
from modules.config import (
    SMTP_CONFIG,
    NOTIFICATION_POLICIES_CONFIG,
    NOTIFICATION_POLICY_DEFINITIONS,
    NOTIFICATION_POLICY_FREQUENCIES,
    NOTIFICATION_POLICY_WEEKDAYS,
    NOTIFICATION_TEMPLATE_CONFIG,
    NOTIFICATION_TEMPLATES_CONFIG,
    NOTIFICATION_TEMPLATE_DEFINITIONS,
    encode_env_multiline,
    encode_notification_policies,
    encode_notification_templates,
    get_notification_policy,
    get_notification_template,
)

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

def test_smtp_config_shape():
    assert isinstance(SMTP_CONFIG, dict)
    assert isinstance(SMTP_CONFIG["enabled"], bool)
    assert isinstance(SMTP_CONFIG["host"], str)
    assert isinstance(SMTP_CONFIG["port"], str)
    assert isinstance(SMTP_CONFIG["user"], str)
    assert isinstance(SMTP_CONFIG["password"], str)
    assert isinstance(SMTP_CONFIG["from_email"], str)
    assert isinstance(SMTP_CONFIG["from_name"], str)
    assert SMTP_CONFIG["security"] in {"tls", "ssl"}

def test_notification_template_body_encoding():
    body = "Linea 1\nLinea 2\n{detalle}"
    encoded = encode_env_multiline(body)
    assert encoded == "Linea 1\\nLinea 2\\n{detalle}"
    assert isinstance(NOTIFICATION_TEMPLATE_CONFIG["subject"], str)
    assert isinstance(NOTIFICATION_TEMPLATE_CONFIG["body"], str)

def test_notification_templates_config_shape():
    assert isinstance(NOTIFICATION_TEMPLATES_CONFIG, dict)
    assert set(NOTIFICATION_TEMPLATE_DEFINITIONS).issubset(set(NOTIFICATION_TEMPLATES_CONFIG))
    for template_key, definition in NOTIFICATION_TEMPLATE_DEFINITIONS.items():
        template = NOTIFICATION_TEMPLATES_CONFIG[template_key]
        assert isinstance(definition["label"], str)
        assert isinstance(definition["description"], str)
        assert isinstance(definition["placeholders"], list)
        assert isinstance(template["enabled"], bool)
        assert isinstance(template["subject"], str)
        assert isinstance(template["body"], str)

def test_notification_template_fallback_and_encoding():
    encoded = encode_notification_templates({
        "cliente_solicitud_aprobada": {
            "enabled": False,
            "subject": "Aprobada {cliente}",
            "body": "Hola {nombre}",
        }
    })
    assert isinstance(encoded, str)
    template = get_notification_template("evento_inexistente")
    assert isinstance(template["enabled"], bool)
    assert isinstance(template["subject"], str)
    assert isinstance(template["body"], str)

def test_notification_policies_config_shape():
    assert isinstance(NOTIFICATION_POLICIES_CONFIG, dict)
    assert set(NOTIFICATION_POLICY_DEFINITIONS).issubset(set(NOTIFICATION_POLICIES_CONFIG))
    assert isinstance(NOTIFICATION_POLICY_FREQUENCIES, dict)
    assert isinstance(NOTIFICATION_POLICY_WEEKDAYS, dict)
    for policy_key, definition in NOTIFICATION_POLICY_DEFINITIONS.items():
        policy = NOTIFICATION_POLICIES_CONFIG[policy_key]
        assert isinstance(definition["label"], str)
        assert isinstance(definition["description"], str)
        assert isinstance(definition["allowed_frequencies"], list)
        assert policy["frequency"] in definition["allowed_frequencies"]
        assert isinstance(policy["enabled"], bool)
        assert isinstance(policy["email_enabled"], bool)
        assert isinstance(policy["send_time"], str)
        assert policy["weekday"] in NOTIFICATION_POLICY_WEEKDAYS

def test_notification_policy_fallback_and_encoding():
    encoded = encode_notification_policies({
        "dia_pendiente_carga": {
            "enabled": True,
            "email_enabled": True,
            "frequency": "daily",
            "send_time": "18:30",
            "weekday": "friday",
        }
    })
    assert isinstance(encoded, str)
    policy = get_notification_policy("evento_inexistente")
    assert isinstance(policy["enabled"], bool)
    assert isinstance(policy["email_enabled"], bool)
    assert isinstance(policy["frequency"], str)
    assert isinstance(policy["send_time"], str)
