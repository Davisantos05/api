# Arquitetura do NEXUS

## Direção das dependências

O domínio contém regras puras e não importa FastAPI, SQLAlchemy ou código do painel. Endpoints validam o protocolo, serviços coordenam casos de uso e adaptadores persistem dados. Essa separação reduz o acoplamento e permite migrar de SQLite para PostgreSQL sem reescrever o motor.

Na Etapa 3, `api` depende de `services`; `services` usa repositories e o domínio; repositories conhecem os modelos SQLAlchemy. O domínio não depende de nenhuma dessas camadas.

Na Etapa 4 existem dois autenticadores independentes. `HumanSession` aceita somente Bearer de sessão nos endpoints administrativos. `AgentCredential` aceita somente `X-Nexus-Agent-Token` na criação de operações. O RBAC central traduz roles humanas em capacidades reutilizáveis.

Na Etapa 5, o resultado imutável da política permanece na solicitação, enquanto uma decisão humana opcional vive em `ApprovalDecision`. `ApprovalService` valida tenant e estado, insere a decisão e o evento de auditoria antes de um único commit. A unicidade por operação resolve disputas concorrentes. Eventos das operações também compartilham a transação que cria a operação; replays não acrescentam eventos.

## Fluxo futuro de uma solicitação

1. A API recebe a API key rotacionável do agente em um cabeçalho exclusivo.
2. O repository procura somente o hash do token e deriva `agent_id` e `company_id`; identidades alegadas no corpo são rejeitadas.
3. O serviço carrega do banco o agente, a empresa e suas permissões.
4. O motor avalia a solicitação.
5. O serviço persiste solicitação e decisão na mesma transação.
6. Autorizações automáticas recebem autorização simulada; pendências aguardam uma decisão humana.

## Evolução de dados

Modelos SQLAlchemy são separados dos modelos Pydantic. Consultas de usuários, agentes e solicitações exigem `company_id`; somente a busca de autenticação começa pelo hash do token e deriva o tenant do agente encontrado. Valores monetários permanecem inteiros em centavos. O esquema é controlado por Alembic e usa tipos SQLAlchemy portáveis; PostgreSQL poderá ser selecionado principalmente pela URL de conexão.

## Idempotência

A combinação `operation_requests(agent_id, request_id)` é única. O agente define o namespace de idempotência porque `agent_id` já determina sua empresa; incluir também `company_id` seria redundante. Um replay do mesmo agente com operação e valor idênticos retorna a decisão persistida, sem criar outra linha. Alterar operação ou valor com o mesmo identificador gera conflito HTTP `409`. Agentes diferentes podem usar o mesmo `request_id`, inclusive dentro da mesma empresa. A restrição no banco também protege tentativas concorrentes; após uma colisão, o serviço relê a linha no escopo da empresa e do agente.

## Decisões da Etapa 1

- `AgentPolicy` representa um snapshot confiável, e não dados enviados pelo agente.
- Objetos Pydantic são imutáveis e proíbem campos extras.
- Resultados e motivos são enums estáveis para posterior persistência e auditoria.
- Limites são inclusivos: exatamente o automático autoriza; exatamente o máximo solicita aprovação.
