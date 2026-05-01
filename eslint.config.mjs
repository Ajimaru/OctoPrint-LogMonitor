export default [
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        API_BASEURL: "readonly",
        OCTOPRINT_VIEWMODELS: "readonly",
        PNotify: "readonly",
        $: "readonly",
        alert: "readonly",
        confirm: "readonly",
        console: "readonly",
        document: "readonly",
        encodeURIComponent: "readonly",
        ko: "readonly",
        setTimeout: "readonly",
        window: "readonly",
      },
    },
    rules: {
      "no-unused-vars": "off",
    },
  },
];
