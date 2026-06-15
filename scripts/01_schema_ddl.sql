-- =============================================================================
-- Proyecto final — Siniestralidad vial en México
-- Fuente: ATUS 2024, INEGI
-- =============================================================================
-- Schema: atus_dwh
-- Grano de la fact: una fila por accidente vial registrado
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS atus_dwh;
SET search_path TO atus_dwh;

-- -----------------------------------------------------------------------------
-- DIMENSIONES
-- -----------------------------------------------------------------------------

-- Una fila por fecha calendario presente en el dataset.
-- date_key es una smart key con formato YYYYMMDD.
CREATE TABLE dim_fecha (
    date_key              INT          PRIMARY KEY,  -- Ejemplo: 20240115
    full_date             DATE         NOT NULL UNIQUE,
    anio                  SMALLINT     NOT NULL,
    trimestre             SMALLINT     NOT NULL,
    mes_numero            SMALLINT     NOT NULL,
    mes_nombre            VARCHAR(12)  NOT NULL,
    dia_mes               SMALLINT     NOT NULL,
    dia_semana_numero     SMALLINT     NOT NULL,
    dia_semana_nombre     VARCHAR(10)  NOT NULL,
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


-- Una fila por combinación hora × minuto.
-- time_key es una smart key con formato HHMM.
CREATE TABLE dim_tiempo (
    time_key              SMALLINT     PRIMARY KEY,  -- Ejemplo: 1845
    hora                  SMALLINT     NOT NULL,
    minuto                SMALLINT     NOT NULL,
    hora_texto            CHAR(5)      NOT NULL UNIQUE,  -- Ejemplo: 18:45
    banda_horaria         VARCHAR(12)  NOT NULL,         -- madrugada, mañana, tarde, noche

    CONSTRAINT chk_dim_tiempo_hora
        CHECK (hora BETWEEN 0 AND 23),

    CONSTRAINT chk_dim_tiempo_minuto
        CHECK (minuto BETWEEN 0 AND 59),

    CONSTRAINT chk_dim_tiempo_banda
        CHECK (banda_horaria IN ('Madrugada', 'Mañana', 'Tarde', 'Noche'))
);


-- Una fila por combinación entidad × municipio × cobertura.
CREATE TABLE dim_ubicacion (
    ubicacion_key         INT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_entidad            SMALLINT     NOT NULL,
    entidad               VARCHAR(50)  NOT NULL,
    id_municipio          SMALLINT     NOT NULL,
    municipio             VARCHAR(100) NOT NULL,
    cobertura             VARCHAR(30)  NOT NULL,

    CONSTRAINT uq_dim_ubicacion
        UNIQUE (id_entidad, id_municipio, cobertura)
);


-- Una fila por combinación de atributos descriptivos del accidente.
CREATE TABLE dim_accidente (
    accidente_key         INT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo_accidente        VARCHAR(100) NOT NULL,
    causa_accidente       VARCHAR(50)  NOT NULL,
    clasificacion         VARCHAR(30)  NOT NULL,
    zona_urbana           VARCHAR(80),
    zona_suburbana        VARCHAR(80),
    capa_rodamiento       VARCHAR(50),
    estatus               VARCHAR(50),

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


-- Una fila por combinación de características de la persona conductora.
CREATE TABLE dim_conductor (
    conductor_key         INT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sexo                  VARCHAR(20)  NOT NULL,
    id_edad               SMALLINT     NOT NULL,
    edad_descripcion      VARCHAR(60)  NOT NULL,
    aliento_alcoholico    VARCHAR(20),
    cinturon_seguridad    VARCHAR(20),

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

    -- Foreign keys
    date_key              INT          NOT NULL REFERENCES dim_fecha(date_key),
    time_key              SMALLINT     NOT NULL REFERENCES dim_tiempo(time_key),
    ubicacion_key         INT          NOT NULL REFERENCES dim_ubicacion(ubicacion_key),
    accidente_key         INT          NOT NULL REFERENCES dim_accidente(accidente_key),
    conductor_key         INT          NOT NULL REFERENCES dim_conductor(conductor_key),

    -- Medida base para facilitar agregaciones
    num_accidentes        SMALLINT     NOT NULL DEFAULT 1,

    -- Vehículos involucrados
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

    CONSTRAINT chk_fact_total_muertos
        CHECK (total_muertos >= 0),

    CONSTRAINT chk_fact_total_heridos
        CHECK (total_heridos >= 0)
);


-- -----------------------------------------------------------------------------
-- ÍNDICES PARA CONSULTAS ANALÍTICAS
-- -----------------------------------------------------------------------------

-- Tendencias temporales
CREATE INDEX idx_fact_fecha
    ON fact_accidentes(date_key);

CREATE INDEX idx_fact_tiempo
    ON fact_accidentes(time_key);

-- Análisis geográfico
CREATE INDEX idx_fact_ubicacion
    ON fact_accidentes(ubicacion_key);

-- Severidad por tipo de accidente
CREATE INDEX idx_fact_accidente
    ON fact_accidentes(accidente_key);

-- Análisis del perfil del conductor
CREATE INDEX idx_fact_conductor
    ON fact_accidentes(conductor_key);

-- Consulta combinada frecuente: ubicación × fecha
CREATE INDEX idx_fact_ubicacion_fecha
    ON fact_accidentes(ubicacion_key, date_key);


-- =============================================================================
-- VERIFICACIÓN
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

