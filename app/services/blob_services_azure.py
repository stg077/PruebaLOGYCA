from azure.storage.blob import BlobServiceClient
from app.config import AZURE_STORAGE_CONNECTION_STRING, BLOB_CONTAINER_NAME


def get_blob_service():
    return BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)


def _ensure_container(blob_service):#no la entiendo bien
    """Crea el container si no existe"""
    container_client = blob_service.get_container_client(BLOB_CONTAINER_NAME)
    try:
        container_client.create_container()
    except Exception:
        pass  # Ya existe
    return container_client


def upload_to_blob_stream(file_stream, blob_name: str) -> str:#no la entiendo bien
    # funcion para realizar la accion de subida por tramas (chunks)

    # Args:
    #     file_stream: Objeto file-like (SpooledTemporaryFile de FastAPI)
    #     blob_name: Nombre del blob destino

    # Returns:
    #     Ruta del blob en formato 'container/blob_name'

    blob_service = get_blob_service()
    container_client = _ensure_container(blob_service)
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(file_stream, overwrite=True)
    return f"{BLOB_CONTAINER_NAME}/{blob_name}"


def download_blob_stream(blob_path: str):#no la entiendo bien
    """Descarga un blob como stream para procesarlo por chunks sin cargar en memoria.

    Args:
        blob_path: Ruta del blob en formato 'container/blob_name'

    Returns:
        StorageStreamDownloader que soporta iteración por chunks
    """
    blob_service = get_blob_service()
    container_name, blob_name = blob_path.split("/", 1)
    blob_client = blob_service.get_container_client(container_name).get_blob_client(blob_name)
    return blob_client.download_blob()
