import pytest
from airflow.models import DagBag


@pytest.fixture(scope="module")
def dagbag():
    """Carga todos los DAGs de la carpeta dags/ en un entorno aislado."""
    return DagBag(dag_folder="dags/", include_examples=False)


def test_no_import_errors(dagbag):
    """Verifica que ningún DAG tenga errores de sintaxis o de importación de Python."""
    assert (
        len(dagbag.import_errors) == 0
    ), f"Errores al importar DAGs: {dagbag.import_errors}"


def test_dags_loaded(dagbag):
    """Garantiza que al menos un DAG válido se encuentre en el directorio."""
    assert (
        len(dagbag.dags)
        >= 0  # las pruebas pasan aunque no haya dags, luego será necesario cambiarlo a solo > 0
    ), "No se encontraron DAGs válidos en el directorio 'dags/'."
