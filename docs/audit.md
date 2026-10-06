# Auditoria append-only na aplicação

`AuditEvent` registra tenant, tipo e identidade do ator, ação, alvo, metadados sanitizados e horário. A API e os repositories oferecem somente inclusão e leitura; não há endpoints de alteração ou exclusão. Nesta versão, portanto, **append-only é garantido pela aplicação**, não é imutabilidade absoluta contra um operador com acesso SQL direto. Permissões restritivas de banco e hardening específico do PostgreSQL são necessários antes de produção.

O banco também rejeita atores incoerentes: eventos `human` exigem somente `actor_user_id`, eventos `agent` exigem somente `actor_agent_id`, e eventos `system` não aceitam nenhuma dessas identidades. As FKs históricas usam `RESTRICT`, portanto excluir empresa, usuário ou agente referenciado falha explicitamente em vez de apagar o histórico em cascata.

## Eventos

- login, logout e troca de senha;
- criação de agente;
- criação e revogação de credencial;
- solicitação de operação e resultado `authorized`, `blocked` ou `pending_approval`;
- aprovação ou rejeição humana.

## Segurança dos metadados

Metadados são mapas rasos construídos pelo servidor com valores escalares. O sanitizador rejeita chaves associadas a passwords, tokens, Authorization, segredos, credenciais e hashes. Bodies e headers nunca são copiados para eventos.

## Idempotência

A primeira operação gera `operation.requested` e exatamente um evento de resultado. Replay idempotente retorna a decisão persistida sem novos eventos. Somente a decisão humana vencedora gera `approval.approved` ou `approval.rejected`; tentativas duplicadas ou concorrentes não geram eventos adicionais.

## Acesso

`admin` e `approver` podem consultar eventos exclusivamente da própria empresa. `viewer` não acessa auditoria nesta versão.

O Control Center renderiza metadados como texto, nunca como HTML, e oferece somente filtros e leitura. A interface declara explicitamente que append-only é uma garantia da aplicação nesta versão.
