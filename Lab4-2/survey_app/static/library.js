"use strict";

/* Question library: create stored questions, walk their versions, share, bank, inspect usage
   and aggregate one question across surveys. All checks are repeated by the server. */
(() => {
  const $ = (id) => document.getElementById(id);
  const state = { user: null, scope: "mine", questions: [], selected: null, banks: [], surveys: [] };
  const TYPE_LABEL = { single: "单选题", multi: "多选题", text: "文本题", number: "数字题" };

  async function api(method, path, body) {
    const options = { method, credentials: "same-origin" };
    if (body !== undefined) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(body);
    }
    const response = await fetch(path, options);
    const text = await response.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch (error) { data = null; }
    }
    if (!response.ok) {
      const message = data && data.error && data.error.message ? data.error.message : `请求失败（${response.status}）`;
      const failure = new Error(message);
      failure.status = response.status;
      throw failure;
    }
    return data;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function button(text, className, action) {
    const node = el("button", `button ${className || ""}`, text);
    node.type = "button";
    node.addEventListener("click", action);
    return node;
  }

  function report(node, error, fallback) {
    if (!node) return;
    node.textContent = error ? `操作失败：${error.message}` : (fallback || "");
    node.hidden = !node.textContent;
  }

  /* ------------------------------------------------------------------ question form */
  function optionRow(value) {
    const row = el("div", "option-row");
    const input = el("input");
    input.value = value;
    input.placeholder = "选项文字";
    const remove = button("删除", "quiet", () => { row.remove(); renumberOptions(); });
    row.append(input, remove);
    return row;
  }

  function renumberOptions() {
    [...$("option-list").children].forEach((row, index) => {
      row.dataset.optionId = String.fromCharCode(97 + index);
    });
  }

  function syncTypeFields() {
    const type = $("question-type").value;
    $("options-field").hidden = !["single", "multi"].includes(type);
    $("number-fields").hidden = type !== "number";
    $("text-fields").hidden = type !== "text";
  }

  function resetForm() {
    $("question-title").value = "";
    $("question-note").value = "";
    $("question-required").checked = false;
    $("question-type").value = "single";
    $("option-list").replaceChildren(optionRow(""), optionRow(""));
    renumberOptions();
    syncTypeFields();
  }

  function formPayload() {
    const type = $("question-type").value;
    const payload = { type, title: $("question-title").value.trim(),
                      required: $("question-required").checked, note: $("question-note").value.trim() };
    if (["single", "multi"].includes(type)) {
      payload.options = [...$("option-list").children].map((row) => ({
        id: row.dataset.optionId,
        label: row.querySelector("input").value.trim(),
      })).filter((option) => option.label);
      payload.validation = {};
    } else if (type === "number") {
      const validation = {};
      if ($("number-min").value !== "") validation.min_value = Number($("number-min").value);
      if ($("number-max").value !== "") validation.max_value = Number($("number-max").value);
      if ($("number-integer").checked) validation.integer_only = true;
      payload.options = [];
      payload.validation = validation;
    } else {
      payload.options = [];
      payload.validation = { min_length: Number($("text-min").value || 0), max_length: Number($("text-max").value || 200) };
    }
    return payload;
  }

  /* ------------------------------------------------------------------ list + detail */
  function questionCard(question) {
    const card = el("button", `question-card${state.selected && state.selected.id === question.id ? " selected" : ""}`);
    card.type = "button";
    card.append(el("div", "title", question.title));
    const meta = el("div", "meta");
    meta.append(el("span", "badge", TYPE_LABEL[question.type] || question.type));
    meta.append(el("span", null, `当前 v${question.current_version}`));
    if (question.owned === false) meta.append(el("span", "badge", question.owner_name ? `来自 ${question.owner_name}` : "共享"));
    if (question.bank_count) meta.append(el("span", null, `在 ${question.bank_count} 个题库`));
    if (question.share_count && question.owned !== false) meta.append(el("span", null, `共享给 ${question.share_count} 人`));
    card.append(meta);
    card.addEventListener("click", () => selectQuestion(question.id));
    return card;
  }

  function renderQuestions() {
    const list = $("question-list");
    list.replaceChildren();
    if (!state.questions.length) {
      list.append(el("p", "muted", state.scope === "mine" ? "还没有保存的题目。" : "暂时没有共享给你的题目。"));
      return;
    }
    state.questions.forEach((question) => list.append(questionCard(question)));
  }

  async function selectQuestion(questionId) {
    state.selected = null;
    try {
      state.selected = await api("GET", `/api/questions/${questionId}`);
    } catch (error) {
      return;
    }
    renderQuestions();
    renderDetail();
    $("stats-panel").hidden = true;
  }

  function contentSummary(version) {
    const wrapper = el("div");
    if (version.options && version.options.length) {
      const list = el("ul");
      version.options.forEach((option) => list.append(el("li", null, `${option.id}. ${option.label}`)));
      wrapper.append(list);
    }
    const validation = Object.entries(version.validation || {});
    if (validation.length) wrapper.append(el("p", "muted", validation.map(([key, value]) => `${key}=${value}`).join("，")));
    wrapper.append(el("p", "muted", version.required ? "默认必答" : "默认选答"));
    return wrapper;
  }

  function renderDetail() {
    const detail = $("detail");
    const question = state.selected;
    detail.replaceChildren();
    if (!question) { detail.hidden = true; return; }
    detail.hidden = false;

    const heading = el("div", "section-heading");
    heading.append(el("h2", null, question.title));
    const tags = el("div", "meta");
    tags.append(el("span", "badge", TYPE_LABEL[question.type] || question.type),
                el("span", "badge", `v${question.current_version}`),
                el("span", "badge", question.owned ? "我是所有者" : "共享给我的"));
    heading.append(tags);
    detail.append(heading, contentSummary(question.current || {}));

    /* versions */
    const versions = el("section");
    versions.append(el("h3", null, "版本历史"));
    (question.versions || []).slice().reverse().forEach((version) => {
      const row = el("div", "version-row");
      const label = el("div");
      label.append(el("strong", null, `v${version.version}`));
      if (version.note) label.append(el("span", "muted", ` · ${version.note}`));
      if (version.derived_from) label.append(el("div", "muted", `改自 ${version.derived_from.question_id === question.id ? "本题" : "其他题"} v${version.derived_from.version}`));
      if (version.restored_from) label.append(el("div", "muted", `恢复自 v${version.restored_from}`));
      row.append(label);
      if (question.owned && version.version !== question.current_version) {
        row.append(button("恢复此版本", "quiet", () => restoreVersion(version.version)));
      }
      versions.append(row);
    });
    detail.append(versions);

    /* usage */
    const usage = el("section");
    usage.append(el("h3", null, "被哪些问卷使用"));
    const usageBox = el("div");
    usageBox.dataset.usage = "pending";
    usage.append(usageBox);
    detail.append(usage);
    api("GET", `/api/questions/${question.id}/usage`).then((data) => {
      usageBox.dataset.usage = "loaded";
      usageBox.replaceChildren();
      if (!data.usages.length) { usageBox.append(el("p", "muted", "还没有问卷使用这道题。")); return; }
      const table = el("table", "grid");
      const head = el("tr");
      ["问卷", "状态", "问卷版本", "题目版本", "可否修改"].forEach((label) => head.append(el("th", null, label)));
      table.append(head);
      data.usages.forEach((row) => {
        const tr = el("tr");
        tr.append(el("td", null, row.title + (row.owner_is_self ? "" : "（他人问卷）")),
                  el("td", null, row.status === "published" ? "已发布（已冻结）" : "草稿"),
                  el("td", null, row.version ? `v${row.version}` : "—"),
                  el("td", null, row.question_version ? `v${row.question_version}` : "本地修改"),
                  el("td", null, row.editable ? "可改" : "不可改"));
        table.append(tr);
      });
      usageBox.append(table);
    }).catch((error) => { usageBox.textContent = `使用情况读取失败：${error.message}`; });

    /* add to survey */
    if (state.surveys.length) {
      const addSection = el("section");
      addSection.append(el("h3", null, "加入我的草稿问卷"));
      const row = el("div", "field-row");
      const surveySelect = el("select");
      state.surveys.filter((survey) => survey.status === "draft").forEach((survey) => {
        const option = el("option", null, survey.title);
        option.value = survey.id;
        surveySelect.append(option);
      });
      const versionSelect = el("select");
      (question.versions || []).forEach((version) => {
        const option = el("option", null, `v${version.version}`);
        option.value = version.version;
        if (version.version === question.current_version) option.selected = true;
        versionSelect.append(option);
      });
      const addButton = button("加入问卷", "secondary", async () => {
        try {
          await api("POST", `/api/surveys/${surveySelect.value}/questions/import`,
                    { question_id: question.id, version: Number(versionSelect.value) });
          await selectQuestion(question.id);
        } catch (error) { alert(`加入失败：${error.message}`); }
      });
      row.append(surveySelect, versionSelect, addButton);
      addSection.append(row);
      detail.append(addSection);
    }

    /* sharing */
    if (question.owned) {
      const shareSection = el("section");
      shareSection.append(el("h3", null, "共享"));
      const row = el("div", "field-row");
      const input = el("input");
      input.placeholder = "对方用户名";
      const shareButton = button("共享", "secondary", async () => {
        try {
          await api("POST", `/api/questions/${question.id}/shares`, { username: input.value.trim() });
          await selectQuestion(question.id);
        } catch (error) { alert(`共享失败：${error.message}`); }
      });
      row.append(input, shareButton);
      shareSection.append(row);
      if (question.shares && question.shares.length) {
        const list = el("div", "stack");
        question.shares.forEach((share) => {
          const line = el("div", "version-row");
          line.append(el("span", null, share.username || share.user_id));
          line.append(button("取消共享", "quiet", async () => {
            try {
              await api("DELETE", `/api/questions/${question.id}/shares/${share.user_id}`);
              await selectQuestion(question.id);
            } catch (error) { alert(`取消失败：${error.message}`); }
          }));
          list.append(line);
        });
        shareSection.append(list);
      }
      detail.append(shareSection);

      /* banks */
      if (state.banks.length) {
        const bankSection = el("section");
        bankSection.append(el("h3", null, "加入题库"));
        const row = el("div", "field-row");
        const select = el("select");
        state.banks.forEach((bank) => {
          const option = el("option", null, bank.name);
          option.value = bank.id;
          select.append(option);
        });
        row.append(select, button("加入", "secondary", async () => {
          try {
            await api("POST", `/api/banks/${select.value}/items`,
                      { question_id: question.id, version: question.current_version });
            await loadBanks();
            await selectQuestion(question.id);
          } catch (error) { alert(`加入题库失败：${error.message}`); }
        }));
        bankSection.append(row);
        detail.append(bankSection);
      }

      /* new version + fork */
      const editSection = el("section");
      editSection.append(el("h3", null, "修改题目"));
      editSection.append(el("p", "muted", "修改会生成新版本；已发布问卷里的旧版本不受影响。"));
      const title = el("input");
      title.value = question.title;
      const note = el("input");
      note.placeholder = "修改说明（写进版本历史）";
      editSection.append(title, note);
      const actions = el("div", "field-row");
      actions.append(button("保存为新版本", "secondary", async () => {
        try {
          const payload = { ...payloadFromQuestion(question), title: title.value.trim(), note: note.value.trim() };
          await api("POST", `/api/questions/${question.id}/versions`, payload);
          await loadQuestions();
          await selectQuestion(question.id);
        } catch (error) { alert(`新建版本失败：${error.message}`); }
      }));
      actions.append(button("另存为新题", "quiet", async () => {
        try {
          const payload = { ...payloadFromQuestion(question), title: title.value.trim(), note: note.value.trim() || "从已有题目另存" };
          const created = await api("POST", `/api/questions/${question.id}/fork`, payload);
          await loadQuestions();
          await selectQuestion(created.id);
        } catch (error) { alert(`另存失败：${error.message}`); }
      }));
      editSection.append(actions);
      detail.append(editSection);
    }

    /* statistics */
    const statsSection = el("section");
    statsSection.append(button("查看跨问卷统计", "secondary", () => showStatistics(question.id)));
    detail.append(statsSection);

    async function restoreVersion(version) {
      try {
        await api("POST", `/api/questions/${question.id}/versions/${version}/restore`);
        await loadQuestions();
        await selectQuestion(question.id);
      } catch (error) { alert(`恢复失败：${error.message}`); }
    }
  }

  function payloadFromQuestion(question) {
    const current = question.current || {};
    return { type: current.type, title: current.title, required: Boolean(current.required),
             options: current.options || [], validation: current.validation || {}, note: "" };
  }

  /* ------------------------------------------------------------------ statistics */
  async function showStatistics(questionId) {
    const panel = $("stats-panel");
    panel.hidden = false;
    panel.replaceChildren(el("p", "muted", "正在汇总…"));
    let data;
    try {
      data = await api("GET", `/api/questions/${questionId}/statistics`);
    } catch (error) {
      panel.replaceChildren(el("p", "error", `统计读取失败：${error.message}`));
      return;
    }
    panel.replaceChildren();
    panel.append(el("h2", null, `跨问卷统计：${data.title}`));
    panel.append(el("p", "muted",
      `范围：${data.scope === "all surveys" ? "使用该题的全部问卷" : "仅我自己的问卷"}；问卷 ${data.survey_count} 份；有效回答 ${data.total_answered} 条。`));

    Object.entries(data.aggregate.by_type || {}).forEach(([type, summary]) => {
      const section = el("section");
      section.append(el("h3", null, `${TYPE_LABEL[type] || type}（${summary.answered} 条）`));
      if (summary.options) {
        const table = el("table", "grid");
        const head = el("tr");
        ["选项", "次数"].forEach((label) => head.append(el("th", null, label)));
        table.append(head);
        summary.options.forEach((option) => {
          const tr = el("tr");
          tr.append(el("td", null, `${option.id}. ${option.label}`), el("td", null, option.count));
          table.append(tr);
        });
        section.append(table);
      } else if (summary.mean !== undefined) {
        section.append(el("p", null, `均值 ${summary.mean === null ? "—" : summary.mean}，有效数值 ${summary.count} 个`));
      } else {
        section.append(el("p", null, `去重前取值：${(summary.values || []).join("、") || "—"}`));
      }
      panel.append(section);
    });

    const perVersion = el("section");
    perVersion.append(el("h3", null, "按题目版本"));
    const table = el("table", "grid");
    const head = el("tr");
    ["题目版本", "有效回答"].forEach((label) => head.append(el("th", null, label)));
    table.append(head);
    Object.entries(data.by_question_version || {}).forEach(([version, summary]) => {
      const tr = el("tr");
      tr.append(el("td", null, version === "null" ? "本地修改" : `v${version}`), el("td", null, summary.answered));
      table.append(tr);
    });
    perVersion.append(table);
    panel.append(perVersion);

    const perSurvey = el("section");
    perSurvey.append(el("h3", null, "按问卷"));
    const surveyTable = el("table", "grid");
    const surveyHead = el("tr");
    ["问卷", "版本", "题目版本", "有效回答"].forEach((label) => surveyHead.append(el("th", null, label)));
    surveyTable.append(surveyHead);
    (data.surveys || []).forEach((row) => {
      const tr = el("tr");
      tr.append(el("td", null, row.title + (row.owner_is_self ? "" : "（他人）")),
                el("td", null, `v${row.survey_version}`),
                el("td", null, row.question_version ? `v${row.question_version}` : "本地修改"),
                el("td", null, row.answered));
      surveyTable.append(tr);
    });
    perSurvey.append(surveyTable);
    panel.append(perSurvey);
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* ------------------------------------------------------------------ banks */
  async function loadBanks() {
    state.banks = await api("GET", "/api/banks");
    const list = $("bank-list");
    list.replaceChildren();
    $("bank-count").textContent = state.banks.length ? `${state.banks.length} 个` : "";
    if (!state.banks.length) { list.append(el("p", "muted", "还没有题库。先新建一个，再把题目加入。")); return; }
    for (const bank of state.banks) {
      const card = el("div", "bank-card");
      const header = el("header");
      header.append(el("strong", null, bank.name), el("span", "muted", `${bank.items} 题`));
      card.append(header);
      const detail = await api("GET", `/api/banks/${bank.id}`);
      detail.items.forEach((item) => {
        const line = el("div", "bank-item");
        const label = el("span", null, item.title);
        if (item.outdated) {
          const badge = el("span", "badge warn", `v${item.question_version} → 最新 v${item.current_version}`);
          line.append(label, badge);
          line.append(button("更新版本", "quiet", async () => {
            try {
              await api("PATCH", `/api/banks/${bank.id}/items/${item.question_id}`, {});
              await loadBanks();
            } catch (error) { alert(`更新失败：${error.message}`); }
          }));
        } else {
          line.append(label, el("span", "badge", `v${item.question_version}`));
        }
        line.append(button("移出", "quiet", async () => {
          try {
            await api("DELETE", `/api/banks/${bank.id}/items/${item.question_id}`);
            await loadBanks();
          } catch (error) { alert(`移出失败：${error.message}`); }
        }));
        card.append(line);
      });
      list.append(card);
    }
  }

  /* ------------------------------------------------------------------ data loading */
  async function loadQuestions() {
    const query = state.scope === "mine" ? "/api/questions" : "/api/questions/shared";
    const search = $("question-search").value.trim();
    state.questions = await api("GET", search && state.scope === "mine"
      ? `/api/questions?q=${encodeURIComponent(search)}` : query);
    renderQuestions();
  }

  async function boot() {
    try {
      state.user = await api("GET", "/api/auth/me");
    } catch (error) {
      $("auth-panel").hidden = false;
      return;
    }
    $("library-body").hidden = false;
    $("library-body").classList.add("library-body");
    $("current-user").textContent = state.user.username;
    $("account").hidden = false;
    resetForm();
    await loadQuestions();
    await loadBanks();
    try { state.surveys = await api("GET", "/api/surveys"); } catch (error) { state.surveys = []; }
  }

  /* ------------------------------------------------------------------ events */
  $("question-type").addEventListener("change", syncTypeFields);
  $("add-option").addEventListener("click", () => {
    if ($("option-list").children.length >= 50) return;
    $("option-list").append(optionRow(""));
    renumberOptions();
  });
  $("question-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = $("form-error");
    report(errorBox, null, "");
    try {
      await api("POST", "/api/questions", formPayload());
      resetForm();
      await loadQuestions();
    } catch (error) { report(errorBox, error); }
  });
  $("question-search").addEventListener("input", () => loadQuestions().catch(() => {}));
  $("refresh-questions").addEventListener("click", () => loadQuestions().catch(() => {}));
  document.querySelectorAll(".tab[data-scope]").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab[data-scope]").forEach((other) => {
        other.classList.toggle("active", other === tab);
        other.setAttribute("aria-pressed", String(other === tab));
      });
      state.scope = tab.dataset.scope;
      $("detail").hidden = true;
      loadQuestions().catch(() => {});
    });
  });
  $("bank-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("POST", "/api/banks", { name: $("bank-name").value.trim(), description: "" });
      $("bank-name").value = "";
      await loadBanks();
    } catch (error) { alert(`新建题库失败：${error.message}`); }
  });
  $("logout").addEventListener("click", async () => {
    try { await api("POST", "/api/auth/logout"); } catch (error) { /* ignore */ }
    window.location.href = "/";
  });

  boot();
})();
