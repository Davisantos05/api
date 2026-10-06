# Modelo de dados — NEXUS 0.3

```text
Company
│
├── Users
│   └── role: admin | approver | viewer
│       └── UserSessions
│
└── Agents
    ├── AgentCredentials
    ├── AgentPermissions
    │   └── operation: purchase | refund | read_inventory | ...
    │
    └── OperationRequests
        ├── policy outcome + reason
        └── ApprovalDecision (opcional e única)

Company
└── AuditEvents (append-only)
```

## Entidades

- **Company:** tenant raiz, com UUID, nome, estado e timestamps.
- **User:** pertence obrigatoriamente a uma empresa e contém role e hash Argon2id da senha.
- **UserSession:** token humano opaco com expiração, revogação e último uso; somente o hash é armazenado.
- **Agent:** pertence a uma empresa e mantém status e limites em centavos; suas chaves ficam em registros de credencial separados.
- **AgentCredential:** permite várias API keys por agente, com prefixo visual, expiração, revogação e último uso.
- **AgentPermission:** uma linha por operação permitida; a combinação agente/operação é única.
- **OperationRequestRecord:** conserva toda decisão, inclusive bloqueada ou pendente, com referências para empresa e agente.
- **ApprovalDecision:** decisão humana opcional, única por operação, sem substituir o resultado original da política.
- **AuditEvent:** evento append-only com ator, ação, alvo e metadados sanitizados.

## Integridade e isolamento

Chaves estrangeiras mantêm os vínculos; checks garantem limites não negativos e limite automático menor ou igual ao máximo. A combinação `(agent_id, request_id)` e o hash do token são únicos. Assim, um identificador é idempotente dentro do agente, sem criar interferência entre agentes ou empresas. E-mail é único dentro de cada empresa. Repositories de recursos administrativos exigem explicitamente `company_id`, impedindo que apenas conhecer um UUID permita atravessar tenants.

O banco local é SQLite, configurado por `NEXUS_DATABASE_URL`. Os UUIDs usam o tipo portátil `Uuid` do SQLAlchemy e enums não dependem de tipos nativos, reduzindo mudanças para uma futura URL PostgreSQL.
