# API planejada

Nenhum endpoint HTTP é implementado na Etapa 1. A especificação abaixo orienta as próximas etapas e poderá mudar após testes de API.

| Método | Rota | Autenticação | Finalidade |
|---|---|---|---|
| `POST` | `/api/v1/operations` | token de agente | Solicitar avaliação idempotente |
| `POST` | `/api/v1/auth/login` | usuário | Obter sessão administrativa |
| `GET` | `/api/v1/agents` | administrador | Listar agentes da própria empresa |
| `POST` | `/api/v1/agents` | administrador | Criar agente e emitir credencial uma vez |
| `GET` | `/api/v1/approvals` | aprovador | Listar pendências da própria empresa |
| `POST` | `/api/v1/approvals/{id}/decision` | aprovador | Aprovar ou rejeitar uma vez |
| `GET` | `/api/v1/audit-events` | administrador | Consultar auditoria da própria empresa |

A documentação OpenAPI será produzida automaticamente pelo FastAPI na Etapa 2. A chave idempotente e os estados finais serão especificados antes da persistência.
