const state = {
  dashboard: null,
  tasks: [],
  agents: [],
  llm: null,
  agentSettings: null,
  configFormDirty: false,
  selectedTaskId: null,
  selectedTask: null,
  selectedTaskPages: [],
  selectedTaskVulns: [],
  selectedTaskMessages: [],
  refreshTimer: null,
};

function inferApiBase() {
  const explicit = window.localStorage.getItem("ctfSolverApiBase");
  if (explicit) {
    return explicit.replace(/\/$/, "");
  }

  const { protocol, hostname, port } = window.location;
  if (port === "5000") {
    return `${protocol}//${hostname}:5000`;
  }
  return `${protocol}//${hostname}:5000`;
}

const API_BASE = inferApiBase();

const elements = {
  statsGrid: document.getElementById("stats-grid"),
  latestTasks: document.getElementById("latest-tasks"),
  latestMessages: document.getElementById("latest-messages"),
  fleetTopology: document.getElementById("fleet-topology"),
  tasksTable: document.getElementById("tasks-table"),
  taskDetailPanel: document.getElementById("task-detail-panel"),
  taskSummary: document.getElementById("task-summary"),
  taskPages: document.getElementById("task-pages"),
  taskVulns: document.getElementById("task-vulns"),
  taskMessages: document.getElementById("task-messages"),
  taskRuntimeOutput: document.getElementById("task-runtime-output"),
  taskExploitChain: document.getElementById("task-exploit-chain"),
  agentGrid: document.getElementById("agent-grid"),
  lastRefreshText: document.getElementById("last-refresh-text"),
  selectedTaskEmpty: document.getElementById("selected-task-empty"),
  selectedTaskMeta: document.getElementById("selected-task-meta"),
  createTaskModal: document.getElementById("create-task-modal"),
  createTaskForm: document.getElementById("create-task-form"),
  taskFormStatus: document.getElementById("task-form-status"),
  agentSelect: document.getElementById("agent-select"),
  llmCurrent: document.getElementById("llm-current"),
  llmStatus: document.getElementById("llm-status"),
  agentNameInput: document.getElementById("agent-name-input"),
  llmProviderSelect: document.getElementById("llm-provider-select"),
  llmProtocolSelect: document.getElementById("llm-protocol-select"),
  llmModelInput: document.getElementById("llm-model-input"),
  llmUrlInput: document.getElementById("llm-url-input"),
  llmKeyInput: document.getElementById("llm-key-input"),
  saveLlmSettings: document.getElementById("save-llm-settings"),
  launchAgentButton: document.getElementById("launch-agent-button"),
  createTaskLlm: document.getElementById("create-task-llm"),
  particleCanvas: document.getElementById("particle-canvas"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatMultiline(value) {
  return escapeHtml(value).replaceAll("\n", "<br>");
}

function isConfigFieldFocused() {
  const activeElement = document.activeElement;
  if (!activeElement) {
    return false;
  }
  return [
    elements.agentNameInput,
    elements.llmProviderSelect,
    elements.llmProtocolSelect,
    elements.llmModelInput,
    elements.llmUrlInput,
    elements.llmKeyInput,
  ].includes(activeElement);
}

function setStatus(target, message, type = "info") {
  if (!target) {
    return;
  }
  if (!message) {
    target.className = "form-status hidden";
    target.textContent = "";
    return;
  }
  target.className = `form-status ${type}`;
  target.textContent = message;
}

async function api(path, options = {}) {
  const requestUrl = `${API_BASE}${path}`;
  const response = await fetch(requestUrl, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok || data?.success === false) {
    throw new Error(data?.message || `Request failed: ${response.status}`);
  }

  return data?.data;
}

function statusClass(status) {
  return String(status || "unknown").toLowerCase();
}

function formatTime(value) {
  if (!value) {
    return "未知时间";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function truncate(value, max = 28) {
  const text = String(value ?? "");
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function collectLlmFormValues() {
  return {
    provider: elements.llmProviderSelect.value,
    protocol: elements.llmProtocolSelect.value,
    model: elements.llmModelInput.value.trim(),
    api_url: elements.llmUrlInput.value.trim(),
    api_key: elements.llmKeyInput.value.trim(),
    temperature: state.llm?.temperature ?? 0.2,
    max_tokens: state.llm?.max_tokens ?? 4096,
    timeout_seconds: state.llm?.timeout_seconds ?? 120,
    response_language: state.llm?.response_language || "zh-CN",
    system_prompt: state.llm?.system_prompt || "",
    summary_template: state.llm?.summary_template || "",
  };
}

function validateLlmPayload(payload) {
  if (!payload.model) {
    throw new Error("Model 为必填项");
  }
  if (!payload.api_key) {
    throw new Error("API Key 为必填项");
  }
  if (Number.isNaN(payload.temperature) || payload.temperature < 0 || payload.temperature > 2) {
    throw new Error("Temperature 必须在 0 到 2 之间");
  }
  if (Number.isNaN(payload.max_tokens) || payload.max_tokens < 512) {
    throw new Error("Max Tokens 不能小于 512");
  }
  if (Number.isNaN(payload.timeout_seconds) || payload.timeout_seconds < 10) {
    throw new Error("Timeout 不能小于 10 秒");
  }
}

async function refreshAgentSettings() {
  state.agentSettings = await api("/api/settings/agent");
  if (!isConfigFieldFocused() && !state.configFormDirty) {
    elements.agentNameInput.value = state.agentSettings?.agent_name || "";
  }
}

function buildFleetTopologySvg(tasks, agents, dashboard) {
  if (!tasks.length && !agents.length) {
    return `<div class="empty-state">暂无拓扑数据</div>`;
  }

  const visibleAgents = agents.slice(0, 5);
  const visibleTasks = tasks.slice(0, 6);
  const vulnCounts = dashboard?.vuln_types || {};
  const vulnEntries = Object.entries(vulnCounts).slice(0, 4);
  const width = 1080;
  const laneX = [110, 430, 760];
  const svgParts = [];

  visibleAgents.forEach((agent, index) => {
    const y = 70 + index * 95;
    svgParts.push(nodeSvg(laneX[0], y, truncate(agent.name, 20), agent.status || "idle", "agent"));
  });

  visibleTasks.forEach((task, index) => {
    const y = 50 + index * 78;
    svgParts.push(nodeSvg(laneX[1], y, truncate(task.target, 24), `${task.status} / ${task.pages_count || 0}p`, "task"));
    const owner = visibleAgents.find((agent) => agent.id === task.agent_id) || visibleAgents[index % Math.max(visibleAgents.length, 1)];
    if (owner) {
      svgParts.push(edgeSvg(laneX[0] + 120, 70 + visibleAgents.indexOf(owner) * 95, laneX[1] - 120, y));
    }
    if (task.flag) {
      svgParts.push(edgeSvg(laneX[1] + 120, y, laneX[2] - 120, 80));
    }
  });

  vulnEntries.forEach(([type, count], index) => {
    const y = 180 + index * 85;
    svgParts.push(nodeSvg(laneX[2], y, truncate(type, 20), `${count} findings`, "vuln"));
    const sourceTask = visibleTasks[index % Math.max(visibleTasks.length, 1)];
    if (sourceTask) {
      svgParts.push(edgeSvg(laneX[1] + 120, 50 + visibleTasks.indexOf(sourceTask) * 78, laneX[2] - 120, y));
    }
  });

  if (visibleTasks.some((task) => task.flag)) {
    svgParts.push(nodeSvg(laneX[2], 80, "FLAG", "captured", "flag"));
  }

  return `<svg class="topology-canvas" viewBox="0 0 ${width} 520" preserveAspectRatio="xMidYMid meet">${svgParts.join("")}</svg>`;
}

function buildTaskTopologySvg(task, pages, vulns) {
  if (!task) {
    return `<div class="empty-state">请选择任务</div>`;
  }

  const width = 1200;
  const svgParts = [];
  const taskNodeY = 70;
  svgParts.push(nodeSvg(170, taskNodeY, truncate(task.target, 28), task.status || "pending", "task"));

  const visiblePages = pages.slice(0, 6);
  visiblePages.forEach((page, index) => {
    const y = 60 + index * 90;
    svgParts.push(nodeSvg(520, y, truncate(page.name, 18), truncate(page.response?.url || "", 22), "page"));
    svgParts.push(edgeSvg(290, taskNodeY, 400, y));
  });

  const visibleVulns = vulns.slice(0, 6);
  visibleVulns.forEach((vuln, index) => {
    const y = 60 + index * 90;
    svgParts.push(nodeSvg(880, y, truncate(vuln.vuln_type || "UNKNOWN", 18), truncate(vuln.description || "", 22), "vuln"));
    const sourcePageY = 60 + (index % Math.max(visiblePages.length, 1)) * 90;
    svgParts.push(edgeSvg(640, sourcePageY, 760, y));
  });

  if (task.flag) {
    svgParts.push(nodeSvg(1080, 80, "FLAG", truncate(task.flag, 18), "flag"));
    svgParts.push(edgeSvg(1000, visibleVulns.length ? 60 : taskNodeY, 960, 80));
  }

  return `<svg class="topology-canvas" viewBox="0 0 ${width} 640" preserveAspectRatio="xMidYMid meet">${svgParts.join("")}</svg>`;
}

function nodeSvg(x, y, title, subtitle, kind) {
  return `
    <g>
      <rect class="topology-node ${escapeHtml(kind)}" x="${x - 110}" y="${y - 24}" rx="18" ry="18" width="220" height="52"></rect>
      <text class="topology-label" x="${x - 94}" y="${y - 3}">${escapeHtml(title)}</text>
      <text class="topology-sub" x="${x - 94}" y="${y + 13}">${escapeHtml(subtitle)}</text>
    </g>
  `;
}

function edgeSvg(x1, y1, x2, y2) {
  const controlX = (x1 + x2) / 2;
  return `<path class="topology-edge" d="M ${x1} ${y1} C ${controlX} ${y1}, ${controlX} ${y2}, ${x2} ${y2}"></path>`;
}

function buildExploitChain(task, vulns, messages) {
  const items = [];
  if (task) {
    items.push({
      kind: "task",
      title: "任务启动",
      content: task.description || task.target,
      time: task.created_at,
    });
  }

  vulns.forEach((vuln) => {
    items.push({
      kind: "vulnerability",
      title: vuln.vuln_type || "UNKNOWN",
      content: vuln.description || "发现漏洞",
      time: vuln.discovered_at,
    });
  });

  messages
    .filter((message) => ["solution", "vulnerability", "summary", "pure", "page"].includes(message.type))
    .forEach((message) => {
      items.push({
        kind: message.type || "message",
        title: truncate(message.type || "message", 18),
        content: message.content,
        time: message.created_at,
      });
    });

  if (task?.flag) {
    items.push({
      kind: "flag",
      title: "Flag Captured",
      content: task.flag,
      time: new Date().toISOString(),
    });
  }

  items.sort((left, right) => String(left.time || "").localeCompare(String(right.time || "")));
  return items;
}

function renderSummaryMetadata(metadata) {
  const sections = metadata?.summary_sections;
  if (!sections) {
    return "";
  }
  return `
    <div class="summary-grid">
      <article class="summary-card">
        <h4>解题思路</h4>
        <div>${formatMultiline(sections.reasoning || "暂无")}</div>
      </article>
      <article class="summary-card">
        <h4>关键步骤</h4>
        <div>${formatMultiline(sections.steps || "暂无")}</div>
      </article>
      <article class="summary-card">
        <h4>代码 / Payload</h4>
        <div class="code-block">${formatMultiline(sections.code || "暂无")}</div>
      </article>
      <article class="summary-card">
        <h4>最终答案</h4>
        <div class="answer-chip">${escapeHtml(sections.answer || "未获取")}</div>
      </article>
      <article class="summary-card span-2">
        <h4>注意事项</h4>
        <div>${formatMultiline(sections.notes || "暂无")}</div>
      </article>
    </div>
  `;
}

function renderMessageItem(message) {
  const metadata = message.metadata || {};
  const summaryContent = message.type === "summary" ? renderSummaryMetadata(metadata) : "";
  return `
    <article class="message-item ${message.type === "summary" ? "summary-message" : ""}">
      <div class="message-meta">${escapeHtml(formatTime(message.created_at))} · ${escapeHtml(message.type || "pure")} · ${escapeHtml(message.status || "")}</div>
      <div>${formatMultiline(message.content)}</div>
      ${summaryContent}
    </article>
  `;
}

function renderOverview() {
  const dashboard = state.dashboard;
  if (!dashboard) {
    return;
  }

  const stats = [
    ["Challenge Queue", dashboard.stats.tasks_total, `${dashboard.stats.tasks_running} active`],
    ["Agents Online", dashboard.stats.agents_online, `${dashboard.stats.agents_total} registered`],
    ["Findings Logged", dashboard.stats.vulns_total, `${dashboard.stats.flags_found} flags secured`],
    ["Fault State", dashboard.stats.tasks_error, "requires triage"],
  ];

  elements.statsGrid.innerHTML = stats.map(([label, value, meta]) => `
    <article class="stat-card">
      <div class="stat-label">${escapeHtml(label)}</div>
      <div class="stat-value">${escapeHtml(value)}</div>
      <div class="stat-meta">${escapeHtml(meta)}</div>
    </article>
  `).join("");

  const latestTasks = dashboard.latest_tasks || [];
  elements.latestTasks.innerHTML = latestTasks.length ? latestTasks.map((task) => `
    <button class="task-row select-task-row" data-task-id="${escapeHtml(task.id)}">
      <div class="task-row-top">
        <strong>${escapeHtml(task.target)}</strong>
        <span class="status ${statusClass(task.status)}">${escapeHtml(task.status)}</span>
      </div>
      <div class="muted">${escapeHtml(task.description || "无描述")}</div>
      <div class="task-row-bottom">
        <span class="code-inline">${escapeHtml(task.id)}</span>
        <span class="muted">${escapeHtml(formatTime(task.created_at))}</span>
      </div>
    </button>
  `).join("") : `<div class="empty-state">暂无任务</div>`;

  const latestMessages = dashboard.latest_messages || [];
  elements.latestMessages.innerHTML = latestMessages.length ? latestMessages.map(renderMessageItem).join("") : `<div class="empty-state">暂无消息</div>`;

  elements.fleetTopology.innerHTML = buildFleetTopologySvg(state.tasks, state.agents, dashboard);
  if (dashboard.llm) {
    state.llm = dashboard.llm;
  }
  renderLlmSettings();
  bindTaskSelectionButtons();
}

function renderLlmSettings() {
  const llm = state.llm || {
    provider: "deepseek",
    protocol: "openai",
    model: "",
    api_url: "",
    api_key: "",
    api_key_masked: "",
    temperature: 0.2,
    max_tokens: 4096,
    timeout_seconds: 120,
    response_language: "zh-CN",
    system_prompt: "",
    summary_template: "",
  };
  const agentName = state.agentSettings?.agent_name || "未设置";

  elements.llmCurrent.innerHTML = `
    Alias: <span class="code-inline">${escapeHtml(agentName)}</span>
    /
    当前: <span class="code-inline">${escapeHtml(llm.provider || "deepseek")}</span>
    /
    <span class="code-inline">${escapeHtml(llm.model || "provider default")}</span>
    /
    <span class="code-inline">${escapeHtml(llm.api_key_masked || "未配置Key")}</span>
  `;
  if (!isConfigFieldFocused() && !state.configFormDirty) {
    elements.llmProviderSelect.value = llm.provider || "deepseek";
    elements.llmProtocolSelect.value = llm.protocol || "openai";
    elements.llmModelInput.value = llm.model || "";
    elements.llmUrlInput.value = llm.api_url || "";
    elements.llmKeyInput.value = llm.api_key || "";
  }
  elements.createTaskLlm.textContent = `${llm.provider || "deepseek"} / ${llm.model || "provider default"}`;
}

async function terminateTask(taskId) {
  if (!taskId) {
    return;
  }
  try {
    await api(`/api/tasks/${taskId}/terminate`, { method: "POST" });
    elements.lastRefreshText.textContent = "任务已发送终止指令";
    await refreshAll();
    if (state.selectedTaskId === taskId) {
      await refreshSelectedTask();
    }
  } catch (error) {
    elements.lastRefreshText.textContent = `终止任务失败: ${error.message}`;
  }
}

async function restartTask(taskId) {
  if (!taskId) {
    return;
  }
  try {
    await api(`/api/tasks/${taskId}/restart`, { method: "POST" });
    elements.lastRefreshText.textContent = "任务已重新排入队列";
    await refreshAll();
    if (state.selectedTaskId === taskId) {
      await refreshSelectedTask();
    }
  } catch (error) {
    elements.lastRefreshText.textContent = `重启任务失败: ${error.message}`;
  }
}

async function deleteTask(taskId) {
  if (!taskId) {
    return;
  }
  try {
    await api(`/api/tasks/${taskId}`, { method: "DELETE" });
    if (state.selectedTaskId === taskId) {
      state.selectedTaskId = null;
      state.selectedTask = null;
      state.selectedTaskPages = [];
      state.selectedTaskVulns = [];
      state.selectedTaskMessages = [];
      renderTaskDetail();
    }
    elements.lastRefreshText.textContent = "任务已删除";
    await refreshAll();
  } catch (error) {
    elements.lastRefreshText.textContent = `删除任务失败: ${error.message}`;
  }
}

function bindTaskActionButtons(container = document) {
  container.querySelectorAll(".terminate-task-button").forEach((button) => {
    button.onclick = async (event) => {
      event.stopPropagation();
      await terminateTask(button.dataset.taskId);
    };
  });
  container.querySelectorAll(".restart-task-button").forEach((button) => {
    button.onclick = async (event) => {
      event.stopPropagation();
      await restartTask(button.dataset.taskId);
    };
  });
  container.querySelectorAll(".delete-task-button").forEach((button) => {
    button.onclick = async (event) => {
      event.stopPropagation();
      await deleteTask(button.dataset.taskId);
    };
  });
}

function renderTasks() {
  const tasks = state.tasks;
  elements.tasksTable.innerHTML = tasks.length ? tasks.map((task) => `
    <article class="task-row">
      <div class="task-row-top">
        <div>
          <strong>${escapeHtml(task.target)}</strong>
          <div class="muted">${escapeHtml(task.description || "无描述")}</div>
        </div>
        <span class="status ${statusClass(task.status)}">${escapeHtml(task.status)}</span>
      </div>
      <div class="task-row-bottom">
        <div class="code-inline">${escapeHtml(task.id)}</div>
        <div class="row-actions">
          <span class="muted">页面 ${escapeHtml(task.pages_count || 0)} / 漏洞 ${escapeHtml(task.vulns_count || 0)}</span>
          <span class="code-inline">${escapeHtml(task.llm_provider || "random")} / ${escapeHtml(task.llm_model || "default")}</span>
          ${task.flag ? `<span class="status finished">FLAG ${escapeHtml(task.flag)}</span>` : ""}
          ${task.status === "running" ? `<button class="ghost-button terminate-task-button" data-task-id="${escapeHtml(task.id)}">终止任务</button>` : ""}
          ${["terminated", "error", "finished"].includes(task.status) ? `<button class="ghost-button restart-task-button" data-task-id="${escapeHtml(task.id)}">重新启动</button>` : ""}
          ${["terminated", "error", "finished", "pending"].includes(task.status) ? `<button class="ghost-button delete-task-button" data-task-id="${escapeHtml(task.id)}">删除任务</button>` : ""}
          <button class="ghost-button select-task-row" data-task-id="${escapeHtml(task.id)}">查看详情</button>
        </div>
      </div>
    </article>
  `).join("") : `<div class="empty-state">暂无任务</div>`;

  bindTaskSelectionButtons();
  bindTaskActionButtons(elements.tasksTable);
}

function renderTaskDetail() {
  if (!state.selectedTask) {
    elements.taskDetailPanel.classList.add("hidden");
    elements.selectedTaskEmpty.classList.remove("hidden");
    elements.selectedTaskMeta.classList.add("hidden");
    return;
  }

  const task = state.selectedTask;
  elements.taskDetailPanel.classList.remove("hidden");
  elements.selectedTaskEmpty.classList.add("hidden");
  elements.selectedTaskMeta.classList.remove("hidden");
  elements.selectedTaskMeta.innerHTML = `
    <div><strong>${escapeHtml(task.target)}</strong></div>
    <div class="muted">${escapeHtml(task.id)}</div>
    <div class="status ${statusClass(task.status)}">${escapeHtml(task.status)}</div>
  `;

  const summary = task.result_summary || {};
  elements.taskSummary.innerHTML = `
    <div class="task-row">
      <div class="task-row-top">
        <strong>${escapeHtml(task.target)}</strong>
        <span class="status ${statusClass(task.status)}">${escapeHtml(task.status)}</span>
      </div>
      <div class="muted">${escapeHtml(task.description || "无描述")}</div>
      <div class="task-row-bottom">
        <span>创建时间: ${escapeHtml(formatTime(task.created_at))}</span>
        <span>Flag: ${escapeHtml(task.flag || "未获取")}</span>
      </div>
      <div class="task-row-bottom">
        <span class="code-inline">${escapeHtml(task.llm_provider || "random")} / ${escapeHtml(task.llm_model || "default")}</span>
        ${task.status === "running" ? `<button class="ghost-button terminate-task-button" data-task-id="${escapeHtml(task.id)}">终止任务</button>` : ""}
        ${["terminated", "error", "finished"].includes(task.status) ? `<button class="ghost-button restart-task-button" data-task-id="${escapeHtml(task.id)}">重新启动</button>` : ""}
        ${["terminated", "error", "finished", "pending"].includes(task.status) ? `<button class="ghost-button delete-task-button" data-task-id="${escapeHtml(task.id)}">删除任务</button>` : ""}
      </div>
    </div>
    ${summary.summary_sections ? renderSummaryMetadata(summary) : ""}
  `;
  bindTaskActionButtons(elements.taskSummary);

  elements.taskPages.innerHTML = state.selectedTaskPages.length ? state.selectedTaskPages.map((page) => {
    const response = page.response || {};
    return `
      <article class="task-row">
        <div class="task-row-top">
          <strong>${escapeHtml(page.name)}</strong>
          <span class="status finished">${escapeHtml(response.status || "N/A")}</span>
        </div>
        <div class="code-inline">${escapeHtml(response.url || "")}</div>
        <div class="muted">${escapeHtml(page.description || page.key || "无额外线索")}</div>
      </article>
    `;
  }).join("") : `<div class="empty-state">暂无页面记录</div>`;

  elements.taskVulns.innerHTML = state.selectedTaskVulns.length ? state.selectedTaskVulns.map((vuln) => `
    <article class="task-row">
      <div class="task-row-top">
        <strong>${escapeHtml(vuln.vuln_type || "UNKNOWN")}</strong>
        <span class="status ${statusClass(vuln.severity || "medium")}">${escapeHtml(vuln.severity || "MEDIUM")}</span>
      </div>
      <div class="muted">${escapeHtml(vuln.description || "无描述")}</div>
      <div class="task-row-bottom">
        <span class="muted">${escapeHtml(formatTime(vuln.discovered_at))}</span>
      </div>
    </article>
  `).join("") : `<div class="empty-state">暂无漏洞</div>`;

  elements.taskMessages.innerHTML = state.selectedTaskMessages.length ? state.selectedTaskMessages.map(renderMessageItem).join("") : `<div class="empty-state">暂无消息</div>`;
  elements.taskRuntimeOutput.innerHTML = state.selectedTaskMessages.length ? `
    <pre class="runtime-pre">${escapeHtml(
      state.selectedTaskMessages
        .map((message) => `[${formatTime(message.created_at)}] ${message.type}/${message.status || "completed"} ${message.content}`)
        .join("\n\n")
    )}</pre>
  ` : `<div class="empty-state">暂无运行输出</div>`;
  const chain = buildExploitChain(task, state.selectedTaskVulns, state.selectedTaskMessages);
  elements.taskExploitChain.innerHTML = chain.length ? chain.map((item) => `
    <article class="chain-step">
      <div class="chain-title">
        <span class="chain-kind">${escapeHtml(item.kind)}</span>
        <span class="muted">${escapeHtml(formatTime(item.time))}</span>
      </div>
      <div><strong>${escapeHtml(item.title)}</strong></div>
      <div class="muted">${escapeHtml(item.content)}</div>
    </article>
  `).join("") : `<div class="empty-state">暂无利用链数据</div>`;
}

function renderAgents() {
  elements.agentGrid.innerHTML = state.agents.length ? state.agents.map((agent) => `
    <article class="agent-card">
      <div class="agent-top">
        <strong>${escapeHtml(agent.metadata?.agent_alias ? `${agent.metadata.agent_alias}(${agent.metadata?.model || "model"})` : agent.name)}</strong>
        <span class="status ${statusClass(agent.status)}">${escapeHtml(agent.status)}</span>
      </div>
      <div class="agent-stack">
        <div class="muted">${escapeHtml(agent.host)}:${escapeHtml(agent.port)}</div>
        <div class="agent-meta">
          <span>任务数 ${escapeHtml(agent.tasks_count || 0)}</span>
          <span>心跳 ${escapeHtml(agent.heartbeat_age_seconds ?? "-")}s</span>
        </div>
        <div class="muted">Provider: <span class="code-inline">${escapeHtml(agent.metadata?.provider || "unknown")}</span></div>
        <div class="muted">Model: <span class="code-inline">${escapeHtml(agent.metadata?.model || "unknown")}</span></div>
        <div class="muted">Protocol: <span class="code-inline">${escapeHtml(agent.metadata?.protocol || "openai")}</span></div>
        <div class="muted">能力: ${escapeHtml(Array.isArray(agent.capabilities) ? agent.capabilities.join(", ") : JSON.stringify(agent.capabilities || {}))}</div>
        <div class="row-actions">
          ${agent.status === "offline" ? `<button class="ghost-button delete-agent-button" data-agent-id="${escapeHtml(agent.id)}">删除离线 Agent</button>` : ""}
        </div>
      </div>
    </article>
  `).join("") : `<div class="empty-state">暂无 Agent</div>`;

  document.querySelectorAll(".delete-agent-button").forEach((button) => {
    button.onclick = async () => {
      const agentId = button.dataset.agentId;
      try {
        await api(`/api/agents/${agentId}`, { method: "DELETE" });
        await refreshAgents();
        await refreshOverview();
      } catch (error) {
        elements.lastRefreshText.textContent = `删除 Agent 失败: ${error.message}`;
      }
    };
  });
}

function onlineAgentCount() {
  return (state.agents || []).filter((agent) => agent.status !== "offline").length;
}

async function persistSettings() {
  const payload = collectLlmFormValues();
  validateLlmPayload(payload);
  const agentName = elements.agentNameInput.value.trim();

  const [llmSettings, agentSettings] = await Promise.all([
    api("/api/settings/llm", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
    api("/api/settings/agent", {
      method: "PUT",
      body: JSON.stringify({ agent_name: agentName }),
    }),
  ]);

  state.llm = llmSettings;
  state.agentSettings = agentSettings;
  state.configFormDirty = false;
  renderLlmSettings();
  await refreshAll();
  await refreshAgentSettings();

  return {
    agentName,
    onlineAgents: onlineAgentCount(),
  };
}

function bindTaskSelectionButtons() {
  document.querySelectorAll(".select-task-row").forEach((button) => {
    button.onclick = async () => {
      const taskId = button.dataset.taskId;
      await selectTask(taskId);
      switchView("tasks");
    };
  });
}

function switchView(viewName) {
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("is-visible", view.id === `${viewName}-view`);
  });
  document.querySelectorAll(".nav-link").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === viewName);
  });
}

async function refreshOverview() {
  state.dashboard = await api("/api/dashboard/overview");
  renderOverview();
}

async function refreshLlmSettings() {
  state.llm = await api("/api/settings/llm");
  renderLlmSettings();
}

async function refreshTasks() {
  state.tasks = await api("/api/tasks?per_page=100");
  renderTasks();
}

async function refreshAgents() {
  const agentStatus = await api("/api/agents/status");
  state.agents = agentStatus.agents || [];
  renderAgents();

  elements.agentSelect.innerHTML = [
    `<option value="">自动分配给可用 Agent</option>`,
    ...state.agents.map((agent) => `<option value="${escapeHtml(agent.id)}">${escapeHtml(agent.name)} (${escapeHtml(agent.status)})</option>`),
  ].join("");
}

async function selectTask(taskId) {
  if (!taskId) {
    return;
  }
  state.selectedTaskId = taskId;
  const [task, pages, vulns, messages] = await Promise.all([
    api(`/api/tasks/${taskId}?include_messages=true`),
    api(`/api/pages/task/${taskId}`),
    api(`/api/vulns/task/${taskId}`),
    api(`/api/messages/task/${taskId}`),
  ]);
  state.selectedTask = task;
  state.selectedTaskPages = pages;
  state.selectedTaskVulns = vulns;
  state.selectedTaskMessages = messages;
  renderTaskDetail();
}

async function refreshSelectedTask() {
  if (!state.selectedTaskId) {
    return;
  }
  await selectTask(state.selectedTaskId);
}

async function refreshAll() {
  try {
    await Promise.all([refreshOverview(), refreshTasks(), refreshAgents(), refreshSelectedTask()]);
    elements.lastRefreshText.textContent = `最近同步: ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    elements.lastRefreshText.textContent = `同步失败: ${error.message}`;
  }
}

async function saveLlmSettings() {
  try {
    setStatus(elements.llmStatus, "正在保存模型配置...", "info");
    elements.saveLlmSettings.disabled = true;
    const { onlineAgents } = await persistSettings();
    setStatus(
      elements.llmStatus,
      onlineAgents
        ? `模型配置与 Agent Alias 已保存到后端。${onlineAgents} 个在线 Agent 会自动同步。`
        : "模型配置与 Agent Alias 已保存到后端。当前没有在线 Agent，请先启动 agent。",
      onlineAgents ? "success" : "info",
    );
  } catch (error) {
    setStatus(elements.llmStatus, `保存失败: ${error.message}`, "error");
  } finally {
    elements.saveLlmSettings.disabled = false;
  }
}

async function launchAgentFromFrontend() {
  try {
    setStatus(elements.llmStatus, "正在保存配置并启动 Agent...", "info");
    elements.launchAgentButton.disabled = true;
    elements.saveLlmSettings.disabled = true;
    const { agentName } = await persistSettings();
    const result = await api("/api/agents/launch", {
      method: "POST",
      body: JSON.stringify({ agent_name: agentName }),
    });
    await new Promise((resolve) => window.setTimeout(resolve, 2500));
    await refreshAll();
    setStatus(
      elements.llmStatus,
      result?.already_running
        ? "同名 Agent 已在运行，配置已保存到后端。"
        : "Agent 启动指令已发送，配置已保存到后端，请等待数秒后出现在 Agent Fleet。",
      "success",
    );
  } catch (error) {
    setStatus(elements.llmStatus, `启动 Agent 失败: ${error.message}`, "error");
  } finally {
    elements.launchAgentButton.disabled = false;
    elements.saveLlmSettings.disabled = false;
  }
}

async function submitTaskForm(event) {
  event.preventDefault();
  const formData = new FormData(elements.createTaskForm);
  const target = String(formData.get("target") || "").trim();
  const description = String(formData.get("description") || "").trim();

  if (!target) {
    setStatus(elements.taskFormStatus, "目标 URL 为必填项。", "error");
    return;
  }
  if (!description) {
    setStatus(elements.taskFormStatus, "题目描述为必填项。", "error");
    return;
  }

  const llmProfile = state.llm || collectLlmFormValues();
  const payload = {
    target,
    description,
    llm_provider: llmProfile.provider || "random",
    llm_model: llmProfile.model || "",
    llm_profile: llmProfile,
  };

  const agentId = String(formData.get("agent_id") || "").trim();
  if (agentId) {
    payload.agent_id = agentId;
  }

  try {
    setStatus(elements.taskFormStatus, "正在提交任务...", "info");
    const submitButton = elements.createTaskForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    await api("/api/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setStatus(elements.taskFormStatus, "任务已成功创建。", "success");
    elements.createTaskForm.reset();
    elements.createTaskModal.close();
    await refreshAll();
    switchView("tasks");
  } catch (error) {
    setStatus(elements.taskFormStatus, `创建任务失败: ${error.message}`, "error");
  } finally {
    elements.createTaskForm.querySelector('button[type="submit"]').disabled = false;
  }
}

function bindEvents() {
  document.querySelectorAll(".nav-link").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });

  document.getElementById("refresh-all").addEventListener("click", refreshAll);
  document.getElementById("open-create-modal").addEventListener("click", () => {
    setStatus(elements.taskFormStatus, "");
    elements.createTaskModal.showModal();
  });
  document.getElementById("close-create-modal").addEventListener("click", () => elements.createTaskModal.close());
  elements.saveLlmSettings.addEventListener("click", saveLlmSettings);
  elements.launchAgentButton.addEventListener("click", launchAgentFromFrontend);
  elements.createTaskForm.addEventListener("submit", submitTaskForm);
  [
    elements.agentNameInput,
    elements.llmProviderSelect,
    elements.llmProtocolSelect,
    elements.llmModelInput,
    elements.llmUrlInput,
    elements.llmKeyInput,
  ].forEach((field) => {
    field?.addEventListener("input", () => {
      state.configFormDirty = true;
    });
    field?.addEventListener("change", () => {
      state.configFormDirty = true;
    });
  });
}

function initParticleCanvas() {
  const canvas = elements.particleCanvas;
  if (!canvas) {
    return;
  }
  const ctx = canvas.getContext("2d");
  const particles = [];
  const particleCount = 48;

  function resize() {
    canvas.width = window.innerWidth * window.devicePixelRatio;
    canvas.height = window.innerHeight * window.devicePixelRatio;
    canvas.style.width = `${window.innerWidth}px`;
    canvas.style.height = `${window.innerHeight}px`;
    ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
  }

  function createParticle() {
    return {
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      r: Math.random() * 2.4 + 0.8,
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.35,
    };
  }

  function seed() {
    particles.length = 0;
    for (let index = 0; index < particleCount; index += 1) {
      particles.push(createParticle());
    }
  }

  function draw() {
    ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);
    particles.forEach((particle, index) => {
      particle.x += particle.vx;
      particle.y += particle.vy;

      if (particle.x < -20 || particle.x > window.innerWidth + 20 || particle.y < -20 || particle.y > window.innerHeight + 20) {
        particles[index] = createParticle();
        particles[index].x = Math.random() > 0.5 ? 0 : window.innerWidth;
      }

      ctx.beginPath();
      ctx.fillStyle = "rgba(108, 247, 255, 0.75)";
      ctx.shadowBlur = 12;
      ctx.shadowColor = "rgba(108, 247, 255, 0.65)";
      ctx.arc(particle.x, particle.y, particle.r, 0, Math.PI * 2);
      ctx.fill();

      for (let next = index + 1; next < particles.length; next += 1) {
        const other = particles[next];
        const distance = Math.hypot(particle.x - other.x, particle.y - other.y);
        if (distance < 140) {
          ctx.beginPath();
          ctx.strokeStyle = `rgba(126, 255, 199, ${0.12 - distance / 1400})`;
          ctx.lineWidth = 1;
          ctx.moveTo(particle.x, particle.y);
          ctx.lineTo(other.x, other.y);
          ctx.stroke();
        }
      }
    });
    requestAnimationFrame(draw);
  }

  resize();
  seed();
  draw();
  window.addEventListener("resize", () => {
    resize();
    seed();
  });
}

async function boot() {
  bindEvents();
  initParticleCanvas();
  switchView("overview");
  await refreshAgentSettings();
  await refreshLlmSettings();
  await refreshAll();
  state.refreshTimer = window.setInterval(refreshAll, 5000);
}

boot();
