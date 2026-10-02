"""
Backup dos dados do finance-db (somente LEITURA: so faz SELECT, nao altera nada).

Como usar (no terminal, dentro da pasta do projeto, com o .venv ativado):
  1) Copie a "External Database URL" no painel do Render (botao de copiar).
  2) Rode:  python backup_dados.py

O script le a URL da area de transferencia (pbpaste) e NAO mostra a URL na tela.
Gera na pasta atual:
  - backup_finance_AAAA-MM-DD.xlsx  (uma aba por tabela)
  - backup_<tabela>_AAAA-MM-DD.csv  (um CSV por tabela)
"""
import os
import subprocess
import sys
from datetime import date

import pandas as pd
from sqlalchemy import create_engine, inspect, text

TABELAS = ["import_batches", "event_consumptions", "monthly_fees"]


def obter_url():
    url = os.getenv("BACKUP_DATABASE_URL")
    if not url:
        try:
            url = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True).stdout
        except Exception:
            url = ""
    url = (url or "").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not (url.startswith("postgresql://") or url.startswith("sqlite")):
        print("A area de transferencia nao parece conter uma URL de banco (deve comecar com postgresql://).")
        print("Copie de novo a External Database URL no painel do Render e rode o script outra vez.")
        sys.exit(1)
    return url


def main():
    engine = create_engine(obter_url())
    hoje = date.today().isoformat()
    existentes = set(inspect(engine).get_table_names())
    arquivo_xlsx = f"backup_finance_{hoje}.xlsx"

    total = 0
    with pd.ExcelWriter(arquivo_xlsx, engine="openpyxl") as writer:
        with engine.connect() as conn:
            for tabela in TABELAS:
                if tabela not in existentes:
                    print(f"- {tabela}: tabela nao encontrada (pulando)")
                    continue
                df = pd.read_sql(text(f"SELECT * FROM {tabela}"), conn)
                df.to_excel(writer, sheet_name=tabela[:31], index=False)
                df.to_csv(f"backup_{tabela}_{hoje}.csv", index=False, encoding="utf-8-sig")
                print(f"- {tabela}: {len(df)} registros salvos")
                total += len(df)

    print(f"\nPronto! {total} registros no total.")
    print(f"Arquivo principal: {arquivo_xlsx}")


if __name__ == "__main__":
    main()
