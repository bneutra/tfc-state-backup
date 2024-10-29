""" dlg.py
This re-runs the state save function in the event of a DLQ message.
"""
import json
import os
from datetime import datetime
import boto3

from lib import get_s3_key, get_tfc_token, save_state

DRY_RUN = bool(os.getenv("DRY_RUN", False))
# required
S3_BUCKET = os.environ["S3_BUCKET"]
TFC_TOKEN_PATH = os.environ["TFC_TOKEN_PATH"]
# run task requires this response body
OK_RESPONSE = "200 OK"
queue_url = os.environ["FAILED_EVENTS_QUEUE_URL"]

# Initialize some things at global scope for re-use
session = boto3.Session()
ssm_client = session.client("ssm")
s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')
TOKEN = get_tfc_token(ssm_client, TFC_TOKEN_PATH)


def lambda_handler(event: dict, context) -> dict:
    """Handle the incoming requests"""
    print(event)
    for record in event['Records']:
        print(record)
        body = json.loads(record["body"])
        event = body["requestPayload"]
        run_timestamp = event["run_created_at"]
        run_datetime = datetime.strptime(run_timestamp, "%Y-%m-%dT%H:%M:%SZ")
        if is_msg_stale(S3_BUCKET, get_s3_key(event["workspace_name"]), run_datetime):
            print("Current s3 object is newer than this failed event, skipping save")
            continue
        save_state(
            s3_client=s3_client,
            workspace_id=event["workspace_id"],
            workspace_name=event["workspace_name"],
            s3_bucket=S3_BUCKET,
            tfc_token=TOKEN,
            dry_run=DRY_RUN,
        )
        sqs_client.delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=record["receiptHandle"]
        )
    return {"statusCode": 200, "body": OK_RESPONSE}

def is_msg_stale(bucket: str, key: str, run_datetime: datetime) -> bool:
    """Check if the s3 object is newer than the run_timestamp"""
    response =  s3_client.head_object(Bucket=bucket, Key=key)
    last_modified = response["LastModified"]
    print(f"Last modified for {bucket}/{key} is: {last_modified}")
    return last_modified > run_datetime


