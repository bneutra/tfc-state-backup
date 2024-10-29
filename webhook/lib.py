import requests
import tempfile
import json
from datetime import datetime

def save_state(s3_client, workspace_id: str, workspace_name: str, s3_bucket: str, tfc_token: str, dry_run:bool) -> None:
    """Save the state file to the S3 bucket."""

    state_api_url = (
        "https://app.terraform.io/api/v2/workspaces/"
        + workspace_id
        + "/current-state-version"
    )

    s3key = get_s3_key(workspace_name)

    tfc_headers = get_headers(tfc_token)
    state_api_response = requests.get(state_api_url, headers=tfc_headers)
    state_api_response.raise_for_status()  # Ensure the request was successful
    state_response_payload = json.loads(state_api_response.text)
    state_created_at = state_response_payload["data"]["attributes"]["created-at"]

    if dry_run:
        print(f"DRY RUN: Not saving state file to {s3_bucket}/{s3key}")
        return
    if s3_state_newer(s3_client, s3_bucket, s3key, state_created_at):
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
        # upload file with state_created_at timestamp as metadata
        s3_client.upload_file(temp_file.name, s3_bucket, s3key, ExtraArgs={'Metadata': {'state_created_at': state_created_at}})
    print(f"File successfully uploaded to s3://{s3_bucket}/{s3key}")


def string_to_datetime(timestamp: str) -> datetime:
    # TFC API timestamp format
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")


def s3_state_newer(s3_client, s3_bucket: str, s3key: str, state_created_at: str) -> bool:
    # read metadata from s3 object if it exists
    print(f"Incoming state file created at: {state_created_at}")
    try:
        response = s3_client.head_object(Bucket=s3_bucket, Key=s3key)
        s3_state_created_at = response["Metadata"]["state_created_at"]
        print(f"Found existing state file in S3 with state_created_at: {s3_state_created_at}")
        if string_to_datetime(s3_state_created_at) >= string_to_datetime(state_created_at):
            print("S3 state timestamp is the same or newer, skipping save")
            return True
        
    except s3_client.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            print("No existing S3 state file found")
        else:
            print(f"WARNING: Error reading S3 object metadata: {e}")
    return False


def get_s3_key(workspace_name: str) -> str:
    return f"tfc-state-backup/{workspace_name}.tfstate"


def get_tfc_token(ssm_client, token_path: str ) -> str:
    """Get the TFC token from the SSM parameter store."""
    tfc_api_token = bytes(
        ssm_client.get_parameter(Name=token_path, WithDecryption=True)["Parameter"][
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


def task_callback(callback_url: str, access_token: str, message: str, status: str) -> None:
    """Send a PATCH request to the callback URL."""
    payload = {
        "data": {
            "type": "task-result",
            "attributes": {
                "status": status,
                "message": message,
            },
        }
    }
    tfc_headers = get_headers(access_token)
    response = requests.patch(callback_url, headers=tfc_headers, json=payload)
    if response.status_code > 399:
        raise Exception("Error sending task callback: ", response.text)
    print("Task callback sent successfully: ", response.status_code)
    return
   