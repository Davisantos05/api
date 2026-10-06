# Modelo de dados — NEXUS 0.3

```text
Company
│
├── Users
│   └── role: admin | approver | viewer
│
└── Agents
    ├── AgentPermissions
    │   └── operation: purchase | refund | read_inventory | ...
    │
    └── OperationRequests
        └── outcome + reason
```

## Entidades

- **Company:** tenant raiz, com UUID, nome, estado e timestamps.
- **User:** pertence obrigatoriamente a uma empresa. Nesta etapa representa dados e roles, sem login.
- **Agent:** pertence a uma empresa e mantém status, limites em centavos e somente o hash do token provisório.
- **AgentPermission:** uma linha por operação permitida; a combinação agente/operação é única.
- **OperationRequestRecord:** conserva toda decisão, inclusive bloqueada ou pendente, com referências para empresa e agente.

## Integridade e isolamento

Chaves estrangeiras mantêm os vínculos; checks garantem limites não negativos e limite automático menor ou igual ao máximo. A combinação `(agent_id, request_id)` e o hash do token são únicos. Assim, um identificador é idempotente dentro do agente, sem criar interferência entre agentes ou empresas. E-mail é único dentro de cada empresa. Repositories de recursos administrativos exigem explicitamente `company_id`, impedindo que apenas conhecer um UUID permita atravessar tenants.

O banco local é SQLite, configurado por `NEXUS_DATABASE_URL`. Os UUIDs usam o tipo portátil `Uuid` do SQLAlchemy e enums não dependem de tipos nativos, reduzindo mudanças para uma futura URL PostgreSQL.
