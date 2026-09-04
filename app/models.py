from datetime import datetime
from enum import Enum
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class GroupType(str, Enum):
    FILHO_DA_CASA = "Filho da Casa"
    VISITANTE = "Visitante"

class PaymentStatus(str, Enum):
    PAID = "PAGO"
    PENDING = "PENDENTE"

class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    month_year: Mapped[str] = mapped_column(String(20), nullable=False) # Ex: "09/2026"
    event_name: Mapped[str] = mapped_column(String(100), nullable=True) # Ex: "Gira de Setembro"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    consumptions: Mapped[list["EventConsumption"]] = relationship(
        back_populates="import_batch", 
        cascade="all, delete-orphan"
    )

class EventConsumption(Base):
    __tablename__ = "event_consumptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_name: Mapped[str] = mapped_column(String(120), nullable=False)
    group: Mapped[GroupType] = mapped_column(SQLEnum(GroupType), nullable=False)
    raw_items: Mapped[str] = mapped_column(String(255), nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    import_batch: Mapped["ImportBatch | None"] = relationship(back_populates="consumptions")