import io
import re
import os
import pandas as pd
from pathlib import Path
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Request, Form, Cookie, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db, SessionLocal
from app.models import EventConsumption, PaymentStatus, GroupType, CategoryType, ImportBatch, MonthlyFee, MenuItem
from app.services.excel_import import process_excel_file

Base.metadata.create_all(bind=engine)

APP_DIR = Path(__file__).resolve().parent

# Horário de Brasília (UTC-3). O servidor (Render) roda em UTC, então sem isso
# "hoje" virava "amanhã" depois das 21h.
BR_TZ = timezone(timedelta(hours=-3))

# Cardápio inicial (só é usado se a tabela estiver vazia)
DEFAULT_MENU = [
    ("Torta de Atum", 12.0), ("Torta de Frango", 12.0), ("Empada", 9.0),
    ("Bolo", 5.0), ("Pudim", 5.0), ("Mousse", 5.0),
    ("Refrigerante", 5.0), ("Café", 5.0), ("Suco", 3.0),
]

def seed_menu():
    db = SessionLocal()
    try:
        if db.query(MenuItem).count() == 0:
            for i, (name, price) in enumerate(DEFAULT_MENU):
                db.add(MenuItem(name=name, price=price, sort_order=i))
            db.commit()
    finally:
        db.close()

seed_menu()

def menu_item_dict(item):
    return {"id": item.id, "name": item.name, "price": float(item.price)}

def back_to_cantina(request: Request):
    """Volta para a mesma tela (e o mesmo dia) de onde o usuário veio."""
    path = "/"
    ref = request.headers.get("referer")
    if ref:
        p = urlparse(ref)
        path = p.path or "/"
        if p.query:
            path += "?" + p.query
        if not path.startswith("/") or path.startswith("//"):
            path = "/"
    return RedirectResponse(url=path + "#pills-cantina", status_code=303)

app = FastAPI(title="Finance API - Gestão de Cantina, Loja e Mensalidades")
templates = Jinja2Templates(directory=APP_DIR / "templates")

# Senha de Acesso para a Aba de Mensalidades (Padrão: 9090)
MONTHLY_FEES_PIN = os.getenv("MONTHLY_FEES_PIN", "9090")

# Senha da sub-aba "Histórico e Planilhas" (se HISTORY_PIN não for definida, usa a mesma das mensalidades)
HISTORY_PIN = os.getenv("HISTORY_PIN", MONTHLY_FEES_PIN)

# LISTA OFICIAL DE MEMBROS (INCLUINDO OS NOVOS INTEGANTES E O GRUPO FAMÍLIA)
MEMBERS_CONFIG = [
    {"name": "Eliana", "amount": 90.0},
    {"name": "Kelvin", "amount": 90.0},
    {"name": "Igor", "amount": 90.0},
    {"name": "Lívia", "amount": 90.0},
    {"name": "Nicole", "amount": 90.0},
    {"name": "Indiara", "amount": 90.0},
    {"name": "Jhon", "amount": 90.0},
    {"name": "Bruna", "amount": 90.0},
    {"name": "Talles", "amount": 90.0},
    {"name": "Isadora", "amount": 90.0},
    {"name": "Suyá", "amount": 90.0},
    {"name": "Ryan", "amount": 90.0},
    {"name": "Elaine (Bruno, Oxinho, Gabriel)", "amount": 360.0}  # R$ 90 x 4 integrantes
]

# --- AGRUPAMENTO POR DIA DE GIRA ---

DATE_PREFIX_RE = re.compile(r"^\s*\[(\d{2}/\d{2}/\d{4})\]\s*")

def extract_event_date(raw_items):
    match = DATE_PREFIX_RE.match(raw_items or "")
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d/%m/%Y").date()
    except ValueError:
        return None

def strip_event_date(raw_items):
    return DATE_PREFIX_RE.sub("", raw_items or "")

def group_by_day(consumptions):
    days = {}
    for c in consumptions:
        day = extract_event_date(c["raw_items"])
        group = days.setdefault(day, {
            "day": day,
            "consumptions": [],
            "total": 0.0,
            "pago": 0.0,
            "pendente": 0.0,
        })
        group["consumptions"].append(c)
        group["total"] += c["total_amount"]
        if c["status"] == "PAGO":
            group["pago"] += c["total_amount"]
        else:
            group["pendente"] += c["total_amount"]
    # dias em ordem do calendario; registros sem data ficam por ultimo
    return sorted(days.values(), key=lambda g: (g["day"] is None, g["day"] or date.min))

templates.env.filters["sem_data"] = strip_event_date

@app.get("/health")
def health_check():
    return {"status": "online"}

@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    dia: str | None = None,
    pin_erro: str | None = None,
    fees_auth: str | None = Cookie(default=None),
    history_auth: str | None = Cookie(default=None), 
    db: Session = Depends(get_db)
):
    is_fees_authorized = (fees_auth == "authorized")
    history_authorized = (history_auth == "authorized")

    raw_consumptions = db.query(EventConsumption).all()
    batches = db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).all()
    monthly_fees = db.query(MonthlyFee).order_by(MonthlyFee.month_year.desc()).all()
    
    # --- 1. CANTINA & LOJA ---
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

    folders = defaultdict(list)
    for c in formatted_consumptions:
        folders[c["month_year"]].append(c)

    formatted_folders = []
    cantina_paid_by_month = defaultdict(float)

    for month_year, consumptions_list in folders.items():
        f_total = sum(i["total_amount"] for i in consumptions_list)
        f_pago = sum(i["total_amount"] for i in consumptions_list if i["status"] == "PAGO")
        f_pendente = sum(i["total_amount"] for i in consumptions_list if i["status"] == "PENDENTE")
        cantina_paid_by_month[month_year] = f_pago

        formatted_folders.append({
            "month_year": month_year,
            "total_geral": f_total,
            "total_pago": f_pago,
            "total_pendente": f_pendente,
            "consumptions": consumptions_list,
            "days": group_by_day(consumptions_list)
        })

    # --- 1.1 COMANDA AO VIVO (apenas o dia escolhido; padrão = hoje) ---
    today = datetime.now(BR_TZ).date()
    try:
        live_date = datetime.strptime(dia, "%Y-%m-%d").date() if dia else today
    except ValueError:
        live_date = today

    live_consumptions = sorted(
        [c for c in formatted_consumptions if extract_event_date(c["raw_items"]) == live_date],
        key=lambda c: c["id"],
        reverse=True,  # lançamentos mais recentes primeiro
    )
    live_total = sum(c["total_amount"] for c in live_consumptions)
    live_pago = sum(c["total_amount"] for c in live_consumptions if c["status"] == "PAGO")
    live_pendente = live_total - live_pago

    menu_items = [
        menu_item_dict(i)
        for i in db.query(MenuItem).filter(MenuItem.active == True)
                   .order_by(MenuItem.sort_order, MenuItem.id).all()
    ]

    # --- 2. MENSALIDADES ---
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

    formatted_fee_folders = []
    fees_paid_by_month = defaultdict(float)

    for month_year, fee_list in fees_by_month.items():
        f_total = sum(i["amount"] for i in fee_list)
        f_pago = sum(i["amount"] for i in fee_list if i["status"] == "PAGO")
        f_pendente = sum(i["amount"] for i in fee_list if i["status"] == "PENDENTE")
        fees_paid_by_month[month_year] = f_pago

        formatted_fee_folders.append({
            "month_year": month_year,
            "total_geral": f_total,
            "total_pago": f_pago,
            "total_pendente": f_pendente,
            "fees": fee_list
        })

    # --- 3. CONSOLIDAÇÃO MENSAL GERAL ---
    all_months = sorted(list(set(list(cantina_paid_by_month.keys()) + list(fees_paid_by_month.keys()))), reverse=True)
    monthly_summary = []

    for m in all_months:
        c_pago = cantina_paid_by_month.get(m, 0.0)
        f_pago = fees_paid_by_month.get(m, 0.0)
        monthly_summary.append({
            "month_year": m,
            "cantina_pago": c_pago,
            "fees_pago": f_pago,
            "total_mes": c_pago + f_pago
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
            "monthly_summary": monthly_summary,
            "is_fees_authorized": is_fees_authorized,
            "history_authorized": history_authorized,
            "pin_erro": bool(pin_erro),
            "live_date_iso": live_date.strftime("%Y-%m-%d"),
            "live_label": live_date.strftime("%d/%m/%Y"),
            "live_is_today": live_date == today,
            "live_consumptions": live_consumptions,
            "live_total": live_total,
            "live_pago": live_pago,
            "live_pendente": live_pendente,
            "menu_items": menu_items,
        }
    )

# --- AUTENTICAÇÃO MENSALIDADES ---

@app.post("/monthly-fees/login")
def monthly_fees_login(pin: str = Form(...)):
    if pin == MONTHLY_FEES_PIN:
        response = RedirectResponse(url="/#pills-fees", status_code=303)
        response.set_cookie(key="fees_auth", value="authorized", max_age=2592000, httponly=True)
        return response
    return RedirectResponse(url="/#pills-fees", status_code=303)

@app.post("/monthly-fees/logout")
def monthly_fees_logout(response: Response):
    response = RedirectResponse(url="/#pills-cantina", status_code=303)
    response.delete_cookie("fees_auth")
    return response

# --- AUTENTICAÇÃO HISTÓRICO E PLANILHAS ---

@app.post("/history/login")
def history_login(pin: str = Form(...)):
    if pin == HISTORY_PIN:
        response = RedirectResponse(url="/#pills-cantina", status_code=303)
        response.set_cookie(key="history_auth", value="authorized", max_age=2592000, httponly=True)
        return response
    return RedirectResponse(url="/?pin_erro=1#pills-cantina", status_code=303)

@app.post("/history/logout")
def history_logout():
    response = RedirectResponse(url="/#pills-cantina", status_code=303)
    response.delete_cookie("history_auth")
    return response

# --- LANÇAMENTO DIRETO AO VIVO ---

@app.post("/consumptions/direct-add")
def add_direct_consumption(
    event_date: str = Form(...),
    person_name: str = Form(...),
    group: str = Form(...),
    category: str = Form(...),
    raw_items: str = Form(...),
    total_amount: float = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        date_obj = datetime.strptime(event_date, "%Y-%m-%d")
        full_date_str = date_obj.strftime("%d/%m/%Y")
        month_year_str = date_obj.strftime("%m/%Y")
        back_url = f"/?dia={event_date}#pills-cantina"
    except ValueError:
        full_date_str = event_date
        month_year_str = event_date
        back_url = "/#pills-cantina"

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
    if category == "Loja":
        cat_enum = CategoryType.LOJA
    elif category == "Cantina - Loja":
        cat_enum = CategoryType.CANTINA_LOJA
    else:
        cat_enum = CategoryType.CANTINA
    st_enum = PaymentStatus.PAID if status == "PAGO" else PaymentStatus.PENDING
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
    return RedirectResponse(url=back_url, status_code=303)

# --- CARDÁPIO (itens e preços da comanda ao vivo) ---

@app.post("/menu-items")
def add_menu_item(name: str = Form(...), price: float = Form(...), db: Session = Depends(get_db)):
    name = name.strip()[:80]
    if not name or price < 0:
        raise HTTPException(status_code=400, detail="Informe um nome e um valor válidos.")
    item = db.query(MenuItem).filter(func.lower(MenuItem.name) == name.lower()).first()
    if item:
        # Já existe (ou foi removido antes): atualiza o preço e reativa
        item.price = price
        item.active = True
    else:
        last = db.query(func.max(MenuItem.sort_order)).scalar() or 0
        item = MenuItem(name=name, price=price, sort_order=last + 1)
        db.add(item)
    db.commit()
    db.refresh(item)
    return menu_item_dict(item)

@app.post("/menu-items/{item_id}/update")
def update_menu_item(item_id: int, name: str = Form(...), price: float = Form(...), db: Session = Depends(get_db)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    name = name.strip()[:80]
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    if not name or price < 0:
        raise HTTPException(status_code=400, detail="Informe um nome e um valor válidos.")
    clash = db.query(MenuItem).filter(
        func.lower(MenuItem.name) == name.lower(), MenuItem.id != item_id, MenuItem.active == True
    ).first()
    if clash:
        raise HTTPException(status_code=400, detail="Já existe um item com esse nome.")
    item.name = name
    item.price = price
    db.commit()
    return menu_item_dict(item)

@app.post("/menu-items/{item_id}/delete")
def delete_menu_item(item_id: int, db: Session = Depends(get_db)):
    # Só desativa: as comandas antigas guardam o texto e não são afetadas
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if item:
        item.active = False
        db.commit()
    return {"ok": True}

# --- ROTAS MENSALIDADES ---

@app.post("/monthly-fees/generate")
def generate_monthly_fees(month_year: str = Form(...), db: Session = Depends(get_db)):
    existing = db.query(MonthlyFee).filter(MonthlyFee.month_year == month_year).first()
    if existing:
        raise HTTPException(status_code=400, detail="A folha deste mês já existe.")

    new_fees = [
        MonthlyFee(
            person_name=member["name"], 
            month_year=month_year, 
            amount=member["amount"], 
            status=PaymentStatus.PENDING
        )
        for member in MEMBERS_CONFIG
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
def mark_as_paid(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.query(EventConsumption).filter(EventConsumption.id == item_id).first()
    if item:
        item.status = PaymentStatus.PAID
        db.commit()
    return back_to_cantina(request)

@app.post("/consumptions/{item_id}/delete")
def delete_consumption(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.query(EventConsumption).filter(EventConsumption.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    return back_to_cantina(request)

@app.post("/consumptions/{item_id}/edit")
def edit_consumption(
    item_id: int,
    request: Request,
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
        if category == "Loja":
            item.category = CategoryType.LOJA
        elif category == "Cantina - Loja":
            item.category = CategoryType.CANTINA_LOJA
        else:
            item.category = CategoryType.CANTINA
        item.raw_items = raw_items
        item.total_amount = total_amount
        item.status = PaymentStatus.PAID if status == "PAGO" else PaymentStatus.PENDING
        db.commit()
    return back_to_cantina(request)

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

@app.get("/export-excel")
def export_excel(history_auth: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    # A planilha contém todo o histórico: só com a senha do histórico
    if history_auth != "authorized":
        return RedirectResponse(url="/?pin_erro=1#pills-cantina", status_code=303)
    consumptions = db.query(EventConsumption).all()
    data = []

    for c in consumptions:
        dia_evento = extract_event_date(c.raw_items)
        data.append({
            "Mês/Ano": c.import_batch.month_year if c.import_batch else "Lançamento Ao Vivo",
            "Data da Gira": dia_evento.strftime("%d/%m/%Y") if dia_evento else "Sem data",
            "Nome": c.person_name,
            "Origem": str(getattr(c.category, 'value', c.category)),
            "Grupo": str(getattr(c.group, 'value', c.group)),
            "Itens Consumidos": strip_event_date(c.raw_items),
            "Valor Bruto (R$)": float(c.total_amount),
            "Situação": str(getattr(c.status, 'value', c.status)).upper()
        })

    df = pd.DataFrame(data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Cantina e Loja")

    output.seek(0)
    return StreamingResponse(
        output, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
        headers={"Content-Disposition": "attachment; filename=Relatorio_Terreiro.xlsx"}
    )