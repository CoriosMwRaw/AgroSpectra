# AgroSpectra: Sistema de Monitoreo Satelital y Gestión Agrícola de Bajo Costo

Proyecto diseñado para productores de la región de Arandas y Los Altos de Jalisco (enfocado en Agave Tequilana Weber y Maíz). Combina monitoreo satelital multiespectral gratuito (Sentinel-2) con una gestión administrativa ágil y económica.

---

## 🛰️ 1. Módulo de Monitoreo Satelital (Streamlit + Earth Engine)

### Requisitos previos
1. **Python 3.9 - 3.11** instalado.
2. Una cuenta activa en [Google Earth Engine](https://earthengine.google.com/) (gratuita para fines no comerciales y de evaluación).

### Instalación y Configuración
En tu terminal:
```bash
# 1. Instalar librerías
pip install -r requirements.txt

# 2. Autenticar Earth Engine (solo se hace una vez)
earthengine authenticate
```

### Ejecución de la aplicación
```bash
streamlit run app.py
```
Abre automáticamente en tu navegador: `http://localhost:8501`.

---

## 📱 2. Módulo de Gestión Administrativa (No-Code / Low-Code)

Para complementar el análisis satelital con el control operativo en campo sin costos de desarrollo a medida:

| Módulo | Función | Herramienta Sugerida |
|---|---|---|
| **Predios** | Filtro base por rancho/parcela | Glide / AppSheet con Google Sheets |
| **Calendario de Labores** | Asignación de jornales, fechas y estado (siembra, fertilización, deshierbe) | Vista de calendario en AppSheet |
| **Control de Gastos** | Botón "Registrar Gasto" (Fecha, Concepto, Monto, Predio) y balance automático | Google Forms / AppSheet conectada a Sheets |
| **Comercialización** | Histórico de precios, compradores y estado de contratos | Tablas y tarjetas visuales de resumen |
