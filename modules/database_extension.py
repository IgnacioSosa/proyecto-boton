
def get_upcoming_vacaciones():
    """Obtiene todas las licencias futuras (fecha_inicio >= hoy)"""
    try:
        ensure_vacaciones_schema()
        query = """
            SELECT v.id, v.user_id, u.nombre, u.apellido, v.fecha_inicio, v.fecha_fin, v.tipo
            FROM vacaciones v
            JOIN usuarios u ON v.user_id = u.id
            WHERE v.fecha_inicio >= CURRENT_DATE
            ORDER BY v.fecha_inicio ASC
        """
        engine = get_engine()
        df = pd.read_sql_query(query, con=engine)
        return df
    except Exception as e:
        log_sql_error(f"Error obteniendo próximas licencias: {e}")
        return pd.DataFrame()
