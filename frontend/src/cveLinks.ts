import { cvePath } from './route.ts'

// CVE ids in Patch's answers link to their page in the app (B35). A remark plugin over the Markdown tree: only plain
// text is touched, never a link's text (it already goes somewhere) or code. The id pattern is strict, so nothing
// else in the model's text becomes a link.

export interface MdNode {
  type: string
  value?: string
  url?: string
  children?: MdNode[]
}

// A whole id: not part of a longer word or number ("XCVE-…", "…-32489999").
const CVE_IN_TEXT = /(?<![\w-])CVE-\d{4}-\d{4,7}(?![\w-])/gi
const SKIP = new Set(['link', 'linkReference', 'inlineCode', 'code', 'definition'])

function split(value: string): MdNode[] | null {
  const out: MdNode[] = []
  let last = 0
  for (const m of value.matchAll(CVE_IN_TEXT)) {
    if (m.index > last) out.push({ type: 'text', value: value.slice(last, m.index) })
    out.push({ type: 'link', url: cvePath(m[0]), children: [{ type: 'text', value: m[0] }] })
    last = m.index + m[0].length
  }
  if (out.length === 0) return null
  if (last < value.length) out.push({ type: 'text', value: value.slice(last) })
  return out
}

/** Turns each CVE id in the tree's text into a link to its page, in place. */
export function linkCveIds(node: MdNode): void {
  if (!node.children || SKIP.has(node.type)) return
  node.children = node.children.flatMap((child) => {
    if (child.type === 'text' && child.value) return split(child.value) ?? [child]
    linkCveIds(child)
    return [child]
  })
}

/** The remark plugin: `remarkPlugins={[remarkGfm, remarkCveLinks]}`. */
export const remarkCveLinks = () => (tree: MdNode) => linkCveIds(tree)
