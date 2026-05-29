const shell = document.querySelector("[data-shell]");
const toggle = document.querySelector("[data-sidebar-toggle]");

if (shell && toggle) {
  const stored = window.localStorage.getItem("fraudlens-sidebar");
  if (stored === "collapsed") {
    shell.classList.add("sidebar-collapsed");
    toggle.setAttribute("aria-expanded", "false");
  }

  toggle.addEventListener("click", () => {
    const collapsed = shell.classList.toggle("sidebar-collapsed");
    toggle.setAttribute("aria-expanded", String(!collapsed));
    window.localStorage.setItem("fraudlens-sidebar", collapsed ? "collapsed" : "expanded");
  });
}
