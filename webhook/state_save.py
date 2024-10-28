""" state_save.py
This script receives notifications from our TFC webhook
and automatically saves the latest state file from the workspace
to an S3 bucket. 
"""

import base64
import hashlib
import json
import os
import boto3
import requests
import tempfile


DRY_RUN = os.getenv("DRY_RUN", False)
REGION = os.getenv("REGION", None)
S3_BUCKET = os.getenv("S3_BUCKET", None)
TFC_TOKEN_PATH = os.getenv("TFC_TOKEN_PATH", None)
# run task requires this response body
OK_RESPONSE = "200 OK"


# Initialize boto3 client at global scope for connection reuse
session = boto3.Session(region_name=REGION)
ssm = session.client("ssm")
s3_client = boto3.client('s3')


def lambda_handler(event: dict, context) -> dict:
    """Handle the incoming requests"""
    print(event)
    save_state(
        event["workspace_id"],
        event["workspace_name"],
    )


def get_tfc_token() -> str:
    """Get the TFC token from the SSM parameter store."""
    tfc_api_token = bytes(
        ssm.get_parameter(Name=TFC_TOKEN_PATH, WithDecryption=True)["Parameter"][
            "Value"
        ],
        "utf-8",
    )
    return tfc_api_token.decode("utf-8")



def get_headers(token: str) -> dict:
    return {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/vnd.api+json",
    }


def save_state(workspace_id: str, workspace_name: str) -> None:
    """Save the state file to the S3 bucket."""

    # TODO: in the event of an error, we could retry but I anticipiate
    # throttling issues with the TFC API. One possible approach:
    # record a marker object in S3 with the run ID and workspace name
    # an hourly lambda could check for these markers and retry the save

    state_api_url = (
        "https://app.terraform.io/api/v2/workspaces/"
        + workspace_id
        + "/current-state-version"
    )

    tfc_headers = get_headers(get_tfc_token())
    state_api_response = requests.get(state_api_url, headers=tfc_headers)
    state_api_response.raise_for_status()  # Ensure the request was successful
    state_response_payload = json.loads(state_api_response.text)
    if DRY_RUN:
        print(f"DRY RUN: Not saving state file to {S3_BUCKET}/{key}")
        return
    url = state_response_payload["data"]["attributes"][
        "hosted-state-download-url"
    ]
    key = f"tfc-state-backup/{workspace_name}"
    # We must stream to disk, then upload to S3
    with tempfile.NamedTemporaryFile(delete=True, mode='wb', dir='/tmp') as temp_file:
        # Fetch the large JSON response from the API and stream to temp file
        with requests.get(url, headers=tfc_headers, stream=True) as response:
            response.raise_for_status()  # Ensure the request was successful
            for chunk in response.iter_content(chunk_size=64*1024):  # Stream in 64KB chunks
                if chunk:
                    temp_file.write(chunk)
        s3_client.upload_file(temp_file.name, S3_BUCKET, key)
    print(f"File successfully uploaded to s3://{S3_BUCKET}/{key}")


def fetch_and_store_large_json():
    # Initialize S3 client
    s3_client = boto3.client('s3')
    bucket_name = 'your-bucket-name'
    s3_key = 'path/to/store/yourfile.json'
    temp_file_path = '/tmp/large_response.json'

    # Fetch the large JSON response from the API and stream to disk
    with requests.get('https://api.example.com/large-json', stream=True) as response:
        response.raise_for_status()  # Ensure the request was successful
        with open(temp_file_path, 'wb') as temp_file:
            for chunk in response.iter_content(chunk_size=1024):  # Stream in 1KB chunks
                if chunk:
                    temp_file.write(chunk)
    
    # Upload the temporary file to S3
    s3_client.upload_file(temp_file_path, bucket_name, s3_key)

    # Clean up the temporary file
    os.remove(temp_file_path)
    
    return f"File successfully uploaded to s3://{bucket_name}/{s3_key}"