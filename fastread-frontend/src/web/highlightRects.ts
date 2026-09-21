export type HighlightRect = { x: number; y: number; width: number; height: number }

// Browser ranges can return both a span box and its text box. Merge only
// touching fragments on the same line; preserve gaps between PDF columns.
export function mergeHighlightRects(rects: HighlightRect[]): HighlightRect[] {
  const lines: HighlightRect[] = []
  for (const rect of rects.filter(r => [r.x, r.y, r.width, r.height].every(Number.isFinite) && r.width > 0 && r.height > 0).sort((a, b) => a.y - b.y || a.x - b.x)) {
    const merged = { ...rect }
    for (let i = 0; i < lines.length;) {
      const other = lines[i]
      const height = Math.min(merged.height, other.height)
      const sameLine = Math.abs(merged.y + merged.height / 2 - other.y - other.height / 2) <= height * 0.25
      const touching = merged.x <= other.x + other.width + 0.001 && other.x <= merged.x + merged.width + 0.001
      if (sameLine && touching) {
        const right = Math.max(merged.x + merged.width, other.x + other.width)
        const bottom = Math.max(merged.y + merged.height, other.y + other.height)
        merged.x = Math.min(merged.x, other.x); merged.y = Math.min(merged.y, other.y)
        merged.width = right - merged.x; merged.height = bottom - merged.y
        lines.splice(i, 1)
        i = 0
      } else i++
    }
    lines.push(merged)
  }
  return lines.sort((a, b) => a.y - b.y || a.x - b.x)
}
