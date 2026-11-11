/**
 * Builds the renderer app (ui://regagentic/work-item.html, adr-renderer-html-lives-in-harness)
 * into one self-contained HTML file: its script and style inline, nothing loaded from anywhere
 * else, so the host's default MCP Apps sandbox policy holds. The file is committed in
 * surfaces/views/; CI rebuilds it and fails when it differs.
 *
 *   npm run build:views
 */
import { fileURLToPath } from 'node:url'
import { build } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'
import tailwindConfig from '../tailwind.config.js'

const VIEWS = ['work-item']

const src = fileURLToPath(new URL('../src', import.meta.url))
const root = `${src}/views`
const outDir = fileURLToPath(new URL('../../views', import.meta.url))

// The GUI's theme, scanned over only what the renderer app draws.
const tailwindViews = {
  ...tailwindConfig,
  content: [`${src}/views/**/*.{html,ts,tsx}`, `${src}/workItem/**/*.{ts,tsx}`],
}

// Inline script text must not close or comment out its <script> element.
const scriptSafe = code => code.replaceAll('</script', '<\\/script').replaceAll('<!--', '<\\!--')

/** Puts the built script and style into the HTML file and drops their files. */
function inlineIntoHtml() {
  return {
    name: 'inline-into-html',
    enforce: 'post',
    generateBundle(_options, bundle) {
      for (const page of Object.values(bundle)) {
        if (!page.fileName.endsWith('.html')) continue
        let html = String(page.source)
        for (const [name, file] of Object.entries(bundle)) {
          if (file.type === 'chunk') {
            html = html.replace(new RegExp(`<script[^>]*src="[^"]*${name}"[^>]*></script>`),
                                () => `<script type="module">${scriptSafe(file.code)}</script>`)
            delete bundle[name]
          } else if (name.endsWith('.css')) {
            html = html.replace(new RegExp(`<link[^>]*href="[^"]*${name}"[^>]*>`),
                                () => `<style>${String(file.source)}</style>`)
            delete bundle[name]
          }
        }
        page.source = html
      }
    },
  }
}

for (const view of VIEWS) {
  await build({
    configFile: false,
    root,
    base: './',
    logLevel: 'warn',
    plugins: [react(), inlineIntoHtml()],
    css: { postcss: { plugins: [tailwindcss(tailwindViews), autoprefixer()] } },
    build: {
      outDir,
      emptyOutDir: false,
      cssCodeSplit: false,
      modulePreload: false,
      assetsInlineLimit: () => true,
      rollupOptions: { input: `${root}/${view}.html`, output: { inlineDynamicImports: true } },
    },
  })
  console.log(`built ${view}.html`)
}
