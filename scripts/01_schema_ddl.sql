-- =============================================================================
-- Proyecto final — Siniestralidad vial en Mexico (ATUS 2024)
-- =============================================================================
-- Schema: atus_dwh
-- Grano de la fact: una fila por accidente vial registrado en ATUS
-- Fuente: INEGI — Accidentes de Transito Terrestre en Zonas Urbanas y Suburbanas
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS atus_dwh;
SET search_path TO atus_dwh;

-- -----------------------------------------------------------------------------
-- DIMENSIONES
-- -----------------------------------------------------------------------------

-- Una fila por fecha calendario.
-- date_key es una smart key con formato YYYYMMDD.
CREATE TABLE dim_fecha (
    date_key              INT          PRIMARY KEY,  -- Ejemplo: 20240115
    full_date             DATE         NOT NULL UNIQUE,
    anio                  SMALLINT     NOT NULL,
    trimestre             SMALLINT     NOT NULL,
    mes_numero            SMALLINT     NOT NULL,
    mes_nombre            VARCHAR(15)  NOT NULL,
    dia_mes               SMALLINT     NOT NULL,
    dia_semana_numero     SMALLINT     NOT NULL,
    dia_semana_nombre     VARCHAR(15)  NOT NULL,
    es_fin_semana         BOOLEAN      NOT NULL,

    CONSTRAINT chk_dim_fecha_mes
        CHECK (mes_numero BETWEEN 1 AND 12),

    CONSTRAINT chk_dim_fecha_dia
        CHECK (dia_mes BETWEEN 1 AND 31),

    CONSTRAINT chk_dim_fecha_trimestre
        CHECK (trimestre BETWEEN 1 AND 4),

    CONSTRAINT chk_dim_fecha_dia_semana
        CHECK (dia_semana_numero BETWEEN 1 AND 7)
);


-- Una fila por combinacion hora × minuto.
-- time_key es una smart key con formato HHMM.
-- Se usa -1 para registros sin hora/minuto especificado.
CREATE TABLE dim_tiempo (
    time_key              SMALLINT     PRIMARY KEY,      -- Ejemplo: 1845, -1 si no especifica
    hora                  SMALLINT     NOT NULL,
    minuto                SMALLINT     NOT NULL,
    hora_texto            VARCHAR(8)   NOT NULL UNIQUE,  -- Ejemplo: 18:45, S/E
    banda_horaria         VARCHAR(20)  NOT NULL,         -- Madrugada, Mañana, Tarde, Noche, Sin especificar

    CONSTRAINT chk_dim_tiempo_hora
        CHECK (hora BETWEEN 0 AND 23 OR hora = -1),

    CONSTRAINT chk_dim_tiempo_minuto
        CHECK (minuto BETWEEN 0 AND 59 OR minuto = -1),

    CONSTRAINT chk_dim_tiempo_banda
        CHECK (
            banda_horaria IN (
                'Madrugada',
                'Mañana',
                'Tarde',
                'Noche',
                'Sin especificar'
            )
        )
);


-- Una fila por combinacion entidad × municipio × cobertura.
CREATE TABLE dim_ubicacion (
    ubicacion_key         INT           GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_entidad            SMALLINT      NOT NULL,
    entidad               VARCHAR(80)   NOT NULL,
    id_municipio          SMALLINT      NOT NULL,
    municipio             VARCHAR(150)  NOT NULL,
    cobertura             VARCHAR(50)   NOT NULL,

    CONSTRAINT uq_dim_ubicacion
        UNIQUE (id_entidad, id_municipio, cobertura)
);


-- Una fila por combinacion de atributos descriptivos del accidente.
CREATE TABLE dim_accidente (
    accidente_key         INT           GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo_accidente        VARCHAR(150)  NOT NULL,
    causa_accidente       VARCHAR(100)  NOT NULL,
    clasificacion         VARCHAR(60)   NOT NULL,
    zona_urbana           VARCHAR(100)  NOT NULL,
    zona_suburbana        VARCHAR(100)  NOT NULL,
    capa_rodamiento       VARCHAR(100)  NOT NULL,
    estatus               VARCHAR(100)  NOT NULL,

    CONSTRAINT uq_dim_accidente
        UNIQUE (
            tipo_accidente,
            causa_accidente,
            clasificacion,
            zona_urbana,
            zona_suburbana,
            capa_rodamiento,
            estatus
        )
);


-- Una fila por combinacion de caracteristicas de la persona conductora.
CREATE TABLE dim_conductor (
    conductor_key         INT           GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sexo                  VARCHAR(40)   NOT NULL,
    id_edad               SMALLINT      NOT NULL,
    edad_descripcion      VARCHAR(100)  NOT NULL,
    aliento_alcoholico    VARCHAR(40)   NOT NULL,
    cinturon_seguridad    VARCHAR(40)   NOT NULL,

    CONSTRAINT uq_dim_conductor
        UNIQUE (
            sexo,
            id_edad,
            edad_descripcion,
            aliento_alcoholico,
            cinturon_seguridad
        )
);


-- -----------------------------------------------------------------------------
-- FACT
-- -----------------------------------------------------------------------------

CREATE TABLE fact_accidentes (
    accidente_id          BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Identificador tecnico de la fila original del CSV.
    -- Sirve para trazabilidad e idempotencia del ETL.
    source_row_id         BIGINT       NOT NULL UNIQUE,

    -- Foreign keys del esquema estrella
    date_key              INT          NOT NULL REFERENCES dim_fecha(date_key),
    time_key              SMALLINT     NOT NULL REFERENCES dim_tiempo(time_key),
    ubicacion_key         INT          NOT NULL REFERENCES dim_ubicacion(ubicacion_key),
    accidente_key         INT          NOT NULL REFERENCES dim_accidente(accidente_key),
    conductor_key         INT          NOT NULL REFERENCES dim_conductor(conductor_key),

    -- Medida base para facilitar agregaciones
    num_accidentes        SMALLINT     NOT NULL DEFAULT 1,

    -- Vehiculos involucrados
    automovil             SMALLINT     NOT NULL DEFAULT 0,
    campasaj              SMALLINT     NOT NULL DEFAULT 0,
    microbus              SMALLINT     NOT NULL DEFAULT 0,
    pascamion             SMALLINT     NOT NULL DEFAULT 0,
    omnibus               SMALLINT     NOT NULL DEFAULT 0,
    tranvia               SMALLINT     NOT NULL DEFAULT 0,
    camioneta             SMALLINT     NOT NULL DEFAULT 0,
    camion                SMALLINT     NOT NULL DEFAULT 0,
    tractor               SMALLINT     NOT NULL DEFAULT 0,
    ferrocarril           SMALLINT     NOT NULL DEFAULT 0,
    motocicleta           SMALLINT     NOT NULL DEFAULT 0,
    bicicleta             SMALLINT     NOT NULL DEFAULT 0,
    otro_vehiculo         SMALLINT     NOT NULL DEFAULT 0,

    -- Personas fallecidas y heridas por tipo de usuario vial
    conductor_muerto      SMALLINT     NOT NULL DEFAULT 0,
    conductor_herido      SMALLINT     NOT NULL DEFAULT 0,
    pasajero_muerto       SMALLINT     NOT NULL DEFAULT 0,
    pasajero_herido       SMALLINT     NOT NULL DEFAULT 0,
    peaton_muerto         SMALLINT     NOT NULL DEFAULT 0,
    peaton_herido         SMALLINT     NOT NULL DEFAULT 0,
    ciclista_muerto       SMALLINT     NOT NULL DEFAULT 0,
    ciclista_herido       SMALLINT     NOT NULL DEFAULT 0,
    otro_muerto           SMALLINT     NOT NULL DEFAULT 0,
    otro_herido           SMALLINT     NOT NULL DEFAULT 0,

    -- Totales reportados por ATUS
    total_muertos         SMALLINT     NOT NULL DEFAULT 0,
    total_heridos         SMALLINT     NOT NULL DEFAULT 0,

    CONSTRAINT chk_fact_num_accidentes
        CHECK (num_accidentes = 1),

    CONSTRAINT chk_fact_vehiculos_no_negativos
        CHECK (
            automovil >= 0
            AND campasaj >= 0
            AND microbus >= 0
            AND pascamion >= 0
            AND omnibus >= 0
            AND tranvia >= 0
            AND camioneta >= 0
            AND camion >= 0
            AND tractor >= 0
            AND ferrocarril >= 0
            AND motocicleta >= 0
            AND bicicleta >= 0
            AND otro_vehiculo >= 0
        ),

    CONSTRAINT chk_fact_muertos_no_negativos
        CHECK (
            conductor_muerto >= 0
            AND pasajero_muerto >= 0
            AND peaton_muerto >= 0
            AND ciclista_muerto >= 0
            AND otro_muerto >= 0
            AND total_muertos >= 0
        ),

    CONSTRAINT chk_fact_heridos_no_negativos
        CHECK (
            conductor_herido >= 0
            AND pasajero_herido >= 0
            AND peaton_herido >= 0
            AND ciclista_herido >= 0
            AND otro_herido >= 0
            AND total_heridos >= 0
        )
);


-- -----------------------------------------------------------------------------
-- INDICES PARA CONSULTAS ANALITICAS
-- -----------------------------------------------------------------------------

-- Tendencias temporales
CREATE INDEX idx_fact_fecha
    ON fact_accidentes(date_key);

CREATE INDEX idx_fact_tiempo
    ON fact_accidentes(time_key);

-- Analisis geografico
CREATE INDEX idx_fact_ubicacion
    ON fact_accidentes(ubicacion_key);

-- Severidad por tipo de accidente
CREATE INDEX idx_fact_accidente
    ON fact_accidentes(accidente_key);

-- Analisis del perfil del conductor
CREATE INDEX idx_fact_conductor
    ON fact_accidentes(conductor_key);

-- Consulta combinada frecuente: ubicacion × fecha
CREATE INDEX idx_fact_ubicacion_fecha
    ON fact_accidentes(ubicacion_key, date_key);

-- Consultas de severidad
CREATE INDEX idx_fact_accidentes_fatales
    ON fact_accidentes(accidente_key, ubicacion_key, date_key)
    WHERE total_muertos > 0;

CREATE INDEX idx_fact_accidentes_con_heridos
    ON fact_accidentes(accidente_key, ubicacion_key, date_key)
    WHERE total_heridos > 0;


-- =============================================================================
-- VERIFICACION
-- =============================================================================

-- Listar tablas creadas:
-- SELECT table_name
-- FROM information_schema.tables
-- WHERE table_schema = 'atus_dwh'
-- ORDER BY table_name;

-- Resultado esperado:
--   dim_accidente
--   dim_conductor
--   dim_fecha
--   dim_tiempo
--   dim_ubicacion
--   fact_accidentes
-- =============================================================================