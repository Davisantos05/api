import {post, ApiError} from "./api.js";

const form = document.querySelector("#login-form");
const button = document.querySelector("#login-button");
const alert = document.querySelector("#login-alert");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (button.disabled) return;
  button.disabled = true; button.textContent = "Verificando…";
  alert.classList.add("hidden");
  try {
    await post("/api/v1/auth/browser-login", {
      company_slug: form.elements.company_slug.value.trim(),
      email: form.elements.email.value.trim(),
      password: form.elements.password.value,
    });
    form.elements.password.value = "";
    window.location.replace("/");
  } catch (error) {
    alert.textContent = error instanceof ApiError && error.status === 401
      ? "Empresa, e-mail ou senha inválidos."
      : "Não foi possível entrar agora. Tente novamente.";
    alert.classList.remove("hidden");
  } finally {
    button.disabled = false; button.textContent = "Entrar →";
  }
});
