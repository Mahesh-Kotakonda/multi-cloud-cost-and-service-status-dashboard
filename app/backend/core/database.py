import os
import json
import boto3
import psycopg2

def get_ssm_credentials(ssm_parameter_name: str, region: str):
    """Fetch DB username and password from AWS SSM Parameter Store"""
    ssm_client = boto3.client("ssm", region_name=region)
    response = ssm_client.get_parameter(Name=ssm_parameter_name, WithDecryption=True)
    creds = json.loads(response["Parameter"]["Value"])
    return {"username": creds["username"], "password": creds["password"]}

def get_db_connection():
    """Create DB connection using env vars + SSM credentials"""
    host = os.environ.get("DB_HOST")
    port = int(os.environ.get("DB_PORT", 5432))
    dbname = os.environ.get("DB_NAME")
    ssm_param_name = os.environ.get("SSM_PARAM_NAME")
    aws_region = os.environ.get("AWS_REGION", "us-east-1")

    if not all([host, dbname, ssm_param_name]):
        raise ValueError("DB_HOST, DB_NAME, and SSM_PARAM_NAME must be set")

    creds = get_ssm_credentials(ssm_param_name, aws_region)

    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=creds["username"],
        password=creds["password"]
    )
    return conn
