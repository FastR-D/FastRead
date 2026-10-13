const KEY_LIKE_IDENTITY = /^(?:key|fk|apikey)[-_]|@sso\.fastresearch\.local$/i

export function safeIdentityLabel(value: unknown, fallback: string): string {
  const label = String(value ?? '').trim()
  return !label || KEY_LIKE_IDENTITY.test(label) ? fallback : label
}
