# API NEXUS 0.2

O endpoint implementado está disponível em `POST /api/v1/operations`. A documentação OpenAPI interativa fica em `/docs` e o documento JSON em `/openapi.json`.

## Autenticação provisória

Envie o token configurado em `NEXUS_DEV_AGENT_TOKEN` no cabeçalho `X-Nexus-Agent-Token`. Ausência ou token desconhecido retorna `401`. Esse cadastro em memória é exclusivo para desenvolvimento local e será substituído na Etapa 4.

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

Erros de autenticação, configuração ou validação usam o envelope `{"error": {"code": "...", "message": "...", "details": null}}` e os status HTTP apropriados (`401`, `422` ou `503`).

## Endpoints futuros

| Método | Rota | Autenticação | Finalidade |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | usuário | Obter sessão administrativa |
| `GET` | `/api/v1/agents` | administrador | Listar agentes da própria empresa |
| `POST` | `/api/v1/agents` | administrador | Criar agente e emitir credencial uma vez |
| `GET` | `/api/v1/approvals` | aprovador | Listar pendências da própria empresa |
| `POST` | `/api/v1/approvals/{id}/decision` | aprovador | Aprovar ou rejeitar uma vez |
| `GET` | `/api/v1/audit-events` | administrador | Consultar auditoria da própria empresa |

A idempotência persistente e os estados finais serão especificados antes da etapa de banco de dados.
