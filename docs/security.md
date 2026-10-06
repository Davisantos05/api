# Segurança e limitações

## Princípios adotados

- O agente nunca define sua empresa, permissões ou limites.
- Tokens de agentes e sessões administrativas terão esquemas e capacidades distintos.
- Tokens de agentes serão exibidos uma única vez e armazenados somente como hashes resistentes a ataques.
- Segredos e URLs de banco serão lidos do ambiente.
- Auditoria será append-only para usuários comuns.
- Isolamento por empresa será aplicado em toda consulta e testado explicitamente.

## Identificação provisória da Etapa 3

O cabeçalho `X-Nexus-Agent-Token` identifica um agente persistido. O banco mantém apenas SHA-256 do token de alta entropia; o valor original é fornecido ao seed por variável de ambiente e não é exibido. Isso não substitui um sistema completo de credenciais: ainda não há expiração, revogação, rotação ou rate limiting. A comunicação local também não configura TLS.

As políticas permanecem no servidor. O corpo da operação não aceita empresa, permissões ou limites, e campos extras são rejeitados. A política é selecionada somente depois da identificação do token.

Ainda não existem autenticação administrativa, concorrência de aprovações, logs operacionais ou painel. SQLite serializa escritas e não representa toda a concorrência esperada no PostgreSQL futuro. Portanto, **a API deve ser usada apenas localmente e não deve controlar dinheiro ou sistemas reais**. Uma decisão `authorized` é somente uma resposta simulada; nenhum pagamento ou efeito externo é executado.

A criação segura do primeiro administrador será implementada com um comando local que recebe credenciais por entrada/variáveis de ambiente, sem senha fixa no repositório. Concorrência e aprovação duplicada exigirão restrições no banco e atualização atômica, a serem implementadas nas etapas de persistência e aprovação.
