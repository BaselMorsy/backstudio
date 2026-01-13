/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f5f1e8',   // ivory
          100: '#e8dfc8',  // light gold
          200: '#d4c9a8',  // warm beige
          300: '#c8a951',  // antique gold
          400: '#b09540',  // darker gold
          500: '#8a7532',  // deep gold
          600: '#1a3d2c',  // forest green
          700: '#14322a',  // darker forest
          800: '#0f2a1f',  // deep forest (logo bg)
          900: '#0a1f17',  // darkest forest
        },
        accent: {
          gold: '#c8a951',      // antique gold
          ivory: '#f5f1e8',     // ivory
          mutedGold: '#b8ad8a', // muted gold
          forest: '#0f2a1f',    // deep forest
        },
      },
      borderWidth: {
        '3': '3px',
      },
    },
  },
  plugins: [],
}