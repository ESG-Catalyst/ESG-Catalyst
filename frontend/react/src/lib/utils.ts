import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Merge Tailwind classes safely (clsx + tailwind-merge). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Tiny CVA-style variant helper.
 * Returns a function that maps variant keys to class strings and merges extras.
 *
 * Usage:
 *   const pill = variants({
 *     base: 'inline-flex items-center rounded-full text-xs font-medium',
 *     variants: { color: { teal: 'bg-primary/10 text-primary', red: 'bg-danger/10 text-danger' } },
 *     defaultVariants: { color: 'teal' },
 *   })
 *   pill({ color: 'red', className: 'px-2' })
 */
type VariantMap = Record<string, Record<string, string>>
type VariantConfig<V extends VariantMap> = {
  base?: string
  variants: V
  defaultVariants?: { [K in keyof V]?: keyof V[K] }
}
type VariantProps<V extends VariantMap> = {
  [K in keyof V]?: keyof V[K]
} & { className?: string }

export function variants<V extends VariantMap>(config: VariantConfig<V>) {
  return (props?: VariantProps<V>): string => {
    const applied: string[] = config.base ? [config.base] : []
    for (const key in config.variants) {
      const value =
        (props?.[key] as string | undefined) ??
        (config.defaultVariants?.[key] as string | undefined)
      if (value !== undefined) {
        const cls = config.variants[key][value as string]
        if (cls) applied.push(cls)
      }
    }
    if (props?.className) applied.push(props.className)
    return twMerge(clsx(applied))
  }
}
