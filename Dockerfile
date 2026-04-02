FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias del sistema para psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Por defecto inicia la API; se puede sobreescribir para el worker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
