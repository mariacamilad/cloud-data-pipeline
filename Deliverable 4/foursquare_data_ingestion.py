import os
import sys
import requests
import pandas as pd
import pg8000.dbapi
from dotenv import load_dotenv


# ============================================================
# 1. CARGAR VARIABLES DE ENTORNO
# ============================================================

load_dotenv()

api_key = os.getenv("FOURSQUARE_API_KEY")

RDS_HOST = os.getenv("DB_HOST")
RDS_DATABASE = os.getenv("DB_NAME")
RDS_USER = os.getenv("DB_USER")
RDS_PASSWORD = os.getenv("DB_PASSWORD")


# ============================================================
# 2. VALIDAR VARIABLES
# ============================================================

if not api_key:
    sys.exit(
        "Error: FOURSQUARE_API_KEY no encontrada en el archivo .env."
    )

if not all([
    RDS_HOST,
    RDS_DATABASE,
    RDS_USER,
    RDS_PASSWORD
]):
    sys.exit(
        "Error: faltan variables de conexión a RDS en el archivo .env."
    )


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

    sys.exit(
        f"Error: the request to the Foursquare API failed: {e}"
    )


# ============================================================
# 6. TRANSFORMAR JSON A DATAFRAME
# ============================================================

try:

    df = pd.json_normalize(data["results"])

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

    sys.exit(
        f"Error: unexpected response structure "
        f"from the API: {e}"
    )


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
# 10. CONECTAR A RDS
# ============================================================

try:

    connection = pg8000.dbapi.connect(
        host=RDS_HOST,
        database=RDS_DATABASE,
        user=RDS_USER,
        password=RDS_PASSWORD
    )

    cursor = connection.cursor()

    print("\nConexión a RDS exitosa.")

except pg8000.Error as e:

    sys.exit(
        f"Error: no fue posible conectar con RDS: {e}"
    )


# ============================================================
# 11. INSERTAR / ACTUALIZAR HOTELES
# ============================================================

sql = """
INSERT INTO hoteles (
    fsq_place_id,
    name,
    address,
    email,
    categories,
    latitude,
    longitude,
    distance
)
VALUES (
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    CAST(%s AS INTEGER)
)

ON CONFLICT (fsq_place_id)

DO UPDATE SET
    name = EXCLUDED.name,
    address = EXCLUDED.address,
    email = EXCLUDED.email,
    categories = EXCLUDED.categories,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    distance = EXCLUDED.distance;
"""


# ============================================================
# 12. CARGAR LOS DATOS
# ============================================================

try:

    registros_insertados = 0

    for _, row in df_clean.iterrows():

        cursor.execute(
            sql,
            (
                row["fsq_place_id"],
                row["name"],
                row["address"],
                row["email"],
                row["categories"],
                row["latitude"],
                row["longitude"],
                row["distance"]
            )
        )

        registros_insertados += 1


    connection.commit()

    print(
        f"\nProceso completado correctamente."
    )

    print(
        f"Registros procesados: "
        f"{registros_insertados}"
    )


except pg8000.Error as e:

    connection.rollback()

    sys.exit(
        f"Error durante la carga de datos en RDS: {e}"
    )


# ============================================================
# 13. CERRAR CONEXIÓN
# ============================================================

finally:

    cursor.close()
    connection.close()

    print("Conexión a RDS cerrada.")