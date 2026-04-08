import hmac
import hashlib
import base64
import requests
import time
import uuid
import os

key = os.getenv("API_KEY", "Insert your API key here")
secret = os.getenv("API_SECRET", "Insert your API secret here")
content = "Insert your request content here, empty for GETs"
url = "Insert the target URL here"

client_request_id = str(uuid.uuid4())
timestamp = str(int(time.time()))  # or int(time.time() * 1000) if API expects ms

message = f"{key}{client_request_id}{timestamp}{content}"
signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()
b64_sig = base64.b64encode(signature).decode()

headers = {
    "Api-Key": key,
    "Timestamp": timestamp,
    "Client-Request-Id": client_request_id,
    "Message-Signature": b64_sig,
    # "Content-Type": "application/json",
}

try:
    r = requests.post(url, data=content, headers=headers, timeout=30)
    r.raise_for_status()
    print(r.status_code, r.text)
except requests.RequestException as e:
    print(f"Request failed: {e}")
