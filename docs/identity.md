# Identidade no NEXUS 0.4

## HUMAN IDENTITY

O usuário informa `company_slug`, `email` e `password`. O slug torna a identidade inequívoca sem tornar o e-mail globalmente único. Senhas são armazenadas apenas como hashes Argon2id. Um login válido cria um token opaco `nxs_us_…`, mostrado na resposta e persistido apenas como SHA-256.

Sessões duram oito horas, podem ser revogadas por logout e atualizam `last_used_at`. O cabeçalho é `Authorization: Bearer <token>`. A troca de senha exige a senha atual e, quando concluída, revoga todas as sessões do usuário — inclusive a sessão usada na troca.

### Matriz RBAC

| Capacidade | admin | approver | viewer |
|---|:---:|:---:|:---:|
| Ver agentes | ✓ | — | ✓ |
| Criar agentes | ✓ | — | — |
| Administrar credenciais | ✓ | — | — |
| Consultar operações/pendências | ✓ | ✓ | ✓ |

As regras residem em uma política RBAC central. Aprovar ou rejeitar permanece fora desta etapa.

## AGENT IDENTITY

API keys são geradas no servidor como `nxs_ag_<aleatório>`. Cada agente pode ter várias credenciais para rotação gradual. O banco guarda SHA-256, um prefixo visual de somente 12 caracteres (o marcador fixo e cinco caracteres aleatórios), criação, expiração opcional, revogação e último uso. O token completo só aparece na resposta de criação.

Agentes só podem chamar `POST /api/v1/operations`. Uma API key não concede acesso aos endpoints administrativos nem permite modificar a própria política.

## Limitações

Não há MFA, SSO, rate limiting distribuído ou TLS configurado pela aplicação. Essas limitações precisam ser tratadas antes de uma implantação comercial.
