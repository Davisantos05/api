# Arquitetura do NEXUS

## Direção das dependências

O domínio contém regras puras e não importa FastAPI, SQLAlchemy ou código do painel. Endpoints validam o protocolo, serviços coordenam casos de uso e adaptadores persistem dados. Essa separação reduz o acoplamento e permite migrar de SQLite para PostgreSQL sem reescrever o motor.

## Fluxo futuro de uma solicitação

1. A API autentica o token do agente por um mecanismo exclusivo para agentes.
2. O servidor deriva `agent_id` e `company_id` da credencial; ignora identidades alegadas no corpo.
3. Um serviço carrega do banco a política ativa do agente.
4. O motor avalia a solicitação.
5. O serviço persiste solicitação, decisão e evento de auditoria em uma transação.
6. Autorizações automáticas recebem autorização simulada; pendências aguardam uma decisão humana.

## Evolução de dados

Modelos SQLAlchemy serão separados dos modelos Pydantic. Todas as consultas administrativas terão escopo obrigatório de empresa. Valores monetários permanecerão inteiros em centavos. Migrações e PostgreSQL serão adicionados quando existir o primeiro esquema persistente.

## Decisões da Etapa 1

- `AgentPolicy` representa um snapshot confiável, e não dados enviados pelo agente.
- Objetos Pydantic são imutáveis e proíbem campos extras.
- Resultados e motivos são enums estáveis para posterior persistência e auditoria.
- Limites são inclusivos: exatamente o automático autoriza; exatamente o máximo solicita aprovação.
