# 📊 Finance API — Gestão Financeira de Cantina e Eventos

Uma aplicação web e API REST moderna, desenvolvida para simplificar e organizar o controle financeiro de eventos, cantina e arrecadações organizadas por grupos e pastas mensais.

O sistema elimina o controle manual em papel, processa planilhas Excel automaticamente, trata divergências de valores, gerencia baixas de pagamentos pendentes e gera relatórios executivos prontos para exportação.

---

## 🚀 Funcionalidades Principais

* **📁 Organização por Pastas Mensais (Mês/Ano):** Agrupamento automático dos registros por mês e evento com totalizadores exclusivos por pasta.
* **📥 Importador Inteligente de Excel:** Leitura automatizada de arquivos `.xlsx` / `.xlsm`, com detecção de transições entre grupos (*Filhos da Casa* / *Visitantes*), tratamento de divergências e limpeza automática de rodapés e legendas.
* **📊 Dashboard Financeira Em Tempo Real:** Cards interativos exibindo *Acumulado Geral*, *Total Recebido* e *Total Pendente*.
* **⚡ Gestão Direta de Registros:** Dar baixa rápida (*PENDENTE* ➔ *PAGO*), editar valores/itens via modal interativo ou excluir lançamentos individuais.
* **🔍 Filtros e Busca Dinâmica:** Pesquisa instantânea por nome ou item consumido e filtros por grupo ou situação de pagamento sem recarregar a página.
* **🕒 Histórico de Importações & Desfazer Lote:** Controle completo de arquivos enviados, permitindo desfazer uma importação inteira com um único clique.
* **📄 Exportação e Relatórios:** Exportação do consolidado em formato `.xlsx` e geração de relatórios de cobrança em PDF limpos e formatados para impressão via CSS Print Media.

---

## 🛠️ Tecnologias Utilizadas

* **Backend:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.13+)
* **Banco de Dados:** [SQLAlchemy](https://www.sqlalchemy.org/) + SQLite
* **Frontend / Templates:** [Jinja2](https://jinja.palletsprojects.com/) + [Bootstrap 5](https://getbootstrap.com/) + Bootstrap Icons
* **Processamento de Dados:** [Pandas](https://pandas.pydata.org/) + [OpenPyXL](https://openpyxl.readthedocs.io/)
* **Servidor ASGI:** [Uvicorn](https://www.uvicorn.org/)

---

## 📁 Estrutura do Projeto

```text
financies_api/
├── app/
│   ├── __init__.py
│   ├── database.py       # Conexão e sessão do banco de dados (SQLite)
│   ├── models.py         # Mapeamento ORM (ImportBatch, EventConsumption)
│   ├── schemas.py        # Validações Pydantic
│   ├── main.py           # Endpoints da API e rotas da interface HTML
│   ├── services/
│   │   └── excel_import.py # Módulo de parsing e inteligência de planilhas
│   └── templates/
│       └── index.html    # Dashboard responsiva e modal interativo
├── .gitignore            # Regras de exclusão do repositório Git
├── requirements.txt      # Dependências do projeto
└── README.md             # Documentação do projeto


🔧 Como Executar o Projeto Localmente
Pré-requisitos

    Python 3.10 ou superior instalado.

Passo a Passo

    1. Clonar o Repositório:

        git clone [https://github.com/indiarasabarreto/financies_api.git](https://github.com/indiarasabarreto/financies_api.git)

        cd financies_api

    2. Criar e Ativar o Ambiente Virtual:

        # Linux / macOS:

        python3 -m venv .venv
        source .venv/bin/activate

        # Windows (PowerShell):

        python -m venv .venv
        .venv\Scripts\Activate.ps1

    3. Instalar as Dependências:
        
        pip install -r requirements.txt

    4. Executar a Aplicação:
        
        uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

    5. Acessar a Aplicação:

        Dashboard Web: http://127.0.0.1:8000

        Documentação Swagger: http://127.0.0.1:8000/docs