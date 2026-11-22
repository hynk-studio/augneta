export const prompts = {
  reach: "중앙에서 출발합니다. 1.6초 안에 더 낮은 추진력으로 닿을 수 있는 관문은 어디인가요?",
  release: "관문에서 표식을 놓습니다. 추진 없이 1.6초 안에 중앙 관측소를 지나는 표식은 어느 쪽에서 출발하나요?",
};
const statuses = {waiting: "대기", held: "직전값 유지", fresh: "갱신", dropout: "수신 누락"};

export function circle(ctx, x, y, r, fill, stroke) {
  ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI);
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = 2; ctx.stroke(); }
}

export function drawMap(canvas, g) {
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, 600, 290);
  const scale = 258;
  const point = ([x, y]) => [300 + x * scale, 140 - y * scale];
  const [lx, ly] = point(g.left), [rx, ry] = point(g.right);
  const steep = Math.abs(ry-ly) > Math.abs(rx-lx);
  const bearing = ly === ry ? "두 관문의 높이가 같습니다." :
    `${ly < ry ? "왼쪽" : "오른쪽"} 관문이 더 위에 있습니다. 기울기는 ${Math.round(Math.atan2(Math.abs(ry-ly), rx-lx) * 180 / Math.PI)}도입니다.`;
  canvas.setAttribute("aria-label", `관측소 양쪽에 같은 거리의 관문이 있습니다. ${bearing}`);
  ctx.beginPath(); ctx.moveTo(lx, ly); ctx.lineTo(rx, ry);
  ctx.strokeStyle = "#c1cec2"; ctx.lineWidth = 2; ctx.stroke();
  for (const [key, label] of [["left", "왼쪽 관문"], ["center", "관측소"], ["right", "오른쪽 관문"]]) {
    const [x, y] = point(g[key]);
    const station = key === "center", radius = g.radius * scale;
    circle(ctx, x, y, radius, station ? "#e0eee8" : "#f3e7db", station ? "#21685e" : "#9c5c34");
    circle(ctx, x, y, 4, station ? "#21685e" : "#9c5c34");
    ctx.fillStyle = "#253e36"; ctx.textAlign = "center"; ctx.font = "23px system-ui";
    if (steep) {
      const left = key === "left";
      ctx.textAlign = left ? "right" : "left";
      ctx.fillText(label, x + (left ? -1 : 1) * (radius + 8), y + 7);
    } else {
      ctx.fillText(label, x, y + radius + 23);
    }
  }
}

export function drawCode(ring, channels) {
  const ctx = ring.getContext("2d");
  ctx.clearRect(0, 0, 180, 180);
  circle(ctx, 90, 90, 60, null, "#c8d6cb");
  channels.forEach((level, slot) => {
    const angle = slot * Math.PI / 4;
    circle(ctx, 90 + 60 * Math.cos(angle), 90 - 60 * Math.sin(angle), 7 + 7 * level,
      level ? `rgba(14,100,85,${.4 + .6 * level})` : "#dbe4d9", null);
  });
  ring.setAttribute("aria-label", channels.map((v, i) => `${i + 1}번 채널 세기 ${v * 4}/4`).join(", "));
}

export function qualityText(s) {
  const age = s.age_steps === null ? "대기" : `${s.age_steps * 50} ms`;
  return `불확실성 ${s.uncertainty_level}/8 · 신호 나이 ${age} · ${statuses[s.sensor_status]} · 누락 ${s.dropped ? "있음" : "없음"}`;
}
