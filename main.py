# main.py
import os, io, base64
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from jose import jwt, JWTError
from passlib.context import CryptContext
from dotenv import load_dotenv
from sqlalchemy import select
from apscheduler.schedulers.background import BackgroundScheduler

from db import database, engine
from models import metadata, users, qr_lots, UserCreate, UserPublic, QRPublic
from utils import generate_qr_image, save_qr_file, DATA_DIR
from payments import check_pending_payments, init_blockchain_clients

load_dotenv()
SECRET_KEY = os.environ.get("SECRET_KEY", "devsecret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="QR Market Demo")
app.mount("/static", StaticFiles(directory="static"), name="static")

metadata.create_all(engine)

def _hash(p): return pwd_context.hash(p)
def _verify(p, h): return pwd_context.verify(p, h)

async def _auth_user(username: str, password: str):
    row = await database.fetch_one(users.select().where(users.c.username==username))
    if not row or not _verify(password, row["password_hash"]):
        return None
    return dict(row)

def _token(data: dict, expires: Optional[timedelta]=None):
    payload = data.copy()
    payload.update({"exp": datetime.utcnow() + (expires or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def current_username(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization")
    token = authorization.split(" ",1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username: raise HTTPException(401)
        return username
    except JWTError:
        raise HTTPException(401, "Invalid token")

@app.on_event("startup")
async def startup():
    await database.connect()
    init_blockchain_clients()
    scheduler = BackgroundScheduler()
    interval = int(os.environ.get("CHECK_INTERVAL", 20))
    scheduler.add_job(lambda: __import__("payments").check_pending_payments_sync(), 'interval', seconds=interval)
    scheduler.start()
    app.state.scheduler = scheduler

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
    app.state.scheduler.shutdown()

@app.post("/api/register", response_model=UserPublic)
async def register(u: UserCreate):
    exists = await database.fetch_one(users.select().where(users.c.username==u.username))
    if exists: raise HTTPException(400, "user exists")
    uid = await database.execute(users.insert().values(username=u.username, password_hash=_hash(u.password), created_at=datetime.utcnow()))
    return {"id": uid, "username": u.username, "created_at": datetime.utcnow()}

@app.post("/api/login")
async def login(username: str = Form(...), password: str = Form(...)):
    u = await _auth_user(username, password)
    if not u: raise HTTPException(401, "Incorrect credentials")
    return {"access_token": _token({"sub": u["username"]}), "token_type":"bearer"}

@app.post("/api/qr/create", response_model=QRPublic)
async def create_qr(
    title: str = Form(...),
    price: float = Form(...),
    currency: str = Form(...),          # TRC20 or BEP20
    token_contract: str | None = Form(None),
    receive_address: str = Form(...),
    file: UploadFile | None = File(None),
    username: str = Depends(current_username)
):
    if file:
        contents = await file.read()
        filename = save_qr_file(contents, prefix="qr_upload")
    else:
        img = generate_qr_image(title)
        buf = io.BytesIO(); img.save(buf, format="PNG")
        filename = save_qr_file(buf.getvalue(), prefix="qr_gen")
    qid = await database.execute(qr_lots.insert().values(
        title=title, price=price, currency=currency, token_contract=token_contract,
        receive_address=receive_address, filename=filename, seller=username,
        status="available", created_at=datetime.utcnow()
    ))
    return {"id": qid, "title": title, "price": price, "currency": currency, "status": "available", "seller": username}

@app.get("/api/qr/list")
async def list_qr():
    rows = await database.fetch_all(qr_lots.select().where(qr_lots.c.status != "deleted"))
    return [dict(r) for r in rows]

@app.post("/api/qr/{lot_id}/buy")
async def buy_lot(lot_id: int, buyer: str = Form(...)):
    row = await database.fetch_one(qr_lots.select().where(qr_lots.c.id==lot_id))
    if not row: raise HTTPException(404, "not found")
    if row["status"] != "available": raise HTTPException(400, "not available")
    await database.execute(qr_lots.update().where(qr_lots.c.id==lot_id).values(status="awaiting_payment", reserved_to=buyer, updated_at=datetime.utcnow()))
    return {
        "lot_id": lot_id,
        "price": row["price"],
        "currency": row["currency"],
        "token_contract": row["token_contract"],
        "pay_to": row["receive_address"],
        "note": f"Send exact amount. Optional memo: buy:{lot_id}"
    }

@app.get("/api/qr/{lot_id}/download")
async def download_qr(lot_id: int):
    row = await database.fetch_one(qr_lots.select().where(qr_lots.c.id==lot_id))
    if not row: raise HTTPException(404)
    if row["status"] != "paid": raise HTTPException(403, "not paid")
    path = os.path.join(DATA_DIR, row["filename"])
    if not os.path.exists(path): raise HTTPException(500, "file missing")
    with open(path, "rb") as f: b = f.read()
    return {"filename": row["filename"], "b64": base64.b64encode(b).decode()}

@app.post("/api/check_payments")
async def check_payments_endpoint():
    res = await check_pending_payments()
    return {"checked": res}

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join("static","index.html"), "r", encoding="utf-8") as f:
        return f.read()
