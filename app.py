import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
import json
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# Configuración de página
st.set_page_config(
    layout="wide",
    page_title="AgroSpectra - Monitoreo Satelital de Salud Vegetal",
    page_icon="icon.png"
)

st.title("🛰️ AgroSpectra: Monitoreo Satelital de Salud Vegetal (NDVI)")
st.markdown("Plataforma sistemática y de bajo costo con imágenes multiespectrales de **Sentinel-2** para cultivos en Arandas y Los Altos de Jalisco.")

# --- INICIALIZACIÓN EARTH ENGINE ---
ee_autenticado = False

# Campo opcional en la barra lateral para el ID del Cloud Project de Google Earth Engine
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
    err_str = str(e)
    if "no project found" in err_str.lower() or "project=" in err_str.lower():
        st.sidebar.warning("⚠️ Ingresa tu Project ID arriba.")
        st.warning("ℹ️ **Earth Engine requiere asociar un Google Cloud Project ID.**")
        st.markdown(
            """
            En las versiones recientes de Earth Engine, cada usuario tiene un ID de proyecto de Google Cloud (gratuito).
            - Puedes verlo o crearlo en: [Google Earth Engine Code Editor](https://code.earthengine.google.com/) (aparece arriba a la derecha) o en [Google Cloud Console](https://console.cloud.google.com/).
            - Cópialo y pégalo en la barra lateral izquierda en el campo **'Google Cloud Project ID'**.
            """
        )
    else:
        st.sidebar.warning("⚠️ Earth Engine sin inicializar.")

# --- BARRA LATERAL: SELECCIÓN DE PREDIO Y ORIGEN DE DATOS ---
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
        "coords": [
            [-102.3420, 20.7180],
            [-102.3375, 20.7185],
            [-102.3380, 20.7220],
            [-102.3425, 20.7215],
            [-102.3420, 20.7180]
        ]
    }
}

if origen_predio == "Predios precargados (Arandas)":
    predio_sel = st.sidebar.selectbox("Selecciona el Predio:", list(predios_default.keys()))
    info_sel = predios_default[predio_sel]
    nombre_predio_activo = predio_sel
    coords_centro = [info_sel["lat"], info_sel["lon"]]
    coords_poligono = info_sel["coords"]
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

            # Calcular centro aproximado
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

# --- FILTROS TEMPORALES Y DE CALIDAD ---
st.sidebar.subheader("📅 Parámetros Satelitales")
hoy = datetime.today()
hace_30_dias = hoy - timedelta(days=35)

fecha_inicio = st.sidebar.date_input("Fecha Inicio", hace_30_dias)
fecha_fin = st.sidebar.date_input("Fecha Fin", hoy)
max_nubes = st.sidebar.slider("Tolerancia máxima de nubes (%):", 0, 50, 20)

# Invertir coordenadas [lon, lat] -> [lat, lon] para Folium
folium_poly_coords = [[pt[1], pt[0]] for pt in coords_poligono]

# Procesamiento Satelital si Earth Engine está activo
fecha_toma = "Pendiente de autenticación"
ndvi_promedio = None
ndvi_tile_url = None
rgb_tile_url = None

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
            st.sidebar.success(f"Pasada satelital: {fecha_toma}")

            # Cálculo de NDVI
            ndvi = imagen.normalizedDifference(["B8", "B4"]).rename("NDVI")

            # Estadísticas NDVI
            stat_ndvi = ndvi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=roi,
                scale=10,
                maxPixels=1e9
            ).getInfo()
            ndvi_promedio = stat_ndvi.get("NDVI", None)

            # Capas visuales (WMS Tiles)
            paleta_ndvi = ["#d7191c", "#fdae61", "#ffffbf", "#a6d96a", "#1a9641"]
            ndvi_vis = ndvi.clip(roi).visualize(min=0.1, max=0.85, palette=paleta_ndvi)
            ndvi_map_id = ee.data.getMapId({"image": ndvi_vis})
            ndvi_tile_url = ndvi_map_id["tile_fetcher"].url_format

            rgb_vis = imagen.clip(roi).visualize(bands=["B4", "B3", "B2"], min=0, max=3000)
            rgb_map_id = ee.data.getMapId({"image": rgb_vis})
            rgb_tile_url = rgb_map_id["tile_fetcher"].url_format
        else:
            st.sidebar.warning(f"No hay pasadas con <{max_nubes}% nubes en este rango.")
    except Exception as ee_err:
        st.error(f"Error procesando datos en Earth Engine: {ee_err}")

# Cabecera de estadísticas rápidas
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    st.metric("Predio Activo", nombre_predio_activo)
with col_m2:
    st.metric("Última Captura Satelital", fecha_toma)
with col_m3:
    if ndvi_promedio is not None:
        st.metric("NDVI Promedio Actual", f"{ndvi_promedio:.2f}")
    else:
        st.metric("NDVI Promedio Actual", "N/D (Autenticar)")
with col_m4:
    if ndvi_promedio is not None:
        if ndvi_promedio >= 0.6:
            st.success("🟢 Vigor Óptimo")
        elif ndvi_promedio >= 0.35:
            st.warning("🟡 Estrés Moderado")
        else:
            st.error("🔴 Follaje Escaso / Daño")
    else:
        st.info("Sin lectura de vigor")

# --- VISTA EN PESTAÑAS: MAPA INTERACTIVO Y SERIE TEMPORAL HISTÓRICA ---
tab_mapa, tab_historico = st.tabs(["🗺️ Semáforo Satelital (NDVI)", "📈 Evolución Histórica del Cultivo"])

with tab_mapa:
    col_map, col_info = st.columns([3, 1])

    with col_map:
        # Folium nativo ultra-estable
        m = folium.Map(location=coords_centro, zoom_start=16, control_scale=True)

        # Capa Satelital de Google de alta resolución
        folium.TileLayer(
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google Satellite",
            name="Google Satelital (Híbrido)",
            overlay=False,
            control=True
        ).add_to(m)

        # Capa NDVI si está disponible
        if ndvi_tile_url:
            folium.TileLayer(
                tiles=ndvi_tile_url,
                attr="Copernicus Sentinel-2 / Google Earth Engine",
                name="Semáforo NDVI (Salud del Cultivo)",
                overlay=True,
                control=True
            ).add_to(m)

        # Capa Color Real RGB si está disponible
        if rgb_tile_url:
            folium.TileLayer(
                tiles=rgb_tile_url,
                attr="Copernicus Sentinel-2",
                name=f"Sentinel-2 Color Real ({fecha_toma})",
                overlay=True,
                show=False,
                control=True
            ).add_to(m)

        # Polígono de linderos
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

    with col_info:
        st.subheader("Semáforo NDVI")
        st.markdown(
            """
            * 🟩 **0.60 – 0.85:** Fotosíntesis vigorosa, cultivo óptimo y denso.
            * 🟨 **0.35 – 0.59:** Estrés hídrico inicial, menor densidad o maleza baja.
            * 🟧 **0.20 – 0.34:** Planta estresada, suelo expuesto o daño radicular.
            * 🟥 **0.00 – 0.19:** Suelo seco, caminos, maleza seca o follaje muerto.
            """
        )
        st.info("💡 **Alerta en Agave:** Caídas bruscas en manchones específicos dentro de la parcela indican posible afectación por picudo (*Scyphophorus acupunctatus*) o pudrición/marchitez antes de que sea evidente a simple vista.")

with tab_historico:
    st.subheader(f"Evolución Histórica de NDVI: {nombre_predio_activo}")
    st.markdown("Analiza la tendencia de vigor a lo largo de las pasadas satelitales para evaluar respuesta a fertilizaciones, riegos o afectación por sequía.")

    meses_hist = st.slider("Meses hacia atrás a evaluar:", min_value=3, max_value=24, value=6, step=1)
    fecha_hist_inicio = hoy - timedelta(days=meses_hist * 30)

    if ee_autenticado and coords_poligono:
        with st.spinner("Procesando serie histórica en Google Earth Engine..."):
            try:
                roi = ee.Geometry.Polygon(coords_poligono)
                coleccion_hist = (
                    ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                    .filterBounds(roi)
                    .filterDate(fecha_hist_inicio.strftime('%Y-%m-%d'), (hoy + timedelta(days=1)).strftime('%Y-%m-%d'))
                    .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
                )

                def extraer_ndvi(img):
                    ndvi_img = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
                    stats = ndvi_img.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=roi,
                        scale=10,
                        maxPixels=1e9
                    )
                    return ee.Feature(None, {
                        "fecha": ee.Date(img.get("system:time_start")).format("YYYY-MM-dd"),
                        "ndvi": stats.get("NDVI")
                    })

                serie = coleccion_hist.map(extraer_ndvi).getInfo()
                registros = []
                for feat in serie.get("features", []):
                    prop = feat.get("properties", {})
                    f = prop.get("fecha")
                    val = prop.get("ndvi")
                    if f and val is not None:
                        registros.append({"Fecha": f, "NDVI": round(val, 3)})

                if registros:
                    df_serie = pd.DataFrame(registros).sort_values(by="Fecha").drop_duplicates(subset=["Fecha"])

                    fig = px.line(
                        df_serie,
                        x="Fecha",
                        y="NDVI",
                        markers=True,
                        title=f"Curva de Vigor Vegetativo (NDVI) - Últimos {meses_hist} meses",
                        labels={"NDVI": "Índice de Vigor (NDVI)", "Fecha": "Fecha de Toma Satelital"},
                        template="plotly_white"
                    )

                    fig.add_hrect(y0=0.6, y1=1.0, line_width=0, fillcolor="green", opacity=0.08, annotation_text="Vigor Óptimo", annotation_position="top left")
                    fig.add_hrect(y0=0.35, y1=0.6, line_width=0, fillcolor="yellow", opacity=0.08, annotation_text="Estrés Moderado", annotation_position="top left")
                    fig.add_hrect(y0=0.0, y1=0.35, line_width=0, fillcolor="red", opacity=0.08, annotation_text="Riesgo / Suelo desnudo", annotation_position="top left")
                    fig.update_yaxes(range=[0, 1])

                    st.plotly_chart(fig, use_container_width=True)

                    with st.expander("📊 Ver tabla detallada de lecturas satelitales"):
                        st.dataframe(df_serie, use_container_width=True)
                else:
                    st.warning("No se encontraron suficientes pasadas satelitales despejadas en el periodo histórico seleccionado.")
            except Exception as err_hist:
                st.error(f"Error al generar serie temporal: {err_hist}")
    else:
        st.info("ℹ️ Para ver la evolución temporal del predio se requiere autenticar Google Earth Engine.")
