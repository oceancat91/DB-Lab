"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const TYPES = { single: "单选题", multi: "多选题", text: "文本题", number: "数字题" };
  const STATUS = { draft: "草稿", published: "已发布", closed: "已关闭" };
  const state = { user: null, surveys: [], current: null, dirty: false, busy: false, authMode: "login", fill: null, results: null };
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
      if (state.focusId) {
        $(state.focusId)?.focus();
        state.focusId = null;
      }
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
    state.results = { surveyId: state.current.id, mode: "statistics", questionId: "" };
    state.dirty = false;
    renderEditor();
    renderList();
    if (!isDraft()) await loadResults();
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
    $("results-section").hidden = survey.status === "draft";
    if (!isDraft()) renderResultsControls();
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
      state.fill = newFill(survey);
      const header = el("div", "fill-header");
      const title = el("h1", "", survey.title); title.id = "fill-title";
      header.append(title);
      if (survey.description) header.append(el("p", "fill-description", survey.description));
      const policies = el("div", "fill-policy");
      policies.append(el("span", "", survey.allow_anonymous ? "对创建者匿名（仍需登录）" : "创建者可查看你的账号"), el("span", "", survey.allow_repeat ? "允许多次填写" : "每个账号限提交一次"));
      header.append(policies);
      const notice = el("p", "fill-notice", "回答仅保留在当前页面，提交前不会自动保存。返回改答会清除后续回答，并重新确定填写顺序。");
      notice.id = "fill-save-note";
      const session = el("div"); session.id = "fill-session";
      $("fill-content").replaceChildren(header, notice, session);
      document.title = `${survey.title} · 问卷工作台`;
      applyFillResult(await nextFill({}));
      renderFillSession();
    } catch (error) {
      $("fill-content").replaceChildren(el("h1", "", "暂时无法打开问卷"), el("p", "muted", error.message));
      throw error;
    }
  }

  async function nextFill(answers) {
    return api(`/api/fill/${encodeURIComponent(shareCode)}/next`, { method: "POST", body: { version: state.fill.survey.version, answers } });
  }

  function newFill(survey) {
    return { survey, answers: {}, path: [], currentId: null, complete: false, changed: false,
      reviewId: null, reviewValue: null, requestId: stableId("r"), submitBody: null,
      submitState: "idle", submitError: "", receipt: null, userId: state.user?.id };
  }

  function applyFillResult(result) {
    const fill = state.fill;
    fill.path = result.path;
    fill.answers = result.answers;
    fill.currentId = result.next_question_id;
    fill.complete = result.complete;
    fill.reviewId = null;
    fill.reviewValue = null;
  }

  function fillQuestion(id) {
    return state.fill.survey.questions.find((question) => question.id === id);
  }

  function answerText(question, value) {
    if (value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length)) return "未回答（选答题）";
    if (question.type === "single") return question.options.find((option) => option.id === value)?.label || String(value);
    if (question.type === "multi") return value.map((id) => question.options.find((option) => option.id === id)?.label || id).join("、");
    return String(value);
  }

  function fillHint(question) {
    const validation = question.validation || {};
    const hints = [];
    if (question.type === "multi") {
      if (validation.exact_choices !== undefined) hints.push(`请选择 ${validation.exact_choices} 项`);
      else {
        if (validation.min_choices !== undefined) hints.push(`最少 ${validation.min_choices} 项`);
        if (validation.max_choices !== undefined) hints.push(`最多 ${validation.max_choices} 项`);
      }
    }
    if (question.type === "text") {
      if (validation.min_length !== undefined) hints.push(`最少 ${validation.min_length} 字`);
      if (validation.max_length !== undefined) hints.push(`最多 ${validation.max_length} 字`);
      hints.push("按 Unicode 码点计字数，保留原文");
    }
    if (question.type === "number") {
      if (validation.min_value !== undefined) hints.push(`不小于 ${validation.min_value}`);
      if (validation.max_value !== undefined) hints.push(`不大于 ${validation.max_value}`);
      if (validation.integer_only) hints.push("仅允许整数");
    }
    if (!question.required) hints.push("可留空并继续");
    return hints.join("；");
  }

  function fillError(error) {
    const message = $("fill-error");
    if (message) {
      message.textContent = error.message;
      message.hidden = false;
    }
  }

  async function goToFillQuestion(id) {
    const fill = state.fill;
    if (["pending", "uncertain", "success"].includes(fill.submitState)) throw new Error("请先确认本次提交结果，再开始新的填写。");
    const index = fill.path.indexOf(id);
    if (index < 0) throw new Error("该题不在当前填写路径中，请从上一题重新继续。");
    const earlier = fill.path.slice(0, index);
    const prefix = {};
    for (const previous of earlier) if (Object.hasOwn(fill.answers, previous)) prefix[previous] = fill.answers[previous];
    const previousValue = fill.answers[id];
    try {
      const result = await nextFill(prefix);
      applyFillResult(result);
      if (fill.submitBody) fill.requestId = stableId("r");
      fill.submitBody = null; fill.submitState = "idle"; fill.submitError = "";
      // Preserve only the target's old value for convenient editing; later answers are discarded.
      if (result.next_question_id === id) {
        fill.reviewId = id;
        fill.reviewValue = previousValue;
      }
      fill.changed = true;
      renderFillSession();
      state.focusId = "fill-question-heading";
    } catch (error) { fillError(error); throw error; }
  }

  function renderFillSession() {
    const fill = state.fill;
    const session = $("fill-session");
    session.replaceChildren();
    if (fill.receipt) { renderFillReceipt(session); return; }
    if (fill.complete) {
      renderFillReview(session);
      return;
    }
    const question = fillQuestion(fill.currentId);
    if (!question) throw new Error("问卷返回的题目不可用，请刷新后重试。");
    const position = fill.survey.questions.findIndex((item) => item.id === question.id) + 1;
    const panel = el("section", "fill-question");
    panel.dataset.testid = "fill-question";
    panel.dataset.questionId = question.id;
    panel.append(el("p", "fill-progress", `第 ${position} 题 / 共 ${fill.survey.questions.length} 题（根据回答可能跳题）`));
    const heading = el("h2", "", question.title);
    heading.id = "fill-question-heading";
    heading.tabIndex = -1;
    const type = el("span", "fill-required", question.required ? "必答" : "选答");
    panel.append(heading, type);
    const hint = el("p", "muted", fillHint(question)); hint.id = "fill-hint";
    panel.append(hint);
    const form = el("form", "fill-form");
    form.id = "fill-answer-form"; form.dataset.testid = "fill-answer-form"; form.noValidate = true;
    const value = fill.reviewId === question.id ? fill.reviewValue : fill.answers[question.id];
    if (question.type === "single" || question.type === "multi") {
      const choices = el("fieldset", "fill-choices");
      choices.setAttribute("aria-describedby", "fill-hint fill-error");
      const legend = el("legend", "sr-only", question.type === "single" ? "选择一个选项" : "选择适用选项");
      choices.append(legend);
      for (const option of question.options || []) {
        const label = el("label", "fill-choice");
        const control = el("input");
        control.type = question.type === "single" ? "radio" : "checkbox";
        control.name = "answer"; control.value = option.id;
        control.dataset.testid = `fill-option-${option.id}`;
        control.checked = question.type === "single" ? value === option.id : Array.isArray(value) && value.includes(option.id);
        label.append(control, el("span", "", option.label)); choices.append(label);
      }
      form.append(choices);
      if (!question.required) form.append(button("清空选择", "quiet", () => {
        for (const control of choices.querySelectorAll("input")) control.checked = false;
        fill.changed = true;
      }, "fill-clear"));
    } else {
      const control = el(question.type === "text" ? "textarea" : "input");
      control.id = "fill-answer"; control.name = "answer"; control.dataset.testid = "fill-answer";
      control.value = value ?? "";
      control.setAttribute("aria-label", question.title);
      control.setAttribute("aria-describedby", "fill-hint fill-error");
      control.setAttribute("aria-required", String(question.required));
      if (question.type === "text") {
        control.rows = 5;
        const count = el("p", "fill-word-count", `${Array.from(control.value).length} 字`);
        control.addEventListener("input", () => { count.textContent = `${Array.from(control.value).length} 字`; });
        form.append(control, count);
      } else { control.type = "number"; control.step = "any"; form.append(control); }
    }
    const error = el("p", "fill-error"); error.id = "fill-error"; error.hidden = true;
    error.setAttribute("role", "alert"); error.dataset.testid = "fill-error";
    form.append(error);
    const actions = el("div", "fill-actions");
    const index = fill.path.indexOf(question.id);
    const back = button("上一题", "secondary", () => action(back, () => goToFillQuestion(fill.path[index - 1])), "fill-back");
    back.id = "fill-back"; back.disabled = index <= 0;
    const next = button("下一题", "primary", () => {}, "fill-next");
    next.id = "fill-next"; next.type = "submit";
    actions.append(back, next); form.append(actions);
    form.addEventListener("input", () => { fill.changed = true; error.hidden = true; });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      action(next, async () => {
        try {
          let answer;
          if (question.type === "single") answer = form.querySelector('input[name="answer"]:checked')?.value ?? null;
          else if (question.type === "multi") {
            answer = Array.from(form.querySelectorAll('input[name="answer"]:checked'), (node) => node.value);
            if (!answer.length) answer = null;
          } else {
            const control = $("fill-answer");
            if (question.type === "number") {
              if (control.validity.badInput) throw new Error("请输入有效数字。");
              answer = control.value === "" ? null : Number(control.value);
              if (answer !== null && !Number.isFinite(answer)) throw new Error("请输入有限数字。");
            } else answer = control.value.trim() === "" ? null : control.value;
          }
          const answers = {};
          for (const id of fill.path.slice(0, index)) if (Object.hasOwn(fill.answers, id)) answers[id] = fill.answers[id];
          answers[question.id] = answer;
          applyFillResult(await nextFill(answers));
          fill.changed = true;
          renderFillSession();
          state.focusId = fill.complete ? "fill-review-heading" : "fill-question-heading";
        } catch (failure) { fillError(failure); throw failure; }
      });
    });
    panel.append(form); session.append(panel);
    const visited = fill.path.filter((id) => id !== question.id && Object.hasOwn(fill.answers, id));
    if (visited.length) {
      const history = el("nav", "fill-history"); history.setAttribute("aria-label", "返回修改已答题");
      history.append(el("p", "muted", "返回修改已答题（后续回答会清除）"));
      for (const id of visited) {
        const previous = fillQuestion(id);
        const edit = button(previous.title, "quiet", () => action(edit, () => goToFillQuestion(id)), `fill-edit-${id}`);
        history.append(edit);
      }
      session.append(history);
    }
  }

  function renderFillReview(session) {
    const fill = state.fill;
    const panel = el("section", "fill-review"); panel.dataset.testid = "fill-review";
    const heading = el("h2", "", "核对你的回答"); heading.id = "fill-review-heading"; heading.tabIndex = -1;
    panel.append(heading, el("p", "muted", `已按实际路径完成 ${fill.path.length} 道题。以下为当前页面中的回答预览。`));
    const locked = ["pending", "uncertain"].includes(fill.submitState);
    const notice = el("p", "fill-notice", locked ? "尚未收到明确的提交回执。请保持本页，点击重试确认结果；确认前暂时不能修改回答。" : "请核对回答，确认后点击提交。成功提交后将显示回执。");
    notice.dataset.testid = "fill-submit-note"; panel.append(notice);
    const list = el("ol", "fill-review-list");
    for (const id of fill.path) {
      const question = fillQuestion(id);
      const item = el("li"); item.dataset.testid = `fill-review-${id}`;
      const row = el("div", "fill-review-row");
      row.append(el("h3", "", question.title));
      const edit = button("修改", "quiet", () => action(edit, () => goToFillQuestion(id)), `fill-edit-${id}`);
      edit.disabled = locked;
      row.append(edit);
      item.append(row, el("p", "fill-review-answer", answerText(question, fill.answers[id]))); list.append(item);
    }
    panel.append(list);
    const error = el("p", "fill-error", fill.submitError);
    error.id = "fill-error"; error.hidden = !fill.submitError;
    error.setAttribute("role", "alert"); error.dataset.testid = "fill-error"; panel.append(error);
    const actions = el("div", "fill-actions");
    const back = button("返回上一题", "secondary", () => action(back, () => goToFillQuestion(fill.path[fill.path.length - 1])), "fill-back");
    back.id = "fill-back"; back.disabled = !fill.path.length || locked;
    const submit = button(fill.submitState === "pending" ? "正在提交…" : fill.submitBody ? "重试提交" : "确认提交", "primary", () => action(submit, submitFill), fill.submitBody ? "fill-retry" : "fill-submit");
    submit.id = "fill-submit"; submit.disabled = fill.submitState === "pending";
    actions.append(back, submit); panel.append(actions); session.append(panel);
  }

  async function submitFill() {
    const fill = state.fill;
    if (!fill.complete || fill.receipt) return;
    const wasUncertain = fill.submitState === "uncertain";
    if (!fill.submitBody) {
      // A detached snapshot is retained unchanged until an explicit server response resolves it.
      fill.submitBody = JSON.parse(JSON.stringify({ version: fill.survey.version, request_id: fill.requestId, answers: fill.answers }));
    }
    fill.submitState = "pending"; fill.submitError = "";
    renderFillSession();
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    try {
      const currentUser = await api("/api/auth/me", { signal: controller.signal });
      if (currentUser.id !== fill.userId) {
        const changed = new Error("当前登录账号已变化，本次未发送。请回到原账号后重试，或退出后重新填写。");
        changed.status = 409; throw changed;
      }
      const receipt = await api(`/api/fill/${encodeURIComponent(shareCode)}/submit`, { method: "POST", body: fill.submitBody, signal: controller.signal });
      if (!receipt || typeof receipt.id !== "string" || !receipt.submitted_at || typeof receipt.replayed !== "boolean") throw new Error("未收到完整回执，请重试确认本次提交结果。");
      fill.receipt = receipt; fill.submitState = "success"; fill.changed = false;
      $("fill-save-note").textContent = "回答已成功提交并保存。下方回执用于确认本次提交结果。";
      renderFillSession(); state.focusId = "fill-receipt-heading";
      feedback(receipt.replayed ? "已确认先前提交成功，没有重复保存。" : "提交成功，回答已保存。");
    } catch (error) {
      // Transport failures and server failures cannot prove that the write did not commit.
      const uncertain = !error.status || error.status >= 500 || wasUncertain;
      fill.submitState = uncertain ? "uncertain" : "rejected";
      fill.submitError = error.status === 401 ? "登录已过期。请在另一个工作台页面登录后，返回本页重试确认提交。" : error.message;
      renderFillSession();
      feedback(uncertain ? "提交结果尚未确认，请重试。重试会确认同一次提交，不会另存一份。" : fill.submitError, true);
    } finally { window.clearTimeout(timeout); }
  }

  function submittedTime(value) {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "时间不可用";
    return new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(date) + "（北京时间）";
  }

  function renderFillReceipt(session) {
    const fill = state.fill;
    const panel = el("section", "fill-receipt"); panel.dataset.testid = "fill-receipt";
    const heading = el("h2", "", "提交成功"); heading.id = "fill-receipt-heading"; heading.tabIndex = -1;
    panel.append(heading, el("p", "", "你的回答已保存，谢谢参与。"));
    const details = el("dl", "receipt-details");
    details.append(el("dt", "", "回执编号"), el("dd", "", fill.receipt.id), el("dt", "", "提交时间"), el("dd", "", submittedTime(fill.receipt.submitted_at)));
    panel.append(details);
    if (fill.receipt.replayed) panel.append(el("p", "muted", "已确认先前提交成功，本次重试没有新增答卷。"));
    if (fill.survey.allow_repeat) {
      const restart = button("重新填写", "primary", () => action(restart, restartFill), "fill-restart");
      panel.append(el("p", "muted", "此问卷允许多次填写。重新填写会从第一题开始，并单独保存一份答卷。"), restart);
    } else panel.append(el("p", "muted", "此问卷每个账号限提交一次。"));
    session.append(panel);
  }

  async function restartFill() {
    const survey = await api(`/api/fill/${encodeURIComponent(shareCode)}`);
    const result = await api(`/api/fill/${encodeURIComponent(shareCode)}/next`, { method: "POST", body: { version: survey.version, answers: {} } });
    state.fill = newFill(survey);
    applyFillResult(result);
    $("fill-save-note").textContent = "本次填写尚未提交。回答仅保留在当前页面，提交前不会自动保存。";
    renderFillSession(); state.focusId = "fill-question-heading";
  }

  function renderResultsControls() {
    if (!state.results || state.results.surveyId !== state.current.id) state.results = { surveyId: state.current.id, mode: "statistics", questionId: "" };
    const statistics = state.results.mode === "statistics";
    $("statistics-tab").classList.toggle("active", statistics);
    $("responses-tab").classList.toggle("active", !statistics);
    $("statistics-tab").setAttribute("aria-pressed", String(statistics));
    $("responses-tab").setAttribute("aria-pressed", String(!statistics));
    $("statistics-filter").hidden = !statistics;
    const scope = $("statistics-question");
    scope.replaceChildren();
    const all = el("option", "", "整卷所有题目"); all.value = ""; scope.append(all);
    for (const question of state.current.questions) {
      const option = el("option", "", question.title); option.value = question.id; scope.append(option);
    }
    scope.value = state.results.questionId;
  }

  async function loadResults() {
    if (!state.current || isDraft()) return;
    const results = state.results;
    const base = `/api/surveys/${encodeURIComponent(results.surveyId)}`;
    $("results-content").replaceChildren(el("p", "muted", "正在读取结果…"));
    try {
      if (results.mode === "responses") {
        const data = await api(base + "/responses");
        renderResponses(Array.isArray(data) ? data : []);
      } else {
        const suffix = results.questionId ? "/" + encodeURIComponent(results.questionId) : "";
        const data = await api(base + "/statistics" + suffix);
        renderStatistics(data, Boolean(results.questionId));
      }
    } catch (error) {
      const message = el("p", "fill-error", `结果读取失败：${error.message} 可点击“刷新结果”重试。`);
      message.setAttribute("role", "alert"); $("results-content").replaceChildren(message); throw error;
    }
  }

  function metric(label, value, testId) {
    const node = el("div", "result-metric");
    node.append(el("span", "", label));
    const number = el("strong", "", value ?? "暂无");
    if (testId) number.dataset.testid = testId;
    node.append(number); return node;
  }

  function renderStatistics(data, single) {
    const content = $("results-content"); content.replaceChildren();
    const container = el("div", "statistics-content"); container.dataset.testid = "statistics-content";
    if (!single) {
      const summary = el("div", "result-metrics");
      summary.append(metric("成功提交", data.submissions, "statistics-submissions"), metric("去重填写人数", data.respondents, "statistics-respondents"), metric("发布版本", data.version, "statistics-version"));
      container.append(summary);
      if (data.submissions === 0) container.append(el("p", "inline-empty", "暂时没有成功提交的答卷。分享问卷后，可刷新查看结果。"));
    } else container.append(el("p", "muted", "当前显示所选题目的统计；空答与跳过不计入有效回答数。"));
    const questions = single ? [data] : data.questions;
    for (const question of questions || []) container.append(statisticsQuestion(question));
    content.append(container);
  }

  function statisticsQuestion(question) {
    const section = el("section", "stat-question"); section.dataset.testid = `statistics-question-${question.id}`;
    section.append(el("p", "question-type", TYPES[question.type] || question.type), el("h4", "", question.title));
    section.append(el("p", "muted", `有效回答 ${question.answered_submissions ?? "暂无"} 份，去重 ${question.answered_people ?? "暂无"} 人。`));
    if (question.type === "single" || question.type === "multi") {
      const table = el("table", "statistics-table");
      const caption = el("caption", "sr-only", `${question.title} 各选项回答统计`); table.append(caption);
      const head = el("thead"), header = el("tr");
      for (const title of ["选项", "选择次数", "去重人数"]) { const cell = el("th", "", title); cell.scope = "col"; header.append(cell); }
      head.append(header); table.append(head);
      const body = el("tbody");
      for (const option of question.options || []) {
        const row = el("tr"); row.dataset.testid = `statistics-option-${question.id}-${option.id}`;
        row.append(el("td", "", option.label), el("td", "", option.count ?? "暂无"), el("td", "", option.people ?? "暂无")); body.append(row);
      }
      table.append(body); section.append(table);
    } else {
      if (question.type === "number") section.append(metric("有效数字均值", question.mean === null || question.mean === undefined ? "暂无" : question.mean, `statistics-mean-${question.id}`));
      const values = Array.isArray(question.values) ? question.values : [];
      if (!values.length) section.append(el("p", "muted", "暂无有效回答。"));
      else {
        const details = el("details", "raw-values");
        details.append(el("summary", "", `查看 ${values.length} 条原始回答`));
        const list = el("ol");
        for (const entry of values) {
          const value = entry && typeof entry === "object" && Object.hasOwn(entry, "value") ? entry.value : entry;
          list.append(el("li", "", ["string", "number"].includes(typeof value) ? value : "回答格式不可用"));
        }
        details.append(list); section.append(details);
      }
    }
    return section;
  }

  function renderResponses(responses) {
    const content = $("results-content"); content.replaceChildren();
    const container = el("div", "responses-content"); container.dataset.testid = "responses-content";
    container.append(el("p", "muted", `共 ${responses.length} 份成功答卷。匿名答卷不显示填写者账号。`));
    if (!responses.length) container.append(el("p", "inline-empty", "暂时没有答卷。"));
    responses.forEach((response, index) => {
      const details = el("details", "response-details"); details.dataset.testid = `response-${response.id}`;
      const summary = el("summary");
      summary.append(el("strong", "", `答卷 ${index + 1}`), el("span", "response-identity", response.anonymous ? "匿名填写" : (typeof response.username === "string" ? response.username : "未提供账号")), el("span", "response-time", submittedTime(response.submitted_at)));
      details.append(summary, el("p", "muted", `发布版本 ${response.version}`));
      const answers = el("dl", "response-answers");
      for (const id of response.path || []) {
        const question = state.current.questions.find((item) => item.id === id);
        if (!question) continue;
        answers.append(el("dt", "", question.title), el("dd", "", answerText(question, response.answers?.[id])));
      }
      details.append(answers); container.append(details);
    });
    content.append(container);
  }

  $("login-tab").addEventListener("click", () => switchAuth("login"));
  $("register-tab").addEventListener("click", () => switchAuth("register"));
  $("auth-form").addEventListener("submit", (event) => {
    event.preventDefault();
    action($("auth-submit"), async () => {
      if (state.fill?.changed && !window.confirm("登录后将开始新的填写，当前尚未提交的回答会丢弃。继续登录？")) return;
      const body = { username: $("username").value.trim(), password: $("password").value };
      if (state.authMode === "register") await api("/api/auth/register", { method: "POST", body });
      state.user = await api("/api/auth/login", { method: "POST", body });
      $("password").value = "";
      state.current = null;
      state.fill = null; state.results = null;
      state.dirty = false;
      await showSignedIn();
      feedback(state.authMode === "register" ? "账号已创建，登录成功。" : "登录成功。");
    });
  });

  $("logout").addEventListener("click", () => action($("logout"), async () => {
    if (state.dirty && !window.confirm("退出会丢失未保存的修改。继续退出？")) return;
    if (state.fill?.changed && !window.confirm("当前回答尚未提交，退出会丢失这些回答。继续退出？")) return;
    await api("/api/auth/logout", { method: "POST" });
    state.current = null; state.surveys = []; state.dirty = false; state.fill = null; state.results = null;
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
  $("statistics-tab").addEventListener("click", () => action($("statistics-tab"), async () => {
    state.results.mode = "statistics"; renderResultsControls(); await loadResults();
  }));
  $("responses-tab").addEventListener("click", () => action($("responses-tab"), async () => {
    state.results.mode = "responses"; renderResultsControls(); await loadResults();
  }));
  $("statistics-question").addEventListener("change", () => action($("statistics-question"), async () => {
    state.results.questionId = $("statistics-question").value; await loadResults();
  }));
  $("refresh-results").addEventListener("click", () => action($("refresh-results"), loadResults));

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
    if (state.dirty || state.fill?.changed) { event.preventDefault(); event.returnValue = ""; }
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
