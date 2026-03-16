"""
AWS Secrets Manager integration.

In production (ECS Fargate), set AWS_SECRET_NAME to the name of the secret
that holds DATABASE_URL, JWT_SECRET_KEY, etc.  The loader injects those
values as environment variables before the rest of the app reads them.

In local dev (docker-compose or bare Python), AWS_SECRET_NAME is not set,
so this module is a no-op.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)


def _fetch_secret(secret_name: str, region: str) -> dict:
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        logger.warning("boto3 not installed — cannot load from Secrets Manager")
        return {}

    client = boto3.client("secretsmanager", region_name=region)
    try:
        response = client.get_secret_value(SecretId=secret_name)
        return json.loads(response["SecretString"])
    except Exception as exc:  # ClientError, json.JSONDecodeError, etc.
        logger.error("Failed to load secret '%s': %s", secret_name, exc)
        return {}


def load_aws_secrets() -> None:
    """
    If AWS_SECRET_NAME is present, pull secrets from Secrets Manager and
    inject them into os.environ.  Existing env vars (e.g. set on the task
    definition directly) are never overwritten.
    """
    secret_name = os.environ.get("AWS_SECRET_NAME")
    if not secret_name:
        return  # Local / non-AWS environment — nothing to do

    region = os.environ.get("AWS_REGION", "us-east-1")
    secrets = _fetch_secret(secret_name, region)

    injected = 0
    for key, value in secrets.items():
        if key not in os.environ:
            os.environ[key] = str(value)
            injected += 1

    logger.info(
        "Loaded %d secret(s) from AWS Secrets Manager (secret=%s, region=%s)",
        injected,
        secret_name,
        region,
    )
