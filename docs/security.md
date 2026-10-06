# Segurança e limitações

## Princípios adotados

- O agente nunca define sua empresa, permissões ou limites.
- Tokens de agentes e sessões administrativas terão esquemas e capacidades distintos.
- Tokens de agentes serão exibidos uma única vez e armazenados somente como hashes resistentes a ataques.
- Segredos e URLs de banco serão lidos do ambiente.
- Auditoria será append-only para usuários comuns.
- Isolamento por empresa será aplicado em toda consulta e testado explicitamente.

## Identidades da Etapa 4

Senhas humanas usam Argon2id, adequado a segredos de baixa entropia por impor custo de memória e CPU. Sessões e API keys são geradas com `secrets` e têm alta entropia; SHA-256 é adequado para o lookup desses valores aleatórios porque ataques de dicionário não são práticos. Tokens completos aparecem somente na criação.

Sessões humanas usam `Authorization: Bearer`; agentes usam `X-Nexus-Agent-Token`. As credenciais não são intercambiáveis. Sessões e API keys possuem expiração, revogação e registro de último uso; tokens inválidos, expirados ou revogados são rejeitados antes de atualizar esse registro. Uma troca de senha válida exige a senha atual e revoga todas as sessões do usuário. O tenant sempre vem da sessão ou do agente autenticado.

As políticas permanecem no servidor. O corpo da operação não aceita empresa, permissões ou limites, e campos extras são rejeitados. A política é selecionada somente depois da identificação do token.

Eventos de auditoria são criados por chamadas tipadas do servidor, nunca copiando corpos ou headers. Uma sanitização rejeita chaves relacionadas a senha, token, autorização, segredo, credencial ou hash. Não existem endpoints para atualizar ou excluir eventos.

Ainda não existem MFA, SSO, OAuth social, rate limiting distribuído ou TLS configurado pela aplicação. Também não há painel ou integração financeira real. SQLite não representa toda a concorrência esperada no PostgreSQL futuro. Portanto, **a API não deve controlar dinheiro ou sistemas reais**. Aprovação humana e `authorized` são somente autorizações simuladas.

O primeiro administrador é criado explicitamente por `nexus-create-admin`, com senha recebida por entrada segura ou variável de ambiente e sem senha fixa no repositório. Concorrência e aprovação duplicada serão tratadas na etapa do fluxo de aprovação.
