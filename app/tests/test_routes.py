import pytest
import io
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ---- Mock de la base de datos ----
class MockCursor:
    """Cursor simulado que almacena datos en memoria"""
    def __init__(self):
        self.rows = []
        self.last_query = None
        self.last_params = None

    def execute(self, query, params=None):
        self.last_query = query
        self.last_params = params

    def fetchone(self):
        if self.rows:
            return self.rows[0]
        return None

    def close(self):
        pass


class MockConnection:
    """Conexión simulada a PostgreSQL"""
    def __init__(self):
        self._cursor = MockCursor()

    def cursor(self, cursor_factory=None):
        return self._cursor

    def commit(self):
        pass

    def close(self):
        pass


def get_mock_db():
    conn = MockConnection()
    try:
        yield conn
    finally:
        conn.close()


# Sobreescribir la dependencia de DB en la app
from app.db.creacion_SQL import get_db
app.dependency_overrides[get_db] = get_mock_db


# ---- Tests de endpoints ----

def test_inicio():
    """Verifica que el health check funcione"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "CORRIENDO"


@patch("app.api.api_conexion.upload_to_blob_stream", return_value="csv-uploads/test.csv")
@patch("app.api.api_conexion.send_processing_message")
def test_upload_csv_valido(mock_queue, mock_blob):
    """Verifica que se pueda subir un CSV correctamente"""
    csv_content = "date,product_id,quantity,price\n2026-01-01,1001,2,10.5\n"
    file = io.BytesIO(csv_content.encode("utf-8"))

    response = client.post(
        "/upload",
        files={"file": ("test.csv", file, "text/csv")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "PENDING"
    # Verificar que se llamó al blob y a la cola
    mock_blob.assert_called_once()
    mock_queue.assert_called_once()


def test_upload_archivo_no_csv():
    """Verifica que rechace archivos que no son CSV"""
    file = io.BytesIO(b"contenido falso")

    response = client.post(
        "/upload",
        files={"file": ("test.txt", file, "text/plain")}
    )
    assert response.status_code == 400


@patch("app.api.api_conexion.upload_to_blob_stream", return_value="csv-uploads/test.csv")
@patch("app.api.api_conexion.send_processing_message")
def test_upload_csv_columnas_invalidas(mock_queue, mock_blob):
    """Verifica que rechace CSV con columnas incorrectas"""
    csv_content = "nombre,apellido,edad\nJuan,Perez,30\n"
    file = io.BytesIO(csv_content.encode("utf-8"))

    response = client.post(
        "/upload",
        files={"file": ("bad.csv", file, "text/csv")}
    )
    assert response.status_code == 400
    assert "columnas" in response.json()["detail"].lower()


def test_upload_archivo_vacio():
    """Verifica que rechace archivos vacíos"""
    file = io.BytesIO(b"")

    response = client.post(
        "/upload",
        files={"file": ("empty.csv", file, "text/csv")}
    )
    assert response.status_code == 400


def test_get_job_no_existente():
    """Verifica que devuelva 404 para un job que no existe"""
    response = client.get("/job/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
