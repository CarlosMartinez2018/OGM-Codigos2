/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Marca AcentoPartners (extraida de acentopartners.com)
        navy:     '#1C2445',
        navy2:    '#212B57',
        navyink:  '#141A34',
        // Acento-sello (laton/oro): lacre premium que combina con el navy
        brass:    '#B4924F',
        brassdim: '#94763B',
        // Neutros
        paper:    '#F5F6F8',
        surface:  '#FFFFFF',
        ink:      '#0B1220',
        muted:    '#667085',
        faint:    '#98A2B3',
        line:     '#E4E7EC',
        // Semantica de estado
        ok:       '#0F7B4A',
        warn:     '#B45309',
        stop:     '#B42318',
      },
      fontFamily: {
        // Helvetica Neue = tipografia real de la marca (local, sin webfont)
        sans: ['"Helvetica Neue"', 'Helvetica', 'Arial', 'system-ui', 'sans-serif'],
        // Mono para tokens de maquina (dominios, stages, ids, %)
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(20,26,52,0.05), 0 1px 1px rgba(20,26,52,0.03)',
        rail: '2px 0 12px rgba(20,26,52,0.08)',
      },
      letterSpacing: {
        label: '0.16em',
      },
    },
  },
  plugins: [],
}
