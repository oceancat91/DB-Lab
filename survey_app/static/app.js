"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const TYPES = { single: "单选题", multi: "多选题", text: "文本题", number: "数字题" };
  const STATUS = { draft: "草稿", published: "已发布", closed: "已关闭" };
  const state = { user: null, surveys: [], current: null, dirty: false, busy: false, authMode: "login" };
  const path = window.location.pathname.match(/^\/survey\/([^/]+)\/?$/);
  const shareCode = path ? decodeURIComponent(path[1]) : null;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  function button(text, className, action, testId) {
    const node = el("button", `button ${className || ""}`, text);
    node.type = "button";
    if (testId) node.dataset.testid = testId;
    node.addEventListener("click", action);
    return node;
  }

  function field(label, input, hint) {
    const node = el("label", "field", label);
    node.append(input);
    if (hint) node.append(el("small", "", hint));
    return node;
  }

  function input(value, onInput, options = {}) {
    const node = el("input");
    node.type = options.type || "text";
    node.value = value ?? "";
    node.disabled = !isDraft();
    for (const [key, value] of Object.entries(options)) {
      if (key === "testId") node.dataset.testid = value;
      else if (key !== "type") node[key] = value;
    }
    node.addEventListener("input", () => onInput(node.value, node));
    return node;
  }

  function select(value, choices, onChange, testId) {
    const node = el("select");
    node.disabled = !isDraft();
    if (testId) node.dataset.testid = testId;
    const values = choices.map(([id]) => String(id));
    if (value !== undefined && value !== null && !values.includes(String(value))) {
      const missing = el("option", "", `已失效：${value}`);
      missing.value = String(value);
      node.append(missing);
    }
    for (const [id, label] of choices) {
      const option = el("option", "", label);
      option.value = id;
      node.append(option);
    }
    node.value = value ?? "";
    node.addEventListener("change", () => onChange(node.value));
    return node;
  }

  function feedback(message, error = false) {
    $("feedback").textContent = message;
    $("feedback").classList.toggle("error", error);
    $("feedback").hidden = !message;
    $("feedback").setAttribute("role", error ? "alert" : "status");
  }

  async function api(url, options = {}) {
    const request = { credentials: "same-origin", ...options, headers: { Accept: "application/json", ...options.headers } };
    if (options.body !== undefined) {
      request.headers["Content-Type"] = "application/json";
      request.body = JSON.stringify(options.body);
    }
    let response;
    try { response = await fetch(url, request); }
    catch { throw new Error("连接失败，请检查网络后重试。未确认成功前请保留当前内容。"); }
    let data = null;
    if (response.status !== 204) {
      try { data = await response.json(); } catch { /* A non-JSON server error must remain understandable. */ }
    }
    if (!response.ok) {
      const message = data?.error?.message || (typeof data?.detail === "string" ? data.detail : null);
      const error = new Error(message || ({ 401: "登录已过期，请重新登录。", 404: "问卷不存在或你没有管理权限。", 409: "内容或状态已变化，请刷新后重试。", 410: "问卷已关闭或已截止。", 422: "请检查填写的内容和配置。", 503: "服务暂不可用，请稍后重试。" }[response.status] || "操作未完成，请稍后重试。"));
      error.status = response.status;
      error.questionId = data?.error?.question_id;
      throw error;
    }
    return data;
  }

  async function action(control, work) {
    if (state.busy) return;
    state.busy = true;
    if (control) control.disabled = true;
    document.body.setAttribute("aria-busy", "true");
    // Prevent edits during an in-flight save from being replaced by its response.
    $("main").inert = true;
    $("create-dialog").inert = true;
    feedback("");
    try { await work(); }
    catch (error) {
      feedback(error.message + (error.questionId ? `（题目：${error.questionId}）` : ""), true);
      if (error.status === 401) showAuth();
    } finally {
      state.busy = false;
      if (control?.isConnected) control.disabled = false;
      document.body.removeAttribute("aria-busy");
      $("main").inert = false;
      $("create-dialog").inert = false;
      updateActionStates();
    }
  }

  function isDraft() { return state.current?.status === "draft"; }
  function dirty() {
    state.dirty = true;
    $("dirty-indicator").hidden = false;
  }

  function stableId(prefix) {
    const bytes = new Uint8Array(8);
    crypto.getRandomValues(bytes);
    return prefix + Array.from(bytes, (v) => v.toString(16).padStart(2, "0")).join("");
  }

  function dateInput(value) {
    if (!value) return "";
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "";
    return new Date(date.getTime() + 8 * 60 * 60 * 1000).toISOString().slice(0, 16);
  }

  function deadlineValue() {
    const value = $("survey-deadline").value;
    if (!value) return null;
    if (state.current?.closes_at && value === dateInput(state.current.closes_at)) return state.current.closes_at;
    const date = new Date(value + ":00+08:00");
    if (!Number.isFinite(date.getTime())) throw new Error("截止时间格式不正确，请重新选择。");
    return date.toISOString();
  }

  function displayDate(value) {
    if (!value) return "未设置截止";
    const date = new Date(value);
    return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date) + " 截止" : "截止时间不可用";
  }

  function switchAuth(mode) {
    state.authMode = mode;
    const registering = mode === "register";
    $("login-tab").classList.toggle("active", !registering);
    $("register-tab").classList.toggle("active", registering);
    $("login-tab").setAttribute("aria-pressed", String(!registering));
    $("register-tab").setAttribute("aria-pressed", String(registering));
    $("auth-heading").textContent = registering ? "注册账号" : "登录工作台";
    $("auth-description").textContent = registering ? "注册成功后会为你登录。" : (shareCode ? "请先登录，再查看这份分享问卷。" : "使用你的账号继续。");
    $("auth-submit").textContent = registering ? "注册并登录" : "登录";
    $("password").autocomplete = registering ? "new-password" : "current-password";
  }

  function showAuth() {
    state.user = null;
    $("auth-view").hidden = false;
    $("workspace").hidden = true;
    $("fill-view").hidden = true;
    $("account").hidden = true;
    switchAuth(state.authMode);
  }

  async function showSignedIn() {
    $("auth-view").hidden = true;
    $("account").hidden = false;
    $("current-user").textContent = state.user.username;
    $("workspace").hidden = Boolean(shareCode);
    $("fill-view").hidden = !shareCode;
    if (shareCode) await loadFill();
    else {
      await reloadList();
      if (state.current) await openSurvey(state.current.id, true);
    }
  }

  async function reloadList() {
    const surveys = await api("/api/surveys");
    state.surveys = Array.isArray(surveys) ? surveys : [];
    renderList();
  }

  function renderList() {
    const list = $("survey-list");
    list.replaceChildren();
    if (!state.surveys.length) list.append(el("p", "list-empty", "还没有问卷。点击“新建问卷”创建第一份草稿。"));
    for (const survey of state.surveys) {
      const row = button("", `survey-item${survey.id === state.current?.id ? " selected" : ""}`, () => action(row, () => openSurvey(survey.id)), `survey-item-${survey.id}`);
      row.setAttribute("aria-pressed", String(survey.id === state.current?.id));
      row.append(el("span", "survey-item-title", survey.title));
      const meta = el("span", "survey-item-meta");
      meta.append(el("span", `status ${survey.status}`, STATUS[survey.status] || survey.status), el("span", "", survey.status === "draft" ? "继续编辑" : displayDate(survey.closes_at)));
      row.append(meta);
      list.append(row);
    }
  }

  async function openSurvey(id, force = false) {
    if (!force && state.dirty && !window.confirm("当前草稿有未保存修改。放弃这些修改并切换问卷？")) return;
    state.current = await api(`/api/surveys/${encodeURIComponent(id)}`);
    state.current.questions ||= [];
    state.current.rules ||= [];
    state.dirty = false;
    renderEditor();
    renderList();
  }

  function renderEditor() {
    const survey = state.current;
    $("empty-editor").hidden = true;
    $("editor").hidden = false;
    $("editor-title").textContent = survey.title;
    $("editor-status").replaceChildren(el("span", `status ${survey.status}`, STATUS[survey.status] || survey.status), el("span", "", isDraft() ? `草稿修订 ${survey.revision}` : `发布版本 ${survey.version ?? 1}`));
    $("editor-summary").textContent = isDraft() ? "配置题目与跳转，保存后再发布。" : "已发布内容只读；你可以调整截止时间或关闭问卷。";
    $("survey-title").value = survey.title;
    $("survey-description").value = survey.description || "";
    $("allow-anonymous").checked = Boolean(survey.allow_anonymous);
    $("allow-repeat").checked = Boolean(survey.allow_repeat);
    for (const id of ["survey-title", "survey-description", "allow-anonymous", "allow-repeat"]) $(id).disabled = !isDraft();
    $("survey-deadline").value = dateInput(survey.closes_at);
    $("dirty-indicator").hidden = !state.dirty;
    $("draft-actions").hidden = !isDraft();
    $("add-questions").hidden = !isDraft();
    $("add-rule").hidden = !isDraft();
    $("close-survey").hidden = survey.status !== "published";
    $("closed-note").hidden = survey.status !== "closed";
    $("share-section").hidden = survey.status === "draft";
    const url = safeShareUrl(survey);
    $("share-url").value = url;
    $("open-share").href = url || "/";
    renderQuestions();
    renderRules();
    updateActionStates();
  }

  function safeShareUrl(survey) {
    if (survey.share_code) return new URL(`/survey/${encodeURIComponent(survey.share_code)}`, window.location.origin).href;
    if (survey.share_url) {
      try {
        const url = new URL(survey.share_url, window.location.origin);
        if (url.origin === window.location.origin && /^\/survey\/[^/]+\/?$/.test(url.pathname)) return url.href;
      } catch { /* Reject unsafe or unexpected links, even if received from a server. */ }
    }
    return "";
  }

  function updateActionStates() {
    const survey = state.current;
    if (!survey) return;
    $("save-survey").disabled = state.busy || !isDraft();
    $("publish-survey").disabled = state.busy || !isDraft();
    $("add-rule").disabled = state.busy || !hasRuleSource();
    $("save-deadline").disabled = state.busy || survey.status === "closed";
    $("survey-deadline").disabled = survey.status === "closed";
    $("close-survey").disabled = state.busy || survey.status !== "published";
    $("copy-share").disabled = !safeShareUrl(survey);
  }

  function validationInput(question, key, label, integer = true) {
    const control = input(question.validation[key], (value) => {
      if (value === "") delete question.validation[key];
      else question.validation[key] = Number(value);
      dirty();
    }, { type: "number", step: integer ? "1" : "any", ...(integer ? { min: "0" } : {}), testId: `${question.id}-${key}` });
    return field(label, control);
  }

  function renderQuestions() {
    const questions = state.current.questions;
    $("questions").replaceChildren();
    $("question-count").textContent = `${questions.length} / 100 题`;
    if (!questions.length) $("questions").append(el("p", "inline-empty", "还没有题目。选择下方题型添加。"));
    questions.forEach((question, index) => {
      question.validation ||= {};
      const block = el("section", "question");
      block.dataset.testid = `question-${question.id}`;
      block.dataset.questionId = question.id;
      const heading = el("div", "question-heading");
      const meta = el("div", "question-heading-meta");
      meta.append(el("h4", "", `${index + 1}. ${TYPES[question.type] || question.type}`), el("span", "identifier", question.id));
      heading.append(meta);
      if (isDraft()) {
        const controls = el("div", "question-actions");
        const up = button("上移", "quiet", () => moveQuestion(index, -1), `move-up-${question.id}`);
        const down = button("下移", "quiet", () => moveQuestion(index, 1), `move-down-${question.id}`);
        up.disabled = index === 0; down.disabled = index === questions.length - 1;
        controls.append(up, down, button("删除", "quiet", () => removeQuestion(question.id), `delete-${question.id}`));
        heading.append(controls);
      }
      block.append(heading);
      block.append(field("题目内容", input(question.title, (value) => { question.title = value; dirty(); }, { required: true, maxLength: 500, testId: `question-title-${question.id}` })));
      const required = input("", (_, node) => { question.required = node.checked; dirty(); }, { type: "checkbox", checked: Boolean(question.required), testId: `required-${question.id}` });
      const requiredLabel = el("label", "check-label question-required");
      requiredLabel.append(required, el("span", "", "必答题"));
      block.append(requiredLabel);
      if (question.type === "single" || question.type === "multi") {
        const options = el("div", "options");
        (question.options || []).forEach((option) => {
          const row = el("div", "option-row");
          row.append(el("span", `option-marker ${question.type}`));
          const wrap = el("div", "option-input-wrap");
          const optionInput = input(option.label, (value) => { option.label = value; dirty(); }, { required: true, maxLength: 200, testId: `option-label-${option.id}` });
          optionInput.setAttribute("aria-label", `选项内容 ${option.id}`);
          wrap.append(optionInput, el("span", "option-id", option.id));
          row.append(wrap);
          if (isDraft()) row.append(button("删除", "quiet", () => {
            question.options = question.options.filter((item) => item.id !== option.id);
            dirty(); renderQuestions(); renderRules();
          }, `delete-option-${option.id}`));
          options.append(row);
        });
        if (isDraft()) {
          const add = button("添加选项", "secondary add-option", () => {
            question.options.push({ id: stableId("o"), label: "" });
            dirty(); renderQuestions(); renderRules();
          }, `add-option-${question.id}`);
          add.disabled = (question.options || []).length >= 50;
          options.append(add);
        }
        block.append(options);
      }
      if (question.type !== "single") {
        const constraints = el("div", "constraints");
        constraints.append(el("p", "", "回答校验（留空表示不限制）"));
        const grid = el("div", "constraint-grid");
        if (question.type === "multi") grid.append(validationInput(question, "min_choices", "最少选几项"), validationInput(question, "max_choices", "最多选几项"), validationInput(question, "exact_choices", "必须选几项"));
        if (question.type === "text") grid.append(validationInput(question, "min_length", "最少字数"), validationInput(question, "max_length", "最多字数"));
        if (question.type === "number") {
          grid.append(validationInput(question, "min_value", "最小值", false), validationInput(question, "max_value", "最大值", false));
          const label = el("label", "check-label");
          label.append(input("", (_, node) => { question.validation.integer_only = node.checked; dirty(); }, { type: "checkbox", checked: Boolean(question.validation.integer_only), testId: `integer-only-${question.id}` }), el("span", "", "仅允许整数"));
          grid.append(label);
        }
        constraints.append(grid); block.append(constraints);
      }
      $("questions").append(block);
    });
    for (const control of document.querySelectorAll("[data-add-type]")) control.disabled = questions.length >= 100;
  }

  function moveQuestion(index, delta) {
    if (state.busy || !isDraft()) return;
    const questions = state.current.questions;
    [questions[index], questions[index + delta]] = [questions[index + delta], questions[index]];
    dirty(); renderQuestions(); renderRules();
    feedback("题目顺序已调整。请检查已有跳转是否仍指向后面的题目，再保存。");
  }

  function removeQuestion(id) {
    if (state.busy || !isDraft()) return;
    const referenced = state.current.rules.some((rule) => rule.source === id || rule.target === id);
    if (referenced && !window.confirm("这道题参与了跳转。删除题目时，也会删除引用它的跳转规则。继续？")) return;
    state.current.questions = state.current.questions.filter((question) => question.id !== id);
    state.current.rules = state.current.rules.filter((rule) => rule.source !== id && rule.target !== id);
    dirty(); renderQuestions(); renderRules(); updateActionStates();
  }

  function hasRuleSource() {
    const questions = state.current?.questions || [];
    return questions.some((question, index) => question.type !== "text" && index < questions.length - 1);
  }

  function renderRules() {
    const survey = state.current;
    const questions = survey.questions;
    const label = (question) => `${question.title || "未填写题目"} [${question.id}]`;
    const sources = questions.filter((question, index) => question.type !== "text" && index < questions.length - 1);
    $("rules").replaceChildren();
    if (!survey.rules.length) $("rules").append(el("p", "inline-empty", "未设置跳转，将按题目顺序填写。至少添加两道题，且前面的题为单选、多选或数字题后，可添加规则。"));
    survey.rules.forEach((rule, index) => {
      const block = el("div", "rule");
      block.dataset.testid = `rule-${index}`;
      const heading = el("div", "rule-heading");
      heading.append(el("h4", "", `规则 ${index + 1}`));
      if (isDraft()) heading.append(button("删除规则", "quiet", () => { survey.rules.splice(index, 1); dirty(); renderRules(); }, `delete-rule-${index}`));
      block.append(heading);
      const grid = el("div", "rule-grid");
      const source = questions.find((question) => question.id === rule.source);
      grid.append(field("当这道题", select(rule.source, sources.map((question) => [question.id, label(question)]), (value) => {
        rule.source = value;
        const selected = questions.find((question) => question.id === value);
        rule.op = selected.type === "multi" ? "any" : "eq";
        rule.value = selected.type === "multi" ? [] : selected.type === "number" ? 0 : (selected.options?.[0]?.id || "");
        const next = questions[questions.indexOf(selected) + 1];
        rule.target = next?.id || "";
        dirty(); renderRules();
      }, `rule-source-${index}`)));
      const operators = source?.type === "multi" ? [["any", "包含任意"], ["all", "包含全部"]] : source?.type === "number" ? [["eq", "等于"], ["lt", "小于"], ["lte", "小于等于"], ["gt", "大于"], ["gte", "大于等于"]] : [["eq", "选择了"]];
      grid.append(field("条件", select(rule.op, operators, (value) => { rule.op = value; dirty(); }, `rule-op-${index}`)));
      if (source?.type === "multi") {
        const note = el("p", "muted", "在下方勾选条件选项。空条件不能保存发布。");
        grid.append(note);
      } else if (source?.type === "number") {
        grid.append(field("比较值", input(rule.value, (value) => { rule.value = value === "" ? null : Number(value); dirty(); }, { type: "number", step: "any", required: true, testId: `rule-value-${index}` })));
      } else {
        grid.append(field("选项", select(rule.value, (source?.options || []).map((option) => [option.id, `${option.label || "未填写选项"} [${option.id}]`]), (value) => { rule.value = value; dirty(); }, `rule-value-${index}`)));
      }
      const sourceIndex = questions.findIndex((question) => question.id === rule.source);
      const targets = sourceIndex < 0 ? [] : questions.slice(sourceIndex + 1);
      const target = field("跳到", select(rule.target, targets.map((question) => [question.id, label(question)]), (value) => { rule.target = value; dirty(); }, `rule-target-${index}`));
      target.classList.add("rule-target");
      grid.append(target, field("优先级（同一来源不能重复）", input(rule.priority, (value) => { rule.priority = value === "" ? null : Number(value); dirty(); }, { type: "number", step: "1", min: "0", required: true, testId: `rule-priority-${index}` })));
      block.append(grid);
      if (source?.type === "multi") {
        const values = el("fieldset", "rule-values");
        values.append(el("legend", "", "匹配选项"));
        for (const option of source.options || []) {
          const choice = el("label", "check-label");
          const control = input("", (_, node) => {
            const selected = Array.isArray(rule.value) ? [...rule.value] : [];
            rule.value = node.checked ? [...selected.filter((id) => id !== option.id), option.id] : selected.filter((id) => id !== option.id);
            dirty();
          }, { type: "checkbox", checked: Array.isArray(rule.value) && rule.value.includes(option.id), testId: `rule-value-${index}-${option.id}` });
          choice.append(control, el("span", "", `${option.label || "未填写选项"} [${option.id}]`));
          values.append(choice);
        }
        const missing = (Array.isArray(rule.value) ? rule.value : []).filter((id) => !source.options?.some((option) => option.id === id));
        if (missing.length) values.append(el("p", "muted", `条件含已删除选项：${missing.join("、")}。请删除并重建此规则。`));
        block.append(values);
      }
      $("rules").append(block);
    });
    updateActionStates();
  }

  function draftPayload() {
    const survey = state.current;
    if (!$("survey-form").reportValidity()) throw new Error("请先补全题目、选项及规则中的必填内容，并检查数值格式。");
    if (!survey.title.trim()) throw new Error("请填写问卷标题。");
    return { title: survey.title.trim(), description: survey.description || "", allow_anonymous: Boolean(survey.allow_anonymous), allow_repeat: Boolean(survey.allow_repeat), closes_at: deadlineValue(), revision: survey.revision, questions: survey.questions, rules: survey.rules };
  }

  async function saveDraft(silent = false) {
    if (!isDraft()) throw new Error("只有草稿可以编辑。");
    const survey = await api(`/api/surveys/${encodeURIComponent(state.current.id)}`, { method: "PUT", body: draftPayload() });
    state.current = survey;
    state.current.questions ||= [];
    state.current.rules ||= [];
    state.dirty = false;
    renderEditor();
    await reloadList();
    if (!silent) feedback("草稿已保存。");
  }

  async function loadFill() {
    $("fill-content").replaceChildren(el("p", "muted", "正在读取问卷…"));
    try {
      const survey = await api(`/api/fill/${encodeURIComponent(shareCode)}`);
      const header = el("div", "fill-header");
      const title = el("h1", "", survey.title); title.id = "fill-title";
      header.append(title);
      if (survey.description) header.append(el("p", "fill-description", survey.description));
      const policies = el("div", "fill-policy");
      policies.append(el("span", "", survey.allow_anonymous ? "对创建者匿名（仍需登录）" : "创建者可查看你的账号"), el("span", "", survey.allow_repeat ? "允许多次填写" : "每个账号限提交一次"));
      header.append(policies);
      const notice = el("p", "fill-notice", "当前可查看发布内容。逐题填写及提交功能尚未开放；本页不会保存回答。");
      notice.dataset.testid = "fill-unavailable";
      const list = el("ol", "preview-list");
      (survey.questions || []).forEach((question, index) => {
        const item = el("li", "preview-question");
        item.append(el("p", "question-type", `${TYPES[question.type] || question.type}${question.required ? " · 必答" : " · 选答"}`), el("h3", "", `${index + 1}. ${question.title}`));
        if (question.options?.length) {
          const options = el("ul");
          for (const option of question.options) options.append(el("li", "", option.label));
          item.append(options);
        } else item.append(el("p", "muted", question.type === "number" ? "数字回答" : "文本回答"));
        list.append(item);
      });
      $("fill-content").replaceChildren(header, notice, list);
      document.title = `${survey.title} · 问卷工作台`;
    } catch (error) {
      $("fill-content").replaceChildren(el("h1", "", "暂时无法打开问卷"), el("p", "muted", error.message));
      throw error;
    }
  }

  $("login-tab").addEventListener("click", () => switchAuth("login"));
  $("register-tab").addEventListener("click", () => switchAuth("register"));
  $("auth-form").addEventListener("submit", (event) => {
    event.preventDefault();
    action($("auth-submit"), async () => {
      const body = { username: $("username").value.trim(), password: $("password").value };
      if (state.authMode === "register") await api("/api/auth/register", { method: "POST", body });
      state.user = await api("/api/auth/login", { method: "POST", body });
      $("password").value = "";
      state.current = null;
      state.dirty = false;
      await showSignedIn();
      feedback(state.authMode === "register" ? "账号已创建，登录成功。" : "登录成功。");
    });
  });

  $("logout").addEventListener("click", () => action($("logout"), async () => {
    if (state.dirty && !window.confirm("退出会丢失未保存的修改。继续退出？")) return;
    await api("/api/auth/logout", { method: "POST" });
    state.current = null; state.surveys = []; state.dirty = false;
    $("editor").hidden = true; $("empty-editor").hidden = false;
    showAuth(); feedback("已退出登录。");
  }));

  function showCreate() {
    if (state.busy) return;
    $("create-form").reset();
    $("create-dialog").showModal();
  }
  $("new-survey").addEventListener("click", showCreate);
  $("empty-create").addEventListener("click", showCreate);
  $("cancel-create").addEventListener("click", () => $("create-dialog").close());
  $("create-form").addEventListener("submit", (event) => {
    event.preventDefault();
    action($("create-submit"), async () => {
      if (state.dirty && !window.confirm("当前问卷还有未保存修改。放弃这些修改并创建新问卷？")) return;
      const title = $("create-title").value.trim();
      if (!title) throw new Error("请填写问卷标题。");
      const survey = await api("/api/surveys", { method: "POST", body: { title, description: $("create-description").value, allow_anonymous: true, allow_repeat: false, closes_at: null } });
      $("create-dialog").close();
      await reloadList();
      await openSurvey(survey.id, true);
      feedback("草稿已创建。选择题型开始添加题目。");
    });
  });
  $("refresh-surveys").addEventListener("click", () => action($("refresh-surveys"), reloadList));

  $("survey-title").addEventListener("input", () => { state.current.title = $("survey-title").value; dirty(); });
  $("survey-description").addEventListener("input", () => { state.current.description = $("survey-description").value; dirty(); });
  $("allow-anonymous").addEventListener("change", () => { state.current.allow_anonymous = $("allow-anonymous").checked; dirty(); });
  $("allow-repeat").addEventListener("change", () => { state.current.allow_repeat = $("allow-repeat").checked; dirty(); });
  $("survey-deadline").addEventListener("input", () => { if (isDraft()) dirty(); });
  for (const control of document.querySelectorAll("[data-add-type]")) control.addEventListener("click", () => {
    if (!isDraft() || state.busy || state.current.questions.length >= 100) return;
    const type = control.dataset.addType;
    const question = { id: stableId("q"), type, title: "", required: true, validation: {} };
    if (type === "single" || type === "multi") question.options = [{ id: stableId("o"), label: "" }, { id: stableId("o"), label: "" }];
    state.current.questions.push(question);
    dirty(); renderQuestions(); renderRules();
    document.querySelector(`[data-testid="question-title-${question.id}"]`)?.focus();
  });
  $("add-rule").addEventListener("click", () => {
    if (!isDraft() || state.busy || !hasRuleSource()) return;
    const questions = state.current.questions;
    const index = questions.findIndex((question, position) => question.type !== "text" && position < questions.length - 1);
    const source = questions[index];
    const priorities = state.current.rules.filter((rule) => rule.source === source.id).map((rule) => Number(rule.priority) || 0);
    state.current.rules.push({ source: source.id, op: source.type === "multi" ? "any" : "eq", value: source.type === "multi" ? [] : source.type === "number" ? 0 : (source.options?.[0]?.id || ""), target: questions[index + 1].id, priority: Math.max(0, ...priorities) + 10 });
    dirty(); renderRules();
  });
  $("survey-form").addEventListener("submit", (event) => { event.preventDefault(); action($("save-survey"), () => saveDraft()); });
  $("publish-survey").addEventListener("click", () => action($("publish-survey"), async () => {
    if (!isDraft()) return;
    if (state.dirty) await saveDraft(true);
    const id = state.current.id;
    await api(`/api/surveys/${encodeURIComponent(id)}/publish`, { method: "POST", body: { revision: state.current.revision } });
    await openSurvey(id, true); await reloadList();
    feedback("问卷已发布。复制下方链接分享给填写者。");
  }));
  $("save-deadline").addEventListener("click", () => action($("save-deadline"), async () => {
    const closesAt = deadlineValue();
    const result = await api(`/api/surveys/${encodeURIComponent(state.current.id)}/deadline`, { method: "PATCH", body: { closes_at: closesAt } });
    state.current.closes_at = result?.closes_at ?? closesAt;
    if (result?.revision !== undefined) state.current.revision = result.revision;
    $("survey-deadline").value = dateInput(state.current.closes_at);
    if (isDraft()) $("editor-status").replaceChildren(el("span", "status draft", STATUS.draft), el("span", "", `草稿修订 ${state.current.revision}`));
    await reloadList(); feedback("截止时间已保存。时间按北京时间显示。");
  }));
  $("close-survey").addEventListener("click", () => action($("close-survey"), async () => {
    if (!window.confirm("关闭后将停止接收新的填写，且本阶段不能重新开放。确认关闭？")) return;
    const id = state.current.id;
    await api(`/api/surveys/${encodeURIComponent(id)}/close`, { method: "POST" });
    await openSurvey(id, true); await reloadList(); feedback("问卷已关闭。");
  }));
  $("copy-share").addEventListener("click", () => action($("copy-share"), async () => {
    const url = safeShareUrl(state.current);
    if (!url) throw new Error("分享链接尚未生成，请刷新问卷详情。");
    try { await navigator.clipboard.writeText(url); feedback("分享链接已复制。"); }
    catch { $("share-url").focus(); $("share-url").select(); feedback("请按 Ctrl+C 或使用系统复制操作复制已选中的链接。"); }
  }));
  window.addEventListener("beforeunload", (event) => {
    if (state.dirty) { event.preventDefault(); event.returnValue = ""; }
  });

  action(null, async () => {
    try { state.user = await api("/api/auth/me"); }
    catch (error) {
      showAuth();
      if (error.status !== 401) throw error;
      return;
    }
    await showSignedIn();
  });
})();
