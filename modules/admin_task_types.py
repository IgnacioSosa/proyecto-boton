import streamlit as st
from .database import (
    get_connection,
    get_tipos_dataframe_with_roles,
    get_roles_dataframe,
    expand_role_ids_to_individuals,
    individual_role_ids_to_department_ids,
    only_department_roles,
    repair_task_type_roles_missing_from_departments,
    migrate_task_type_department_roles,
    repair_task_types_without_any_roles,
)
from .utils import show_success_message, safe_rerun


def _build_label_for_role(row):
    """Label simple para el multiselect.

    Solo el nombre del rol (sin prefijos "Departamento: / Admin: / Rol:").
    Si el nombre empieza con dpto_/adm_ se deja tal cual en el chip (no es
    necesario agregar prefijos que ocupen ancho).
    """
    return str(getattr(row, "nombre", "")).strip()


def _compute_default_selection_for_edit(existing_role_ids, roles_df):
    """Calcula qué ids deben marcarse por defecto en el multiselect mixto.

    Estrategia (SIN auto-promover a chips de dpto, porque generaba
    ambigüedad cuando existing == expand(dpto)):

      1. Devuelve simplemente los IDs INDIVIDUALES ORIGINALES que estaban
         guardados en `tipos_tarea_roles`, filtrados por lo que exista en
         roles_df.
      2. Si algún id no existe en roles_df (rol borrado o no incluido en el
         multiselect), se filtra para no romper el `default=` del Streamlit.

    Así, el usuario VE exactamente lo que guardó (ej: "tecnico + adm_tecnico")
    y NUNCA le aparece el chip "dpto_tecnico" sin que él lo haya elegido
    explícitamente al guardar. Al guardar, si después selecciona un dpto,
    `expand_role_ids_to_individuals` lo expandirá bien a individuales (como
    ya hace hoy).
    """
    import re

    def _norm(s):
        return re.sub(r"[^a-z0-9]+", "_", str(s or "").strip().lower()).strip("_")

    if not existing_role_ids:
        return []
    try:
        existing = {int(x) for x in existing_role_ids}
    except (TypeError, ValueError):
        return []

    all_ids_known = set()
    for row in roles_df.itertuples(index=False):
        rid = getattr(row, "id_rol", None)
        if rid is None:
            continue
        try:
            all_ids_known.add(int(rid))
        except (TypeError, ValueError):
            continue

    return sorted(rid for rid in existing if rid in all_ids_known)


def render_task_type_management():
    """Renderiza la gestión de tipos de tarea (extraído)"""
    st.subheader("Gestión de Tipos de Tarea")

    if "task_type_counter" not in st.session_state:
        st.session_state.task_type_counter = 0

    # ============================================================
    # Saneos: SOLO al MONTAR el panel (una sola vez por session_state
    # en esta carga). Después NO tocamos la tabla `tipos_tarea_roles`
    # durante la edición, para NO revertir subsets custom que el admin
    # guarde (ej: "solo tecnico, sin adm_tecnico").
    # ============================================================
    _tt_flag = "__task_types_repairs_done_once"
    if not st.session_state.get(_tt_flag, False):
        migrate_task_type_department_roles()
        repair_task_type_roles_missing_from_departments()
        repair_task_types_without_any_roles()
        st.session_state[_tt_flag] = True

    # Incluimos roles ocultos (exclude_hidden=False) para que aparezcan los
    # dptos is_hidden como dpto_compras, dpto_administracion, dpto_rrhh.
    # Usamos exclude_admin=False porque los adm_* (adm_tecnico, adm_comercial,
    # etc.) NO son el rol de admin global. El rol "admin" global se excluye
    # aparte por nombre más abajo; si ponemos exclude_admin=True, se quitan
    # TODOS los adm_*, y entonces el default selection no los ve, causando
    # que existing={tecnico, adm_tecnico} se muestre erróneamente como
    # dpto_tecnico (solo).
    roles_df = get_roles_dataframe(
        exclude_admin=False, exclude_sin_rol=True, exclude_hidden=False
    )
    # Excluimos manualmente el rol global de admin (nombre exacto "admin")
    # y el hipervisor (opcional: lo dejamos, ya que es un rol del personal
    # que podría acceder a tipos de tarea). Si quieres NO excluir hipervisor,
    # borra el filtro de abajo.
    if (not roles_df.empty) and ("nombre" in roles_df.columns):
        import re as _re

        def _gn(s):
            return _re.sub(
                r"[^a-z0-9]+", "_", str(s or "").strip().lower()
            ).strip("_")

        roles_df = roles_df[
            roles_df["nombre"].map(
                lambda n: _gn(n) not in {"admin", "hipervisor"}
            )
        ].reset_index(drop=True)

    # Modo MIXTO: el multiselect muestra todos los roles disponibles, tanto
    # departamentos como individuales. El usuario puede elegir la combinación
    # que quiera; al guardar, los dptos se expanden a individuales y los
    # individuales se persisten tal cual.
    if not roles_df.empty:
        roles_df = roles_df.sort_values(
            by=["nombre"], kind="mergesort"
        ).reset_index(drop=True)
        roles_df["display_label"] = [
            _build_label_for_role(row)
            for row in roles_df.itertuples(index=False)
        ]
    role_ids_all = roles_df["id_rol"].astype(int).tolist() if not roles_df.empty else []
    role_id_to_label = (
        {int(row.id_rol): row.display_label for row in roles_df.itertuples(index=False)}
        if not roles_df.empty
        else {}
    )
    dptos_df = only_department_roles(roles_df)

    with st.expander("Agregar Tipo de Tarea"):
        new_task_type = st.text_input(
            "Descripción del Tipo de Tarea",
            key=f"new_task_type_{st.session_state.task_type_counter}",
        )

        selected_roles = st.multiselect(
            "Roles / Departamentos que pueden acceder a este tipo de tarea",
            options=role_ids_all,
            format_func=lambda x: role_id_to_label.get(int(x), str(x)),
            key=f"new_task_type_roles_{st.session_state.task_type_counter}",
        )

        if st.button("Agregar Tipo de Tarea", key="add_task_type_btn"):
            if new_task_type:
                new_task_type_normalized = " ".join(new_task_type.strip().split()).title()
                conn = get_connection()
                c = conn.cursor()
                try:
                    c.execute(
                        "SELECT id_tipo FROM tipos_tarea WHERE LOWER(TRIM(descripcion)) = LOWER(TRIM(%s))",
                        (new_task_type_normalized,),
                    )
                    existing = c.fetchone()

                    if existing:
                        st.error(f"⚠️ Ya existe un tipo de tarea similar: '{new_task_type_normalized}'")
                    else:
                        c.execute(
                            "INSERT INTO tipos_tarea (descripcion) VALUES (%s) RETURNING id_tipo",
                            (new_task_type_normalized,),
                        )
                        tipo_id = c.fetchone()[0]

                        for rol_id in expand_role_ids_to_individuals(selected_roles):
                            c.execute(
                                "INSERT INTO tipos_tarea_roles (id_tipo, id_rol) VALUES (%s, %s)",
                                (tipo_id, rol_id),
                            )

                        conn.commit()
                        st.success(f"✅ Tipo de tarea '{new_task_type_normalized}' agregado exitosamente.")
                        st.session_state.task_type_counter += 1
                        safe_rerun()
                except Exception as e:
                    st.error(f"❌ Error al agregar tipo de tarea: {str(e)}")
                finally:
                    conn.close()
            else:
                st.error("La descripción del tipo de tarea es obligatoria.")

    tipos_df = get_tipos_dataframe_with_roles(skip_repairs=True)
    st.subheader("Tipos de Tarea Existentes")
    if not tipos_df.empty:
        if "id_tipo" in tipos_df.columns:
            st.dataframe(tipos_df.drop(columns=["id_tipo"]), use_container_width=True)
        else:
            st.dataframe(tipos_df, use_container_width=True)
    else:
        st.info("No hay tipos de tarea registrados.")

    render_task_type_edit_delete_forms(tipos_df, roles_df, dptos_df, role_ids_all, role_id_to_label)


def render_task_type_edit_delete_forms(
    tipos_df, roles_df, dptos_df, role_ids_all, role_id_to_label
):
    """Formularios de edición y eliminación de tipos de tarea (extraído)"""
    with st.expander("Editar Tipo de Tarea"):
        if not tipos_df.empty:
            tipo_ids = tipos_df["id_tipo"].tolist()
            tipo_descriptions = tipos_df["descripcion"].tolist()
            tipo_options = [f"{tid} - {tdesc}" for tid, tdesc in zip(tipo_ids, tipo_descriptions)]

            selected_tipo_edit = st.selectbox(
                "Seleccionar Tipo de Tarea para Editar",
                options=tipo_options,
                key="select_tipo_edit",
            )
            if selected_tipo_edit:
                tipo_id = int(selected_tipo_edit.split(" - ")[0])
                tipo_row = tipos_df[tipos_df["id_tipo"] == tipo_id].iloc[0]

                edit_tipo_desc = st.text_input(
                    "Descripción del Tipo de Tarea",
                    value=tipo_row["descripcion"],
                    key="edit_tipo_desc",
                )

                conn = get_connection()
                c = conn.cursor()
                try:
                    c.execute("SELECT id_rol FROM tipos_tarea_roles WHERE id_tipo = %s", (tipo_id,))
                    existing_role_ids = [row[0] for row in c.fetchall()]
                finally:
                    conn.close()

                default_ids = _compute_default_selection_for_edit(
                    existing_role_ids, roles_df=roles_df
                )
                default_ids = [rid for rid in default_ids if rid in set(role_ids_all)]

                selected_roles = st.multiselect(
                    "Roles / Departamentos permitidos para este tipo",
                    options=role_ids_all,
                    format_func=lambda x: role_id_to_label.get(int(x), str(x)),
                    default=default_ids,
                    key="edit_task_type_roles",
                )

                if st.button("Guardar Cambios de Tipo de Tarea", key="save_tipo_edit"):
                    if edit_tipo_desc:
                        edit_tipo_desc_normalized = " ".join(edit_tipo_desc.strip().split()).title()
                        conn = get_connection()
                        c = conn.cursor()
                        try:
                            c.execute(
                                "UPDATE tipos_tarea SET descripcion = %s WHERE id_tipo = %s",
                                (edit_tipo_desc_normalized, tipo_id),
                            )
                            c.execute("DELETE FROM tipos_tarea_roles WHERE id_tipo = %s", (tipo_id,))
                            for rol_id in expand_role_ids_to_individuals(selected_roles):
                                c.execute(
                                    "INSERT INTO tipos_tarea_roles (id_tipo, id_rol) VALUES (%s, %s)",
                                    (tipo_id, rol_id),
                                )
                            conn.commit()
                            st.success("Tipo de tarea actualizado exitosamente.")
                            safe_rerun()
                        except Exception as e:
                            st.error(f"Error al actualizar tipo de tarea: {str(e)}")
                        finally:
                            conn.close()
                    else:
                        st.error("La descripción del tipo de tarea es obligatoria.")
        else:
            st.info("No hay tipos de tarea para editar.")

    with st.expander("Eliminar Tipo de Tarea"):
        if not tipos_df.empty:
            tipo_ids = tipos_df["id_tipo"].tolist()
            tipo_descriptions = tipos_df["descripcion"].tolist()
            tipo_options = [f"{tid} - {tdesc}" for tid, tdesc in zip(tipo_ids, tipo_descriptions)]

            selected_tipo_delete = st.selectbox(
                "Seleccionar Tipo de Tarea para Eliminar",
                options=tipo_options,
                key="select_tipo_delete",
            )
            if selected_tipo_delete:
                tipo_id = int(selected_tipo_delete.split(" - ")[0])
                tipo_row = tipos_df[tipos_df["id_tipo"] == tipo_id].iloc[0]

                st.warning("¿Estás seguro de que deseas eliminar este tipo de tarea? Esta acción no se puede deshacer.")
                st.info(f"**Tipo de tarea a eliminar:** {tipo_row['descripcion']}")

                if st.button("Eliminar Tipo de Tarea", key="delete_tipo_btn", type="primary"):
                    conn = get_connection()
                    c = conn.cursor()
                    try:
                        c.execute("SELECT COUNT(*) FROM registros WHERE id_tipo = %s", (tipo_id,))
                        registro_count = c.fetchone()[0]

                        if registro_count > 0:
                            st.error(
                                f"No se puede eliminar el tipo de tarea porque tiene {registro_count} registros asociados."
                            )
                        else:
                            c.execute("DELETE FROM tipos_tarea_roles WHERE id_tipo = %s", (tipo_id,))
                            c.execute("DELETE FROM tipos_tarea_puntajes WHERE id_tipo = %s", (tipo_id,))
                            c.execute("DELETE FROM tipos_tarea WHERE id_tipo = %s", (tipo_id,))
                            conn.commit()
                            show_success_message(f"✅ Tipo de tarea '{tipo_row['descripcion']}' eliminado exitosamente.", 1.5)
                            safe_rerun()
                    except Exception as e:
                        st.error(f"Error al eliminar tipo de tarea: {str(e)}")
                    finally:
                        conn.close()
        else:
            st.info("No hay tipos de tarea para eliminar.")


def clean_duplicate_task_types():
    """Limpia tipos de tarea duplicados manteniendo solo uno de cada tipo (extraído)"""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("SELECT id_tipo, descripcion FROM tipos_tarea ORDER BY id_tipo")
        tipos = c.fetchall()

        grupos_duplicados = {}
        for id_tipo, descripcion in tipos:
            desc_normalizada = " ".join(descripcion.strip().split()).lower()
            grupos_duplicados.setdefault(desc_normalizada, []).append((id_tipo, descripcion))

        duplicados_a_eliminar = []
        grupos_con_duplicados = 0

        for desc_norm, grupo in grupos_duplicados.items():
            if len(grupo) > 1:
                grupos_con_duplicados += 1
                for id_tipo, descripcion in grupo[1:]:
                    duplicados_a_eliminar.append(id_tipo)

        deleted_count = 0
        for id_tipo in duplicados_a_eliminar:
            c.execute("SELECT COUNT(*) FROM registros WHERE id_tipo = %s", (id_tipo,))
            registro_count = c.fetchone()[0]
            if registro_count == 0:
                c.execute("DELETE FROM tipos_tarea_roles WHERE id_tipo = %s", (id_tipo,))
                c.execute("DELETE FROM tipos_tarea WHERE id_tipo = %s", (id_tipo,))
                deleted_count += 1

        conn.commit()
        return deleted_count, grupos_con_duplicados
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
