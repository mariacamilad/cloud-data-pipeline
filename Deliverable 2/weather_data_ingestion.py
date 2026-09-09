import os
import requests
import pandas as pd
from datetime import datetime
import boto3
from dotenv import load_dotenv

# Load environment variables from the .env files
load_dotenv()
api_key = os.getenv("OPENWEATHER_API_KEY")
bucket_name = os.getenv("BUCKET_NAME")

# Coordinates of the zone of interest (Chía)
lat = 4.85876
lon = -74.05866

# API request
url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
response = requests.get(url)

if response.status_code == 200:
    data = response.json()
    # Load the query results into the DataFrame
    weather_list = data.get("weather", [])
    weather_desc = weather_list[0].get("description", "N/A") if weather_list else "N/A"
    weather_dict = {
       "extraction_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
       "temperature_C": data["main"]["temp"],
       "humidity_pct": data["main"]["humidity"],
       "weather_desc": weather_desc,
       "wind_speed_ms": data["wind"]["speed"]
    }
    df = pd.DataFrame([weather_dict])
    # Save temporarily in the local filesystem
    filename = f"weather-data_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    df.to_csv(filename, index=False)
    # Send to the Raw Zone of the Data Lake in S3 created in the Learner Lab previously
    # Note: passing credentials to boto3 is not required already, thanks to LabInstanceProfile
    s3_client = boto3.client('s3', region_name='us-east-1')
    s3_client.upload_file(filename, bucket_name, f"raw-zone/weather/{filename}")

    print(f"Success: data saved in s3://{bucket_name}/raw-zone/weather/{filename}")
else:
    print(f"API Error: {response.status_code}")