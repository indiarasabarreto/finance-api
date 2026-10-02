"""
Copia os dados do banco ANTIGO (Render) para o banco NOVO (Neon).

- O banco antigo e apenas LIDO (nada e alterado ou apagado nele).
- O banco novo precisa estar VAZIO (o script se recusa a rodar se ja houver dados).
- As URLs sao digitadas/coladas com a entrada oculta: nao aparecem na tela.

Rode na pasta principal do projeto, com o .venv ativo:
    python migrar_para_neon.py
"""
import sys
from getpass import getpass

from sqlalchemy import create_engine, func, select, text

from app.database import Base
import app.models  # noqa: F401  (registra as tabelas em Base.metadata)

ORDEM = ["import_batches", "event_consumptions", "monthly_fees"]


def normalizar(url):
    url = (url or "").strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not (url.startswith("postgresql://") or url.startswith("sqlite")):
        print("A URL deve comecar com postgresql:// . Confira o que foi colado.")
        sys.exit(1)
    return url


def contar(conn, tabela):
    return conn.execute(select(func.count()).select_from(tabela)).scalar_one()


def main():
    print("Cole a URL do banco ANTIGO (Render - External Database URL) e tecle Enter.")
    origem = create_engine(normalizar(getpass("URL antiga (oculta): ")))
    print("\nCole a URL do banco NOVO (Neon) e tecle Enter.")
    destino = create_engine(normalizar(getpass("URL nova (oculta): ")))

    if str(origem.url) == str(destino.url):
        print("As duas URLs sao iguais. Abortando para nao misturar os dados.")
        sys.exit(1)

    tabelas = {t.name: t for t in Base.metadata.sorted_tables}
    faltando = [n for n in ORDEM if n not in tabelas]
    if faltando:
        print("Tabelas nao encontradas nos modelos:", faltando)
        sys.exit(1)

    # 1) cria as tabelas no banco novo (mesma estrutura do app)
    Base.metadata.create_all(bind=destino)

    # 2) seguranca: o destino precisa estar vazio
    with destino.connect() as d:
        ocupadas = [n for n in ORDEM if contar(d, tabelas[n]) > 0]
    if ocupadas:
        print("O banco NOVO ja tem dados em:", ocupadas)
        print("Abortando para nao duplicar registros. (Use um banco novo e vazio.)")
        sys.exit(1)

    # 3) copia tabela por tabela, preservando os ids
    print("\nCopiando...")
    with origem.connect() as o, destino.begin() as d:
        for nome in ORDEM:
            t = tabelas[nome]
            linhas = [dict(r._mapping) for r in o.execute(select(t))]
            if linhas:
                d.execute(t.insert(), linhas)
            print(f"- {nome}: {len(linhas)} registros copiados")

        # 4) acerta os contadores de id (so no Postgres)
        if destino.dialect.name == "postgresql":
            for nome in ORDEM:
                d.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{nome}', 'id'), "
                    f"(SELECT COALESCE(MAX(id), 0) + 1 FROM {nome}), false)"
                ))

    # 5) conferencia
    print("\nConferencia (antigo x novo):")
    ok = True
    with origem.connect() as o, destino.connect() as d:
        for nome in ORDEM:
            a, b = contar(o, tabelas[nome]), contar(d, tabelas[nome])
            marca = "OK" if a == b else "DIFERENTE!"
            if a != b:
                ok = False
            print(f"- {nome}: {a} x {b}  {marca}")
    print("\nTUDO CERTO!" if ok else "\nATENCAO: os numeros nao batem. Nao troque a DATABASE_URL ainda.")


if __name__ == "__main__":
    main()
