import io
import pandas as pd
from pathlib import Path
from collections import defaultdict
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.models import EventConsumption, PaymentStatus, GroupType, CategoryType, ImportBatch, MonthlyFee
from app.services.excel_import import process_excel_file

Base.metadata.create_all(bind=engine)

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Finance API - Gestão de Cantina, Loja e Mensalidades")
templates = Jinja2Templates(directory=APP_DIR / "templates")

MEMBERS_LIST = [
    "Eliana", "Kelvin", "Igor", "Lívia", 
    "Nicole", "Indiara", "Jhon", "Bruna", "Talles"
]

@app.get("/health")
def health_check():
    return {"status": "online"}

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    raw_consumptions = db.query(EventConsumption).all()
    batches = db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).all()
    monthly_fees = db.query(MonthlyFee).order_by(MonthlyFee.month_year.desc()).all()
    
    cantina_total_geral = 0.0
    cantina_total_pago = 0.0
    cantina_total_pendente = 0.0
    formatted_consumptions = []

    for item in raw_consumptions:
        amount = float(item.total_amount or 0.0)
        cantina_total_geral += amount
        status_val = str(getattr(item.status, 'value', item.status)).upper()
        group_val = str(getattr(item.group, 'value', item.group))
        cat_val = str(getattr(item.category, 'value', item.category or "Cantina"))

        if status_val == "PAGO":
            cantina_total_pago += amount
        else:
            cantina_total_pendente += amount

        batch_month = item.import_batch.month_year if item.import_batch else "Lançamentos Ao Vivo"

        formatted_consumptions.append({
            "id": item.id,
            "person_name": item.person_name,
            "group": group_val,
            "category": cat_val,
            "raw_items": item.raw_items,
            "total_amount": amount,
            "status": status_val,
            "month_year": batch_month
        })

    # Agrupa consumos por pasta (Mês/Ano)
    folders = defaultdict(list)
    for c in formatted_consumptions:
        folders[c["month_year"]].append(c)

    formatted_folders = []
    for month_year, consumptions_list in folders.items():
        f_total = sum(i["total_amount"] for i in consumptions_list)
        f_pago = sum(i["total_amount"] for i in consumptions_list if i["status"] == "PAGO")
        f_pendente = sum(i["total_amount"] for i in consumptions_list if i["status"] == "PENDENTE")
        formatted_folders.append({
            "month_year": month_year,
            "total_geral": f_total,
            "total_pago": f_pago,
            "total_pendente": f_pendente,
            "consumptions": consumptions_list  # Alterado de 'items' para 'consumptions'
        })

    fees_total_geral = 0.0
    fees_total_pago = 0.0
    fees_total_pendente = 0.0
    fees_by_month = defaultdict(list)

    for fee in monthly_fees:
        amount = float(fee.amount or 90.0)
        fees_total_geral += amount
        status_val = str(getattr(fee.status, 'value', fee.status)).upper()

        if status_val == "PAGO":
            fees_total_pago += amount
        else:
            fees_total_pendente += amount

        fees_by_month[fee.month_year].append({
            "id": fee.id,
            "person_name": fee.person_name,
            "amount": amount,
            "status": status_val
        })

    # Agrupa mensalidades por Mês/Ano
    formatted_fee_folders = []
    for month_year, fee_list in fees_by_month.items():
        f_total = sum(i["amount"] for i in fee_list)
        f_pago = sum(i["amount"] for i in fee_list if i["status"] == "PAGO")
        f_pendente = sum(i["amount"] for i in fee_list if i["status"] == "PENDENTE")
        formatted_fee_folders.append({
            "month_year": month_year,
            "total_geral": f_total,
            "total_pago": f_pago,
            "total_pendente": f_pendente,
            "fees": fee_list  # Alterado de 'items' para 'fees'
        })

    formatted_batches = [
        {
            "id": b.id,
            "filename": b.filename,
            "month_year": b.month_year,
            "event_name": b.event_name,
            "created_at": b.created_at.strftime("%d/%m/%Y %H:%M"),
            "items_count": len(b.consumptions)
        }
        for b in batches
    ]

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "folders": formatted_folders,
            "fee_folders": formatted_fee_folders,
            "batches": formatted_batches,
            "cantina_total_geral": cantina_total_geral,
            "cantina_total_pago": cantina_total_pago,
            "cantina_total_pendente": cantina_total_pendente,
            "fees_total_geral": fees_total_geral,
            "fees_total_pago": fees_total_pago,
            "fees_total_pendente": fees_total_pendente,
        }
    )

# --- LANÇAMENTO DIRETO AO VIVO ---

from datetime import datetime

@app.post("/consumptions/direct-add")
def add_direct_consumption(
    event_date: str = Form(...),  # Espera 'YYYY-MM-DD' do input date
    person_name: str = Form(...),
    group: str = Form(...),
    category: str = Form(...),
    raw_items: str = Form(...),
    total_amount: float = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    # Converte '2026-09-04' para '04/09/2026' (data do dia) e '09/2026' (pasta do mês)
    try:
        date_obj = datetime.strptime(event_date, "%Y-%m-%d")
        full_date_str = date_obj.strftime("%d/%m/%Y")
        month_year_str = date_obj.strftime("%m/%Y")
    except ValueError:
        full_date_str = event_date
        month_year_str = event_date

    # Localiza ou cria a pasta do mês correspondente
    batch = db.query(ImportBatch).filter(ImportBatch.month_year == month_year_str).first()
    if not batch:
        batch = ImportBatch(
            filename="Lançamentos Ao Vivo",
            month_year=month_year_str,
            event_name=f"Vendas Ao Vivo - {month_year_str}"
        )
        db.add(batch)
        db.flush()

    grp_enum = GroupType.FILHO_DA_CASA if group == "Filho da Casa" else GroupType.VISITANTE
    cat_enum = CategoryType.LOJA if category == "Loja" else CategoryType.CANTINA
    st_enum = PaymentStatus.PAID if status == "PAGO" else PaymentStatus.PENDING

    # Formata a descrição para incluir a data do dia nos itens se desejar, ou grava os itens diretamente
    item_description = f"[{full_date_str}] {raw_items}"

    consumption = EventConsumption(
        person_name=person_name,
        group=grp_enum,
        category=cat_enum,
        raw_items=item_description,
        total_amount=total_amount,
        status=st_enum,
        import_batch_id=batch.id
    )
    db.add(consumption)
    db.commit()
    return RedirectResponse(url="/#pills-cantina", status_code=303)

# --- ROTAS MENSALIDADES ---

@app.post("/monthly-fees/generate")
def generate_monthly_fees(month_year: str = Form(...), db: Session = Depends(get_db)):
    existing = db.query(MonthlyFee).filter(MonthlyFee.month_year == month_year).first()
    if existing:
        raise HTTPException(status_code=400, detail="A folha deste mês já existe.")

    new_fees = [
        MonthlyFee(person_name=name, month_year=month_year, amount=90.0, status=PaymentStatus.PENDING)
        for name in MEMBERS_LIST
    ]
    db.add_all(new_fees)
    db.commit()
    return RedirectResponse(url="/#pills-fees", status_code=303)

@app.post("/monthly-fees/{fee_id}/pay")
def pay_monthly_fee(fee_id: int, db: Session = Depends(get_db)):
    fee = db.query(MonthlyFee).filter(MonthlyFee.id == fee_id).first()
    if fee:
        fee.status = PaymentStatus.PAID if fee.status == PaymentStatus.PENDING else PaymentStatus.PENDING
        db.commit()
    return RedirectResponse(url="/#pills-fees", status_code=303)

@app.post("/monthly-fees/delete-month")
def delete_monthly_fee_folder(month_year: str = Form(...), db: Session = Depends(get_db)):
    db.query(MonthlyFee).filter(MonthlyFee.month_year == month_year).delete()
    db.commit()
    return RedirectResponse(url="/#pills-fees", status_code=303)

# --- ROTAS CANTINA & LOJA ---

@app.post("/batches/{batch_id}/delete")
def delete_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if batch:
        db.delete(batch)
        db.commit()
    return RedirectResponse(url="/#pills-cantina", status_code=303)

@app.post("/consumptions/{item_id}/pay")
def mark_as_paid(item_id: int, db: Session = Depends(get_db)):
    item = db.query(EventConsumption).filter(EventConsumption.id == item_id).first()
    if item:
        item.status = PaymentStatus.PAID
        db.commit()
    return RedirectResponse(url="/#pills-cantina", status_code=303)

@app.post("/consumptions/{item_id}/delete")
def delete_consumption(item_id: int, db: Session = Depends(get_db)):
    item = db.query(EventConsumption).filter(EventConsumption.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/#pills-cantina", status_code=303)

@app.post("/consumptions/{item_id}/edit")
def edit_consumption(
    item_id: int,
    person_name: str = Form(...),
    group: str = Form(...),
    category: str = Form("Cantina"),
    raw_items: str = Form(...),
    total_amount: float = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    item = db.query(EventConsumption).filter(EventConsumption.id == item_id).first()
    if item:
        item.person_name = person_name
        item.group = GroupType.FILHO_DA_CASA if group == "Filho da Casa" else GroupType.VISITANTE
        item.category = CategoryType.LOJA if category == "Loja" else CategoryType.CANTINA
        item.raw_items = raw_items
        item.total_amount = total_amount
        item.status = PaymentStatus.PAID if status == "PAGO" else PaymentStatus.PENDING
        db.commit()
    return RedirectResponse(url="/#pills-cantina", status_code=303)

@app.post("/upload-html")
async def upload_html(
    file: UploadFile = File(...),
    month_year: str = Form(...),
    event_name: str = Form(""),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith(('.xlsx', '.xlsm')):
        raise HTTPException(status_code=400, detail="Formato de arquivo inválido")
    
    contents = await file.read()
    process_excel_file(contents, file.filename, month_year, event_name, db)
    return RedirectResponse(url="/#pills-cantina", status_code=303)