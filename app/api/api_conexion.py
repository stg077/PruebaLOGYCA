import uuid
from fastapi import APIRouter, UploadFile, HTTPException, File, Depends
from psycopg2.extras import RealDictCursor
from app.db.creacion_SQL import get_db
from app.services.blob_services_azure import upload_to_blob_stream
from app.services.queue_service import send_processing_message

router = APIRouter()

# Columnas esperadas en el CSV
EXPECTED_CSV_COLUMNS = {"date", "product_id", "quantity", "price"}


@router.post("/upload")
async def cargar_archivo(file: UploadFile = File(...), db=Depends(get_db)):
    """Recibe un CSV, lo sube a Azure Blob Storage y encola su procesamiento.

    El archivo se sube en streaming sin cargarlo completamente en memoria.
    Retorna inmediatamente un job_id para consultar el estado.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Archivo no proporcionado")

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="El archivo debe ser .csv")

    # Validar que el CSV tenga las columnas esperadas (leer solo la primera línea)
    first_line = await file.read(1024)  # Leer solo lo necesario para el header
    if not first_line:
        raise HTTPException(status_code=400, detail="El archivo está vacío")

    header_line = first_line.decode("utf-8").split("\n")[0]
    columns = {col.strip().lower() for col in header_line.split(",")}
    if not EXPECTED_CSV_COLUMNS.issubset(columns):
        raise HTTPException(
            status_code=400,
            detail=f"CSV inválido: se requieren las columnas {EXPECTED_CSV_COLUMNS}"
        )

    # Rebobinar el archivo para subirlo completo al blob
    await file.seek(0)

    job_id = str(uuid.uuid4())
    cursor = db.cursor()

    cursor.execute(
        "INSERT INTO jobs (id, file_name, status) VALUES (%s, %s, %s)",
        (job_id, file.filename, "PENDING")
    )
    db.commit()

    # Subir a Azure Blob Storage usando streaming (file.file es el SpooledTemporaryFile)
    blob_name = f"{job_id}_{file.filename}"
    blob_path = upload_to_blob_stream(file.file, blob_name)

    cursor.execute(
        "UPDATE jobs SET blob_path = %s WHERE id = %s",
        (blob_path, job_id)
    )
    db.commit()
    cursor.close()

    # Enviar mensaje a la cola para procesamiento asíncrono
    send_processing_message(job_id, blob_path)

    return {"job_id": job_id, "status": "PENDING"}


@router.get("/job/{job_id}")
async def consulta_estado(job_id: str, db=Depends(get_db)):
    """Consulta el estado de procesamiento de un job."""
    cursor = db.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
    job = cursor.fetchone()
    cursor.close()

    if not job:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")

    result = {
        "job_id": str(job["id"]),
        "file_name": job["file_name"],
        "status": job["status"],
        "created_at": str(job["created_at"]),
    }

    if job.get("error_message"):
        result["error_message"] = job["error_message"]

    return result


@router.get("/stats")
async def stats(db=Depends(get_db)):
    """Muestra conteos de las tablas principales para validar el procesamiento."""
    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) FROM sales")
    total_sales = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = 'COMPLETED'")
    completed_jobs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM sales_daily_summary")
    total_summary_rows = cursor.fetchone()[0]

    cursor.execute("SELECT * FROM sales_daily_summary ORDER BY date LIMIT 10")
    cols = [desc[0] for desc in cursor.description]
    summary = [dict(zip(cols, row)) for row in cursor.fetchall()]

    cursor.close()
    return {
        "total_sales_records": total_sales,
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "sales_daily_summary_rows": total_summary_rows,
        "sales_daily_summary_sample": summary
    }


@router.get("/")
async def inicio():
    """Health check del servicio"""
    return {"status": "CORRIENDO"}
