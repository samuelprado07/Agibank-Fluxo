# Agibank Fluxo

Aplicação de planejamento financeiro preventivo voltada especialmente a aposentados, pensionistas e pessoas com renda limitada. O objetivo é antecipar possíveis faltas de saldo, ajudar o cliente a compreender seus compromissos e avaliar alternativas antes que a situação se agrave.

## Funcionalidades

- Cadastro com nome, e-mail e senha, login por e-mail e senha, encerramento de sessão e planejamento separado por usuário.

- Dashboard com saldo atual, próximo recebimento, despesas essenciais e projeção diária inicial de 15 dias. A análise pode se estender até o próximo recebimento, respeitando o limite de 60 dias.
- Alertas de insuficiência e ausência de margem, incluindo situações em que o saldo fica negativo durante o dia e termina positivo. Os marcadores do gráfico abrem um resumo dos compromissos em risco.
- Cadastro e gestão de despesas, essencialidade, estimativas variáveis e recorrências mensais com ocorrências independentes.
- Renda única ou mensal, ajustes de previsões, identificação de atrasos e confirmação de recebimentos.
- Registro, correção e desfazimento de pagamentos e recebimentos, com histórico e prevenção de dupla contagem.
- Simulação de alterações de valor ou data de uma ocorrência pendente, com comparação antes/depois e aplicação somente mediante ação explícita.
- Assistente Gemini para explicar resultados calculados pelo backend, com histórico temporário e identificação de respostas referentes a projeções anteriores.
- Contingência local identificada como **“Explicações automáticas demonstrativas”** quando ocorrerem falhas elegíveis da IA.
- Solicitação de atendimento humano registrada no chat local. O encaminhamento a uma central real ainda não está integrado.
- Interface responsiva para desktop e smartphones.

## Stack e organização

| Camada | Tecnologia / localização |
| --- | --- |
| Interface | React + Vite + JavaScript, em `frontend/src/` |
| API e configuração | Python + Django, em `backend/config/` |
| Regras financeiras | Serviços em `backend/finance/services/` |
| Persistência | SQLite, Django ORM e migrações em `backend/finance/` |
| Assistente | SDK oficial `google-genai`, acessado exclusivamente pelo backend |
| Testes | `backend/finance/tests/` e `backend/core/tests.py` |

Os cálculos, projeções e alertas são determinísticos e independentes da IA. O assistente não pode confirmar pagamentos, editar cadastros ou aplicar alternativas. As projeções são estimativas condicionadas aos dados cadastrados e aos recebimentos previstos; limites de crédito não compõem recursos próprios.

## Pré-requisitos

- Python 3.12, versão validada no desenvolvimento.
- Node.js 22.12 ou superior e npm.
- Git para clonar e versionar o projeto.
- Chave da API Gemini, opcional para usar as respostas da IA. Sem chave, o assistente oferece explicações locais; as demais funcionalidades continuam disponíveis.

Os comandos abaixo utilizam **PowerShell no Windows**, partindo da raiz do repositório. Não é necessário ativar o ambiente virtual.

## Primeira execução: ordem de configuração

### 1. Abrir o projeto e configurar o ambiente

Após clonar o repositório, abra um terminal na pasta que contém `backend/`, `frontend/` e `.env.example`.

Crie o arquivo de configuração somente se ele ainda não existir:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edite o `.env` na raiz e configure:

```dotenv
DJANGO_SECRET_KEY=sua-chave-local-do-django
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
GEMINI_API_KEY=sua-chave-do-gemini
GEMINI_MODEL=gemini-3.6-flash
```

A disponibilidade do modelo depende do acesso e dos limites da conta Gemini. A variável `GEMINI_MODEL` permite trocar o modelo. Para usar somente as explicações locais, deixe `GEMINI_API_KEY` vazia.

O Django carrega esse arquivo sem sobrescrever variáveis já definidas no processo. Reinicie o backend após modificar o `.env`. A chave Gemini deve permanecer no backend, sem prefixo `VITE_` e sem ser incluída em commits.

### 2. Criar o ambiente virtual Python

```powershell
python -m venv backend/.venv
```

### 3. Instalar as dependências do backend

```powershell
& ./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

### 4. Criar ou atualizar o banco de dados

```powershell
& ./backend/.venv/Scripts/python.exe backend/manage.py migrate
```

O SQLite será criado em `backend/db.sqlite3`. Não é necessário instalar um servidor de banco de dados.

### 5. Carregar o cenário inicial

```powershell
& ./backend/.venv/Scripts/python.exe backend/manage.py load_demo
```

Esse comando cria o cenário inicial com referência em **22/10/2026**, sem apagar os registros existentes. Ao executá-lo novamente, o cenário de mesmo nome é preservado, sem duplicar sua carga. As datas exibidas seguem a referência do cenário, não o relógio do computador.

Sem cenário cadastrado, o dashboard apresenta o estado inicial sem dados. O primeiro usuário cadastrado recebe o primeiro cenário ainda sem proprietário. As contas seguintes começam com um planejamento vazio e saldo zero; cada conta acessa somente seus próprios dados.

### 6. Instalar as dependências do frontend

```powershell
npm ci --prefix frontend
```

O comando utiliza `frontend/package-lock.json` para instalar as versões resolvidas das dependências.

## Executar a aplicação

Mantenha dois terminais abertos, ambos inicialmente na raiz do projeto.

**Terminal 1 — iniciar o backend:**

```powershell
& ./backend/.venv/Scripts/python.exe backend/manage.py runserver 127.0.0.1:8000
```

**Terminal 2 — iniciar o frontend:**

```powershell
npm run dev --prefix frontend
```

Abra [http://127.0.0.1:5173](http://127.0.0.1:5173). O Vite encaminha as chamadas `/api/` ao Django em `127.0.0.1:8000`. As portas devem estar disponíveis. Encerre cada servidor com `Ctrl+C` no respectivo terminal.

Nas próximas execuções, basta iniciar os dois servidores. Após atualizar o código, instale novamente as dependências caso seus arquivos tenham mudado e execute `migrate` quando houver novas migrações. Não é necessário recarregar o cenário inicial para preservar seu uso normal.

## Cadastro, login e sessão

Ao abrir a aplicação sem sessão, entre com o e-mail e a senha cadastrados. Se ainda não tiver uma conta, selecione **Criar conta** e preencha nome, e-mail, senha e confirmação. O cadastro inicia a sessão automaticamente. O nome informado aparece no dashboard, e a opção **Sair da conta** encerra a sessão e retorna ao login.

Você pode voltar a entrar para continuar no mesmo planejamento. O e-mail de acesso não diferencia letras maiúsculas e minúsculas; a senha é conferida exatamente como foi cadastrada. A sessão encerra ao sair da conta ou fechar a sessão do navegador, conforme a configuração do Django. Recuperação de senha e confirmação de e-mail não estão incluídas nesta etapa.

As senhas são protegidas pelo hash do Django. As rotas financeiras exigem sessão, e a migração `0008_scenario_owner` vincula cada planejamento ao proprietário sem apagar os registros existentes. Execute `migrate` antes de iniciar esta versão. O assistente e as simulações também respeitam o proprietário dos dados.

## Como o assistente funciona

O backend fornece contexto estruturado da projeção, dos alertas e de alternativas já calculadas. Números mencionados nas respostas são resolvidos a partir de referências validadas pelo servidor. Cada resposta identifica a projeção utilizada; quando os dados mudam, respostas antigas são sinalizadas.

Perguntas e dados necessários do planejamento, incluindo descrições dos compromissos, são enviados ao Gemini quando a integração está disponível. A conversa fica temporariamente na sessão da interface, sem histórico persistido no banco.

A chamada ao provedor tem timeout de 25 segundos e uma tentativa por pergunta. Falhas elegíveis de conexão, limite de uso, configuração ou resposta inválida acionam as explicações locais identificadas. Bloqueios de conteúdo e erros de contexto não são contornados. Na próxima pergunta, o sistema tenta o Gemini novamente.

## Verificação e testes

Na raiz do projeto:

```powershell
& ./backend/.venv/Scripts/python.exe backend/manage.py check
& ./backend/.venv/Scripts/python.exe backend/manage.py makemigrations --check --dry-run
& ./backend/.venv/Scripts/python.exe -m pip check
npm run lint --prefix frontend
npm run build --prefix frontend
```

Para executar todos os testes do backend:

```powershell
Set-Location backend
& ./.venv/Scripts/python.exe manage.py test --noinput
Set-Location ..
```

Os testes automatizados do assistente simulam o provedor, sem consumir a API Gemini. O comando `npm run build` gera a interface estática em `frontend/dist/`; ele não inicia o Django. O proxy da API está configurado no servidor de desenvolvimento; `npm run preview` não substitui a execução conjunta descrita acima.

## Limites do MVP

Execução local, um cenário por usuário e ausência de infraestrutura de produção. O cadastro ainda não inclui confirmação de e-mail ou recuperação de senha. Os registros representam um planejamento, sem conexão com contas bancárias ou canais reais de atendimento. Nenhuma projeção autoriza ou executa pagamentos. A opção de atendimento humano registra apenas uma solicitação local no chat.

O Git ignora `.env`, ambiente virtual, dependências, banco SQLite e arquivos de build. O `.env.example`, os arquivos de dependências e as migrações devem acompanhar o repositório para permitir configurar o projeto em outra máquina.
