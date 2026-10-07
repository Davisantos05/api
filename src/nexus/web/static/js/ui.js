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
  const copy = el("div", {}, [el("h1", {text: title}), el("p", {class: "muted", text: description})]);
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

// Fixed paths for navigation icons; brand assets remain the official PNG files.
export function icon(name) {
  const paths = {
    dashboard: ["M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z"],
    operations: ["M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4"],
    approvals: ["M9 3H5v18h14V3h-4", "M9 2h6v4H9z", "m8 13 3 3 5-6"],
    agents: ["M8 3h8v5H8zM3 16h6v5H3zM15 16h6v5h-6z", "M12 8v4M6 16v-4h12v4"],
    audit: ["M5 3h14v18H5z", "M8 7h8M8 12h8M8 17h5"],
  };
  const ns = "http://www.w3.org/2000/svg";
  const node = document.createElementNS(ns, "svg");
  for (const [key, value] of Object.entries({viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.5", "stroke-linecap": "round", "stroke-linejoin": "round", class: "nav-icon", "aria-hidden": "true"})) node.setAttribute(key, value);
  for (const d of paths[name] || []) {
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", d);
    node.append(path);
  }
  return node;
}
