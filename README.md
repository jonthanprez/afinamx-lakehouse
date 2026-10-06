# AfinaMX - Lakehouse End-to-End 🚀

Este proyecto implementa una arquitectura Data Lakehouse parametrizable y modular bajo la filosofía **Local-First**. Esto permite desarrollar y probar pipelines completos de Ingeniería de Datos localmente a costo $0 (usando Docker, DuckDB y Pandas) y, mediante un switch de configuración, conmutar el cómputo y almacenamiento para desplegarse en producción sobre AWS (S3, Glue, Athena, PySpark).

---

## 1. Arquitectura de Contenedores (Docker) 🐳

El proyecto utiliza `docker-compose.yml` para orquestar los distintos servicios locales. Hemos diseñado la infraestructura separando las bases de datos transaccionales de las analíticas y de orquestación.

### Descripción de los Servicios:
* **`postgres-airflow`**: Base de datos interna (Metastore) exclusiva para el funcionamiento de Airflow. Funciona en el puerto `5432` interno.
* **`postgres-ecommerce`**: Contenedor que simula nuestra primera fuente de datos transaccional (WooCommerce). Está mapeado al puerto `5434` de tu PC local, por lo que puedes inspeccionarlo externamente usando clientes como DBeaver o DataGrip.
* **`airflow-init`**: Servicio efímero de inicialización. Ejecuta las migraciones de la base de datos nativas de Airflow 3 y crea el usuario administrador de forma automática, terminando su ejecución una vez listo.
* **`airflow-webserver`**: Interfaz de usuario web de Airflow (basada en React). Expuesta en el puerto `8080` de tu máquina local.
* **`airflow-scheduler`**: El "cerebro" del orquestador, encargado de monitorizar y lanzar las tareas (DAGs) basándose en sus dependencias.

---

## 2. Gestión del Ciclo de Vida (Comandos Docker) ⚙️

Para operar este ecosistema de desarrollo, utiliza los siguientes comandos en tu terminal desde la raíz del proyecto:

* **Iniciar los contenedores en segundo plano:**
  ```bash
  docker compose up -d
  ```

* **Forzar la reconstrucción de la imagen (usar cuando se modifiquen las librerías de Python):**
  ```bash
  docker compose build
  ```
  *O para reconstruir y levantar en un solo paso:*
  ```bash
  docker compose up -d --build
  ```

* **Detener los contenedores:**
  ```bash
  docker compose down
  ```

* **Eliminar contenedores y VOLÚMENES:**
  ⚠️ **Precaución:** Esto borrará la base de datos de metadatos de Airflow y los datos de WooCommerce almacenados en Docker.
  ```bash
  docker compose down -v
  ```

---

## 3. Gestión de Dependencias y Librerías en Airflow 📦

### El Problema
La variable nativa de Airflow `_PIP_ADDITIONAL_REQUIREMENTS` descarga las librerías cada vez que el contenedor se reinicia, volviendo el levantamiento local extremadamente lento. Además, herramientas tradicionales como `pip-tools` tardan decenas de segundos en resolver dependencias.

### La Solución Arquitectónica
En nuestra arquitectura hemos adoptado **`uv`** (el gestor ultrarrápido en Rust de Astral) junto con el estándar moderno **PEP 621 (`pyproject.toml`)**.
La imagen se compila localmente mediante el `Dockerfile` inyectando el binario oficial de `uv`, aprovechando tanto las capas de caché de Docker como la velocidad extrema de resolución e instalación.

### ¿Cómo agregar una nueva librería a Airflow sin tiempos de espera infinitos?
No edites directamente archivos de bloqueo. Sigue este flujo simple con `uv`:

1. **Para librerías de producción / Airflow:**
   Agrega la nueva librería con `uv` (esto actualizará automáticamente `pyproject.toml` y `uv.lock` en milisegundos):
   ```bash
   uv add boto3
   ```

2. **Para librerías de desarrollo o pruebas locales:**
   ```bash
   uv add --group dev pytest-mock
   ```

3. **Sincronizar tu entorno virtual local (`.venv/`):**
   ```bash
   uv sync
   ```

4. **Reconstruir tu imagen de Airflow en Docker:**
   ```bash
   docker compose build
   ```
   *O bien, directamente:*
   ```bash
   docker compose up -d --build
   ```

### ¿Por qué esto es más rápido?
* **10x - 100x más rápido:** `uv` resuelve e instala dependencias en cuestión de milisegundos.
* **Caché de Docker optimizada:** Al inyectar el binario compilado de `uv` en el `Dockerfile` y copiar `pyproject.toml` y `uv.lock`, Docker salta la instalación si no cambiaron las dependencias y, si cambian, las instala en segundos apuntando al entorno de Airflow (`/home/airflow/.local`).

---

## 4. Reglas de Oro de Seguridad 🔒

* **Sin secretos en Git:** Bajo ninguna circunstancia se deben hacer commits de secretos, contraseñas o tokens a Git.
* **Configuración Base:** Clona el archivo `.env.example` y renómbralo a `.env` (este archivo está en el `.gitignore` y nunca subirá al repositorio):
  ```bash
  cp .env.example .env
  ```
* **Conexiones de Airflow:** Prohibido definir secretos en los archivos `.py` de los DAGs. En lugar de eso, inyectamos las conexiones directamente mediante variables de entorno en el `.env` (por ejemplo, `AIRFLOW_CONN_POSTGRES_WOOCOMMERCE` y `AIRFLOW_CONN_AWS_DEFAULT`), las cuales son leídas de forma segura por el orquestador.

---

## 5. Calidad de Código, Seguridad y CI/CD (Quality Gates) 🛡️

Este repositorio implementa un enfoque de **Seguridad a la Izquierda (*Shift-Left Security*)** y control de calidad en 3 niveles para asegurar que solo código limpio, libre de secretos y funcional se fusione en la rama principal (`main`).

---

### 5.1. Herramientas de Estandarización y Linting

| Herramienta | Función | Alcance |
| :--- | :--- | :--- |
| **uv** | Gestor de paquetes, entornos virtuales y ejecución de herramientas en Rust. | Resuelve dependencias, sincroniza el entorno y ejecuta linters/tests (`uv run`). |
| **Ruff** | Linter y formateador ultrarrápido para Python (sustituye Flake8, Isort, Black, Bandit). | Formateo estricto, sintaxis, importaciones no usadas y reglas de estilo en todo el repositorio. |
| **Gitleaks** | Detector automatizado de secretos e API Keys. | Previene la fuga accidental de credenciales al historial de Git. |
| **Pytest** | Framework de pruebas unitarias y de integración. | Ejecuta la validación de integridad de DAGs y la suite completa de pruebas del motor de ingesta. |

---

### 5.2. Flujo de Trabajo Local (Pre-Commit Hooks)

Antes de que un `git commit` sea confirmado en tu máquina, **`pre-commit`** ejecuta automáticamente las herramientas de formateo y escaneo estático localmente.

#### Configuración e instalación inicial (solo una vez):
```bash
# 1. Instalar y sincronizar dependencias de desarrollo con uv
uv sync

# 2. Activar los hooks de Git en el proyecto
uv run pre-commit install
```

#### Ejecución manual (opcional):
Si deseas formatear o validar todo el proyecto sin hacer un commit:
```bash
uv run pre-commit run --all-files
```

---

### 5.3. Estrategia y Suite de Pruebas Automatizadas (pytest) 🧪

El proyecto cuenta con una pirámide de pruebas automatizadas con aislamiento total del sistema de archivos, garantizando que el código sea confiable y reproducible tanto en local como en CI/CD:

```text
tests/
├── conftest.py                             # Fixtures globales, aislamiento de rutas y mocks de AWS/Dominio
├── test_dag_validation.py                  # Pruebas de integridad y carga de DAGs de Airflow (DagBag)
├── unit/                                   # Pruebas Unitarias Aisladas
│   └── ingest/
│       ├── test_config.py                  # Resolución dinámica de rutas (DEV vs PROD S3)
│       ├── test_local_writer.py            # Escrituras atómicas (.tmp -> .json) y estructura de carpetas
│       ├── test_s3_writer.py               # Subida a S3 con boto3 y manejo de excepciones
│       ├── test_storage_factory.py         # Factory pattern y resolución de StorageWriter
│       ├── test_state_manager.py           # Checkpointing, persistencia y recuperación de estado corrupto
│       └── test_api_client.py              # Cliente API, rate limiting y disparo de Circuit Breaker
└── integration/                            # Pruebas de Integración End-to-End
    └── ingest/
        ├── test_simulator_to_storage.py    # Pipeline E2E: Simulator -> Client -> Writer con particionado Hive
        └── test_state_persistence.py       # Checkpointing multi-lote, continuidad de IDs y ciclo del Circuit Breaker
```

#### Capas de Prueba:
1. **Aislamiento del Entorno y Fixtures Globales (`conftest.py`):**
   * **Redirección de Almacenamiento:** Mediante la fixture `mock_lakehouse_dirs`, todas las operaciones de escritura de las pruebas se redirigen a directorios temporales efímeros (`tmp_path`), garantizando que ninguna prueba altere los datos locales reales (`./data/`).
   * **Mocks de AWS y Entorno:** Inyecta automáticamente credenciales falsas de AWS y fuerza `ENVIRONMENT=dev`.
   * **Payloads Tipados:** Provee fixtures tipadas (`mock_customer`, `mock_line_item`, `mock_order`) conformes a los modelos del dominio.

2. **Pruebas Unitarias (`tests/unit/ingest/`):**
   * Valida componentes individuales en aislamiento: cálculo de rutas, escrituras atómicas en disco, subidas mockeadas a S3, instanciación por factoría y manejo de errores de conexión.

3. **Pruebas de Integración (`tests/integration/ingest/`):**
   * **Flujo E2E:** Verifica la cadena completa `DataSimulator` $\rightarrow$ `WooCommerceAPIClient` $\rightarrow$ `LocalStorageWriter`.
   * **Particionado Hive:** Valida la creación exacta de particiones temporales (`year=YYYY/month=MM/batch_orders_X_to_Y.json`).
   * **Continuidad de Lotes e Idempotencia:** Confirma que ejecuciones consecutivas incrementen el cursor de pedidos sin duplicados ni pérdida de eventos.
   * **Resiliencia de Circuit Breaker:** Prueba la apertura del interruptor tras fallos reiterados y su posterior recuperación ante respuestas exitosas.

4. **Integridad de DAGs (`tests/test_dag_validation.py`):**
   * Asegura que los DAGs carguen limpiamente en la `DagBag` de Airflow sin ciclos ni errores de importación.

#### Comandos de Ejecución de Pruebas:

##### Opción A: Pruebas unitarias ultrarrápidas en local (Sin levantar Docker ⚡)
Para desarrollar lógica de negocio y probar el motor de ingesta sin consumir RAM de contenedores:
```bash
# Ejecutar todas las pruebas unitarias locales (70+ tests en < 0.5s)
uv run pytest tests/unit/ -v

# Validar formato y linter
uv run ruff check .
```

##### Opción B: Pruebas dentro del contenedor de Airflow (Hermético)
Para probar dentro del entorno exacto de los contenedores o validar los DAGs con Airflow cargado:
```bash
# 1. Ejecutar la suite completa de pruebas
docker compose exec airflow-webserver pytest tests/ -v

# 2. Ejecutar únicamente las pruebas unitarias del motor de ingesta
docker compose exec airflow-webserver pytest tests/unit/ingest/ -v

# 3. Ejecutar únicamente las pruebas de integración E2E
docker compose exec airflow-webserver pytest tests/integration/ingest/ -v

# 4. Validar únicamente la integridad de los DAGs de Airflow
docker compose exec airflow-webserver pytest tests/test_dag_validation.py -v
```

> **Nota:** La carpeta `./tests` está mapeada como un volumen dinámico dentro de Docker en `/opt/airflow/tests`, permitiendo probar cambios en vivo sin reconstruir la imagen.

---

### 5.4. Integración Continua en la Nube (GitHub Actions)

Al abrir un Pull Request (PR) o hacer push hacia `main` o `master`, el pipeline de GitHub Actions (`.github/workflows/ci.yml`) ejecuta dos jobs en paralelo:

- **`code-quality-and-security`**:
  - Valida formato estricto con `ruff format --check .`
  - Ejecuta el linter con `ruff check .`
  - Escanea el historial de commits y credenciales con `gitleaks`.
- **`dag-integrity-testing`**:
  - Levanta un entorno efímero con Python 3.11 y Apache Airflow.
  - Ejecuta la suite completa de `pytest tests/ -v` (DAGs, pruebas unitarias y de integración).

---

### 5.5. Comandos Útiles de Mantenimiento de Contenedores ⚡

| Acción | Comando | Impacto |
| :--- | :--- | :--- |
| **Pausar jornada** | `docker compose stop` | Detiene procesos liberando CPU y RAM. Mantiene estado exacto. |
| **Reanudar jornada** | `docker compose start` | Arranca los contenedores en 3 segundos. |
| **Liberar recursos** | `docker compose down` | Elimina contenedores y redes. Preserva bases de datos en `docker_volumes/`. |
| **Recrear por cambios en Compose** | `docker compose up -d` | Aplica nuevos volúmenes/variables reconfigurando solo los servicios cambiados. |

---

## 6. Motor de Ingesta - Capa Bronze (`src/ingest/`) 📥

### 6.1. Resumen Ejecutivo y Visión General de la Arquitectura
El módulo `src/ingest` actúa como el **Bronze Layer Engine** para el Lakehouse. Se encarga de la extracción e ingesta de datos en bruto (*raw*) desde diversos sistemas fuente (WooCommerce, MercadoLibre, Amazon) y garantiza una transición transparente entre el desarrollo local y la producción en la nube mediante el patrón de arquitectura **Double Switch**.

#### Características Arquitectónicas Clave:
* **Switch de Entorno (DEV vs PROD):** Enruta sin fricciones los destinos de datos entre el disco local (`data/bronze/...`) y AWS S3 (`s3://<bucket>/bronze/...`) sin modificar el código de negocio.
* **Resiliencia y Tolerancia a Fallos:** Reintentos con *exponential backoff* integrados, estado persistente de *Circuit Breaker*, limitación de tasa (*rate limiting*) y manejo explícito de excepciones.
* **Particionamiento Estilo Hive:** Garantiza la persistencia de datos en bruto mediante rutas de particionamiento estandarizadas (`year=YYYY/month=MM/day=DD`).
* **Política Cero Secretos (*Zero Secrets Policy*):** Lee estrictamente desde configuraciones en tiempo de ejecución o instancias de conexión de Airflow, evitando credenciales en texto plano o referencias no gestionadas a `os.environ` dentro de las tareas de orquestación.

---

### 6.2. Estructura de Directorios
```text
src/ingest/
├── __init__.py               # Marcador de paquete
├── config.py                 # Rutas de almacenamiento dinámicas y configuración de entorno
├── exceptions.py             # Jerarquía de excepciones personalizadas
├── models.py                 # Dataclasses y TypedDicts para seguridad de tipos
├── storage/
│   ├── __init__.py           # Exportación de abstracciones
│   ├── base.py               # Clase Base Abstracta (ABC) para escritores de almacenamiento
│   ├── factory.py            # Implementación del patrón Factory para selección de almacenamiento
│   ├── local_writer.py       # DEV: Manejador de almacenamiento en disco local (escrituras atómicas)
│   └── s3_writer.py          # PROD: Manejador de almacenamiento en AWS S3 vía boto3
└── woocommerce/
    ├── __init__.py
    ├── api_client.py         # Orquestador principal y consumidor de API con wrapper de resiliencia
    ├── data_simulator.py     # Simulador de fuente local usando Faker y lógica transaccional
    ├── products.py           # Semilla de catálogo y constantes estáticas del dominio
    └── state_manager.py      # Checkpoint de estado para ingesta incremental
```

---

### 6.3. Módulos Core y Arquitectura de Componentes

#### `src/ingest/config.py`
Determina dinámicamente las raíces de ejecución basándose en la variable de entorno `ENVIRONMENT` (`dev` vs `prod`).
* **Modo DEV:** Resuelve rutas a instancias de `Path` locales apuntando a `/opt/airflow/data/`.
* **Modo PROD:** Genera prefijos de URI S3 explícitos (`s3://<bucket-name>/...`).

#### `src/ingest/exceptions.py`
Establece una jerarquía explícita de excepciones para que los DAGs y tareas puedan diferenciar entre reintentos de red, fallos de escritura en almacenamiento y violaciones irrecuperables de la API.

```text
IngestionError (Base)
 ├── StorageError
 └── WooCommerceError
      ├── WooCommerceCircuitBreakerError
      └── WooCommerceAPIError
```

#### `src/ingest/models.py`
Proporciona estructura estricta y tipado para las entidades del dominio (`Customer`, `LineItem`, `Order`, `SimulatorState`) utilizando `TypedDict` de Python y primitivas estándar de tipado.

#### `src/ingest/storage/` (Motor de Switch de Almacenamiento)
Implementa el patrón de diseño **Abstract Factory**:
* **`base.py`:** Define `BaseStorageWriter` forzando el contrato `write_json()`.
* **`local_writer.py`:** Escribe archivos JSON atómicamente en local utilizando archivos temporales para evitar lecturas parciales durante operaciones concurrentes.
* **`s3_writer.py`:** Carga payloads directamente a AWS S3 usando `boto3`.
* **`factory.py`:** Inspecciona `config.ENVIRONMENT` para instanciar dinámicamente `LocalStorageWriter` o `S3StorageWriter`.

#### `src/ingest/woocommerce/` (*Vertical Slice*: Sistema Fuente)
* **`api_client.py`:** Integra adaptadores de reintento (`HTTPAdapter`, `Retry`), búsquedas de cursor de estado y verificaciones de *Circuit Breaker*. Soporta operación en modo dual (consultando endpoints de API en vivo o utilizando `data_simulator.py`).
* **`state_manager.py`:** Gestiona checkpoints de cursor (`last_order_id`, `last_updated_at`) almacenados en `metadata/` para garantizar cargas por lotes incrementales e idempotentes.
* **`data_simulator.py`:** Genera pedidos transaccionales sintéticos y realistas enfocados en atributos del dominio de e-commerce mexicano usando `Faker("es_MX")`.

---

### 6.4. Decisiones Arquitectónicas y Justificación

#### ¿Por qué usar una Fábrica Abstracta de Almacenamiento (*Abstract Storage Factory*)?
Codificar directamente la escritura de archivos o llamadas a `boto3` dentro de los DAGs o clientes de API genera un acoplamiento estricto con proveedores de la nube. Al desacoplar el almacenamiento mediante `StorageWriterFactory` y `BaseStorageWriter`:
* La ejecución local incurre en **$0 costo operativo** y cero latencia.
* El despliegue a producción requiere **cero modificaciones de código**—únicamente cambiar la bandera de configuración (`ENVIRONMENT=prod`).
* Las pruebas unitarias son rápidas y confiables porque las pruebas locales no dependen de *mocks* de AWS ni de acceso a internet.

#### ¿Por qué implementar *Circuit Breakers* y *State Managers* personalizados?
En ingestas de e-commerce reales, las APIs de terceros frecuentemente fallan o aplican límites de tasa (*rate limit*) durante picos de tráfico.
* El **State Manager** asegura que si una ingesta falla a mitad de camino, la reejecución del trabajo reanudará precisamente desde el último checkpoint exitoso sin introducir eventos duplicados en la capa Bronze.
* El **Circuit Breaker** previene fallos en cascada y peticiones innecesarias a la API cuando el endpoint de destino sufre caídas prolongadas.
