document.addEventListener("DOMContentLoaded", () => {
  const alerts = document.querySelectorAll(".alert");
  alerts.forEach((alert) => {
    setTimeout(() => {
      alert.classList.add("fade");
      setTimeout(() => alert.remove(), 250);
    }, 4500);
  });

  const registerForm = document.querySelector("[data-register-form]");
  if (registerForm) {
    const fullName = registerForm.querySelector('input[name="full_name"]');
    const organizationName = registerForm.querySelector('input[name="organization_name"]');
    const organizationField = registerForm.querySelector("[data-organization-field]");
    const password1 = registerForm.querySelector('input[name="password1"]');
    const password2 = registerForm.querySelector('input[name="password2"]');
    const roleInputs = registerForm.querySelectorAll('input[name="role"]');
    const toggleRoleCards = () => {
      let selectedRole = "";
      roleInputs.forEach((input) => {
        input.closest(".role-option-card")?.classList.toggle("is-selected", input.checked);
        if (input.checked) {
          selectedRole = input.value;
        }
      });
      const needsOrganization = selectedRole === "BANK_OFFICER";
      if (organizationField) {
        organizationField.hidden = !needsOrganization;
      }
      if (organizationName) {
        organizationName.required = needsOrganization;
        if (!needsOrganization) {
          organizationName.setCustomValidity("");
        }
      }
    };
    const syncFullName = () => {
      if (!fullName) {
        return;
      }
      const words = fullName.value.trim().split(/\s+/).filter(Boolean);
      if (fullName.value.trim() && words.length < 2) {
        fullName.setCustomValidity("Please enter your full name.");
      } else {
        fullName.setCustomValidity("");
      }
    };
    const syncPasswordMatch = () => {
      if (!password1 || !password2) {
        return;
      }
      if (password2.value && password1.value !== password2.value) {
        password2.setCustomValidity("Passwords do not match.");
      } else {
        password2.setCustomValidity("");
      }
    };
    const syncOrganization = () => {
      if (!organizationName) {
        return;
      }
      const selectedRole = Array.from(roleInputs).find((input) => input.checked)?.value;
      if (selectedRole === "BANK_OFFICER" && !organizationName.value.trim()) {
        organizationName.setCustomValidity("Enter the bank, NBFC, or financial company where you work.");
      } else {
        organizationName.setCustomValidity("");
      }
    };

    fullName?.addEventListener("input", syncFullName);
    organizationName?.addEventListener("input", syncOrganization);
    password1?.addEventListener("input", syncPasswordMatch);
    password2?.addEventListener("input", syncPasswordMatch);
    roleInputs.forEach((input) =>
      input.addEventListener("change", () => {
        toggleRoleCards();
        syncOrganization();
      })
    );
    registerForm.addEventListener("submit", () => {
      syncFullName();
      syncOrganization();
      syncPasswordMatch();
    });
    toggleRoleCards();
    syncOrganization();
  }
});
