module.exports = {
  content: ["./templates/**/*.html", "./apps/**/templates/**/*.html", "./static/core/*.js"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#fff7ed", 100: "#ffedd5", 400: "#fb923c",
          500: "#f97316", 600: "#ea580c", 700: "#c2410c"
        }
      }
    }
  },
  plugins: []
};
