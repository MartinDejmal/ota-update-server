from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Integer, DateTime, ForeignKey, Text, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings

def now(): return datetime.now(timezone.utc)
engine = create_engine(settings.db_url, connect_args={"check_same_thread": False, "timeout": 5}, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
class Base(DeclarativeBase): pass

class Device(Base):
    __tablename__="devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128)); product: Mapped[str] = mapped_column(String(64))
    hardware_revision: Mapped[str] = mapped_column(String(64)); chip: Mapped[str] = mapped_column(String(64))
    ota_layout: Mapped[str] = mapped_column(String(64)); signing_profile: Mapped[str] = mapped_column(String(64))
    token_digest: Mapped[str|None] = mapped_column(String(64), unique=True, nullable=True)
    min_ota_battery_mv: Mapped[int|None] = mapped_column(Integer, nullable=True)
    last_seen_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_build: Mapped[int|None] = mapped_column(Integer, nullable=True); observed_sha256: Mapped[str|None] = mapped_column(String(64), nullable=True)

class Release(Base):
    __tablename__="releases"; __table_args__=(UniqueConstraint("product","build"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True); product: Mapped[str] = mapped_column(String(64)); hardware_revision: Mapped[str] = mapped_column(String(64)); chip: Mapped[str] = mapped_column(String(64)); ota_layout: Mapped[str] = mapped_column(String(64)); signing_profile: Mapped[str] = mapped_column(String(64)); build: Mapped[int] = mapped_column(Integer); version: Mapped[str] = mapped_column(String(64)); artifact_sha256: Mapped[str] = mapped_column(String(64)); size: Mapped[int] = mapped_column(Integer); storage_key: Mapped[str] = mapped_column(String(128)); notes: Mapped[str] = mapped_column(Text, default=""); withdrawn: Mapped[bool] = mapped_column(Boolean, default=False); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Deployment(Base):
    __tablename__="deployments"; __table_args__=(Index("ix_deploy_active_device","device_id","control_state"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True); device_id: Mapped[str] = mapped_column(ForeignKey("devices.id")); release_id: Mapped[str] = mapped_column(ForeignKey("releases.id")); control_state: Mapped[str] = mapped_column(String(16), default="active"); result_state: Mapped[str] = mapped_column(String(24), default="pending"); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class CheckIn(Base):
    __tablename__="check_ins"; id: Mapped[str] = mapped_column(String(36), primary_key=True); device_id: Mapped[str] = mapped_column(ForeignKey("devices.id")); request_id: Mapped[str] = mapped_column(String(36)); received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now); payload: Mapped[str] = mapped_column(Text); decision: Mapped[str] = mapped_column(String(64)); response: Mapped[str] = mapped_column(Text)
    __table_args__=(UniqueConstraint("device_id","request_id"),)

class Offer(Base):
    __tablename__="offers"; id: Mapped[str] = mapped_column(String(36), primary_key=True); deployment_id: Mapped[str] = mapped_column(ForeignKey("deployments.id")); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now); expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True)); manifest: Mapped[str] = mapped_column(Text)

class Attempt(Base):
    __tablename__="ota_attempts"; id: Mapped[str] = mapped_column(String(36), primary_key=True); offer_id: Mapped[str] = mapped_column(ForeignKey("offers.id")); deployment_id: Mapped[str] = mapped_column(ForeignKey("deployments.id")); device_id: Mapped[str] = mapped_column(ForeignKey("devices.id")); status: Mapped[str] = mapped_column(String(24), default="started"); started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now); closed_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True); error_code: Mapped[str|None] = mapped_column(String(64), nullable=True)

class OtaEvent(Base):
    __tablename__="ota_events"; id: Mapped[str] = mapped_column(String(36), primary_key=True); attempt_id: Mapped[str] = mapped_column(ForeignKey("ota_attempts.id")); sequence: Mapped[int] = mapped_column(Integer); status: Mapped[str] = mapped_column(String(24)); payload: Mapped[str] = mapped_column(Text); received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now); __table_args__=(UniqueConstraint("attempt_id","sequence"),)

def init_db():
    Base.metadata.create_all(engine)
