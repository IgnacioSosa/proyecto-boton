import html
import io
import json
import os
import textwrap
import zipfile
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from .config import PROJECT_UPLOADS_DIR
from .database import get_marcas_dataframe
from .ui_components import inject_project_card_css
from .quotes_data import (
    append_cotizacion_documents,
    create_cotizacion,
    delete_cotizacion,
    get_quote_assignee_users_df,
    get_cotizacion,
    get_cotizacion_comments_df,
    get_cotizacion_documents_df,
    get_cotizacion_items_df,
    get_cotizaciones_dataframe,
    get_proyecto,
    get_visible_quote_projects,
    is_project_open_status,
    is_quote_editable_status,
    request_new_cotizacion_version,
    update_cotizacion,
)
from .utils import safe_rerun


def _scope_prefix(scope):
    return f"cotizaciones_{scope}"


def _is_admin_scope(scope):
    return scope in {"admin_comercial", "compras"}


def _quote_is_editable(row):
    return bool(
        is_project_open_status(row.get("trato_estado"))
        and is_quote_editable_status(row.get("cotizacion_estado"))
    )


def _quote_assignee_label(option):
    nombre = " ".join(
        [
            str(option.get("nombre") or "").strip(),
            str(option.get("apellido") or "").strip(),
        ]
    ).strip() or str(option.get("username") or "Usuario").strip()
    return nombre


def _quote_assignee_options_df(current_assigned_row=None):
    assignees_df = get_quote_assignee_users_df()
    if current_assigned_row:
        current_id = current_assigned_row.get("assigned_to")
        if current_id is not None:
            exists = False
            if not assignees_df.empty and "id" in assignees_df.columns:
                try:
                    exists = bool((pd.to_numeric(assignees_df["id"], errors="coerce") == int(current_id)).any())
                except Exception:
                    exists = False
            if not exists:
                fallback_row = pd.DataFrame(
                    [
                        {
                            "id": int(current_id),
                            "username": "",
                            "nombre": current_assigned_row.get("compras_nombre") or "",
                            "apellido": "",
                            "email": "",
                            "view_type": "",
                            "rol_nombre": "",
                        }
                    ]
                )
                assignees_df = pd.concat([fallback_row, assignees_df], ignore_index=True)
    return assignees_df.drop_duplicates(subset=["id"], keep="first") if not assignees_df.empty else assignees_df


def _quote_brand_options_df():
    try:
        brands_df = get_marcas_dataframe(only_active=True)
        if brands_df is None or brands_df.empty:
            return pd.DataFrame()
        out = brands_df.copy()
        out = out[pd.to_numeric(out.get("id_marca"), errors="coerce").notna()].copy()
        out["id_marca"] = pd.to_numeric(out["id_marca"], errors="coerce").astype(int)
        out["nombre"] = out.get("nombre", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
        out = out[out["nombre"] != ""]
        return out.drop_duplicates(subset=["id_marca"], keep="first").sort_values("nombre")
    except Exception:
        return pd.DataFrame()


def _quote_series_label(value):
    try:
        return str(int(value))
    except Exception:
        return "-"


def _blank_item_row():
    return {"cantidad": 1, "sku": "", "modelo": "", "descripcion": ""}


def _items_dataframe_from_records(records=None):
    rows = records or [_blank_item_row()]
    df = pd.DataFrame(rows)
    for col in ["cantidad", "sku", "modelo", "descripcion"]:
        if col not in df.columns:
            df[col] = 1 if col == "cantidad" else ""
    return df[["cantidad", "sku", "modelo", "descripcion"]]


def _sanitize_editor_df(df):
    if df is None or df.empty:
        return _items_dataframe_from_records()
    out = df.copy()
    for col in ["cantidad", "sku", "modelo", "descripcion"]:
        if col not in out.columns:
            out[col] = 1 if col == "cantidad" else ""
    return out[["cantidad", "sku", "modelo", "descripcion"]]


def _item_row_has_content(row):
    sku = str(row.get("sku") or "").strip()
    modelo = str(row.get("modelo") or "").strip()
    descripcion = str(row.get("descripcion") or "").strip()
    cantidad_value = row.get("cantidad")
    if isinstance(cantidad_value, str):
        cantidad_text = cantidad_value.strip().replace(",", ".")
        if cantidad_text:
            try:
                cantidad_has_content = abs(float(cantidad_text) - 1.0) > 1e-9
            except Exception:
                cantidad_has_content = True
        else:
            cantidad_has_content = False
    else:
        cantidad = pd.to_numeric(cantidad_value, errors="coerce")
        cantidad_has_content = pd.notna(cantidad) and abs(float(cantidad) - 1.0) > 1e-9
    return bool(sku or modelo or descripcion or cantidad_has_content)


def _normalize_item_quantity(value, fallback=1.0):
    if isinstance(value, str):
        text = "".join(ch for ch in value.strip() if ch.isdigit())
        if not text:
            return int(max(1, round(float(fallback))))
        try:
            return max(1, int(text))
        except Exception:
            return int(max(1, round(float(fallback))))
    quantity = pd.to_numeric(value, errors="coerce")
    if pd.isna(quantity):
        return int(max(1, round(float(fallback))))
    try:
        normalized = int(round(float(quantity)))
    except Exception:
        return int(max(1, round(float(fallback))))
    return max(1, normalized)


def _format_item_quantity_for_input(value):
    quantity = _normalize_item_quantity(value, fallback=1.0)
    return str(int(quantity))


def _drop_empty_item_rows(df):
    sanitized = _sanitize_editor_df(df)
    if sanitized.empty:
        return pd.DataFrame(columns=["cantidad", "sku", "modelo", "descripcion"])
    kept_rows = []
    for _, row in sanitized.iterrows():
        if not _item_row_has_content(row):
            continue
        row_data = row.to_dict()
        row_data["cantidad"] = _normalize_item_quantity(row_data.get("cantidad"), fallback=1.0)
        kept_rows.append(row_data)
    if not kept_rows:
        return pd.DataFrame(columns=["cantidad", "sku", "modelo", "descripcion"])
    return _sanitize_editor_df(pd.DataFrame(kept_rows))


def _editor_items_with_trailing_blank(df):
    content_df = _drop_empty_item_rows(df)
    rows = content_df.to_dict("records") if not content_df.empty else []
    rows.append(_blank_item_row())
    return _sanitize_editor_df(pd.DataFrame(rows))


def _items_payload_from_df(df):
    payload = []
    filtered_df = _drop_empty_item_rows(df)
    if filtered_df is None or filtered_df.empty:
        return payload
    for _, row in filtered_df.iterrows():
        payload.append(
            {
                "cantidad": row.get("cantidad"),
                "sku": row.get("sku"),
                "modelo": row.get("modelo"),
                "descripcion": row.get("descripcion"),
            }
        )
    return payload


def _clear_widget_state_prefix(prefix):
    for state_key in list(st.session_state.keys()):
        if str(state_key).startswith(prefix):
            st.session_state.pop(state_key, None)


def _items_dataframe_to_excel_bytes(df):
    output = io.BytesIO()
    export_df = _drop_empty_item_rows(df).copy()
    if "precio" not in export_df.columns:
        export_df["precio"] = ""
    export_df = export_df[["cantidad", "sku", "modelo", "descripcion", "precio"]]
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Items")
    output.seek(0)
    return output.getvalue()


def _dataframe_to_excel_bytes(df, sheet_name="Datos"):
    output = io.BytesIO()
    export_df = df.copy() if df is not None else pd.DataFrame()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name=sheet_name[:31] or "Datos")
    output.seek(0)
    return output.getvalue()


def _documents_zip_bytes(documents_df):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for _, row in documents_df.iterrows():
            file_path = str(row.get("file_path") or "").strip()
            filename = str(row.get("filename") or "").strip() or "documento"
            if not file_path or not os.path.exists(file_path):
                continue
            zip_file.write(file_path, arcname=filename)
    output.seek(0)
    return output.getvalue()


def _render_items_enter_navigation(labels, key):
    components.html(
        f"""
        <script>
        const labels = {json.dumps(labels)};
        const navKey = {json.dumps(key)};
        const doc = window.parent.document;
        const quantityLabels = labels.filter((label) => label.startsWith("Cantidad "));

        function getInputs() {{
          const allInputs = Array.from(doc.querySelectorAll("input"));
          return labels
            .map((label) => allInputs.find((input) => input.getAttribute("aria-label") === label))
            .filter(Boolean);
        }}

        function normalizeQuantityValue(rawValue) {{
          return String(rawValue || "").replace(/[^0-9]/g, "");
        }}

        function bindEnterNavigation() {{
          const inputs = getInputs();
          if (inputs.length !== labels.length) {{
            window.setTimeout(bindEnterNavigation, 120);
            return;
          }}
          inputs.forEach((input, index) => {{
            if (input.dataset.enterNavKey === navKey) {{
              if (quantityLabels.includes(input.getAttribute("aria-label") || "") && input.dataset.qtyRestrictKey !== navKey) {{
                input.dataset.qtyRestrictKey = navKey;
                input.setAttribute("inputmode", "numeric");
                input.setAttribute("pattern", "[0-9]*");
                input.addEventListener("input", () => {{
                  const normalized = normalizeQuantityValue(input.value);
                  if (input.value !== normalized) {{
                    input.value = normalized;
                  }}
                }});
                input.addEventListener("blur", () => {{
                  const normalized = normalizeQuantityValue(input.value);
                  input.value = normalized === "0" ? "1" : normalized;
                }});
              }}
              return;
            }}
            input.dataset.enterNavKey = navKey;
            if (quantityLabels.includes(input.getAttribute("aria-label") || "")) {{
              input.dataset.qtyRestrictKey = navKey;
              input.setAttribute("inputmode", "numeric");
              input.setAttribute("pattern", "[0-9]*");
              input.addEventListener("input", () => {{
                const normalized = normalizeQuantityValue(input.value);
                if (input.value !== normalized) {{
                  input.value = normalized;
                }}
              }});
              input.addEventListener("blur", () => {{
                const normalized = normalizeQuantityValue(input.value);
                input.value = normalized === "0" ? "1" : normalized;
              }});
            }}
            input.addEventListener("keydown", (event) => {{
              if (event.key !== "Enter") {{
                return;
              }}
              event.preventDefault();
              event.stopPropagation();
              const orderedInputs = getInputs();
              const currentIndex = orderedInputs.indexOf(input);
              if (currentIndex === -1) {{
                return;
              }}
              const nextInput = orderedInputs[currentIndex + 1];
              if (nextInput) {{
                input.blur();
                window.setTimeout(() => {{
                  nextInput.focus();
                  if (nextInput.select) {{
                    nextInput.select();
                  }}
                }}, 0);
              }} else {{
                input.blur();
              }}
            }});
          }});
        }}

        bindEnterNavigation();
        </script>
        """,
        height=0,
        width=0,
    )


def _render_quote_items_grid(df, read_only, key):
    base_df = (
        _drop_empty_item_rows(df).copy().reset_index(drop=True)
        if read_only
        else _editor_items_with_trailing_blank(df).copy().reset_index(drop=True)
    )
    base_df["cantidad"] = pd.to_numeric(base_df.get("cantidad"), errors="coerce").fillna(1.0)
    for col in ["sku", "modelo", "descripcion"]:
        base_df[col] = base_df.get(col, pd.Series(dtype=str)).fillna("").astype(str)
    if read_only:
        st.dataframe(base_df, use_container_width=True, hide_index=True)
        return base_df, []

    header_cols = st.columns([0.9, 1.4, 1.1, 1.6])
    header_cols[0].markdown("**Cantidad**")
    header_cols[1].markdown("**Numero de Parte / SKU**")
    header_cols[2].markdown("**Modelo**")
    header_cols[3].markdown("**Descripcion**")

    rows = []
    input_labels = []
    with st.container(height=320):
        for idx, row in base_df.iterrows():
            is_trailing_blank = idx == len(base_df.index) - 1 and not _item_row_has_content(row)
            cols = st.columns([0.9, 1.4, 1.1, 1.6])
            cantidad_label = f"Cantidad {idx + 1}"
            cantidad = cols[0].text_input(
                cantidad_label,
                value=("" if is_trailing_blank else _format_item_quantity_for_input(row.get("cantidad"))),
                key=f"{key}_cantidad_{idx}",
                label_visibility="collapsed",
                placeholder="Cantidad",
            )
            input_labels.append(cantidad_label)
            sku_label = f"SKU {idx + 1}"
            sku = cols[1].text_input(
                sku_label,
                value=str(row.get("sku") or ""),
                key=f"{key}_sku_{idx}",
                label_visibility="collapsed",
                placeholder="Cargar SKU",
            )
            input_labels.append(sku_label)
            modelo_label = f"Modelo {idx + 1}"
            modelo = cols[2].text_input(
                modelo_label,
                value=str(row.get("modelo") or ""),
                key=f"{key}_modelo_{idx}",
                label_visibility="collapsed",
                placeholder="Cargar modelo",
            )
            input_labels.append(modelo_label)
            descripcion_label = f"Descripcion {idx + 1}"
            descripcion = cols[3].text_input(
                descripcion_label,
                value=str(row.get("descripcion") or ""),
                key=f"{key}_descripcion_{idx}",
                label_visibility="collapsed",
                placeholder="Cargar descripcion",
            )
            input_labels.append(descripcion_label)
            rows.append(
                {
                    "cantidad": cantidad,
                    "sku": sku,
                    "modelo": modelo,
                    "descripcion": descripcion,
                }
            )
    _render_items_enter_navigation(input_labels, key=f"{key}_enter_nav_{len(base_df.index)}")
    return _drop_empty_item_rows(pd.DataFrame(rows)), []


def _read_items_from_upload(uploaded_file):
    name = str(getattr(uploaded_file, "name", "") or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(uploaded_file.getvalue()))
    else:
        df = pd.read_csv(io.BytesIO(uploaded_file.getvalue()))
    if df.empty:
        return _items_dataframe_from_records()

    normalized = {}
    for col in df.columns:
        key = str(col).strip().lower()
        normalized[key] = col

    rename_map = {}
    aliases = {
        "cantidad": ["cantidad", "qty", "cant"],
        "sku": ["sku", "numero de parte", "numero de parte / sku", "numero de parte/skus", "numero_parte", "part number"],
        "modelo": ["modelo", "model"],
        "descripcion": ["descripcion", "descrip", "detalle", "description"],
    }
    for target, options in aliases.items():
        for option in options:
            if option in normalized:
                rename_map[normalized[option]] = target
                break

    df = df.rename(columns=rename_map)
    for col in ["cantidad", "sku", "modelo", "descripcion"]:
        if col not in df.columns:
            df[col] = 1 if col == "cantidad" else ""
    return _sanitize_editor_df(df[["cantidad", "sku", "modelo", "descripcion"]])


def _unique_filename(directory, filename):
    name, ext = os.path.splitext(filename)
    candidate = filename
    counter = 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{name}_{counter}{ext}"
        counter += 1
    return candidate


def _persist_uploaded_quote_documents(cotizacion_id, uploaded_files, uploaded_by, vigente_choice):
    if not uploaded_files:
        return []
    save_dir = os.path.join(PROJECT_UPLOADS_DIR, "cotizaciones", str(cotizacion_id))
    os.makedirs(save_dir, exist_ok=True)
    documents = []
    for file_obj in uploaded_files:
        unique_name = _unique_filename(save_dir, file_obj.name)
        file_path = os.path.join(save_dir, unique_name)
        data_bytes = file_obj.getvalue()
        with open(file_path, "wb") as out:
            out.write(data_bytes)
        documents.append(
            {
                "filename": unique_name,
                "file_path": file_path,
                "mime_type": getattr(file_obj, "type", "") or None,
                "file_size": len(data_bytes),
                "uploaded_by": int(uploaded_by),
                "is_vigente": vigente_choice == f"new::{file_obj.name}",
            }
        )
    return documents


def _client_display_name(project_row, show_legal_name=False):
    alias = str(project_row.get("cliente_alias") or "").strip()
    legal_name = str(project_row.get("cliente_nombre") or "").strip()
    fallback = str(project_row.get("marca_nombre") or "").strip() or "Sin cliente"
    if alias:
        if show_legal_name and legal_name and legal_name.casefold() != alias.casefold():
            return f"{alias} ({legal_name})"
        return alias
    if legal_name:
        return legal_name
    return fallback


def _format_project_option(project_row):
    trato = project_row.get("trato_id") or project_row.get("id")
    cliente = _client_display_name(project_row)
    titulo = project_row.get("titulo") or project_row.get("descripcion") or "Sin descripcion"
    return f"Trato {trato} - {cliente} - {titulo}"


def _build_quote_display_dataframe(df):
    out = df.copy()
    out["ID"] = out.get("trato_id").fillna(out.get("proyecto_id"))
    out["Serie"] = out.get("cotizacion_serie", pd.Series(dtype=str)).apply(_quote_series_label)
    out["CUIT"] = out.get("cliente_cuit", pd.Series(dtype=str)).fillna("")
    out["RAZON"] = out.apply(_client_display_name, axis=1)
    out["Marca"] = out.get("marca_nombre", pd.Series(dtype=str)).fillna("-")
    out["VENDEDOR"] = out.get("vendedor_nombre", pd.Series(dtype=str)).fillna("Sin vendedor")
    out["Descripcion"] = out.get("trato_titulo", pd.Series(dtype=str)).fillna("-")
    out["Tipo Venta"] = out.get("tipo_venta", pd.Series(dtype=str)).fillna("-")
    out["Estado"] = out.get("cotizacion_estado", pd.Series(dtype=str)).fillna("-")
    out["Acciones"] = out.apply(lambda row: "Editar" if _quote_is_editable(row) else "Vista", axis=1)
    return out[["ID", "Serie", "CUIT", "RAZON", "Marca", "VENDEDOR", "Descripcion", "Tipo Venta", "Estado", "Acciones"]]


def _empty_quote_display_dataframe():
    return pd.DataFrame(
        columns=["ID", "Serie", "CUIT", "RAZON", "Marca", "VENDEDOR", "Descripcion", "Tipo Venta", "Estado", "Acciones"]
    )


def _render_existing_comments(comments_df):
    st.markdown("**Comentarios**")
    if comments_df.empty:
        st.caption("No hay comentarios registrados.")
        return
    items_html = []
    for _, row in comments_df.iterrows():
        fecha = "-"
        try:
            fecha = pd.to_datetime(row.get("created_at"), errors="coerce").strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass
        autor = html.escape(str(row.get("autor_nombre") or "Usuario"))
        comentario = html.escape(str(row.get("comentario") or "-")).replace("\n", "<br>")
        items_html.append(
            textwrap.dedent(
                f"""
                <div class="quote-comment-item">
                  <div class="quote-comment-meta">
                    <span class="quote-comment-date">{html.escape(fecha)}</span>
                    <span class="quote-comment-author">{autor}</span>
                  </div>
                  <div class="quote-comment-text">{comentario}</div>
                </div>
                """
            ).strip()
        )
    st.html(
        textwrap.dedent(
            f"""
            <style>
              body {{
                margin: 0;
                color: #f5f5f5;
                font-family: sans-serif;
              }}
              .quote-comments-scroll {{
                width: 100%;
                max-height: 320px;
                overflow-y: auto;
                padding-right: 8px;
                scrollbar-width: thin;
                scrollbar-color: rgba(160, 160, 160, 0.35) transparent;
              }}
              .quote-comments-scroll::-webkit-scrollbar {{
                width: 8px;
              }}
              .quote-comments-scroll::-webkit-scrollbar-track {{
                background: transparent;
              }}
              .quote-comments-scroll::-webkit-scrollbar-thumb {{
                background: rgba(160, 160, 160, 0.28);
                border-radius: 999px;
              }}
              .quote-comments-scroll::-webkit-scrollbar-thumb:hover {{
                background: rgba(160, 160, 160, 0.4);
              }}
              .quote-comment-item {{
                padding: 10px 0 12px 0;
                border-bottom: 1px solid rgba(128, 128, 128, 0.14);
              }}
              .quote-comment-item:last-child {{
                border-bottom: none;
                padding-bottom: 0;
              }}
              .quote-comment-meta {{
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                align-items: center;
                margin-bottom: 8px;
              }}
              .quote-comment-date {{
                display: inline-flex;
                align-items: center;
                padding: 2px 7px;
                border-radius: 6px;
                background: rgba(34, 197, 94, 0.08);
                color: #22c55e;
                font-family: monospace;
                font-size: 0.9rem;
              }}
              .quote-comment-author {{
                font-weight: 600;
              }}
              .quote-comment-text {{
                line-height: 1.5;
                word-break: break-word;
              }}
            </style>
            <div class="quote-comments-scroll">
              {''.join(items_html)}
            </div>
            """
        ).strip(),
        width="stretch",
    )


def _render_filter_button_spacer():
    st.markdown("<div style='height: 1.75rem;'></div>", unsafe_allow_html=True)


def _quote_status_class(value):
    status = str(value or "").strip().lower()
    if status == "solicitado":
        return "solicitado"
    if status == "enviado":
        return "enviado"
    if status == "cancelado / cerrado":
        return "cancelado-cerrado"
    return "solicitado"


def _format_compact_comment_html(comments_df):
    if comments_df is None or comments_df.empty:
        return "<div class='value muted'>No hay comentarios registrados.</div>"
    row = comments_df.iloc[0]
    autor = html.escape(str(row.get("autor_nombre") or "Usuario"))
    comentario = html.escape(str(row.get("comentario") or "").strip())
    if len(comentario) > 120:
        comentario = comentario[:117] + "..."
    fecha = "-"
    try:
        fecha = pd.to_datetime(row.get("created_at"), errors="coerce").strftime("%d/%m/%Y %H:%M")
    except Exception:
        pass
    return (
        f"<div class='value'>{comentario or '-'}</div>"
        f"<div class='quote-card-mini-meta'>{autor} • {html.escape(fecha)}</div>"
    )


def _format_compact_docs_html(documents_df):
    if documents_df is None or documents_df.empty:
        return "<div class='value muted'>No hay documentos cargados.</div>"
    top_docs = documents_df.head(2)
    items = []
    for _, row in top_docs.iterrows():
        version_label = html.escape(str(row.get("version_label") or "Version"))
        filename = html.escape(str(row.get("filename") or "Documento"))
        suffix = " (vigente)" if bool(row.get("is_vigente")) else ""
        items.append(f"<div class='quote-card-doc-item'>{version_label}: {filename}{suffix}</div>")
    extra_count = max(len(documents_df) - len(top_docs), 0)
    extra_html = f"<div class='quote-card-mini-meta'>+{extra_count} adjunto(s) mas</div>" if extra_count else ""
    return "".join(items) + extra_html


def _render_quote_summary_card(selected_row, quote_detail, comments_df, docs_df, open_param_name=None, scope="commercial"):
    inject_project_card_css()
    trato = int(selected_row.get("trato_id") or selected_row.get("proyecto_id") or 0)
    cotizacion_id = int(selected_row.get("cotizacion_id") or 0)
    serie_label = _quote_series_label(selected_row.get("cotizacion_serie"))
    razon = _client_display_name(selected_row) or "-"
    vendedor = selected_row.get("vendedor_nombre") or "-"
    marca = selected_row.get("marca_nombre") or "-"
    estado = selected_row.get("cotizacion_estado") or "-"
    descripcion = selected_row.get("trato_titulo") or "-"
    tipo_venta = selected_row.get("tipo_venta") or "-"
    solicitante = quote_detail.get("solicitante_nombre") or "-"
    compras = quote_detail.get("compras_nombre") or "-"
    estado_cls = _quote_status_class(estado)
    comments_html = _format_compact_comment_html(comments_df)
    docs_html = _format_compact_docs_html(docs_df)

    def _html_escape(value):
        return html.escape(str(value or "-"))

    preserved_params_html = ""
    if open_param_name:
        preserved_inputs = []
        for key, value in st.query_params.items():
            if key in {open_param_name, "qscope"}:
                continue
            values = value if isinstance(value, list) else [value]
            for entry in values:
                preserved_inputs.append(
                    f'<input type="hidden" name="{_html_escape(key)}" value="{_html_escape(entry)}" />'
                )
        preserved_params_html = "".join(preserved_inputs)
    hidden_open = (
        f'<input type="hidden" name="{_html_escape(open_param_name)}" value="{cotizacion_id}" />'
        if open_param_name
        else ""
    )
    card_submit = '<button type="submit" class="card-submit"></button>' if open_param_name else ""
    card_wrapper_open = '<form method="get" class="card-form">' if open_param_name else '<div>'
    card_wrapper_close = '</form>' if open_param_name else '</div>'

    st.markdown(
        f"""
        <style>
          .quote-card-wrap {{
            margin: 10px 0 14px 0;
          }}
          .quote-card-wrap .project-card {{
            cursor: default;
            align-items: flex-start;
          }}
          .quote-card-wrap .project-card:hover {{
            border-color: rgba(128, 128, 128, 0.2);
            transform: none;
            box-shadow: none;
          }}
          .quote-card-wrap .project-info {{
            gap: 6px;
          }}
          .quote-card-wrap .project-title {{
            margin-bottom: 0;
          }}
          .quote-card-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 2px;
            font-size: 0.9rem;
            opacity: 0.78;
          }}
          .quote-card-blocks {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            width: 100%;
            margin-top: 12px;
          }}
          .quote-card-block {{
            background: rgba(128, 128, 128, 0.08);
            border-radius: 10px;
            padding: 12px 14px;
            min-width: 0;
          }}
          .quote-card-block .label {{
            font-size: 0.82rem;
            opacity: 0.75;
            margin-bottom: 4px;
          }}
          .quote-card-block .value {{
            font-size: 0.98rem;
            font-weight: 600;
            line-height: 1.35;
          }}
          .quote-card-block .value.muted {{
            font-weight: 500;
            opacity: 0.72;
          }}
          .quote-card-mini-meta {{
            margin-top: 6px;
            font-size: 0.82rem;
            opacity: 0.7;
          }}
          .quote-card-doc-item {{
            font-size: 0.94rem;
            line-height: 1.4;
            margin-top: 2px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }}
          .quote-summary-foot {{
            font-size: 0.92rem;
            opacity: 0.85;
            margin-top: 12px;
          }}
          .status-pill.solicitado {{
            background: rgba(234, 179, 8, 0.12);
            color: #facc15;
            border-color: rgba(234, 179, 8, 0.3);
          }}
          .status-pill.enviado {{
            background: rgba(34, 197, 94, 0.12);
            color: #34d399;
            border-color: rgba(34, 197, 94, 0.3);
          }}
          .status-pill.cancelado-cerrado {{
            background: rgba(239, 68, 68, 0.12);
            color: #f87171;
            border-color: rgba(239, 68, 68, 0.3);
          }}
          .dot-left.solicitado {{
            background-color: #facc15;
            box-shadow: 0 0 8px rgba(250, 204, 21, 0.35);
          }}
          .dot-left.enviado {{
            background-color: #34d399;
            box-shadow: 0 0 8px rgba(52, 211, 153, 0.35);
          }}
          .dot-left.cancelado-cerrado {{
            background-color: #f87171;
          }}
          @media (max-width: 1100px) {{
            .quote-card-blocks {{
              grid-template-columns: 1fr;
            }}
          }}
        </style>
        <div class="quote-card-wrap">
          {card_wrapper_open}
          {preserved_params_html}
          {hidden_open}
          <div class="project-card selected">
            <div class="project-info">
              <div class="project-title" title="{_html_escape(descripcion)}">
                <span class="dot-left {estado_cls}"></span>
                <span>{_html_escape(descripcion)}</span>
              </div>
              <div class="project-sub">
                <span class="hl-label">ID</span>
                <span class="hl-val bright">{_html_escape(trato)}</span>
                <span class="hl-sep">•</span>
                <span class="hl-val client">{_html_escape(razon)}</span>
              </div>
              <div class="project-sub2">
                <span>Cotizacion</span>
                <span class="hl-sep">•</span>
                <span>{_html_escape(tipo_venta)}</span>
                <span class="hl-sep">•</span>
                <span>Vendedor: {_html_escape(vendedor)}</span>
              </div>
              <div class="quote-card-blocks">
                <div class="quote-card-block">
                  <div class="label">Solicitante</div>
                  <div class="value">{_html_escape(solicitante)}</div>
                </div>
                <div class="quote-card-block">
                    <div class="label">Asignado</div>
                  <div class="value">{_html_escape(compras)}</div>
                </div>
                  <div class="quote-card-block">
                    <div class="label">Serie</div>
                    <div class="value">{_html_escape(serie_label)}</div>
                  </div>
                  <div class="quote-card-block">
                    <div class="label">Marca</div>
                    <div class="value">{_html_escape(marca)}</div>
                  </div>
                <div class="quote-card-block">
                  <div class="label">Comentarios</div>
                  {comments_html}
                </div>
                <div class="quote-card-block">
                  <div class="label">Adjuntos</div>
                  {docs_html}
                </div>
              </div>
              <div class="quote-summary-foot">
                Trato {_html_escape(trato)} vinculado a esta solicitud.
              </div>
            </div>
            <div style="display:flex; align-items:center;">
              <span class="status-pill {estado_cls}">{_html_escape(estado)}</span>
            </div>
          </div>
          {card_submit}
          {card_wrapper_close}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_existing_documents(documents_df):
    st.markdown("**Documentos adjuntos**")
    if documents_df.empty:
        st.caption("No hay documentos cargados.")
        return
    display_df = documents_df.copy()
    display_df["version"] = display_df.get("version_label", pd.Series(dtype=str)).fillna("Version")
    display_df["vigente"] = display_df["is_vigente"].apply(lambda value: "Si" if bool(value) else "")
    display_df["fecha"] = pd.to_datetime(display_df["created_at"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M")
    st.dataframe(
        display_df[["version", "filename", "uploaded_by_name", "fecha", "vigente"]].rename(
            columns={
                "version": "Version",
                "filename": "Archivo",
                "uploaded_by_name": "Subido por",
                "fecha": "Fecha",
                "vigente": "Vigente",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
    available_docs = []
    for _, row in documents_df.iterrows():
        file_path = str(row.get("file_path") or "").strip()
        if not file_path or not os.path.exists(file_path):
            continue
        available_docs.append(row.to_dict())
    if not available_docs:
        st.caption("No se encontraron archivos disponibles para descargar.")
        return

    vigente_doc = next((doc for doc in available_docs if bool(doc.get("is_vigente"))), None)
    if vigente_doc is None and available_docs:
        vigente_doc = available_docs[0]

    if vigente_doc is not None:
        vigente_version = str(vigente_doc.get("version_label") or "Version").strip()
        vigente_name = str(vigente_doc.get("filename") or "Documento").strip()
        vigente_author = str(vigente_doc.get("uploaded_by_name") or "-").strip() or "-"
        vigente_date = pd.to_datetime(vigente_doc.get("created_at"), errors="coerce")
        vigente_date_label = vigente_date.strftime("%d/%m/%Y %H:%M") if pd.notna(vigente_date) else "-"
        st.markdown(
            f"""
            <div style="
                margin: 0.35rem 0 0.85rem 0;
                padding: 0.9rem 1rem;
                border-radius: 12px;
                border: 1px solid rgba(34, 197, 94, 0.28);
                background: rgba(34, 197, 94, 0.08);
            ">
              <div style="display:flex; align-items:center; gap:0.55rem; margin-bottom:0.45rem;">
                <span style="
                    display:inline-flex;
                    align-items:center;
                    justify-content:center;
                    padding:0.18rem 0.62rem;
                    border-radius:999px;
                    background:rgba(34, 197, 94, 0.16);
                    border:1px solid rgba(34, 197, 94, 0.3);
                    color:#34d399;
                    font-size:0.78rem;
                    font-weight:700;
                ">Vigente</span>
                <span style="font-weight:700;">{html.escape(vigente_version)}</span>
              </div>
              <div style="font-size:1rem; font-weight:600; margin-bottom:0.3rem; word-break:break-word;">
                {html.escape(vigente_name)}
              </div>
              <div style="opacity:0.78; font-size:0.86rem;">
                Subido por {html.escape(vigente_author)} • {html.escape(vigente_date_label)}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


    selector_options = [doc["id"] for doc in available_docs]
    selected_doc_id = st.selectbox(
        "Version para descargar",
        options=selector_options,
        format_func=lambda doc_id: next(
            (
                f"{doc.get('version_label') or 'Version'} - {doc.get('filename') or 'Documento'}"
            )
            for doc in available_docs
            if int(doc.get("id")) == int(doc_id)
        ),
        key="quote_doc_selector",
    )
    selected_doc = next(doc for doc in available_docs if int(doc.get("id")) == int(selected_doc_id))

    if bool(selected_doc.get("is_vigente")):
        st.caption("Estas por descargar el documento vigente.")

    download_cols = st.columns([1, 1.1, 2])
    with download_cols[0]:
        with open(str(selected_doc.get("file_path")), "rb") as file_obj:
            st.download_button(
                "Descargar archivo",
                data=file_obj.read(),
                file_name=selected_doc.get("filename") or "documento",
                key=f"quote_doc_dl_{selected_doc.get('id')}",
                use_container_width=True,
            )
    with download_cols[1]:
        if len(available_docs) > 1:
            st.download_button(
                "Descargar todo",
                data=_documents_zip_bytes(pd.DataFrame(available_docs)),
                file_name="cotizacion_adjuntos.zip",
                mime="application/zip",
                key="quote_doc_dl_all",
                use_container_width=True,
            )


def _clear_filters(prefix):
    for suffix in ["filter_id", "filter_cuit", "filter_razon", "filter_estado"]:
        st.session_state[f"{prefix}_{suffix}"] = "Todos"
    safe_rerun()


def _apply_filters(df, prefix):
    filtered = df.copy()
    filter_id = st.session_state.get(f"{prefix}_filter_id", "Todos")
    filter_cuit = st.session_state.get(f"{prefix}_filter_cuit", "Todos")
    filter_razon = st.session_state.get(f"{prefix}_filter_razon", "Todos")
    filter_estado = st.session_state.get(f"{prefix}_filter_estado", "Todos")

    if filter_id != "Todos":
        filtered = filtered[filtered.get("trato_id").fillna(filtered.get("proyecto_id")).astype(str) == str(filter_id)]
    if filter_cuit != "Todos":
        filtered = filtered[filtered.get("cliente_cuit", pd.Series(dtype=str)).fillna("") == str(filter_cuit)]
    if filter_razon != "Todos":
        filtered = filtered[filtered.get("cliente_nombre", pd.Series(dtype=str)).fillna("") == str(filter_razon)]
    if filter_estado != "Todos":
        filtered = filtered[filtered.get("cotizacion_estado", pd.Series(dtype=str)).fillna("") == str(filter_estado)]
    return filtered


def render_create_project_quote_section(section_key="create_quote", draft_context=None):
    assignees_df = _quote_assignee_options_df()
    assignee_ids = assignees_df["id"].tolist() if not assignees_df.empty and "id" in assignees_df.columns else []
    brands_df = _quote_brand_options_df()
    brand_ids = brands_df["id_marca"].tolist() if not brands_df.empty and "id_marca" in brands_df.columns else []

    mode = st.radio(
        "Cotizacion",
        options=["No cargar ahora", "Cargar cotizacion", "Solicitar a compras"],
        key=f"{section_key}_mode",
        horizontal=True,
    )
    if mode == "No cargar ahora":
        return {"mode": "none", "comment": "", "uploaded_docs": [], "items": [], "vigente_choice": None, "assigned_to": None}

    if assignees_df.empty:
        st.error("No hay usuarios activos de Compras o adm_comercial para asignar la cotización.")
        return {"mode": "none", "comment": "", "uploaded_docs": [], "items": [], "vigente_choice": None, "assigned_to": None}
    if not brand_ids:
        st.error("No hay marcas activas disponibles para asignar a la cotización.")
        return {"mode": "none", "comment": "", "uploaded_docs": [], "items": [], "vigente_choice": None, "assigned_to": None}

    assigned_to = st.selectbox(
        "Enviar a",
        options=assignee_ids,
        index=0,
        format_func=lambda uid: _quote_assignee_label(
            assignees_df[pd.to_numeric(assignees_df["id"], errors="coerce") == int(uid)].iloc[0].to_dict()
        ),
        key=f"{section_key}_assigned_to",
    )
    selected_brand_id = st.selectbox(
        "Marca",
        options=brand_ids,
        index=0,
        format_func=lambda mid: brands_df.loc[brands_df["id_marca"] == int(mid), "nombre"].iloc[0],
        key=f"{section_key}_brand_id",
    )

    if mode == "Cargar cotizacion":
        st.caption("Adjunta una cotización ya disponible para que quede asociada automáticamente al nuevo trato.")
        uploader_version = int(st.session_state.get(f"{section_key}_docs_version", 0) or 0)
        uploaded_docs = st.file_uploader(
            "Adjuntar cotizacion",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            key=f"{section_key}_docs_{uploader_version}",
        )
        comment = st.text_area(
            "Comentario de cotizacion",
            key=f"{section_key}_comment",
            placeholder="Agregar detalle para la cotización.",
        )
        vigente_choice = None
        if uploaded_docs:
            labels = [f"Nuevo: {file_obj.name}" for file_obj in uploaded_docs]
            value_map = {f"Nuevo: {file_obj.name}": f"new::{file_obj.name}" for file_obj in uploaded_docs}
            vigente_label = st.radio(
                "Indicar cual es la vigente",
                options=labels,
                index=0,
                key=f"{section_key}_vigente",
            )
            vigente_choice = value_map.get(vigente_label)
        return {
            "mode": "upload",
            "comment": comment,
            "uploaded_docs": uploaded_docs or [],
            "items": [],
            "vigente_choice": vigente_choice,
            "assigned_to": assigned_to,
            "marca_id": selected_brand_id,
        }

    st.caption("Genera la cotización asociada al nuevo trato y envía la solicitud al sector Compras.")

    data_key = f"{section_key}_items_data"
    if data_key not in st.session_state:
        st.session_state[data_key] = _items_dataframe_from_records()

    edited_df, _ = _render_quote_items_grid(
        _sanitize_editor_df(st.session_state.get(data_key)),
        read_only=False,
        key=f"{data_key}_editor",
    )
    st.session_state[data_key] = edited_df

    comment = st.text_area(
        "Comentario de cotizacion",
        key=f"{section_key}_comment",
        placeholder="Agregar detalle para la cotización.",
    )
    return {
        "mode": "request",
        "comment": comment,
        "uploaded_docs": [],
        "items": _items_payload_from_df(st.session_state.get(data_key)),
        "vigente_choice": None,
        "assigned_to": assigned_to,
        "marca_id": selected_brand_id,
    }


def create_project_quote_from_create_flow(project_id, user_id, mode, items=None, comment="", uploaded_docs=None, vigente_choice=None, scope="commercial", assigned_to=None, marca_id=None):
    selected_mode = str(mode or "none").strip().lower()
    files = list(uploaded_docs or [])
    if selected_mode == "none":
        return None
    if selected_mode == "upload" and not files:
        raise ValueError("Debes adjuntar al menos una cotización para cargarla junto al trato.")

    items_payload = list(items or [])
    if selected_mode == "upload" and not items_payload:
        merged_frames = []
        for file_obj in files:
            imported_df = _read_items_from_upload(file_obj)
            cleaned_df = _drop_empty_item_rows(imported_df)
            if cleaned_df is not None and not cleaned_df.empty:
                merged_frames.append(cleaned_df)
        if merged_frames:
            items_payload = _items_payload_from_df(pd.concat(merged_frames, ignore_index=True))

    initial_status = "Enviado" if selected_mode == "upload" else "Solicitado"
    notify_request = selected_mode != "upload"
    cotizacion_id = create_cotizacion(
        proyecto_id=project_id,
        requested_by=user_id,
        items=items_payload,
        comentario_inicial=comment,
        scope=scope,
        initial_status=initial_status,
        notify_request=notify_request,
        assigned_to=assigned_to,
        marca_id=marca_id,
    )
    if files:
        vigente_choice = vigente_choice or f"new::{files[0].name}"
        docs_payload = _persist_uploaded_quote_documents(
            cotizacion_id,
            files,
            uploaded_by=user_id,
            vigente_choice=vigente_choice,
        )
        append_cotizacion_documents(cotizacion_id, docs_payload)
    return cotizacion_id


def render_project_quote_entry(user_id, project_id, scope="commercial", key_prefix=None):
    prefix = _scope_prefix(scope)
    key_prefix = key_prefix or f"{prefix}_project_quote_{int(project_id)}"
    project = get_proyecto(project_id)
    if not project:
        return

    quotes_df = get_cotizaciones_dataframe(user_id, scope=scope)
    project_quotes_df = pd.DataFrame()
    if not quotes_df.empty:
        project_quotes_df = quotes_df[quotes_df.get("proyecto_id").astype("Int64") == int(project_id)].copy()
        if not project_quotes_df.empty:
            project_quotes_df["_serie_sort"] = pd.to_numeric(project_quotes_df.get("cotizacion_serie"), errors="coerce")
            project_quotes_df = project_quotes_df.sort_values(
                ["_serie_sort", "cotizacion_id"],
                ascending=[True, False],
                na_position="last",
            ).drop(columns=["_serie_sort"], errors="ignore")

    can_request = scope in {"commercial", "admin_comercial"} and is_project_open_status(project.get("estado"))
    first_quote_row = project_quotes_df.iloc[0].to_dict() if not project_quotes_df.empty else None
    assignee_users = _quote_assignee_options_df(first_quote_row) if can_request else pd.DataFrame()

    st.markdown(
        """
        <style>
          .status-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 28px;
            padding: 0.2rem 0.65rem;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.25);
            font-size: 0.78rem;
            font-weight: 700;
            line-height: 1;
            letter-spacing: 0.01em;
            white-space: nowrap;
          }
          .status-pill.solicitado {
            background: rgba(234, 179, 8, 0.12);
            color: #facc15;
            border-color: rgba(234, 179, 8, 0.3);
          }
          .status-pill.enviado {
            background: rgba(34, 197, 94, 0.12);
            color: #34d399;
            border-color: rgba(34, 197, 94, 0.3);
          }
          .status-pill.cancelado-cerrado {
            background: rgba(239, 68, 68, 0.12);
            color: #f87171;
            border-color: rgba(239, 68, 68, 0.3);
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <style>
          .quote-entry-actions {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            width: 100%;
            justify-content: center;
            min-height: 100%;
          }
          div[data-testid="stButton"] > button[kind],
          div[data-testid="stDownloadButton"] > button[kind] {
            min-height: 54px;
            height: 54px;
            padding-top: 0.5rem;
            padding-bottom: 0.5rem;
            border-radius: 10px;
          }
        </style>
        <div class="quote-entry-actions"></div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        header_col, new_col = st.columns([3.2, 1.2], vertical_alignment="center")
        with header_col:
            st.markdown("### Cotizacion")
            if project_quotes_df.empty:
                st.caption("Este trato todavía no tiene series de cotización asociadas.")
                if not can_request:
                    st.caption("Solo se pueden solicitar cotizaciones sobre tratos abiertos.")
                elif assignee_users.empty:
                    st.caption("No hay usuarios activos de Compras o adm_comercial para recibir solicitudes.")
                else:
                    st.caption("Cada serie tendrá su propia tarjeta para que puedas iterarla por separado.")
            else:
                st.caption(f"Series activas en este trato: {len(project_quotes_df.index)}.")
        with new_col:
            new_label = "Nueva serie" if not project_quotes_df.empty else "Solicitar cotizacion"
            if st.button(
                new_label,
                key=f"{key_prefix}_new_series",
                type="primary",
                use_container_width=True,
                disabled=(not can_request) or assignee_users.empty,
            ):
                _render_quote_dialog(
                    user_id,
                    scope,
                    cotizacion_id=None,
                    default_project_id=int(project_id),
                    lock_project_selection=True,
                )

    if not project_quotes_df.empty:
        series_container_height = 540 if len(project_quotes_df.index) > 3 else None
        series_container = st.container(height=series_container_height) if series_container_height else st.container()
        with series_container:
            for idx, (_, quote_row) in enumerate(project_quotes_df.iterrows()):
                quote_row = quote_row.to_dict()
                estado = str(quote_row.get("cotizacion_estado") or "-").strip()
                cotizacion_id = int(quote_row.get("cotizacion_id") or 0)
                trato = int(quote_row.get("trato_id") or quote_row.get("proyecto_id") or project_id)
                serie_label = _quote_series_label(quote_row.get("cotizacion_serie"))
                marca_label = str(quote_row.get("marca_nombre") or "-").strip() or "-"
                assigned_label = str(quote_row.get("compras_nombre") or "-").strip() or "-"
                estado_cls = _quote_status_class(estado)
                docs_df = get_cotizacion_documents_df(cotizacion_id)
                docs_count = len(docs_df.index) if docs_df is not None and not docs_df.empty else 0
                updated_label = "-"
                try:
                    updated_label = pd.to_datetime(
                        quote_row.get("cotizacion_updated_at") or quote_row.get("cotizacion_created_at"),
                        errors="coerce",
                    ).strftime("%d/%m/%Y %H:%M")
                except Exception:
                    updated_label = "-"
                download_doc = None
                if not docs_df.empty:
                    vigente_docs = docs_df[docs_df.get("is_vigente") == True]
                    selected_docs = vigente_docs if not vigente_docs.empty else docs_df.head(1)
                    if not selected_docs.empty:
                        candidate = selected_docs.iloc[0].to_dict()
                        file_path = str(candidate.get("file_path") or "").strip()
                        if file_path and os.path.exists(file_path):
                            download_doc = candidate

                with st.container(border=True):
                    info_col, action_col = st.columns([3.4, 1.3], vertical_alignment="top")
                    with info_col:
                        st.markdown(
                            f"""
                            <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
                              <span class="status-pill {estado_cls}">{html.escape(estado)}</span>
                              <span style="opacity:0.82;">Serie {html.escape(serie_label)} asociada al trato {trato}</span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        meta_row_1 = st.columns(2)
                        meta_row_2 = st.columns(2)
                        with meta_row_1[0]:
                            st.markdown(f"**Marca**\n\n{marca_label}")
                        with meta_row_1[1]:
                            st.markdown(f"**Asignado**\n\n{assigned_label}")
                        with meta_row_2[0]:
                            st.markdown(f"**Iteraciones**\n\n{docs_count}")
                        with meta_row_2[1]:
                            st.markdown(f"**Actualizada**\n\n{updated_label}")
                    with action_col:
                        st.markdown("<div style='height: 0.15rem;'></div>", unsafe_allow_html=True)
                        if st.button("Ver cotizacion", key=f"{key_prefix}_open_{cotizacion_id}_{idx}", use_container_width=True):
                            _render_quote_dialog(user_id, scope, cotizacion_id=cotizacion_id)
                        if download_doc:
                            with open(str(download_doc.get("file_path")), "rb") as file_obj:
                                st.download_button(
                                    "Descargar cotizacion",
                                    data=file_obj.read(),
                                    file_name=download_doc.get("filename") or "cotizacion",
                                    key=f"{key_prefix}_download_{cotizacion_id}_{idx}",
                                    use_container_width=True,
                                )
                        else:
                            st.button(
                                "Sin archivo",
                                key=f"{key_prefix}_no_download_{cotizacion_id}_{idx}",
                                use_container_width=True,
                                disabled=True,
                            )


def _render_quote_dialog(user_id, scope, cotizacion_id=None, default_project_id=None, lock_project_selection=False):
    prefix = _scope_prefix(scope)
    editor_id = cotizacion_id if cotizacion_id is not None else (f"new_{int(default_project_id)}" if default_project_id else "new")
    data_key = f"{prefix}_items_data_{editor_id}"
    upload_key = f"{prefix}_items_upload_{editor_id}"

    quote_row = get_cotizacion(cotizacion_id, user_id=user_id, scope=scope) if cotizacion_id else None
    quote_docs_df = get_cotizacion_documents_df(cotizacion_id) if cotizacion_id else pd.DataFrame()
    quote_comments_df = get_cotizacion_comments_df(cotizacion_id) if cotizacion_id else pd.DataFrame()
    quote_items_df = get_cotizacion_items_df(cotizacion_id) if cotizacion_id else pd.DataFrame()
    assignees_df = _quote_assignee_options_df(quote_row)
    quote_brands_df = _quote_brand_options_df()

    editable = True if cotizacion_id is None else _quote_is_editable(quote_row)
    current_quote_status = str((quote_row or {}).get("cotizacion_estado") or "").strip()
    can_manage_closed_quote = bool(
        cotizacion_id is not None
        and current_quote_status == "Cancelado / Cerrado"
        and scope in {"commercial", "admin_comercial"}
        and is_project_open_status((quote_row or {}).get("trato_estado"))
    )
    can_change_status = scope in {"admin_comercial", "compras"}
    read_only = cotizacion_id is not None and not editable
    action_locked = read_only and not can_manage_closed_quote
    can_request_new_version = bool(
        cotizacion_id is not None
        and scope in {"commercial", "admin_comercial"}
        and not read_only
        and quote_row is not None
        and not quote_docs_df.empty
        and str(quote_row.get("cotizacion_estado") or "").strip().lower() != "solicitado"
    )

    visible_projects_df = get_visible_quote_projects(
        user_id,
        scope="admin_comercial" if _is_admin_scope(scope) else "commercial",
        only_open=(cotizacion_id is None),
    )
    if cotizacion_id is not None and quote_row is not None:
        current_project = get_proyecto(quote_row["proyecto_id"])
        if current_project:
            current_df = pd.DataFrame([current_project])
            visible_projects_df = pd.concat([visible_projects_df, current_df], ignore_index=True)
            visible_projects_df = visible_projects_df.drop_duplicates(subset=["id"])

    if visible_projects_df.empty:
        st.error("No hay tratos disponibles para cotizaciones.")
        return

    visible_quotes_df = get_cotizaciones_dataframe(user_id, scope=scope)

    if data_key not in st.session_state:
        if quote_items_df.empty:
            st.session_state[data_key] = _items_dataframe_from_records()
        else:
            st.session_state[data_key] = _sanitize_editor_df(quote_items_df)

    dialog_project = None
    if quote_row is not None:
        dialog_project = get_proyecto(quote_row.get("proyecto_id"))
    elif default_project_id:
        dialog_project = get_proyecto(default_project_id)

    dialog_project_quotes_df = (
        visible_quotes_df[visible_quotes_df.get("proyecto_id").astype("Int64") == int(dialog_project.get("id"))].copy()
        if dialog_project is not None
        and visible_quotes_df is not None
        and not visible_quotes_df.empty
        and "proyecto_id" in visible_quotes_df.columns
        else pd.DataFrame()
    )
    dialog_series_label = _quote_series_label(quote_row.get("cotizacion_serie")) if quote_row else "1"
    if cotizacion_id is None and dialog_project is not None:
        next_series_num = 1
        if not dialog_project_quotes_df.empty:
            try:
                next_series_num = int(pd.to_numeric(dialog_project_quotes_df.get("cotizacion_serie"), errors="coerce").dropna().max()) + 1
            except Exception:
                next_series_num = 1
        dialog_series_label = str(next_series_num)

    dialog_project_title = ""
    if dialog_project is not None:
        dialog_project_title = str(dialog_project.get("titulo") or dialog_project.get("descripcion") or "").strip()
    title = (
        f"{dialog_project_title} (Serie {dialog_series_label})"
        if dialog_project_title
        else ("Pedido de Cotizacion" if cotizacion_id is None else f"Serie {dialog_series_label}")
    )

    @st.dialog(title, width="large")
    def _dialog():
        current_df = _sanitize_editor_df(st.session_state.get(data_key))
        project_options = visible_projects_df["id"].tolist()
        selected_project_default = quote_row["proyecto_id"] if quote_row else (default_project_id or project_options[0])
        if selected_project_default not in project_options:
            project_options = [selected_project_default] + project_options

        selected_project_id = st.selectbox(
            "Trato",
            options=project_options,
            index=project_options.index(selected_project_default),
            format_func=lambda pid: _format_project_option(
                visible_projects_df[visible_projects_df["id"] == pid].iloc[0].to_dict()
            ),
            disabled=(cotizacion_id is not None) or bool(lock_project_selection),
            key=f"{prefix}_project_{editor_id}",
        )
        project = get_proyecto(selected_project_id)
        if not project:
            st.error("No se pudo cargar el trato seleccionado.")
            return

        project_quotes_current_df = (
            visible_quotes_df[visible_quotes_df.get("proyecto_id").astype("Int64") == int(selected_project_id)].copy()
            if visible_quotes_df is not None and not visible_quotes_df.empty and "proyecto_id" in visible_quotes_df.columns
            else pd.DataFrame()
        )
        current_series_label = _quote_series_label(quote_row.get("cotizacion_serie")) if quote_row else "1"
        if cotizacion_id is None:
            next_series_num = 1
            if not project_quotes_current_df.empty:
                try:
                    next_series_num = int(pd.to_numeric(project_quotes_current_df.get("cotizacion_serie"), errors="coerce").dropna().max()) + 1
                except Exception:
                    next_series_num = 1
            current_series_label = str(next_series_num)
        current_iterations_count = len(quote_docs_df.index) if cotizacion_id is not None and not quote_docs_df.empty else 0

        trato_id_display = project.get("trato_id") or project.get("id")
        descripcion_auto = project.get("titulo") or project.get("descripcion") or "-"
        razon_auto = _client_display_name(project)
        contacto_auto = " ".join(
            [
                str(project.get("contacto_nombre") or "").strip(),
                str(project.get("contacto_apellido") or "").strip(),
            ]
        ).strip() or "-"
        telefono_auto = project.get("contacto_telefono") or project.get("cliente_telefono") or "-"
        tipo_venta_auto = project.get("tipo_venta") or "-"

        st.markdown(f"**Trato asociado:** `{trato_id_display}`")
        st.markdown("**Iteraciones**")
        st.write(current_iterations_count)
        info_col1, info_col2 = st.columns(2)
        with info_col1:
            st.markdown("**Descripcion**")
            st.write(descripcion_auto)
            st.markdown("**Razon Social**")
            st.write(razon_auto)
            st.markdown("**Contacto**")
            st.write(contacto_auto)
        with info_col2:
            st.markdown("**Telefono**")
            st.write(telefono_auto)
            st.markdown("**Tipo de Venta**")
            st.write(tipo_venta_auto)
            st.markdown("**Estado del trato**")
            st.write(project.get("estado") or "-")

        items_read_only = read_only or scope == "compras"
        selected_assignee_id = quote_row.get("assigned_to") if quote_row else None
        selected_brand_id = quote_row.get("cotizacion_marca_id") if quote_row else project.get("marca_id")
        if scope in {"commercial", "admin_comercial"}:
            st.markdown("**Enviar a**")
            assignee_ids = assignees_df["id"].tolist() if not assignees_df.empty and "id" in assignees_df.columns else []
            if not assignee_ids:
                st.error("No hay usuarios activos de Compras o adm_comercial para asignar la cotización.")
                return
            if selected_assignee_id is None or selected_assignee_id not in assignee_ids:
                selected_assignee_id = assignee_ids[0]
            selected_assignee_id = st.selectbox(
                "Enviar a",
                options=assignee_ids,
                index=assignee_ids.index(selected_assignee_id),
                format_func=lambda uid: _quote_assignee_label(
                    assignees_df[pd.to_numeric(assignees_df["id"], errors="coerce") == int(uid)].iloc[0].to_dict()
                ),
                disabled=read_only,
                label_visibility="collapsed",
                key=f"{prefix}_assigned_to_{editor_id}",
            )
            st.markdown("**Marca**")
            brand_ids = quote_brands_df["id_marca"].tolist() if not quote_brands_df.empty and "id_marca" in quote_brands_df.columns else []
            if not brand_ids:
                st.error("No hay marcas activas disponibles para asignar a la cotización.")
                return
            if selected_brand_id is None or selected_brand_id not in brand_ids:
                selected_brand_id = brand_ids[0]
            selected_brand_id = st.selectbox(
                "Marca",
                options=brand_ids,
                index=brand_ids.index(int(selected_brand_id)),
                format_func=lambda mid: quote_brands_df.loc[quote_brands_df["id_marca"] == int(mid), "nombre"].iloc[0],
                disabled=read_only,
                label_visibility="collapsed",
                key=f"{prefix}_brand_{editor_id}",
            )
            if cotizacion_id is not None:
                st.caption(f"Serie {_quote_series_label(quote_row.get('cotizacion_serie'))}")
        else:
            st.markdown("**Marca**")
            st.write(str(quote_row.get("marca_nombre") if quote_row else project.get("marca_nombre") or "-").strip() or "-")

        st.markdown("---")
        st.markdown("**Items de la cotizacion**")
        edited_df, selected_row_ids = _render_quote_items_grid(
            current_df,
            read_only=items_read_only,
            key=f"{data_key}_editor",
        )
        st.session_state[data_key] = edited_df
        export_items_df = _drop_empty_item_rows(st.session_state[data_key]).copy()
        has_export_items = not export_items_df.empty

        if scope == "compras":
            export_col, _ = st.columns([1, 3])
            with export_col:
                st.download_button(
                    "Exportar Excel",
                    data=_items_dataframe_to_excel_bytes(export_items_df),
                    file_name=f"cotizacion_items_{editor_id}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"{prefix}_export_rows_{editor_id}",
                    disabled=not has_export_items,
                    use_container_width=True,
                )
        else:
            show_import_items = st.checkbox(
                "Importar Excel",
                value=False,
                disabled=read_only,
                key=f"{prefix}_show_import_{editor_id}",
            )
            upload_items = None
            import_token_key = f"{prefix}_import_token_{editor_id}"
            if show_import_items:
                upload_items = st.file_uploader(
                    "Importar items (CSV o XLSX)",
                    type=["csv", "xlsx"],
                    key=upload_key,
                    disabled=read_only,
                )
                if upload_items is not None and not read_only:
                    current_token = f"{getattr(upload_items, 'name', '')}:{getattr(upload_items, 'size', 0)}"
                    if st.session_state.get(import_token_key) != current_token:
                        imported_df = _read_items_from_upload(upload_items)
                        st.session_state[data_key] = pd.concat(
                            [_drop_empty_item_rows(st.session_state[data_key]), imported_df],
                            ignore_index=True,
                        )
                        st.session_state[import_token_key] = current_token
                        _clear_widget_state_prefix(f"{data_key}_editor_")
                        safe_rerun()
            else:
                st.session_state.pop(import_token_key, None)
            item_buttons = st.columns([1.2, 1, 1.5])
            with item_buttons[0]:
                if st.button(
                    "Eliminar fila",
                    key=f"{prefix}_remove_row_{editor_id}",
                    disabled=(read_only or st.session_state[data_key].empty),
                    use_container_width=True,
                ):
                    remaining_df = _drop_empty_item_rows(st.session_state[data_key]).copy().reset_index(drop=True)
                    if len(remaining_df.index) > 0:
                        remaining_df = remaining_df.iloc[:-1].reset_index(drop=True)
                    st.session_state[data_key] = remaining_df
                    _clear_widget_state_prefix(f"{data_key}_editor_")
                    safe_rerun()
            with item_buttons[1]:
                st.download_button(
                    "Exportar Excel",
                    data=_items_dataframe_to_excel_bytes(export_items_df),
                    file_name=f"cotizacion_items_{editor_id}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"{prefix}_export_rows_{editor_id}",
                    disabled=not has_export_items,
                    use_container_width=True,
                )
            with item_buttons[2]:
                st.download_button(
                    "Template Excel",
                    data=_items_dataframe_to_excel_bytes(_items_dataframe_from_records([_blank_item_row()])),
                    file_name="template_cotizacion_items.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"{prefix}_template_rows_{editor_id}",
                    use_container_width=True,
                )

        st.markdown("---")
        if cotizacion_id:
            _render_existing_comments(quote_comments_df)
            st.markdown("---")
            _render_existing_documents(quote_docs_df)
            st.markdown("---")

        new_comment = st.text_area(
            "Comentarios",
            key=f"{prefix}_comment_{editor_id}",
            disabled=read_only,
            placeholder="Agrega un comentario para compras/comercial.",
        )

        uploaded_docs = []
        if scope == "compras":
            uploaded_docs = st.file_uploader(
                "Adjuntar cotizacion",
                type=["xlsx", "xls"],
                accept_multiple_files=True,
                key=f"{prefix}_docs_{editor_id}",
                    disabled=action_locked,
            )

        vigente_choice = None
        existing_vigente_id = None
        has_existing_vigente = False
        if cotizacion_id and not quote_docs_df.empty and "id" in quote_docs_df.columns:
            for _, doc_row in quote_docs_df.iterrows():
                if bool(doc_row.get("is_vigente")):
                    existing_vigente_id = int(doc_row["id"])
                    has_existing_vigente = True
                    break

        if scope in {"commercial", "admin_comercial"} and cotizacion_id and not quote_docs_df.empty:
            vigente_options = []
            vigente_default = None
            for _, doc_row in quote_docs_df.iterrows():
                option_value = f"existing::{int(doc_row['id'])}"
                version_label = doc_row.get("version_label") or "Version"
                filename = doc_row.get("filename") or f"Documento {doc_row['id']}"
                vigente_options.append((option_value, f"{version_label}: {filename}"))
                if bool(doc_row.get("is_vigente")):
                    vigente_default = option_value
            if vigente_options:
                labels = [label for _, label in vigente_options]
                values = {label: value for value, label in vigente_options}
                default_label = labels[0]
                if vigente_default:
                    for value, label in vigente_options:
                        if value == vigente_default:
                            default_label = label
                            break
                vigente_label = st.radio(
                    "Indicar cual es la vigente",
                    options=labels,
                    index=labels.index(default_label),
                disabled=action_locked,
                    key=f"{prefix}_vigente_{editor_id}",
                )
                vigente_choice = values.get(vigente_label)
        elif scope == "compras" and uploaded_docs:
            if not has_existing_vigente:
                vigente_choice = f"new::{uploaded_docs[0].name}"
                if len(uploaded_docs) == 1:
                    st.caption("La primera cotización enviada por Compras quedará marcada como vigente por defecto.")
                else:
                    st.caption("Como aún no había una cotización vigente, el primer archivo adjunto quedará marcado como vigente por defecto.")

        selected_status = quote_row.get("cotizacion_estado") if quote_row else "Solicitado"
        if can_manage_closed_quote and cotizacion_id:
            st.markdown(f"**Estado:** {selected_status}")
            st.caption("Para volver a trabajar esta cotización, usá el botón Reabrir.")
        elif scope == "compras" and cotizacion_id:
            purchase_status_options = ["Enviado", "Cancelado / Cerrado"]
            default_purchase_status = (
                "Cancelado / Cerrado"
                if str(selected_status).strip() == "Cancelado / Cerrado"
                else "Enviado"
            )
            selected_status = st.selectbox(
                "Estado de respuesta",
                options=purchase_status_options,
                index=purchase_status_options.index(default_purchase_status),
                disabled=action_locked,
                key=f"{prefix}_estado_{editor_id}",
            )
        elif can_change_status and cotizacion_id:
            selected_status = st.selectbox(
                "Estado",
                options=["Solicitado", "Enviado", "Cancelado / Cerrado"],
                index=["Solicitado", "Enviado", "Cancelado / Cerrado"].index(selected_status)
                if selected_status in {"Solicitado", "Enviado", "Cancelado / Cerrado"}
                else 0,
                disabled=action_locked,
                key=f"{prefix}_estado_{editor_id}",
            )
        elif cotizacion_id:
            st.markdown(f"**Estado:** {selected_status}")

        can_delete = cotizacion_id is not None and scope != "compras" and (not read_only or can_manage_closed_quote)
        force_save_mode = str(selected_status or "").strip() == "Cancelado / Cerrado"
        if can_manage_closed_quote:
            primary_action_mode = "reopen"
            primary_action_label = "Reabrir"
        else:
            primary_action_mode = "request_new_version" if can_request_new_version and not force_save_mode else "save"
            primary_action_label = "Solicitar nueva version" if primary_action_mode == "request_new_version" else "Guardar"
        if can_delete:
            action_cols = st.columns([1, 1, 2])
        else:
            action_cols = st.columns([1, 2])
        with action_cols[0]:
            if st.button("Cerrar", key=f"{prefix}_close_{editor_id}", use_container_width=True):
                _clear_widget_state_prefix(f"{data_key}_editor_")
                for key in [
                    data_key,
                    f"{data_key}_editor",
                    f"{prefix}_dialog_quote_id",
                ]:
                    st.session_state.pop(key, None)
                safe_rerun()
        next_action_idx = 1
        if can_delete:
            with action_cols[next_action_idx]:
                if st.button(
                    "Eliminar",
                    key=f"{prefix}_delete_request_{editor_id}",
                    use_container_width=True,
                ):
                    st.session_state[f"{prefix}_delete_dialog_quote_id"] = int(cotizacion_id)
                    st.session_state.pop(f"{prefix}_dialog_quote_id", None)
                    st.query_params["_close_dialog"] = str(datetime.now().timestamp())
                    safe_rerun()
            next_action_idx += 1
            save_col = action_cols[next_action_idx]
        else:
            save_col = action_cols[next_action_idx]
        with save_col:
            if st.button(
                primary_action_label,
                key=f"{prefix}_{primary_action_mode}_{editor_id}",
                type="primary",
                disabled=action_locked,
                use_container_width=True,
            ):
                try:
                    items_payload = _items_payload_from_df(st.session_state[data_key])
                    if primary_action_mode == "reopen":
                        update_cotizacion(
                            cotizacion_id=cotizacion_id,
                            acting_user_id=user_id,
                            items=items_payload,
                            new_comment="",
                            documents=[],
                            selected_existing_vigente_id=existing_vigente_id,
                            new_status="Enviado",
                            scope=scope,
                            assigned_to=selected_assignee_id if scope in {"commercial", "admin_comercial"} else None,
                            marca_id=selected_brand_id if scope in {"commercial", "admin_comercial"} else None,
                        )
                        st.success("Cotizacion reabierta.")
                    elif primary_action_mode == "request_new_version":
                        docs_payload = _persist_uploaded_quote_documents(
                            cotizacion_id,
                            uploaded_docs,
                            uploaded_by=user_id,
                            vigente_choice=vigente_choice,
                        )
                        existing_vigente_id = None
                        if vigente_choice and str(vigente_choice).startswith("existing::"):
                            existing_vigente_id = int(str(vigente_choice).split("::", 1)[1])
                        update_cotizacion(
                            cotizacion_id=cotizacion_id,
                            acting_user_id=user_id,
                            items=items_payload,
                            new_comment="",
                            documents=docs_payload,
                            selected_existing_vigente_id=existing_vigente_id,
                            new_status="Solicitado",
                            scope=scope,
                            assigned_to=selected_assignee_id,
                            marca_id=selected_brand_id,
                        )
                        request_new_cotizacion_version(
                            cotizacion_id=cotizacion_id,
                            acting_user_id=user_id,
                            scope=scope,
                            request_comment=new_comment,
                            assigned_to=selected_assignee_id,
                        )
                        st.success("Nueva version solicitada a compras.")
                    elif cotizacion_id is None:
                        new_id = create_cotizacion(
                            proyecto_id=selected_project_id,
                            requested_by=user_id,
                            items=items_payload,
                            comentario_inicial=new_comment,
                            scope=scope,
                            assigned_to=selected_assignee_id,
                            marca_id=selected_brand_id,
                        )
                        if uploaded_docs:
                            docs_payload = _persist_uploaded_quote_documents(
                                new_id,
                                uploaded_docs,
                                uploaded_by=user_id,
                                vigente_choice=vigente_choice,
                            )
                            append_cotizacion_documents(new_id, docs_payload)
                        st.success("Solicitud de cotizacion enviada a compras.")
                    else:
                        docs_payload = _persist_uploaded_quote_documents(
                            cotizacion_id,
                            uploaded_docs,
                            uploaded_by=user_id,
                            vigente_choice=vigente_choice,
                        )
                        existing_vigente_id = None
                        if vigente_choice and str(vigente_choice).startswith("existing::"):
                            existing_vigente_id = int(str(vigente_choice).split("::", 1)[1])
                        update_cotizacion(
                            cotizacion_id=cotizacion_id,
                            acting_user_id=user_id,
                            items=items_payload,
                            new_comment=new_comment,
                            documents=docs_payload,
                            selected_existing_vigente_id=existing_vigente_id,
                            new_status=selected_status if can_change_status else None,
                            scope=scope,
                            assigned_to=selected_assignee_id if scope in {"commercial", "admin_comercial"} else None,
                            marca_id=selected_brand_id if scope in {"commercial", "admin_comercial"} else None,
                        )
                        st.success("Cotizacion actualizada.")
                    for key in [
                        data_key,
                        f"{data_key}_editor",
                        upload_key,
                        f"{prefix}_docs_{editor_id}",
                        f"{prefix}_comment_{editor_id}",
                        f"{prefix}_assigned_to_{editor_id}",
                        f"{prefix}_brand_{editor_id}",
                        f"{prefix}_dialog_quote_id",
                    ]:
                        st.session_state.pop(key, None)
                    _clear_widget_state_prefix(f"{data_key}_editor_")
                    safe_rerun()
                except Exception as exc:
                    st.error(str(exc))

    _dialog()


def _render_quote_delete_dialog(user_id, scope, cotizacion_id):
    prefix = _scope_prefix(scope)
    if scope == "compras":
        st.session_state.pop(f"{prefix}_delete_dialog_quote_id", None)
        return
    quote_row = get_cotizacion(cotizacion_id, user_id=user_id, scope=scope)
    if not quote_row:
        st.session_state.pop(f"{prefix}_delete_dialog_quote_id", None)
        return

    title = f"Eliminar cotizacion {int(quote_row.get('cotizacion_id') or cotizacion_id)}"

    @st.dialog(title, width="small")
    def _dialog():
        st.error("Eliminar la cotizacion es una accion irreversible. ¿Seguro desea continuar?")
        info = f"Trato {int(quote_row.get('trato_id') or quote_row.get('proyecto_id') or 0)} - {_client_display_name(quote_row)}"
        st.caption(info)

        confirm_cols = st.columns([1, 1])
        with confirm_cols[0]:
            if st.button("Eliminar", key=f"{prefix}_delete_confirm_dialog_{cotizacion_id}", type="primary", use_container_width=True):
                try:
                    delete_cotizacion(cotizacion_id, acting_user_id=user_id, scope=scope)
                    for key in [
                        f"{prefix}_delete_dialog_quote_id",
                        f"{prefix}_dialog_quote_id",
                        f"{prefix}_selected_quote_id",
                    ]:
                        st.session_state.pop(key, None)
                    st.success("Cotizacion eliminada.")
                    safe_rerun()
                except Exception as exc:
                    st.error(str(exc))
        with confirm_cols[1]:
            if st.button("Cancelar", key=f"{prefix}_delete_cancel_dialog_{cotizacion_id}", use_container_width=True):
                st.session_state.pop(f"{prefix}_delete_dialog_quote_id", None)
                safe_rerun()

    _dialog()


def render_quotes_workspace(user_id, scope="commercial", title="Cotizaciones"):
    prefix = _scope_prefix(scope)
    open_param_name = f"{prefix}_open_quote"
    pending_open_quote = st.query_params.get(open_param_name)
    if pending_open_quote:
        try:
            st.session_state[f"{prefix}_dialog_quote_id"] = int(pending_open_quote)
            st.query_params.pop(open_param_name, None)
            st.query_params.pop("qscope", None)
            safe_rerun()
        except Exception:
            pass
    st.subheader("Consulta Cotizaciones")
    df = get_cotizaciones_dataframe(user_id, scope=scope)

    create_col, _ = st.columns([0.24, 0.76])
    with create_col:
        if scope in {"commercial", "admin_comercial"}:
            assignee_users = _quote_assignee_options_df()
            if st.button(
                "➕ Solicitar Cotizacion",
                key=f"{prefix}_new_quote_btn",
                type="primary",
                use_container_width=False,
                disabled=assignee_users.empty,
            ):
                _render_quote_dialog(user_id, scope, cotizacion_id=None)
            if assignee_users.empty:
                st.caption("No hay usuarios activos de Compras o adm_comercial para recibir solicitudes.")

    if df.empty:
        df = pd.DataFrame(
            columns=[
                "cotizacion_id",
                "proyecto_id",
                "trato_id",
                "marca_nombre",
                "cliente_cuit",
                "cliente_nombre",
                "cliente_alias",
                "vendedor_nombre",
                "trato_titulo",
                "trato_descripcion",
                "tipo_venta",
                "cotizacion_estado",
                "trato_estado",
                "fecha_cierre",
                "cotizacion_created_at",
                "cotizacion_updated_at",
            ]
        )
    else:
        df = df.copy()
    df["_client_filter"] = df.apply(_client_display_name, axis=1) if not df.empty else pd.Series(dtype=str)

    unique_clients = sorted([value for value in df.get("_client_filter", pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()])
    unique_marcas = sorted([value for value in df.get("marca_nombre", pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()])
    unique_vendedores = sorted([value for value in df.get("vendedor_nombre", pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()])
    estado_options = sorted([value for value in df.get("cotizacion_estado", pd.Series(dtype=str)).dropna().unique().tolist() if str(value).strip()])

    sort_options = (
        ["Más recientes", "Ascendente", "Descendente"]
        if scope == "compras"
        else ["Más recientes", "Fecha Cierre (Asc)", "Fecha Cierre (Desc)"]
    )

    if scope == "compras":
        filter_cols = st.columns([1.1, 1.8, 1.8, 1.8, 1.9, 1.8, 1.6, 1.2])
        fcol_id, fcol_cliente, fcol_marca, fcol_vendedor, fcol_nombre, fcol_estado, fcol_orden, fcol_fecha = filter_cols
    else:
        filter_cols = st.columns([1.2, 2, 2, 2, 2, 1.7, 1.3])
        fcol_id, fcol_cliente, fcol_marca, fcol_nombre, fcol_estado, fcol_orden, fcol_fecha = filter_cols
        fcol_vendedor = None

    with fcol_id:
        filtro_id_raw = st.text_input("ID de trato", value="", key=f"{prefix}_filter_id_text")
        filtro_id = None
        try:
            filtro_id_str = str(filtro_id_raw or "").strip()
            if filtro_id_str:
                filtro_id = int(filtro_id_str)
        except Exception:
            filtro_id = None
    with fcol_cliente:
        sel_cliente = st.selectbox("Cliente", options=["Todos"] + unique_clients, key=f"{prefix}_filter_cliente")
        filtro_cliente = sel_cliente if sel_cliente != "Todos" else ""
    with fcol_marca:
        sel_marca = st.selectbox("Marca", options=["Todas"] + unique_marcas, key=f"{prefix}_filter_marca")
        filtro_marca = sel_marca if sel_marca != "Todas" else ""
    filtro_vendedor = ""
    if fcol_vendedor is not None:
        with fcol_vendedor:
            sel_vendedor = st.selectbox("Vendedor", options=["Todos"] + unique_vendedores, key=f"{prefix}_filter_vendedor")
            filtro_vendedor = sel_vendedor if sel_vendedor != "Todos" else ""
    with fcol_nombre:
        filtro_nombre = st.text_input("Nombre del proyecto", value="", key=f"{prefix}_filter_nombre")
    with fcol_estado:
        filtro_estados = st.multiselect("Estado", options=estado_options, key=f"{prefix}_filter_estado_multi")
    with fcol_orden:
        ordenar_por = st.selectbox(
            "Ordenar por",
            sort_options,
            key=f"{prefix}_sort_option",
        )
    with fcol_fecha:
        st.markdown("<div style='height: 22px;'></div>", unsafe_allow_html=True)
        use_date_filter = st.toggle("Filtrar por fecha", value=False, key=f"{prefix}_filter_date_enabled")

    filtro_fecha_desde = None
    filtro_fecha_hasta = None
    if use_date_filter:
        dcol1, dcol2 = st.columns([1, 1])
        with dcol1:
            filtro_fecha_desde = st.date_input(
                "Desde",
                value=pd.Timestamp.now().replace(day=1).date(),
                key=f"{prefix}_filter_date_from",
            )
        with dcol2:
            filtro_fecha_hasta = st.date_input(
                "Hasta",
                value=pd.Timestamp.now().date(),
                key=f"{prefix}_filter_date_to",
            )

    filtered_df = df.copy()
    if filtro_id is not None:
        trato_series = filtered_df.get("trato_id").fillna(filtered_df.get("proyecto_id"))
        try:
            filtered_df = filtered_df[trato_series.astype("Int64") == int(filtro_id)]
        except Exception:
            filtered_df = filtered_df[trato_series.astype(str) == str(filtro_id)]
    if filtro_cliente:
        filtered_df = filtered_df[filtered_df.get("_client_filter", pd.Series(dtype=str)).fillna("") == filtro_cliente]
    if filtro_marca:
        filtered_df = filtered_df[filtered_df.get("marca_nombre", pd.Series(dtype=str)).fillna("") == filtro_marca]
    if filtro_vendedor:
        filtered_df = filtered_df[filtered_df.get("vendedor_nombre", pd.Series(dtype=str)).fillna("") == filtro_vendedor]
    if filtro_nombre:
        titulo_series = filtered_df.get("trato_titulo", pd.Series(dtype=str)).fillna("")
        descripcion_series = filtered_df.get("trato_descripcion", pd.Series(dtype=str)).fillna("")
        filtered_df = filtered_df[
            titulo_series.str.contains(filtro_nombre, case=False, na=False)
            | descripcion_series.str.contains(filtro_nombre, case=False, na=False)
        ]
    if filtro_estados:
        filtered_df = filtered_df[filtered_df.get("cotizacion_estado", pd.Series(dtype=str)).fillna("").isin(filtro_estados)]
    if use_date_filter and filtro_fecha_desde is not None and filtro_fecha_hasta is not None:
        fecha_desde = pd.Timestamp(min(filtro_fecha_desde, filtro_fecha_hasta))
        fecha_hasta = pd.Timestamp(max(filtro_fecha_desde, filtro_fecha_hasta)) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        fecha_actualizacion = pd.to_datetime(filtered_df.get("cotizacion_updated_at"), errors="coerce")
        fecha_creacion = pd.to_datetime(filtered_df.get("cotizacion_created_at"), errors="coerce")
        fecha_referencia = fecha_actualizacion.fillna(fecha_creacion)
        filtered_df = filtered_df[fecha_referencia.between(fecha_desde, fecha_hasta, inclusive="both")]

    if ordenar_por == "Más recientes":
        sort_created = pd.to_datetime(filtered_df.get("cotizacion_created_at"), errors="coerce")
        sort_updated = pd.to_datetime(filtered_df.get("cotizacion_updated_at"), errors="coerce").fillna(sort_created)
        filtered_df = (
            filtered_df.assign(_sort_updated=sort_updated)
            .sort_values(["_sort_updated", "cotizacion_id"], ascending=[False, False], na_position="last")
            .drop(columns=["_sort_updated"], errors="ignore")
        )
    else:
        if scope == "compras":
            fecha_orden = pd.to_datetime(filtered_df.get("cotizacion_created_at"), errors="coerce")
            ascending_order = ordenar_por == "Ascendente"
        else:
            fecha_orden = pd.to_datetime(filtered_df.get("fecha_cierre"), errors="coerce")
            ascending_order = ordenar_por == "Fecha Cierre (Asc)"
        sorted_indices = fecha_orden.sort_values(ascending=ascending_order, na_position="last").index
        filtered_df = filtered_df.loc[sorted_indices]

    export_df = _build_quote_display_dataframe(filtered_df) if not filtered_df.empty else _empty_quote_display_dataframe()
    export_df = export_df.drop(columns=["Acciones"], errors="ignore")
    export_col, _ = st.columns([0.2, 0.8])
    with export_col:
        _render_filter_button_spacer()
        st.download_button(
            "Exportar todo",
            data=_dataframe_to_excel_bytes(export_df, sheet_name="Cotizaciones"),
            file_name=f"{title.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{prefix}_export_quotes_excel",
            use_container_width=True,
            disabled=export_df.empty,
        )

    if filtered_df.empty:
        if df.empty:
            st.info("No hay cotizaciones registradas.")
        else:
            st.info("No hay cotizaciones que coincidan con los filtros.")
        return

    page_key = f"{prefix}_quotes_page"
    page_size_key = f"{prefix}_quotes_page_size"
    page_size_options = [5, 10, 15, 20, 30, 50]

    if page_size_key not in st.session_state:
        st.session_state[page_size_key] = 10
    if st.session_state.get(page_size_key) not in page_size_options:
        st.session_state[page_size_key] = 10

    def on_page_size_change():
        st.session_state[page_key] = 1

    page_size = int(st.session_state.get(page_size_key, 10) or 10)
    total_items = len(filtered_df)
    page = int(st.session_state.get(page_key, 1) or 1)
    total_pages = max((total_items + page_size - 1) // page_size, 1)

    if page > total_pages:
        page = total_pages
    if page < 1:
        page = 1
    st.session_state[page_key] = page

    start = (page - 1) * page_size
    end = start + page_size
    df_page = filtered_df.iloc[start:end]
    count_text = f"Mostrando elementos {start + 1}-{min(end, total_items)} de {total_items}"

    for _, row in df_page.iterrows():
        cotizacion_id = int(row.get("cotizacion_id") or 0)
        comments_df = get_cotizacion_comments_df(cotizacion_id)
        docs_df = get_cotizacion_documents_df(cotizacion_id)
        _render_quote_summary_card(
            row,
            row.to_dict(),
            comments_df,
            docs_df,
            open_param_name=open_param_name,
            scope=scope,
        )

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

    col_ps, col_text, col_spacer, col_prev, col_sep, col_next = st.columns([0.6, 3.4, 2.6, 1, 0.5, 1])
    with col_ps:
        st.selectbox(
            "filas / pagina",
            options=page_size_options,
            key=page_size_key,
            label_visibility="collapsed",
            on_change=on_page_size_change,
        )
    with col_text:
        st.markdown(
            f"<div style='display:flex; align-items:center; height:100%; color:#888; margin-top:6px;'>{count_text}</div>",
            unsafe_allow_html=True,
        )
    with col_prev:
        if st.button(
            "Anterior",
            disabled=(page <= 1),
            key=f"{prefix}_prev_page",
            use_container_width=True,
        ):
            st.session_state[page_key] = page - 1
            safe_rerun()
    with col_next:
        if st.button(
            "Siguiente",
            disabled=(page >= total_pages),
            key=f"{prefix}_next_page",
            use_container_width=True,
        ):
            st.session_state[page_key] = page + 1
            safe_rerun()

    delete_dialog_quote_id = st.session_state.get(f"{prefix}_delete_dialog_quote_id")
    if delete_dialog_quote_id:
        _render_quote_delete_dialog(user_id, scope, cotizacion_id=int(delete_dialog_quote_id))
        return

    dialog_quote_id = st.session_state.get(f"{prefix}_dialog_quote_id")
    if dialog_quote_id:
        _render_quote_dialog(user_id, scope, cotizacion_id=int(dialog_quote_id))
