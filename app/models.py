from datetime import datetime
from enum import Enum
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class GroupType(str, Enum):
    FILHO_DA_CASA = "Filho da Casa"
    VISITANTE = "Visitante"

class PaymentStatus(str, Enum):
    PAID = "PAGO"
    PENDING = "PENDENTE"

class CategoryType(str, Enum):
    CANTINA = "Cantina"
    LOJA = "Loja"
    CANTINA_LOJA = "Cantina - Loja"

class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    month_year: Mapped[str] = mapped_column(String(20), nullable=False)
    event_name: Mapped[str] = mapped_column(String(100), nullable=True)
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
    category: Mapped[CategoryType] = mapped_column(SQLEnum(CategoryType), default=CategoryType.CANTINA)
    raw_items: Mapped[str] = mapped_column(String(255), nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    import_batch: Mapped["ImportBatch | None"] = relationship(back_populates="consumptions")

class MonthlyFee(Base):
    __tablename__ = "monthly_fees"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_name: Mapped[str] = mapped_column(String(120), nullable=False)
    month_year: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=90.0)  # valor mensal (editável por mês/pessoa)
    paid_amount: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")  # quanto já foi pago
    status: Mapped[PaymentStatus] = mapped_column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

class MenuItem(Base):
    """Cardápio (catálogo) da comanda ao vivo: itens com preço editável."""
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str] = mapped_column(String(20), default="Cantina", server_default="Cantina")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
