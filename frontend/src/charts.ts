export function conicGradient(percentages: number[], colors: string[]): string {
  let start = 0;
  return percentages
    .map((percent, index) => {
      const end = start + percent;
      const stop = `${colors[index % colors.length]} ${start}% ${end}%`;
      start = end;
      return stop;
    })
    .join(", ");
}

export function donutArcPaths(percentages: number[], outer = 48, inner = 28): string[] {
  let angle = -Math.PI / 2;
  return percentages.map((percent) => {
    const next = angle + (Math.PI * 2 * percent) / 100;
    const point = (radius: number, value: number) => `${50 + radius * Math.cos(value)} ${50 + radius * Math.sin(value)}`;
    const large = next - angle > Math.PI ? 1 : 0;
    const path = `M ${point(outer, angle)} A ${outer} ${outer} 0 ${large} 1 ${point(outer, next)} L ${point(inner, next)} A ${inner} ${inner} 0 ${large} 0 ${point(inner, angle)} Z`;
    angle = next;
    return path;
  });
}
