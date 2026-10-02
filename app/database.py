import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Pega a URL do ambiente (no Render) ou usa o SQLite local se a variável não existir
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./finance.db")

# Força o uso do driver psycopg2, não importa como a URL foi colada no Render
if DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL.split("://", 1)[1]

# Configuração de engine adequada para SQLite ou PostgreSQL
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    # pool_pre_ping testa a conexão antes de usar (evita erro quando o banco 'acorda')
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()