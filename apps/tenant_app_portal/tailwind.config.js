const oklch = (token) => `oklch(var(${token}) / <alpha-value>)`

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-body)'],
        mono: ['var(--font-mono)'],
      },
      borderRadius: {
        lg: 'var(--radius-pane)',
        md: 'var(--radius)',
        sm: 'calc(var(--radius) - 2px)',
      },
      colors: {
        background: oklch('--background'),
        foreground: oklch('--foreground'),
        card: {
          DEFAULT: oklch('--card'),
          foreground: oklch('--card-foreground'),
        },
        popover: {
          DEFAULT: oklch('--popover'),
          foreground: oklch('--popover-foreground'),
        },
        primary: {
          DEFAULT: oklch('--primary'),
          foreground: oklch('--primary-foreground'),
        },
        secondary: {
          DEFAULT: oklch('--secondary'),
          foreground: oklch('--secondary-foreground'),
        },
        muted: {
          DEFAULT: oklch('--muted'),
          foreground: oklch('--muted-foreground'),
        },
        accent: {
          DEFAULT: oklch('--accent'),
          foreground: oklch('--accent-foreground'),
        },
        destructive: {
          DEFAULT: oklch('--destructive'),
          foreground: oklch('--destructive-foreground'),
        },
        success: oklch('--success'),
        warn: oklch('--warn'),
        border: oklch('--border'),
        input: oklch('--input'),
        ring: oklch('--ring'),
        chart: {
          1: oklch('--chart-1'),
          2: oklch('--chart-2'),
          3: oklch('--chart-3'),
          4: oklch('--chart-4'),
          5: oklch('--chart-5'),
          6: oklch('--chart-6'),
          7: oklch('--chart-7'),
          8: oklch('--chart-8'),
          9: oklch('--chart-9'),
          10: oklch('--chart-10'),
        },
      },
    },
  },
  plugins: [require('tailwindcss-animate'), require('@tailwindcss/typography')],
}
