# NEXUS

O NEXUS será uma camada de controle para operações solicitadas por agentes de IA. O projeto está sendo construído incrementalmente; **a API atual apenas simula decisões e não executa pagamentos reais**.

## Estado atual: Etapa 6 — NEXUS 0.6

Esta entrega acrescenta o **NEXUS Control Center**, uma interface empresarial responsiva servida pelo próprio FastAPI. Usuários humanos podem consultar métricas, operações, agentes, pendências e auditoria, além de executar as ações já protegidas pelo backend. Cada operação preserva um snapshot versionado da política usada. Nenhum pagamento ou efeito externo é executado.

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
└── web/             # templates e módulos HTML/CSS/JS do Control Center
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

## Preparar banco, administrador e dados de demonstração

O seed nunca é executado automaticamente. Com o ambiente virtual ativo, aplique a migração e execute explicitamente o seed:

```powershell
$env:NEXUS_DATABASE_URL = "sqlite:///./nexus.db"
alembic upgrade head
nexus-seed
```

O comando cria a empresa `NEXUS Demo` e o agente `Purchasing Agent`, com permissão `purchase`. Uma API key é gerada pelo servidor e exibida uma única vez; guarde-a localmente, pois somente o hash fica no banco. Para iniciar a API:

Crie explicitamente o primeiro administrador, sem senha padrão:

```powershell
$env:NEXUS_ADMIN_PASSWORD = "escolha-uma-senha-forte-123A"
nexus-create-admin --company-name "NEXUS Demo" --company-slug nexus-demo --name "Administrador" --email "admin@example.com"
Remove-Item Env:NEXUS_ADMIN_PASSWORD
```

Se a variável não for definida, o comando solicita a senha por entrada segura.

```powershell
uvicorn nexus.api.app:app --reload
```

A API ficará disponível em `http://127.0.0.1:8000`. As variáveis são definidas somente na sessão atual do PowerShell. O arquivo `.env.example` serve como referência e não é carregado automaticamente.

Abra `http://127.0.0.1:8000/` para acessar o Control Center. O navegador usa um cookie de sessão `HttpOnly`, `SameSite=Strict`; o JavaScript nunca recebe o token opaco. Em produção HTTPS, defina `NEXUS_COOKIE_SECURE=true`.

### Dataset visual completo

Para criar explicitamente uma empresa, administrador, agente e exemplos autorizados, bloqueados, pendentes, aprovados e rejeitados em um banco vazio:

```powershell
$env:NEXUS_DEMO_ADMIN_PASSWORD = "escolha-uma-senha-forte-123A"
nexus-seed-dashboard
Remove-Item Env:NEXUS_DEMO_ADMIN_PASSWORD
```

Entre com empresa `nexus-demo`, e-mail `admin@nexus.demo` e a senha escolhida. A API key do agente é exibida uma única vez no terminal. Esse comando é somente para desenvolvimento e nunca roda no startup.

### Swagger

1. Abra `http://127.0.0.1:8000/docs` no navegador.
2. Clique em **Authorize** e informe a API key mostrada pelo `nexus-seed` ou criada por um administrador.
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

### Demonstrar uma aprovação

1. No Swagger, autorize `AgentApiKey` com a chave do seed e envie uma compra de `100000` centavos em `POST /api/v1/operations`.
2. Faça login em `POST /api/v1/auth/login` com o administrador ou um `approver` e copie o token `nxs_us_…`.
3. Autorize `HumanSession` com esse token e consulte `GET /api/v1/approvals`.
4. Use o `operation_id` em `POST /api/v1/approvals/{operation_id}/decision` com `approved` ou `rejected`.
5. Consulte `GET /api/v1/audit-events` para ver a solicitação, o resultado da política e a decisão humana. Nenhuma ação financeira é executada.

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
4. **Concluída:** autenticação separada, autorização administrativa e isolamento multiempresa.
5. **Concluída:** aprovação humana idempotente e trilha de auditoria.
6. **Concluída:** NEXUS Control Center responsivo.
7. Integração e testes de segurança/concorrência.
8. Documentação final e demonstração funcional.

Consulte também [`docs/dashboard.md`](docs/dashboard.md) para a arquitetura, segurança e páginas do Control Center.
