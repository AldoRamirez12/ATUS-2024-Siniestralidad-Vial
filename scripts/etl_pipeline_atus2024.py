"""
ETL Pipeline — Siniestralidad vial en México (ATUS 2024)

Lee los microdatos anuales de ATUS 2024 y sus catálogos, transforma la
información al modelo dimensional y la carga a Aurora PostgreSQL.

Uso:
    python scripts/etl_pipeline.py \
        --host aurora-mod4.cluster-XXX.us-east-1.rds.amazonaws.com \
        --password TU_PASSWORD \
        --database northwind \
        --data-dir data/raw


El ETL carga:
    - dim_ubicacion
    - dim_accidente
    - dim_conductor
    - fact_accidentes
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.types import BigInteger, Integer, SmallInteger
from tqdm import tqdm

logger = logging.getLogger("etl_atus")


# =============================================================================
# Configuración de columnas
# =============================================================================

VEHICULOS_MAP = {
    "automovil": "automovil",
    "campasaj": "campasaj",
    "microbus": "microbus",
    "pascamion": "pascamion",
    "omnibus": "omnibus",
    "tranvia": "tranvia",
    "camioneta": "camioneta",
    "camion": "camion",
    "tractor": "tractor",
    "ferrocarri": "ferrocarril",
    "motociclet": "motocicleta",
    "bicicleta": "bicicleta",
    "otrovehic": "otro_vehiculo",
}

PERSONAS_MAP = {
    "condmuerto": "conductor_muerto",
    "condherido": "conductor_herido",
    "pasamuerto": "pasajero_muerto",
    "pasaherido": "pasajero_herido",
    "peatmuerto": "peaton_muerto",
    "peatherido": "peaton_herido",
    "ciclmuerto": "ciclista_muerto",
    "ciclherido": "ciclista_herido",
    "otromuerto": "otro_muerto",
    "otroherido": "otro_herido",
    "nemuerto": "total_muertos",
    "neherido": "total_heridos",
}


# =============================================================================
# Extract
# =============================================================================

def read_csv(data_dir: Path, filename: str) -> pd.DataFrame:
    """Lee un CSV con codificación UTF-8."""
    path = data_dir / filename
    logger.info("Leyendo %s", path)

    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo: {path}")

    df = pd.read_csv(path, encoding="utf-8")
    df.columns = df.columns.str.strip().str.lower()

    logger.info("  %s: %s filas × %s columnas", filename, *df.shape)
    return df


def extract(data_dir: Path) -> dict[str, pd.DataFrame]:
    """Lee el archivo principal de ATUS y los catálogos."""
    data = {
        "atus": read_csv(data_dir, "atus_anual_2024.csv"),
        "entidad": read_csv(data_dir, "tc_entidad.csv"),
        "municipio": read_csv(data_dir, "tc_municipio.csv"),
        "edad": read_csv(data_dir, "tc_edad.csv"),
    }

    return data


# =============================================================================
# Transform
# =============================================================================

def clean_text_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Limpia nulos y espacios en columnas de texto."""
    df = df.copy()

    for col in columns:
        if col in df.columns:
            df[col] = (
                df[col]
                .fillna("Sin especificar")
                .astype(str)
                .str.strip()
                .replace({"": "Sin especificar"})
            )

    return df


def build_base_dataframe(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Integra ATUS con catálogos y calcula llaves naturales."""
    atus = data["atus"].copy()
    entidad = data["entidad"].copy()
    municipio = data["municipio"].copy()
    edad = data["edad"].copy()

    # Trazabilidad de la fila original.
    atus = atus.reset_index(drop=True)
    atus["source_row_id"] = atus.index + 1

    # Normalizar nombres de catálogos.
    entidad = entidad.rename(
        columns={
            "nom_entidad": "entidad",
        }
    )

    municipio = municipio.rename(
        columns={
            "nom_municipio": "municipio",
        }
    )

    edad = edad.rename(
        columns={
            "desc_edad": "edad_descripcion",
        }
    )

    # Enriquecer ubicación y edad.
    df = atus.merge(
        entidad[["id_entidad", "entidad"]],
        on="id_entidad",
        how="left",
        validate="many_to_one",
    )

    df = df.merge(
        municipio[["id_entidad", "id_municipio", "municipio"]],
        on=["id_entidad", "id_municipio"],
        how="left",
        validate="many_to_one",
    )

    df = df.merge(
        edad[["id_edad", "edad_descripcion"]],
        on="id_edad",
        how="left",
        validate="many_to_one",
    )

    # Limpieza de textos.
    text_columns = [
        "cobertura",
        "entidad",
        "municipio",
        "tipaccid",
        "causaacci",
        "clasacc",
        "urbana",
        "suburbana",
        "caparod",
        "estatus",
        "sexo",
        "aliento",
        "cinturon",
        "edad_descripcion",
    ]

    df = clean_text_columns(df, text_columns)

    # Convertir numéricos.
    numeric_columns = (
        ["anio", "mes", "id_dia", "id_hora", "id_minuto", "id_edad"]
        + list(VEHICULOS_MAP.keys())
        + list(PERSONAS_MAP.keys())
    )

    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Construir fecha real y date_key.
    df["full_date"] = pd.to_datetime(
        {
            "year": df["anio"],
            "month": df["mes"],
            "day": df["id_dia"],
        },
        errors="coerce",
    )

    if df["full_date"].isna().any():
        invalid_dates = df[df["full_date"].isna()].shape[0]
        raise ValueError(f"Hay {invalid_dates} registros con fecha inválida.")

    df["date_key"] = df["full_date"].dt.strftime("%Y%m%d").astype(int)

    # Construir time_key en formato HHMM.
    valid_time = (
        df["id_hora"].between(0, 23)
        & df["id_minuto"].between(0, 59)
    )

    df["time_key"] = -1
    df.loc[valid_time, "time_key"] = (
        df.loc[valid_time, "id_hora"] * 100
        + df.loc[valid_time, "id_minuto"]
    )

    return df


def build_dimensions(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Construye las dimensiones derivadas desde ATUS."""
    dim_ubicacion = (
        df[
            [
                "id_entidad",
                "entidad",
                "id_municipio",
                "municipio",
                "cobertura",
            ]
        ]
        .drop_duplicates()
        .sort_values(["id_entidad", "id_municipio", "cobertura"])
        .reset_index(drop=True)
    )

    dim_accidente = (
        df[
            [
                "tipaccid",
                "causaacci",
                "clasacc",
                "urbana",
                "suburbana",
                "caparod",
                "estatus",
            ]
        ]
        .drop_duplicates()
        .rename(
            columns={
                "tipaccid": "tipo_accidente",
                "causaacci": "causa_accidente",
                "clasacc": "clasificacion",
                "urbana": "zona_urbana",
                "suburbana": "zona_suburbana",
                "caparod": "capa_rodamiento",
            }
        )
        .sort_values(
            [
                "tipo_accidente",
                "causa_accidente",
                "clasificacion",
                "zona_urbana",
                "zona_suburbana",
                "capa_rodamiento",
                "estatus",
            ]
        )
        .reset_index(drop=True)
    )

    dim_conductor = (
        df[
            [
                "sexo",
                "id_edad",
                "edad_descripcion",
                "aliento",
                "cinturon",
            ]
        ]
        .drop_duplicates()
        .rename(
            columns={
                "aliento": "aliento_alcoholico",
                "cinturon": "cinturon_seguridad",
            }
        )
        .sort_values(
            [
                "sexo",
                "id_edad",
                "edad_descripcion",
                "aliento_alcoholico",
                "cinturon_seguridad",
            ]
        )
        .reset_index(drop=True)
    )

    logger.info("dim_ubicacion: %s filas", f"{len(dim_ubicacion):,}")
    logger.info("dim_accidente: %s filas", f"{len(dim_accidente):,}")
    logger.info("dim_conductor: %s filas", f"{len(dim_conductor):,}")

    return dim_ubicacion, dim_accidente, dim_conductor


def load_dimension(df: pd.DataFrame, table_name: str, engine, chunksize: int):
    """Carga una dimensión a PostgreSQL."""
    logger.info("Cargando %s: %s filas", table_name, f"{len(df):,}")

    n_chunks = (len(df) + chunksize - 1) // chunksize

    for i in tqdm(range(n_chunks), desc=f"  {table_name}"):
        chunk = df.iloc[i * chunksize:(i + 1) * chunksize]

        chunk.to_sql(
            table_name,
            engine,
            schema="atus_dwh",
            if_exists="append",
            index=False,
            method="multi",
        )


def resolve_keys(df: pd.DataFrame, engine) -> pd.DataFrame:
    """Sustituye llaves naturales por surrogate keys desde PostgreSQL."""
    logger.info("Resolviendo surrogate keys")

    dim_ubicacion = pd.read_sql(
        text("""
            SELECT
                ubicacion_key,
                id_entidad,
                entidad,
                id_municipio,
                municipio,
                cobertura
            FROM atus_dwh.dim_ubicacion
        """),
        engine,
    )

    dim_accidente = pd.read_sql(
        text("""
            SELECT
                accidente_key,
                tipo_accidente,
                causa_accidente,
                clasificacion,
                zona_urbana,
                zona_suburbana,
                capa_rodamiento,
                estatus
            FROM atus_dwh.dim_accidente
        """),
        engine,
    )

    dim_conductor = pd.read_sql(
        text("""
            SELECT
                conductor_key,
                sexo,
                id_edad,
                edad_descripcion,
                aliento_alcoholico,
                cinturon_seguridad
            FROM atus_dwh.dim_conductor
        """),
        engine,
    )

    fact = df.merge(
        dim_ubicacion,
        on=[
            "id_entidad",
            "entidad",
            "id_municipio",
            "municipio",
            "cobertura",
        ],
        how="left",
        validate="many_to_one",
    )

    fact = fact.rename(
        columns={
            "tipaccid": "tipo_accidente",
            "causaacci": "causa_accidente",
            "clasacc": "clasificacion",
            "urbana": "zona_urbana",
            "suburbana": "zona_suburbana",
            "caparod": "capa_rodamiento",
            "aliento": "aliento_alcoholico",
            "cinturon": "cinturon_seguridad",
        }
    )

    fact = fact.merge(
        dim_accidente,
        on=[
            "tipo_accidente",
            "causa_accidente",
            "clasificacion",
            "zona_urbana",
            "zona_suburbana",
            "capa_rodamiento",
            "estatus",
        ],
        how="left",
        validate="many_to_one",
    )

    fact = fact.merge(
        dim_conductor,
        on=[
            "sexo",
            "id_edad",
            "edad_descripcion",
            "aliento_alcoholico",
            "cinturon_seguridad",
        ],
        how="left",
        validate="many_to_one",
    )

    null_keys = fact[
        ["ubicacion_key", "accidente_key", "conductor_key"]
    ].isna().sum()

    if null_keys.sum() > 0:
        raise ValueError(f"Hay llaves nulas después del merge:\n{null_keys}")

    # Renombrar columnas de medidas para que coincidan con el DDL.
    fact = fact.rename(columns={**VEHICULOS_MAP, **PERSONAS_MAP})

    fact["num_accidentes"] = 1

    fact_columns = [
        "source_row_id",
        "date_key",
        "time_key",
        "ubicacion_key",
        "accidente_key",
        "conductor_key",
        "num_accidentes",
        "automovil",
        "campasaj",
        "microbus",
        "pascamion",
        "omnibus",
        "tranvia",
        "camioneta",
        "camion",
        "tractor",
        "ferrocarril",
        "motocicleta",
        "bicicleta",
        "otro_vehiculo",
        "conductor_muerto",
        "conductor_herido",
        "pasajero_muerto",
        "pasajero_herido",
        "peaton_muerto",
        "peaton_herido",
        "ciclista_muerto",
        "ciclista_herido",
        "otro_muerto",
        "otro_herido",
        "total_muertos",
        "total_heridos",
    ]

    return fact[fact_columns].copy()


# =============================================================================
# Load
# =============================================================================

def reset_etl_tables(engine):
    """Limpia tablas cargadas por el ETL para hacer la carga idempotente."""
    logger.info("Limpiando tablas ETL")

    with engine.begin() as conn:
        conn.execute(
            text("""
                TRUNCATE TABLE
                    atus_dwh.fact_accidentes,
                    atus_dwh.dim_ubicacion,
                    atus_dwh.dim_accidente,
                    atus_dwh.dim_conductor
                RESTART IDENTITY CASCADE
            """)
        )


def load_fact(df: pd.DataFrame, engine, chunksize: int):
    """Carga la tabla de hechos por chunks."""
    logger.info("Cargando fact_accidentes: %s filas", f"{len(df):,}")

    n_chunks = (len(df) + chunksize - 1) // chunksize

    dtype = {
        "source_row_id": BigInteger(),
        "date_key": Integer(),
        "time_key": SmallInteger(),
        "ubicacion_key": Integer(),
        "accidente_key": Integer(),
        "conductor_key": Integer(),
        "num_accidentes": SmallInteger(),
        "automovil": SmallInteger(),
        "campasaj": SmallInteger(),
        "microbus": SmallInteger(),
        "pascamion": SmallInteger(),
        "omnibus": SmallInteger(),
        "tranvia": SmallInteger(),
        "camioneta": SmallInteger(),
        "camion": SmallInteger(),
        "tractor": SmallInteger(),
        "ferrocarril": SmallInteger(),
        "motocicleta": SmallInteger(),
        "bicicleta": SmallInteger(),
        "otro_vehiculo": SmallInteger(),
        "conductor_muerto": SmallInteger(),
        "conductor_herido": SmallInteger(),
        "pasajero_muerto": SmallInteger(),
        "pasajero_herido": SmallInteger(),
        "peaton_muerto": SmallInteger(),
        "peaton_herido": SmallInteger(),
        "ciclista_muerto": SmallInteger(),
        "ciclista_herido": SmallInteger(),
        "otro_muerto": SmallInteger(),
        "otro_herido": SmallInteger(),
        "total_muertos": SmallInteger(),
        "total_heridos": SmallInteger(),
    }

    for i in tqdm(range(n_chunks), desc="  fact_accidentes"):
        chunk = df.iloc[i * chunksize:(i + 1) * chunksize]

        chunk.to_sql(
            "fact_accidentes",
            engine,
            schema="atus_dwh",
            if_exists="append",
            index=False,
            method="multi",
            dtype=dtype,
        )


def load(dim_ubicacion, dim_accidente, dim_conductor, df_base, engine, chunksize: int):
    """Carga dimensiones derivadas y tabla de hechos."""
    reset_etl_tables(engine)

    load_dimension(dim_ubicacion, "dim_ubicacion", engine, chunksize)
    load_dimension(dim_accidente, "dim_accidente", engine, chunksize)
    load_dimension(dim_conductor, "dim_conductor", engine, chunksize)

    fact = resolve_keys(df_base, engine)
    load_fact(fact, engine, chunksize)


# =============================================================================
# Validate
# =============================================================================

def validate(engine, expected_rows: int):
    """Validaciones post-carga."""
    logger.info("Validaciones post-carga")

    resumen = pd.read_sql(
        text("""
            SELECT
                COUNT(*) AS total_accidentes,
                SUM(total_muertos) AS total_muertos,
                SUM(total_heridos) AS total_heridos,
                SUM(automovil) AS total_automoviles,
                SUM(motocicleta) AS total_motocicletas,
                SUM(bicicleta) AS total_bicicletas
            FROM atus_dwh.fact_accidentes
        """),
        engine,
    )

    logger.info("Resumen general:\n%s", resumen.to_string(index=False))

    total_accidentes = int(resumen.loc[0, "total_accidentes"])

    if total_accidentes != expected_rows:
        raise AssertionError(
            f"Se esperaban {expected_rows:,} filas, "
            f"pero se cargaron {total_accidentes:,}."
        )

    nulls = pd.read_sql(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE date_key IS NULL) AS date_key_nulls,
                COUNT(*) FILTER (WHERE time_key IS NULL) AS time_key_nulls,
                COUNT(*) FILTER (WHERE ubicacion_key IS NULL) AS ubicacion_key_nulls,
                COUNT(*) FILTER (WHERE accidente_key IS NULL) AS accidente_key_nulls,
                COUNT(*) FILTER (WHERE conductor_key IS NULL) AS conductor_key_nulls
            FROM atus_dwh.fact_accidentes
        """),
        engine,
    )

    logger.info("Llaves nulas:\n%s", nulls.to_string(index=False))

    if nulls.sum(axis=1).iloc[0] != 0:
        raise AssertionError("Hay llaves nulas en fact_accidentes.")

    checks = pd.read_sql(
        text("""
            SELECT
                du.entidad,
                SUM(fa.num_accidentes) AS accidentes,
                SUM(fa.total_muertos) AS muertos,
                SUM(fa.total_heridos) AS heridos
            FROM atus_dwh.fact_accidentes fa
            JOIN atus_dwh.dim_ubicacion du USING (ubicacion_key)
            GROUP BY du.entidad
            ORDER BY accidentes DESC
            LIMIT 10
        """),
        engine,
    )

    logger.info("Top 10 entidades por accidentes:\n%s", checks.to_string(index=False))

    logger.info("✓ Validaciones completadas correctamente")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--database", default="northwind")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--data-dir", default="data/raw")
    parser.add_argument("--chunksize", type=int, default=10000)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    data_dir = Path(args.data_dir)

    url = URL.create(
        drivername="postgresql+psycopg2",
        username=args.user,
        password=args.password,
        host=args.host,
        port=args.port,
        database=args.database,
    )

    engine = create_engine(url)

    try:
        data = extract(data_dir)
        df_base = build_base_dataframe(data)
        dim_ubicacion, dim_accidente, dim_conductor = build_dimensions(df_base)

        load(
            dim_ubicacion=dim_ubicacion,
            dim_accidente=dim_accidente,
            dim_conductor=dim_conductor,
            df_base=df_base,
            engine=engine,
            chunksize=args.chunksize,
        )

        validate(engine, expected_rows=len(df_base))

        logger.info("ETL completado correctamente")

    except Exception as exc:
        logger.exception("ETL falló: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()