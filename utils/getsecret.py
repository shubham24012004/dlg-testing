import os

import boto3
from botocore.exceptions import ClientError
from flask import json
from dotenv import load_dotenv

load_dotenv()

_secret_cache = None

def get_secret():
    global _secret_cache

    if _secret_cache is not None:
        return _secret_cache

    secret_name = os.getenv("DLG_AWS_SECRET_NAME")
    region_name = "ap-south-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    secret = get_secret_value_response['SecretString']
    secret_dict = json.loads(secret)

    for key, value in secret_dict.items():
        os.environ[key] = str(value)

    _secret_cache = secret_dict
    return _secret_cache
    