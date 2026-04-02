# Prueba Técnica LOGYCA - Pipeline de Procesamiento de Ventas CSV

**Autor:** Santiago Colmenares Bolivar

---

## Descripción del Sistema

Sistema backend para la recepción, procesamiento y almacenamiento de archivos CSV con registros de ventas. El sistema está diseñado de forma modular: una API construida con FastAPI que expone endpoints para la carga de archivos y consulta de estados, almacenamiento en Azure Blob Storage, procesamiento asíncrono mediante un Worker que escucha una cola de mensajes, y automatización de reportes con N8N.

---

## Arquitectura

```
┌─────────────┐     ┌───────────────────┐    ┌──────────────────┐
│   Cliente   │────>│   FastAPI API     │───>│  Azure Blob      │
│  (CSV file) │     │  POST /upload     │    │  Storage         │
└─────────────┘     │  GET /job/{id}    │    │  (streaming)     │
                    └────────┬──────────┘    └──────────────────┘
                             │                        │
                             v                        │
                    ┌──────────────────┐              │
                    │  Azure Storage   │              │
                    │  Queue           │              │
                    └────────┬─────────┘              │
                             │                        │
                             v                        v
                    ┌───────────────────────────────────────┐
                    │           Worker (Python)             │
                    │  - Escucha la cola (polling)          │
                    │  - Descarga CSV como stream (chunks)  │
                    │  - Parsea línea por línea             │
                    │  - Inserta con execute_values         │
                    │  - Lotes de 5000 filas                │
                    └────────────────┬──────────────────────┘
                                     │
                                     v
                    ┌───────────────────────────────────────┐
                    │           PostgreSQL                  │
                    │  - jobs (estado del procesamiento)    │
                    │  - sales (registros de ventas)        │
                    │  - sales_daily_summary (resumen N8N)  │
                    └────────────────┬──────────────────────┘
                                     │
                                     v
                    ┌───────────────────────────────────────┐
                    │           N8N Workflow                │
                    │  - Consulta jobs completados          │
                    │  - Calcula total de ventas por día    │
                    │  - Guarda en sales_daily_summary      │
                    └───────────────────────────────────────┘
```

---

## Decisiones Técnicas

### psycopg2 para PostgreSQL

Se utilizó la librería psycopg2 para la conexión con PostgreSQL con el fin de realizar las consultas SQL lo más claras posible. Una alternativa era SQLAlchemy, sin embargo su modelo ORM agrega complejidad innecesaria para este caso de uso. Con psycopg2 se tiene control directo sobre las queries SQL, lo cual facilita la optimización de inserciones masivas con `execute_values`.

### ¿Cómo se evita cargar todo el CSV en memoria?

El procesamiento se realiza en dos niveles de streaming:

1. **Upload (API):** El archivo se sube a Azure Blob Storage directamente desde el `SpooledTemporaryFile` de FastAPI, sin hacer `file.read()` que cargaría todo en RAM.

2. **Descarga y procesamiento (Worker):** El blob se descarga usando `download_blob().chunks()` que entrega pedazos de 4MB. Cada chunk se parsea línea por línea, acumulando filas en un batch de 5,000. Cuando el batch está lleno se inserta y se libera la memoria. De esta forma el consumo de memoria se mantiene constante sin importar el tamaño del archivo.

Este enfoque lo basé en un programa que realicé con microcontroladores donde tenía que pasar datos entre dos memorias SD. No era a la escala de 5,000 líneas pero sí el mismo método: leer un pedazo, procesarlo, guardarlo, y seguir con el siguiente. Con esto se evitaba el overflow de memoria en el microcontrolador.

### ¿Cómo se evita saturar PostgreSQL?

- **Inserción masiva con `execute_values`:** En vez de usar `executemany` (que internamente hace un INSERT por fila), se usa `psycopg2.extras.execute_values` que genera un solo INSERT con múltiples VALUES. Esto es ~10x más rápido y reduce la carga en PostgreSQL.

- **Commit por batch:** Se hace commit después de cada lote de 5,000 filas, no al final de todo el archivo. Si algo falla a la mitad, los lotes ya insertados no se pierden.

- **Procesamiento secuencial:** La cola procesa un mensaje a la vez (`max_messages=1`), evitando múltiples escrituras simultáneas.

- **Visibility timeout:** Se usa un timeout de 300 segundos para evitar que otro worker tome el mismo mensaje si el procesamiento es largo.

### ¿Por qué Azure Storage Queue y no Service Bus?

Se optó por Azure Storage Queue por ser más simple y suficiente para este caso de uso. El worker utiliza polling (consulta la cola cada 2 segundos) similar al modelo de polling en sistemas embebidos. Como mejora futura se podría migrar a Azure Service Bus que soporta un modelo basado en eventos (push), equivalente a trabajar con interrupciones en vez de polling, lo cual reduciría la latencia de respuesta.

### Configuración centralizada

Todas las variables de configuración (PostgreSQL, Azure, worker) están centralizadas en `app/config.py` y se cargan desde variables de entorno con valores por defecto para desarrollo local. Esto permite cambiar entre entornos (local, Docker, producción) sin modificar código.

### Emulador Azurite

Para desarrollo local se utiliza Azurite como emulador de Azure Storage. El sistema está diseñado para funcionar con Azure Blob Storage y Azure Storage Queue en producción, únicamente cambiando la variable de entorno `AZURE_STORAGE_CONNECTION_STRING`.

---

## Estructura del Proyecto

```
PRUEBALOGYCA/
├── app/
│   ├── __init__.py
│   ├── main.py                    # Punto de entrada FastAPI
│   ├── config.py                  # Configuración centralizada (env vars)
│   ├── api/
│   │   ├── __init__.py
│   │   └── api_conexion.py        # Endpoints (upload, job status)
│   ├── db/
│   │   ├── __init__.py
│   │   └── creacion_SQL.py        # Conexión y creación de tablas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── blob_services_azure.py # Upload/download streaming Azure Blob
│   │   ├── queue_service.py       # Envío de mensajes a la cola
│   │   └── worker.py              # Procesamiento asíncrono del CSV
│   └── tests/
│       ├── __init__.py
│       ├── test_routes.py         # Tests de endpoints (con mocks)
│       └── test_worker.py         # Tests del worker (con mocks)
├── data/
│   ├── generate_sample.py         # Generador de CSV de prueba
│   └── sample.csv                 # CSV de ejemplo (100,000 registros)
├── n8n/
│   └── workflow.json              # Export del workflow de N8N
├── .env.example                   # Variables de entorno (Opción 2: Docker + Local)
├── .env.docker.example            # Variables de entorno (Opción 1: Todo Docker)
├── .env.local.example             # Variables de entorno (Opción 3: Todo Local)
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Cómo Ejecutar el Sistema

### Prerrequisitos

- Python 3.10+
- Docker Desktop
- PostgreSQL 16+ (solo si se ejecuta con la Opción 3, sin Docker)

### Clonar el repositorio e instalar dependencias

```bash
git clone https://github.com/stg077/PruebaLOGYCA.git
cd PruebaLOGYCA
```
### Configurar variables de entorno

Antes de ejecutar cualquier opción, copia el archivo de ejemplo correspondiente:

| Opción              | Comando                              |
|---------------------|--------------------------------------|
| 1 (Todo Docker)     | `cp .env.docker.example .env.docker` |
| 2 (Docker + Local)  | `cp .env.example .env`               |
| 3 (Todo Local)      | `cp .env.local.example .env`         |

**Nota sobre puertos:** PostgreSQL en Docker se expone en el puerto `5433` del host para evitar conflictos con instalaciones locales de PostgreSQL (que usan `5432`).

### Crear entorno virtual e instalar dependencias


```bash
# Crear el entorno virtual
python3 -m venv venv

# Activar el entorno
source venv/bin/activate      # Linux / macOS
# venv\Scripts\activate       # Windows (PowerShell/CMD)

# Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt
```

En caso de que solo descargue el comprimido del proyecto, corrobore que esté dentro de la raíz del proyecto para realizar todo de la mejor manera.

---

### Opción 1: Todo con Docker Compose (recomendada)

Este comando levanta todo el ecosistema: PostgreSQL, Azurite, n8n, la API y el Worker.

Nota: Si tienes un entorno virtual activo, puedes desactivarlo con el comando deactivate antes de correr Docker para evitar confusiones de rutas, aunque no es estrictamente necesario.

```bash
docker-compose up -d --build
```

**No se necesita iniciar nada más manualmente.**
La API queda disponible en `http://localhost:8000/docs`.
Una vez que los contenedores estén corriendo, puedes pasar directamente a la sección de [Probar el flujo Completo](#probar-el-flujo-completo).

---

### Opción 2: Docker para infraestructura + local para desarrollo
Levanta solo PostgreSQL, Azurite y N8N con Docker, y ejecuta la API y el Worker localmente.

#### 1. Levantar infraestructura

```bash
docker-compose up -d postgres azurite n8n
```

#### 2. Iniciar la API

```bash
uvicorn app.main:app --reload
```

La API estará disponible en `http://localhost:8000/docs`


#### 3. Iniciar el Worker (en otra terminal)

```bash
python -m app.services.worker
```
Una vez que los contenedores estén corriendo, puedes pasar directamente a la sección de [Probar el flujo Completo](#probar-el-flujo-completo).
---

### Opción 3: Todo manual (sin Docker Compose)

Si no se quiere usar docker-compose, se pueden levantar los servicios individualmente con Docker.

#### 1. Crear la base de datos PostgreSQL

En pgAdmin o psql, crear la base de datos:

```sql
CREATE DATABASE logyca_sales;
```

#### 2. Levantar Azurite (emulador de Azure)

```bash
docker run -d --name azurite -p 10000:10000 -p 10001:10001 -p 10002:10002 mcr.microsoft.com/azure-storage/azurite azurite --skipApiVersionCheck --blobHost 0.0.0.0 --queueHost 0.0.0.0
```

#### 3. Levantar N8N

```bash
docker run -d --name n8n -p 5678:5678 -e N8N_HOST=localhost -e WEBHOOK_URL=http://localhost:5678/ n8nio/n8n
```

#### 4. Iniciar la API

```bash
uvicorn app.main:app --reload
```

#### 5. Iniciar el Worker (en otra terminal)

```bash
python -m app.services.worker
```

---

### Probar el flujo completo

1. Generar CSV de prueba: `python data/generate_sample.py`
2. Subir el CSV: `POST http://localhost:8000/upload` (usar Swagger UI o curl)
3. Verificar estado: `GET http://localhost:8000/job/{job_id}`
4. El worker procesa automáticamente y el status cambia a COMPLETED
5. Configurar N8N:
   - Abrir `http://localhost:5678` en el navegador
   - Ir a **Workflows** > **Import from File**
   - Seleccionar el archivo **`n8n/workflow.json`** incluido en el proyecto
   - Configurar las credenciales de PostgreSQL en N8N:
     - **Base de datos:** `logyca_sales`
     - **Usuario:** `postgres`
     - **Contraseña:** `postgres`
     - **Host y Puerto según la opción:**

       | Opción | Host                   | Puerto |
       |--------|------------------------|--------|
       | 1      | `postgres`             | `5432` |
       | 2      | `host.docker.internal` | `5433` |
       | 3      | `host.docker.internal` | `5432` |
   - Activar el workflow para que ejecute periódicamente y genere el resumen diario en `sales_daily_summary`

6. Para validar la ejecucion de el WorkFlow de n8n ejecutar `http://localhost:8000/stats` Este traera una breve resumen de las base de datos integradas

**Se recomienda utilizar el Swagger UI (`http://localhost:8000/docs`) para que el proceso de validación sea más sencillo.**

### Ejecutar las pruebas

```bash
pytest app/tests/ -v
```

Las pruebas usan mocks y no requieren servicios externos corriendo.

---

## Endpoints de la API

| Método | Ruta          | Descripción |
|--------|---------------|-------------|
| GET    | /             | Validacion inicio de API  |
| POST   | /upload       | Sube un CSV, lo almacena en Blob y encola su procesamiento |
| GET    | /job/{job_id} | Consulta el estado de un job (PENDING, PROCESSING, COMPLETED, FAILED) |
| GET    | /stats        | Consulta las bases de Datos retornado un breve resumen de las mismas |

### POST /upload

Recibe un archivo CSV con la estructura:

```csv
date,product_id,quantity,price
2026-01-01,1001,2,10.5
2026-01-01,1002,1,5.2
```

Respuesta:
```json
{
    "job_id": "uuid-del-job",
    "status": "PENDING"
}
```

Validaciones:
- Solo acepta archivos `.csv`
- Verifica que el CSV contenga las columnas requeridas (date, product_id, quantity, price)
- Rechaza archivos vacíos

### GET /job/{job_id}

Respuesta:
```json
{
    "job_id": "uuid-del-job",
    "file_name": "ventas.csv",
    "status": "COMPLETED",
    "created_at": "2026-01-15 10:30:00"
}
```

---

### GET /stats
Respuesta:
```json
{
  "total_sales_records": 300000,
  "total_jobs": 4,
  "completed_jobs": 3,
  "sales_daily_summary_rows": 91,
  "sales_daily_summary_sample": [
    {
      "id": 50,
      "date": "2026-01-01",
      "total_sales": 1821138.26,
      "total_quantity": 34674,
      "record_count": 3294,
      "updated_at": "2026-04-02T12:45:58.569438"
    },
    {
      "id": 34,
      "date": "2026-01-02",
      "total_sales": 1886160.99,
      "total_quantity": 35463,
      "record_count": 3386,
      "updated_at": "2026-04-02T12:45:58.569438"
    },
    {(....)}
}

```

---

## Tablas de la Base de Datos

### jobs
Almacena el estado de cada archivo subido.

| Campo         | Tipo      | Descripción |
|---------------|-----------|-------------|
| id            | UUID      | Identificador único del job |
| file_name     | VARCHAR   | Nombre del archivo original |
| blob_path     | VARCHAR   | Ruta en Azure Blob Storage |
| status        | VARCHAR   | PENDING, PROCESSING, COMPLETED, FAILED |
| error_message | TEXT      | Mensaje de error si falló |
| created_at    | TIMESTAMP | Fecha de creación |
| updated_at    | TIMESTAMP | Última actualización |

### sales
Almacena cada registro de venta procesado.

| Campo      | Tipo          | Descripción |
|------------|---------------|-------------|
| id         | SERIAL        | Identificador autoincremental |
| job_id     | UUID          | Referencia al job que lo procesó |
| date       | DATE          | Fecha de la venta |
| product_id | INTEGER       | ID del producto |
| quantity   | INTEGER       | Cantidad vendida |
| price      | NUMERIC(10,2) | Precio unitario |
| total      | NUMERIC(12,2) | quantity * price |

### sales_daily_summary
Resumen diario generado por N8N.

| Campo          | Tipo          | Descripción |
|----------------|---------------|-------------|
| id             | SERIAL        | Identificador autoincremental |
| date           | DATE          | Fecha (única) |
| total_sales    | NUMERIC(14,2) | Suma de ventas del día |
| total_quantity | INTEGER       | Suma de cantidades del día |
| record_count   | INTEGER       | Número de registros del día |
| updated_at     | TIMESTAMP     | Última actualización |

---

## Tecnologías Utilizadas

- **FastAPI** — Framework para la API REST
- **PostgreSQL 16** — Base de datos relacional
- **psycopg2** — Driver de PostgreSQL con soporte para inserción masiva (execute_values)
- **Azure Blob Storage** — Almacenamiento de archivos CSV (Azurite para local)
- **Azure Storage Queue** — Cola de mensajes para procesamiento asíncrono
- **N8N** — Automatización del workflow de reportes diarios
- **Docker** — Contenerización y orquestación de servicios