import io
import pandas as pd
from pathlib import Path
from collections import defaultdict
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.models import EventConsumption, PaymentStatus, GroupType, ImportBatch
from app.schemas import EventConsumptionResponse
from app.services.excel_import import process_excel_file

Base.metadata.create_all(bind=engine)

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Finance API - Gestão de Cantina e Eventos")
templates = Jinja2Templates(directory=APP_DIR / "templates")

@app.get("/health")
def health_check():
    return {"status": "online"}

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    raw_consumptions = db.query(EventConsumption).all()
    batches = db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).all()
    
    total_geral = 0.0
    total_pago = 0.0
    total_pendente = 0.0
    formatted_consumptions = []

    for item in raw_consumptions:
        amount = float(item.total_amount or 0.0)
        total_geral += amount
        
        status_val = str(getattr(item.status, 'value', item.status)).upper()
        group_val = str(getattr(item.group, 'value', item.group))

        if status_val == "PAGO":
            total_pago += amount
        else:
            total_pendente += amount

        batch_month = item.import_batch.month_year if item.import_batch else "Outros"
        batch_event = item.import_batch.event_name if item.import_batch else "Sem Evento"

        formatted_consumptions.append({
            "id": item.id,
            "person_name": item.person_name,
            "group": group_val,
            "raw_items": item.raw_items,
            "total_amount": amount,
            "status": status_val,
            "month_year": batch_month,
            "event_name": batch_event
        })

    # Agrupa consumos por pasta (Mês/Ano)
    folders = defaultdict(list)
    for c in formatted_consumptions:
        folders[c["month_year"]].append(c)

    formatted_folders = []
    for month_year, items in folders.items():
        f_total = sum(i["total_amount"] for i in items)
        f_pago = sum(i["total_amount"] for i in items if i["status"] == "PAGO")
        f_pendente = sum(i["total_amount"] for i in items if i["status"] == "PENDENTE")
        formatted_folders.append({
            "month_year": month_year,
            "total_geral": f_total,
            "total_pago": f_pago,
            "total_pendente": f_pendente,
            "items": items
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
            "batches": formatted_batches,
            "total_geral": total_geral,
            "total_pago": total_pago,
            "total_pendente": total_pendente,
        }
    )

@app.get("/export-excel")
def export_excel(db: Session = Depends(get_db)):
    consumptions = db.query(EventConsumption).all()
    
    data = []
    for item in consumptions:
        status_val = str(getattr(item.status, 'value', item.status)).upper()
        group_val = str(getattr(item.group, 'value', item.group))
        batch_month = item.import_batch.month_year if item.import_batch else "Outros"
        
        data.append({
            "PASTA (MÊS/ANO)": batch_month,
            "NOME": item.person_name,
            "GRUPO": group_val,
            "ITENS CONSUMIDOS": item.raw_items,
            "VALOR (R$)": item.total_amount,
            "SITUAÇÃO": status_val
        })
    
    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Consumo_Cantina")
    
    output.seek(0)
    
    headers = {
        'Content-Disposition': 'attachment; filename="relatorio_cantina_consolidado.xlsx"'
    }
    return StreamingResponse(
        output, 
        headers=headers, 
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.post("/batches/{batch_id}/delete")
def delete_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    
    db.delete(batch)
    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.post("/consumptions/{item_id}/pay")
def mark_as_paid(item_id: int, db: Session = Depends(get_db)):
    item = db.query(EventConsumption).filter(EventConsumption.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    item.status = PaymentStatus.PAID
    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.post("/consumptions/{item_id}/delete")
def delete_consumption(item_id: int, db: Session = Depends(get_db)):
    item = db.query(EventConsumption).filter(EventConsumption.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    db.delete(item)
    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.post("/consumptions/{item_id}/edit")
def edit_consumption(
    item_id: int,
    person_name: str = Form(...),
    group: str = Form(...),
    raw_items: str = Form(...),
    total_amount: float = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    item = db.query(EventConsumption).filter(EventConsumption.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    
    item.person_name = person_name
    item.group = GroupType.FILHO_DA_CASA if group == "Filho da Casa" else GroupType.VISITANTE
    item.raw_items = raw_items
    item.total_amount = total_amount
    item.status = PaymentStatus.PAID if status == "PAGO" else PaymentStatus.PENDING

    db.commit()
    return RedirectResponse(url="/", status_code=303)

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
    return RedirectResponse(url="/", status_code=303)