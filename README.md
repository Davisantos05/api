# NEXUS

O NEXUS será uma camada de controle para operações solicitadas por agentes de IA. O projeto está sendo construído incrementalmente; **a API atual apenas simula decisões e não executa pagamentos reais**.

## Estado atual: Etapa 2 — NEXUS 0.2

Esta entrega adiciona uma API FastAPI ao motor de autorização puro, ainda sem interface ou banco de dados. Ela recebe uma operação simulada, identifica provisoriamente o agente por um token local e devolve uma decisão explicável:

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
├── services/        # casos de uso e orquestração
├── models/          # modelos SQLAlchemy (Etapa 3)
├── security/        # autenticação de usuários/agentes (Etapa 4)
├── audit/           # eventos imutáveis de auditoria (Etapa 5)
└── web/             # painel HTML/CSS/JS (Etapa 6)
tests/               # testes automatizados
docs/                # decisões, endpoints e segurança
```

A dependência aponta das bordas para o domínio. Assim, a regra de autorização pode ser testada sem FastAPI ou SQLAlchemy e continuará igual ao trocar SQLite por PostgreSQL. Nesta etapa, a API identifica o agente e seleciona uma política em memória; futuramente, buscará a política e o `company_id` no banco antes de chamar o mesmo motor.

## Instalação no Windows (terminal do VS Code)

Pré-requisito: Python 3.12 instalado e disponível como `py`.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Se o PowerShell impedir a ativação, execute `Set-ExecutionPolicy -Scope Process Bypass` apenas para a sessão atual e tente novamente.

## Executar os testes

```powershell
pytest
```

## Iniciar a API no Windows

Com o ambiente virtual ativo, configure um token local de no mínimo 32 caracteres e inicie o Uvicorn:

```powershell
$env:NEXUS_DEV_AGENT_TOKEN = "troque-por-um-token-local-longo-e-aleatorio"
uvicorn nexus.api.app:app --reload
```

A API ficará disponível em `http://127.0.0.1:8000`. A variável é definida somente na sessão atual do PowerShell. O arquivo `.env.example` serve como referência e não é carregado automaticamente.

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

O agente provisório permite somente `purchase`, autoriza automaticamente até 50.000 centavos, exige aprovação até 200.000 centavos e bloqueia valores maiores. Essa configuração existe no servidor; campos adicionais, incluindo limites ou empresa, são rejeitados.

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
3. SQLite/SQLAlchemy, empresas, usuários e agentes.
4. Autenticação separada, autorização administrativa e isolamento multiempresa.
5. Aprovação humana idempotente e trilha de auditoria.
6. Painel web responsivo.
7. Integração e testes de segurança/concorrência.
8. Documentação final e demonstração funcional.

Consulte [`docs/architecture.md`](docs/architecture.md), [`docs/api.md`](docs/api.md) e [`docs/security.md`](docs/security.md) para limites e decisões planejadas.
