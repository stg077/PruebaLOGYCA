import os
from dotenv import load_dotenv

load_dotenv()

# PostgreSQL
DATABASE_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "database": os.getenv("POSTGRES_DB", "logyca_sales"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
}

# Azure Storage (Azurite en local)
AZURE_STORAGE_CONNECTION_STRING = os.getenv(
    "AZURE_STORAGE_CONNECTION_STRING",
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://azurite:10000/devstoreaccount1;"
    "QueueEndpoint=http://azurite:10001/devstoreaccount1;"
)

BLOB_CONTAINER_NAME = os.getenv("BLOB_CONTAINER_NAME", "csv-uploads")
QUEUE_NAME = os.getenv("QUEUE_NAME", "csv-processing")

# Worker
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "5000"))
WORKER_POLL_INTERVAL = int(os.getenv("WORKER_POLL_INTERVAL", "2"))
