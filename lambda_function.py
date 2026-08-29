import gspread
import pg8000.dbapi
import os
import json

def lambda_handler(event, context):
    # 1. Modern Authentication (Google Cloud)
    # gspread 6.x natively handles google-auth and reads the JSON directly
    creds_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
    client = gspread.service_account(filename=creds_path)

    # 2. Data Extraction
    sheet_name = os.environ.get('GOOGLE_SHEET_NAME')
    sheet = client.open(sheet_name).sheet1
    data = sheet.get_all_records()

    # 3. AWS RDS Connection (pg8000)
    conn = pg8000.dbapi.connect(
        host=os.environ.get('DB_HOST'),
        database=os.environ.get('DB_NAME'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD')
    )
    cur = conn.cursor()

    # 4. Transformation and Load (Idempotent & Parameterized)
    INSERT_SQL = """
        INSERT INTO datos_externos
            (name, address, categories, latitude, longitude, distance)
        VALUES (%s, %s, %s::jsonb, %s, %s, %s)
        """

    for row in data:
        cur.execute(INSERT_SQL, (
            row['name'],
            row['location.address'],
            json.dumps(row['categories'], ensure_ascii=False),
            float(row['latitude']),
            float(row['longitude']),
            int(row['distance']),
        ))
    conn.commit()
    cur.close()
    conn.close()

    return {
        'statusCode': 200,
        'body': f'Successful ETL process: {len(data)} records inserted into RDS.'
    }
