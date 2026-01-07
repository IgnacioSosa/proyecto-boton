import streamlit as st
import pandas as pd
from sqlalchemy import text

from .database import get_connection, get_engine, generate_roles_from_nomina


def render_department_management():
    """Renderiza la gestión de departamentos (extraído de admin_panel.render_role_management)"""
    st.subheader("Gestión de Departamentos")

    # Generar departamentos automáticamente al cargar la pestaña (mantiene la lógica original)
    generate_roles_from_nomina()
    
    # Generar grupos desde equipos de nómina
    from .database import generate_grupos_from_nomina
    generate_grupos_from_nomina()

    # Formulario para agregar nuevo departamento
    with st.expander("Agregar Departamento"):
        nombre_rol = st.text_input("Nombre del Departamento", key="new_role_name")
        descripcion_rol = st.text_area("Descripción del Departamento", key="new_role_desc")
        is_hidden = st.checkbox("Ocultar en listas desplegables", key="new_role_hidden")

        if st.button("Agregar Departamento", key="add_role_btn"):
            if nombre_rol:
                # Verificar que no sea un departamento protegido
                if nombre_rol.lower() == 'admin':
                    st.error("No se puede crear un departamento con el nombre 'admin' ya que es un departamento protegido.")
                else:
                    conn = get_connection()
                    c = conn.cursor()
                    try:
                        # Verificar si ya existe un departamento con el mismo nombre normalizado
                        from .utils import normalize_text
                        c.execute("SELECT id_rol, nombre FROM roles")
                        roles = c.fetchall()

                        nombre_normalizado = normalize_text(nombre_rol)
                        duplicado = False

                        for _, rol_nombre in roles:
                            if normalize_text(rol_nombre) == nombre_normalizado:
                                duplicado = True
                                break

                        if not duplicado:
                            c.execute("INSERT INTO roles (nombre, descripcion, is_hidden) VALUES (%s, %s, %s) RETURNING id_rol", (nombre_rol, descripcion_rol, 1 if is_hidden else 0))
                            new_role_id = c.fetchone()[0]
                            try:
                                from .utils import normalize_text
                                base_norm = normalize_text(nombre_rol)
                                base_norm = base_norm.replace("  ", " ").strip()
                                if base_norm.startswith("dpto "):
                                    base_norm = base_norm.replace("dpto ", "", 1).strip()
                                admin_name = f"adm_{base_norm.replace(' ', '_')}"
                                c.execute("SELECT id_rol FROM roles WHERE nombre = %s", (admin_name,))
                                exists_admin = c.fetchone()
                                if not exists_admin:
                                    c.execute("INSERT INTO roles (nombre, descripcion, is_hidden, view_type) VALUES (%s, %s, %s, %s) RETURNING id_rol", (admin_name, f"Departamento administrador para: {nombre_rol}", 0, "admin_tecnico"))
                            except Exception:
                                pass
                            conn.commit()
                            st.success(f"Departamento '{nombre_rol}' agregado correctamente.")
                            st.rerun()
                        else:
                            st.error("Este departamento ya existe (con un nombre similar).")
                    except Exception as e:
                        if "UNIQUE constraint failed" in str(e):
                            st.error("Este departamento ya existe.")
                        else:
                            st.error(f"Error al agregar departamento: {str(e)}")
                    finally:
                        conn.close()
            else:
                st.error("El nombre del departamento es obligatorio.")

    # Mostrar lista de departamentos existentes
    st.subheader("Departamentos Existentes")
    conn = get_connection()

    # Verificar si la columna is_hidden existe en la tabla roles
    c = conn.cursor()
    try:
        c.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'roles' AND column_name = 'is_hidden'
        """)
        has_is_hidden = c.fetchone() is not None
    except Exception:
        # Fallback para bases de datos que no soportan information_schema
        try:
            c.execute("SELECT is_hidden FROM roles LIMIT 1")
            has_is_hidden = True
        except Exception:
            has_is_hidden = False

    # Lecturas con pandas usando SQLAlchemy (evita warnings)
    engine = get_engine()

    if has_is_hidden:
        roles_df = pd.read_sql_query(
            text("SELECT id_rol, nombre, descripcion, is_hidden FROM roles ORDER BY nombre"),
            con=engine,
        )
        if 'is_hidden' in roles_df.columns:
            roles_df['Oculto'] = roles_df['is_hidden'].apply(lambda x: 'Sí' if x else 'No')
            roles_df = roles_df.drop(columns=['is_hidden'])
    else:
        roles_df = pd.read_sql_query(
            text("SELECT id_rol, nombre, descripcion FROM roles ORDER BY nombre"),
            con=engine,
        )

    conn.close()

    if not roles_df.empty:
        if 'id_rol' in roles_df.columns:
            st.dataframe(roles_df.drop(columns=['id_rol']), use_container_width=True)
        else:
            st.dataframe(roles_df, use_container_width=True)
    else:
        st.info("No hay departamentos registrados.")

    # Formularios para editar y eliminar departamentos
    render_department_edit_delete_forms(roles_df)

    with st.expander("Asignar vista por departamento"):
        try:
            engine = get_engine()
            df_roles = pd.read_sql_query(text("SELECT id_rol, nombre, COALESCE(view_type,'') AS view_type FROM roles ORDER BY nombre"), con=engine)
        except Exception:
            df_roles = pd.DataFrame(columns=["id_rol","nombre","view_type"])
        options = [(int(r["id_rol"]), r["nombre"]) for _, r in df_roles.iterrows()]
        if options:
            role_ids = [rid for rid, _ in options]
            selected_role_id = st.selectbox("Departamento", options=role_ids, format_func=lambda rid: next(name for rid2, name in options if rid2 == rid))
            view_options = ["tecnico", "comercial", "admin_comercial", "admin_tecnico", "hipervisor"]
            current_view = ""
            try:
                current_view = df_roles[df_roles["id_rol"] == selected_role_id]["view_type"].iloc[0]
            except Exception:
                current_view = ""
            selected_view = st.selectbox("Vista asignada", options=view_options, index=(view_options.index(current_view) if current_view in view_options else 0))
            if st.button("Guardar asignación de vista"):
                conn = get_connection()
                c = conn.cursor()
                try:
                    c.execute("UPDATE roles SET view_type = %s WHERE id_rol = %s", (selected_view, int(selected_role_id)))
                    conn.commit()
                    st.success("Vista actualizada.")
                    st.rerun()
                except Exception as e:
                    conn.rollback()
                    st.error(str(e))
                finally:
                    conn.close()


def render_department_edit_delete_forms(roles_df: pd.DataFrame):
    """Renderiza formularios de edición y eliminación de departamentos"""
    # Formulario para editar departamentos
    with st.expander("Editar Departamento"):
        if not roles_df.empty:
            # Filtrar departamentos protegidos para edición
            roles_editables_df = roles_df[~roles_df['nombre'].str.lower().isin(['admin'])]

            if not roles_editables_df.empty:
                rol_options = [f"{row['id_rol']} - {row['nombre']}" for _, row in roles_editables_df.iterrows()]
                selected_rol = st.selectbox("Seleccionar Departamento para Editar", options=rol_options, key="select_rol_edit")

                if selected_rol:
                    rol_id = int(selected_rol.split(' - ')[0])
                    rol_actual = roles_editables_df[roles_editables_df['id_rol'] == rol_id].iloc[0]

                    nuevo_nombre = st.text_input("Nuevo Nombre", value=rol_actual['nombre'], key="edit_role_name")
                    nueva_descripcion = st.text_area("Nueva Descripción", value=rol_actual['descripcion'] if pd.notna(rol_actual['descripcion']) else "", key="edit_role_desc")
                    is_hidden = st.checkbox("Ocultar en listas desplegables", value=bool(rol_actual.get('is_hidden', 0)), key="edit_role_hidden")

                    if st.button("Guardar Cambios", key="save_rol_edit"):
                        if nuevo_nombre:
                            conn = get_connection()
                            c = conn.cursor()
                            try:
                                c.execute(
                                    "UPDATE roles SET nombre = %s, descripcion = %s, is_hidden = %s WHERE id_rol = %s",
                                    (nuevo_nombre, nueva_descripcion, 1 if is_hidden else 0, rol_id),
                                )
                                conn.commit()
                                st.success("Departamento actualizado correctamente.")
                                st.rerun()
                            except Exception as e:
                                if "UNIQUE constraint failed" in str(e):
                                    st.error("Ya existe un departamento con ese nombre.")
                                else:
                                    st.error(f"Error al actualizar departamento: {str(e)}")
                            finally:
                                conn.close()
                        else:
                            st.error("El nombre del departamento no puede estar vacío.")
            else:
                st.info("No hay departamentos disponibles para editar (los departamentos protegidos no se pueden modificar).")
        else:
            st.info("No hay departamentos para editar.")

    # Formulario para eliminar departamentos
    with st.expander("Eliminar Departamento"):
        if not roles_df.empty:
            # Filtrar departamentos protegidos para eliminación usando criterios dinámicos
            # Los roles del sistema tienen descripciones que empiezan con "Rol del sistema:"
            roles_eliminables_df = roles_df[
                ~roles_df['descripcion'].str.startswith('Rol del sistema:', na=False)
            ]

            if not roles_eliminables_df.empty:
                rol_options = [f"{row['id_rol']} - {row['nombre']}" for _, row in roles_eliminables_df.iterrows()]
                selected_rol = st.selectbox("Seleccionar Departamento para Eliminar", options=rol_options, key="select_rol_delete")

                if selected_rol:
                    rol_id = int(selected_rol.split(' - ')[0])

                    if st.button("Eliminar Departamento", key="delete_rol_btn"):
                        conn = get_connection()
                        c = conn.cursor()
                        c.execute("SELECT COUNT(*) FROM usuarios WHERE rol_id = %s", (rol_id,))
                        count = c.fetchone()[0]

                        if count > 0:
                            st.error(f"No se puede eliminar el departamento porque está asignado a {count} usuarios.")
                        else:
                            c.execute("DELETE FROM roles WHERE id_rol = %s", (rol_id,))
                            conn.commit()
                            st.success("Departamento eliminado exitosamente.")
                            st.rerun()
                        conn.close()
            else:
                st.info("No hay departamentos disponibles para eliminar (los departamentos protegidos no se pueden eliminar).")
        else:
            st.info("No hay departamentos para eliminar.")
