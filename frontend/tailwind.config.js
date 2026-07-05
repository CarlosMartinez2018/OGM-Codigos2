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
        // Acento coral/terracota de la marca Acento (del logo)
        coral:    '#E2664B',
        coraldim: '#C74E36',
        // Neutros
        paper:    '#F5F6F8',
        surface:  '#FFFFFF',
        surfacealt:'#FAFBFC',
        navysoft: '#2A3565',
        coralsoft:'#F4E3DE',
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
        // Display = Space Grotesk (titulares con caracter, tecnica)
        display: ['"Space Grotesk"', '"Helvetica Neue"', 'system-ui', 'sans-serif'],
        // Helvetica Neue = tipografia de cuerpo de la marca
        sans: ['"Helvetica Neue"', 'Helvetica', 'Arial', 'system-ui', 'sans-serif'],
        // Mono para tokens de maquina (dominios, stages, ids, %)
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(20,26,52,0.05), 0 1px 1px rgba(20,26,52,0.03)',
        rail: '2px 0 12px rgba(20,26,52,0.08)',
        pop:  '0 8px 24px rgba(20,26,52,0.12)',
        focus:'0 0 0 3px rgba(226,102,75,0.30)',
      },
      letterSpacing: {
        label: '0.16em',
      },
    },
  },
  plugins: [],
}
