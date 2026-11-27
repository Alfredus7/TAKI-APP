document.addEventListener("DOMContentLoaded", () => {
    // Ocultar alertas flash después de 5 s
    document.querySelectorAll(".alert").forEach((el) => {
        setTimeout(() => {
            el.style.opacity = "0";
            setTimeout(() => el.remove(), 400);
        }, 5000);
    });

    // Mostrar/ocultar contraseña
    document.querySelectorAll(".toggle-pass").forEach((btn) => {
        btn.addEventListener("click", () => {
            const input = btn.parentElement.querySelector("input");
            input.type = input.type === "password" ? "text" : "password";
        });
    });

    // Registro: alternar campos según rol
    const roles = document.querySelectorAll('input[name="rol"]');
    const cliente = document.getElementById("campos-cliente");
    const conductor = document.getElementById("campos-conductor");
    if (roles.length && cliente && conductor) {
        const actualizar = () => {
            const esConductor = document.querySelector('input[name="rol"]:checked').value === "conductor";
            conductor.hidden = !esConductor;
            cliente.hidden = esConductor;
            conductor.querySelector('input[name="licencia"]').required = esConductor;
        };
        roles.forEach((r) => r.addEventListener("change", actualizar));
        actualizar();
    }
});
