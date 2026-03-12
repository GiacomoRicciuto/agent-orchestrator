"""
SQLAlchemy ORM models.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    String, Boolean, Text, Integer, Numeric, DateTime, ForeignKey, LargeBinary, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_uuid():
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    credits: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    instances: Mapped[list["Instance"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    billing_txns: Mapped[list["BillingTxn"]] = relationship(back_populates="user")


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(String(10))  # emoji
    category: Mapped[str | None] = mapped_column(String(50))
    github_repo: Mapped[str] = mapped_column(String(200), nullable=False)
    github_branch: Mapped[str] = mapped_column(String(50), default="main")
    required_vars: Mapped[dict] = mapped_column(JSONB, nullable=False)
    llm_options: Mapped[dict | None] = mapped_column(JSONB)
    cost_per_sprint: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Instance(Base):
    __tablename__ = "instances"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("templates.id"))
    name: Mapped[str | None] = mapped_column(String(200))

    # Railway resources
    railway_project_id: Mapped[str | None] = mapped_column(String(100))
    railway_service_id: Mapped[str | None] = mapped_column(String(100))
    railway_environment_id: Mapped[str | None] = mapped_column(String(100))
    railway_domain: Mapped[str | None] = mapped_column(String(300))

    # Config (encrypted)
    encrypted_vars: Mapped[bytes | None] = mapped_column(LargeBinary)
    admin_api_key_hash: Mapped[str | None] = mapped_column(String(255))

    # LLM config
    llm_provider: Mapped[str | None] = mapped_column(String(50))
    llm_model: Mapped[str | None] = mapped_column(String(100))

    # Status
    status: Mapped[str] = mapped_column(String(20), default="provisioning", index=True)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Usage
    sprints_used: Mapped[int] = mapped_column(Integer, default=0)
    last_sprint_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="instances")
    template: Mapped["Template"] = relationship()
    sprints: Mapped[list["Sprint"]] = relationship(back_populates="instance", cascade="all, delete-orphan")

    __table_args__ = (Index("idx_instances_user", "user_id"),)


class Sprint(Base):
    __tablename__ = "sprints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    instance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("instances.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="running")
    phase: Mapped[str | None] = mapped_column(String(20))
    cost: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    instance: Mapped["Instance"] = relationship(back_populates="sprints")

    __table_args__ = (
        Index("idx_sprints_instance", "instance_id"),
        Index("idx_sprints_user", "user_id"),
    )


class BillingTxn(Base):
    __tablename__ = "billing_txns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # topup, sprint_deduct, refund, bonus
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    credits_delta: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    stripe_payment_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="billing_txns")

    __table_args__ = (Index("idx_billing_user", "user_id"),)
