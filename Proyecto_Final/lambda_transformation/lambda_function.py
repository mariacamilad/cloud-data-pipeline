import os
import json
import boto3
import pandas as pd
import pg8000.dbapi

from botocore.exceptions import ClientError


# ============================================================
# CONFIGURACIÓN
# ============================================================

BUCKET_NAME = os.getenv("BUCKET_NAME")

SOURCE_KEY = "raw_zone/final_project/hotels.json"
TARGET_KEY = "optimized_zone/final_project/hotels_processed.parquet"

QUALITY_THRESHOLD = 0.20

s3 = boto3.client("s3")


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def lambda_handler(event, context):

    if not BUCKET_NAME:
        raise ValueError("BUCKET_NAME no está configurada.")

    print(f"Leyendo: s3://{BUCKET_NAME}/{SOURCE_KEY}")

    # ========================================================
    # 1. LEER JSON DESDE S3
    # ========================================================

    try:
        response = s3.get_object(
            Bucket=BUCKET_NAME,
            Key=SOURCE_KEY
        )

        raw_data = response["Body"].read()
        data = json.loads(raw_data)

    except ClientError as e:
        print(f"Error leyendo el archivo desde S3: {e}")
        raise

    # ========================================================
    # 2. EXTRAER RESULTADOS DE FOURSQUARE
    # ========================================================

    if isinstance(data, dict):
        resultados = data.get("results", [])
    elif isinstance(data, list):
        resultados = data
    else:
        raise ValueError(
            "El JSON no tiene una estructura reconocida."
        )

    if not resultados:
        raise ValueError(
            "No se encontraron registros dentro de hotels.json."
        )

    print(f"Registros raw encontrados: {len(resultados)}")

    # ========================================================
    # 3. NORMALIZAR JSON
    # ========================================================

    df = pd.json_normalize(resultados)

    columnas = [
        "fsq_place_id",
        "name",
        "location.address",
        "email",
        "categories",
        "latitude",
        "longitude",
        "distance"
    ]

    # reindex evita errores si alguna columna opcional
    # como email no aparece en Foursquare
    df = df.reindex(columns=columnas)

    df.rename(
        columns={
            "location.address": "address"
        },
        inplace=True
    )

    total_original = len(df)

    # ========================================================
    # 4. CONVERTIR CAMPOS NUMÉRICOS
    # ========================================================

    df["latitude"] = pd.to_numeric(
        df["latitude"],
        errors="coerce"
    )

    df["longitude"] = pd.to_numeric(
        df["longitude"],
        errors="coerce"
    )

    df["distance"] = pd.to_numeric(
        df["distance"],
        errors="coerce"
    )

    # ========================================================
    # 5. VALIDACIÓN DE CALIDAD
    # ========================================================

    invalid_mask = (
        df["fsq_place_id"].isna()
        | df["latitude"].isna()
        | df["longitude"].isna()
        | df["distance"].isna()
        | (df["distance"] < 0)
    )

    registros_invalidos = int(invalid_mask.sum())

    porcentaje_invalidos = (
        registros_invalidos / total_original
        if total_original > 0
        else 1
    )

    print(f"Registros originales: {total_original}")
    print(f"Registros inválidos: {registros_invalidos}")
    print(
        f"Porcentaje inválido: "
        f"{porcentaje_invalidos:.2%}"
    )

    # ========================================================
    # 6. REGLA DEL 20 %
    # ========================================================

    if porcentaje_invalidos > QUALITY_THRESHOLD:

        raise ValueError(
            f"Data Quality failed. "
            f"{porcentaje_invalidos:.2%} de los registros "
            f"son inválidos, superando el límite de "
            f"{QUALITY_THRESHOLD:.0%}."
        )

    # ========================================================
    # 7. LIMPIEZA
    # ========================================================

    df_clean = df.loc[~invalid_mask].copy()

    # Transformar lista de categorías
    # a una categoría principal
    df_clean["categories"] = df_clean["categories"].apply(
        lambda x: (
            x[0].get("name")
            if isinstance(x, list)
            and len(x) > 0
            and isinstance(x[0], dict)
            else None
        )
    )

    print(
        f"Registros válidos después de limpieza: "
        f"{len(df_clean)}"
    )

    # ========================================================
    # 8. CONVERTIR A PARQUET
    # ========================================================

    tmp_path = "/tmp/hotels_processed.parquet"

    df_clean.to_parquet(
        tmp_path,
        index=False,
        engine="pyarrow"
    )

    print("Archivo Parquet generado correctamente.")

    # ========================================================
    # 9. CARGAR PARQUET A OPTIMIZED ZONE
    # ========================================================

    try:

        s3.upload_file(
            tmp_path,
            BUCKET_NAME,
            TARGET_KEY
        )

    except ClientError as e:

        print(f"Error cargando Parquet a S3: {e}")
        raise

    print(
        f"Archivo cargado en: "
        f"s3://{BUCKET_NAME}/{TARGET_KEY}"
    )
    
    # ============================================================
    # CARGA A AMAZON RDS POSTGRESQL
    # ============================================================

    conn = pg8000.dbapi.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=5432,
        timeout=10
    )

    cur = conn.cursor()

    UPSERT_SQL = """
    INSERT INTO datos_externos
    (
        fsq_place_id,
        name,
        address,
        categories,
        latitude,
        longitude,
        distance
    )
    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)

    ON CONFLICT (fsq_place_id)
    DO UPDATE SET
        name = EXCLUDED.name,
        address = EXCLUDED.address,
        categories = EXCLUDED.categories,
        latitude = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude,
        distance = EXCLUDED.distance;
    """

    for _, row in df_clean.iterrows():
        cur.execute(
            UPSERT_SQL,
            (
                str(row["fsq_place_id"]),
                str(row["name"]),
                None if pd.isna(row["address"]) else str(row["address"]),
                json.dumps(row["categories"], ensure_ascii=False),
                float(row["latitude"]),
                float(row["longitude"]),
                int(row["distance"])
            )
        )

    conn.commit()

    cur.close()
    conn.close()

    print(f"RDS load completed: {len(df_clean)} records processed")

    # ========================================================
    # 10. RESPUESTA DE LAMBDA
    # ========================================================

    return {
        "statusCode": 200,
        "body": {
            "source": SOURCE_KEY,
            "target": TARGET_KEY,
            "original_records": total_original,
            "invalid_records": registros_invalidos,
            "valid_records": len(df_clean),
            "invalid_percentage": round(
                porcentaje_invalidos * 100,
                2
            )
        }
    }