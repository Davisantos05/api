import {api, get, post, ApiError} from "./api.js";
import {dateTime, label, money, shortId} from "./format.js";
import {badge, clear, el, empty, errorState, field, heading, loading, toast} from "./ui.js";

const main = document.querySelector("#main-content");
const modal = document.querySelector("#modal");
const modalTitle = document.querySelector("#modal-title");
const modalContent = document.querySelector("#modal-content");
let currentUser;
document.querySelector("#modal .icon-button").addEventListener("click", () => modal.close());

const capabilities = {
  admin: new Set(["dashboard", "operations", "approvals", "agents", "audit"]),
  approver: new Set(["dashboard", "operations", "approvals", "audit"]),
  viewer: new Set(["dashboard", "operations", "agents"]),
};
const pages = [
  ["dashboard", "Visão geral", "▦"], ["operations", "Operações", "⇄"],
  ["approvals", "Aprovações", "✓"], ["agents", "Agentes", "◇"], ["audit", "Auditoria", "≡"],
];

function openModal(title, content) { modalTitle.textContent = title; clear(modalContent); modalContent.append(content); modal.showModal(); }
function query(params) { const value = new URLSearchParams(Object.entries(params).filter(([, item]) => item)); return value.size ? `?${value}` : ""; }
function pageTable(headers, rows) {
  const table = el("table"); const head = el("tr"); headers.forEach((item) => head.append(el("th", {text: item})));
  table.append(el("thead", {}, head), el("tbody", {}, rows)); return el("div", {class: "table-wrap"}, table);
}
function statusFor(operation) { return operation.approval?.decision || operation.policy_outcome; }

async function renderDashboard() {
  main.replaceChildren(loading());
  try {
    const [summary, operations] = await Promise.all([get("/api/v1/dashboard/summary"), get("/api/v1/operations?limit=6")]);
    const cards = [
      ["Agentes ativos", summary.agents_active, "Agentes disponíveis para operar"],
      ["Total de operações", summary.operations_total, "Solicitações avaliadas"],
      ["Autorizadas", summary.authorized, "Pela política automática"],
      ["Pendentes", summary.pending_approval, "Inclui já decididas"],
      ["Bloqueadas", summary.blocked, "Interrompidas pela política"],
      ["Aprovações humanas", summary.human_approved, `${summary.human_rejected} rejeitadas`],
    ].map(([name, value, detail]) => el("article", {class: "metric-card"}, [el("span", {text: name}), el("strong", {text: value}), el("small", {text: detail})]));
    const recent = operations.length ? operationTable(operations) : empty("Nenhuma operação", "As solicitações dos agentes aparecerão aqui.");
    main.replaceChildren(heading("Visão geral", "Indicadores operacionais da sua empresa."), el("section", {class: "metrics"}, cards), el("section", {class: "panel"}, [el("div", {class: "panel-heading"}, [el("h2", {text: "Atividade recente"}), el("a", {href: "#operations", text: "Ver todas"})]), recent]));
  } catch (error) { main.replaceChildren(errorState(error.message, renderDashboard)); }
}

function operationTable(items) {
  return pageTable(["Horário", "Solicitação", "Agente", "Operação", "Valor", "Status"], items.map((item) => {
    const row = el("tr", {tabindex: "0", role: "button", "aria-label": `Abrir operação ${shortId(item.request_id)}`, onclick: () => showOperation(item.operation_id)});
    row.addEventListener("keydown", (event) => { if (event.key === "Enter") showOperation(item.operation_id); });
    [dateTime(item.created_at), shortId(item.request_id), item.agent_name, item.operation, money(item.amount_cents)].forEach((value) => row.append(el("td", {text: value})));
    row.append(el("td", {}, badge(statusFor(item), label(statusFor(item))))); return row;
  }));
}

async function renderOperations() {
  main.replaceChildren(loading());
  try {
    const [items, agents] = await Promise.all([get("/api/v1/operations?limit=100"), get("/api/v1/agents")]);
    const agent = el("select", {id: "operation-agent"}, [el("option", {value: "", text: "Todos os agentes"}), ...agents.map((item) => el("option", {value: item.id, text: item.name}))]);
    const status = el("select", {id: "operation-status"}, [el("option", {value: "", text: "Todos os status"}), ...["authorized", "pending_approval", "blocked"].map((item) => el("option", {value: item, text: label(item)}))]);
    const filter = el("button", {class: "button secondary", text: "Aplicar filtros", type: "button", onclick: async () => {
      const data = await get(`/api/v1/operations${query({agent_id: agent.value, outcome: status.value, limit: "100"})}`);
      document.querySelector("#operations-result").replaceChildren(data.length ? operationTable(data) : empty("Sem resultados", "Altere os filtros e tente novamente."));
    }});
    const result = el("div", {id: "operations-result"}, items.length ? operationTable(items) : empty("Nenhuma operação", "Ainda não há solicitações registradas."));
    main.replaceChildren(heading("Operações", "Decisões de política e resultados humanos."), el("section", {class: "filter-bar"}, [field("Agente", agent), field("Resultado da política", status), filter]), result);
  } catch (error) { main.replaceChildren(errorState(error.message, renderOperations)); }
}

function policyView(snapshot) {
  const permitted = Array.isArray(snapshot.allowed_operations) ? snapshot.allowed_operations.join(", ") : "—";
  return el("section", {class: "policy-box"}, [el("h3", {text: "Política aplicada no momento da operação"}), el("dl", {class: "detail-grid"}, [
    el("div", {}, [el("dt", {text: "Agente ativo"}), el("dd", {text: snapshot.active ? "Sim" : "Não"})]),
    el("div", {}, [el("dt", {text: "Operações permitidas"}), el("dd", {text: permitted})]),
    el("div", {}, [el("dt", {text: "Limite automático"}), el("dd", {text: money(snapshot.automatic_limit_cents)})]),
    el("div", {}, [el("dt", {text: "Limite máximo"}), el("dd", {text: money(snapshot.maximum_limit_cents)})]),
  ])]);
}

async function showOperation(id) {
  try {
    const item = await get(`/api/v1/operations/${id}`);
    const details = el("div", {class: "detail-stack"}, [
      el("dl", {class: "detail-grid"}, [
        ["Agente", item.agent_name], ["Operação", item.operation], ["Valor", money(item.amount_cents)], ["Horário", dateTime(item.created_at)],
        ["Resultado original", label(item.policy_outcome)], ["Motivo da política", label(item.policy_reason)], ["Request ID", item.request_id],
        ["Decisão humana", item.approval ? label(item.approval.decision) : "Ainda não decidida"], ["Motivo humano", item.approval?.reason || "—"],
      ].map(([term, value]) => el("div", {}, [el("dt", {text: term}), el("dd", {text: value})]))), policyView(item.policy_snapshot),
    ]);
    openModal("Detalhes da operação", details);
  } catch (error) { toast(error.message, "error"); }
}

async function renderApprovals() {
  main.replaceChildren(loading());
  try {
    const items = await get("/api/v1/approvals?status=pending&limit=100");
    const content = items.length ? el("div", {class: "approval-grid"}, items.map((item) => {
      const actions = el("div", {class: "card-actions"}, [
        el("button", {class: "button success", text: "Aprovar", type: "button", onclick: () => decisionDialog(item, "approved")}),
        el("button", {class: "button danger", text: "Rejeitar", type: "button", onclick: () => decisionDialog(item, "rejected")}),
      ]);
      return el("article", {class: "approval-card"}, [el("div", {class: "approval-title"}, [el("span", {class: "avatar agent", text: item.agent_name.slice(0, 1)}), el("div", {}, [el("h2", {text: item.agent_name}), el("p", {text: `${item.operation} · ${dateTime(item.created_at)}`})])]), el("strong", {class: "approval-value", text: money(item.amount_cents)}), badge("pending_approval", "Requer decisão humana"), policyView(item.policy_snapshot), actions]);
    })) : empty("Tudo em dia", "Não existem operações aguardando aprovação.");
    main.replaceChildren(heading("Aprovações", "Revise solicitações que ultrapassaram o limite automático."), content);
  } catch (error) { main.replaceChildren(errorState(error.message, renderApprovals)); }
}

function decisionDialog(item, choice) {
  const reason = el("textarea", {id: "decision-reason", rows: "4", maxlength: "1000", placeholder: "Motivo opcional da decisão"});
  const submit = el("button", {class: choice === "approved" ? "button success" : "button danger", type: "button", text: choice === "approved" ? "Confirmar aprovação" : "Confirmar rejeição"});
  submit.addEventListener("click", async () => {
    submit.disabled = true;
    try { await post(`/api/v1/approvals/${item.operation_id}/decision`, {decision: choice, reason: reason.value.trim() || null}); modal.close(); toast(choice === "approved" ? "Operação aprovada." : "Operação rejeitada."); await renderApprovals(); }
    catch (error) { toast(error.status === 409 ? "Esta operação já foi decidida por outro usuário." : error.message, "error"); submit.disabled = false; }
  });
  openModal(choice === "approved" ? "Aprovar operação" : "Rejeitar operação", el("div", {}, [el("p", {text: `Confirme a decisão para ${item.agent_name}, no valor de ${money(item.amount_cents)}.`}), field("Motivo", reason), el("div", {class: "modal-actions"}, submit)]));
}

async function renderAgents() {
  main.replaceChildren(loading());
  try {
    const agents = await get("/api/v1/agents");
    const create = currentUser.role === "admin" ? el("button", {class: "button primary", text: "+ Novo agente", type: "button", onclick: createAgentDialog}) : null;
    const cards = agents.length ? el("div", {class: "agent-grid"}, agents.map((item) => el("article", {class: "agent-card"}, [
      el("div", {class: "agent-card-head"}, [el("span", {class: "avatar agent", text: item.name.slice(0, 1)}), badge(item.active ? "active" : "blocked", item.active ? "Ativo" : "Inativo")]),
      el("h2", {text: item.name}), el("p", {text: item.description || "Sem descrição"}),
      el("div", {class: "limit-row"}, [el("span", {text: `Automático ${money(item.automatic_limit_cents)}`}), el("span", {text: `Máximo ${money(item.maximum_limit_cents)}`})]),
      el("p", {class: "permissions", text: item.allowed_operations.join(" · ")}),
      currentUser.role === "admin" ? el("button", {class: "button secondary wide", text: "Gerenciar credenciais", type: "button", onclick: () => credentialsDialog(item)}) : null,
    ]))) : empty("Nenhum agente", "Crie o primeiro agente para começar.");
    main.replaceChildren(heading("Agentes", "Políticas e identidades de software da empresa.", create), cards);
  } catch (error) { main.replaceChildren(errorState(error.message, renderAgents)); }
}

function createAgentDialog() {
  const inputs = {name: el("input", {id: "agent-name", required: ""}), description: el("textarea", {id: "agent-description", rows: "3"}), permissions: el("input", {id: "agent-permissions", value: "purchase"}), automatic: el("input", {id: "agent-automatic", type: "number", min: "0", value: "50000"}), maximum: el("input", {id: "agent-maximum", type: "number", min: "0", value: "200000"})};
  const save = el("button", {class: "button primary", type: "button", text: "Criar agente", onclick: async () => {
    save.disabled = true;
    try { await post("/api/v1/agents", {name: inputs.name.value.trim(), description: inputs.description.value.trim(), allowed_operations: inputs.permissions.value.split(",").map((v) => v.trim()).filter(Boolean), automatic_limit_cents: Number(inputs.automatic.value), maximum_limit_cents: Number(inputs.maximum.value)}); modal.close(); toast("Agente criado."); await renderAgents(); }
    catch (error) { toast(error.message, "error"); save.disabled = false; }
  }});
  openModal("Criar agente", el("div", {}, [field("Nome", inputs.name), field("Descrição", inputs.description), field("Operações permitidas (separadas por vírgula)", inputs.permissions), el("div", {class: "two-columns"}, [field("Limite automático (centavos)", inputs.automatic), field("Limite máximo (centavos)", inputs.maximum)]), el("div", {class: "modal-actions"}, save)]));
}

async function credentialsDialog(agent) {
  const body = el("div", {}, loading()); openModal(`Credenciais — ${agent.name}`, body);
  async function reload() {
    try {
      const items = await get(`/api/v1/agents/${agent.id}/credentials`); clear(body);
      const create = el("button", {class: "button primary", text: "Gerar nova credencial", type: "button", onclick: generate});
      body.append(create, items.length ? el("div", {class: "credential-list"}, items.map((item) => el("div", {class: "credential-row"}, [el("div", {}, [el("strong", {text: item.token_prefix}), el("small", {text: `Criada ${dateTime(item.created_at)} · Último uso ${dateTime(item.last_used_at)}`})]), badge(item.revoked_at ? "revoked" : "active", item.revoked_at ? "Revogada" : "Ativa"), !item.revoked_at ? el("button", {class: "button danger ghost", text: "Revogar", type: "button", onclick: () => revoke(item)}) : null]))) : empty("Sem credenciais", "Gere uma chave para este agente."));
    } catch (error) { body.replaceChildren(errorState(error.message, reload)); }
  }
  async function generate() {
    try {
      const result = await post(`/api/v1/agents/${agent.id}/credentials`, {});
      const token = el("code", {class: "one-time-key", text: result.token});
      openModal("Nova API key criada", el("div", {}, [el("p", {text: "Copie esta chave agora. Ela não poderá ser exibida novamente."}), token, el("button", {class: "button primary wide", type: "button", text: "Copiar chave", onclick: async (event) => { await navigator.clipboard.writeText(result.token); event.currentTarget.textContent = "Copiada"; }}), el("p", {class: "security-note", text: "Ao fechar esta janela, a chave completa será removida da interface."})]));
    } catch (error) { toast(error.message, "error"); }
  }
  async function revoke(item) {
    if (!window.confirm(`Revogar a credencial ${item.token_prefix}?`)) return;
    try { await post(`/api/v1/agents/${agent.id}/credentials/${item.id}/revoke`); toast("Credencial revogada."); await reload(); }
    catch (error) { toast(error.message, "error"); }
  }
  await reload();
}

async function renderAudit() {
  main.replaceChildren(loading());
  try {
    const events = await get("/api/v1/audit-events?limit=100");
    const rows = events.map((item) => { const row = el("tr"); [dateTime(item.created_at), `${item.actor_name} · ${label(item.actor_type)}`, item.action, `${item.target_type} · ${shortId(item.target_id)}`, JSON.stringify(item.metadata)].forEach((value) => row.append(el("td", {text: value}))); return row; });
    main.replaceChildren(heading("Audit Log", "Histórico append-only pela aplicação. Eventos não podem ser editados pela API."), events.length ? pageTable(["Horário", "Ator", "Ação", "Alvo", "Metadados"], rows) : empty("Sem eventos", "Eventos de segurança e operação aparecerão aqui."));
  } catch (error) { main.replaceChildren(errorState(error.message, renderAudit)); }
}

const renderers = {dashboard: renderDashboard, operations: renderOperations, approvals: renderApprovals, agents: renderAgents, audit: renderAudit};
async function navigate() {
  let page = location.hash.slice(1) || "dashboard"; if (!capabilities[currentUser.role].has(page)) page = "dashboard";
  document.querySelectorAll("nav a").forEach((item) => item.classList.toggle("active", item.dataset.page === page));
  document.querySelector("#sidebar").classList.remove("open"); await renderers[page](); main.focus();
}
async function initialize() {
  try { currentUser = await get("/api/v1/auth/me"); } catch (_error) { return; }
  document.querySelector("#company-name").textContent = currentUser.company_name;
  document.querySelector("#user-name").textContent = currentUser.name;
  document.querySelector("#user-role").textContent = label(currentUser.role);
  document.querySelector("#user-initial").textContent = currentUser.name.slice(0, 1).toUpperCase();
  const navigation = document.querySelector("#navigation");
  pages.filter(([key]) => capabilities[currentUser.role].has(key)).forEach(([key, text, icon]) => navigation.append(el("a", {href: `#${key}`, "data-page": key}, [el("span", {text: icon, "aria-hidden": "true"}), el("span", {text})])));
  window.addEventListener("hashchange", navigate); await navigate();
}
document.querySelector("#logout-button").addEventListener("click", async () => { try { await post("/api/v1/auth/browser-logout"); } finally { window.location.replace("/login"); } });
document.querySelector("#menu-toggle").addEventListener("click", (event) => { const sidebar = document.querySelector("#sidebar"); sidebar.classList.toggle("open"); event.currentTarget.setAttribute("aria-expanded", String(sidebar.classList.contains("open"))); });
initialize().catch((error) => { if (error instanceof ApiError) main.replaceChildren(errorState(error.message, initialize)); });
