"""Interfaz Streamlit del prototipo Linkwards."""
import csv

import streamlit as st
from src.datos import dominio, leer_enlaces

from src.interfaz import (
    candidatos_para_tabla,
    cargar_metricas,
    formatear_fecha_captura,
    recuperar,
)

VARIANTE_PUNTUACION = "levenshtein"


st.set_page_config(page_title="Linkwards", page_icon="↗", layout="wide")

st.markdown(
    """
    <style>
      .block-container {max-width: 1120px; padding-top: 2.2rem; padding-bottom: 3rem;}
      .lw-subtitle {color: #cbd5e1; font-size: 1.08rem; margin-top: -0.65rem;}
      .lw-note {color: #cbd5e1; font-size: .9rem;}
      div[data-testid="stMetric"] {background: #222831; border: 1px solid #39424e;
        color: #f1f5f9; padding: 1rem; border-radius: .65rem;}
      div[data-testid="stMetricLabel"] {color: #d5dce5 !important;}
      div[data-testid="stMetricValue"] {color: #f8fafc !important;}
      div[data-testid="stMetricDelta"] {color: #cbd5e1 !important;}
      .st-key-eval-top1-heuristico-favorable [data-testid="stMetricValue"],
      .st-key-eval-top5-heuristico-favorable [data-testid="stMetricValue"] {color: #4ade80 !important;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Linkwards")
st.markdown(
    '<p class="lw-subtitle">Recuperación de enlaces web antiguos mediante '
    'metadatos históricos y búsqueda de candidatos.</p>',
    unsafe_allow_html=True,
)
st.divider()

def mostrar_resultado(resultado, url_entrada):
    estado = resultado["estado"]
    detalle = resultado.get("detalle", "")
    if estado == "completado":
        st.success(detalle)
    elif estado == "sin_captura":
        st.warning(detalle)
    elif estado == "sin_candidatos":
        st.info(detalle)
    elif estado == "url_invalida":
        st.error(detalle)
    elif estado == "falta_configuracion_tavily":
        st.warning(detalle)
    else:
        st.error(detalle)

    meta = resultado.get("metadatos")
    if meta:
        st.subheader("Metadatos históricos")
        fecha = formatear_fecha_captura(meta.get("fecha_copia"))
        fecha_raw = meta.get("fecha_copia", "")
        url_archivada = (
            f"https://web.archive.org/web/{fecha_raw}/{meta.get('url', url_entrada)}"
            if fecha_raw else ""
        )
        col_titulo, col_fecha = st.columns([3, 1])
        with col_titulo:
            st.markdown(f"**Título**  \n{meta.get('titulo') or 'No disponible'}")
        with col_fecha:
            st.markdown(f"**Fecha de captura**  \n{fecha}")
        if url_archivada:
            st.markdown(f"**Captura archivada:** [{url_archivada}]({url_archivada})")
        st.markdown("**Texto histórico relevante**")
        st.write(meta.get("texto") or "No se extrajo texto relevante.")

    items = resultado.get("candidatos", [])
    if items:
        st.subheader("Candidatos recuperados")
        variante = resultado.get("variante", VARIANTE_PUNTUACION)
        st.caption(f"Ordenados de mayor a menor puntuación heurística · variante {variante}.")
        st.dataframe(
            candidatos_para_tabla(items),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Puntuación heurística": st.column_config.NumberColumn(format="%.2f / 100"),
                "URL": st.column_config.LinkColumn(display_text="Abrir URL"),
            },
        )
        st.markdown(
            '<p class="lw-note">La puntuación combina señales de dominio, título y '
            'proximidad mediante la variante Levenshtein seleccionada. Es un indicador '
            'heurístico de similitud, no una probabilidad estadística de éxito.</p>',
            unsafe_allow_html=True,
        )


st.subheader("Conjunto experimental de enlaces")
st.caption(
    "Estos registros pertenecen al preexperimento académico y se cargan desde "
    "datos/enlaces.csv. La interfaz permite probarlos, pero no modificar ese archivo."
)

try:
    enlaces_experimentales = leer_enlaces()
except (OSError, UnicodeError, csv.Error, ValueError) as error:
    enlaces_experimentales = None
    st.error(f"No se pudo leer el conjunto experimental de datos/enlaces.csv: {error}")

if enlaces_experimentales is not None:
    if not enlaces_experimentales:
        st.info("El CSV experimental no contiene registros utilizables.")
    else:
        filas_tabla = []
        for fila in enlaces_experimentales:
            url_vieja = str(fila.get("url_vieja", "")).strip()
            try:
                dominio_origen = dominio(url_vieja) if url_vieja else ""
            except (AttributeError, ValueError):
                dominio_origen = ""
            filas_tabla.append({
                "ID": fila.get("id", ""),
                "URL antigua": url_vieja,
                "Dominio de origen": dominio_origen,
                "Destino esperado": fila.get("url_nueva_correcta", ""),
                "Tipo de cambio": fila.get("tipo_cambio", ""),
            })

        st.dataframe(filas_tabla, hide_index=True, use_container_width=True)
        indices = list(range(len(enlaces_experimentales)))
        indice_seleccionado = st.selectbox(
            "Selecciona un enlace del preexperimento",
            options=indices,
            format_func=lambda indice: (
                f"ID {enlaces_experimentales[indice].get('id', indice + 1)} · "
                f"{enlaces_experimentales[indice].get('url_vieja', '')}"
            ),
            key="enlace_experimental_seleccionado",
        )
        enlace_seleccionado = enlaces_experimentales[indice_seleccionado]
        url_seleccionada = str(enlace_seleccionado.get("url_vieja", "")).strip()
        st.markdown(f"**URL antigua seleccionada:** `{url_seleccionada}`")

        with st.form("recuperacion_experimental_form"):
            probar = st.form_submit_button(
                "Probar recuperación con Levenshtein", type="primary"
            )
        if probar:
            with st.spinner("Consultando metadatos y preparando candidatos…"):
                st.session_state["linkwards_resultado_experimental"] = recuperar(
                    url_seleccionada,
                    variante=VARIANTE_PUNTUACION,
                    url_metadatos=url_seleccionada,
                )
            st.session_state["linkwards_resultado_experimental_id"] = str(
                enlace_seleccionado.get("id", indice_seleccionado)
            )

        resultado_experimental = st.session_state.get("linkwards_resultado_experimental")
        id_resultado = st.session_state.get("linkwards_resultado_experimental_id")
        id_seleccionado = str(enlace_seleccionado.get("id", indice_seleccionado))
        if resultado_experimental and id_resultado == id_seleccionado:
            mostrar_resultado(resultado_experimental, url_seleccionada)

with st.expander("Probar otra URL con Levenshtein"):
    with st.form("recuperacion_manual_form"):
        url_manual = st.text_input(
            "URL antigua",
            placeholder="https://sitio-antiguo.example/articulo",
            help="Puedes incluir http:// o https://; si lo omites se usará HTTPS.",
        )
        iniciar_manual = st.form_submit_button("Recuperar URL")
    if iniciar_manual:
        with st.spinner("Consultando metadatos y preparando candidatos…"):
            st.session_state["linkwards_resultado_manual"] = recuperar(
                url_manual, variante=VARIANTE_PUNTUACION
            )
    resultado_manual = st.session_state.get("linkwards_resultado_manual")
    if resultado_manual:
        mostrar_resultado(resultado_manual, url_manual)

st.divider()
st.subheader("Evaluación experimental")
evaluacion = cargar_metricas()
if not evaluacion:
    st.info("Aún no hay un archivo de evaluación disponible en resultados/evaluacion_candidatos.json.")
else:
    resumen = evaluacion.get("resumen", {})
    st.caption(
        f"Métricas cargadas del archivo existente · generado: "
        f"{evaluacion.get('generado_utc', 'fecha no registrada')} · "
        f"registros evaluables: {resumen.get('registros_evaluables_con_respuesta', 0)}"
    )
    metricas = [
        ("top1-buscador", "Top-1 buscador", resumen.get("top1_busqueda", {}), None),
        ("top1-heuristico", "Top-1 heurístico", resumen.get("top1_heuristico", {}), resumen.get("top1_busqueda", {})),
        ("top5-buscador", "Top-5 buscador", resumen.get("top5_busqueda", {}), None),
        ("top5-heuristico", "Top-5 heurístico", resumen.get("top5_heuristico", {}), resumen.get("top5_busqueda", {})),
        ("cobertura", "Cobertura", resumen.get("cobertura", {}), None),
    ]
    columnas = st.columns(len(metricas))
    for columna, (clave_metric, nombre, valor, linea_base) in zip(columnas, metricas):
        aciertos = valor.get("aciertos", 0)
        denominador = valor.get("denominador", 0)
        tasa = valor.get("tasa")
        porcentaje = "sin datos" if tasa is None else f"{tasa * 100:.1f}%"
        tasa_base = linea_base.get("tasa") if linea_base else None
        favorable = tasa is not None and tasa_base is not None and tasa > tasa_base
        clave = "eval-" + clave_metric
        if favorable:
            clave += "-favorable"
        with columna.container(key=clave):
            st.metric(nombre, porcentaje, f"{aciertos}/{denominador} casos", delta_color="off")
    st.caption(
        f"URL correcta ausente de candidatos: "
        f"{resumen.get('registros_correcta_ausente_de_candidatos', 0)} · "
        f"presente pero no Top-1 del buscador: "
        f"{resumen.get('registros_correcta_presente_pero_no_top1_busqueda', 0)} · "
        f"errores: {resumen.get('registros_con_error', 0)}"
    )
    st.caption("Fuente: resultados/evaluacion_candidatos.json. La interfaz solo presenta sus métricas; no las recalcula.")

