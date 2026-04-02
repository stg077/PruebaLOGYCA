import json
import csv
import io
import time
from psycopg2.extras import execute_values
from azure.storage.queue import QueueServiceClient
from app.config import AZURE_STORAGE_CONNECTION_STRING, QUEUE_NAME, BATCH_SIZE, WORKER_POLL_INTERVAL
from app.services.blob_services_azure import download_blob_stream
from app.db.creacion_SQL import get_connection


def process_csv_stream(blob_stream, job_id: str, conn) -> int:
    """Procesa el CSV por chunks usando streaming + execute_values para inserción masiva.

    El blob se descarga en chunks de 4MB para no cargar todo en memoria.
    Las filas se insertan en lotes usando execute_values (un solo INSERT con
    múltiples VALUES), que es significativamente más rápido que executemany.

    Args:
        blob_stream: StorageStreamDownloader del blob
        job_id: ID del job para asociar los registros
        conn: Conexión a PostgreSQL

    Returns:
        Número total de filas insertadas
    """
    cursor = conn.cursor()
    batch = []
    total_rows = 0
    leftover = ""

    # Leer el blob en chunks de 4MB para no saturar la memoria
    chunks_iterator = blob_stream.chunks()
    header_parsed = False
    expected_columns = {"date", "product_id", "quantity", "price"}

    for chunk in chunks_iterator:
        text = leftover + chunk.decode("utf-8")
        lines = text.split("\n")
        # La última línea puede estar incompleta, la guardamos para el siguiente chunk
        leftover = lines[-1]
        lines = lines[:-1]

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Parsear y validar el header
            if not header_parsed:
                columns = {col.strip().lower() for col in line.split(",")}
                if not expected_columns.issubset(columns):
                    raise ValueError(
                        f"CSV inválido: se esperaban columnas {expected_columns}, "
                        f"se encontraron {columns}"
                    )
                header_parsed = True
                # Guardar el orden de columnas para el reader
                header_list = [col.strip().lower() for col in line.split(",")]
                continue

            # Parsear la fila
            values = line.split(",")
            if len(values) != len(header_list):
                continue  # Saltar filas malformadas

            row = dict(zip(header_list, values))

            try:
                quantity = int(row["quantity"])
                price = float(row["price"])
                total = round(quantity * price, 2)

                batch.append((
                    job_id,
                    row["date"].strip(),
                    int(row["product_id"]),
                    quantity,
                    price,
                    total
                ))
            except (ValueError, KeyError) as e:
                print(f"  Fila malformada ignorada: {line} -> {e}")
                continue

            if len(batch) >= BATCH_SIZE:
                _insert_batch(cursor, batch)
                conn.commit()
                total_rows += len(batch)
                print(f"  Insertadas {total_rows} filas...")
                batch = []

    # Procesar la última línea que quedó en leftover
    if leftover.strip() and header_parsed:
        values = leftover.strip().split(",")
        if len(values) == len(header_list):
            row = dict(zip(header_list, values))
            try:
                quantity = int(row["quantity"])
                price = float(row["price"])
                total = round(quantity * price, 2)
                batch.append((
                    job_id, row["date"].strip(), int(row["product_id"]),
                    quantity, price, total
                ))
            except (ValueError, KeyError):
                pass

    # Insertar el último lote
    if batch:
        _insert_batch(cursor, batch)
        conn.commit()
        total_rows += len(batch)

    cursor.close()
    return total_rows


def _insert_batch(cursor, batch: list):
    """Inserta un lote de filas usando execute_values (inserción masiva real).

    execute_values genera un solo INSERT con múltiples VALUES, por ejemplo:
    INSERT INTO sales (...) VALUES (row1), (row2), ..., (row5000)
    Esto es ~10x más rápido que executemany que ejecuta un INSERT por fila.
    """
    execute_values(
        cursor,
        """INSERT INTO sales (job_id, date, product_id, quantity, price, total)
           VALUES %s""",
        batch,
        page_size=BATCH_SIZE
    )


# Mantener compatibilidad: función legacy para los tests existentes
def process_csv(csv_stream: io.StringIO, job_id: str, conn) -> int:
    """Procesa un CSV desde un StringIO (usado en tests y compatibilidad).

    Para producción se usa process_csv_stream que trabaja con el blob directamente.
    """
    reader = csv.DictReader(csv_stream)
    batch = []
    total_rows = 0
    cursor = conn.cursor()

    for row in reader:
        quantity = int(row["quantity"])
        price = float(row["price"])
        total = round(quantity * price, 2)
        batch.append((job_id, row["date"], int(row["product_id"]), quantity, price, total))

        if len(batch) >= BATCH_SIZE:
            _insert_batch(cursor, batch)
            conn.commit()
            total_rows += len(batch)
            batch = []

    if batch:
        _insert_batch(cursor, batch)
        conn.commit()
        total_rows += len(batch)

    cursor.close()
    return total_rows


def process_queue_messages():
    """Escucha la cola y procesa los mensajes de forma continua"""
    queue_service = QueueServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    queue_client = queue_service.get_queue_client(QUEUE_NAME)

    # Crear la cola si no existe (puede arrancar antes que la API)
    try:
        queue_client.create_queue()
    except Exception:
        pass  # Ya existe

    print("Worker escuchando la cola...")

    while True:
        messages = queue_client.receive_messages(max_messages=1, visibility_timeout=300)

        for message in messages:
            conn = get_connection()
            cursor = conn.cursor()
            job_id = None
            try:
                data = json.loads(message.content)
                job_id = data["job_id"]
                blob_path = data["blob_path"]

                print(f"Procesando job: {job_id}")

                # Actualizar status a PROCESSING
                cursor.execute(
                    "UPDATE jobs SET status = 'PROCESSING', updated_at = NOW() WHERE id = %s",
                    (job_id,)
                )
                conn.commit()

                # Descargar como stream y procesar sin cargar en memoria
                blob_stream = download_blob_stream(blob_path)
                total = process_csv_stream(blob_stream, job_id, conn)

                # Actualizar status a COMPLETED
                cursor.execute(
                    "UPDATE jobs SET status = 'COMPLETED', updated_at = NOW() WHERE id = %s",
                    (job_id,)
                )
                conn.commit()
                print(f"Job {job_id} completado. {total} registros insertados.")

            except Exception as e:
                if job_id:
                    cursor.execute(
                        "UPDATE jobs SET status = 'FAILED', error_message = %s, updated_at = NOW() WHERE id = %s",
                        (str(e), job_id)
                    )
                    conn.commit()
                print(f"Error procesando job {job_id}: {e}")

            finally:
                queue_client.delete_message(message)
                cursor.close()
                conn.close()

        time.sleep(WORKER_POLL_INTERVAL)


if __name__ == "__main__":
    process_queue_messages()
