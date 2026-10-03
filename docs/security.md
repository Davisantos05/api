# Segurança e limitações

## Princípios adotados

- O agente nunca define sua empresa, permissões ou limites.
- Tokens de agentes e sessões administrativas terão esquemas e capacidades distintos.
- Tokens de agentes serão exibidos uma única vez e armazenados somente como hashes resistentes a ataques.
- Segredos e URLs de banco serão lidos do ambiente.
- Auditoria será append-only para usuários comuns.
- Isolamento por empresa será aplicado em toda consulta e testado explicitamente.

## Identificação provisória da Etapa 2

O cabeçalho `X-Nexus-Agent-Token` identifica um único agente local configurado por variável de ambiente. O processo mantém apenas o hash SHA-256 do token na memória, mas isso não substitui um sistema completo de credenciais: não há persistência, expiração, revogação, rotação, rate limiting ou gestão de múltiplos agentes. A comunicação também depende do servidor local e não configura TLS.

As políticas permanecem no servidor. O corpo da operação não aceita empresa, permissões ou limites, e campos extras são rejeitados. A política é selecionada somente depois da identificação do token.

Ainda não existem autenticação administrativa, banco de dados, idempotência persistente, concorrência de aprovações, logs operacionais ou painel. Portanto, **a API deve ser usada apenas localmente e não deve controlar dinheiro ou sistemas reais**. Uma decisão `authorized` é somente uma resposta simulada; nenhum pagamento ou efeito externo é executado.

A criação segura do primeiro administrador será implementada com um comando local que recebe credenciais por entrada/variáveis de ambiente, sem senha fixa no repositório. Concorrência e aprovação duplicada exigirão restrições no banco e atualização atômica, a serem implementadas nas etapas de persistência e aprovação.
