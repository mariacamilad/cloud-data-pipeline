import os
import io
import duckdb
import pandas as pd
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load temporary AWS credentials from .env
load_dotenv()

# Create the S3 client
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
    region_name=os.getenv("AWS_DEFAULT_REGION"),
)

bucket_name = "practice-datalake-carlos-jaramillo"           # Change to your bucket name
source_key = "optimized_zone/restaurants_processed.parquet"

# --- Download the S3 object into memory (no local disk write) ---
try:
    obj = s3_client.get_object(Bucket=bucket_name, Key=source_key)
    df = pd.read_parquet(io.BytesIO(obj["Body"].read()))
    print(df.info())
except ClientError as e:
    raise SystemExit(f"Error reading the object from S3: {e}")

# --- Convert to Parquet for optimized (columnar) storage ---
df.to_parquet("output/restaurants_processed.parquet", engine="pyarrow", index=False)
print("File transformed and saved as restaurants_processed.parquet")

# --- High-speed analytics with DuckDB ---
con = duckdb.connect()
result = con.execute(
    """
    SELECT SUM(ROUND(COUNT(*))) OVER () AS 'Total Restaurantes', COUNT(*) AS 'Total Restaurantes por Categoría', categories AS Categoría, ROUND(AVG(distance), 1) AS 'Distancia Promedio'
    FROM 'output/restaurants_processed.parquet'
    GROUP BY categories
    ORDER BY 3 ASC
    """
).df()

result.to_parquet("./output/category_kpis.parquet", index=False)
print(result)
con.close()
