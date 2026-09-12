import os
import requests
import pandas as pd


# ============================================================
# 1. CARGAR VARIABLES DE ENTORNO
# ============================================================

api_key = os.getenv("FOURSQUARE_API_KEY")
bucket = os.getenv("BUCKET_NAME")

# ============================================================
# 2. VALIDAR VARIABLES
# ============================================================

if not api_key:
    print("Error: FOURSQUARE_API_KEY no encontrada en el archivo .env.")
    raise


# ============================================================
# 3. CONFIGURACIÓN FOURSQUARE
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
# 5. CONSULTAR FOURSQUARE
# ============================================================

try:

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

except requests.exceptions.RequestException as e:

    print(f"Error: the request to the Foursquare API failed: {e}")
    raise


# ============================================================
# 6. TRANSFORMAR JSON A DATAFRAME
# ============================================================

try:

    df = pd.json_normalize(resultados)

    df_clean = df[
        [
            "fsq_place_id",
            "name",
            "location.address",
            "email",
            "categories",
            "latitude",
            "longitude",
            "distance"
        ]
    ].copy()

    # Cambiar nombre de la dirección
    df_clean.rename(
        columns={
            "location.address": "address"
        },
        inplace=True
    )

except (KeyError, ValueError) as e:

    print(
        f"Error: unexpected response structure "
        f"from the API: {e}"
    )
    raise


print("\nDatos obtenidos:")
print(df_clean.head())


# ============================================================
# 7. LIMPIEZA DE DATOS
# ============================================================

df_clean = df_clean.dropna(
    subset=[
        "fsq_place_id",
        "latitude",
        "longitude"
    ]
)

df_clean = df_clean[
    df_clean["distance"] >= 0
]


# ============================================================
# 8. TRANSFORMAR CATEGORÍAS
# ============================================================

df_clean["categories"] = df_clean["categories"].apply(
    lambda x:
        x[0]["name"]
        if isinstance(x, list) and len(x) > 0
        else None
)


# ============================================================
# 9. VALIDAR CALIDAD DE DATOS
# ============================================================

cantidad_nulos = df_clean.isna().any(axis=1).sum()

print(
    f"\nRegistros con algún valor nulo: "
    f"{cantidad_nulos}"
)

print(
    f"Registros válidos después de la limpieza: "
    f"{len(df_clean)}"
)

# ============================================================
# 10. CONVERTIR A PARQUET
# ============================================================

tmp_path = "/tmp/hotels.parquet"
df_clean.to_parquet("/tmp/hotels.parquet", index=False, engine="pyarrow")

# ============================================================
# 11. CONECTAR A S3
# ============================================================

client = boto3.client("s3")

path_s3 = "raw_zone/final_project/hotels.parquet"

# ============================================================
# 12. CARGAR LOS DATOS
# ============================================================

try:

    registros_insertados = len(df_clean)

    client.upload_file(tmp_path, bucket, path_s3)

    print(
        f"\nProceso completado correctamente."
    )

    print(
        f"Registros procesados: "
        f"{registros_insertados}"
    )


except boto3.Error as e:

    print(f"Error: no fue posible cargar a S3: {e}")
    raise