export function extractMindmapMarkdown(markdown: string): string {
  const source = (markdown || '').trim()
  if (!source)
    return ''

  const headingRe = /^##\s*思维导图\s*$/gm
  const matches = Array.from(source.matchAll(headingRe))
  if (matches.length === 0)
    return source

  for (const match of matches) {
    if (match.index === undefined)
      continue

    const rest = source.slice(match.index + match[0].length)
    const nextSection = rest.search(/^##\s+/m)
    const sectionBody = nextSection >= 0 ? rest.slice(0, nextSection) : rest
    const hasMindmapNodes = /^(#{3,6}\s+\S+|\s*-\s+\S+)/m.test(sectionBody)

    if (hasMindmapNodes)
      return `# 思维导图${sectionBody}`.trim()
  }

  return source
}
