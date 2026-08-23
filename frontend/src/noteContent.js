const INLINE_IMAGE_PATTERN = /\[\[画像(\d+)\]\]/g

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
