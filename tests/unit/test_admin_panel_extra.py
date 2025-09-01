import argparse
import pandas as pd
import calendar
from datetime import datetime
import streamlit as st

# Importa tus funciones internas (ajusta según tu proyecto)
# from modules.database import get_registros_by_rol_with_date_filter

# Función principal del panel
def render_admin_panel(args=None):
    """
    Renderiza el panel de administración en Streamlit.
    Si se ejecuta desde test, args puede ser None.
    """
    # Si no vienen args (por test o ejecución directa), inicializamos con valores por defecto
    if args is None:
        args = argparse.Namespace(
            filtro="current_month",   # valor por defecto para filtro de fechas
            usuario="admin"           # valor de ejemplo
        )

    # Mostrar un título en Streamlit
    st.title("Panel de Administración")

    # Ejemplo de uso de fechas
    mes_actual = datetime.now().month
    st.write(f"Mes actual: {calendar.month_name[mes_actual]}")

    # Obtener registros desde la base (mock si no está implementado)
    try:
        registros = get_registros_by_rol_with_date_filter(args.usuario, args.filtro)
    except Exception:
        registros = pd.DataFrame()

    if registros.empty:
        st.info("No hay registros disponibles.")
    else:
        st.dataframe(registros)


def main():
    """Punto de entrada desde consola"""
    parser = argparse.ArgumentParser(description="Panel de administración")
    parser.add_argument("--filtro", default="current_month", help="Filtro de fechas")
    parser.add_argument("--usuario", default="admin", help="Usuario administrador")
    args = parser.parse_args()

    render_admin_panel(args)


# Si se ejecuta directamente: python -m modules.admin_panel
if __name__ == "__main__":
    main()
