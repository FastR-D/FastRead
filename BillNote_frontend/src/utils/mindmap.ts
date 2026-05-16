export function extractMindmapMarkdown(markdown: string): string {
  const source = (markdown || '').trim()
  if (!source)
    return ''

  const match = source.match(/^##\s*思维导图\s*$/m)
  if (!match || match.index === undefined)
    return source

  const sectionStart = match.index
  const rest = source.slice(sectionStart + match[0].length)
  const nextSection = rest.search(/^##\s+/m)
  const sectionBody = nextSection >= 0 ? rest.slice(0, nextSection) : rest
  const section = `# 思维导图${sectionBody}`.trim()

  return section || source
}
