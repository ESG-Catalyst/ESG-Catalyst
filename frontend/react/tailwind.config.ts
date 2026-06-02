import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg:              'var(--color-bg)',
        surface:         'var(--color-surface)',
        'surface-raised':'var(--color-surface-raised)',
        border:          'var(--color-border)',
        'border-subtle': 'var(--color-border-subtle)',
        primary: {
          DEFAULT: 'var(--color-primary)',
          hover:   'var(--color-primary-hover)',
          subtle:  'var(--color-primary-subtle)',
        },
        text: {
          DEFAULT: 'var(--color-text)',
          muted:   'var(--color-text-muted)',
          subtle:  'var(--color-text-subtle)',
        },
        success:         'var(--color-success)',
        'success-subtle':'var(--color-success-subtle)',
        warning:         'var(--color-warning)',
        'warning-subtle':'var(--color-warning-subtle)',
        danger:          'var(--color-danger)',
        'danger-subtle': 'var(--color-danger-subtle)',
        info:            'var(--color-info)',
        'info-subtle':   'var(--color-info-subtle)',

        /* 5-colour chart palette — for recharts <Cell fill="…"> */
        chart: {
          1: 'var(--chart-1)',
          2: 'var(--chart-2)',
          3: 'var(--chart-3)',
          4: 'var(--chart-4)',
          5: 'var(--chart-5)',
        },
      },

      fontFamily: {
        sans:    ['var(--font-sans)'],
        arabic:  ['var(--font-arabic)'],
        mono:    ['var(--font-mono)'],
      },

      borderRadius: {
        DEFAULT: 'var(--radius)',
        lg:      'var(--radius-lg)',
        xl:      'var(--radius-xl)',
      },

      /* Elevation shadows — use shadow-card, shadow-panel etc. via boxShadow */
      boxShadow: {
        xs:    'var(--shadow-xs)',
        sm:    'var(--shadow-sm)',
        card:  'var(--shadow-md)',
        panel: 'var(--shadow-lg)',
      },

      transitionDuration: {
        fast: '120ms',
        base: '180ms',
        slow: '280ms',
      },

      /* Focus ring colour for Tailwind ring utilities */
      ringColor: {
        primary: 'var(--color-primary)',
        danger:  'var(--color-danger)',
        warning: 'var(--color-warning)',
      },
    },
  },
  plugins: [],
}

export default config
