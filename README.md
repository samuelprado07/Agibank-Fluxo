# Agibank Preventivo

MVP demonstrativo de acompanhamento financeiro preventivo, voltado inicialmente a aposentados e pensionistas. Ambiente exclusivamente local, com dados fictícios e sem integração bancária real.

## Etapa atual

Base React + Vite, Django + SQLite, endpoint de saúde e tela de verificação da conexão. Funcionalidades financeiras, carga de cenários e assistente ainda não foram implementados.

## Pré-requisitos

- Python 3.12 ou superior compatível com Django 5.2.
- Node.js 22.12 ou superior (ambiente validado com Node 24.14.1).
- npm e Git.

Os comandos abaixo são para PowerShell, executados inicialmente na raiz do projeto. Use um Python funcional: se `python --version` abrir a Microsoft Store ou falhar, substitua `python` pelo caminho do interpretador instalado.

## Configuração inicial

```powershell
Copy-Item .env.example .env
python -m venv backend/.venv
& ./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
& ./backend/.venv/Scripts/python.exe backend/manage.py migrate
Set-Location frontend
npm ci
Set-Location ..
```

Não é necessário ativar o ambiente virtual. O arquivo `.env` fica na raiz e é carregado pelo Django, sem sobrescrever variáveis já definidas no processo. SQLite será criado em `backend/db.sqlite3`.

### Python disponível nesta máquina

Na preparação inicial, os atalhos `python` e `py` do Windows não funcionaram. Foi usado o interpretador já fornecido pelo aplicativo Codex:

```powershell
& "$env:USERPROFILE/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe" -m venv backend/.venv
```

Esse caminho é específico desta máquina; uma instalação convencional de Python também pode ser usada. O ambiente virtual deve ser recriado ao mover o projeto para outro computador.

## Executar localmente

Terminal 1, na raiz:

```powershell
& ./backend/.venv/Scripts/python.exe backend/manage.py runserver 127.0.0.1:8000
```

Terminal 2, na raiz:

```powershell
Set-Location frontend
npm run dev
```

Abra http://127.0.0.1:5173. O Vite encaminha `/api` para `http://127.0.0.1:8000`, sem dependência de CORS. A tela confirma a conexão e permite tentar novamente se houver falha. Encerre os servidores com `Ctrl+C`.

O endpoint `GET /api/health/` retorna:

```json
{"status": "ok", "service": "agibank-preventivo"}
```

Ele verifica a disponibilidade HTTP da aplicação; não testa banco de dados nem OpenAI.

## Verificações

Na raiz:

```powershell
& ./backend/.venv/Scripts/python.exe backend/manage.py check
& ./backend/.venv/Scripts/python.exe backend/manage.py makemigrations --check --dry-run
```

Para descobrir e executar todos os testes, use o diretório do backend:

```powershell
Set-Location backend
& ./.venv/Scripts/python.exe manage.py test
Set-Location ..
```

Em `frontend/`:

```powershell
npm run lint
npm run build
```

O proxy da API existe no servidor de desenvolvimento. `npm run preview` serve apenas para inspecionar o build estático; não configura integração de produção com Django.

## Configuração e segurança

- `DJANGO_DEBUG`: `true` para desenvolvimento local.
- `DJANGO_SECRET_KEY`: chave do Django; o valor demonstrativo não serve para publicação.
- `DJANGO_ALLOWED_HOSTS`: hosts separados por vírgula; padrão `localhost,127.0.0.1`.
- `OPENAI_API_KEY`: reservada à próxima etapa; pode ficar vazia e nunca deve receber prefixo `VITE_`.

Credenciais, banco local, ambiente virtual e dependências estão ignorados pelo Git. A API não utiliza a chave da OpenAI nesta etapa. Requisições futuras de escrita deverão manter proteção CSRF; a rota de saúde aceita apenas leitura.

## Organização

- `frontend/src/`: interface React e cliente HTTP nativo com `fetch`.
- `backend/config/`: configuração e rotas do Django.
- `backend/core/`: endpoint de saúde e seus testes.
- `backend/requirements.txt`: dependências Python fixadas.
- `frontend/package-lock.json`: resolução reproduzível das dependências JavaScript.

As próximas etapas separarão motor financeiro, persistência dos cenários e serviço do assistente, conforme os requisitos aprovados. Não há autenticação, dados reais ou configuração de produção nesta entrega.
