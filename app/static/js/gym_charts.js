(() => {
  const number = value => new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
  const label = value => new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(`${value}T12:00:00`));
  function chart(element) {
    const points = JSON.parse(element.dataset.points || '[]');
    const metric = element.dataset.metric;
    if (!points.length) return;
    const width = Math.max(280, element.clientWidth || 600), height = 230, pad = { left: 48, right: 18, top: 20, bottom: 42 };
    const values = points.map(point => point[metric]), max = Math.max(...values, 1), min = Math.min(...values, 0);
    const x = index => points.length === 1 ? width / 2 : pad.left + index * ((width - pad.left - pad.right) / (points.length - 1));
    const y = value => pad.top + (max === min ? .5 : 1 - ((value - min) / (max - min))) * (height - pad.top - pad.bottom);
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('viewBox', `0 0 ${width} ${height}`); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', metric === 'volume' ? 'Session volume chart' : 'Maximum weight chart');
    const grid = document.createElementNS(svg.namespaceURI, 'path'); grid.setAttribute('d', `M ${pad.left} ${pad.top} V ${height-pad.bottom} H ${width-pad.right}`); grid.setAttribute('stroke', '#795e4b'); grid.setAttribute('fill', 'none'); svg.append(grid);
    const line = document.createElementNS(svg.namespaceURI, 'polyline'); line.setAttribute('points', points.map((point, index) => `${x(index)},${y(point[metric])}`).join(' ')); line.setAttribute('fill', 'none'); line.setAttribute('stroke', '#e4a36d'); line.setAttribute('stroke-width', '2.5'); svg.append(line);
    const detail = document.createElement('p'); detail.className = 'gym-chart-detail'; detail.setAttribute('aria-live', 'polite');
    const show = point => { detail.innerHTML = `<strong>${label(point.date)}</strong>Max weight: ${number(point.max_weight)} kg · Volume: ${number(point.volume)} kg<br>${point.sets.join(' · ')}`; };
    points.forEach((point, index) => { const circle = document.createElementNS(svg.namespaceURI, 'circle'); circle.setAttribute('cx', x(index)); circle.setAttribute('cy', y(point[metric])); circle.setAttribute('r', '6'); circle.setAttribute('fill', '#f5d1b0'); circle.setAttribute('stroke', '#8e5938'); circle.setAttribute('tabindex', '0'); circle.setAttribute('role', 'button'); circle.setAttribute('aria-label', `${label(point.date)}: ${number(point[metric])} kg`); ['mouseenter','focus','click'].forEach(event => circle.addEventListener(event, () => show(point))); svg.append(circle); });
    const shown = Math.min(points.length, 4); for (let index = 0; index < shown; index++) { const pointIndex = shown === 1 ? 0 : Math.round(index * (points.length - 1) / (shown - 1)); const text = document.createElementNS(svg.namespaceURI, 'text'); text.setAttribute('x', x(pointIndex)); text.setAttribute('y', height - 14); text.setAttribute('fill', '#c8ada0'); text.setAttribute('font-size', '11'); text.setAttribute('text-anchor', 'middle'); text.textContent = label(points[pointIndex].date).replace(/ \d{4}$/, ''); svg.append(text); }
    element.replaceChildren(svg, detail); show(points.at(-1));
  }
  document.querySelectorAll('.gym-chart').forEach(chart);
})();
