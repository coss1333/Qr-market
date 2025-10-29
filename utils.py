# utils.py
import os, uuid, io
import qrcode
from PIL import Image
from dotenv import load_dotenv
load_dotenv()

DATA_DIR = os.environ.get("DATA_DIR", "./data")
os.makedirs(DATA_DIR, exist_ok=True)

def generate_qr_image(payload: str):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img

def save_qr_file(data_bytes: bytes, prefix="qr"):
    fname = f"{prefix}_{uuid.uuid4().hex[:8]}.png"
    path = os.path.join(DATA_DIR, fname)
    with open(path, "wb") as f:
        f.write(data_bytes)
    return fname

def save_qr_image_obj(img, prefix="qr"):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return save_qr_file(buf.getvalue(), prefix=prefix)
