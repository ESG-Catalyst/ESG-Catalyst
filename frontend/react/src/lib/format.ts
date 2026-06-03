// Shared display formatters — keep ID / date / label rendering consistent
// across pages instead of re-implementing them per component.

/** Human-friendly absolute date: "3 June 2026". Returns "—" for empty/invalid input. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-GB', { year: 'numeric', month: 'long', day: 'numeric' })
}

/** Title-case a snake_case / lowercase label: "company_admin" → "Company Admin". */
export function humanizeLabel(value: string | null | undefined): string {
  if (!value) return '—'
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

/** Short, human-pasteable reference from a UUID: "a1b2c3d4-e5f6-..." → "a1b2c3d4". */
export function shortRef(id: string | null | undefined): string {
  if (!id) return ''
  return id.split('-')[0] || id.slice(0, 8)
}
