const avatarSelectState = {
  wrappers: [],
  listenersBound: false,
};

const rotasAssistantState = {
  bound: false,
  loaded: false,
  refresh: null,
  scheduled: false,
};

const disponiveisAssistantState = {
  bound: false,
  loaded: false,
  refresh: null,
  scheduled: false,
};

const scheduleBackgroundRefresh = (callback) => {
  if (typeof window.requestIdleCallback === "function") {
    window.requestIdleCallback(() => callback(), { timeout: 1200 });
    return;
  }
  window.setTimeout(callback, 500);
};

const initConfirmDialogs = () => {
  if (initConfirmDialogs.bound) {
    return;
  }
  initConfirmDialogs.bound = true;
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    if (!form.matches("form[data-confirm]")) {
      return;
    }
    const msg = form.getAttribute("data-confirm") || "Confirmar?";
    if (!window.confirm(msg)) {
      event.preventDefault();
    }
  });
};

const initAvatarSelects = (root = document) => {
  avatarSelectState.wrappers = avatarSelectState.wrappers.filter((wrapper) =>
    document.body.contains(wrapper)
  );
  const avatarSelects = root.querySelectorAll("select.js-avatar-select");
  if (!avatarSelects.length) {
    return;
  }

  const initialsFrom = (label) => {
    const cleaned = (label || "").replace(/[^A-Za-z\u00c0-\u00ff\s]/g, " ").trim();
    if (!cleaned) {
      return "";
    }
    const parts = cleaned.split(/\s+/);
    const first = parts[0]?.[0] || "";
    const second = parts[1]?.[0] || "";
    return (first + second).toUpperCase();
  };

  const setAvatar = (el, url, label, blank) => {
    if (!el) {
      return;
    }
    if (url) {
      el.style.backgroundImage = `url("${url}")`;
      el.textContent = "";
      el.classList.add("has-image");
    } else if (blank) {
      el.style.backgroundImage = "";
      el.textContent = "";
      el.classList.remove("has-image");
    } else {
      el.style.backgroundImage = "";
      el.textContent = initialsFrom(label);
      el.classList.remove("has-image");
    }
  };

  const closeAll = (ignoreTarget) => {
    avatarSelectState.wrappers = avatarSelectState.wrappers.filter((wrapper) =>
      document.body.contains(wrapper)
    );
    avatarSelectState.wrappers.forEach((wrapper) => {
      if (ignoreTarget && wrapper.contains(ignoreTarget)) {
        return;
      }
      wrapper.classList.remove("is-open");
      const trigger = wrapper.querySelector(".avatar-select__trigger");
      if (trigger) {
        trigger.setAttribute("aria-expanded", "false");
      }
      const searchInput = wrapper.querySelector(".avatar-select__search input");
      if (searchInput && searchInput.value) {
        searchInput.value = "";
        if (wrapper._avatarFilter) {
          wrapper._avatarFilter();
        }
      }
    });
  };

  avatarSelects.forEach((select) => {
    if (select.dataset.avatarReady) {
      return;
    }
    select.dataset.avatarReady = "1";

    const wrapper = document.createElement("div");
    wrapper.className = "avatar-select";
    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(select);
    select.classList.add("avatar-select__native");

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "avatar-select__trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");

    const value = document.createElement("span");
    value.className = "avatar-select__value";

    const triggerAvatar = document.createElement("span");
    triggerAvatar.className = "avatar-select__avatar";
    const triggerLabel = document.createElement("span");
    triggerLabel.className = "avatar-select__label";

    value.appendChild(triggerAvatar);
    value.appendChild(triggerLabel);
    trigger.appendChild(value);

    const caret = document.createElement("span");
    caret.className = "avatar-select__caret";
    caret.textContent = "v";
    trigger.appendChild(caret);
    wrapper.appendChild(trigger);

    const panel = document.createElement("div");
    panel.className = "avatar-select__panel";
    panel.setAttribute("role", "listbox");
    wrapper.appendChild(panel);

    const searchWrap = document.createElement("div");
    searchWrap.className = "avatar-select__search";
    const searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.placeholder = "Pesquisar...";
    searchInput.autocomplete = "off";
    searchInput.setAttribute("aria-label", "Pesquisar");
    searchWrap.appendChild(searchInput);
    panel.appendChild(searchWrap);

    const optionButtons = [];
    Array.from(select.options).forEach((option, index) => {
      if (option.disabled) {
        return;
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = "avatar-select__option";
      button.setAttribute("role", "option");
      button.dataset.index = String(index);
      if (option.dataset.motAj === "1") {
        button.dataset.motAj = "1";
      }

      const optionAvatar = document.createElement("span");
      optionAvatar.className = "avatar-select__avatar";
      const optionLabel = document.createElement("span");
      optionLabel.className = "avatar-select__label";
      optionLabel.textContent = option.textContent;

      setAvatar(optionAvatar, option.dataset.avatar, option.textContent, option.value === "");

      button.appendChild(optionAvatar);
      button.appendChild(optionLabel);
      button.addEventListener("click", () => {
        if (option.disabled) {
          return;
        }
        select.selectedIndex = index;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        closeAll();
      });

      panel.appendChild(button);
      optionButtons.push({ button, option, index });
    });

    const filterOptions = () => {
      const term = (searchInput.value || "").trim().toLowerCase();
      optionButtons.forEach(({ button }) => {
        const label = (button.textContent || "").toLowerCase();
        const matches = !term || label.includes(term);
        const isHidden = button.classList.contains("is-hidden");
        button.classList.toggle("is-filtered", !matches);
        button.hidden = !matches || isHidden;
      });
    };

    wrapper._avatarFilter = filterOptions;

    const syncFromSelect = () => {
      const selected = select.options[select.selectedIndex];
      if (selected) {
        triggerLabel.textContent = selected.textContent;
        setAvatar(triggerAvatar, selected.dataset.avatar, selected.textContent, selected.value === "");
      }
      optionButtons.forEach(({ button, index }) => {
        button.classList.toggle("is-selected", index === select.selectedIndex);
      });
      trigger.disabled = select.disabled;
      wrapper.classList.toggle("is-disabled", select.disabled);
    };

    syncFromSelect();
    select.addEventListener("change", syncFromSelect);
    searchInput.addEventListener("input", filterOptions);

    trigger.addEventListener("click", (event) => {
      event.stopPropagation();
      if (select.disabled) {
        return;
      }
      const isOpen = wrapper.classList.toggle("is-open");
      trigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
      if (isOpen) {
        closeAll(wrapper);
        setTimeout(() => {
          searchInput.focus();
        }, 0);
      }
    });

    avatarSelectState.wrappers.push(wrapper);
  });

  if (!avatarSelectState.listenersBound) {
    avatarSelectState.listenersBound = true;
    document.addEventListener("click", (event) => closeAll(event.target));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeAll();
      }
    });
  }
};

const initRotasAssistant = () => {
  const widget = document.querySelector("[data-rotas-assistente]");
  if (!widget) {
    return;
  }

  const list = widget.querySelector(".assistant-rotas__list");
  const status = widget.querySelector(".assistant-rotas__status");
  const count = widget.querySelector(".assistant-rotas__count");
  const getBaseDate = () => {
    const url = new URL(window.location.href);
    return url.searchParams.get("data") || widget.dataset.baseDate || "";
  };

  const refresh = async () => {
    const data = getBaseDate();
    const url = `/assistente-rotas?data=${encodeURIComponent(data)}`;
    if (status) {
      status.textContent = "Carregando...";
    }
    try {
      const response = await fetch(url, { headers: { "X-Requested-With": "fetch" } });
      if (!response.ok) {
        throw new Error("Erro ao carregar");
      }
      const payload = await response.json();
      const total = Number(payload.total || 0);
      if (count) {
        count.textContent = String(total);
      }
      if (list) {
        list.innerHTML = "";
      }
      if (!payload.rotas || !payload.rotas.length) {
        if (status) {
          status.textContent = `Sem pendências${payload.data_br ? ` (${payload.data_br})` : ""}.`;
        }
        return;
      }
      if (status) {
        status.textContent = `Pendentes para ${payload.data_br || data}`;
      }
      payload.rotas.forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item.label || item.rota || "";
        if (list) {
          list.appendChild(li);
        }
      });
      rotasAssistantState.loaded = true;
    } catch (err) {
      if (status) {
        status.textContent = "Não foi possível carregar.";
      }
    }
  };

  rotasAssistantState.refresh = refresh;
  if (!rotasAssistantState.bound) {
    rotasAssistantState.bound = true;
    const toggle = widget.querySelector(".assistant-rotas__toggle");
    const refreshButton = widget.querySelector(".assistant-rotas__refresh");
    if (toggle) {
      toggle.addEventListener("click", () => {
        const aberto = widget.classList.toggle("is-open");
        if (aberto && !rotasAssistantState.loaded) {
          refresh();
        }
      });
    }
    if (refreshButton) {
      refreshButton.addEventListener("click", refresh);
    }
    window.addEventListener("popstate", refresh);
  }

  if (!rotasAssistantState.scheduled) {
    rotasAssistantState.scheduled = true;
    scheduleBackgroundRefresh(refresh);
  }
};

const initDisponiveisAssistant = () => {
  const widget = document.querySelector("[data-disponiveis-assistente]");
  if (!widget) {
    return;
  }

  const listMotoristas = widget.querySelector("[data-list-motoristas]");
  const listAjudantes = widget.querySelector("[data-list-ajudantes]");
  const status = widget.querySelector(".assistant-disponiveis__status");
  const count = widget.querySelector(".assistant-disponiveis__count");
  const getBaseDate = () => {
    const url = new URL(window.location.href);
    return url.searchParams.get("data") || widget.dataset.baseDate || "";
  };

  const refresh = async () => {
    const data = getBaseDate();
    const url = `/assistente-disponiveis?data=${encodeURIComponent(data)}`;
    if (status) {
      status.textContent = "Carregando...";
    }
    if (listMotoristas) {
      listMotoristas.innerHTML = "";
    }
    if (listAjudantes) {
      listAjudantes.innerHTML = "";
    }
    try {
      const response = await fetch(url, { headers: { "X-Requested-With": "fetch" } });
      if (!response.ok) {
        throw new Error("Erro ao carregar");
      }
      const payload = await response.json();
      const total = Number(payload.total || 0);
      if (count) {
        count.textContent = String(total);
      }
      if (status) {
        status.textContent = `Disponíveis em ${payload.data_br || data}`;
      }
      const motoristas = payload.motoristas || [];
      const ajudantes = payload.ajudantes || [];
      if (!motoristas.length && !ajudantes.length) {
        if (status) {
          status.textContent = `Nenhum disponível${payload.data_br ? ` (${payload.data_br})` : ""}.`;
        }
        return;
      }
      motoristas.forEach((nome) => {
        const li = document.createElement("li");
        li.textContent = nome;
        if (listMotoristas) {
          listMotoristas.appendChild(li);
        }
      });
      ajudantes.forEach((nome) => {
        const li = document.createElement("li");
        li.textContent = nome;
        if (listAjudantes) {
          listAjudantes.appendChild(li);
        }
      });
      disponiveisAssistantState.loaded = true;
    } catch (err) {
      if (status) {
        status.textContent = "Não foi possível carregar.";
      }
    }
  };

  disponiveisAssistantState.refresh = refresh;
  if (!disponiveisAssistantState.bound) {
    disponiveisAssistantState.bound = true;
    const toggle = widget.querySelector(".assistant-disponiveis__toggle");
    const refreshButton = widget.querySelector(".assistant-disponiveis__refresh");
    if (toggle) {
      toggle.addEventListener("click", () => {
        const aberto = widget.classList.toggle("is-open");
        if (aberto && !disponiveisAssistantState.loaded) {
          refresh();
        }
      });
    }
    if (refreshButton) {
      refreshButton.addEventListener("click", refresh);
    }
    window.addEventListener("popstate", refresh);
  }

  if (!disponiveisAssistantState.scheduled) {
    disponiveisAssistantState.scheduled = true;
    scheduleBackgroundRefresh(refresh);
  }
};

const initAjaxCarregamentos = () => {
  const content = document.getElementById("carregamentos-content");
  if (!content) {
    return;
  }

  const fetchAndSwap = async (url, options = {}) => {
    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "fetch" },
        ...options,
      });

      if (!response.ok) {
        window.location.href = response.url || url;
        return;
      }

      const html = await response.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const newContent = doc.querySelector("#carregamentos-content");
      const currentContent = document.querySelector("#carregamentos-content");
      if (!newContent || !currentContent) {
        window.location.href = response.url || url;
        return;
      }
      currentContent.replaceWith(newContent);

      const newFlash = doc.querySelector("#flash-area");
      const currentFlash = document.querySelector("#flash-area");
      if (newFlash && currentFlash) {
        currentFlash.replaceWith(newFlash);
      }

      initAvatarSelects(newContent);
      initMotAjToggle(newContent);

      if (response.url) {
        history.pushState({}, "", response.url);
      }
      if (rotasAssistantState.refresh) {
        rotasAssistantState.refresh();
      }
      if (disponiveisAssistantState.refresh) {
        disponiveisAssistantState.refresh();
      }
    } catch (err) {
      window.location.href = url;
    }
  };

  document.addEventListener("submit", (event) => {
    if (event.defaultPrevented) {
      return;
    }
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    if (!form.matches("form[data-ajax]")) {
      return;
    }
    if (!form.closest("#carregamentos-content")) {
      return;
    }
    event.preventDefault();

    const method = (form.getAttribute("method") || "get").toUpperCase();
    const action = form.getAttribute("action") || window.location.href;

    if (method === "GET") {
      const url = new URL(action, window.location.origin);
      const params = new URLSearchParams(new FormData(form));
      url.search = params.toString();
      fetchAndSwap(url.toString(), { method: "GET" });
      return;
    }

    const body = new FormData(form);
    fetchAndSwap(action, { method, body });
  });

  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-ajax-link]");
    if (!link) {
      return;
    }
    if (!link.closest("#carregamentos-content")) {
      return;
    }
    event.preventDefault();
    fetchAndSwap(link.href, { method: "GET" });
  });
};

const initAjaxColaboradores = () => {
  document.addEventListener("submit", async (event) => {
    if (event.defaultPrevented) {
      return;
    }
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    if (!form.matches('form[data-ajax-colaborador="excluir"]')) {
      return;
    }

    event.preventDefault();
    const action = form.getAttribute("action");
    if (!action) {
      return;
    }

    const button = form.querySelector('button[type="submit"]');
    if (button) {
      button.disabled = true;
    }

    const showFlash = (message, category = "success") => {
      const flashArea = document.getElementById("flash-area");
      if (!flashArea) {
        return;
      }
      flashArea.innerHTML = "";
      const flash = document.createElement("div");
      flash.className = `flash ${category}`;
      flash.textContent = message;
      flashArea.appendChild(flash);
    };

    try {
      const response = await fetch(action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: { "X-Requested-With": "fetch" },
      });

      const payload = await response.json().catch(() => null);
      if (!response.ok || !payload || !payload.ok) {
        const message = (payload && payload.message) || "Não foi possível excluir o colaborador.";
        showFlash(message, "error");
        if (button) {
          button.disabled = false;
        }
        return;
      }

      const row = form.closest("tr");
      if (row) {
        const tbody = row.parentElement;
        row.remove();
        if (tbody && !tbody.querySelector("tr")) {
          const empty = document.createElement("tr");
          const cell = document.createElement("td");
          cell.colSpan = 5;
          cell.textContent = "Nenhum colaborador cadastrado.";
          empty.appendChild(cell);
          tbody.appendChild(empty);
        }
      }

      const badge = document.querySelector("[data-colaboradores-total]");
      if (badge) {
        let total = Number(payload.total);
        if (!Number.isFinite(total)) {
          const atual = Number(badge.dataset.colaboradoresTotal || "0");
          total = Math.max(0, atual - 1);
        }
        badge.dataset.colaboradoresTotal = String(total);
        badge.textContent = `${total} colaborador${total === 1 ? "" : "es"}`;
      }

      showFlash(payload.message || "Colaborador excluído.", "success");
      if (rotasAssistantState.refresh) {
        rotasAssistantState.refresh();
      }
      if (disponiveisAssistantState.refresh) {
        disponiveisAssistantState.refresh();
      }
    } catch (err) {
      showFlash("Erro de conexão ao excluir colaborador.", "error");
      if (button) {
        button.disabled = false;
      }
    }
  });
};

const initAjaxDeletes = () => {
  document.addEventListener("submit", async (event) => {
    if (event.defaultPrevented) {
      return;
    }
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    if (!form.matches("form[data-ajax-delete]")) {
      return;
    }

    event.preventDefault();
    const action = form.getAttribute("action");
    if (!action) {
      return;
    }

    const button = form.querySelector('button[type="submit"]');
    if (button) {
      button.disabled = true;
    }

    const showFlash = (message, category = "success") => {
      const flashArea = document.getElementById("flash-area");
      if (!flashArea) {
        return;
      }
      flashArea.innerHTML = "";
      const flash = document.createElement("div");
      flash.className = `flash ${category}`;
      flash.textContent = message;
      flashArea.appendChild(flash);
    };

    try {
      const response = await fetch(action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: { "X-Requested-With": "fetch" },
      });

      const payload = await response.json().catch(() => null);
      if (!response.ok || !payload || !payload.ok) {
        const message = (payload && payload.message) || "Nao foi possivel excluir.";
        showFlash(message, "error");
        if (button) {
          button.disabled = false;
        }
        return;
      }

      const removeClosest = form.dataset.removeClosest || "tr";
      const target = form.closest(removeClosest) || form;
      const parent = target.parentElement;
      target.remove();

      if (removeClosest === "tr" && parent && !parent.querySelector("tr")) {
        const emptyRow = document.createElement("tr");
        const emptyCell = document.createElement("td");
        const emptyColspan = Number(form.dataset.emptyColspan || "1");
        emptyCell.colSpan = Number.isFinite(emptyColspan) && emptyColspan > 0 ? emptyColspan : 1;
        emptyCell.textContent = form.dataset.emptyText || "Nenhum registro cadastrado.";
        emptyRow.appendChild(emptyCell);
        parent.appendChild(emptyRow);
      }

      if (form.dataset.emptyTarget) {
        const emptyTarget = document.querySelector(form.dataset.emptyTarget);
        const emptyCheck = form.dataset.emptyCheck || "[data-ajax-item]";
        if (emptyTarget && !emptyTarget.querySelector(emptyCheck)) {
          const emptyText = form.dataset.emptyText || "Nenhum registro encontrado.";
          emptyTarget.innerHTML = `<div class=\"card\">${emptyText}</div>`;
        }
      }

      showFlash(payload.message || "Excluido com sucesso.", "success");
      if (rotasAssistantState.refresh) {
        rotasAssistantState.refresh();
      }
      if (disponiveisAssistantState.refresh) {
        disponiveisAssistantState.refresh();
      }
    } catch (err) {
      showFlash("Erro de conexao ao excluir.", "error");
      if (button) {
        button.disabled = false;
      }
    }
  });
};

const initRedirectOnChange = () => {
  document.querySelectorAll("[data-redirect-param]").forEach((input) => {
    if (input.dataset.redirectReady) {
      return;
    }
    input.dataset.redirectReady = "1";
    input.addEventListener("change", () => {
      const param = input.dataset.redirectParam || input.name;
      const url = new URL(window.location.href);
      if (input.value) {
        url.searchParams.set(param, input.value);
      } else {
        url.searchParams.delete(param);
      }
      const extras = (input.dataset.redirectExtra || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      extras.forEach((name) => {
        const field = document.querySelector(`[name="${name}"]`);
        if (field && field.value) {
          url.searchParams.set(name, field.value);
        } else {
          url.searchParams.delete(name);
        }
      });
      if (input.dataset.redirectEditId) {
        url.searchParams.set("edit_id", input.dataset.redirectEditId);
      }
      window.location.href = url.toString();
    });
  });
};

const applyMotAjState = (root = document) => {
  const toggle = root.querySelector('input[data-mot-aj-toggle]');
  if (!toggle) {
    return;
  }
  const checked = toggle.checked;
  const selects = root.querySelectorAll("select[data-mot-aj-select]");
  selects.forEach((select) => {
    const options = Array.from(select.options);
    options.forEach((option) => {
      const label = (option.textContent || "").toLowerCase();
      const isMotAj = option.dataset.motAj === "1" || label.includes("(.mot)");
      const shouldHide = !checked && isMotAj;
      option.hidden = shouldHide;
    });

    const wrapper = select.closest(".avatar-select");
    if (wrapper) {
      wrapper.querySelectorAll(".avatar-select__option").forEach((button) => {
        const index = Number(button.dataset.index || "-1");
        const option = options[index];
        if (!option) {
          return;
        }
        const label = (option.textContent || "").toLowerCase();
        const isMotAj = option.dataset.motAj === "1" || label.includes("(.mot)");
        const shouldHide = !checked && isMotAj;
        button.hidden = shouldHide;
        button.classList.toggle("is-hidden", shouldHide);
      });
      if (wrapper._avatarFilter) {
        wrapper._avatarFilter();
      }
    }

    if (!checked) {
      const selected = select.options[select.selectedIndex];
      if (selected && selected.dataset.motAj === "1") {
        select.selectedIndex = 0;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
  });

  document.querySelectorAll('input[name="permitir_mot_aj"][type="hidden"]').forEach((input) => {
    input.value = checked ? "1" : "0";
  });

  const url = new URL(window.location.href);
  if (checked) {
    url.searchParams.set("permitir_mot_aj", "1");
  } else {
    url.searchParams.delete("permitir_mot_aj");
  }
  history.replaceState({}, "", url.toString());
};

const initMotAjToggle = (root = document) => {
  const toggle = root.querySelector('input[data-mot-aj-toggle]');
  if (!toggle || toggle.dataset.motAjReady) {
    applyMotAjState(root);
    return;
  }
  toggle.dataset.motAjReady = "1";
  toggle.addEventListener("change", () => applyMotAjState(root));
  applyMotAjState(root);
};

document.addEventListener("DOMContentLoaded", () => {
  initConfirmDialogs();
  initAvatarSelects();
  initAjaxCarregamentos();
  initAjaxColaboradores();
  initAjaxDeletes();
  initRedirectOnChange();
  initMotAjToggle();
  initRotasAssistant();
  initDisponiveisAssistant();
});
