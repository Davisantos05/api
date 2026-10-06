# API NEXUS 0.5

O endpoint implementado está disponível em `POST /api/v1/operations`. A documentação OpenAPI interativa fica em `/docs` e o documento JSON em `/openapi.json`.

## Autenticação de agentes

Envie no cabeçalho `X-Nexus-Agent-Token` uma API key criada pelo servidor. Ausência, expiração, revogação ou token desconhecido retorna `401`. A API procura seu hash no banco e deriva dele o agente e a empresa.

## Solicitação

```json
{
  "request_id": "01950000-0000-7000-8000-000000000099",
  "operation": "purchase",
  "amount_cents": 30000
}
```

Somente esses três campos são aceitos. `amount_cents` deve ser um inteiro maior ou igual a zero. Empresa, permissões e limites vêm da política no servidor.

## Resposta de decisão

Decisões autorizadas, pendentes e bloqueadas usam HTTP `200`, pois todas representam uma avaliação válida:

```json
{
  "data": {
    "request_id": "01950000-0000-7000-8000-000000000099",
    "agent_id": "01950000-0000-7000-8000-000000000001",
    "operation": "purchase",
    "amount_cents": 30000,
    "outcome": "authorized",
    "reason": "within_automatic_limit"
  }
}
```

Erros de autenticação, idempotência ou validação usam o envelope `{"error": {"code": "...", "message": "...", "details": null}}` e os status HTTP apropriados (`401`, `409` ou `422`).

## Replays

- mesmo agente, `request_id`, operação e valor: HTTP `200` com a decisão originalmente persistida;
- mesmo agente e `request_id`, mas operação ou valor diferente: HTTP `409`, código `idempotency_conflict`;
- outro agente pode usar o mesmo `request_id`, na mesma empresa ou em outra, sem colisão;
- toda primeira avaliação, inclusive bloqueada ou pendente, é persistida.
- o replay reutiliza também o snapshot histórico da política e nunca consulta a política atual para recalcular a resposta.

## Identidade humana e administração

| Método | Rota | Capacidade |
|---|---|---|
| `POST` | `/api/v1/auth/login` | público, usa empresa/e-mail/senha |
| `POST` | `/api/v1/auth/logout` | sessão humana válida |
| `GET` | `/api/v1/auth/me` | sessão humana válida |
| `POST` | `/api/v1/auth/change-password` | sessão humana válida |
| `GET` | `/api/v1/agents` | visualizar agentes |
| `POST` | `/api/v1/agents` | criar agentes |
| `POST` | `/api/v1/agents/{id}/credentials` | administrar credenciais |
| `GET` | `/api/v1/agents/{id}/credentials` | administrar credenciais |
| `POST` | `/api/v1/agents/{id}/credentials/{credential_id}/revoke` | administrar credenciais |
| `GET` | `/api/v1/operations` | visualizar operações |
| `GET` | `/api/v1/approvals` | visualizar pendências (`admin`, `approver`) |
| `GET` | `/api/v1/approvals/{operation_id}` | detalhar uma revisão |
| `POST` | `/api/v1/approvals/{operation_id}/decision` | aprovar/rejeitar uma vez |
| `GET` | `/api/v1/audit-events` | ler auditoria (`admin`, `approver`) |

Todos os endpoints administrativos derivam `company_id` da sessão. O login sempre retorna a mesma mensagem genérica para empresa, e-mail ou senha incorretos.

Os detalhes de aprovação incluem `policy_snapshot`, com a versão do formato, estado do agente, operações permitidas e limites em centavos usados na decisão. O campo é histórico e não contém credenciais ou hashes.

## Limite funcional

Nenhum endpoint executa a ação solicitada ou movimenta dinheiro. Uma aprovação somente registra uma autorização simulada; integrações e execução externa permanecem fora do produto atual.
