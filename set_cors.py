import os
import boto3
from botocore.config import Config
from dotenv import load_dotenv

# Load credentials from .env
load_dotenv('.env')

print("Configuring B2 Bucket CORS...")

b2 = boto3.client(
    's3',
    endpoint_url=os.environ['B2_ENDPOINT'],
    aws_access_key_id=os.environ['B2_KEY_ID'],
    aws_secret_access_key=os.environ['B2_APP_KEY'],
    config=Config(signature_version='s3v4')
)

cors_configuration = {
    'CORSRules': [{
        'AllowedHeaders': ['*'],
        'AllowedMethods': ['GET', 'HEAD', 'PUT', 'POST', 'DELETE'],
        'AllowedOrigins': ['*'],
        'ExposeHeaders': ['ETag', 'Content-Length', 'Accept-Ranges', 'Content-Range'],
        'MaxAgeSeconds': 3600
    }]
}

try:
    b2.put_bucket_cors(
        Bucket=os.environ['B2_BUCKET_NAME'], 
        CORSConfiguration=cors_configuration
    )
    print("✅ CORS configured successfully for origin * and range requests.")
    print("Refresh your browser to load the PDF seamlessly.")
except Exception as e:
    print(f"❌ Error configuring CORS: {e}")
