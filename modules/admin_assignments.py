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


def find_matching_user_by_components(tecnico_nombre, usuarios_info, umbral_minimo=70, usuarios_full_info=None):
    """
    Algoritmo mejorado de coincidencia basado en componentes individuales de nombres.
    Valida cada nombre+nombre+apellido+apellido independientemente del orden.

    Tie-break robusto: cuando existen múltiples usuarios con el mismo
    nombre/apellido (ej: mismo nombre y mail, pero username distinto para
    adm_Técnico vs Técnico), se prefiere al usuario cuyo rol coincide con
    departamento técnico y, de persistir empate, NO se asigna para evitar
    pisar registros previamente asignados.

    Args:
        tecnico_nombre: Nombre del técnico a buscar
        usuarios_info: Lista de usuarios [(id, nombre, apellido, rol_id, rol_nombre)]
        umbral_minimo: Puntuación mínima para considerar una coincidencia válida
        usuarios_full_info: DataFrame opcional con columnas [id, username, email, rol_nombre, ...]
            para desempates adicionales por username/email.

    Returns:
        tuple: (mejor_usuario, mejor_puntuacion)
    """
    import unicodedata

    def normalizar_texto(texto):
        if not texto:
            return ""
        texto_sin_acentos = ''.join(c for c in unicodedata.normalize('NFD', texto)
                                   if unicodedata.category(c) != 'Mn')
        return texto_sin_acentos.lower().strip()

    def extraer_componentes(texto_completo):
        if not texto_completo:
            return []
        componentes = [normalizar_texto(comp) for comp in texto_completo.split() if comp.strip()]
        return [comp for comp in componentes if comp]

    def calcular_coincidencia_componentes(componentes_tecnico, componentes_usuario):
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

    def es_usuario_rol_tecnico(rol_nombre, username, email):
        if not rol_nombre:
            return False
        rn = normalizar_texto(rol_nombre)
        keywords_tecnico = ("tecnico", "dpto tecnico", "departamento tecnico", "dtecnico", "tecnica")
        if any(k in rn for k in keywords_tecnico):
            return True
        uname = normalizar_texto(username or "")
        if uname.endswith("1") or uname.endswith("2"):
            suffixed = uname[:-1]
            if any(k in suffixed for k in keywords_tecnico):
                return True
        return False

    def es_usuario_rol_adm_tecnico(rol_nombre):
        if not rol_nombre:
            return False
        rn = normalizar_texto(rol_nombre)
        return "adm" in rn and "tecnico" in rn

    componentes_tecnico = extraer_componentes(tecnico_nombre)
    tecnico_norm = normalizar_texto(tecnico_nombre)

    if not componentes_tecnico:
        return None, 0

    username_by_id = {}
    email_by_id = {}
    if usuarios_full_info is not None and len(usuarios_full_info) > 0:
        try:
            for _, r in usuarios_full_info.iterrows():
                uid = int(r.get("id"))
                username_by_id[uid] = str(r.get("username") or "").strip()
                email_by_id[uid] = str(r.get("email") or "").strip().lower()
        except Exception:
            username_by_id = {}
            email_by_id = {}

    candidatos_puntuacion_maxima = []
    puntuacion_maxima_global = 0

    for usuario_id, nombre, apellido, rol_id, rol_nombre in usuarios_info:
        nombre_completo_usuario = f"{nombre} {apellido}".strip()
        componentes_usuario = extraer_componentes(nombre_completo_usuario)

        if not componentes_usuario:
            continue

        resultado = calcular_coincidencia_componentes(componentes_tecnico, componentes_usuario)

        puntuacion = 0

        if (resultado['coincidencias'] == resultado['total_tecnico'] and
            resultado['coincidencias'] == resultado['total_usuario']):
            puntuacion = 100
        elif resultado['tasa_tecnico'] == 1.0:
            if resultado['tasa_usuario'] >= 0.8:
                puntuacion = 95
            else:
                puntuacion = 90
        elif resultado['tasa_promedio'] >= 0.8:
            puntuacion = 80 + (resultado['tasa_promedio'] * 9)
        elif resultado['tasa_promedio'] >= 0.6:
            puntuacion = 60 + (resultado['tasa_promedio'] * 19)
        elif resultado['coincidencias'] >= 2 or resultado['tasa_promedio'] >= 0.4:
            puntuacion = 40 + (resultado['tasa_promedio'] * 19)

        if resultado['coincidencias'] >= 3:
            puntuacion += 5
        if resultado['coincidencias'] >= len(componentes_tecnico) // 2:
            puntuacion += 3

        diferencia_componentes = abs(resultado['total_tecnico'] - resultado['total_usuario'])
        if diferencia_componentes > 2:
            puntuacion -= diferencia_componentes * 2

        puntuacion = max(0, min(100, puntuacion))

        if puntuacion < umbral_minimo:
            continue

        usuario_dict = {
            "id": usuario_id,
            "nombre_completo": nombre_completo_usuario,
            "nombre": nombre,
            "apellido": apellido,
            "rol_id": rol_id,
            "rol_nombre": rol_nombre,
        }

        if puntuacion > puntuacion_maxima_global:
            puntuacion_maxima_global = puntuacion
            candidatos_puntuacion_maxima = [(usuario_dict, resultado)]
        elif puntuacion == puntuacion_maxima_global:
            candidatos_puntuacion_maxima.append((usuario_dict, resultado))

    if not candidatos_puntuacion_maxima:
        return None, 0

    if len(candidatos_puntuacion_maxima) == 1:
        return candidatos_puntuacion_maxima[0][0], puntuacion_maxima_global

    # Empate de puntuación: desempatar por rol (preferir Técnico)
    # Si todavía hay empate por igualdad de nombre+apellido+email, NO ASIGNAR.
    tecnicos = []
    adm_tecnicos = []
    otros = []
    for user_dict, _res in candidatos_puntuacion_maxima:
        uid = int(user_dict["id"])
        uname = username_by_id.get(uid, "")
        email = email_by_id.get(uid, "")
        if es_usuario_rol_tecnico(user_dict.get("rol_nombre"), uname, email):
            tecnicos.append((user_dict, _res, uid))
        elif es_usuario_rol_adm_tecnico(user_dict.get("rol_nombre")):
            adm_tecnicos.append((user_dict, _res, uid))
        else:
            otros.append((user_dict, _res, uid))

    bucket_ganador = None
    if len(tecnicos) == 1:
        bucket_ganador = tecnicos[0]
    elif len(adm_tecnicos) == 1 and not tecnicos:
        bucket_ganador = adm_tecnicos[0]
    elif len(otros) == 1 and not tecnicos and not adm_tecnicos:
        bucket_ganador = otros[0]

    if bucket_ganador is not None:
        return bucket_ganador[0], puntuacion_maxima_global

    # Sigue habiendo empate: revisar si los candidatos son duplicados
    # por nombre/apellido/email idénticos. En ese caso no tocar.
    try:
        signature_set = set()
        for user_dict, _res, uid in (tecnicos + adm_tecnicos + otros):
            uname = normalizar_texto(username_by_id.get(uid, ""))
            email = normalizar_texto(email_by_id.get(uid, ""))
            fullname = normalizar_texto(user_dict.get("nombre_completo") or "")
            signature_set.add((fullname, email, uname))
        if len(signature_set) > 1:
            # Empate no es por misma persona: fallback a primero, pero bajar score
            # para reflejar incertidumbre (no asigna si umbral sigue siendo exigente)
            tiebreak_score = max(umbral_minimo - 1, 0)
            return candidatos_puntuacion_maxima[0][0], tiebreak_score
    except Exception:
        pass

    return None, 0


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

    try:
        import pandas as pd
        from .database import get_users_dataframe
        usuarios_full_df = get_users_dataframe()
        if usuarios_full_df is None:
            usuarios_full_df = pd.DataFrame()
    except Exception:
        usuarios_full_df = pd.DataFrame()

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
            tecnico_nombre, usuarios, umbral_minimo, usuarios_full_info=usuarios_full_df
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

    Regla clave: SOLO asigna registros que aún NO tienen usuario_id asignado.
    NO reescribe asignaciones previas (evita pisar registros de usuarios con
    mismo nombre/apellido, por ejemplo adm_Técnico vs Técnico).
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    c = conn.cursor()

    # Obtener usuarios con data extra para desempates robustos
    c.execute("""
        SELECT u.id, u.nombre, u.apellido, u.rol_id, r.nombre as rol_nombre
        FROM usuarios u
        JOIN roles r ON u.rol_id = r.id_rol
        WHERE u.nombre IS NOT NULL AND u.apellido IS NOT NULL
    """)
    usuarios = c.fetchall()

    try:
        import pandas as pd
        from .database import get_users_dataframe
        usuarios_full_df = get_users_dataframe()
        if usuarios_full_df is None:
            usuarios_full_df = pd.DataFrame()
    except Exception:
        usuarios_full_df = pd.DataFrame()

    # Obtener técnicos
    c.execute("SELECT id_tecnico, nombre FROM tecnicos")
    tecnicos = c.fetchall()

    with st.spinner(f"Procesando {len(usuarios)} usuarios y {len(tecnicos)} técnicos con algoritmo mejorado..."):
        registros_asignados = 0
        tecnicos_procesados = set()
        resultados_detallados = []

        for tecnico_id, tecnico_nombre in tecnicos:
            mejor_usuario, mejor_puntuacion = find_matching_user_by_components(
                tecnico_nombre, usuarios, umbral_minimo, usuarios_full_info=usuarios_full_df
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
                c.execute(
                    "UPDATE registros SET usuario_id = %s WHERE id_tecnico = %s AND usuario_id IS NULL",
                    (mejor_usuario["id"], tecnico_id),
                )
                registros_actualizados = c.rowcount
                registros_asignados += registros_actualizados
                resultado_detalle['asignado'] = registros_actualizados > 0
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


def recover_misassigned_records_by_username_pairs(pairs_list, dry_run=True, conn=None):
    """
    Corrige asignaciones históricas colapsadas entre usuarios con mismo
    nombre/apellido pero distinto username.

    Ejemplo de pairs_list:
        [
            ("rousseauxs", "rousseauxs1"),
            ("gomeze", "gomeze1"),
        ]

    La convención asumida es:
        wrong_username  → adm_Técnico (a quien se le asignó por error)
        correct_username → Técnico (a quien DEBÍAN corresponderle)

    Para cada par, si un registro está apuntando a wrong_user Y su técnico
    asociado coincide en nombre completo con correct_user, se corrige.

    Si dry_run=True no hace cambios, solo reporta qué corregiría.
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    if not pairs_list:
        if close_conn:
            conn.close()
        return {
            "dry_run": dry_run,
            "updated_count": 0,
            "details": [],
            "skipped_reason": "pairs_list vacío",
        }

    c = conn.cursor()

    # Construir lookup username -> usuario_id + nombre completo
    lookup_rows = []
    for pair in pairs_list:
        for uname in pair:
            lookup_rows.append(str(uname).strip().lower())

    placeholder = ",".join(["%s"] * len(lookup_rows))
    c.execute(
        f"""
        SELECT id, LOWER(username), nombre, apellido, email, rol_id
        FROM usuarios
        WHERE LOWER(username) IN ({placeholder})
        """,
        tuple(lookup_rows),
    )
    usuarios_by_uname = {}
    for uid, uname, nombre, apellido, email, rol_id in c.fetchall():
        nombre_completo = " ".join(
            p for p in [str(nombre or "").strip(), str(apellido or "").strip()] if p
        ).strip()
        usuarios_by_uname[uname.lower()] = {
            "id": int(uid),
            "username": uname.lower(),
            "nombre_completo": nombre_completo,
            "email": (email or "").lower(),
            "rol_id": rol_id,
        }

    updated_count = 0
    details = []

    for wrong_uname, correct_uname in pairs_list:
        wrong_u = usuarios_by_uname.get(str(wrong_uname).strip().lower())
        correct_u = usuarios_by_uname.get(str(correct_uname).strip().lower())

        pair_detail = {
            "wrong_username": wrong_uname,
            "correct_username": correct_uname,
            "wrong_user_found": wrong_u is not None,
            "correct_user_found": correct_u is not None,
            "rows_to_update": 0,
            "rows_updated": 0,
            "note": None,
        }

        if not wrong_u or not correct_u:
            pair_detail["note"] = "Falta uno de los usuarios en la tabla usuarios"
            details.append(pair_detail)
            continue

        if wrong_u["id"] == correct_u["id"]:
            pair_detail["note"] = "wrong y correct son el mismo usuario"
            details.append(pair_detail)
            continue

        correct_fullname_norm = ""
        if correct_u["nombre_completo"]:
            try:
                import unicodedata
                correct_fullname_norm = unicodedata.normalize(
                    "NFD", correct_u["nombre_completo"].lower()
                )
                correct_fullname_norm = "".join(
                    ch for ch in correct_fullname_norm if unicodedata.category(ch) != "Mn"
                )
            except Exception:
                correct_fullname_norm = correct_u["nombre_completo"].lower()

        # Encontrar técnicos candidatos que coincidan en nombre normalizado
        # (normalmente sería 1 solo por usuario técnico real)
        c.execute("SELECT id_tecnico, nombre FROM tecnicos")
        candidate_tecnico_ids = []
        for id_tecnico, tnombre in c.fetchall():
            try:
                tn = unicodedata.normalize("NFD", str(tnombre or "").lower())
                tn_norm = "".join(ch for ch in tn if unicodedata.category(ch) != "Mn")
            except Exception:
                tn_norm = str(tnombre or "").lower()
            if tn_norm and tn_norm == correct_fullname_norm:
                candidate_tecnico_ids.append(int(id_tecnico))

        if not candidate_tecnico_ids:
            pair_detail["note"] = (
                "No se encontró registro en 'tecnicos' cuyo nombre coincida "
                f"con el usuario técnico {correct_uname!r}."
            )
            details.append(pair_detail)
            continue

        # Contar filas que están mal asignadas (a wrong_user_id) pero que
        # pertenecen al técnico del usuario correcto.
        ph_ids = ",".join(["%s"] * len(candidate_tecnico_ids))
        params_count = (
            [int(wrong_u["id"])] + [int(x) for x in candidate_tecnico_ids] + [int(correct_u["id"])]
        )
        c.execute(
            f"""
            SELECT COUNT(*)
            FROM registros
            WHERE usuario_id = %s
              AND id_tecnico IN ({ph_ids})
              AND usuario_id != %s
            """,
            tuple(params_count),
        )
        rows_to_update = int(c.fetchone()[0] or 0)
        pair_detail["rows_to_update"] = rows_to_update

        if rows_to_update <= 0:
            pair_detail["note"] = "No hay registros para corregir en este par"
            details.append(pair_detail)
            continue

        if not dry_run:
            params_upd = (
                [int(correct_u["id"]), int(wrong_u["id"])]
                + [int(x) for x in candidate_tecnico_ids]
                + [int(correct_u["id"])]
            )
            c.execute(
                f"""
                UPDATE registros
                SET usuario_id = %s
                WHERE usuario_id = %s
                  AND id_tecnico IN ({ph_ids})
                  AND usuario_id != %s
                """,
                tuple(params_upd),
            )
            updated_rows = c.rowcount or 0
            updated_count += updated_rows
            pair_detail["rows_updated"] = updated_rows

        details.append(pair_detail)

    if not dry_run and updated_count > 0:
        conn.commit()

    if close_conn:
        conn.close()

    return {
        "dry_run": dry_run,
        "updated_count": updated_count,
        "details": details,
    }


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

    # Corrección histórica de asignaciones colapsadas
    # (adm_Técnico vs Técnico con mismo nombre/email pero distinto username)
    st.subheader("🔁 Corrección de Asignaciones Colapsadas (duplicados nombre/email)")
    st.caption(
        "Usar únicamente cuando existen usuarios con mismo nombre y mail pero "
        "distinto username (ej: adm_Técnico 'rousseauxs' / Técnico 'rousseauxs1') "
        "y los registros fueron reasignados por error al primero."
    )

    st.markdown(
        "**Pares conocidos (username erróneo → username correcto):** "
        "`rousseauxs → rousseauxs1`, `gomeze → gomeze1`"
    )

    col_rec1, col_rec2 = st.columns(2)
    with col_rec1:
        if st.button("🔍 Simular corrección histórica", use_container_width=True):
            st.session_state["run_recovery_dry_run"] = True
            st.session_state["run_recovery_apply"] = False

    with col_rec2:
        if st.button("✅ Aplicar corrección histórica (CONFIRMAR)", use_container_width=True):
            if st.session_state.get("confirm_recovery_apply", False):
                st.session_state["run_recovery_apply"] = True
                st.session_state["run_recovery_dry_run"] = False
                st.session_state["confirm_recovery_apply"] = False
            else:
                st.session_state["confirm_recovery_apply"] = True
                st.session_state["run_recovery_apply"] = False
                st.warning(
                    "⚠️ Confirma nuevamente 'Aplicar corrección histórica' para "
                    "reasignar los registros a los usuarios técnicos correctos."
                )

    default_pairs = [("rousseauxs", "rousseauxs1"), ("gomeze", "gomeze1")]

    if st.session_state.get("run_recovery_dry_run"):
        st.session_state["run_recovery_dry_run"] = False
        result = recover_misassigned_records_by_username_pairs(
            default_pairs, dry_run=True
        )
        total_corregir = sum(int(d.get("rows_to_update") or 0) for d in result["details"])
        st.info(
            f"[SIMULACIÓN] Se corregirían {total_corregir} registros en total."
        )
        for d in result["details"]:
            with st.expander(
                f"{d['wrong_username']} → {d['correct_username']} "
                f"(registros a corregir: {d.get('rows_to_update', 0)})"
            ):
                st.json(d)

    if st.session_state.get("run_recovery_apply"):
        st.session_state["run_recovery_apply"] = False
        with st.spinner("Aplicando corrección histórica..."):
            result = recover_misassigned_records_by_username_pairs(
                default_pairs, dry_run=False
            )
            st.success(
                f"✅ Corrección aplicada. Se actualizaron {result['updated_count']} registros."
            )
            for d in result["details"]:
                with st.expander(
                    f"{d['wrong_username']} → {d['correct_username']} "
                    f"(actualizados: {d.get('rows_updated', 0)})"
                ):
                    st.json(d)
            st.info("🔄 Refrescá la vista de registros para confirmar que los usuarios técnicos recuperaron sus registros.")

    st.divider()

    # Algoritmo original para comparación
    st.subheader("🔄 Algoritmo Original (para comparación)")

    col3, col4 = st.columns(2)

    with col3:
        if st.button("🔧 Ejecutar Algoritmo Original", use_container_width=True):
            fix_existing_records_assignment()

    with col4:
        st.info("El algoritmo original usa el método de coincidencia anterior")
