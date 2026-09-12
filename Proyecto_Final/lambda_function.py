import os
import json
import boto3
import requests
from datetime import datetime


# ============================================================
# 1. VARIABLES DE ENTORNO
# ============================================================

api_key = os.getenv("FOURSQUARE_API_KEY")
bucket = os.getenv("BUCKET_NAME")


# ============================================================
# 2. VALIDAR VARIABLES
# ============================================================

if not api_key:
    raise ValueError(
        "FOURSQUARE_API_KEY no encontrada en las variables de entorno."
    )

if not bucket:
    raise ValueError(
        "BUCKET_NAME no encontrada en las variables de entorno."
    )


# ============================================================
# 3. CONFIGURACIÓN
# ============================================================

URL = "https://places-api.foursquare.com/places/search"

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {api_key.strip()}",
    "X-Places-Api-Version": "2025-06-17",
}


# ============================================================
# 4. PARÁMETROS DE BÚSQUEDA
# ============================================================

params = {
    "query": "hotels",
    "ll": "41.901706,12.478713",
    "limit": 50
}


# ============================================================
# 5. CLIENTE S3
# ============================================================

s3 = boto3.client("s3")


# ============================================================
# 6. FUNCIÓN PRINCIPAL
# ============================================================

def lambda_handler(event, context):

    try:

        # ----------------------------------------------------
        # CONSULTAR FOURSQUARE
        # ----------------------------------------------------

        response = requests.get(
            URL,
            headers=headers,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        resultados = data.get("results", [])

        print(
            f"Query successful: "
            f"{len(resultados)} hotels found."
        )


        # ----------------------------------------------------
        # VALIDAR RESULTADOS
        # ----------------------------------------------------

        if not resultados:

            print("Foursquare no devolvió resultados.")

            return {
                "statusCode": 204,
                "message": "No se encontraron hoteles."
            }

        path_s3 = (
            f"raw_zone/final_project/"
            f"hotels.json"
        )


        # ----------------------------------------------------
        # GUARDAR JSON EN S3
        # ----------------------------------------------------

        s3.put_object(
            Bucket=bucket,
            Key=path_s3,
            Body=json.dumps(data),
            ContentType="application/json"
        )


        # ----------------------------------------------------
        # RESULTADO
        # ----------------------------------------------------

        print(
            f"Datos almacenados correctamente en: "
            f"s3://{bucket}/{path_s3}"
        )

        print(
            f"Registros procesados: "
            f"{len(resultados)}"
        )


        return {

            "statusCode": 200,

            "message": (
                "Ingesta completada correctamente."
            ),

            "records": len(resultados),

            "bucket": bucket,

            "key": path_s3

        }


    except requests.exceptions.RequestException as e:

        print(
            f"Error en la API de Foursquare: {e}"
        )

        raise


    except boto3.exceptions.Boto3Error as e:

        print(
            f"Error al almacenar los datos en S3: {e}"
        )

        raise


    except Exception as e:

        print(
            f"Error inesperado: {e}"
        )

        raise