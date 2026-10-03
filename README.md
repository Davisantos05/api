# NEXUS

O NEXUS será uma camada de controle para operações solicitadas por agentes de IA. O projeto está sendo construído incrementalmente; **a Etapa 1 não é uma API financeira nem executa pagamentos reais**.

## Estado atual: Etapa 1

Esta entrega contém um motor de autorização puro, sem interface, API ou banco de dados. Ele recebe uma política confiável do agente e uma solicitação validada e devolve uma decisão explicável:

- operação não permitida ou agente inativo: `blocked`;
- valor até o limite automático (inclusive): `authorized`;
- valor entre o limite automático e o máximo (inclusive): `pending_approval`;
- valor acima do máximo: `blocked`.

Valores monetários são inteiros em centavos. A política é uma entrada interna do motor: quando a API for criada, ela será carregada pelo servidor, nunca aceita do agente.

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

A dependência aponta das bordas para o domínio. Assim, a regra de autorização pode ser testada sem FastAPI ou SQLAlchemy e continuará igual ao trocar SQLite por PostgreSQL. A futura API será responsável por autenticar a credencial do agente, buscar a política e o `company_id` no banco e só então chamar o motor.

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
2. API FastAPI e testes das políticas via HTTP.
3. SQLite/SQLAlchemy, empresas, usuários e agentes.
4. Autenticação separada, autorização administrativa e isolamento multiempresa.
5. Aprovação humana idempotente e trilha de auditoria.
6. Painel web responsivo.
7. Integração e testes de segurança/concorrência.
8. Documentação final e demonstração funcional.

Consulte [`docs/architecture.md`](docs/architecture.md), [`docs/api.md`](docs/api.md) e [`docs/security.md`](docs/security.md) para limites e decisões planejadas.
