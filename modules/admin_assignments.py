import streamlit as st
from .database import get_connection


def fix_existing_records_assignment(conn=None):
    """Corrige la asignación de registros existentes basándose en el nombre del técnico y su rol"""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    c = conn.cursor()

    c.execute("""
        SELECT u.id, u.nombre, u.apellido, u.rol_id, r.nombre as rol_nombre
        FROM usuarios u
        JOIN roles r ON u.rol_id = r.id_rol
        WHERE u.nombre IS NOT NULL AND u.apellido IS NOT NULL
    """)
    usuarios = c.fetchall()

    # Si no hay usuarios en el sistema, salir silenciosamente
    if not usuarios:
        if close_conn:
            conn.close()
        return 0

    c.execute("SELECT id_tecnico, nombre FROM tecnicos")
    tecnicos = c.fetchall()

    with st.spinner(f"Procesando {len(usuarios)} usuarios y {len(tecnicos)} técnicos..."):
        registros_asignados = 0
        tecnicos_procesados = set()

        def normalizar_texto(texto):
            import unicodedata
            texto_sin_acentos = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
            return texto_sin_acentos.lower()

        def find_matching_user_flexible(tecnico_nombre, usuarios_info):
            partes_tecnico = tecnico_nombre.strip().split()
            if len(partes_tecnico) == 0:
                return None, 0
            elif len(partes_tecnico) == 1:
                tecnico_primer_nombre = partes_tecnico[0].lower()
                tecnico_apellidos = ""
            else:
                tecnico_primer_nombre = partes_tecnico[0].lower()
                tecnico_apellidos = " ".join(partes_tecnico[1:]).lower()

            mejor_usuario = None
            mejor_puntuacion = 0

            for usuario_id, nombre, apellido, rol_id, rol_nombre in usuarios_info:
                partes_nombre_usuario = nombre.strip().split()
                usuario_primer_nombre = partes_nombre_usuario[0].lower() if partes_nombre_usuario else ""
                usuario_apellidos = apellido.strip().lower()

                puntuacion = 0
                nombre_completo_usuario = f"{nombre} {apellido}"
                if (normalizar_texto(tecnico_nombre) == normalizar_texto(nombre_completo_usuario)):
                    puntuacion = 100
                elif (tecnico_primer_nombre == usuario_primer_nombre and tecnico_apellidos == usuario_apellidos):
                    puntuacion = 95
                elif tecnico_primer_nombre == usuario_primer_nombre and tecnico_apellidos:
                    partes_apellidos_tecnico = tecnico_apellidos.split()
                    partes_apellidos_usuario = usuario_apellidos.split()
                    if (len(partes_apellidos_tecnico) >= 1 and len(partes_apellidos_usuario) >= 1 and
                        partes_apellidos_tecnico[0] == partes_apellidos_usuario[0]):
                        puntuacion = 90
                elif tecnico_primer_nombre == usuario_primer_nombre and tecnico_apellidos:
                    partes_apellidos_tecnico = tecnico_apellidos.split()
                    partes_apellidos_usuario = usuario_apellidos.split()
                    if (len(partes_apellidos_tecnico) >= 1 and len(partes_apellidos_usuario) >= 1 and
                        partes_apellidos_tecnico[-1] == partes_apellidos_usuario[-1]):
                        puntuacion = 85
                elif (tecnico_primer_nombre == usuario_primer_nombre and tecnico_apellidos):
                    partes_apellidos_tecnico = tecnico_apellidos.split()
                    partes_apellidos_usuario = usuario_apellidos.split()
                    coincidencias_apellidos = 0
                    for apellido_tecnico in partes_apellidos_tecnico:
                        if apellido_tecnico in partes_apellidos_usuario:
                            coincidencias_apellidos += 1
                    if coincidencias_apellidos > 0:
                        porcentaje_coincidencia = coincidencias_apellidos / len(partes_apellidos_tecnico)
                        puntuacion = 70 + (porcentaje_coincidencia * 10)
                elif (tecnico_primer_nombre == usuario_primer_nombre and not tecnico_apellidos):
                    puntuacion = 60
                else:
                    todas_partes_usuario = (nombre + " " + apellido).lower().split()
                    coincidencias_nombres = 0
                    total_partes_tecnico = len(partes_tecnico)
                    for parte_tecnico in partes_tecnico:
                        parte_tecnico_lower = parte_tecnico.lower()
                        for parte_usuario in todas_partes_usuario:
                            if (normalizar_texto(parte_tecnico_lower) == normalizar_texto(parte_usuario) or
                                parte_tecnico_lower == parte_usuario):
                                coincidencias_nombres += 1
                                break
                    if coincidencias_nombres > 0:
                        porcentaje_coincidencia = coincidencias_nombres / total_partes_tecnico
                        if porcentaje_coincidencia >= 0.5:
                            puntuacion = 50 + (porcentaje_coincidencia * 30)

                if puntuacion > mejor_puntuacion:
                    mejor_puntuacion = puntuacion
                    mejor_usuario = {
                        "id": usuario_id,
                        "nombre_completo": nombre_completo_usuario,
                        "nombre": nombre,
                        "apellido": apellido,
                        "rol_id": rol_id,
                        "rol_nombre": rol_nombre,
                    }

            return mejor_usuario, mejor_puntuacion

        # Aumentar el umbral mínimo para evitar asignaciones incorrectas
        UMBRAL_MINIMO = 70  # Aumentado de 50 a 70 para mayor precisión

        for tecnico_id, tecnico_nombre in tecnicos:
            mejor_usuario, mejor_puntuacion = find_matching_user_flexible(tecnico_nombre, usuarios)
            # Solo asignar si hay una coincidencia válida Y supera el umbral mínimo
            if mejor_usuario and mejor_puntuacion >= UMBRAL_MINIMO:
                tecnicos_procesados.add(tecnico_id)
                c.execute("UPDATE registros SET usuario_id = %s WHERE id_tecnico = %s AND usuario_id IS NULL", 
                         (mejor_usuario["id"], tecnico_id))
                registros_actualizados = c.rowcount
                registros_asignados += registros_actualizados

        if registros_asignados > 0:
            conn.commit()
            st.success(f"🎯 Total de registros procesados: {registros_asignados}")
        else:
            st.info("No se encontraron nuevos registros para reasignar.")

    tecnicos_no_procesados = []
    for tecnico_id, tecnico_nombre in tecnicos:
        if tecnico_id not in tecnicos_procesados:
            tecnicos_no_procesados.append((tecnico_id, tecnico_nombre))

    if tecnicos_no_procesados:
        st.warning(f"⚠️ Técnicos que no pudieron ser procesados: {len(tecnicos_no_procesados)}")
        with st.expander("Ver técnicos no procesados"):
            for tecnico_id, tecnico_nombre in tecnicos_no_procesados:
                mejor_usuario, mejor_puntuacion = find_matching_user_flexible(tecnico_nombre, usuarios)
                st.markdown(f"**{tecnico_nombre}**")
                if mejor_usuario:
                    st.write(f"Usuario más cercano: {mejor_usuario['nombre_completo']} (puntuación: {mejor_puntuacion:.1f})")
                    if mejor_puntuacion < UMBRAL_MINIMO:
                        st.write(f"Razón: Puntuación insuficiente (mínimo requerido: {UMBRAL_MINIMO})")
                else:
                    st.write("Razón: No hay coincidencias con ningún usuario en el sistema")
                st.write("---")

    if close_conn:
        conn.close()
    return registros_asignados


def find_matching_user_by_components(tecnico_nombre, usuarios_info, umbral_minimo=70):
    """
    Algoritmo mejorado de coincidencia basado en componentes individuales de nombres.
    Valida cada nombre+nombre+apellido+apellido independientemente del orden.
    
    Args:
        tecnico_nombre: Nombre del técnico a buscar
        usuarios_info: Lista de usuarios [(id, nombre, apellido, rol_id, rol_nombre)]
        umbral_minimo: Puntuación mínima para considerar una coincidencia válida
    
    Returns:
        tuple: (mejor_usuario, mejor_puntuacion)
    """
    import unicodedata
    
    def normalizar_texto(texto):
        """Normaliza texto removiendo acentos y convirtiendo a minúsculas"""
        if not texto:
            return ""
        texto_sin_acentos = ''.join(c for c in unicodedata.normalize('NFD', texto) 
                                   if unicodedata.category(c) != 'Mn')
        return texto_sin_acentos.lower().strip()
    
    def extraer_componentes(texto_completo):
        """Extrae todos los componentes de un nombre completo"""
        if not texto_completo:
            return []
        # Dividir por espacios y filtrar componentes vacíos
        componentes = [normalizar_texto(comp) for comp in texto_completo.split() if comp.strip()]
        return [comp for comp in componentes if comp]  # Filtrar strings vacíos
    
    def calcular_coincidencia_componentes(componentes_tecnico, componentes_usuario):
        """
        Calcula la tasa de coincidencia entre componentes de nombres.
        
        Returns:
            dict: {
                'coincidencias': int,
                'total_tecnico': int,
                'total_usuario': int,
                'tasa_tecnico': float,  # coincidencias / total_tecnico
                'tasa_usuario': float,  # coincidencias / total_usuario
                'tasa_promedio': float,
                'componentes_coincidentes': list
            }
        """
        if not componentes_tecnico or not componentes_usuario:
            return {
                'coincidencias': 0,
                'total_tecnico': len(componentes_tecnico),
                'total_usuario': len(componentes_usuario),
                'tasa_tecnico': 0.0,
                'tasa_usuario': 0.0,
                'tasa_promedio': 0.0,
                'componentes_coincidentes': []
            }
        
        coincidencias = 0
        componentes_coincidentes = []
        componentes_usuario_usados = set()
        
        # Buscar coincidencias exactas
        for comp_tecnico in componentes_tecnico:
            for i, comp_usuario in enumerate(componentes_usuario):
                if i not in componentes_usuario_usados and comp_tecnico == comp_usuario:
                    coincidencias += 1
                    componentes_coincidentes.append(comp_tecnico)
                    componentes_usuario_usados.add(i)
                    break
        
        total_tecnico = len(componentes_tecnico)
        total_usuario = len(componentes_usuario)
        
        tasa_tecnico = coincidencias / total_tecnico if total_tecnico > 0 else 0
        tasa_usuario = coincidencias / total_usuario if total_usuario > 0 else 0
        tasa_promedio = (tasa_tecnico + tasa_usuario) / 2
        
        return {
            'coincidencias': coincidencias,
            'total_tecnico': total_tecnico,
            'total_usuario': total_usuario,
            'tasa_tecnico': tasa_tecnico,
            'tasa_usuario': tasa_usuario,
            'tasa_promedio': tasa_promedio,
            'componentes_coincidentes': componentes_coincidentes
        }
    
    # Extraer componentes del técnico
    componentes_tecnico = extraer_componentes(tecnico_nombre)
    
    if not componentes_tecnico:
        return None, 0
    
    mejor_usuario = None
    mejor_puntuacion = 0
    mejor_detalle = None
    
    for usuario_id, nombre, apellido, rol_id, rol_nombre in usuarios_info:
        # Crear nombre completo del usuario
        nombre_completo_usuario = f"{nombre} {apellido}".strip()
        componentes_usuario = extraer_componentes(nombre_completo_usuario)
        
        if not componentes_usuario:
            continue
        
        # Calcular coincidencia
        resultado = calcular_coincidencia_componentes(componentes_tecnico, componentes_usuario)
        
        # Calcular puntuación basada en diferentes criterios
        puntuacion = 0
        
        # Criterio 1: Coincidencia perfecta (100 puntos)
        if (resultado['coincidencias'] == resultado['total_tecnico'] and 
            resultado['coincidencias'] == resultado['total_usuario']):
            puntuacion = 100
        
        # Criterio 2: Alta coincidencia con todos los componentes del técnico (90-95 puntos)
        elif resultado['tasa_tecnico'] == 1.0:  # Todos los componentes del técnico coinciden
            if resultado['tasa_usuario'] >= 0.8:  # Al menos 80% del usuario coincide
                puntuacion = 95
            else:
                puntuacion = 90
        
        # Criterio 3: Alta coincidencia bidireccional (80-89 puntos)
        elif resultado['tasa_promedio'] >= 0.8:
            puntuacion = 80 + (resultado['tasa_promedio'] * 9)  # 80-89 puntos
        
        # Criterio 4: Coincidencia moderada (60-79 puntos)
        elif resultado['tasa_promedio'] >= 0.6:
            puntuacion = 60 + (resultado['tasa_promedio'] * 19)  # 60-79 puntos
        
        # Criterio 5: Coincidencia mínima (40-59 puntos)
        elif resultado['coincidencias'] >= 2 or resultado['tasa_promedio'] >= 0.4:
            puntuacion = 40 + (resultado['tasa_promedio'] * 19)  # 40-59 puntos
        
        # Bonificaciones adicionales
        if resultado['coincidencias'] >= 3:  # 3 o más componentes coinciden
            puntuacion += 5
        
        if resultado['coincidencias'] >= len(componentes_tecnico) // 2:  # Más de la mitad coincide
            puntuacion += 3
        
        # Penalizaciones por diferencias significativas en cantidad de componentes
        diferencia_componentes = abs(resultado['total_tecnico'] - resultado['total_usuario'])
        if diferencia_componentes > 2:
            puntuacion -= diferencia_componentes * 2
        
        # Asegurar que la puntuación esté en el rango válido
        puntuacion = max(0, min(100, puntuacion))
        
        # Actualizar mejor coincidencia
        if puntuacion > mejor_puntuacion:
            mejor_puntuacion = puntuacion
            mejor_usuario = {
                "id": usuario_id,
                "nombre_completo": nombre_completo_usuario,
                "nombre": nombre,
                "apellido": apellido,
                "rol_id": rol_id,
                "rol_nombre": rol_nombre,
            }
            mejor_detalle = resultado
    
    return mejor_usuario, mejor_puntuacion


def simulate_assignment_with_improved_algorithm(conn=None, umbral_minimo=70):
    """
    Simula la asignación de registros con el algoritmo mejorado sin hacer cambios reales.
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    c = conn.cursor()

    # Obtener usuarios
    c.execute("""
        SELECT u.id, u.nombre, u.apellido, u.rol_id, r.nombre as rol_nombre
        FROM usuarios u
        JOIN roles r ON u.rol_id = r.id_rol
        WHERE u.nombre IS NOT NULL AND u.apellido IS NOT NULL
    """)
    usuarios = c.fetchall()

    # Obtener técnicos
    c.execute("SELECT id_tecnico, nombre FROM tecnicos")
    tecnicos = c.fetchall()

    st.subheader("🔍 Simulación de Asignación con Algoritmo Mejorado")
    st.info(f"Analizando {len(tecnicos)} técnicos contra {len(usuarios)} usuarios con umbral mínimo de {umbral_minimo} puntos")

    resultados_detallados = []
    asignaciones_exitosas = 0
    asignaciones_fallidas = 0

    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, (tecnico_id, tecnico_nombre) in enumerate(tecnicos):
        progress = (i + 1) / len(tecnicos)
        progress_bar.progress(progress)
        status_text.text(f"Analizando: {tecnico_nombre} ({i+1}/{len(tecnicos)})")
        
        mejor_usuario, mejor_puntuacion = find_matching_user_by_components(
            tecnico_nombre, usuarios, umbral_minimo
        )
        
        resultado_detalle = {
            'tecnico_id': tecnico_id,
            'tecnico_nombre': tecnico_nombre,
            'mejor_usuario': mejor_usuario,
            'puntuacion': mejor_puntuacion,
            'seria_asignado': mejor_usuario is not None and mejor_puntuacion >= umbral_minimo
        }
        
        if resultado_detalle['seria_asignado']:
            asignaciones_exitosas += 1
        else:
            asignaciones_fallidas += 1
        
        resultados_detallados.append(resultado_detalle)

    progress_bar.empty()
    status_text.empty()

    # Mostrar resumen
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("✅ Asignaciones Exitosas", asignaciones_exitosas)
    with col2:
        st.metric("❌ Asignaciones Fallidas", asignaciones_fallidas)
    with col3:
        tasa_exito = (asignaciones_exitosas / len(tecnicos)) * 100 if tecnicos else 0
        st.metric("📊 Tasa de Éxito", f"{tasa_exito:.1f}%")

    # Mostrar asignaciones exitosas
    asignaciones_exitosas_lista = [r for r in resultados_detallados if r['seria_asignado']]
    if asignaciones_exitosas_lista:
        with st.expander(f"✅ Ver {len(asignaciones_exitosas_lista)} asignaciones que serían exitosas"):
            for resultado in asignaciones_exitosas_lista:
                st.markdown(f"**{resultado['tecnico_nombre']}** → "
                          f"{resultado['mejor_usuario']['nombre_completo']} "
                          f"(puntuación: {resultado['puntuacion']:.1f})")

    # Mostrar asignaciones fallidas
    asignaciones_fallidas_lista = [r for r in resultados_detallados if not r['seria_asignado']]
    if asignaciones_fallidas_lista:
        with st.expander(f"❌ Ver {len(asignaciones_fallidas_lista)} asignaciones que fallarían"):
            for resultado in asignaciones_fallidas_lista:
                st.markdown(f"**{resultado['tecnico_nombre']}**")
                if resultado['mejor_usuario']:
                    st.write(f"Usuario más cercano: {resultado['mejor_usuario']['nombre_completo']} "
                           f"(puntuación: {resultado['puntuacion']:.1f})")
                    if resultado['puntuacion'] < umbral_minimo:
                        st.write(f"Razón: Puntuación insuficiente (mínimo requerido: {umbral_minimo})")
                else:
                    st.write("Razón: No hay coincidencias con ningún usuario en el sistema")
                st.write("---")

    if close_conn:
        conn.close()
    
    return resultados_detallados


def fix_existing_records_assignment_improved(conn=None, umbral_minimo=70):
    """
    Versión mejorada de asignación de registros usando coincidencia por componentes.
    Resuelve problemas de orden y formato inconsistente en nombres.
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    c = conn.cursor()

    # Obtener usuarios
    c.execute("""
        SELECT u.id, u.nombre, u.apellido, u.rol_id, r.nombre as rol_nombre
        FROM usuarios u
        JOIN roles r ON u.rol_id = r.id_rol
        WHERE u.nombre IS NOT NULL AND u.apellido IS NOT NULL
    """)
    usuarios = c.fetchall()

    # Obtener técnicos
    c.execute("SELECT id_tecnico, nombre FROM tecnicos")
    tecnicos = c.fetchall()

    with st.spinner(f"Procesando {len(usuarios)} usuarios y {len(tecnicos)} técnicos con algoritmo mejorado..."):
        registros_asignados = 0
        tecnicos_procesados = set()
        resultados_detallados = []

        for tecnico_id, tecnico_nombre in tecnicos:
            mejor_usuario, mejor_puntuacion = find_matching_user_by_components(
                tecnico_nombre, usuarios, umbral_minimo
            )
            
            resultado_detalle = {
                'tecnico_id': tecnico_id,
                'tecnico_nombre': tecnico_nombre,
                'mejor_usuario': mejor_usuario,
                'puntuacion': mejor_puntuacion,
                'asignado': False
            }
            
            if mejor_usuario and mejor_puntuacion >= umbral_minimo:
                tecnicos_procesados.add(tecnico_id)
                c.execute("UPDATE registros SET usuario_id = %s WHERE id_tecnico = %s", 
                         (mejor_usuario["id"], tecnico_id))
                registros_actualizados = c.rowcount
                registros_asignados += registros_actualizados
                resultado_detalle['asignado'] = True
                resultado_detalle['registros_actualizados'] = registros_actualizados
            
            resultados_detallados.append(resultado_detalle)

        if registros_asignados > 0:
            conn.commit()
            st.success(f"🎯 Total de registros procesados con algoritmo mejorado: {registros_asignados}")
        else:
            st.info("No se encontraron nuevos registros para reasignar con el algoritmo mejorado.")

    # Mostrar resultados detallados
    tecnicos_no_procesados = [r for r in resultados_detallados if not r['asignado']]
    
    if tecnicos_no_procesados:
        st.warning(f"⚠️ Técnicos que no pudieron ser procesados: {len(tecnicos_no_procesados)}")
        with st.expander("Ver análisis detallado de técnicos no procesados"):
            for resultado in tecnicos_no_procesados:
                st.markdown(f"**{resultado['tecnico_nombre']}**")
                if resultado['mejor_usuario']:
                    st.write(f"Usuario más cercano: {resultado['mejor_usuario']['nombre_completo']} "
                           f"(puntuación: {resultado['puntuacion']:.1f})")
                    if resultado['puntuacion'] < umbral_minimo:
                        st.write(f"Razón: Puntuación insuficiente (mínimo requerido: {umbral_minimo})")
                else:
                    st.write("Razón: No hay coincidencias con ningún usuario en el sistema")
                st.write("---")
    
    # Mostrar estadísticas de asignaciones exitosas
    tecnicos_procesados_lista = [r for r in resultados_detallados if r['asignado']]
    if tecnicos_procesados_lista:
        with st.expander(f"Ver {len(tecnicos_procesados_lista)} asignaciones exitosas"):
            for resultado in tecnicos_procesados_lista:
                st.markdown(f"✅ **{resultado['tecnico_nombre']}** → "
                          f"{resultado['mejor_usuario']['nombre_completo']} "
                          f"(puntuación: {resultado['puntuacion']:.1f})")

    if close_conn:
        conn.close()
    
    return registros_asignados


def render_assignment_management():
    """
    Renderiza la interfaz de gestión de asignaciones mejorada.
    """
    st.subheader("🔧 Gestión de Asignaciones de Registros")
    
    # Configuración del umbral
    umbral_minimo = st.slider(
        "Umbral mínimo de puntuación para asignación",
        min_value=40,
        max_value=95,
        value=70,
        step=5,
        help="Puntuación mínima requerida para considerar una coincidencia válida"
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔍 Simular Asignación Mejorada", use_container_width=True):
            simulate_assignment_with_improved_algorithm(umbral_minimo=umbral_minimo)
    
    with col2:
        if st.button("✅ Ejecutar Asignación Mejorada", use_container_width=True):
            if st.session_state.get('confirm_improved_assignment', False):
                fix_existing_records_assignment_improved(umbral_minimo=umbral_minimo)
                st.session_state['confirm_improved_assignment'] = False
            else:
                st.session_state['confirm_improved_assignment'] = True
                st.warning("⚠️ Haz clic nuevamente para confirmar la ejecución de la asignación mejorada")
    
    st.divider()
    
    # Algoritmo original para comparación
    st.subheader("🔄 Algoritmo Original (para comparación)")
    
    col3, col4 = st.columns(2)
    
    with col3:
        if st.button("🔧 Ejecutar Algoritmo Original", use_container_width=True):
            fix_existing_records_assignment()
    
    with col4:
        st.info("El algoritmo original usa el método de coincidencia anterior")