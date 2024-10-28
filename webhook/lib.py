import requests
import tempfile
import json

def save_state(s3_client, workspace_id: str, workspace_name: str, s3_bucket: str, tfc_token: str, dry_run:bool) -> None:
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

    tfc_headers = get_headers(tfc_token)
    state_api_response = requests.get(state_api_url, headers=tfc_headers)
    state_api_response.raise_for_status()  # Ensure the request was successful
    state_response_payload = json.loads(state_api_response.text)
    s3key = f"tfc-state-backup/{workspace_name}"
    if dry_run:
        print(f"DRY RUN: Not saving state file to {s3_bucket}/{s3key}")
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
        s3_client.upload_file(temp_file.name, s3_bucket, s3key)
    print(f"File successfully uploaded to s3://{s3_bucket}/{s3key}")


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
   