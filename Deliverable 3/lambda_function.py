import pg8000.dbapi
import os
import json
import boto3
import io
import csv

def lambda_handler(event, context):
    try:
        client = boto3.client("s3")
        bucket = "practice-datalake-carlos-jaramillo"
        prefix = "raw_zone/"

        response = client.list_objects_v2(
                    Bucket=bucket,
                    Prefix=prefix
                )

        data = []

        if "Contents" in response:        
            for file in response["Contents"]:
                obj = client.get_object(Bucket=bucket, Key=file["Key"])
                content = obj["Body"].read().decode("utf-8")
                reader = csv.DictReader(io.StringIO(content))
                for row in reader:
                    data.append(row)
        else:
            print("No files found in raw_zone/")

        # 3. AWS RDS Connection (pg8000)
        conn = pg8000.dbapi.connect(
            host=os.environ.get('DB_HOST'),
            database=os.environ.get('DB_NAME'),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASSWORD')
        )
        cur = conn.cursor()
        cur.execute("DELETE FROM datos_externos;")

        # 4. Transformation and Load (Idempotent & Parameterized)
        INSERT_SQL = """
            INSERT INTO datos_externos
                (name, address, categories, latitude, longitude, distance)
            VALUES (%s, %s, %s::jsonb, %s, %s, %s)
            ON CONFLICT (name)
            DO UPDATE SET
                address = EXCLUDED.address,
                categories = EXCLUDED.categories,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                distance = EXCLUDED.distance;
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
    except Exception as e:
        print(e)
