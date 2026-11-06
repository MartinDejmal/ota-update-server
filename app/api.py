import json, uuid, hashlib, tempfile, shutil
from datetime import timedelta
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException, UploadFile, File, Form, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from .config import settings
from .db import *
from .schemas import *
from .security import device_auth, new_token, digest

app=FastAPI(title="OTA Update Server", version="1.0")
@app.on_event("startup")
def startup(): init_db()
def db():
    s=SessionLocal()
    try: yield s
    finally: s.close()
def uid(): return str(uuid.uuid4())
def err(code): raise HTTPException(409, code)
def manifest(r, dep):
    return {"offer_id":None,"deployment_id":dep.id,"release_id":r.id,"build":r.build,"version":r.version,"product":r.product,"hardware_revision":r.hardware_revision,"chip":r.chip,"ota_layout":r.ota_layout,"signing_profile":r.signing_profile,"size":r.size,"sha256":r.artifact_sha256,"url":f"{settings.public_base_url}/api/v1/releases/{r.id}/firmware","offer_expires_at":None}

@app.get("/health/live")
def live(): return {"status":"ok"}
@app.get("/health/ready")
def ready(db: Session=Depends(db)):
    try: db.execute(text("select 1")); return {"status":"ready"}
    except Exception: raise HTTPException(503,"database_unavailable")

@app.post("/api/v1/check-in")
def checkin(body: CheckInIn, authorization: str|None=Header(None), db: Session=Depends(db)):
    d=device_auth(authorization,db); existing=db.query(CheckIn).filter_by(device_id=d.id,request_id=body.request_id).first()
    if existing:
        if hashlib.sha256(body.model_dump_json().encode()).hexdigest()!=json.loads(existing.payload)["digest"]: err("idempotency_conflict")
        return json.loads(existing.response)
    d.last_seen_at=now(); d.observed_build=body.firmware.build; d.observed_sha256=body.firmware.sha256
    accepted=[]
    for ev in body.events:
        a=db.get(Attempt,ev.attempt_id)
        if a and db.get(OtaEvent,ev.event_id) is None:
            db.add(OtaEvent(id=ev.event_id,attempt_id=a.id,sequence=ev.sequence,status=ev.status,payload=ev.model_dump_json())); accepted.append(ev.event_id)
            if ev.status in ("confirmed","failed","rolled_back"):
                a.status=ev.status; a.closed_at=now(); a.error_code=ev.error_code
                dep=db.get(Deployment,a.deployment_id); dep.result_state=ev.status
                if ev.status=="confirmed": dep.control_state="completed"
    dep=db.query(Deployment).filter_by(device_id=d.id,control_state="active").first(); decision="no_assignment"; ota=None
    if dep:
        r=db.get(Release,dep.release_id)
        if r and not r.withdrawn and body.firmware.build<r.build and body.ota_slot_size>=r.size and (d.min_ota_battery_mv is None or (body.battery_mv is not None and body.battery_mv>=d.min_ota_battery_mv)) and all(getattr(r,k)==getattr(d,k) for k in ("product","hardware_revision","chip","ota_layout","signing_profile")):
            o=Offer(id=uid(),deployment_id=dep.id,expires_at=now()+timedelta(seconds=settings.offer_ttl_seconds),manifest=""); m=manifest(r,dep); m["offer_id"]=o.id; m["offer_expires_at"]=o.expires_at.isoformat(); o.manifest=json.dumps(m); db.add(o); ota=m; decision="offered"
        else: decision="incompatible"
    result={"request_id":body.request_id,"server_time":now().isoformat(),"accepted_event_ids":accepted,"decision":decision,"ota":ota}
    payload={"digest":hashlib.sha256(body.model_dump_json().encode()).hexdigest()}; db.add(CheckIn(id=uid(),device_id=d.id,request_id=body.request_id,payload=json.dumps(payload),decision=decision,response=json.dumps(result))); db.commit(); return result

@app.post("/api/v1/attempts",status_code=201)
def start_attempt(body: StartAttempt, authorization: str|None=Header(None), db: Session=Depends(db)):
    d=device_auth(authorization,db); o=db.get(Offer,body.offer_id)
    if not o or o.expires_at<now(): err("offer_not_startable")
    dep=db.get(Deployment,o.deployment_id); r=db.get(Release,dep.release_id)
    if dep.device_id!=d.id or dep.control_state!="active": err("offer_not_startable")
    if db.query(Attempt).filter(Attempt.device_id==d.id,Attempt.status.in_(["started","image_verified"])).first(): err("attempt_active")
    a=Attempt(id=uid(),offer_id=o.id,deployment_id=dep.id,device_id=d.id); db.add(a); dep.result_state="started"; db.commit(); return {"attempt_id":a.id,"status":"started","release_id":r.id}

@app.get("/api/v1/releases/{release_id}/firmware")
def firmware(release_id: str, attempt_id: str, authorization: str|None=Header(None), db: Session=Depends(db)):
    d=device_auth(authorization,db); a=db.get(Attempt,attempt_id); r=db.get(Release,release_id)
    if not a or a.device_id!=d.id or a.status not in ("started","image_verified") or not r or r.withdrawn: raise HTTPException(404,"not_found")
    if not Path(settings.firmware_dir,r.storage_key).is_file(): raise HTTPException(503,"artifact_unavailable")
    return FileResponse(Path(settings.firmware_dir,r.storage_key),media_type="application/octet-stream",headers={"ETag":f'"{r.artifact_sha256}"',"Cache-Control":"private, no-store"})

@app.post("/api/v1/ota-events")
def events(body: EventBatch, authorization: str|None=Header(None), db: Session=Depends(db)):
    d=device_auth(authorization,db); accepted=[]
    for ev in body.events:
        a=db.get(Attempt,ev.attempt_id)
        if not a or a.device_id!=d.id: raise HTTPException(404,"not_found")
        old=db.get(OtaEvent,ev.event_id)
        if old: accepted.append(ev.event_id); continue
        db.add(OtaEvent(id=ev.event_id,attempt_id=a.id,sequence=ev.sequence,status=ev.status,payload=ev.model_dump_json())); accepted.append(ev.event_id)
        if ev.status in ("confirmed","failed","rolled_back"):
            a.status=ev.status; a.closed_at=now(); a.error_code=ev.error_code; dep=db.get(Deployment,a.deployment_id); dep.result_state=ev.status
            if ev.status=="confirmed": dep.control_state="completed"
    db.commit(); return {"accepted_event_ids":accepted}

@app.post("/api/v1/admin/devices",status_code=201)
def create_device(body: DeviceCreate, db: Session=Depends(db)):
    token=new_token(); d=Device(id=uid(),token_digest=digest(token),**body.model_dump()); db.add(d); db.commit(); return {"id":d.id,"name":d.name,"token":token}

@app.post("/api/v1/admin/deployments",status_code=201)
def create_deployment(body: DeploymentCreate, db: Session=Depends(db)):
    if db.query(Deployment).filter_by(device_id=body.device_id,control_state="active").first(): err("active_deployment_exists")
    if not db.get(Device,body.device_id) or not db.get(Release,body.release_id): raise HTTPException(404,"not_found")
    d=Deployment(id=uid(),**body.model_dump()); db.add(d); db.commit(); return {"id":d.id,"status":"active"}

@app.post("/api/v1/admin/releases",status_code=201)
async def create_release(file: UploadFile=File(...), metadata: str=Form(...), db: Session=Depends(db)):
    m=json.loads(metadata); required=("product","hardware_revision","chip","ota_layout","signing_profile","build","version")
    if any(k not in m for k in required): raise HTTPException(422,"missing_metadata")
    total=0; h=hashlib.sha256(); tmp=settings.data_dir/"tmp"; tmp.mkdir(exist_ok=True); p=tmp/f"{uid()}.upload"
    with p.open("wb") as out:
        while chunk:=await file.read(1024*1024):
            total+=len(chunk)
            if total>settings.max_firmware_bytes: p.unlink(missing_ok=True); raise HTTPException(413,"firmware_too_large")
            h.update(chunk); out.write(chunk)
    sha=h.hexdigest(); r=Release(id=uid(),artifact_sha256=sha,size=total,storage_key=f"{sha}.bin",notes=m.get("notes","")[:4096],**{k:m[k] for k in required}); db.add(r); db.commit(); shutil.move(str(p),str(settings.firmware_dir/f"{sha}.bin")); return {"id":r.id,"sha256":sha,"size":total}
