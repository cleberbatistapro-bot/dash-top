(function () {
  const ICONE_SOL =
    '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<circle cx="12" cy="12" r="4"></circle>' +
    '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path>' +
    "</svg>";

  const ICONE_LUA =
    '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"></path>' +
    "</svg>";

  function temaAtual() {
    return localStorage.getItem("dashtop_tema") || "dark";
  }

  function atualizarIconeBotao(tema) {
    const botao = document.getElementById("botao-tema");
    if (!botao) return;
    botao.innerHTML = tema === "dark" ? ICONE_LUA : ICONE_SOL;
    botao.setAttribute("aria-label", tema === "dark" ? "Mudar para tema claro" : "Mudar para tema escuro");
    botao.title = botao.getAttribute("aria-label");
  }

  function aplicarTema(tema) {
    document.documentElement.setAttribute("data-theme", tema);
    localStorage.setItem("dashtop_tema", tema);
    atualizarIconeBotao(tema);
  }

  function alternarTema() {
    const novoTema = temaAtual() === "dark" ? "light" : "dark";
    aplicarTema(novoTema);
    document.dispatchEvent(new CustomEvent("dashtop:tema-mudou", { detail: { tema: novoTema } }));
  }

  window.DashTopTema = { obter: temaAtual, aplicar: aplicarTema, alternar: alternarTema };

  document.addEventListener("DOMContentLoaded", function () {
    aplicarTema(temaAtual());
    const botao = document.getElementById("botao-tema");
    if (botao) {
      botao.addEventListener("click", alternarTema);
    }
  });
})();
