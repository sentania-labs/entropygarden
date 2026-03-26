/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg:          '#080810',
        surface:     '#0d0d1a',
        'surface-2': '#12121f',
        border:      '#1a1a30',
        dim:         '#6e7681',
        amber:       '#e6a817',
        green:       '#3fb950',
        red:         '#f85149',
        blue:        '#58a6ff',
        cyan:        '#79c0ff',
        text:        '#c9d1d9',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}

