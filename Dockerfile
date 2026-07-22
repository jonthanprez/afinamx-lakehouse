# Usamos la misma imagen estable base que definimos en la arquitectura
FROM apache/airflow:3.2.2-python3.11

# Cambiamos temporalmente a root solo si necesitáramos dependencias del sistema (ej. gcc)
USER root

# Regresamos al usuario airflow (seguridad nativa de Airflow) para instalar paquetes de Python
USER airflow

# Copiamos e instalamos el requirements compilado por tus pip-tools
COPY requirements.txt /opt/airflow/requirements.txt
RUN pip install --no-cache-dir -r /opt/airflow/requirements.txt
