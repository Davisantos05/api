# Auditoria imutável

`AuditEvent` registra tenant, tipo e identidade do ator, ação, alvo, metadados sanitizados e horário. A API oferece somente leitura; não há endpoints de alteração ou exclusão.

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
