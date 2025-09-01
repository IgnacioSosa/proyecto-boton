import types
import pandas as pd
import pytest
from modules import utils
from datetime import datetime

def test_normalize_text():
    # Probar normalización de texto con tildes
    result = utils.normalize_text("Héllò Wórld")
    assert result == "hello world"
    
    # Probar con texto vacío
    assert utils.normalize_text("") == ""
    
    # Probar con None
    assert utils.normalize_text(None) == ""

def test_normalize_sector_name():
    # Probar normalización de sector
    result = utils.normalize_sector_name("Tecnología")
    assert result == "tecnologia"
    
    # Verificar que es igual a normalize_text
    text = "Educación"
    assert utils.normalize_sector_name(text) == utils.normalize_text(text)

def test_format_week_range():
    # Probar formato de rango de semana
    from datetime import datetime
    start_date = datetime(2023, 5, 1)  # Lunes 1 de mayo de 2023
    end_date = datetime(2023, 5, 7)    # Domingo 7 de mayo de 2023
    result = utils.format_week_range(start_date, end_date)
    assert result == "Semana del 01/05/2023 al 07/05/2023"