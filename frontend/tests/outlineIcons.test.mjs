import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
function sources(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const target = path.join(dir, entry.name)
    return entry.isDirectory() ? sources(target) : /\.(vue|js|css|scss)$/.test(entry.name) ? [target] : []
  })
}

test('every UI icon has an outline SVG, including dynamically selected states', () => {
  const stylesheet = readFileSync(path.join(root, 'src/assets/icons.css'), 'utf8')
  const mapping = new Map([...stylesheet.matchAll(/\.ti-([\w-]+)::before\s*\{\s*mask-image: url\("@tabler\/icons\/outline\/([\w-]+)\.svg"\)/g)]
    .map(match => [match[1], match[2]]))
  for (const file of sources(path.join(root, 'src'))) {
    const source = readFileSync(file, 'utf8')
    assert.doesNotMatch(source, /@tabler\/icons-webfont/, file)
    assert.doesNotMatch(source, /ti-\$\{|['"]ti-['"]\s*\+/, `Use complete icon class names so coverage includes dynamic states: ${file}`)
    for (const [, name] of source.matchAll(/\bti-([a-z0-9]+(?:-[a-z0-9]+)*)/g)) {
      assert.ok(!name.endsWith('-filled'), `Filled icon in ${file}: ${name}`)
      assert.ok(mapping.has(name), `Missing outline SVG in ${file}: ${name}`)
      const svg = readFileSync(path.join(root, 'node_modules/@tabler/icons/icons/outline', `${mapping.get(name)}.svg`), 'utf8')
      assert.match(svg, /fill="none"/)
      assert.match(svg, /stroke="currentColor"/)
    }
  }
})
