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
        ├── policy outcome + reason + policy snapshot
        └── ApprovalDecision (opcional e única)

Company
└── AuditEvents (append-only pela aplicação)
```

## Entidades

- **Company:** tenant raiz, com UUID, nome, estado e timestamps.
- **User:** pertence obrigatoriamente a uma empresa e contém role e hash Argon2id da senha.
- **UserSession:** token humano opaco com expiração, revogação e último uso; somente o hash é armazenado.
- **Agent:** pertence a uma empresa e mantém status e limites em centavos; suas chaves ficam em registros de credencial separados.
- **AgentCredential:** permite várias API keys por agente, com prefixo visual, expiração, revogação e último uso.
- **AgentPermission:** uma linha por operação permitida; a combinação agente/operação é única.
- **OperationRequestRecord:** conserva toda decisão, inclusive bloqueada ou pendente, com referências para empresa e agente e um snapshot versionado da política usada.
- **ApprovalDecision:** decisão humana opcional, única por operação, sem substituir o resultado original da política.
- **AuditEvent:** evento append-only pela aplicação com ator, ação, alvo e metadados sanitizados.

## Integridade e isolamento

Chaves estrangeiras históricas em operações, decisões e auditoria usam `RESTRICT`; uma exclusão futura não pode apagar silenciosamente o histórico. Checks garantem limites válidos e a coerência entre `actor_type` e sua identidade. A combinação `(agent_id, request_id)` e o hash do token são únicos. Assim, um identificador é idempotente dentro do agente, sem criar interferência entre agentes ou empresas. E-mail é único dentro de cada empresa. Repositories de recursos administrativos exigem explicitamente `company_id`, impedindo que apenas conhecer um UUID permita atravessar tenants.

## Snapshot histórico da política

Cada nova operação grava, junto da decisão, somente os elementos confiáveis que explicam a avaliação: versão do formato, estado ativo, operações permitidas e limites automático/máximo. O snapshot é montado no servidor e não contém API keys, hashes, sessões, senhas ou outros segredos. Mudanças posteriores no agente não alteram esse JSON. Um replay idempotente reutiliza a linha e a decisão originais, sem recalcular com a política atual.

A migração `0006` preenche registros legados com a melhor informação disponível no momento da migração. Como versões anteriores não capturavam a política, esse backfill não pode provar alterações ocorridas antes da atualização; operações criadas a partir de `0006` possuem o snapshot exato do instante da decisão.

O banco local é SQLite, configurado por `NEXUS_DATABASE_URL`. Os UUIDs usam o tipo portátil `Uuid` do SQLAlchemy e enums não dependem de tipos nativos, reduzindo mudanças para uma futura URL PostgreSQL.
