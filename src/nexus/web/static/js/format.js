export const money = (cents) => new Intl.NumberFormat("pt-BR", {style: "currency", currency: "BRL"}).format(cents / 100);
export const dateTime = (value) => value ? new Intl.DateTimeFormat("pt-BR", {dateStyle: "short", timeStyle: "short"}).format(new Date(value)) : "Nunca";
export const shortId = (value) => value ? `${value.slice(0, 8)}…` : "—";
export const label = (value) => ({
  authorized: "Autorizada", pending_approval: "Aguardando decisão", blocked: "Bloqueada",
  approved: "Aprovada", rejected: "Rejeitada", active: "Ativa", revoked: "Revogada",
  human: "Humano", agent: "Agente", system: "Sistema",
  admin: "Administrador", approver: "Aprovador", viewer: "Observador",
  expired: "Expirada", inactive: "Inativo",
  human_approval_required: "Acima do limite automático",
  within_automatic_limit: "Dentro do limite automático",
  exceeds_maximum_limit: "Acima do limite máximo",
  operation_not_allowed: "Operação não permitida",
  agent_inactive: "Agente inativo",
}[value] || String(value || "—").replaceAll("_", " "));
export const statusClass = (value) => `status status-${value || "neutral"}`;
