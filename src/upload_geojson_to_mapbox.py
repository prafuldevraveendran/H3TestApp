import re
import requests
import boto3
import json
import os

# Create a Token (Not the Default public token)
# https://console.mapbox.com/account/access-tokens/create
API_TOKEN = ""
# Displayed in the top left corner of the console
# https://console.mapbox.com/
USERNAME = ""
TILESET_NAME = "Polygon with a hole"
GEOJSON_PATH = "../data/polygon-with-a-hole.geojson"

def generate_tileset_id(name):
    # Remove invalid characters
    clean = re.sub(r'[^a-z0-9_]', '_', name.lower())
    # Ensure it starts with a letter
    if not clean[0].isalpha():
        clean = 't_' + clean
    # Limit to 32 characters
    return clean[:32]

def get_temp_s3_bucket_credentials(username, api_token):
    url = f"https://api.mapbox.com/uploads/v1/{username}/credentials?access_token={api_token}"
    response = requests.post(url)
    response.raise_for_status()
    credentials = response.json()
    return credentials

def upload_to_s3(creds, filepath):
    s3 = boto3.client(
        's3',
        aws_access_key_id=creds['accessKeyId'],
        aws_secret_access_key=creds['secretAccessKey'],
        aws_session_token=creds['sessionToken'],
    )

    with open(filepath, 'rb') as f:
        s3.upload_fileobj(f, creds['bucket'], creds['key'])

    print("Upload to S3 successful.")

def create_mapbox_upload(username, mapbox_token, creds, tileset_id, name):
    url = f"https://api.mapbox.com/uploads/v1/{username}?access_token={mapbox_token}"

    payload = {
        "url": creds["url"],
        "tileset": f"{username}.{tileset_id}",
        "name": name
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()

def main():
    creds = get_temp_s3_bucket_credentials(USERNAME, API_TOKEN)
    upload_to_s3(creds, GEOJSON_PATH)
    create_mapbox_upload(USERNAME, API_TOKEN, creds, generate_tileset_id(TILESET_NAME), TILESET_NAME)

if __name__ == "__main__":
    main()
