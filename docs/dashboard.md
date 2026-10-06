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
