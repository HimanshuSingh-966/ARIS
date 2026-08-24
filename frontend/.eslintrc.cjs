/**
 * frontend/.eslintrc.cjs
 *
 * package.json has advertised an `npm run lint` script since the project was
 * created, and eslint-plugin-react / -react-hooks / -react-refresh are all in
 * devDependencies — but no config file was ever committed, so the script exited 2
 * with "ESLint couldn't find a configuration file" and nothing was ever linted.
 * This is the standard Vite + React 18 config those plugins were installed for.
 */
module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'plugin:react/jsx-runtime',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', 'node_modules', '.eslintrc.cjs'],
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  settings: { react: { version: '18.2' } },
  plugins: ['react-refresh'],
  rules: {
    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    // plugin:react/recommended turns this on as an error, but there is not a single
    // PropTypes declaration anywhere in src/. Enabling it would mean annotating
    // every component before the linter can report anything else — off, so the
    // rules that catch real defects are the ones that speak.
    'react/prop-types': 'off',
  },
  overrides: [
    {
      // The Vercel Edge function and the Node-side build config: no JSX, and
      // `process` legitimately exists in both.
      files: ['api/**/*.js', 'vite.config.js', 'postcss.config.js'],
      env: { browser: true, node: true, es2022: true },
      rules: { 'react-refresh/only-export-components': 'off' },
    },
  ],
};
