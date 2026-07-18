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
