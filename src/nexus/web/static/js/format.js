export const money = (cents) => new Intl.NumberFormat("pt-BR", {style: "currency", currency: "BRL"}).format(cents / 100);
export const dateTime = (value) => value ? new Intl.DateTimeFormat("pt-BR", {dateStyle: "short", timeStyle: "short"}).format(new Date(value)) : "Nunca";
export const shortId = (value) => value ? `${value.slice(0, 8)}…` : "—";
export const label = (value) => ({
  authorized: "Autorizada", pending_approval: "Aguardando aprovação", blocked: "Bloqueada",
  approved: "Aprovada", rejected: "Rejeitada", active: "Ativa", revoked: "Revogada",
  human: "Humano", agent: "Agente", system: "Sistema",
}[value] || String(value || "—").replaceAll("_", " "));
export const statusClass = (value) => `status status-${value || "neutral"}`;
