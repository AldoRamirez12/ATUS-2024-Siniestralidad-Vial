-- =============================================================================
-- Queries analíticas — Siniestralidad vial en México (ATUS 2024)
-- =============================================================================
-- Schema: atus_dwh
-- Objetivo: responder preguntas de negocio sobre patrones geográficos,
-- temporales y de severidad de los accidentes viales registrados en ATUS 2024.
-- =============================================================================

SET search_path TO atus_dwh;


-- =============================================================================
-- 1. Ranking de entidades con mayor número de accidentes
-- =============================================================================
-- Pregunta:
-- ¿Qué entidades concentran la mayor cantidad de accidentes viales en 2024?
--
-- Técnica:
-- GROUP BY + RANK() OVER()
-- =============================================================================


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

-- =============================================================================
-- 2. Tendencia mensual de accidentes, muertos y heridos
-- =============================================================================
-- Pregunta:
-- ¿Cómo evolucionaron los accidentes viales a lo largo de 2024?
--
-- Técnica:
-- CTE + LAG() para variación mensual
-- =============================================================================

WITH accidentes_mes AS (
    SELECT
        df.mes_numero,
        df.mes_nombre,
        SUM(fa.num_accidentes) AS total_accidentes,
        SUM(fa.total_muertos) AS total_muertos,
        SUM(fa.total_heridos) AS total_heridos
    FROM fact_accidentes fa
    JOIN dim_fecha df
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


-- =============================================================================
-- 3. Promedio móvil semanal de accidentes
-- =============================================================================
-- Pregunta:
-- ¿Existen periodos con incrementos sostenidos en la frecuencia de accidentes?
--
-- Técnica:
-- Window function con AVG() OVER()
-- =============================================================================

WITH accidentes_dia AS (
    SELECT
        df.full_date,
        SUM(fa.num_accidentes) AS total_accidentes
    FROM fact_accidentes fa
    JOIN dim_fecha df
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


-- =============================================================================
-- 4. Accidentes por día de semana y banda horaria
-- =============================================================================
-- Pregunta:
-- ¿En qué combinaciones de día y franja horaria se concentran más accidentes?
--
-- Técnica:
-- GROUP BY + ordenamiento analítico
-- =============================================================================

SELECT
    df.dia_semana_numero,
    df.dia_semana_nombre,
    dt.banda_horaria,
    SUM(fa.num_accidentes) AS total_accidentes,
    SUM(fa.total_muertos) AS total_muertos,
    SUM(fa.total_heridos) AS total_heridos
FROM fact_accidentes fa
JOIN dim_fecha df
    ON fa.date_key = df.date_key
JOIN dim_tiempo dt
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


-- =============================================================================
-- 5. Municipios con mayor siniestralidad dentro de cada entidad
-- =============================================================================
-- Pregunta:
-- ¿Cuál es el municipio con más accidentes dentro de cada entidad federativa?
--
-- Técnica:
-- ROW_NUMBER() PARTITION BY
-- =============================================================================

WITH accidentes_municipio AS (
    SELECT
        du.entidad,
        du.municipio,
        SUM(fa.num_accidentes) AS total_accidentes,
        SUM(fa.total_muertos) AS total_muertos,
        SUM(fa.total_heridos) AS total_heridos
    FROM fact_accidentes fa
    JOIN dim_ubicacion du
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


-- =============================================================================
-- 6. Participación porcentual de accidentes por clasificación
-- =============================================================================
-- Pregunta:
-- ¿Qué proporción de accidentes corresponde a sólo daños, no fatales y fatales?
--
-- Técnica:
-- SUM() OVER() para porcentaje sobre total
-- =============================================================================

WITH accidentes_clasificacion AS (
    SELECT
        da.clasificacion,
        SUM(fa.num_accidentes) AS total_accidentes,
        SUM(fa.total_muertos) AS total_muertos,
        SUM(fa.total_heridos) AS total_heridos
    FROM fact_accidentes fa
    JOIN dim_accidente da
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


-- =============================================================================
-- 7. Vehículos más involucrados en accidentes
-- =============================================================================
-- Pregunta:
-- ¿Qué tipos de vehículos aparecen con mayor frecuencia en los accidentes?
--
-- Técnica:
-- UNPIVOT manual con UNION ALL
-- =============================================================================

WITH vehiculos AS (
    SELECT 'Automovil' AS tipo_vehiculo, SUM(automovil) AS total FROM fact_accidentes
    UNION ALL
    SELECT 'Motocicleta', SUM(motocicleta) FROM fact_accidentes
    UNION ALL
    SELECT 'Bicicleta', SUM(bicicleta) FROM fact_accidentes
    UNION ALL
    SELECT 'Camioneta', SUM(camioneta) FROM fact_accidentes
    UNION ALL
    SELECT 'Camion', SUM(camion) FROM fact_accidentes
    UNION ALL
    SELECT 'Microbus', SUM(microbus) FROM fact_accidentes
    UNION ALL
    SELECT 'Omnibus', SUM(omnibus) FROM fact_accidentes
    UNION ALL
    SELECT 'Tractor', SUM(tractor) FROM fact_accidentes
    UNION ALL
    SELECT 'Ferrocarril', SUM(ferrocarril) FROM fact_accidentes
    UNION ALL
    SELECT 'Otro vehiculo', SUM(otro_vehiculo) FROM fact_accidentes
)
SELECT
    tipo_vehiculo,
    total,
    RANK() OVER (ORDER BY total DESC) AS ranking
FROM vehiculos
ORDER BY total DESC;


