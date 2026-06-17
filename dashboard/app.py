
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.engine import URL


# =============================================================================
# Configuración general
# =============================================================================

st.set_page_config(
    page_title="ATUS 2024 — Siniestralidad vial",
    page_icon="🚗",
    layout="wide",
)

st.title("🚗 Siniestralidad vial en México")
st.markdown(
    """
    Análisis de siniestros viales basados en el estudio ATUS 2024 del INEGI.
    """
)


# =============================================================================
# Parámetros fijos de conexión
# =============================================================================

HOST = "aurora-mod4.cluster-cjbcsxubmizx.us-east-1.rds.amazonaws.com"
DATABASE = "northwind"
USER = "postgres"
PORT = 5432


# =============================================================================
# Conexión a PostgreSQL / Aurora
# =============================================================================

@st.cache_resource
def get_engine(password: str):
    """Crea una conexión a PostgreSQL/Aurora usando SQLAlchemy."""
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=USER,
        password=password,
        host=HOST,
        port=PORT,
        database=DATABASE,
    )
    return create_engine(url)


with st.sidebar:
    st.header("🔌 Conexión")
    password = st.text_input("Contraseña", type="password")

if not password:
    st.info("Ingresa la contraseña en la barra lateral para cargar el dashboard.")
    st.stop()

try:
    engine = get_engine(password=password)
except Exception as exc:
    st.error(f"No se pudo crear la conexión: {exc}")
    st.stop()


# =============================================================================
# Funciones auxiliares
# =============================================================================

def format_int(value):
    """Formatea enteros con separador de miles."""
    if pd.isna(value):
        return "0"
    return f"{int(value):,}"


# =============================================================================
# KPIs
# =============================================================================

@st.cache_data(ttl=600)
def load_kpis(_engine):
    query = """
    SELECT
        COUNT(*) AS registros_fact,
        SUM(num_accidentes) AS total_accidentes,
        SUM(total_muertos) AS total_muertos,
        SUM(total_heridos) AS total_heridos,
        ROUND(
            SUM(total_muertos)::NUMERIC / NULLIF(SUM(num_accidentes), 0),
            4
        ) AS muertos_por_accidente,
        ROUND(
            SUM(total_heridos)::NUMERIC / NULLIF(SUM(num_accidentes), 0),
            4
        ) AS heridos_por_accidente
    FROM atus_dwh.fact_accidentes;
    """
    return pd.read_sql(query, _engine)


# =============================================================================
# Query 1 — Ranking de entidades
# =============================================================================

@st.cache_data(ttl=600)
def q1_ranking_entidades(_engine):
    query = """
    WITH accidentes_entidad AS (
        SELECT
            du.entidad,
            SUM(fa.num_accidentes) AS total_accidentes,
            SUM(fa.total_muertos) AS total_muertos,
            SUM(fa.total_heridos) AS total_heridos
        FROM atus_dwh.fact_accidentes fa
        JOIN atus_dwh.dim_ubicacion du
            ON fa.ubicacion_key = du.ubicacion_key
        GROUP BY du.entidad
    )
    SELECT
        RANK() OVER (ORDER BY total_accidentes DESC) AS ranking,
        entidad,
        total_accidentes,
        total_muertos,
        total_heridos,
        ROUND(total_muertos::NUMERIC / NULLIF(total_accidentes, 0), 4) AS muertos_por_accidente,
        ROUND(total_heridos::NUMERIC / NULLIF(total_accidentes, 0), 4) AS heridos_por_accidente
    FROM accidentes_entidad
    ORDER BY ranking
    LIMIT 10;
    """
    return pd.read_sql(query, _engine)


# =============================================================================
# Query 2 — Tendencia mensual
# =============================================================================

@st.cache_data(ttl=600)
def q2_tendencia_mensual(_engine):
    query = """
    WITH accidentes_mes AS (
        SELECT
            df.mes_numero,
            df.mes_nombre,
            SUM(fa.num_accidentes) AS total_accidentes,
            SUM(fa.total_muertos) AS total_muertos,
            SUM(fa.total_heridos) AS total_heridos
        FROM atus_dwh.fact_accidentes fa
        JOIN atus_dwh.dim_fecha df
            ON fa.date_key = df.date_key
        GROUP BY df.mes_numero, df.mes_nombre
    )
    SELECT
        mes_numero,
        mes_nombre,
        total_accidentes,
        total_muertos,
        total_heridos,
        LAG(total_accidentes) OVER (ORDER BY mes_numero) AS accidentes_mes_anterior,
        total_accidentes
            - LAG(total_accidentes) OVER (ORDER BY mes_numero) AS variacion_accidentes,
        ROUND(
            100.0 * (
                total_accidentes
                - LAG(total_accidentes) OVER (ORDER BY mes_numero)
            ) / NULLIF(LAG(total_accidentes) OVER (ORDER BY mes_numero), 0),
            2
        ) AS variacion_porcentual_accidentes
    FROM accidentes_mes
    ORDER BY mes_numero;
    """
    return pd.read_sql(query, _engine)


# =============================================================================
# Query 3 — Promedio móvil semanal
# =============================================================================

@st.cache_data(ttl=600)
def q3_promedio_movil(_engine):
    query = """
    WITH accidentes_dia AS (
        SELECT
            df.full_date,
            SUM(fa.num_accidentes) AS total_accidentes
        FROM atus_dwh.fact_accidentes fa
        JOIN atus_dwh.dim_fecha df
            ON fa.date_key = df.date_key
        GROUP BY df.full_date
    )
    SELECT
        full_date,
        total_accidentes,
        ROUND(
            AVG(total_accidentes) OVER (
                ORDER BY full_date
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ),
            2
        ) AS promedio_movil_7_dias
    FROM accidentes_dia
    ORDER BY full_date;
    """
    return pd.read_sql(query, _engine)


# =============================================================================
# Query 4 — Día de semana × banda horaria
# =============================================================================

@st.cache_data(ttl=600)
def q4_dia_banda(_engine):
    query = """
    SELECT
        df.dia_semana_numero,
        df.dia_semana_nombre,
        dt.banda_horaria,
        SUM(fa.num_accidentes) AS total_accidentes,
        SUM(fa.total_muertos) AS total_muertos,
        SUM(fa.total_heridos) AS total_heridos
    FROM atus_dwh.fact_accidentes fa
    JOIN atus_dwh.dim_fecha df
        ON fa.date_key = df.date_key
    JOIN atus_dwh.dim_tiempo dt
        ON fa.time_key = dt.time_key
    GROUP BY
        df.dia_semana_numero,
        df.dia_semana_nombre,
        dt.banda_horaria
    ORDER BY
        df.dia_semana_numero,
        CASE dt.banda_horaria
            WHEN 'Madrugada' THEN 1
            WHEN 'Mañana' THEN 2
            WHEN 'Tarde' THEN 3
            WHEN 'Noche' THEN 4
            ELSE 5
        END;
    """
    return pd.read_sql(query, _engine)


# =============================================================================
# Query 5 — Top municipios por entidad
# =============================================================================

@st.cache_data(ttl=600)
def q5_top_municipios(_engine):
    query = """
    WITH accidentes_municipio AS (
        SELECT
            du.entidad,
            du.municipio,
            SUM(fa.num_accidentes) AS total_accidentes,
            SUM(fa.total_muertos) AS total_muertos,
            SUM(fa.total_heridos) AS total_heridos
        FROM atus_dwh.fact_accidentes fa
        JOIN atus_dwh.dim_ubicacion du
            ON fa.ubicacion_key = du.ubicacion_key
        GROUP BY du.entidad, du.municipio
    ),
    ranking_municipios AS (
        SELECT
            entidad,
            municipio,
            total_accidentes,
            total_muertos,
            total_heridos,
            ROW_NUMBER() OVER (
                PARTITION BY entidad
                ORDER BY total_accidentes DESC
            ) AS ranking_en_entidad
        FROM accidentes_municipio
    )
    SELECT
        entidad,
        municipio,
        total_accidentes,
        total_muertos,
        total_heridos,
        ranking_en_entidad
    FROM ranking_municipios
    WHERE ranking_en_entidad <= 3
    ORDER BY entidad, ranking_en_entidad;
    """
    return pd.read_sql(query, _engine)


# =============================================================================
# Query 6 — Clasificación de accidentes
# =============================================================================

@st.cache_data(ttl=600)
def q6_clasificacion(_engine):
    query = """
    WITH accidentes_clasificacion AS (
        SELECT
            da.clasificacion,
            SUM(fa.num_accidentes) AS total_accidentes,
            SUM(fa.total_muertos) AS total_muertos,
            SUM(fa.total_heridos) AS total_heridos
        FROM atus_dwh.fact_accidentes fa
        JOIN atus_dwh.dim_accidente da
            ON fa.accidente_key = da.accidente_key
        GROUP BY da.clasificacion
    )
    SELECT
        clasificacion,
        total_accidentes,
        total_muertos,
        total_heridos,
        ROUND(
            100.0 * total_accidentes
            / SUM(total_accidentes) OVER (),
            2
        ) AS porcentaje_accidentes
    FROM accidentes_clasificacion
    ORDER BY total_accidentes DESC;
    """
    return pd.read_sql(query, _engine)


# =============================================================================
# Query 7 — Vehículos involucrados
# =============================================================================

@st.cache_data(ttl=600)
def q7_vehiculos(_engine):
    query = """
    WITH vehiculos AS (
        SELECT 'Automovil' AS tipo_vehiculo, SUM(automovil) AS total FROM atus_dwh.fact_accidentes
        UNION ALL
        SELECT 'Motocicleta', SUM(motocicleta) FROM atus_dwh.fact_accidentes
        UNION ALL
        SELECT 'Bicicleta', SUM(bicicleta) FROM atus_dwh.fact_accidentes
        UNION ALL
        SELECT 'Camioneta', SUM(camioneta) FROM atus_dwh.fact_accidentes
        UNION ALL
        SELECT 'Camion', SUM(camion) FROM atus_dwh.fact_accidentes
        UNION ALL
        SELECT 'Microbus', SUM(microbus) FROM atus_dwh.fact_accidentes
        UNION ALL
        SELECT 'Omnibus', SUM(omnibus) FROM atus_dwh.fact_accidentes
        UNION ALL
        SELECT 'Tractor', SUM(tractor) FROM atus_dwh.fact_accidentes
        UNION ALL
        SELECT 'Ferrocarril', SUM(ferrocarril) FROM atus_dwh.fact_accidentes
        UNION ALL
        SELECT 'Otro vehiculo', SUM(otro_vehiculo) FROM atus_dwh.fact_accidentes
    )
    SELECT
        tipo_vehiculo,
        total,
        RANK() OVER (ORDER BY total DESC) AS ranking
    FROM vehiculos
    ORDER BY total DESC;
    """
    return pd.read_sql(query, _engine)


# =============================================================================
# Carga de datos
# =============================================================================

try:
    kpis = load_kpis(engine)

    q1 = q1_ranking_entidades(engine)
    q2 = q2_tendencia_mensual(engine)
    q3 = q3_promedio_movil(engine)
    q4 = q4_dia_banda(engine)
    q5 = q5_top_municipios(engine)
    q6 = q6_clasificacion(engine)
    q7 = q7_vehiculos(engine)

except Exception as exc:
    st.error(f"Error al consultar la base de datos: {exc}")
    st.stop()


# =============================================================================
# KPIs
# =============================================================================

st.subheader("📌 Resumen general")

kpi = kpis.iloc[0]

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Accidentes", format_int(kpi["total_accidentes"]))
col2.metric("Muertos", format_int(kpi["total_muertos"]))
col3.metric("Heridos", format_int(kpi["total_heridos"]))
col4.metric("Muertos / accidente", f"{kpi['muertos_por_accidente']:.4f}")
col5.metric("Heridos / accidente", f"{kpi['heridos_por_accidente']:.4f}")

st.divider()


# =============================================================================
# Tabs del dashboard
# =============================================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "🗺️ Geografía",
        "📈 Temporal",
        "🕒 Día y hora",
        "⚠️ Severidad",
        "🚗 Vehículos",
    ]
)


# =============================================================================
# Tab 1 — Geografía
# =============================================================================

with tab1:
    st.header("1. Ranking de entidades con mayor número de accidentes")

    fig_q1 = px.bar(
        q1.sort_values("total_accidentes", ascending=True),
        x="total_accidentes",
        y="entidad",
        orientation="h",
        hover_data=[
            "ranking",
            "total_muertos",
            "total_heridos",
            "muertos_por_accidente",
            "heridos_por_accidente",
        ],
        title="Top 10 entidades por accidentes viales",
        labels={
            "total_accidentes": "Accidentes",
            "entidad": "Entidad",
        },
    )
    fig_q1.update_layout(
        yaxis_title=None,
        xaxis_title="Accidentes",
        height=550,
    )
    st.plotly_chart(fig_q1, use_container_width=True)

    st.divider()

    st.header("5. Municipios con mayor siniestralidad dentro de cada entidad")

    entidades = sorted(q5["entidad"].unique())
    entidad_sel = st.selectbox("Selecciona una entidad", entidades)

    q5_filtrado = q5[q5["entidad"] == entidad_sel].sort_values(
        "total_accidentes",
        ascending=True,
    )

    fig_q5 = px.bar(
        q5_filtrado,
        x="total_accidentes",
        y="municipio",
        orientation="h",
        hover_data=["total_muertos", "total_heridos", "ranking_en_entidad"],
        title=f"Top municipios en {entidad_sel}",
        labels={
            "total_accidentes": "Accidentes",
            "municipio": "Municipio",
        },
    )
    fig_q5.update_layout(
        yaxis_title=None,
        xaxis_title="Accidentes",
        height=450,
    )
    st.plotly_chart(fig_q5, use_container_width=True)


# =============================================================================
# Tab 2 — Temporal
# =============================================================================

with tab2:
    st.header("2. Tendencia mensual de accidentes, muertos y heridos")

    fig_q2 = px.line(
        q2,
        x="mes_nombre",
        y=["total_accidentes", "total_heridos", "total_muertos"],
        markers=True,
        title="Tendencia mensual de accidentes, heridos y muertos",
        labels={
            "mes_nombre": "Mes",
            "value": "Total",
            "variable": "Métrica",
        },
    )
    fig_q2.update_layout(
        xaxis_title="Mes",
        yaxis_title="Total",
        height=500,
    )
    st.plotly_chart(fig_q2, use_container_width=True)

    st.divider()

    st.header("3. Promedio móvil semanal de accidentes")

    fig_q3 = px.line(
        q3,
        x="full_date",
        y=["total_accidentes", "promedio_movil_7_dias"],
        title="Accidentes diarios y promedio móvil de 7 días",
        labels={
            "full_date": "Fecha",
            "value": "Accidentes",
            "variable": "Serie",
        },
    )
    fig_q3.update_layout(
        xaxis_title="Fecha",
        yaxis_title="Accidentes",
        height=500,
    )
    st.plotly_chart(fig_q3, use_container_width=True)


# =============================================================================
# Tab 3 — Día y hora
# =============================================================================

with tab3:
    st.header("4. Accidentes por día de semana y banda horaria")

    orden_dias = [
        "Lunes",
        "Martes",
        "Miércoles",
        "Jueves",
        "Viernes",
        "Sábado",
        "Domingo",
    ]

    orden_bandas = [
        "Madrugada",
        "Mañana",
        "Tarde",
        "Noche",
        "Sin especificar",
    ]

    heatmap = q4.pivot(
        index="dia_semana_nombre",
        columns="banda_horaria",
        values="total_accidentes",
    )

    heatmap = heatmap.reindex(index=orden_dias, columns=orden_bandas)

    fig_q4 = px.imshow(
        heatmap,
        text_auto=True,
        aspect="auto",
        title="Heatmap de accidentes por día de semana y banda horaria",
        labels={
            "x": "Banda horaria",
            "y": "Día de semana",
            "color": "Accidentes",
        },
    )
    fig_q4.update_layout(
        xaxis_title="Banda horaria",
        yaxis_title="Día de semana",
        height=550,
    )
    st.plotly_chart(fig_q4, use_container_width=True)


# =============================================================================
# Tab 4 — Severidad
# =============================================================================

with tab4:
    st.header("6. Participación porcentual de accidentes por clasificación")

    col_a, col_b = st.columns([1, 1])

    with col_a:
        fig_q6_pie = px.pie(
            q6,
            names="clasificacion",
            values="total_accidentes",
            title="Distribución de accidentes por clasificación",
            hover_data=["porcentaje_accidentes", "total_muertos", "total_heridos"],
        )
        fig_q6_pie.update_layout(height=500)
        st.plotly_chart(fig_q6_pie, use_container_width=True)

    with col_b:
        fig_q6_bar = px.bar(
            q6.sort_values("total_accidentes", ascending=True),
            x="total_accidentes",
            y="clasificacion",
            orientation="h",
            title="Accidentes por clasificación",
            labels={
                "total_accidentes": "Accidentes",
                "clasificacion": "Clasificación",
            },
        )
        fig_q6_bar.update_layout(
            yaxis_title=None,
            xaxis_title="Accidentes",
            height=500,
        )
        st.plotly_chart(fig_q6_bar, use_container_width=True)


# =============================================================================
# Tab 5 — Vehículos
# =============================================================================
with tab5:
    st.header("7. Vehículos más involucrados en accidentes")

    fig_q7 = px.bar(
        q7.sort_values("total", ascending=True),
        x="total",
        y="tipo_vehiculo",
        orientation="h",
        text="ranking",
        title="Tipos de vehículos más involucrados",
        labels={
            "total": "Vehículos registrados",
            "tipo_vehiculo": "Tipo de vehículo",
        },
    )

    fig_q7.update_layout(
        yaxis_title=None,
        xaxis_title="Vehículos registrados",
        height=550,
    )

    st.plotly_chart(fig_q7, use_container_width=True)


# =============================================================================
# Pie de página
# =============================================================================

st.divider()

st.markdown(
    """
    **Fuente:** INEGI — Accidentes de Tránsito Terrestre en Zonas Urbanas y Suburbanas (ATUS), 2024.  
    """
)

