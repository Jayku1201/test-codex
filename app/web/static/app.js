let flashTimer = null;

document.addEventListener("DOMContentLoaded", () => {
  setupModals();
  setupExportForm();
  setupImportForm();
  setupContactForm();
  setupInteractionForm();
  setupReminderForm();
  setupInteractionActions();
  setupReminderActions();
});

function showMessage(type, message) {
  const container = document.getElementById("flash-message");
  if (!container) {
    return;
  }

  container.classList.remove("flash-success", "flash-error", "visible");
  if (flashTimer) {
    window.clearTimeout(flashTimer);
    flashTimer = null;
  }

  if (!message) {
    container.textContent = "";
    return;
  }

  container.textContent = message;
  container.classList.add(type === "error" ? "flash-error" : "flash-success", "visible");
  flashTimer = window.setTimeout(() => {
    container.classList.remove("flash-success", "flash-error", "visible");
    container.textContent = "";
  }, 5000);
}

function setupModals() {
  document.querySelectorAll("[data-open-modal]").forEach((trigger) => {
    trigger.addEventListener("click", () => {
      const targetId = trigger.dataset.openModal;
      if (!targetId) {
        return;
      }
      const modal = document.getElementById(targetId);
      if (modal) {
        modal.classList.add("is-open");
      }
    });
  });

  document.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", () => {
      const modal = button.closest(".modal");
      if (modal) {
        modal.classList.remove("is-open");
      }
    });
  });

  document.querySelectorAll(".modal").forEach((modal) => {
    modal.addEventListener("click", (event) => {
      if (event.target === modal) {
        modal.classList.remove("is-open");
      }
    });
  });
}

function setupContactForm() {
  const form = document.getElementById("contact-form");
  if (!form) {
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const contactId = form.dataset.contactId;
    if (!contactId) {
      return;
    }

    const payload = buildContactPayload(form);

    try {
      const response = await fetch(`/api/v1/contacts/${contactId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const message = data?.error?.message ?? "更新聯絡人失敗";
        showMessage("error", message);
        return;
      }

      showMessage("success", "聯絡人資料已更新");
      window.setTimeout(() => window.location.reload(), 800);
    } catch (error) {
      console.error(error);
      showMessage("error", "更新聯絡人時發生錯誤");
    }
  });
}

function buildContactPayload(form) {
  const payload = {
    name: form.elements.namedItem("name").value.trim(),
    company: emptyToNull(form.elements.namedItem("company").value),
    title: emptyToNull(form.elements.namedItem("title").value),
    email: emptyToNull(form.elements.namedItem("email").value),
    phone: emptyToNull(form.elements.namedItem("phone").value),
    note: emptyToNull(form.elements.namedItem("note").value),
    tags: [],
    custom: {},
  };

  const tagsValue = form.elements.namedItem("tags").value;
  if (typeof tagsValue === "string") {
    const tags = tagsValue
      .split(",")
      .map((tag) => tag.trim())
      .filter((tag) => tag.length > 0);
    payload.tags = tags;
  }

  const customFields = form.querySelectorAll("[data-custom-field]");
  customFields.forEach((field) => {
    const key = field.dataset.fieldKey;
    const type = field.dataset.fieldType;
    if (!key || !type) {
      return;
    }

    if (type === "bool") {
      payload.custom[key] = field.checked;
      return;
    }

    if (type === "multi_select") {
      const raw = field.value ?? "";
      const items = raw
        .split(",")
        .map((item) => item.trim())
        .filter((item) => item.length > 0);
      payload.custom[key] = items;
      return;
    }

    const value = emptyToNull(field.value ?? "");
    payload.custom[key] = value;
  });

  return payload;
}

function setupInteractionForm() {
  const form = document.getElementById("interaction-form");
  if (!form) {
    return;
  }

  const happenedInput = form.querySelector("input[name='happened_at']");
  if (happenedInput && !happenedInput.value) {
    const now = new Date();
    const iso = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
    happenedInput.value = iso;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const contactId = form.dataset.contactId;
    if (!contactId) {
      return;
    }

    const formData = new FormData(form);
    const payload = {
      contact_id: Number(contactId),
      type: formData.get("type"),
      happened_at: formData.get("happened_at"),
      summary: emptyToNull(formData.get("summary")),
      content: emptyToNull(formData.get("content")),
    };

    try {
      const response = await fetch("/api/v1/interactions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const message = data?.error?.message ?? "新增互動紀錄失敗";
        showMessage("error", message);
        return;
      }

      showMessage("success", "已新增互動紀錄");
      window.setTimeout(() => window.location.reload(), 600);
    } catch (error) {
      console.error(error);
      showMessage("error", "新增互動紀錄時發生錯誤");
    }
  });
}

function setupReminderForm() {
  const form = document.getElementById("reminder-form");
  if (!form) {
    return;
  }

  const remindInput = form.querySelector("input[name='remind_at']");
  if (remindInput && !remindInput.value) {
    const today = new Date();
    const iso = new Date(today.getTime() - today.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 10);
    remindInput.value = iso;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const contactId = form.dataset.contactId;
    if (!contactId) {
      return;
    }

    const formData = new FormData(form);
    const payload = {
      contact_id: Number(contactId),
      remind_at: formData.get("remind_at"),
      content: formData.get("content"),
      sync_google: formData.has("sync_google"),
    };

    try {
      const response = await fetch("/api/v1/reminders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const message = data?.error?.message ?? "新增提醒失敗";
        showMessage("error", message);
        return;
      }

      showMessage("success", "提醒已建立");
      window.setTimeout(() => window.location.reload(), 600);
    } catch (error) {
      console.error(error);
      showMessage("error", "新增提醒時發生錯誤");
    }
  });
}

function setupInteractionActions() {
  document.querySelectorAll(".delete-interaction").forEach((button) => {
    button.addEventListener("click", async () => {
      const interactionId = button.dataset.interactionId;
      if (!interactionId) {
        return;
      }

      try {
        const response = await fetch(`/api/v1/interactions/${interactionId}`, {
          method: "DELETE",
        });

        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          const message = data?.error?.message ?? "刪除互動紀錄失敗";
          showMessage("error", message);
          return;
        }

        showMessage("success", "互動紀錄已刪除");
        window.setTimeout(() => window.location.reload(), 400);
      } catch (error) {
        console.error(error);
        showMessage("error", "刪除互動紀錄時發生錯誤");
      }
    });
  });
}

function setupReminderActions() {
  document.querySelectorAll(".toggle-reminder").forEach((button) => {
    button.addEventListener("click", async () => {
      const reminderId = button.dataset.reminderId;
      if (!reminderId) {
        return;
      }
      const done = button.dataset.reminderDone === "true";

      try {
        const response = await fetch(`/api/v1/reminders/${reminderId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ done: !done }),
        });

        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          const message = data?.error?.message ?? "更新提醒失敗";
          showMessage("error", message);
          return;
        }

        showMessage("success", "提醒狀態已更新");
        window.setTimeout(() => window.location.reload(), 400);
      } catch (error) {
        console.error(error);
        showMessage("error", "更新提醒時發生錯誤");
      }
    });
  });

  document.querySelectorAll(".delete-reminder").forEach((button) => {
    button.addEventListener("click", async () => {
      const reminderId = button.dataset.reminderId;
      if (!reminderId) {
        return;
      }

      try {
        const response = await fetch(`/api/v1/reminders/${reminderId}`, {
          method: "DELETE",
        });

        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          const message = data?.error?.message ?? "刪除提醒失敗";
          showMessage("error", message);
          return;
        }

        showMessage("success", "提醒已刪除");
        window.setTimeout(() => window.location.reload(), 400);
      } catch (error) {
        console.error(error);
        showMessage("error", "刪除提醒時發生錯誤");
      }
    });
  });
}

function setupImportForm() {
  const form = document.getElementById("import-form");
  if (!form) {
    return;
  }

  const report = document.getElementById("import-report");
  const dryRunButton = document.getElementById("import-dry-run");
  const submitButton = document.getElementById("import-submit");

  const updateReport = (builder) => {
    if (!report) {
      return;
    }
    report.innerHTML = "";
    builder(report);
  };

  dryRunButton?.addEventListener("click", async () => {
    const payload = new FormData(form);
    if (!payload.get("file")) {
      showMessage("error", "請選擇要上傳的 CSV 檔案");
      return;
    }

    try {
      const response = await fetch("/api/v1/import/contacts/dry-run", {
        method: "POST",
        body: payload,
      });
      const data = await response.json();

      if (!response.ok) {
        const message = data?.error?.message ?? "預檢失敗";
        showMessage("error", message);
        return;
      }

      showMessage("success", "預檢完成");
      updateReport((container) => renderDryRunReport(container, data.data));
    } catch (error) {
      console.error(error);
      showMessage("error", "預檢時發生錯誤");
    }
  });

  submitButton?.addEventListener("click", async () => {
    const payload = new FormData(form);
    if (!payload.get("file")) {
      showMessage("error", "請選擇要上傳的 CSV 檔案");
      return;
    }

    try {
      const response = await fetch("/api/v1/import/contacts", {
        method: "POST",
        body: payload,
      });
      const data = await response.json();

      if (!response.ok) {
        const message = data?.error?.message ?? "匯入失敗";
        showMessage("error", message);
        return;
      }

      showMessage("success", `匯入完成：新增 ${data.data.created} 筆，更新 ${data.data.updated} 筆`);
      updateReport((container) => renderImportResult(container, data.data));
      window.setTimeout(() => window.location.reload(), 1200);
    } catch (error) {
      console.error(error);
      showMessage("error", "匯入時發生錯誤");
    }
  });
}

function renderDryRunReport(container, data) {
  if (!data) {
    return;
  }

  const summary = document.createElement("p");
  summary.textContent = `總筆數：${data.total ?? 0}，通過：${data.valid ?? 0}，錯誤：${data.invalid ?? 0}`;
  container.appendChild(summary);

  if (Array.isArray(data.errors) && data.errors.length > 0) {
    const title = document.createElement("h3");
    title.textContent = "錯誤列";
    container.appendChild(title);

    const list = document.createElement("ul");
    data.errors.forEach((error) => {
      const item = document.createElement("li");
      item.textContent = `第 ${error.row} 列：${error.message}`;
      list.appendChild(item);
    });
    container.appendChild(list);
  } else {
    const ok = document.createElement("p");
    ok.textContent = "預檢通過，沒有錯誤。";
    container.appendChild(ok);
  }

  if (Array.isArray(data.sample) && data.sample.length > 0) {
    const title = document.createElement("h3");
    title.textContent = "解析範例";
    container.appendChild(title);

    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(data.sample.slice(0, 3), null, 2);
    container.appendChild(pre);
  }
}

function renderImportResult(container, data) {
  if (!data) {
    return;
  }

  const summary = document.createElement("p");
  summary.textContent = `新增 ${data.created ?? 0} 筆，更新 ${data.updated ?? 0} 筆，略過 ${data.skipped ?? 0} 筆，失敗 ${data.failed ?? 0} 筆`;
  container.appendChild(summary);

  if (data.report_url) {
    const link = document.createElement("a");
    link.href = data.report_url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "下載結果報告";
    container.appendChild(link);
  }
}

function setupExportForm() {
  const form = document.getElementById("export-form");
  if (!form) {
    return;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const params = new URLSearchParams();
    for (const [key, value] of formData.entries()) {
      if (value instanceof File) {
        continue;
      }
      const text = typeof value === "string" ? value.trim() : "";
      if (!text) {
        continue;
      }
      params.append(key, text);
    }

    const url = `/api/v1/export/contacts.csv${params.toString() ? `?${params.toString()}` : ""}`;
    window.open(url, "_blank");

    const modal = form.closest(".modal");
    if (modal) {
      modal.classList.remove("is-open");
    }
  });
}

function emptyToNull(value) {
  if (value == null) {
    return null;
  }
  const text = typeof value === "string" ? value.trim() : String(value).trim();
  return text.length === 0 ? null : text;
}

