import hashlib, secrets
from fastapi import Header, HTTPException
from sqlalchemy.orm import Session
from .db import Device

def digest(value: str) -> str: return hashlib.sha256(value.encode()).hexdigest()
def new_token() -> str: return secrets.token_urlsafe(32)
def device_auth(authorization: str|None, db: Session) -> Device:
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401, "authentication_required")
    d=db.query(Device).filter(Device.token_digest==digest(authorization[7:])).first()
    if not d: raise HTTPException(401, "invalid_token")
    return d
