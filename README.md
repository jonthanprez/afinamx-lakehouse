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
La variable nativa de Airflow `_PIP_ADDITIONAL_REQUIREMENTS` descarga las librerías cada vez que el contenedor se reinicia, volviendo el levantamiento local extremadamente lento.

### La Solución Arquitectónica
En nuestra arquitectura hemos eliminado esa variable. En su lugar, hemos implementado una compilación de imagen local a través del `Dockerfile` aprovechando las capas de caché de Docker.

### ¿Cómo agregar una nueva librería a Airflow sin tiempos de espera infinitos?
No edites directamente el `requirements.txt`. El proyecto utiliza `pip-tools` para garantizar reproducibilidad en los entornos híbridos (Dev/Prod). Sigue este flujo vertical:

1. Agrega la nueva librería en el archivo `requirements.in` (ej. `boto3`).
2. Compila las dependencias exactas ejecutando en tu terminal local (requiere tener `pip-tools` instalado en tu entorno local):
   ```bash
   pip-compile requirements.in
   ```
   Esto generará automáticamente un `requirements.txt` seguro y unificado.
3. Reconstruye tu imagen de Airflow ejecutando:
   ```bash
   docker compose build
   ```
   o bien, directamente:
   ```bash
   docker compose up -d --build
   ```

### ¿Por qué esto es más rápido?
Al tener el comando `COPY requirements.txt` antes de instalar en el `Dockerfile`, Docker almacena el paso de instalación en su caché. Si reinicias los contenedores sin haber modificado `requirements.txt`, Docker saltará la instalación y tus contenedores arrancarán en segundos.

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
| **Ruff** | Linter ultrarrápido para Python (sustituye Flake8, Isort, Bandit). | Sintaxis, importaciones no usadas, calidad de código. |
| **Black** | Formateador estricto de código Python. | Estilo de código unificado en `dags/` y `plugins/`. |
| **Gitleaks** | Detector automatizado de secretos e API Keys. | Previene la fuga accidental de credenciales al historial de Git. |
| **Pytest** | Framework de pruebas unitarias. | Ejecuta pruebas de integridad de DAGs e importación en Airflow. |

---

### 5.2. Flujo de Trabajo Local (Pre-Commit Hooks)

Antes de que un `git commit` sea confirmado en tu máquina, **`pre-commit`** ejecuta automáticamente las herramientas de formateo y escaneo estático localmente.

#### Configuración e instalación inicial (solo una vez):
```bash
# 1. Instalar pre-commit en tu PC / entorno local
pip install pre-commit

# 2. Activar los hooks de Git en el proyecto
pre-commit install
```

#### Ejecución manual (opcional):
Si deseas formatear o validar todo el proyecto sin hacer un commit:
```bash
pre-commit run --all-files
```

---

### 5.3. Pruebas Unitarias de Integridad de Airflow (pytest)

Garantizamos que todos los DAGs sean legibles y estén libres de errores de sintaxis o dependencias faltantes ejecutando pytest dentro del entorno aislado de Docker:

```bash
# Ejecutar la suite de pruebas locales dentro del contenedor de Airflow
docker compose exec airflow-webserver pytest tests/ -v
```

> **Nota:** La carpeta `./tests` está mapeada como un volumen dinámico dentro de Docker en `/opt/airflow/tests`, permitiendo probar cambios en vivo.

---

### 5.4. Integración Continua en la Nube (GitHub Actions)

Al abrir un Pull Request (PR) hacia `main`, el pipeline de GitHub Actions (`.github/workflows/ci.yml`) ejecuta dos jobs en paralelo:

- **`code-quality-and-security`**:
  - Valida formato con `black --check .`
  - Corre el linter con `ruff check .`
  - Escanea el historial de commits con `gitleaks`.
- **`dag-integrity-testing`**:
  - Levanta un entorno efímero con Python 3.11 y Apache Airflow.
  - Ejecuta la suite de `pytest tests/` para validar la carga de la DagBag.

---

### 5.5. Comandos Útiles de Mantenimiento de Contenedores ⚡

| Acción | Comando | Impacto |
| :--- | :--- | :--- |
| **Pausar jornada** | `docker compose stop` | Detiene procesos liberando CPU y RAM. Mantiene estado exacto. |
| **Reanudar jornada** | `docker compose start` | Arranca los contenedores en 3 segundos. |
| **Liberar recursos** | `docker compose down` | Elimina contenedores y redes. Preserva bases de datos en `docker_volumes/`. |
| **Recrear por cambios en Compose** | `docker compose up -d` | Aplica nuevos volúmenes/variables reconfigurando solo los servicios cambiados. |
