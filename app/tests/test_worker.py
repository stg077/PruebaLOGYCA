import pytest
import io
from unittest.mock import patch, MagicMock, call
from psycopg2.extras import execute_values


class MockCursor:
    #Cursor simulado que registra las queries ejecutadas
    def __init__(self):
        self.queries = []
        self.inserted_data = []

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def close(self):
        pass


class MockConnection:
    #Conexión simulada a PostgreSQL
    def __init__(self):
        self.cursor_obj = MockCursor()
        self.committed = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed += 1

    def close(self):
        pass


# ---- Tests del procesamiento CSV ----

@patch("app.services.worker.execute_values")
def test_process_csv_inserta_correctamente(mock_execute_values):
    #Verifica que process_csv inserte datos correctamente usando execute_values
    from app.services.worker import process_csv

    conn = MockConnection()
    csv_content = "date,product_id,quantity,price\n2026-01-01,1001,5,10.00\n2026-01-02,1002,3,20.00\n"
    csv_stream = io.StringIO(csv_content)

    total = process_csv(csv_stream, "test-job-id", conn)

    assert total == 2
    # Verificar que execute_values fue llamado (inserción masiva)
    mock_execute_values.assert_called_once()


@patch("app.services.worker.execute_values")
def test_process_csv_calcula_total(mock_execute_values):
    #Verifica que el total se calcule correctamente (quantity * price)
    from app.services.worker import process_csv

    conn = MockConnection()
    csv_content = "date,product_id,quantity,price\n2026-01-01,1001,5,10.50\n"
    csv_stream = io.StringIO(csv_content)

    process_csv(csv_stream, "test-job-id", conn)

    # Obtener los datos que se pasaron a execute_values
    args = mock_execute_values.call_args
    batch = args[0][2]  # Tercer argumento posicional: los datos
    assert len(batch) == 1
    # batch[0] = (job_id, date, product_id, quantity, price, total)
    assert batch[0][5] == 52.50  # 5 * 10.50 = 52.50


@patch("app.services.worker.execute_values")
def test_process_csv_batch_grande(mock_execute_values):
    #Verifica que con muchas filas se hagan múltiples batches
    from app.services.worker import process_csv

    conn = MockConnection()

    # Crear CSV con 6000 filas (> BATCH_SIZE de 5000)
    lines = ["date,product_id,quantity,price"]
    for i in range(6000):
        lines.append(f"2026-01-01,{1000+i},1,10.00")
    csv_content = "\n".join(lines) + "\n"
    csv_stream = io.StringIO(csv_content)

    total = process_csv(csv_stream, "test-job-id", conn)

    assert total == 6000
    # Deben ser 2 llamadas a execute_values: una con 5000 y otra con 1000
    assert mock_execute_values.call_count == 2
    # Verificar que se hicieron commits por cada batch
    assert conn.committed >= 2


@patch("app.services.worker.execute_values")
def test_process_csv_stream_valida_header(mock_execute_values):
    #Verifica que process_csv_stream rechace CSVs con columnas inválidas
    from app.services.worker import process_csv_stream

    conn = MockConnection()

    # Crear un mock del blob stream con chunks
    bad_csv = b"nombre,apellido,edad\nJuan,Perez,30\n"
    mock_stream = MagicMock()
    mock_stream.chunks.return_value = iter([bad_csv])

    with pytest.raises(ValueError, match="CSV inválido"):
        process_csv_stream(mock_stream, "test-job-id", conn)


@patch("app.services.worker.execute_values")
def test_process_csv_stream_funciona(mock_execute_values):
    #Verifica que process_csv_stream procese correctamente un blob en chunks
    from app.services.worker import process_csv_stream

    conn = MockConnection()

    # Simular chunks del blob
    chunk1 = b"date,product_id,quantity,price\n2026-01-01,1001,2,15.00\n"
    chunk2 = b"2026-01-02,1002,3,20.00\n"
    mock_stream = MagicMock()
    mock_stream.chunks.return_value = iter([chunk1, chunk2])

    total = process_csv_stream(mock_stream, "test-job-id", conn)

    assert total == 2
    mock_execute_values.assert_called_once()


@patch("app.services.worker.execute_values")
def test_process_csv_filas_malformadas(mock_execute_values):
    #Verifica que filas malformadas se ignoren sin romper el proceso
    from app.services.worker import process_csv_stream

    conn = MockConnection()

    csv_data = b"date,product_id,quantity,price\n2026-01-01,1001,2,15.00\nbad,row\n2026-01-02,1002,3,20.00\n"
    mock_stream = MagicMock()
    mock_stream.chunks.return_value = iter([csv_data])

    total = process_csv_stream(mock_stream, "test-job-id", conn)

    # Solo 2 filas válidas, la malformada se ignora
    assert total == 2
