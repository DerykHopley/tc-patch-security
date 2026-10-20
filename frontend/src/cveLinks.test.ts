// CVE ids in Patch's answers link to their page (B35, #85). Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { linkCveIds, type MdNode } from './cveLinks.ts'

const text = (value: string): MdNode => ({ type: 'text', value })
const para = (...children: MdNode[]): MdNode => ({ type: 'root', children: [{ type: 'paragraph', children }] })
const link = (url: string, ...children: MdNode[]): MdNode => ({ type: 'link', url, children })

test('B35.9 a CVE id in an answer becomes a link to its page', () => {
  const tree = para(text('Fix CVE-2025-3248 first, then cve-2024-8309.'))
  linkCveIds(tree)
  assert.deepEqual(tree, para(
    text('Fix '),
    link('/cves/CVE-2025-3248', text('CVE-2025-3248')),
    text(' first, then '),
    link('/cves/CVE-2024-8309', text('cve-2024-8309')),
    text('.'),
  ))
})

test('B35.9 ids already in a link, in code, or in a longer word stay as they are', () => {
  const inLink = para(link('https://nvd.nist.gov/vuln/detail/CVE-2025-3248', text('CVE-2025-3248')))
  const before = structuredClone(inLink)
  linkCveIds(inLink)
  assert.deepEqual(inLink, before)

  const code = para({ type: 'inlineCode', value: 'CVE-2025-3248' })
  const codeBefore = structuredClone(code)
  linkCveIds(code)
  assert.deepEqual(code, codeBefore)

  const word = para(text('XCVE-2025-3248 and CVE-2025-32489999'))
  const wordBefore = structuredClone(word)
  linkCveIds(word)
  assert.deepEqual(word, wordBefore)
})

test('B35.9 ids inside bold or a list item are linked too', () => {
  const tree: MdNode = { type: 'root', children: [{ type: 'strong', children: [text('CVE-2025-3248')] }] }
  linkCveIds(tree)
  assert.deepEqual(tree, { type: 'root', children: [{ type: 'strong', children: [
    link('/cves/CVE-2025-3248', text('CVE-2025-3248')),
  ] }] })
})
