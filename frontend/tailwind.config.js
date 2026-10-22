/** FixFlow design tokens.
 *  Blueprint blue carries structure; signal amber is reserved for time pressure (SLA);
 *  breach red and moss green only ever mean "late" and "done". */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#F3F5F4',
        ink: { DEFAULT: '#1D2B36', soft: '#5D6B75', faint: '#8A969E' },
        line: '#D6DCDF',
        blueprint: { DEFAULT: '#22577A', dark: '#173F5A', deep: '#10304A', light: '#E3EDF4' },
        signal: { DEFAULT: '#E8A317', dark: '#9A6A00', light: '#FBF0D5' },
        breach: { DEFAULT: '#C8372D', light: '#F8E1DE' },
        moss: { DEFAULT: '#3A7D44', light: '#E1EFE3' },
      },
      fontFamily: {
        sans: ['Archivo', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        narrow: ['"Archivo Narrow"', 'Archivo', 'system-ui', 'sans-serif'],
      },
      borderRadius: { sm: '3px', DEFAULT: '5px', md: '7px', lg: '10px' },
    },
  },
  plugins: [],
};
