export function el(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(options)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = String(value);
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  }
  for (const child of Array.isArray(children) ? children : [children]) {
    if (child) node.append(child);
  }
  return node;
}

export function clear(node) { node.replaceChildren(); }
export function heading(title, description, action = null) {
  const copy = el("div", {}, [el("p", {class: "eyebrow", text: "NEXUS CONTROL CENTER"}), el("h1", {text: title}), el("p", {class: "muted", text: description})]);
  return el("header", {class: "page-header"}, action ? [copy, action] : [copy]);
}
export function badge(value, text) { return el("span", {class: `status status-${value}`, text}); }
export function empty(title, detail) { return el("div", {class: "empty-state"}, [el("strong", {text: title}), el("p", {text: detail})]); }
export function loading() { return el("div", {class: "page-loading", text: "Carregando dados…", role: "status"}); }
export function errorState(message, retry) { return el("div", {class: "error-state"}, [el("strong", {text: "Não foi possível carregar"}), el("p", {text: message}), el("button", {class: "button secondary", text: "Tentar novamente", type: "button", onclick: retry})]); }
export function toast(message, kind = "success") {
  const region = document.querySelector("#toast-region");
  const item = el("div", {class: `toast ${kind}`, text: message, role: "status"});
  region.append(item); setTimeout(() => item.remove(), 4500);
}
export function field(labelText, input) { const id = input.id; return el("div", {class: "field"}, [el("label", {for: id, text: labelText}), input]); }
