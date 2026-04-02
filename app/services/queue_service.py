from azure.storage.queue import QueueServiceClient
import json
from app.config import AZURE_STORAGE_CONNECTION_STRING, QUEUE_NAME


def get_queue_client():
    """Obtiene el cliente de la cola, creándola si no existe"""
    queue_service = QueueServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
    queue_client = queue_service.get_queue_client(QUEUE_NAME)
    try:
        queue_client.create_queue()
    except Exception:
        pass  # Ya existe
    return queue_client


def send_processing_message(job_id: str, blob_path: str):
    """Envía un mensaje a la cola indicando que hay un archivo por procesar"""
    queue_client = get_queue_client()
    message = json.dumps({
        "job_id": job_id,
        "blob_path": blob_path
    })
    queue_client.send_message(message)
