# Segurança e limitações

## Princípios adotados

- O agente nunca define sua empresa, permissões ou limites.
- Tokens de agentes e sessões administrativas terão esquemas e capacidades distintos.
- Tokens de agentes serão exibidos uma única vez e armazenados somente como hashes resistentes a ataques.
- Segredos e URLs de banco serão lidos do ambiente.
- Auditoria será append-only para usuários comuns.
- Isolamento por empresa será aplicado em toda consulta e testado explicitamente.

## Limitações da Etapa 1

Esta etapa oferece somente a regra pura de decisão e validação de seus objetos. Ainda não existem autenticação, API, armazenamento, idempotência persistente, concorrência de aprovações, rate limiting, rotação de credenciais, logs operacionais ou painel. Portanto, **não deve ser implantada nem usada para controlar dinheiro ou sistemas reais**.

A criação segura do primeiro administrador será implementada com um comando local que recebe credenciais por entrada/variáveis de ambiente, sem senha fixa no repositório. Concorrência e aprovação duplicada exigirão restrições no banco e atualização atômica, a serem implementadas nas etapas de persistência e aprovação.
