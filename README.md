# NEXUS

O NEXUS será uma camada de controle para operações solicitadas por agentes de IA. O projeto está sendo construído incrementalmente; **a API atual apenas simula decisões e não executa pagamentos reais**.

## Estado atual: Etapa 3 — NEXUS 0.3

Esta entrega conecta a API FastAPI ao SQLite por SQLAlchemy 2.x. Empresas, usuários, agentes, permissões e decisões agora são persistentes, enquanto o motor de autorização continua puro e independente:

- operação não permitida ou agente inativo: `blocked`;
- valor até o limite automático (inclusive): `authorized`;
- valor entre o limite automático e o máximo (inclusive): `pending_approval`;
- valor acima do máximo: `blocked`.

Valores monetários são inteiros em centavos. A política fica no servidor e nunca é aceita no corpo enviado pelo agente. A API não executa a operação autorizada e não realiza pagamentos.

## Arquitetura proposta

```text
src/nexus/
├── api/             # rotas e contratos HTTP (Etapa 2+)
├── domain/          # entidades, tipos e regras puras
├── database/        # engine, sessões e modelos SQLAlchemy
├── repositories/    # consultas sempre delimitadas por empresa
├── services/        # autorização persistente e idempotência
├── security/        # autenticação de usuários/agentes (Etapa 4)
├── audit/           # eventos imutáveis de auditoria (Etapa 5)
└── web/             # painel HTML/CSS/JS (Etapa 6)
tests/               # testes automatizados
docs/                # decisões, endpoints e segurança
```

A dependência aponta das bordas para o domínio. Assim, a regra de autorização pode ser testada sem FastAPI ou SQLAlchemy. A API identifica o agente pelo hash do token, deriva a empresa do registro persistido e o serviço monta a política antes de chamar o mesmo motor. Tipos e sessões SQLAlchemy mantêm a troca futura de SQLite por PostgreSQL concentrada principalmente na URL de conexão.

## Instalação no Windows (terminal do VS Code)

Pré-requisito: Python 3.12 instalado e disponível como `py`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Se o PowerShell impedir a ativação, execute `Set-ExecutionPolicy -Scope Process Bypass` apenas para a sessão atual e tente novamente.

## Executar os testes

```powershell
pytest
```

## Preparar banco e dados de demonstração

O seed nunca é executado automaticamente. Com o ambiente virtual ativo, configure um token local de no mínimo 32 caracteres, aplique a migração e execute explicitamente o seed:

```powershell
$env:NEXUS_DEV_AGENT_TOKEN = "troque-por-um-token-local-longo-e-aleatorio"
$env:NEXUS_DATABASE_URL = "sqlite:///./nexus.db"
alembic upgrade head
nexus-seed
```

O comando cria a empresa `NEXUS Demo` e o agente `Purchasing Agent`, com permissão `purchase`. O token original não é persistido nem exibido. Para iniciar a API:

```powershell
uvicorn nexus.api.app:app --reload
```

A API ficará disponível em `http://127.0.0.1:8000`. As variáveis são definidas somente na sessão atual do PowerShell. O arquivo `.env.example` serve como referência e não é carregado automaticamente.

### Swagger

1. Abra `http://127.0.0.1:8000/docs` no navegador.
2. Clique em **Authorize** e informe o valor de `NEXUS_DEV_AGENT_TOKEN`.
3. Expanda `POST /api/v1/operations`, clique em **Try it out** e use, por exemplo:

```json
{
  "request_id": "01950000-0000-7000-8000-000000000099",
  "operation": "purchase",
  "amount_cents": 30000
}
```

4. Clique em **Execute** para consultar a decisão simulada. O esquema OpenAPI também está disponível em `http://127.0.0.1:8000/openapi.json`.

O agente de demonstração permite somente `purchase`, autoriza automaticamente até 50.000 centavos, exige aprovação até 200.000 centavos e bloqueia valores maiores. Essa configuração vem do banco; campos adicionais, incluindo limites ou empresa, são rejeitados. Para o mesmo agente, repetir o mesmo `request_id` e payload retorna a decisão existente, enquanto reutilizá-lo com conteúdo diferente retorna HTTP `409`. Cada agente possui seu próprio namespace de `request_id`.

## Exemplo do motor

```python
from uuid import uuid4
from nexus.domain.authorization import AgentPolicy, OperationRequest, evaluate_operation

policy = AgentPolicy(
    agent_id=uuid4(),
    company_id=uuid4(),
    active=True,
    allowed_operations={"purchase"},
    automatic_limit_cents=50_000,
    maximum_limit_cents=200_000,
)
decision = evaluate_operation(
    policy,
    OperationRequest(request_id=uuid4(), operation="purchase", amount_cents=30_000),
)
print(decision.outcome)  # authorized
```

## Plano incremental

1. **Concluída:** arquitetura, ambiente e motor inicial.
2. **Concluída:** API FastAPI e testes das políticas via HTTP.
3. **Concluída:** SQLite/SQLAlchemy, empresas, usuários, agentes e solicitações.
4. Autenticação separada, autorização administrativa e isolamento multiempresa.
5. Aprovação humana idempotente e trilha de auditoria.
6. Painel web responsivo.
7. Integração e testes de segurança/concorrência.
8. Documentação final e demonstração funcional.

Consulte [`docs/architecture.md`](docs/architecture.md), [`docs/data-model.md`](docs/data-model.md), [`docs/api.md`](docs/api.md) e [`docs/security.md`](docs/security.md) para o desenho e as limitações atuais.
