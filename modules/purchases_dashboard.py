import os
from datetime import datetime

import pandas as pd
import streamlit as st

from .quotes_ui import render_quotes_workspace
from .quotes_data import (
    get_daily_toast_alert_keys_shown,
    get_quote_alerts_summary,
    mark_daily_toast_alerts_shown,
)
from .database import (
    get_all_proyectos,
    get_clientes_dataframe,
    get_proyecto,
    get_proyecto_documentos,
)
from .utils import safe_rerun


def _estado_to_class(value):
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    legacy = {
        "activo": "prospecto",
        "pendiente": "presupuestado",
        "finalizado": "ganado",
        "cerrado": "perdido",
    }
    mapping = {
        "prospecto": "prospecto",
        "presupuestado": "presupuestado",
        "negociacion": "negociacion",
        "negociación": "negociacion",
        "objecion": "objecion",
        "objeción": "objecion",
        "ganado": "ganado",
        "perdido": "perdido",
        "abierto": "abierto",
        "en progreso": "en progreso",
    }
    return mapping.get(raw, legacy.get(raw, raw))


def _estado_display(value):
    mapping = {
        "prospecto": "Prospecto",
        "presupuestado": "Presupuestado",
        "negociacion": "Negociacion",
        "objecion": "Objecion",
        "ganado": "Ganado",
        "perdido": "Perdido",
        "abierto": "Abierto",
        "en progreso": "En Progreso",
    }
    normalized = _estado_to_class(value)
    return mapping.get(normalized, str(value or "").strip() or "-")


def _clean_cuit(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _format_date(value):
    try:
        dt = pd.to_datetime(value, errors="coerce")
        if pd.isna(dt):
            return "-"
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return "-"


def _build_cotizaciones_dataframe():
    proyectos_df = get_all_proyectos()
    if proyectos_df.empty:
        return proyectos_df

    proyectos_df = proyectos_df.copy()

    clientes_df = get_clientes_dataframe()
    if not clientes_df.empty and "id_cliente" in clientes_df.columns:
        clientes_merge = clientes_df[["id_cliente", "cuit"]].copy()
        clientes_merge = clientes_merge.rename(columns={"id_cliente": "cliente_id", "cuit": "cliente_cuit"})
        proyectos_df = proyectos_df.merge(clientes_merge, on="cliente_id", how="left")
    else:
        proyectos_df["cliente_cuit"] = ""

    proyectos_df["razon_social"] = (
        proyectos_df.get("cliente_nombre", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    )
    empty_reason = proyectos_df["razon_social"] == ""
    proyectos_df.loc[empty_reason, "razon_social"] = (
        proyectos_df.loc[empty_reason, "marca_nombre"].fillna("").astype(str).str.strip()
    )
    proyectos_df.loc[proyectos_df["razon_social"] == "", "razon_social"] = "Sin razon social"

    proyectos_df["vendedor"] = (
        proyectos_df.get("usuario_nombre", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    )
    proyectos_df.loc[proyectos_df["vendedor"] == "", "vendedor"] = "Sin asignar"

    proyectos_df["descripcion_cotizacion"] = (
        proyectos_df.get("titulo", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    )
    empty_desc = proyectos_df["descripcion_cotizacion"] == ""
    proyectos_df.loc[empty_desc, "descripcion_cotizacion"] = (
        proyectos_df.loc[empty_desc, "descripcion"].fillna("").astype(str).str.strip()
    )
    proyectos_df.loc[proyectos_df["descripcion_cotizacion"] == "", "descripcion_cotizacion"] = "-"

    proyectos_df["estado_display"] = proyectos_df.get("estado", pd.Series(dtype=str)).apply(_estado_display)
    proyectos_df["estado_sort"] = proyectos_df.get("estado", pd.Series(dtype=str)).apply(_estado_to_class)
    proyectos_df["cliente_cuit"] = proyectos_df.get("cliente_cuit", pd.Series(dtype=str)).fillna("").astype(str)
    proyectos_df["cliente_cuit_clean"] = proyectos_df["cliente_cuit"].apply(_clean_cuit)

    if "id" in proyectos_df.columns:
        proyectos_df = proyectos_df.sort_values("id", ascending=False)

    return proyectos_df


def _apply_filters(df):
    filtered_df = df.copy()

    filtro_id = str(st.session_state.get("compras_filter_id", "") or "").strip()
    filtro_cuit = _clean_cuit(st.session_state.get("compras_filter_cuit", ""))
    filtro_razon = str(st.session_state.get("compras_filter_razon", "") or "").strip().lower()
    filtro_estado = st.session_state.get("compras_filter_estado", "Todos")

    if filtro_id:
        try:
            filtered_df = filtered_df[filtered_df["id"].astype("Int64") == int(filtro_id)]
        except Exception:
            filtered_df = filtered_df.iloc[0:0]

    if filtro_cuit:
        filtered_df = filtered_df[
            filtered_df.get("cliente_cuit_clean", pd.Series(dtype=str)).fillna("").str.contains(filtro_cuit, na=False)
        ]

    if filtro_razon:
        filtered_df = filtered_df[
            filtered_df.get("razon_social", pd.Series(dtype=str))
            .fillna("")
            .str.lower()
            .str.contains(filtro_razon, na=False)
        ]

    if filtro_estado and filtro_estado != "Todos":
        filtered_df = filtered_df[
            filtered_df.get("estado_display", pd.Series(dtype=str)).fillna("") == filtro_estado
        ]

    return filtered_df


def _clear_filters():
    st.session_state["compras_filter_id"] = ""
    st.session_state["compras_filter_cuit"] = ""
    st.session_state["compras_filter_razon"] = ""
    st.session_state["compras_filter_estado"] = "Todos"
    safe_rerun()


def _render_documents(project_id):
    docs_df = get_proyecto_documentos(project_id)
    if docs_df.empty:
        st.caption("No hay documentos adjuntos para esta cotizacion.")
        return

    st.markdown("#### Documentos")
    for _, doc in docs_df.iterrows():
        file_path = str(doc.get("file_path") or "")
        file_name = str(doc.get("filename") or "archivo")
        uploaded_at = _format_date(doc.get("uploaded_at"))
        cols = st.columns([3, 1])
        with cols[0]:
            st.write(f"{file_name} - {uploaded_at}")
        with cols[1]:
            if file_path and os.path.exists(file_path):
                with open(file_path, "rb") as file_obj:
                    st.download_button(
                        "Descargar",
                        data=file_obj.read(),
                        file_name=file_name,
                        key=f"compras_doc_{project_id}_{doc.get('id')}",
                        use_container_width=True,
                    )
            else:
                st.caption("No disponible")


def _render_detail(selected_row):
    project_id = int(selected_row["id"])
    project_data = get_proyecto(project_id)
    if not project_data:
        st.error("No se pudo cargar la cotizacion seleccionada.")
        return

    st.markdown("---")
    st.subheader(f"Cotizacion {project_id}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Razon social", selected_row.get("razon_social") or "-")
        st.caption(f"CUIT: {selected_row.get('cliente_cuit') or '-'}")
    with col2:
        st.metric("Vendedor", selected_row.get("vendedor") or "-")
        st.caption(f"Estado: {selected_row.get('estado_display') or '-'}")
    with col3:
        moneda = str(project_data.get("moneda") or "ARS")
        valor = project_data.get("valor")
        if valor is None or str(valor) == "":
            valor_display = f"{moneda} -"
        else:
            try:
                valor_display = f"{moneda} {float(valor):,.0f}".replace(",", ".")
            except Exception:
                valor_display = f"{moneda} {valor}"
        st.metric("Importe", valor_display)
        st.caption(f"Cierre estimado: {_format_date(project_data.get('fecha_cierre'))}")

    detail_cols = st.columns(2)
    with detail_cols[0]:
        st.markdown("**Descripcion**")
        st.write(selected_row.get("descripcion_cotizacion") or "-")
        st.markdown("**Tipo de venta**")
        st.write(project_data.get("tipo_venta") or "-")
    with detail_cols[1]:
        st.markdown("**Detalle interno**")
        st.write(project_data.get("descripcion") or "-")
        st.markdown("**Contacto**")
        contact_name = " ".join(
            [
                str(project_data.get("contacto_nombre") or "").strip(),
                str(project_data.get("contacto_apellido") or "").strip(),
            ]
        ).strip()
        st.write(contact_name or "-")

    _render_documents(project_id)


def render_purchases_dashboard(user_id, nombre_completo_usuario, show_toasts=True):
    quote_alerts = get_quote_alerts_summary(user_id, scope="compras")
    pending_quote_requests = int(quote_alerts.get("pending_purchase_requests_count", 0) or 0)
    has_quote_alerts = pending_quote_requests > 0

    if show_toasts and pending_quote_requests > 0:
        shown_daily_toasts = get_daily_toast_alert_keys_shown(user_id, ["compras_pending_quotes"])
        if "compras_pending_quotes" not in shown_daily_toasts:
            st.toast(f"🟨 Tienes {pending_quote_requests} solicitudes de cotización pendientes.", icon="📄")
            mark_daily_toast_alerts_shown(user_id, ["compras_pending_quotes"])

    col_head, col_icon = st.columns([0.92, 0.08])
    with col_head:
        st.header("Panel de Compras")
    with col_icon:
        st.write("")
        try:
            wrapper_class = "has-alerts" if has_quote_alerts else "no-alerts"
            st.markdown(f"<div class='notif-trigger {wrapper_class}'>", unsafe_allow_html=True)
            icon_str = "🔔" if has_quote_alerts else "🔕"
            with st.popover(icon_str, use_container_width=True):
                st.markdown("### Notificaciones")
                if not has_quote_alerts:
                    st.info("No hay alertas pendientes.")
                else:
                    label = f"🟨 Cotizaciones: {pending_quote_requests} pendientes"
                    if st.button(label, key="compras_btn_notif_quotes", use_container_width=True):
                        st.session_state["cotizaciones_compras_filter_estado_multi"] = ["Solicitado"]
                        safe_rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        except AttributeError:
            if st.button("🔔"):
                st.info(f"Notificaciones: {pending_quote_requests} cotizaciones pendientes")

    st.caption(f"Gestion de cotizaciones recibidas. Usuario: {nombre_completo_usuario}")
    render_quotes_workspace(user_id, scope="compras", title="cotizaciones_compras")
