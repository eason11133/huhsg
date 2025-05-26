import hmac
import hashlib

def verify_signature(body, signature):
    secret = os.getenv("LINE_CHANNEL_SECRET")
    calculated_signature = hmac.new(
        secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    return calculated_signature == signature
