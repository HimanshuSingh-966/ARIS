import os, requests
from dotenv import load_dotenv
load_dotenv('.env')
import boto3
from botocore.config import Config
b2 = boto3.client('s3', endpoint_url=os.environ['B2_ENDPOINT'], aws_access_key_id=os.environ['B2_KEY_ID'], aws_secret_access_key=os.environ['B2_APP_KEY'], config=Config(signature_version='s3v4'))
url = b2.generate_presigned_url('get_object', Params={'Bucket': os.environ['B2_BUCKET_NAME'], 'Key': 'cdsco/FAQ_CT.pdf', 'ResponseContentDisposition': 'inline; filename="FAQ_CT"', 'ResponseContentType': 'application/pdf'}, ExpiresIn=3600)
print("URL:", url)
r = requests.get(url)
print("Status:", r.status_code)
print("Content-Type:", r.headers.get('content-type'))
print("Body Start:", r.text[:200])
