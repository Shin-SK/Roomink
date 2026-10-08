const UNAMBIGUOUS_PASSWORD_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'

export function generateTemporaryPassword(length = 12) {
  const result = []
  const acceptedRange = 256 - (256 % UNAMBIGUOUS_PASSWORD_CHARS.length)
  while (result.length < length) {
    const bytes = crypto.getRandomValues(new Uint8Array(length * 2))
    for (const value of bytes) {
      if (value >= acceptedRange) continue
      result.push(UNAMBIGUOUS_PASSWORD_CHARS[value % UNAMBIGUOUS_PASSWORD_CHARS.length])
      if (result.length === length) break
    }
  }
  return result.join('')
}
