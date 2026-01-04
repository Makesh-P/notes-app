import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

def generate_vapid_keys():
    # 1. Generate the Private Key (Elliptic Curve P-256)
    private_key = ec.generate_private_key(ec.SECP256R1())
    
    # 2. Derive the Public Key
    public_key = private_key.public_key()
    
    # 3. Format Private Key (32 bytes -> URL-Safe Base64)
    priv_val = private_key.private_numbers().private_value
    priv_bytes = priv_val.to_bytes(32, byteorder='big')
    priv_b64 = base64.urlsafe_b64encode(priv_bytes).rstrip(b'=').decode('utf-8')
    
    # 4. Format Public Key (65 bytes uncompressed -> URL-Safe Base64)
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    pub_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b'=').decode('utf-8')
    
    return priv_b64, pub_b64

# Run and Print
try:
    private_key, public_key = generate_vapid_keys()
    print("\n✅ SUCCESS! Here are your keys:\n")
    print(f"VAPID_PRIVATE_KEY = \"{private_key}\"")
    print(f"VAPID_PUBLIC_KEY  = \"{public_key}\"")
    print("\n👉 Copy these strings into your app.py and note.html as instructed.")
except Exception as e:
    print("Error:", e)