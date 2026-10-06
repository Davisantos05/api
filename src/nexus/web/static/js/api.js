const WEB_HEADER = {"X-Nexus-Web-Request": "1"};

export class ApiError extends Error {
  constructor(status, code, message, details = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  headers.set("X-Nexus-Web-Request", WEB_HEADER["X-Nexus-Web-Request"]);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response;
  try {
    response = await fetch(path, {...options, headers, credentials: "same-origin"});
  } catch (_error) {
    throw new ApiError(0, "network_error", "Não foi possível conectar ao NEXUS.");
  }
  if (response.status === 401 && path !== "/api/v1/auth/browser-login") {
    window.location.replace("/login");
    throw new ApiError(401, "invalid_session", "Sua sessão expirou.");
  }
  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const error = payload?.error || {};
    const friendly = {
      403: "Você não possui permissão para executar esta ação.",
      404: "O recurso solicitado não foi encontrado.",
      422: "Revise os dados informados e tente novamente.",
      500: "O NEXUS encontrou um erro inesperado.",
    }[response.status];
    throw new ApiError(response.status, error.code || "request_failed", friendly || error.message || "A solicitação falhou.", error.details);
  }
  return payload;
}

export const get = (path) => api(path);
export const post = (path, data = {}) => api(path, {method: "POST", body: JSON.stringify(data)});
