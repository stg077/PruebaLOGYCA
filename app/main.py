from fastapi import FastAPI,HTTPException
from app.api.api_conexion import router
from app.db.creacion_SQL import  init_db
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Código que corre al INICIAR la app (Docker / Producción) ---
    init_db()
    yield
    # --- Código que corre al CERRAR la app (si lo necesitas) ---
    # print("Cerrando recursos...")

app=FastAPI(title="Prueba LOGYCA Santiago Colmenares",
    description="Backend para automatización de lectura de CVS Azure y PostgreSQL",
    version="1.0.0",
    lifespan=lifespan
    )

app.include_router(router)
