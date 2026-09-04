import io
import pandas as pd
from sqlalchemy.orm import Session
from app.models import EventConsumption, GroupType, PaymentStatus, ImportBatch

def process_excel_file(file_bytes: bytes, filename: str, month_year: str, event_name: str, db: Session):
    excel_file = io.BytesIO(file_bytes)
    df = pd.read_excel(excel_file, sheet_name="Planilha1")
    
    # Cria o lote associado à pasta do Mês/Ano escolhido
    batch = ImportBatch(
        filename=filename,
        month_year=month_year,
        event_name=event_name or f"Evento {month_year}"
    )
    db.add(batch)
    db.flush()

    current_group = GroupType.FILHO_DA_CASA
    records = []

    for _, row in df.iterrows():
        col_a = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        col_b = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        col_c = row.iloc[2]
        col_d = str(row.iloc[3]).strip().upper() if pd.notna(row.iloc[3]) else "PENDENTE"

        if "LEGENDA" in col_a.upper() or "LEGENDA" in col_b.upper():
            break

        if "VISITANTES" in col_a.upper():
            current_group = GroupType.VISITANTE
            continue

        if not col_a or "TOTAL" in col_a.upper() or "TOTAL" in col_b.upper() or col_a in ["FILHOS DA CASA", "ITENS"]:
            continue

        if pd.isna(col_c):
            continue

        try:
            amount = float(col_c)
        except (ValueError, TypeError):
            continue

        status = PaymentStatus.PAID if col_d == "PAGO" else PaymentStatus.PENDING

        consumption = EventConsumption(
            person_name=col_a,
            group=current_group,
            raw_items=col_b,
            total_amount=amount,
            status=status,
            import_batch_id=batch.id
        )
        records.append(consumption)

    db.add_all(records)
    db.commit()
    return len(records)