import psycopg2
from psycopg2.extras import RealDictCursor
from app.config import DATABASE_CONFIG


def get_connection():
    #esta funcion realiza la conexion de la base de datos 
    return psycopg2.connect(**DATABASE_CONFIG)


def get_db():
    #se utilza en la api para relizar consultas e insertar datos
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    #inicializa la base de datos si no existen
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            file_name VARCHAR NOT NULL,
            blob_path VARCHAR,
            status VARCHAR DEFAULT 'PENDING',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id SERIAL PRIMARY KEY,
            job_id UUID REFERENCES jobs(id),
            date DATE NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price NUMERIC(10,2) NOT NULL,
            total NUMERIC(12,2) NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales_daily_summary (
            id SERIAL PRIMARY KEY,
            date DATE UNIQUE NOT NULL,
            total_sales NUMERIC(14,2),
            total_quantity INTEGER,
            record_count INTEGER,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("Base de datos inicializada correctamente")
