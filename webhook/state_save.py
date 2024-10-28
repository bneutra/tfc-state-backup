""" state_save.py
This script receives notifications from our TFC webhook
and automatically saves the latest state file from the workspace
to an S3 bucket. 
"""

import os
import boto3
from lib import get_tfc_token, save_state

DRY_RUN = bool(os.getenv("DRY_RUN", False))
# required
S3_BUCKET = os.environ["S3_BUCKET"]
TFC_TOKEN_PATH = os.environ["TFC_TOKEN_PATH"]
# run task requires this response body
OK_RESPONSE = "200 OK"

# Initialize some things at global scope for re-use
session = boto3.Session()
ssm_client = session.client("ssm")
s3_client = boto3.client('s3')
TOKEN = get_tfc_token(ssm_client, TFC_TOKEN_PATH)


def lambda_handler(event: dict, context) -> dict:
    """Handle the incoming requests"""
    print(event)
    save_state(
        s3_client=s3_client,
        workspace_id=event["workspace_id"],
        workspace_name=event["workspace_name"],
        s3_bucket=S3_BUCKET,
        tfc_token=TOKEN,
        dry_run=DRY_RUN,
    )
    return {"statusCode": 200, "body": OK_RESPONSE}



