import {get, post, ApiError} from "./api.js";
import {dateTime, label, money, shortId} from "./format.js";
import {badge, clear, el, empty, errorState, field, heading, icon, loading, toast} from "./ui.js";

const main = document.querySelector("#main-content");
const modal = document.querySelector("#modal");
const modalTitle = document.querySelector("#modal-title");
const modalContent = document.querySelector("#modal-content");
let currentUser;
let modalVersion = 0;
let navigationVersion = 0;
const capabilities = {
  admin: new Set(["dashboard", "operations", "approvals", "agents", "audit"]),
  approver: new Set(["dashboard", "operations", "approvals", "audit"]),
  viewer: new Set(["dashboard", "operations", "agents"]),
};
const pages = [["dashboard", "Visão geral"], ["operations", "Operações"], ["approvals", "Aprovações"], ["agents", "Agentes"], ["audit", "Auditoria"]];

// Clear content and event closures on every close, including Escape and logout.
function discardModal() { modalVersion += 1; clear(modalContent); }
function closeModal() { modal.close(); discardModal(); }
modal.addEventListener("close", discardModal);
modal.addEventListener("cancel", discardModal);
document.querySelector("#modal .icon-button").addEventListener("click", closeModal);
function openModal(title, content) {
  modalVersion += 1;
  modalTitle.textContent = title;
  modalContent.replaceChildren(content);
  if (!modal.open) modal.showModal();
}
function query(params) {
  const value = new URLSearchParams(Object.entries(params).filter(([, item]) => item));
  return value.size ? `?${value}` : "";
}
function details(pairs, className = "detail-grid") {
  return el("dl", {class: className}, pairs.map(([term, value]) => el("div", {}, [el("dt", {text: term}), el("dd", {text: value ?? "—"})])));
}
function pageTable(headers, rows) {
  const table = el("table");
  const head = el("tr");
  headers.forEach((item) => head.append(el("th", {text: item, scope: "col"})));
  table.append(el("thead", {}, head), el("tbody", {}, rows));
  return el("div", {class: "table-wrap", tabindex: "0", role: "region", "aria-label": "Tabela de dados"}, table);
}
function clickableRow(name, action) {
  const row = el("tr", {tabindex: "0", role: "button", "aria-label": name, onclick: action});
  row.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); action(); }
  });
  return row;
}
function statusFor(operation) { return operation.approval?.decision || operation.policy_outcome; }
function humanStatus(item) {
  return item.approval ? badge(item.approval.decision, label(item.approval.decision)) : el("span", {class: "muted", text: item.policy_outcome === "pending_approval" ? "Aguardando decisão" : "Não requerida"});
}
function beginPage() {
  const version = navigationVersion;
  main.replaceChildren(loading());
  return () => version === navigationVersion;
}

async function renderDashboard() {
  const active = beginPage();
  try {
    const [summary, operations, attention] = await Promise.all([
      get("/api/v1/dashboard/summary"), get("/api/v1/operations?limit=6"), get("/api/v1/dashboard/attention"),
    ]);
    if (!active()) return;
    const cards = [
      ["Agentes ativos", summary.agents_active, "Identidades disponíveis para operar"],
      ["Operações processadas", summary.operations_total, "Operações processadas pelo NEXUS"],
      ["Autorizadas", summary.authorized, "Dentro do limite automático"],
      ["Aguardando decisão", summary.pending_approval, "Solicitações sem decisão humana"],
      ["Bloqueadas", summary.blocked, "Operações bloqueadas pelas políticas"],
      ["Decisões humanas", summary.human_approved + summary.human_rejected, `${summary.human_approved} aprovadas • ${summary.human_rejected} rejeitadas`],
    ].map(([name, value, detail]) => el("article", {class: "metric-card"}, [el("span", {text: name}), el("strong", {text: value}), el("small", {text: detail})]));
    const review = el("section", {class: "panel attention-panel", "aria-labelledby": "attention-title"}, [
      el("div", {class: "panel-heading"}, el("h2", {id: "attention-title", text: "Requer atenção"})),
      attention.length ? el("p", {class: "attention-count", text: `${summary.pending_approval} ${summary.pending_approval === 1 ? "solicitação aguardando decisão" : "solicitações aguardando decisão"}`}) : null,
      ...attention.map((item) => el("div", {class: "attention-row"}, [
        el("div", {}, [
          el("strong", {text: `${item.agent_name} · ${item.operation} · ${money(item.amount_cents)}`}),
          el("small", {text: `Acima do limite automático de ${money(item.policy_snapshot.automatic_limit_cents)}`}),
          el("small", {text: `Limite máximo ${money(item.policy_snapshot.maximum_limit_cents)} · ${dateTime(item.created_at)}`}),
        ]),
        el("button", {class: "button secondary", type: "button", text: "Revisar solicitação →", onclick: () => reviewOperation(item.operation_id)}),
      ])),
      !attention.length ? el("p", {class: "muted", text: "Nenhuma operação aguardando decisão."}) : null,
      summary.pending_approval > attention.length && capabilities[currentUser.role].has("approvals") ? el("a", {href: "#approvals", text: "Ver todas as solicitações →"}) : null,
    ]);
    main.replaceChildren(heading("Visão geral", "Indicadores operacionais da sua empresa."), el("section", {class: "metrics", "aria-label": "Indicadores operacionais"}, cards), review,
      el("section", {class: "panel"}, [el("div", {class: "panel-heading"}, [el("h2", {text: "Atividade recente"}), el("a", {href: "#operations", text: "Ver todas →"})]), operations.length ? operationTable(operations, true) : empty("Nenhuma operação", "As solicitações dos agentes aparecerão aqui.")]));
  } catch (error) { if (active()) main.replaceChildren(errorState(error.message, renderDashboard)); }
}

function operationTable(items, compact = false) {
  const headers = compact ? ["Horário", "Agente", "Operação", "Valor", "Status"] : ["Horário", "Solicitação", "Agente", "Operação", "Valor", "Resultado da política", "Decisão humana"];
  return pageTable(headers, items.map((item) => {
    const row = clickableRow(`Abrir operação ${shortId(item.request_id)}`, () => showOperation(item.operation_id));
    const values = [dateTime(item.created_at), ...(compact ? [] : [shortId(item.request_id)]), item.agent_name, item.operation, money(item.amount_cents)];
    values.forEach((value) => row.append(el("td", {text: value})));
    row.append(el("td", {}, badge(compact ? statusFor(item) : item.policy_outcome, label(compact ? statusFor(item) : item.policy_outcome))));
    if (!compact) row.append(el("td", {}, humanStatus(item)));
    return row;
  }));
}

async function renderOperations() {
  const active = beginPage();
  try {
    const items = await get("/api/v1/operations?limit=100");
    // Approvers can view operations but cannot list agent identities through RBAC.
    const agents = capabilities[currentUser.role].has("agents") ? await get("/api/v1/agents") : [...new Map(items.map((item) => [item.agent_id, {id: item.agent_id, name: item.agent_name}])).values()];
    if (!active()) return;
    const agent = el("select", {id: "operation-agent"}, [el("option", {value: "", text: "Todos os agentes"}), ...agents.map((item) => el("option", {value: item.id, text: item.name}))]);
    const status = el("select", {id: "operation-status"}, [el("option", {value: "", text: "Todos os resultados"}), ...["authorized", "pending_approval", "blocked"].map((item) => el("option", {value: item, text: label(item)}))]);
    const result = el("div", {id: "operations-result"}, items.length ? operationTable(items) : empty("Nenhuma operação", "Ainda não há solicitações registradas."));
    const filter = el("button", {class: "button secondary", text: "Aplicar filtros", type: "button", onclick: async () => {
      if (filter.disabled) return;
      filter.disabled = true;
      try {
        const data = await get(`/api/v1/operations${query({agent_id: agent.value, outcome: status.value, limit: "100"})}`);
        if (active()) result.replaceChildren(data.length ? operationTable(data) : empty("Sem resultados", "Altere os filtros e tente novamente."));
      } catch (error) { toast(error.message, "error"); }
      finally { filter.disabled = false; }
    }});
    main.replaceChildren(heading("Operações", "Resultado original da política e decisão humana, preservados no histórico."), el("section", {class: "filter-bar", "aria-label": "Filtros de operações"}, [field("Agente", agent), field("Resultado da política", status), filter]), result);
  } catch (error) { if (active()) main.replaceChildren(errorState(error.message, renderOperations)); }
}

function policyView(snapshot) {
  return el("section", {class: "policy-box"}, [el("h3", {text: "Política aplicada no momento da operação"}), details([
    ["Agente ativo", snapshot.active ? "Sim" : "Não"], ["Permissões", Array.isArray(snapshot.allowed_operations) ? snapshot.allowed_operations.join(", ") : "—"],
    ["Limite automático", money(snapshot.automatic_limit_cents)], ["Limite máximo", money(snapshot.maximum_limit_cents)],
  ])]);
}
function operationDetails(item) {
  return el("div", {class: "detail-stack"}, [details([
    ["Agente", item.agent_name], ["Operação", item.operation], ["Valor", money(item.amount_cents)], ["Horário", dateTime(item.created_at)],
    ["Resultado original", label(item.policy_outcome)], ["Motivo da política", label(item.policy_reason)], ["Solicitação", item.request_id],
    ["Decisão humana", item.approval ? label(item.approval.decision) : item.policy_outcome === "pending_approval" ? "Aguardando decisão" : "Não requerida"],
    ["Responsável", item.approval?.decided_by_user_name || item.approval?.decided_by_user_id || "—"],
    ["Justificativa", item.approval?.reason || "—"], ["Horário da decisão", item.approval ? dateTime(item.approval.created_at) : "—"],
  ]), policyView(item.policy_snapshot)]);
}
async function showOperation(id) {
  const version = modalVersion;
  try {
    const item = await get(`/api/v1/operations/${id}`);
    if (version === modalVersion) openModal("Detalhes da operação", operationDetails(item));
  } catch (error) { toast(error.message, "error"); }
}
function approvalActions(item) {
  return el("div", {class: "card-actions"}, [
    el("button", {class: "button success", text: "Aprovar", type: "button", onclick: () => decisionDialog(item, "approved")}),
    el("button", {class: "button danger", text: "Rejeitar", type: "button", onclick: () => decisionDialog(item, "rejected")}),
  ]);
}
async function reviewOperation(id) {
  const version = modalVersion;
  try {
    const item = await get(`/api/v1/operations/${id}`);
    if (version !== modalVersion) return;
    const content = operationDetails(item);
    if (!item.approval && item.policy_outcome === "pending_approval" && capabilities[currentUser.role].has("approvals")) content.append(approvalActions(item));
    openModal("Revisar solicitação", content);
  } catch (error) { toast(error.message, "error"); }
}
async function renderApprovals() {
  const active = beginPage();
  try {
    const items = await get("/api/v1/approvals?status=pending&limit=100");
    if (!active()) return;
    const content = items.length ? el("div", {class: "approval-grid"}, items.map((item) => el("article", {class: "approval-card"}, [
      el("div", {class: "approval-title"}, [el("span", {class: "avatar", text: item.agent_name.slice(0, 1)}), el("div", {}, [el("h2", {text: item.agent_name}), el("p", {text: `${item.operation} · ${dateTime(item.created_at)}`})])]),
      el("strong", {class: "approval-value", text: money(item.amount_cents)}), badge("pending_approval", "Aguardando decisão"),
      el("p", {class: "approval-reason", text: `${label(item.policy_reason)} de ${money(item.policy_snapshot.automatic_limit_cents)}`}),
      policyView(item.policy_snapshot), approvalActions(item),
    ]))) : empty("Tudo em dia", "Nenhuma operação aguardando decisão.");
    main.replaceChildren(heading("Aprovações", "Revise solicitações e decida com base na política aplicada."), content);
  } catch (error) { if (active()) main.replaceChildren(errorState(error.message, renderApprovals)); }
}
function decisionDialog(item, choice) {
  const reason = el("textarea", {id: "decision-reason", rows: "3", maxlength: "1000", placeholder: "Justificativa opcional"});
  const submit = el("button", {class: choice === "approved" ? "button success" : "button danger", type: "button", text: choice === "approved" ? "Confirmar aprovação" : "Confirmar rejeição"});
  submit.addEventListener("click", async () => {
    if (submit.disabled) return;
    submit.disabled = true;
    const version = modalVersion;
    try {
      await post(`/api/v1/approvals/${item.operation_id}/decision`, {decision: choice, reason: reason.value.trim() || null});
      if (version === modalVersion) closeModal();
      toast(choice === "approved" ? "Operação aprovada." : "Operação rejeitada.");
      await navigate();
    } catch (error) {
      if (error.status === 409) {
        if (version === modalVersion) closeModal();
        toast("Esta operação já foi decidida por outro usuário.", "error");
        await navigate();
      } else { toast(error.message, "error"); submit.disabled = false; }
    }
  });
  openModal(choice === "approved" ? "Aprovar operação" : "Rejeitar operação", el("div", {class: "detail-stack"}, [operationDetails(item), field("Justificativa", reason), el("div", {class: "modal-actions"}, submit)]));
}

async function renderAgents() {
  const active = beginPage();
  try {
    const agents = await get("/api/v1/agents");
    if (!active()) return;
    const create = currentUser.role === "admin" ? el("button", {class: "button primary", text: "Novo agente", type: "button", onclick: createAgentDialog}) : null;
    const cards = agents.length ? el("div", {class: "agent-grid"}, agents.map((item) => el("article", {class: "agent-card"}, [
      el("div", {class: "agent-card-head"}, [el("span", {class: "avatar", text: item.name.slice(0, 1)}), badge(item.active ? "active" : "inactive", item.active ? "Ativo" : "Inativo")]),
      el("h2", {text: item.name}), el("p", {text: item.description || "Sem descrição"}),
      el("p", {class: "permissions", text: item.allowed_operations.join(" · ")}),
      el("div", {class: "limit-row"}, [el("span", {text: `Automático ${money(item.automatic_limit_cents)}`}), el("span", {text: `Máximo ${money(item.maximum_limit_cents)}`})]),
      el("button", {class: "button secondary wide", text: "Ver identidade e limites →", type: "button", onclick: () => agentDialog(item)}),
    ]))) : empty("Nenhum agente", "Crie o primeiro agente para começar.");
    main.replaceChildren(heading("Agentes", "Identidade e cerca operacional de cada agente.", create), cards);
  } catch (error) { if (active()) main.replaceChildren(errorState(error.message, renderAgents)); }
}
async function agentDialog(agent) {
  const version = modalVersion;
  try {
    const operations = await get(`/api/v1/operations?agent_id=${agent.id}&limit=5`);
    const credentials = currentUser.role === "admin" ? await get(`/api/v1/agents/${agent.id}/credentials`) : null;
    if (version !== modalVersion) return;
    openModal(agent.name, el("div", {class: "detail-stack"}, [
      el("p", {class: "muted", text: "Esta é a identidade e a cerca operacional deste agente."}),
      details([["Nome", agent.name], ["Status", agent.active ? "Ativo" : "Inativo"], ["Descrição", agent.description || "Sem descrição"]]),
      el("section", {class: "detail-section"}, [el("h3", {text: "PERMISSÕES"}), el("p", {class: "permissions", text: agent.allowed_operations.join(" · ")})]),
      el("section", {class: "detail-section"}, [el("h3", {text: "LIMITES"}), details([["Automático", money(agent.automatic_limit_cents)], ["Máximo", money(agent.maximum_limit_cents)]])]),
      el("section", {class: "detail-section"}, [el("h3", {text: "CREDENCIAIS"}), credentials ? credentialList(credentials) : el("p", {class: "muted", text: "Disponíveis apenas para administradores."}), currentUser.role === "admin" ? el("div", {class: "modal-actions"}, el("button", {class: "button secondary", type: "button", text: "Gerenciar credenciais", onclick: () => credentialsDialog(agent)})) : null]),
      el("section", {class: "detail-section"}, [el("h3", {text: "ÚLTIMAS OPERAÇÕES"}), operations.length ? operationTable(operations, true) : empty("Nenhuma operação", "Este agente ainda não enviou solicitações.")]),
    ]));
  } catch (error) { toast(error.message, "error"); }
}
function createAgentDialog() {
  const inputs = {name: el("input", {id: "agent-name", required: "", maxlength: "200"}), description: el("textarea", {id: "agent-description", rows: "3", maxlength: "2000"}), permissions: el("input", {id: "agent-permissions", value: "purchase", required: ""}), automatic: el("input", {id: "agent-automatic", type: "number", min: "0", step: "1", value: "50000", required: ""}), maximum: el("input", {id: "agent-maximum", type: "number", min: "0", step: "1", value: "200000", required: ""})};
  const save = el("button", {class: "button primary", type: "submit", text: "Criar agente"});
  const form = el("form", {}, [field("Nome", inputs.name), field("Descrição", inputs.description), field("Permissões (separadas por vírgula)", inputs.permissions), el("div", {class: "two-columns"}, [field("Limite automático (centavos)", inputs.automatic), field("Limite máximo (centavos)", inputs.maximum)]), el("div", {class: "modal-actions"}, save)]);
  form.addEventListener("submit", async (event) => {
    event.preventDefault(); if (save.disabled) return; save.disabled = true;
    const version = modalVersion;
    try {
      await post("/api/v1/agents", {name: inputs.name.value.trim(), description: inputs.description.value.trim(), allowed_operations: inputs.permissions.value.split(",").map((v) => v.trim()).filter(Boolean), automatic_limit_cents: Number(inputs.automatic.value), maximum_limit_cents: Number(inputs.maximum.value)});
      if (version === modalVersion) closeModal(); toast("Agente criado."); await navigate();
    } catch (error) { toast(error.message, "error"); save.disabled = false; }
  });
  openModal("Criar agente", form);
}
function credentialStatus(item) {
  if (item.revoked_at) return ["revoked", "Revogada"];
  if (item.expires_at && new Date(item.expires_at) <= new Date()) return ["expired", "Expirada"];
  return ["active", "Ativa"];
}
function credentialList(items, revoke = null) {
  return items.length ? el("div", {class: "credential-list"}, items.map((item) => {
    const [status, text] = credentialStatus(item);
    return el("div", {class: "credential-row"}, [el("div", {}, [el("strong", {text: item.token_prefix}),
      el("small", {text: `Criação: ${dateTime(item.created_at)}`}), el("small", {text: `Expiração: ${item.expires_at ? dateTime(item.expires_at) : "Sem expiração"}`}), el("small", {text: `Último uso: ${dateTime(item.last_used_at)}`}),
    ]), badge(status, text), revoke && !item.revoked_at ? el("button", {class: "button danger ghost", text: "Revogar", type: "button", onclick: (event) => revoke(item, event.currentTarget)}) : null]);
  })) : empty("Sem credenciais", "Nenhuma credencial registrada para este agente.");
}
async function credentialsDialog(agent) {
  const body = el("div", {}, loading());
  openModal(`Credenciais — ${agent.name}`, body);
  const version = modalVersion;
  async function reload() {
    try {
      const items = await get(`/api/v1/agents/${agent.id}/credentials`);
      if (version !== modalVersion || !modal.open) return;
      const create = el("button", {class: "button primary", text: "Gerar nova credencial", type: "button", onclick: (event) => generate(event.currentTarget)});
      body.replaceChildren(create, credentialList(items, revoke));
    } catch (error) { if (version === modalVersion) body.replaceChildren(errorState(error.message, reload)); }
  }
  async function generate(button) {
    if (button.disabled) return; button.disabled = true;
    try {
      const result = await post(`/api/v1/agents/${agent.id}/credentials`, {});
      // A response arriving after dismissal must never reopen the secret dialog.
      if (version !== modalVersion || !modal.open) return;
      const token = el("code", {class: "one-time-key", text: result.token});
      const copy = el("button", {class: "button primary wide", type: "button", text: "Copiar chave", onclick: async () => {
        try { await navigator.clipboard.writeText(token.textContent); copy.textContent = "Copiada"; }
        catch (_error) { toast("Não foi possível copiar. Selecione a chave e copie manualmente.", "error"); }
      }});
      openModal("Nova credencial criada", el("div", {}, [el("p", {text: "Copie esta chave agora. Ela não poderá ser exibida novamente."}), token, copy, el("p", {class: "security-note", text: "Ao fechar, a chave será removida da interface."})]));
    } catch (error) { toast(error.message, "error"); button.disabled = false; }
  }
  async function revoke(item, button) {
    if (button.disabled || !window.confirm(`Revogar a credencial ${item.token_prefix}? O agente perderá o acesso por esta chave.`)) return;
    button.disabled = true;
    try { await post(`/api/v1/agents/${agent.id}/credentials/${item.id}/revoke`); toast("Credencial revogada."); await reload(); }
    catch (error) { toast(error.message, "error"); button.disabled = false; }
  }
  await reload();
}

async function renderAudit() {
  const active = beginPage();
  try {
    const events = await get("/api/v1/audit-events?limit=100");
    if (!active()) return;
    const rows = events.map((item) => {
      const row = clickableRow(`Abrir evento ${item.action}`, () => openModal("Detalhes do evento", el("div", {class: "detail-stack"}, [
        details([["Horário", dateTime(item.created_at)], ["Ator", item.actor_name], ["Tipo", label(item.actor_type)], ["Ação", item.action], ["Alvo", `${item.target_type} · ${item.target_id}`]]),
        el("section", {class: "detail-section"}, [el("h3", {text: "METADADOS"}), Object.keys(item.metadata).length ? details(Object.entries(item.metadata).map(([key, value]) => [label(key), String(value ?? "—")]), "detail-grid metadata-grid") : el("p", {class: "muted", text: "Sem metadados adicionais."})]),
      ])));
      [dateTime(item.created_at), item.actor_name, label(item.actor_type), item.action, `${item.target_type} · ${shortId(item.target_id)}`].forEach((value) => row.append(el("td", {text: value})));
      return row;
    });
    main.replaceChildren(heading("Auditoria", "Histórico de operações e decisões. Eventos somente para consulta."), events.length ? pageTable(["Horário", "Ator", "Tipo", "Ação", "Alvo"], rows) : empty("Sem eventos", "Os eventos de segurança e operação aparecerão aqui."));
  } catch (error) { if (active()) main.replaceChildren(errorState(error.message, renderAudit)); }
}

const renderers = {dashboard: renderDashboard, operations: renderOperations, approvals: renderApprovals, agents: renderAgents, audit: renderAudit};
function setSidebar(open) {
  document.querySelector("#sidebar").classList.toggle("open", open);
  document.querySelector("#menu-toggle").setAttribute("aria-expanded", String(open));
  document.querySelector("#sidebar-backdrop").hidden = !open;
}
async function navigate() {
  navigationVersion += 1;
  let page = location.hash.slice(1) || "dashboard";
  if (!capabilities[currentUser.role].has(page)) page = "dashboard";
  document.querySelectorAll("nav a").forEach((item) => {
    const active = item.dataset.page === page;
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page"); else item.removeAttribute("aria-current");
  });
  if (modal.open) closeModal();
  setSidebar(false);
  await renderers[page]();
  main.focus({preventScroll: true});
}
async function initialize() {
  currentUser = await get("/api/v1/auth/me");
  document.querySelector("#company-name").textContent = currentUser.company_name;
  document.querySelector("#user-name").textContent = currentUser.name;
  document.querySelector("#user-role").textContent = label(currentUser.role);
  document.querySelector("#user-initial").textContent = currentUser.name.slice(0, 1).toUpperCase();
  const navigation = document.querySelector("#navigation"); clear(navigation);
  pages.filter(([key]) => capabilities[currentUser.role].has(key)).forEach(([key, text]) => navigation.append(el("a", {href: `#${key}`, "data-page": key}, [icon(key), el("span", {text})])));
  await navigate();
}
window.addEventListener("hashchange", () => { if (currentUser) navigate(); });
document.querySelector("#logout-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (button.disabled) return; button.disabled = true;
  try { await post("/api/v1/auth/browser-logout"); closeModal(); window.location.replace("/login"); }
  catch (error) { toast("Não foi possível encerrar sua sessão. Tente novamente.", "error"); button.disabled = false; }
});
document.querySelector("#menu-toggle").addEventListener("click", () => setSidebar(!document.querySelector("#sidebar").classList.contains("open")));
document.querySelector("#sidebar-backdrop").addEventListener("click", () => setSidebar(false));
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && document.querySelector("#sidebar").classList.contains("open")) { setSidebar(false); document.querySelector("#menu-toggle").focus(); } });
initialize().catch((error) => { if (error instanceof ApiError) main.replaceChildren(errorState(error.message, initialize)); });
