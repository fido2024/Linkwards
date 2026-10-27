"""Interfaz Streamlit del prototipo Linkwards."""
import streamlit as st

from src.interfaz import (
    candidatos_para_tabla,
    cargar_metricas,
    formatear_fecha_captura,
    recuperar,
)


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

with st.form("recuperacion_form"):
    url_entrada = st.text_input(
        "URL antigua",
        placeholder="https://sitio-antiguo.example/articulo",
        help="Puedes incluir el esquema http:// o https://; si lo omites se usará HTTPS.",
    )
    iniciar = st.form_submit_button("Recuperar URL", type="primary")

if iniciar:
    with st.spinner("Consultando metadatos y preparando candidatos…"):
        st.session_state["linkwards_resultado"] = recuperar(url_entrada)

resultado = st.session_state.get("linkwards_resultado")
if resultado:
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
        st.caption("Ordenados de mayor a menor puntuación heurística.")
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
            'proximidad. Es un indicador heurístico de similitud, no una probabilidad '
            'estadística de que el candidato sea la URL correcta.</p>',
            unsafe_allow_html=True,
        )

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

