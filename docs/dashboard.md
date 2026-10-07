# NEXUS Control Center

## Decisão arquitetural

O frontend usa HTML semântico, CSS responsivo e módulos JavaScript nativos, servidos pelo FastAPI. Não há React, bundler, Node ou duplicação das regras de negócio. Essa escolha reduz dependências e mantém o dashboard como cliente da API existente. A estrutura é:

```text
src/nexus/web/
├── templates/
│   ├── login.html
│   └── index.html
└── static/
    ├── css/nexus.css
    └── js/
        ├── api.js       # HTTP, erros e 401 global
        ├── format.js    # moeda, datas, IDs e labels
        ├── ui.js        # componentes DOM seguros
        ├── login.js     # autenticação web
        └── app.js       # páginas e fluxos
```

## Sessão no navegador

`POST /api/v1/auth/browser-login` cria a mesma sessão opaca da API, mas retorna o token exclusivamente em cookie `HttpOnly`, `SameSite=Strict`. O JSON nunca contém o token. Requisições mutáveis autenticadas por cookie exigem `X-Nexus-Web-Request: 1`, adicionando uma defesa simples contra CSRF. O cookie fica somente em memória/armazenamento controlado pelo navegador; não usamos `localStorage` nem `sessionStorage`. Em HTTPS, `NEXUS_COOKIE_SECURE=true` é obrigatório.

O endpoint Bearer original permanece disponível para clientes da API. `POST /api/v1/auth/browser-logout` revoga a sessão no banco e remove o cookie.

## Páginas e RBAC

- **Dashboard:** métricas agregadas no banco pelo tenant.
- **Operações:** filtros, status humano e detalhes baseados no snapshot histórico.
- **Aprovações:** `admin` e `approver` podem decidir; conflitos concorrentes continuam resolvidos pelo backend.
- **Agentes e credenciais:** administração exclusiva do `admin`; a API key aparece somente na resposta de criação e é descartada ao fechar o modal.
- **Audit Log:** leitura para `admin` e `approver`, sem edição ou exclusão.

O JavaScript esconde navegação incompatível com a role, mas isso é apenas UX. Todas as decisões continuam protegidas pelo RBAC central no backend. Não existe seletor de tenant; a empresa vem da sessão.

## Segurança e acessibilidade

Dados da API são inseridos usando `textContent` e criação explícita de nós DOM; não se usa `innerHTML`. O FastAPI aplica CSP sem scripts inline, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` e `Cache-Control: no-store`. Labels, foco visível, elementos semânticos, navegação por teclado, contraste e `aria-live` cobrem a acessibilidade básica.

O CSP é aplicado às páginas e assets do Control Center sem quebrar o Swagger. TLS, HSTS, rate limiting, MFA, SSO, proteção contra operador com acesso direto ao banco e testes em navegadores múltiplos continuam sendo responsabilidades de preparação para produção.

## Fluxo reproduzível

1. Execute migrações e `nexus-seed-dashboard` com uma senha fornecida pelo ambiente.
2. Entre em `/` com o administrador criado.
3. Use a API key mostrada uma vez para enviar `100000` centavos em `POST /api/v1/operations`.
4. Abra **Aprovações**, revise o snapshot e aprove ou rejeite.
5. Confirme a decisão em **Operações**, as métricas no Dashboard e a sequência em **Audit Log**.

Nenhuma etapa executa pagamentos ou efeitos externos.

### Demonstração com dois agentes

Em um banco novo, aplique `alembic upgrade head` e execute explicitamente
`nexus-seed-dashboard` com `NEXUS_DEMO_ADMIN_PASSWORD`. O seed cria `NEXUS Demo`
(`nexus-demo`), `Administrador Demo` (`admin@nexus.demo`) e duas identidades:

- Purchasing Agent: permite `purchase`, automático de 50.000 centavos e máximo
  de 200.000 centavos.
- Finance Agent: permite `pix`, automático de 10.000 centavos e máximo de
  100.000 centavos. `pix` continua sendo somente uma operação simulada.

As chaves são geradas separadamente e exibidas uma única vez com o nome do agente.
O banco guarda somente hash/prefixo; o seed não é chamado no startup. Se a empresa
já existe, o comando recusa a execução sem modificar o banco. Para avaliar o novo
dataset, use um banco de demonstração novo, preservando bancos existentes.

| Agente | Operação | Centavos | Resultado da política | Decisão humana |
|---|---|---:|---|---|
| Purchasing Agent | `purchase` | 30.000 | `authorized` | Não requerida |
| Purchasing Agent | `purchase` | 100.000 | `pending_approval` | Aguardando decisão |
| Purchasing Agent | `purchase` | 125.000 | `pending_approval` | `rejected` |
| Purchasing Agent | `purchase` | 150.000 | `pending_approval` | `approved` |
| Purchasing Agent | `purchase` | 300.000 | `blocked` | Não requerida |
| Finance Agent | `pix` | 5.000 | `authorized` | Não requerida |
| Finance Agent | `pix` | 50.000 | `pending_approval` | Aguardando decisão |
| Finance Agent | `pix` | 70.000 | `pending_approval` | `approved` |
| Finance Agent | `pix` | 80.000 | `pending_approval` | `rejected` |
| Finance Agent | `pix` | 200.000 | `blocked` | Não requerida |

As operações passam pelos serviços existentes de autorização persistente e
aprovação; cada decisão humana usa o identificador exato da solicitação criada.
O histórico guarda os limites e permissões da política aplicada e os eventos
registram o agente solicitante e o administrador responsável pelas decisões.

Os indicadores esperados no banco recém-criado são: 2 agentes ativos, 10 operações,
2 autorizadas, 2 bloqueadas, 2 pendências reais, 2 decisões aprovadas e 2 rejeitadas.
Na página Agentes, as credenciais e as últimas operações permanecem separadas por
identidade. Nenhum número é fixado no frontend.

## NEXUS 0.6 — interface premium

A interface usa preto/carvão, branco, off-white e cinzas neutros, com fontes do
sistema. Cores são reservadas aos resultados: verde para autorização/aprovação,
âmbar para decisão pendente e vermelho para bloqueio/rejeição. O login mantém
`company_slug` como texto e organiza a apresentação em 45% institucional e 55%
formulário; em telas menores, as áreas ficam empilhadas.

Os arquivos oficiais são servidos sem redesenho ou conversão em
`/static/assets/nexus-logo-{black,white}.png` e
`/static/assets/nexus-symbol-{black,white}.png`. Os logos aparecem no login; os
símbolos são usados na sidebar e no favicon. Esses PNGs também fazem parte dos
arquivos de distribuição do pacote Python.

### Indicadores e atenção operacional

`pending_approval` em `GET /api/v1/dashboard/summary` conta somente operações com
esse resultado original **e sem ApprovalDecision**. Aprovar ou rejeitar diminui
a pendência e aumenta o respectivo contador humano; não reescreve o resultado da
política nem seu snapshot histórico.

`GET /api/v1/dashboard/attention?limit=5` fornece até cinco pendências, filtradas
antes da limitação e ordenadas pelas mais recentes. Usa a mesma capacidade
`VIEW_OPERATIONS` da visão geral e deriva a empresa da sessão autenticada. O
viewer pode consultar os detalhes; somente admin e approver podem decidir. Os
limites exibidos vêm do `policy_snapshot`, mesmo que a política atual tenha
mudado. Nenhuma permissão de administração de agentes é ampliada para approvers.

Operações exibem resultado original e decisão humana separadamente. Os detalhes
incluem o responsável, justificativa e horário da decisão. A identidade de cada
agente apresenta permissões, limites, metadados das credenciais (admin) e suas
últimas operações. Auditoria usa uma tabela compacta e apresenta os metadados
sanitizados em um diálogo somente para leitura.

### Ciclo de vida das credenciais

A chave completa é exibida somente no diálogo de criação. Fechar, pressionar
Escape, navegar ou encerrar a sessão remove seu conteúdo e os handlers do DOM.
Uma resposta de criação recebida após fechar o diálogo não o reabre. A chave
não é mantida em estado global, storage, URL ou console. A revogação exige
confirmação. As requisições de criação e decisão têm proteção contra clique
repetido; conflitos HTTP 409 atualizam a visão a partir do backend.

### Validação reproduzível

```bash
python -m pip install -e '.[dev,browser]'
pytest -q
pytest -q tests/test_dashboard.py
ruff check .
ruff format --check .
pyright
python -m compileall -q src tests migrations
git diff --check
node --check src/nexus/web/static/js/api.js
node --check src/nexus/web/static/js/format.js
node --check src/nexus/web/static/js/ui.js
node --check src/nexus/web/static/js/login.js
node --check src/nexus/web/static/js/app.js
NEXUS_DATABASE_URL=sqlite:////tmp/nexus-validation.db alembic upgrade head
NEXUS_DATABASE_URL=sqlite:////tmp/nexus-validation.db alembic check
```

Node é usado apenas na checagem de sintaxe; a aplicação não precisa de bundler ou
runtime Node. Os testes de navegador requerem Chromium instalado e o extra
`browser`. `NEXUS_CHROMIUM_PATH` pode indicar outro executável compatível. Quando
um desses pré-requisitos não existe, os testes de navegador são explicitamente
marcados como skipped; isso não valida a interface visual.

Para registrar capturas durante os testes reais de navegador:

```bash
NEXUS_REVIEW_DIR=/tmp/nexus-review pytest -q tests/test_dashboard.py -k browser
```

Os testes cobrem login, cookie HttpOnly/SameSite/Secure, CSRF, logout persistente,
RBAC, isolamento de empresa, pendência real, snapshot histórico, aprovação,
conflito concorrente, descarte da API key e XSS. As capturas incluem login e
visão geral desktop/mobile, operações, aprovações, agentes e auditoria. Não
capturam chaves completas ou tokens de sessão.
