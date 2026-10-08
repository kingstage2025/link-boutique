document.querySelectorAll("[data-phone-demo]").forEach((demo) => {
  const views = [...demo.querySelectorAll(".demo-view")];
  let current = 0;
  let timer;

  const show = (index) => {
    current = index % views.length;
    views.forEach((view, position) => view.classList.toggle("is-active", position === current));
  };

  const next = () => show(current + 1);
  const restart = () => {
    window.clearInterval(timer);
    timer = window.setInterval(next, 3200);
  };

  demo.addEventListener("click", (event) => {
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
