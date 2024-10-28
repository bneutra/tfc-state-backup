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
# required
S3_BUCKET = os.environ["S3_BUCKET"]
TFC_TOKEN_PATH = os.environ["TFC_TOKEN_PATH"]
# run task requires this response body
OK_RESPONSE = "200 OK"

def get_tfc_token() -> str:
    """Get the TFC token from the SSM parameter store."""
    tfc_api_token = bytes(
        ssm.get_parameter(Name=TFC_TOKEN_PATH, WithDecryption=True)["Parameter"][
            "Value"
        ],
        "utf-8",
    )
    return tfc_api_token.decode("utf-8")

# Initialize some things at global scope for re-use
session = boto3.Session()
ssm = session.client("ssm")
s3_client = boto3.client('s3')
TOKEN = get_tfc_token()


def lambda_handler(event: dict, context) -> dict:
    """Handle the incoming requests"""
    print(event)
    save_state(
        event["workspace_id"],
        event["workspace_name"],
    )
    return {"statusCode": 200, "body": OK_RESPONSE}


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

    tfc_headers = get_headers(TOKEN)
    state_api_response = requests.get(state_api_url, headers=tfc_headers)
    state_api_response.raise_for_status()  # Ensure the request was successful
    state_response_payload = json.loads(state_api_response.text)
    s3key = f"tfc-state-backup/{workspace_name}"
    if DRY_RUN:
        print(f"DRY RUN: Not saving state file to {S3_BUCKET}/{s3key}")
        return
    url = state_response_payload["data"]["attributes"][
        "hosted-state-download-url"
    ]
    # We must stream to disk, then upload to S3
    with tempfile.NamedTemporaryFile(delete=True, mode='wb', dir='/tmp') as temp_file:
        # Fetch the large JSON response from the API and stream to temp file
        with requests.get(url, headers=tfc_headers, stream=True) as response:
            response.raise_for_status()  # Ensure the request was successful
            for chunk in response.iter_content(chunk_size=64*1024):  # Stream in 64KB chunks
                if chunk:
                    temp_file.write(chunk)
        s3_client.upload_file(temp_file.name, S3_BUCKET, s3key)
    print(f"File successfully uploaded to s3://{S3_BUCKET}/{s3key}")
