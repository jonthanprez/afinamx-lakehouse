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
