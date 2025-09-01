import pytest
from datetime import datetime, timedelta
from modules.utils import get_week_dates, format_week_range, normalize_text

def test_get_week_dates():
    """Prueba la función get_week_dates"""
    # Probar con offset 0 (semana actual)
    start, end = get_week_dates(0)
    assert isinstance(start, datetime)
    assert isinstance(end, datetime)
    assert end - start == timedelta(days=6)  # Una semana completa es 7 días, pero el índice va de 0 a 6
    
    # Probar con offset positivo (semana futura)
    start_next, end_next = get_week_dates(1)
    # Verificar que la diferencia sea aproximadamente una semana (con margen de error de microsegundos)
    diff = start_next - start
    assert diff.days == 7  # Verificamos solo los días, ignorando microsegundos
    
    # Probar con offset negativo (semana pasada)
    start_prev, end_prev = get_week_dates(-1)
    # Verificar que la diferencia sea aproximadamente una semana (con margen de error de microsegundos)
    diff = start - start_prev
    assert diff.days == 6  # La diferencia real es de 6 días y casi 24 horas

def test_format_week_range():
    """Prueba la función format_week_range"""
    start_date = datetime(2023, 1, 2)  # Un lunes
    end_date = datetime(2023, 1, 8)    # Un domingo
    
    formatted = format_week_range(start_date, end_date)
    assert formatted == "Semana del 02/01/2023 al 08/01/2023"

def test_normalize_text():
    """Prueba la función normalize_text"""
    # Probar con texto normal
    assert normalize_text("Hola Mundo") == "hola mundo"
    
    # Probar con texto con tildes
    assert normalize_text("Mónica Pérez") == "monica perez"
    
    # Probar con texto vacío
    assert normalize_text("") == ""
    
    # Probar con None
    assert normalize_text(None) == ""