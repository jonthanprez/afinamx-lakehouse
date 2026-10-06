# Usamos la misma imagen estable base que definimos en la arquitectura
FROM apache/airflow:3.2.2-python3.11

# Cambiamos temporalmente a root solo si necesitáramos dependencias del sistema (ej. gcc)
USER root

# Copiamos el binario de uv desde la imagen oficial
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Regresamos al usuario airflow (seguridad nativa de Airflow) para instalar paquetes de Python
USER airflow

# Copiamos los archivos de definición del proyecto y lockfile
COPY pyproject.toml uv.lock /opt/airflow/

# Instalamos las dependencias principales (sin dev) en el entorno de Airflow
RUN uv export --no-dev --format requirements-txt -o /tmp/requirements.txt && \
    uv pip install --no-cache --python /home/airflow/.local/bin/python -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt
