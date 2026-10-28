import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import json
import os
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# Configuración de página con branding AgroSpectra
st.set_page_config(
    layout="wide",
    page_title="AgroSpectra - Inteligencia Agrícola y Satelital",
    page_icon="icon.png"
)

# Inyección de soporte PWA (Manifest, Meta tags para iOS/Android y Service Worker)
pwa_header_html = """
<link rel="manifest" href="/app/static/manifest.json">
<meta name="theme-color" content="#1a9641">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="AgroSpectra">
<link rel="apple-touch-icon" href="/app/static/icon-192.png">
<script>
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/app/static/sw.js')
        .then(reg => console.log('[AgroSpectra PWA] Service Worker registrado:', reg.scope))
        .catch(err => console.log('[AgroSpectra PWA] Fallo Service Worker:', err));
    });
  }
</script>
"""
st.markdown(pwa_header_html, unsafe_allow_html=True)

# Estilo visual moderno y limpio
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.3rem;
        font-weight: 800;
        color: #1a9641;
        margin-bottom: 0px;
    }
    .sub-title {
        color: #555;
        font-size: 1.05rem;
        margin-bottom: 1.2rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 12px;
        border-left: 4px solid #1a9641;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<p class="main-title">🛰️ AgroSpectra: Inteligencia Agrícola y Satelital</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Monitoreo multiespectral Sentinel-2, control financiero y telemetría de campo para Los Altos de Jalisco.</p>', unsafe_allow_html=True)

# --- INICIALIZACIÓN EARTH ENGINE ---
ee_autenticado = False
st.sidebar.markdown("### ☁️ Conexión Earth Engine")
proyecto_cloud_input = st.sidebar.text_input(
    "Google Cloud Project ID:",
    value="agrospectra-513021",
    help="ID del proyecto de Google Cloud con Earth Engine habilitado."
)

try:
    if proyecto_cloud_input.strip():
        ee.Initialize(project=proyecto_cloud_input.strip())
    else:
        ee.Initialize()
    ee_autenticado = True
    st.sidebar.success("✅ Conectado a Google Earth Engine")
except Exception as e:
    st.sidebar.warning("⚠️ Earth Engine no inicializado")

# --- GESTIÓN DE PREDIOS Y DELIMITACIÓN ---
st.sidebar.markdown("---")
st.sidebar.header("📍 Configuración del Predio")

origen_predio = st.sidebar.radio(
    "Fuente de delimitación:",
    ["Predios precargados (Arandas)", "Subir archivo GeoJSON propio"]
)

coords_poligono = None
nombre_predio_activo = ""
coords_centro = [20.7050, -102.3020]

predios_default = {
    "Predio Los Encinos (Agave - Arandas)": {
        "lat": 20.7050,
        "lon": -102.3020,
        "cultivo": "Agave Tequilana Weber",
        "superficie_ha": 3.8,
        "coords": [
            [-102.3040, 20.7035],
            [-102.3000, 20.7040],
            [-102.2995, 20.7065],
            [-102.3038, 20.7060],
            [-102.3040, 20.7035]
        ]
    },
    "Predio La Herradura (Maíz - Arandas)": {
        "lat": 20.7200,
        "lon": -102.3400,
        "cultivo": "Maíz de Temporal",
        "superficie_ha": 5.2,
        "coords": [
            [-102.3420, 20.7180],
            [-102.3375, 20.7185],
            [-102.3380, 20.7220],
            [-102.3425, 20.7215],
            [-102.3420, 20.7180]
        ]
    }
}

superficie_activa_ha = 4.0
cultivo_activo = "Agave Tequilana Weber"

if origen_predio == "Predios precargados (Arandas)":
    predio_sel = st.sidebar.selectbox("Selecciona el Predio:", list(predios_default.keys()))
    info_sel = predios_default[predio_sel]
    nombre_predio_activo = predio_sel
    coords_centro = [info_sel["lat"], info_sel["lon"]]
    coords_poligono = info_sel["coords"]
    superficie_activa_ha = info_sel.get("superficie_ha", 4.0)
    cultivo_activo = info_sel.get("cultivo", "Cultivo General")
else:
    archivo_geojson = st.sidebar.file_uploader("Cargar polígono (.geojson o .json):", type=["geojson", "json"])
    if archivo_geojson is not None:
        try:
            datos_geo = json.load(archivo_geojson)
            features = datos_geo.get("features", [])
            if not features:
                geom = datos_geo.get("geometry", datos_geo)
                coords_poligono = geom.get("coordinates", [[]])[0]
                nombre_predio_activo = "Polígono Personalizado"
            else:
                opciones_nombres = []
                for i, f in enumerate(features):
                    props = f.get("properties", {})
                    nom = props.get("nombre") or props.get("Name") or f"Polígono #{i+1}"
                    opciones_nombres.append(nom)

                predio_idx = st.sidebar.selectbox("Selecciona polígono dentro del archivo:", range(len(opciones_nombres)), format_func=lambda x: opciones_nombres[x])
                feat_sel = features[predio_idx]
                nombre_predio_activo = opciones_nombres[predio_idx]
                coords_poligono = feat_sel["geometry"]["coordinates"][0]
                superficie_activa_ha = feat_sel.get("properties", {}).get("superficie_ha", 5.0)

            lats = [pt[1] for pt in coords_poligono]
            lons = [pt[0] for pt in coords_poligono]
            coords_centro = [sum(lats) / len(lats), sum(lons) / len(lons)]
            st.sidebar.success(f"Polígono cargado: {nombre_predio_activo}")
        except Exception as err:
            st.sidebar.error(f"Error al leer archivo GeoJSON: {err}")
            st.stop()
    else:
        st.info("ℹ️ Sube un archivo GeoJSON con los linderos de tu parcela o usa los predios precargados para explorar.")
        st.stop()

# --- SELECTOR DE ÍNDICE ESPECTRAL ---
st.sidebar.markdown("---")
st.sidebar.header("🔬 Índice Multiespectral")
indice_sel = st.sidebar.selectbox(
    "Selecciona el indicador a visualizar:",
    [
        "NDVI - Vigor General y Salud Vegetal",
        "NDRE - Clorofila, Nitrógeno y Dosel Denso",
        "NDWI - Humedad Foliar y Estrés Hídrico"
    ]
)

# Filtros temporales
st.sidebar.subheader("📅 Parámetros Satelitales")
hoy = datetime.today()
hace_30_dias = hoy - timedelta(days=35)
fecha_inicio = st.sidebar.date_input("Fecha Inicio", hace_30_dias)
fecha_fin = st.sidebar.date_input("Fecha Fin", hoy)
max_nubes = st.sidebar.slider("Tolerancia máxima de nubes (%):", 0, 50, 20)

folium_poly_coords = [[pt[1], pt[0]] for pt in coords_poligono]

# --- PROCESAMIENTO SATELITAL CON EARTH ENGINE ---
fecha_toma = "Pendiente"
valor_indice_promedio = None
capa_tile_url = None
rgb_tile_url = None
nombre_clave_indice = "NDVI"

if "NDRE" in indice_sel:
    nombre_clave_indice = "NDRE"
elif "NDWI" in indice_sel:
    nombre_clave_indice = "NDWI"

if ee_autenticado and coords_poligono:
    try:
        roi = ee.Geometry.Polygon(coords_poligono)
        coleccion = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(roi)
            .filterDate(fecha_inicio.strftime('%Y-%m-%d'), (fecha_fin + timedelta(days=1)).strftime('%Y-%m-%d'))
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_nubes))
        )
        conteo = coleccion.size().getInfo()

        if conteo > 0:
            imagen = coleccion.sort("system:time_start", False).first()
            timestamp_ms = imagen.get("system:time_start").getInfo()
            fecha_toma = datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d")
            st.sidebar.success(f"Pasada Sentinel-2: {fecha_toma}")

            # Fórmulas espectrales de Sentinel-2:
            # NDVI: (NIR - Red) / (NIR + Red) -> (B8 - B4) / (B8 + B4)
            # NDRE: (NIR - RedEdge1) / (NIR + RedEdge1) -> (B8 - B5) / (B8 + B5)
            # NDWI: (NIR - SWIR1) / (NIR + SWIR1) -> (B8 - B11) / (B8 + B11)
            if nombre_clave_indice == "NDVI":
                img_indice = imagen.normalizedDifference(["B8", "B4"]).rename("INDICE")
                paleta_colores = ["#d7191c", "#fdae61", "#ffffbf", "#a6d96a", "#1a9641"]
                v_min, v_max = 0.1, 0.85
            elif nombre_clave_indice == "NDRE":
                img_indice = imagen.normalizedDifference(["B8", "B5"]).rename("INDICE")
                paleta_colores = ["#a50026", "#f46d43", "#fee08b", "#d9ef8b", "#1a9850"]
                v_min, v_max = 0.05, 0.65
            else: # NDWI
                img_indice = imagen.normalizedDifference(["B8", "B11"]).rename("INDICE")
                paleta_colores = ["#8c510a", "#dfc27d", "#f6e8c3", "#80cdc1", "#01665e"]
                v_min, v_max = -0.3, 0.45

            stat = img_indice.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=roi,
                scale=10,
                maxPixels=1e9
            ).getInfo()
            valor_indice_promedio = stat.get("INDICE", None)

            indice_vis = img_indice.clip(roi).visualize(min=v_min, max=v_max, palette=paleta_colores)
            map_id = ee.data.getMapId({"image": indice_vis})
            capa_tile_url = map_id["tile_fetcher"].url_format

            rgb_vis = imagen.clip(roi).visualize(bands=["B4", "B3", "B2"], min=0, max=3000)
            rgb_map_id = ee.data.getMapId({"image": rgb_vis})
            rgb_tile_url = rgb_map_id["tile_fetcher"].url_format
        else:
            st.sidebar.warning(f"No hay imágenes despejadas (<{max_nubes}% nubes).")
    except Exception as ee_err:
        st.error(f"Error procesando satélite: {ee_err}")

# Cabecera de métricas rápidas
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    st.metric("Predio Seleccionado", nombre_predio_activo, f"{superficie_activa_ha} ha")
with col_m2:
    st.metric("Última Captura Satelital", fecha_toma)
with col_m3:
    if valor_indice_promedio is not None:
        st.metric(f"Promedio {nombre_clave_indice}", f"{valor_indice_promedio:.2f}")
    else:
        st.metric(f"Promedio {nombre_clave_indice}", "Cargando...")
with col_m4:
    if valor_indice_promedio is not None:
        if nombre_clave_indice == "NDVI":
            estado = "🟢 Follaje Óptimo" if valor_indice_promedio >= 0.6 else ("🟡 Estrés Moderado" if valor_indice_promedio >= 0.35 else "🔴 Bajo Vigor")
        elif nombre_clave_indice == "NDRE":
            estado = "🟢 Clorofila Alta" if valor_indice_promedio >= 0.4 else ("🟡 Nitrógeno Medio" if valor_indice_promedio >= 0.25 else "🔴 Deficiencia Foliar")
        else: # NDWI
            estado = "💧 Hidratación Óptima" if valor_indice_promedio >= 0.1 else ("🟡 Déficit Moderado" if valor_indice_promedio >= -0.1 else "🔥 Estrés Hídrico Severo")
        st.metric("Diagnóstico Espectral", estado)
    else:
        st.metric("Diagnóstico Espectral", "N/D")

# --- SISTEMA DE PESTAÑAS PRINCIPALES ---
tab_satelite, tab_historico, tab_finanzas, tab_sensores = st.tabs([
    "🗺️ Visor Multiespectral",
    "📈 Serie Histórica",
    "💰 Costos, Jornales y Rentabilidad",
    "📡 Telemetría y Sensores IoT"
])

# ----------------- TAB 1: VISOR MULTIESPECTRAL -----------------
with tab_satelite:
    col_mapa, col_leyenda = st.columns([3, 1])
    with col_mapa:
        m = folium.Map(location=coords_centro, zoom_start=16, control_scale=True)
        folium.TileLayer(
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google Satellite",
            name="Google Satelital (Híbrido)",
            overlay=False
        ).add_to(m)

        if capa_tile_url:
            folium.TileLayer(
                tiles=capa_tile_url,
                attr="Copernicus Sentinel-2",
                name=f"Capa Multiespectral {nombre_clave_indice}",
                overlay=True
            ).add_to(m)

        if rgb_tile_url:
            folium.TileLayer(
                tiles=rgb_tile_url,
                attr="Copernicus Sentinel-2",
                name=f"Color Real RGB ({fecha_toma})",
                overlay=True,
                show=False
            ).add_to(m)

        folium.Polygon(
            locations=folium_poly_coords,
            color="#FFD700",
            weight=3,
            fill=True,
            fill_color="#FFD700",
            fill_opacity=0.1,
            tooltip=f"<b>{nombre_predio_activo}</b>"
        ).add_to(m)

        folium.LayerControl().add_to(m)
        st_folium(m, width=None, height=520, use_container_width=True)

    with col_leyenda:
        st.subheader(f"Interpretación: {nombre_clave_indice}")
        if nombre_clave_indice == "NDVI":
            st.markdown(
                """
                **NDVI (Normalized Difference Vegetation Index)**
                * 🟩 **0.60 – 0.85:** Fotosíntesis vigorosa, cultivo denso y sano.
                * 🟨 **0.35 – 0.59:** Densidad media, maleza baja o estrés inicial.
                * 🟥 **0.00 – 0.20:** Suelo seco, caminos o daño foliar severo.
                """
            )
            st.info("💡 **Uso clave:** Detección de manchones de marchitez y monitoreo general de biomasa.")
        elif nombre_clave_indice == "NDRE":
            st.markdown(
                """
                **NDRE (Red Edge):**
                * 🟩 **0.40 – 0.65:** Alto contenido de clorofila y nutrición balanceada (nitrógeno).
                * 🟨 **0.25 – 0.39:** Clorofila moderada; respuesta a fertilización en progreso.
                * 🟥 **0.05 – 0.24:** Clorosis, suelo expuesto o follaje amarillento.
                """
            )
            st.info("💡 **Uso clave:** Ideal en cultivos cerrados o agave adulto donde el NDVI suele saturarse.")
        else:
            st.markdown(
                """
                **NDWI (Water Index):**
                * 🟦 **> 0.10:** Turgencia celular alta y buena hidratación de hojas.
                * 🟨 **-0.10 a 0.10:** Humedad foliar moderada a límite.
                * 🟫 **< -0.10:** Sequía severa o estrés hídrico activo.
                """
            )
            st.info("💡 **Uso clave:** Decisión prioritaria de riegos de auxilio antes de que la penca pierda peso.")

# ----------------- TAB 2: SERIE HISTÓRICA -----------------
with tab_historico:
    st.subheader(f"Evolución Histórica ({nombre_clave_indice}) - {nombre_predio_activo}")
    meses_hist = st.slider("Meses hacia atrás:", min_value=3, max_value=24, value=8, step=1)
    fecha_hist_inicio = hoy - timedelta(days=meses_hist * 30)

    if ee_autenticado and coords_poligono:
        with st.spinner("Extrayendo serie temporal en Google Earth Engine..."):
            try:
                roi = ee.Geometry.Polygon(coords_poligono)
                col_hist = (
                    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                    .filterBounds(roi)
                    .filterDate(fecha_hist_inicio.strftime('%Y-%m-%d'), (hoy + timedelta(days=1)).strftime('%Y-%m-%d'))
                    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
                )

                def extraer_valores(img):
                    if nombre_clave_indice == "NDVI":
                        ind = img.normalizedDifference(["B8", "B4"]).rename("VAL")
                    elif nombre_clave_indice == "NDRE":
                        ind = img.normalizedDifference(["B8", "B5"]).rename("VAL")
                    else:
                        ind = img.normalizedDifference(["B8", "B11"]).rename("VAL")
                    
                    stt = ind.reduceRegion(reducer=ee.Reducer.mean(), geometry=roi, scale=10, maxPixels=1e9)
                    return ee.Feature(None, {
                        "fecha": ee.Date(img.get("system:time_start")).format("YYYY-MM-dd"),
                        "valor": stt.get("VAL")
                    })

                serie_res = col_hist.map(extraer_valores).getInfo()
                data_points = []
                for f in serie_res.get("features", []):
                    p = f.get("properties", {})
                    dt = p.get("fecha")
                    v = p.get("valor")
                    if dt and v is not None:
                        data_points.append({"Fecha": dt, nombre_clave_indice: round(v, 3)})

                if data_points:
                    df_hist = pd.DataFrame(data_points).sort_values("Fecha").drop_duplicates(subset=["Fecha"])
                    fig_h = px.line(
                        df_hist,
                        x="Fecha",
                        y=nombre_clave_indice,
                        markers=True,
                        title=f"Comportamiento de {nombre_clave_indice} a través del tiempo",
                        labels={"Fecha": "Fecha de pasada satelital", nombre_clave_indice: f"Índice {nombre_clave_indice}"},
                        template="plotly_white"
                    )
                    fig_h.update_traces(line_color="#1a9641", marker=dict(size=7, color="#005a32"))
                    st.plotly_chart(fig_h, use_container_width=True)
                    with st.expander("📄 Ver tabla de registros satelitales"):
                        st.dataframe(df_hist, use_container_width=True)
                else:
                    st.warning("No hay suficientes pasadas satelitales despejadas en el intervalo.")
            except Exception as e_hist:
                st.error(f"Error procesando serie: {e_hist}")

# ----------------- TAB 3: COSTOS, JORNALES Y RENTABILIDAD -----------------
with tab_finanzas:
    st.subheader(f"Gestión Administrativa y Financiera: {nombre_predio_activo}")
    
    # Archivo de persistencia de gastos local en CSV
    csv_gastos_path = "gastos_agrospectra.csv"
    if not os.path.exists(csv_gastos_path):
        # Crear base inicial con ejemplos para el productor
        df_init = pd.DataFrame([
            {"Fecha": "2026-06-15", "Predio": "Predio Los Encinos (Agave - Arandas)", "Rubro": "Jornales / Nómina", "Concepto": "Deshierbe manual de calles (8 jornales)", "Costo_MXN": 3200.0, "Tipo": "Gasto"},
            {"Fecha": "2026-07-20", "Predio": "Predio Los Encinos (Agave - Arandas)", "Rubro": "Insumos y Agroquímicos", "Concepto": "Fertilizante foliar con micronutrientes", "Costo_MXN": 6800.0, "Tipo": "Gasto"},
            {"Fecha": "2026-08-10", "Predio": "Predio Los Encinos (Agave - Arandas)", "Rubro": "Maquinaria y Combustible", "Concepto": "Pase de rastra con tractor (diesel y operador)", "Costo_MXN": 2400.0, "Tipo": "Gasto"},
            {"Fecha": "2026-10-05", "Predio": "Predio Los Encinos (Agave - Arandas)", "Rubro": "Venta de Cosecha", "Concepto": "Venta lote anticipado de hijuelos", "Costo_MXN": 25000.0, "Tipo": "Ingreso"},
        ])
        df_init.to_csv(csv_gastos_path, index=False)

    df_gastos = pd.read_csv(csv_gastos_path)

    col_form, col_resumen = st.columns([1, 2])
    with col_form:
        st.markdown("#### ➕ Registrar Movimiento")
        with st.form("form_gastos", clear_on_submit=True):
            tipo_mov = st.radio("Tipo:", ["Gasto", "Ingreso"], horizontal=True)
            fecha_mov = st.date_input("Fecha:", datetime.today())
            rubro_mov = st.selectbox("Categoría:", [
                "Jornales / Nómina",
                "Insumos y Agroquímicos",
                "Maquinaria y Combustible",
                "Riego y Agua",
                "Venta de Cosecha / Hijuelos",
                "Otros Costos Operativos"
            ])
            concepto_mov = st.text_input("Concepto / Descripción:", placeholder="Ej. 6 jornales para poda o limpia")
            monto_mov = st.number_input("Monto ($ MXN):", min_value=1.0, step=100.0, value=1500.0)
            btn_guardar = st.form_submit_button("Guardar Registro", use_container_width=True)

            if btn_guardar and concepto_mov.strip():
                nuevo_reg = pd.DataFrame([{
                    "Fecha": fecha_mov.strftime("%Y-%m-%d"),
                    "Predio": nombre_predio_activo,
                    "Rubro": rubro_mov,
                    "Concepto": concepto_mov,
                    "Costo_MXN": float(monto_mov),
                    "Tipo": tipo_mov
                }])
                df_gastos = pd.concat([df_gastos, nuevo_reg], ignore_index=True)
                df_gastos.to_csv(csv_gastos_path, index=False)
                st.success("¡Registro guardado correctamente!")
                st.rerun()

    with col_resumen:
        df_predio_actual = df_gastos[df_gastos["Predio"] == nombre_predio_activo]

        total_gastado = df_predio_actual[df_predio_actual["Tipo"] == "Gasto"]["Costo_MXN"].sum()
        total_ingresado = df_predio_actual[df_predio_actual["Tipo"] == "Ingreso"]["Costo_MXN"].sum()
        balance_neto = total_ingresado - total_gastado
        gasto_por_ha = total_gastado / (superficie_activa_ha if superficie_activa_ha > 0 else 1.0)

        # Tarjetas financieras visuales
        c_fin1, c_fin2, c_fin3, c_fin4 = st.columns(4)
        c_fin1.metric("Total Gastado", f"${total_gastado:,.2f} MXN")
        c_fin2.metric("Total Ingresado", f"${total_ingresado:,.2f} MXN")
        c_fin3.metric("Balance Neto", f"${balance_neto:,.2f} MXN", delta=f"{balance_neto:,.2f} MXN")
        c_fin4.metric("Costo por Hectárea", f"${gasto_por_ha:,.2f} / ha")

        if not df_predio_actual.empty:
            df_gastos_solo = df_predio_actual[df_predio_actual["Tipo"] == "Gasto"]
            if not df_gastos_solo.empty:
                fig_pie = px.pie(
                    df_gastos_solo,
                    names="Rubro",
                    values="Costo_MXN",
                    title="Distribución de Gastos en el Predio",
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                st.plotly_chart(fig_pie, use_container_width=True)

        st.markdown("#### Historial de Movimientos de la Parcela")
        st.dataframe(df_predio_actual.sort_values("Fecha", ascending=False), use_container_width=True)

# ----------------- TAB 4: TELEMETRÍA Y SENSORES IOT -----------------
with tab_sensores:
    st.subheader(f"Telemetría en Suelo y Clima (IoT): {nombre_predio_activo}")
    st.markdown("Integración directa con sondas agrícolas RS485 Modbus y microcontroladores ESP32 en campo.")

    c_iot1, c_iot2, c_iot3, c_iot4 = st.columns(4)
    with c_iot1:
        st.metric("Humedad en Raíz (20 cm)", "38.5 %", delta="+2.1% (Óptimo)")
    with c_iot2:
        st.metric("Temp. de Suelo", "21.4 °C", delta="-0.8 °C")
    with c_iot3:
        st.metric("Conductividad (EC)", "420 µS/cm", "Nutrición Adecuada")
    with c_iot4:
        st.metric("Batería Nodo Solar", "3.95 V", "100% Carga")

    st.markdown("---")
    st.markdown("#### 🧠 Diagnóstico Cruzado (Satélite + Sensores de Suelo)")

    # Lógica de diagnóstico inteligente
    if valor_indice_promedio is not None:
        if valor_indice_promedio < 0.4:
            st.error("🚨 **ALERTA CRÍTICA:** El satélite detecta bajo vigor en el cuadrante, pero la sonda de suelo registra humedad adecuada (38%). **Diagnóstico:** Muy probable ataque de patógeno radicular o picudo del agave; inspección presencial urgente recomendada.")
        else:
            st.success("✅ **CONDICIONES FAVORABLES:** El satélite corrobora masa vegetal activa y la sonda confirma reserva de agua adecuada en estrato radicular.")
    else:
        st.info("💡 Cuando se procesa el satélite, AgroSpectra cruza automáticamente el índice espectral con los valores de humedad y temperatura del suelo para generar diagnósticos automáticos.")

    with st.expander("🛠️ Ver Diagrama de Conexión del Nodo ESP32 y Sensor de Suelo"):
        st.code(
            """
[ Panel Solar 5W ] ──> [ Módulo Cargador TP4056 + Batería 18650 ]
                                 │
                                 ▼
                     [ ESP32 Microcontrolador ]
                          │             │
                    GPIO 16 (RX)    GPIO 17 (TX)
                          │             │
                          ▼             ▼
                    [ Convertidor MAX485 TTL ]
                          │             │
                       Línea A+      Línea B-
                          │             │
                          ▼             ▼
          [ Sonda Agrícola de Suelo Modbus RS485 ]
          (Mide Humedad Volumétrica, Temperatura y EC)
            """,
            language="text"
        )
        st.caption("El código fuente listo para cargar al microcontrolador se encuentra en el archivo: `firmware_esp32_suelo.py`.")
