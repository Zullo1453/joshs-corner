(() => {
  const monthLabel = (value, includeYear) => new Intl.DateTimeFormat(undefined, {
    month: "short", ...(includeYear ? { year: "2-digit" } : {}), timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
  const tooltipText = (point, base, quote) => {
    const formattedDate = new Intl.DateTimeFormat(undefined, {
      day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
    }).format(new Date(`${point.date}T00:00:00Z`));
    return `${formattedDate}\n1 ${base} = ${point.rate} ${quote}`;
  };
  const axisLabels = (points, maximum = 7) => {
    if (!points.length) return [];
    const firstYear = points[0].date.slice(0, 4);
    const lastYear = points.at(-1).date.slice(0, 4);
    const candidates = points.filter((point, index) => {
      const previous = points[index - 1];
      return index === 0 || point.date.slice(0, 7) !== previous.date.slice(0, 7);
    });
    const finalPoint = points.at(-1);
    if (finalPoint.date.slice(0, 7) !== candidates.at(-1).date.slice(0, 7)) candidates.push(finalPoint);
    const stride = Math.max(1, Math.ceil(candidates.length / maximum));
    return candidates.filter((_, index) => index % stride === 0 || index === candidates.length - 1).map((point) => ({
      ...point,
      label: monthLabel(point.date, point.date.slice(0, 4) !== firstYear || point.date.slice(0, 4) !== lastYear),
    }));
  };

  window.JoshsCornerCurrencyChart = { axisLabels, tooltipText };

  document.querySelectorAll(".currency-chart").forEach((canvas) => {
    let points;
    try { points = JSON.parse(canvas.dataset.points || "[]"); } catch (_) { return; }
    if (!Array.isArray(points) || points.length < 2) return;
    const wrap = canvas.closest(".currency-chart-wrap");
    const tooltip = wrap?.querySelector("[data-chart-tooltip]");
    const base = canvas.dataset.base || "";
    const quote = canvas.dataset.quote || "";
    let geometry;

    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const scale = window.devicePixelRatio || 1;
      const width = Math.max(260, Math.round(rect.width));
      const height = Math.max(190, Math.round(rect.height));
      canvas.width = width * scale;
      canvas.height = height * scale;
      const ctx = canvas.getContext("2d");
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      const values = points.map((point) => Number(point.rate));
      const min = Math.min(...values);
      const max = Math.max(...values);
      const span = max - min || 1;
      const padding = { top: 16, right: 16, bottom: 31, left: 16 };
      const graphWidth = width - padding.left - padding.right;
      const graphHeight = height - padding.top - padding.bottom;
      const positionFor = (point, index) => ({
        x: padding.left + index * graphWidth / (points.length - 1),
        y: padding.top + (max - Number(point.rate)) * graphHeight / span,
      });
      geometry = { width, height, padding, positionFor };

      ctx.strokeStyle = "#314746";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(padding.left, height - padding.bottom);
      ctx.lineTo(width - padding.right, height - padding.bottom);
      ctx.stroke();
      ctx.font = "11px system-ui, sans-serif";
      ctx.fillStyle = "#91a5a3";
      ctx.textAlign = "center";
      axisLabels(points, width < 420 ? 4 : 7).forEach((label) => {
        const index = points.findIndex((point) => point.date === label.date);
        const { x } = positionFor(label, index);
        ctx.fillText(label.label, x, height - 10);
      });
      ctx.strokeStyle = "#86bbb4";
      ctx.lineWidth = 2;
      ctx.beginPath();
      points.forEach((point, index) => {
        const { x, y } = positionFor(point, index);
        if (index) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      });
      ctx.stroke();
    };

    const showPoint = (clientX) => {
      if (!geometry || !tooltip) return;
      const rect = canvas.getBoundingClientRect();
      const relativeX = Math.max(geometry.padding.left, Math.min(rect.width - geometry.padding.right, clientX - rect.left));
      const index = Math.round((relativeX - geometry.padding.left) / (rect.width - geometry.padding.left - geometry.padding.right) * (points.length - 1));
      const safeIndex = Math.max(0, Math.min(points.length - 1, index));
      const point = points[safeIndex];
      const { x, y } = geometry.positionFor(point, safeIndex);
      tooltip.textContent = tooltipText(point, base, quote);
      tooltip.hidden = false;
      tooltip.style.left = `${Math.max(8, Math.min(rect.width - tooltip.offsetWidth - 8, x + 8))}px`;
      tooltip.style.top = `${Math.max(8, y - tooltip.offsetHeight - 8)}px`;
    };

    canvas.addEventListener("pointermove", (event) => showPoint(event.clientX));
    canvas.addEventListener("pointerdown", (event) => showPoint(event.clientX));
    canvas.addEventListener("pointerleave", () => { if (tooltip) tooltip.hidden = true; });
    new ResizeObserver(draw).observe(canvas);
    draw();
  });
})();
