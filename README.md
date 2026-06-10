# 🚗 Análisis de siniestralidad vial en México — ATUS 2024

> El objetivo del proyecto es construir un flujo completo de datos: desde los microdatos públicos del INEGI hasta un modelo dimensional en Aurora PostgreSQL, consultas analíticas y visualizaciones.

---

## 📋 Resumen ejecutivo

| Campo                  | Valor                                                                                                                                                                                                           |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Pregunta analítica** | ¿Cuáles son los patrones geográficos, temporales y de severidad de los accidentes viales registrados en México durante 2024, y qué factores se asocian con una mayor cantidad de personas heridas y fallecidas? |
| **Dataset**            | Microdatos anuales de Accidentes de Tránsito Terrestre en Zonas Urbanas y Suburbanas (ATUS), año 2024.                                                                                                          |
| **Fuente**             | [INEGI — Accidentes de Tránsito Terrestre en Zonas Urbanas y Suburbanas (ATUS)](https://www.inegi.org.mx/programas/accidentes/?ps=Microdatos)                                                                   |
| **Volumen**            | Aproximadamente 390 mil registros de accidentes viales.                                                                                                                                                         |
| **Modelo**             | Esquema estrella con 1 tabla de hechos y 5 dimensiones: fecha, tiempo, ubicación, accidente y conductor.                                                                                                        |
| **Infraestructura**    | Aurora PostgreSQL en AWS, schema `atus_dwh`.                                                                                                                                                                    |
| **ETL**                | Python con `pandas`, `SQLAlchemy` y validaciones post-carga.                                                                                                                                                    |
| **SQL avanzado**       | CTE, funciones de ventana, rankings, variaciones temporales, agregaciones condicionales y análisis de severidad.                                                                                                |
| **Dashboard**          | Visualizaciones estáticas con `matplotlib`: mapa, series temporales, rankings y heatmap por hora y día de la semana.                                                                                            |

---

## 🎯 Problema y motivación

Los accidentes viales constituyen un problema relevante para la movilidad y la seguridad pública. Analizar únicamente el número total de accidentes no permite identificar dónde, cuándo y bajo qué condiciones se presentan los eventos más severos.

El dataset ATUS del INEGI permite estudiar los accidentes viales desde distintas perspectivas:

* Ubicación geográfica.
* Fecha y horario.
* Tipo de accidente.
* Causa presunta.
* Perfil de la persona conductora.
* Cantidad y tipo de vehículos involucrados.
* Número de personas heridas y fallecidas.

Este proyecto busca transformar los microdatos en información útil para responder preguntas concretas:

1. **¿Qué entidades y municipios concentran la mayor cantidad de accidentes viales?**
2. **¿Existen patrones por mes, día de la semana y franja horaria?**
3. **¿Qué tipos de accidente presentan una mayor severidad?**
4. **¿Qué características del conductor aparecen con mayor frecuencia en accidentes con personas heridas o fallecidas?**
5. **¿Qué tipos de vehículos están involucrados con mayor frecuencia en los accidentes registrados?**

---

## 📦 Origen de los datos

Los datos provienen del programa estadístico ATUS del Instituto Nacional de Estadística y Geografía (INEGI).

El archivo principal utilizado es:

```text
atus_anual_2024.csv
```

Además, la descarga incluye catálogos auxiliares para enriquecer los datos:

```text
tc_entidad.csv
tc_municipio.csv
tc_periodo_mes.csv
tc_dia.csv
tc_hora.csv
tc_minuto.csv
tc_edad.csv
diccionario_de_datos_atus_anual_1997_2024.csv
```

Los CSV originales se almacenan localmente en:

```text
data/raw/
```

No se cargan al repositorio debido a su tamaño. El repositorio contiene únicamente código, documentación y visualizaciones generadas.

---

## 🔄 Flujo end-to-end

```text
┌──────────────────────────────────────────────┐
│ INEGI — Microdatos ATUS 2024                 │
│                                              │
│ • Archivo anual de accidentes                │
│ • Catálogos de entidad, municipio y tiempo   │
│ • Diccionario de datos                       │
└──────────────────────┬───────────────────────┘
                       │
                       │ Descarga desde portal público
                       ▼
┌──────────────────────────────────────────────┐
│ Archivos locales — data/raw/                 │
│                                              │
│ atus_anual_2024.csv                          │
│ tc_entidad.csv                               │
│ tc_municipio.csv                             │
│ tc_hora.csv                                  │
│ tc_minuto.csv                                │
│ tc_periodo_mes.csv                           │
│ tc_dia.csv                                   │
│ tc_edad.csv                                  │
└──────────────────────┬───────────────────────┘
                       │
                       │ ETL Python
                       ▼
┌──────────────────────────────────────────────┐
│ Transformación con pandas                    │
│                                              │
│ Extract:   lectura de CSVs                    │
│ Transform: limpieza, cruces y validaciones   │
│ Resolve:   generación de surrogate keys      │
│ Load:      carga con SQLAlchemy               │
└──────────────────────┬───────────────────────┘
                       │
                       │ INSERT
                       ▼
┌──────────────────────────────────────────────┐
│ Aurora PostgreSQL                            │
│ Schema: atus_dwh                             │
│                                              │
│ • 5 dimensiones                              │
│ • 1 tabla de hechos                          │
│ • Índices para consultas analíticas          │
└──────────────────────┬───────────────────────┘
                       │
                       │ SELECT
                       ▼
┌──────────────────────────────────────────────┐
│ SQL avanzado + dashboard                     │
│                                              │
│ • Rankings geográficos                       │
│ • Tendencias temporales                      │
│ • Análisis de severidad                      │
│ • Visualizaciones con matplotlib             │
└──────────────────────────────────────────────┘
```

---

## ⭐ Modelo dimensional

### Esquema estrella

```text
                         ┌────────────────────────────┐
                         │         dim_fecha          │
                         │────────────────────────────│
                         │ date_key PK                │
                         │ full_date                  │
                         │ anio                       │
                         │ trimestre                  │
                         │ mes_numero                 │
                         │ mes_nombre                 │
                         │ dia_mes                    │
                         │ dia_semana_nombre          │
                         │ es_fin_semana              │
                         └──────────────▲─────────────┘
                                        │
                                        │
┌────────────────────────────┐          │          ┌────────────────────────────┐
│       dim_ubicacion        │          │          │       dim_accidente       │
│────────────────────────────│          │          │────────────────────────────│
│ ubicacion_key PK           │◄─────────┼─────────►│ accidente_key PK          │
│ id_entidad                 │                     │ tipo_accidente             │
│ entidad                    │                     │ causa_accidente            │
│ id_municipio               │                     │ clasificacion              │
│ municipio                  │                     │ zona_urbana                │
│ cobertura                  │                     │ zona_suburbana             │
└────────────────────────────┘                     │ capa_rodamiento            │
                                                  └────────────────────────────┘
                                        │
                                        │
                         ┌──────────────▼─────────────┐
                         │      fact_accidentes       │
                         │────────────────────────────│
                         │ accidente_id PK            │
                         │ date_key FK                │
                         │ time_key FK                │
                         │ ubicacion_key FK           │
                         │ accidente_key FK           │
                         │ conductor_key FK           │
                         │ num_accidentes             │
                         │ total_muertos              │
                         │ total_heridos              │
                         │ automovil                  │
                         │ motocicleta                │
                         │ bicicleta                  │
                         │ camion                     │
                         │ camioneta                  │
                         └──────────────▲─────────────┘
                                        │
                ┌───────────────────────┴───────────────────────┐
                │                                               │
┌───────────────┴──────────────┐                ┌───────────────┴──────────────┐
│         dim_tiempo           │                │        dim_conductor         │
│──────────────────────────────│                │──────────────────────────────│
│ time_key PK                  │                │ conductor_key PK             │
│ hora                         │                │ sexo                         │
│ minuto                       │                │ id_edad                      │
│ hora_texto                   │                │ edad_descripcion             │
│ banda_horaria                │                │ aliento_alcoholico           │
└──────────────────────────────┘                │ cinturon_seguridad           │
                                                └──────────────────────────────┘
```

---

## 🧠 Decisiones de diseño

**Grano de la fact:** una fila por accidente vial registrado en ATUS. Este es el nivel más fino que provee el origen. Cada registro representa un evento ocurrido en una ubicación, fecha y horario determinados, junto con sus atributos de severidad, características del conductor y vehículos involucrados.

**Por qué `dim_tiempo` está separada de `dim_fecha`:** los patrones diarios y los patrones horarios responden a preguntas diferentes. La separación facilita analizar tendencias por mes o día de la semana, al mismo tiempo que permite agrupar por franja horaria sin reconstruir timestamps en cada consulta.

**Por qué `dim_ubicacion` integra entidad y municipio:** el municipio pertenece naturalmente a una entidad federativa. Ambos atributos se aplanan en una sola dimensión para simplificar las consultas geográficas y evitar una normalización innecesaria dentro del esquema estrella.

**Por qué `dim_accidente` concentra tipo, causa y clasificación:** estas variables describen la naturaleza del evento vial. Agruparlas en una dimensión facilita comparar frecuencia y severidad entre atropellamientos, colisiones, volcaduras y otros tipos de accidente.

**Por qué `dim_conductor` se mantiene separada:** variables como sexo, edad, aliento alcohólico y uso del cinturón corresponden al perfil de la persona conductora. Mantenerlas en una dimensión propia permite estudiar su relación con la severidad del accidente.

**Por qué los vehículos permanecen en la fact:** ATUS reporta los vehículos involucrados como conteos por accidente. Estas columnas son medidas aditivas, por lo que pueden agregarse directamente mediante `SUM()` sin crear una relación muchos-a-muchos adicional.

**Por qué se conserva la medida `num_accidentes`:** cada registro recibe el valor constante `1`. Esto permite calcular el total de accidentes con `SUM(num_accidentes)` y mantener consistencia con las demás métricas agregables.

**Por qué no se filtran los accidentes clasificados como “sólo daños”:** estos registros también forman parte de la siniestralidad vial. Excluirlos sesgaría el análisis al concentrarse únicamente en accidentes con personas heridas o fallecidas.

---

## 📂 Estructura del repositorio

```text
ATUS-2024-Siniestralidad-Vial/
├── README.md
├── .gitignore
│
├── data/
│   ├── raw/                         ← CSVs locales, excluidos de GitHub
│   └── processed/                   ← archivos intermedios, excluidos de GitHub
│
├── notebooks/
│   ├── 01_exploracion.ipynb         ← exploración inicial
│   └── 02_etl_desarrollo.ipynb      ← desarrollo del ETL
│
├── scripts/
│   ├── 01_schema_ddl.sql            ← creación del esquema estrella
│   └── etl_pipeline.py              ← ETL Python end-to-end
│
├── analisis/
│   └── queries_analiticas.sql       ← consultas con SQL avanzado
│
└── dashboard/
    ├── generar_visualizaciones.py   ← generación de gráficos
    └── img/
        ├── 01_mapa_accidentes.png
        ├── 02_serie_mensual.png
        ├── 03_top_municipios.png
        └── 04_heatmap_hora_dia.png
```

---

## 🔧 Cómo ejecutar

### 1. Instalar dependencias

```bash
pip install pandas sqlalchemy psycopg2-binary tqdm matplotlib
```

### 2. Crear el schema en Aurora PostgreSQL

Desde DBeaver, abre y ejecuta:

```text
scripts/01_schema_ddl.sql
```

También puedes ejecutarlo desde Terminal con `psql`:

```bash
psql "postgresql://postgres:TU_PASSWORD@TU_HOST:5432/TU_DATABASE" \
    -f scripts/01_schema_ddl.sql
```

Esto crea el schema:

```text
atus_dwh
```

con las tablas dimensionales y la tabla de hechos vacías.

### 3. Ejecutar el ETL

> Esta sección se completará cuando el archivo `etl_pipeline.py` esté listo.

El comando tendrá una estructura similar a:

```bash
python scripts/etl_pipeline.py \
    --host TU_HOST_AURORA \
    --password TU_PASSWORD \
    --database TU_DATABASE \
    --data-dir ./data/raw
```

### 4. Ejecutar consultas analíticas

Desde DBeaver, abre:

```text
analisis/queries_analiticas.sql
```

Las consultas incluirán:

* Ranking de entidades y municipios.
* Tendencias mensuales.
* Patrones por hora y día de la semana.
* Severidad por tipo de accidente.
* Comparaciones mediante funciones de ventana.

### 5. Generar visualizaciones

> Esta sección se completará cuando el script del dashboard esté listo.

```bash
python dashboard/generar_visualizaciones.py
```

---

## 📊 Visualizaciones planeadas

1. **Mapa de accidentes por entidad federativa.**
2. **Serie mensual de accidentes registrados.**
3. **Top de municipios con mayor número de accidentes.**
4. **Heatmap de accidentes por hora y día de la semana.**
5. **Severidad por tipo de accidente.**

---

## 🚧 Estado del proyecto

| Componente                          | Estado           |
| ----------------------------------- | ---------------- |
| Definición de la pregunta analítica | ✅ Completado     |
| Descarga de datos ATUS 2024         | ✅ Completado     |
| Organización del repositorio        | ✅ Completado     |
| Diseño del esquema estrella         | ✅ Completado     |
| Script DDL                          | 🟡 En desarrollo |
| Exploración inicial en Python       | 🟡 En desarrollo |
| ETL end-to-end                      | ⏳ Pendiente      |
| Consultas SQL avanzadas             | ⏳ Pendiente      |
| Visualizaciones                     | ⏳ Pendiente      |
| Documentación final                 | ⏳ Pendiente      |

---

## 👤 Autor

**Aldo Ramírez Alanís**

