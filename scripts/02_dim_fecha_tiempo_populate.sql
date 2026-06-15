-- =============================================================================
-- Poblar dim_fecha y dim_tiempo
-- =============================================================================
-- Rango 2024 completo + combinaciones hora:minuto.
-- Fuente: ATUS 2024, INEGI
-- =============================================================================

SET search_path TO atus_dwh;

-- -----------------------------------------------------------------------------
-- dim_fecha (366 filas para 2024, año bisiesto)
-- -----------------------------------------------------------------------------

INSERT INTO dim_fecha (
    date_key,
    full_date,
    anio,
    trimestre,
    mes_numero,
    mes_nombre,
    dia_mes,
    dia_semana_nombre,
    es_fin_semana
)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT                AS date_key,
    d                                          AS full_date,
    EXTRACT(year    FROM d)::SMALLINT          AS anio,
    EXTRACT(quarter FROM d)::SMALLINT          AS trimestre,
    EXTRACT(month   FROM d)::SMALLINT          AS mes_numero,
    CASE EXTRACT(month FROM d)
        WHEN 1  THEN 'Enero'
        WHEN 2  THEN 'Febrero'
        WHEN 3  THEN 'Marzo'
        WHEN 4  THEN 'Abril'
        WHEN 5  THEN 'Mayo'
        WHEN 6  THEN 'Junio'
        WHEN 7  THEN 'Julio'
        WHEN 8  THEN 'Agosto'
        WHEN 9  THEN 'Septiembre'
        WHEN 10 THEN 'Octubre'
        WHEN 11 THEN 'Noviembre'
        WHEN 12 THEN 'Diciembre'
    END                                        AS mes_nombre,
    EXTRACT(day FROM d)::SMALLINT              AS dia_mes,
    CASE EXTRACT(isodow FROM d)
        WHEN 1 THEN 'Lunes'
        WHEN 2 THEN 'Martes'
        WHEN 3 THEN 'Miércoles'
        WHEN 4 THEN 'Jueves'
        WHEN 5 THEN 'Viernes'
        WHEN 6 THEN 'Sábado'
        WHEN 7 THEN 'Domingo'
    END                                        AS dia_semana_nombre,
    EXTRACT(isodow FROM d) IN (6, 7)           AS es_fin_semana
FROM generate_series(
    '2024-01-01'::DATE,
    '2024-12-31'::DATE,
    '1 day'
) AS d
ON CONFLICT (date_key) DO NOTHING;


-- -----------------------------------------------------------------------------
-- dim_tiempo (1,440 filas hora:minuto + 1 fila para sin especificar)
-- -----------------------------------------------------------------------------
-- time_key usa formato HHMM:
--   0    = 00:00
--   1    = 00:01
--   930  = 09:30
--   2359 = 23:59
--  -1    = Sin especificar
-- -----------------------------------------------------------------------------

INSERT INTO dim_tiempo (
    time_key,
    hora,
    minuto,
    hora_texto,
    banda_horaria
)
SELECT
    (h * 100 + m)::SMALLINT                    AS time_key,
    h::SMALLINT                                AS hora,
    m::SMALLINT                                AS minuto,
    LPAD(h::TEXT, 2, '0') || ':' ||
    LPAD(m::TEXT, 2, '0')                      AS hora_texto,
    CASE
        WHEN h BETWEEN 0  AND 5  THEN 'Madrugada'
        WHEN h BETWEEN 6  AND 11 THEN 'Mañana'
        WHEN h BETWEEN 12 AND 17 THEN 'Tarde'
        ELSE 'Noche'
    END                                        AS banda_horaria
FROM generate_series(0, 23) AS h
CROSS JOIN generate_series(0, 59) AS m
ON CONFLICT (time_key) DO NOTHING;


-- -----------------------------------------------------------------------------
-- Fila especial para registros sin hora/minuto especificado
-- -----------------------------------------------------------------------------

INSERT INTO dim_tiempo (
    time_key,
    hora,
    minuto,
    hora_texto,
    banda_horaria
)
VALUES (
    -1,
    -1,
    -1,
    'Sin esp.',
    'Sin especificar'
)
ON CONFLICT (time_key) DO NOTHING;


-- =============================================================================
-- VERIFICACIÓN
-- =============================================================================

-- SELECT COUNT(*) FROM atus_dwh.dim_fecha;
-- Esperado: 366

-- SELECT COUNT(*) FROM atus_dwh.dim_tiempo;
-- Esperado: 1441

-- SELECT banda_horaria, COUNT(*)
-- FROM atus_dwh.dim_tiempo
-- GROUP BY banda_horaria
-- ORDER BY banda_horaria;
--
-- Esperado:
-- Madrugada        360
-- Mañana           360
-- Noche            360
-- Sin especificar    1
-- Tarde            360