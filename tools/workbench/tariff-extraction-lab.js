(() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
  const stages = [
    ["queued", "排队", "任务已创建"],
    ["downloading", "下载源文件", "读取公开 PDF"],
    ["inspecting", "检查 PDF", "页数与文本层"],
    ["extracting", "提取目录", "逐页识别税则号"],
    ["normalizing", "整理多层类目", "章节至 8 位税号"],
    ["validating", "校验", "重复与层级"],
    ["writing", "生成候选包", "JSONL 与清单"],
    ["completed", "完成", "等待审核发布"]
  ];
  const state = {jobId: "", timer: null, samples: []};

  const formatBytes = value => {
    const bytes = Number(value || 0);
    if (!bytes) return "0 MB";
    if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
    return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  };
  const formatSeconds = value => {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds < 0) return "—";
    if (seconds < 60) return `${Math.round(seconds)}s`;
    return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  };
  const percent = value => `${Math.max(0, Math.min(100, Number(value || 0) * 100)).toFixed(1).replace(/\.0$/, "")}%`;

  function setActionMessage(message, error = false) {
    $("action-message").textContent = message;
    $("action-message").style.color = error ? "#c95353" : "";
  }

  function renderStages(job) {
    const current = stages.findIndex(([id]) => id === job.stage);
    const container = $("stages");
    container.innerHTML = stages.map(([id, label, hint], index) => {
      let cls = "";
      if (job.status === "failed" && index === current) cls = "failed";
      else if ((job.status === "running" || job.status === "queued") && index === current) cls = "current";
      else if ((job.status === "completed" || job.status === "cancelled") && index < stages.length - 1) cls = "done";
      else if (job.status === "running" && index < current) cls = "done";
      return `<div class="stage ${cls}"><b>${index + 1}</b><div><strong>${label}</strong><small>${hint}</small></div></div>`;
    }).join("");
  }

  function renderNodes(nodes) {
    const target = $("recent-nodes");
    if (!nodes || !nodes.length) {
      target.innerHTML = `<tr><td colspan="5" class="empty">任务开始后显示最近识别的目录节点</td></tr>`;
      return;
    }
    target.innerHTML = nodes.slice(-8).reverse().map(node => `<tr>
      <td>${esc(node.code)}</td><td>${esc(node.name)}</td><td>L${esc(node.level)}</td><td>${esc(node.page || "—")}</td><td>${node.kind === "sku" ? "8 位税号" : "上级类目"}</td>
    </tr>`).join("");
  }

  function renderLogs(logs) {
    $("logs").innerHTML = (logs && logs.length ? logs : ["等待任务创建"]).slice().reverse().map(log => `<li>${esc(log)}</li>`).join("");
  }

  function drawChart() {
    const canvas = $("throughput");
    const ctx = canvas.getContext("2d");
    const width = canvas.clientWidth || 560;
    const height = 190;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    ctx.scale(ratio, ratio);
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = "#edf2f1";
    ctx.lineWidth = 1;
    [35, 80, 125, 170].forEach(y => { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); });
    const values = state.samples.length ? state.samples : [0];
    const max = Math.max(1, ...values);
    const points = values.map((value, index) => [
      values.length === 1 ? width / 2 : index * width / (values.length - 1),
      170 - (Number(value || 0) / max) * 135,
    ]);
    const gradient = ctx.createLinearGradient(0, 25, 0, 170);
    gradient.addColorStop(0, "rgba(9,135,125,.26)");
    gradient.addColorStop(1, "rgba(9,135,125,0)");
    ctx.beginPath();
    points.forEach(([x, y], index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
    ctx.lineTo(points[points.length - 1][0], 170);
    ctx.lineTo(points[0][0], 170);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();
    ctx.beginPath();
    points.forEach(([x, y], index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
    ctx.strokeStyle = "#09877d";
    ctx.lineWidth = 2.5;
    ctx.stroke();
    const last = values[values.length - 1];
    $("chart-last").textContent = last ? `${Number(last).toFixed(2)} 页/秒` : "等待数据";
  }

  function render(job) {
    const progress = Number(job.overall_progress || 0);
    const stageText = job.stage_label || "等待启动";
    $("progress-ring").style.setProperty("--progress", `${progress * 360}deg`);
    $("progress-value").textContent = percent(progress);
    $("progress-stage").textContent = stageText;
    $("progress-bar").style.width = `${progress * 100}%`;
    $("progress-message").textContent = job.message || "等待后台任务";
    $("elapsed").textContent = formatSeconds(job.elapsed_seconds);
    $("eta").textContent = job.status === "completed" ? "完成" : formatSeconds(job.eta_seconds);
    $("speed").textContent = job.pages_per_second ? `${Number(job.pages_per_second).toFixed(2)} 页/s` : "—";
    $("job-id").textContent = job.job_id ? `JOB ${job.job_id.slice(0, 10)}` : "未创建任务";
    $("source-status").textContent = job.status === "running" ? "处理中" : job.status === "completed" ? "已完成" : job.status === "failed" ? "失败" : job.status === "cancelled" ? "已停止" : "已排队";
    $("source-status").className = `pill ${job.status === "running" ? "running" : job.status === "completed" ? "complete" : job.status === "failed" ? "error" : "neutral"}`;
    $("downloaded").textContent = formatBytes(job.downloaded_bytes);
    $("download-total").textContent = job.total_bytes ? `总量 ${formatBytes(job.total_bytes)}` : "总量待确认";
    $("pages").textContent = `${Number(job.pages_processed || 0)} / ${job.page_count || 1492}`;
    $("nodes").textContent = Number(job.nodes_found || 0).toLocaleString("zh-CN");
    $("leaf-codes").textContent = Number(job.leaf_codes_found || 0).toLocaleString("zh-CN");
    $("issues").textContent = Number(job.issues_found || 0).toLocaleString("zh-CN");
    $("output-status").textContent = job.output_files && job.output_files.length ? `已生成 ${job.output_files.length} 个文件` : "尚未生成候选包";
    renderStages(job);
    renderNodes(job.recent_nodes || []);
    renderLogs(job.recent_logs || []);
    if (job.pages_per_second) {
      state.samples.push(Number(job.pages_per_second));
      state.samples = state.samples.slice(-32);
      drawChart();
    }
    $("cancel").disabled = !job.can_cancel;
    $("start").disabled = job.status === "running" || job.status === "queued";
    if (job.status === "completed") setActionMessage("候选包已生成，可进入下一步人工审核");
    if (job.status === "failed") setActionMessage(job.error || job.message || "任务失败", true);
    if (job.status === "cancelled") setActionMessage("任务已安全停止；未写入 ERPNext");
  }

  async function poll() {
    if (!state.jobId) return;
    try {
      const response = await fetch(`/api/tariff-extraction/job?job_id=${encodeURIComponent(state.jobId)}`, {cache: "no-store"});
      const body = await response.json();
      if (!body.ok) throw new Error(body.error || "读取任务状态失败");
      render(body.job);
      if (["completed", "failed", "cancelled"].includes(body.job.status)) {
        clearInterval(state.timer);
        state.timer = null;
      }
    } catch (error) {
      setActionMessage(error.message || "网络读取失败", true);
    }
  }

  async function start() {
    const mode = $("mode").value;
    const confirmed = $("confirm-full").checked;
    if (mode === "full" && !confirmed) {
      setActionMessage("全量模式必须先勾选明确确认", true);
      return;
    }
    $("start").disabled = true;
    setActionMessage(mode === "demo" ? "正在创建演示任务…" : "正在创建全量任务…");
    try {
      const response = await fetch("/api/tariff-extraction/jobs", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({mode, confirmed, source_url: $("source-url").value}),
      });
      const body = await response.json();
      if (!body.ok) throw new Error(body.error || "任务创建失败");
      state.jobId = body.job.job_id;
      state.samples = [];
      render(body.job);
      clearInterval(state.timer);
      state.timer = setInterval(poll, 700);
      await poll();
    } catch (error) {
      $("start").disabled = false;
      setActionMessage(error.message || "任务创建失败", true);
    }
  }

  async function cancel() {
    if (!state.jobId) return;
    $("cancel").disabled = true;
    try {
      const response = await fetch("/api/tariff-extraction/jobs/cancel", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({job_id: state.jobId}),
      });
      const body = await response.json();
      if (!body.ok) throw new Error(body.error || "停止失败");
      render(body.job);
      await poll();
    } catch (error) { setActionMessage(error.message || "停止失败", true); }
  }

  $("mode").addEventListener("change", event => {
    const full = event.target.value === "full";
    $("confirm-full").disabled = !full;
    $("start").textContent = full ? "启动全量任务" : "启动演示任务";
    setActionMessage(full ? "勾选确认后才会访问公开 PDF" : "演示模式不会访问网络");
  });
  $("confirm-full").disabled = true;
  $("start").addEventListener("click", start);
  $("cancel").addEventListener("click", cancel);
  window.addEventListener("resize", drawChart);
  renderStages({stage: "queued", status: "queued"});
  drawChart();
})();
