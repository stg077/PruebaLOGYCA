import csv
import random
from datetime import datetime, timedelta

# Generar CSV de prueba con el formato que pide LOGYCA
# date,product_id,quantity,price

NUM_ROWS = 100000  # 100k registros para probar

with open("data/sample.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["date", "product_id", "quantity", "price"])
    
    start_date = datetime(2026, 1, 1)
    
    for i in range(NUM_ROWS):
        date = (start_date + timedelta(days=random.randint(0, 90))).strftime("%Y-%m-%d")
        product_id = random.randint(1000, 1050)
        quantity = random.randint(1, 20)
        price = round(random.uniform(5.0, 100.0), 2)
        writer.writerow([date, product_id, quantity, price])

print(f"CSV generado con {NUM_ROWS} registros en data/sample.csv")