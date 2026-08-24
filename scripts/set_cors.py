"""
scripts/set_cors.py
Apply a read-only CORS policy to the B2 bucket.

Run from anywhere:  python scripts/set_cors.py

The bucket only ever serves reads: the API streams objects through FastAPI
(/api/v1/documents/{id}/stream) and hands out presigned GET URLs. It is never
written to from a browser, so PUT/POST/DELETE have no legitimate caller and are
not granted here.

Origins default to localhost dev servers only. Set ARIS_ALLOWED_ORIGINS (the same
comma-separated variable the API uses for its own CORS) to include production.
"""

import os
import sys
from pathlib import Path

import boto3
from botocore.config import Config
from dotenv import load_dotenv

# File-relative rather than the old load_dotenv('.env'), which resolved against
# the working directory and so only worked when launched from the repo root.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
]


def allowed_origins() -> list[str]:
    configured = [
        o.strip()
        for o in os.environ.get("ARIS_ALLOWED_ORIGINS", "").split(",")
        if o.strip()
    ]
    origins = configured or DEFAULT_ORIGINS

    # A wildcard here would let any website read the bucket directly, bypassing
    # the API key entirely. Refuse rather than quietly apply it.
    if "*" in origins:
        sys.exit(
            "Refusing to apply '*' as an allowed origin: it would make every "
            "object in the bucket world-readable from any website, which "
            "defeats the API-key gate on the backend. List real origins in "
            "ARIS_ALLOWED_ORIGINS instead."
        )
    return origins


def main() -> int:
    origins = allowed_origins()

    print("Configuring B2 Bucket CORS...")
    print(f"  Origins : {', '.join(origins)}")
    print("  Methods : GET, HEAD (read-only)")

    b2 = boto3.client(
        's3',
        endpoint_url=os.environ['B2_ENDPOINT'],
        aws_access_key_id=os.environ['B2_KEY_ID'],
        aws_secret_access_key=os.environ['B2_APP_KEY'],
        config=Config(signature_version='s3v4')
    )

    cors_configuration = {
        'CORSRules': [{
            # Range headers are what let a browser's PDF viewer seek within a
            # large document instead of downloading all of it.
            'AllowedHeaders': ['Range', 'Content-Type', 'Authorization'],
            'AllowedMethods': ['GET', 'HEAD'],
            'AllowedOrigins': origins,
            'ExposeHeaders': [
                'ETag', 'Content-Length', 'Accept-Ranges', 'Content-Range',
            ],
            'MaxAgeSeconds': 3600,
        }]
    }

    try:
        b2.put_bucket_cors(
            Bucket=os.environ['B2_BUCKET_NAME'],
            CORSConfiguration=cors_configuration
        )
        print("OK: read-only CORS applied (GET/HEAD + range requests).")
        return 0
    except Exception as e:
        print(f"ERROR configuring CORS: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
