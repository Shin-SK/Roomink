import DOMPurify from 'dompurify'

const INLINE_IMAGE_PATTERN = /\[\[画像(\d+)\]\]/g
const RICH_TEXT_PATTERN = /<(?:p|br|h[1-6]|strong|b|em|i|u|s|ul|ol|li|blockquote|a|img|hr|pre|code)\b/i

const NOTE_HTML_CONFIG = {
  ALLOWED_TAGS: [
    'p', 'br', 'h2', 'h3', 'strong', 'b', 'em', 'i', 'u', 's',
    'ul', 'ol', 'li', 'blockquote', 'a', 'img', 'hr', 'pre', 'code',
  ],
  ALLOWED_ATTR: ['href', 'target', 'rel', 'src', 'alt', 'title'],
  ALLOW_DATA_ATTR: false,
}

function escapeHtml(value = '') {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function plainTextToHtml(value = '') {
  const normalized = String(value).replaceAll('\r\n', '\n').trim()
  if (!normalized) return ''
  return normalized
    .split(/\n{2,}/)
    .map(paragraph => `<p>${escapeHtml(paragraph).replaceAll('\n', '<br>')}</p>`)
    .join('')
}

export function inlineImageMarker(index) {
  return `[[画像${index + 1}]]`
}

export function parseNoteContent(body = '', imageUrls = []) {
  const content = String(body)
  const blocks = []
  let cursor = 0

  for (const match of content.matchAll(INLINE_IMAGE_PATTERN)) {
    if (match.index > cursor) {
      blocks.push({ type: 'text', text: content.slice(cursor, match.index) })
    }

    const imageIndex = Number(match[1]) - 1
    const url = imageUrls[imageIndex]
    if (url) {
      blocks.push({ type: 'image', url, imageIndex })
    } else {
      blocks.push({ type: 'text', text: match[0] })
    }
    cursor = match.index + match[0].length
  }

  if (cursor < content.length) {
    blocks.push({ type: 'text', text: content.slice(cursor) })
  }
  return blocks.filter(block => block.type !== 'text' || block.text)
}

export function trailingNoteImages(body = '', imageUrls = []) {
  const inlineIndexes = new Set(
    parseNoteContent(body, imageUrls)
      .filter(block => block.type === 'image')
      .map(block => block.imageIndex),
  )
  return imageUrls
    .map((url, imageIndex) => ({ url, imageIndex }))
    .filter(image => !inlineIndexes.has(image.imageIndex))
}

export function removeInlineImage(body = '', removedIndex) {
  return String(body).replace(INLINE_IMAGE_PATTERN, (marker, number) => {
    const imageIndex = Number(number) - 1
    if (imageIndex === removedIndex) return ''
    if (imageIndex > removedIndex) return inlineImageMarker(imageIndex - 1)
    return marker
  })
}

export function isRichNoteBody(body = '') {
  return RICH_TEXT_PATTERN.test(String(body))
}

/**
 * 旧形式（プレーンテキスト + [[画像N]]）を、Tiptapで編集できるHTMLへ変換する。
 * すでにHTMLの本文はそのまま返し、保存済み記事との後方互換を維持する。
 */
export function noteBodyToHtml(body = '', imageUrls = []) {
  if (isRichNoteBody(body)) return String(body)

  const blocks = parseNoteContent(body, imageUrls)
  const html = blocks.map(block => {
    if (block.type === 'image') {
      return `<img src="${escapeHtml(block.url)}" alt="ノート画像 ${block.imageIndex + 1}">`
    }
    return plainTextToHtml(block.text)
  })

  for (const image of trailingNoteImages(body, imageUrls)) {
    html.push(`<img src="${escapeHtml(image.url)}" alt="ノート画像 ${image.imageIndex + 1}">`)
  }
  return html.join('')
}

/** v-html へ渡す直前に、ノートで使う最小限のタグ・属性だけへ制限する。 */
export function sanitizeNoteHtml(body = '', imageUrls = []) {
  const clean = DOMPurify.sanitize(noteBodyToHtml(body, imageUrls), NOTE_HTML_CONFIG)
  const template = document.createElement('template')
  template.innerHTML = clean
  template.content.querySelectorAll('a').forEach(link => {
    link.setAttribute('target', '_blank')
    link.setAttribute('rel', 'noopener noreferrer')
  })
  return template.innerHTML
}

export function extractNoteImageUrls(html = '') {
  const template = document.createElement('template')
  template.innerHTML = DOMPurify.sanitize(String(html), NOTE_HTML_CONFIG)
  return Array.from(template.content.querySelectorAll('img[src]'))
    .map(image => image.getAttribute('src'))
    .filter((url, index, urls) => url && urls.indexOf(url) === index)
}
