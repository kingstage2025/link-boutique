document.querySelectorAll("[data-phone-demo]").forEach((demo) => {
  const views = [...demo.querySelectorAll(".demo-view")];
  const roleButtons = [...demo.querySelectorAll("[data-demo-role]")];
  let current = 0;
  let timer;

  const show = (index) => {
    current = index % views.length;
    views.forEach((view, position) => view.classList.toggle("is-active", position === current));
  };

  const next = () => show(current + 1);
  const restart = () => {
    window.clearInterval(timer);
    if (current === views.length - 1) return;
    timer = window.setInterval(next, 3200);
  };
  const selectRole = (role) => {
    roleButtons.forEach((button) => button.classList.toggle("is-selected", button.dataset.demoRole === role));
    show(role === "merchant" ? views.length - 1 : 0);
  };

  demo.addEventListener("click", (event) => {
    const role = event.target.closest("[data-demo-role]");
    if (role) {
      selectRole(role.dataset.demoRole);
      restart();
      return;
    }
    const control = event.target.closest("[data-demo-step]");
    if (control) {
      show(Number(control.dataset.demoStep));
    } else if (!event.target.closest("button")) {
      next();
    }
    restart();
  });
  demo.addEventListener("mouseenter", () => window.clearInterval(timer));
  demo.addEventListener("mouseleave", restart);
  demo.addEventListener("focusin", () => window.clearInterval(timer));
  demo.addEventListener("focusout", restart);
  show(0);
  restart();
});
