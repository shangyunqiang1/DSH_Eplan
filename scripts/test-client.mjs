// Offline render test for client.js: loads the bundle with a stub React,
// registers the slots, then renders every registered component with several
// subjects. It proves (a) the module parses and applies, (b) hook order stays
// stable across different subjects (the crash we fixed), and (c) every
// translation key the renderers ask for exists in the dictionaries.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const source = fs.readFileSync(path.join(here, '..', 'client.js'), 'utf8')

// ── stub React with a hook runtime ───────────────────────────────────────────
let renderCtx = null // { hooks: [], index, effects: [], id }
const hookState = new Map() // instance id -> array of hook values

function useSlot(kind, init) {
  const ctx = renderCtx
  const index = ctx.index++
  const store = hookState.get(ctx.id) || []
  // React treats a function argument as a lazy initializer, exactly like this.
  if (!(index in store)) store[index] = kind === 'state' ? (typeof init === 'function' ? init() : init) : undefined
  hookState.set(ctx.id, store)
  ctx.count = ctx.index
  return [store[index], (next) => {
    store[index] = typeof next === 'function' ? next(store[index]) : next
  }]
}

const React = {
  createElement(type, props, ...children) {
    return { type, props: { ...(props || {}), children: children.length ? children : (props || {}).children } }
  },
  createContext: () => ({ Provider: null, Consumer: null }),
  useState: (init) => useSlot('state', init),
  useRef: (init) => {
    const ctx = renderCtx
    const index = ctx.index++
    const store = hookState.get(ctx.id) || []
    if (!(index in store)) store[index] = { current: init }
    hookState.set(ctx.id, store)
    return store[index]
  },
  useEffect: (fn) => {
    const ctx = renderCtx
    ctx.index++
    ctx.effects.push(fn)
  },
  useMemo: (fn) => fn(),
  useCallback: (fn) => fn,
}

function render(id, component, props) {
  renderCtx = { hooks: [], index: 0, effects: [], id }
  let out
  try {
    out = component(props)
  } finally {
    const ctx = renderCtx
    for (const effect of ctx.effects) {
      try {
        effect()
      } catch (_) {
        /* effect bodies touch fetch/store; ignore in this harness */
      }
    }
    renderCtx.hooks = ctx
  }
  return { out, hookCount: renderCtx.index }
}

// ── load the bundle ──────────────────────────────────────────────────────────
let exportsRef = null
globalThis.window = {
  __ModuleLoader__: {
    load(entry) {
      exportsRef = entry.factory((name) => {
        if (name === 'react') return React
        throw new Error('unexpected require: ' + name)
      })
    },
  },
}
globalThis.fetch = async (url) => ({
  ok: true,
  status: 200,
  json: async () =>
    String(url).includes('/version/update')
      ? { ok: true, unchanged: false, from: '0.2.3', to: '0.2.4', version: '0.2.4', needsReload: true, message: '已更新到 0.2.4' }
      : {
          ok: true,
          current: '0.2.3',
          latest: '0.2.4',
          localLatest: '0.2.4',
          updateAvailable: true,
          source: 'offline',
          remoteError: 'HTTP 404',
          checkedAt: new Date().toISOString(),
          releases: [
            { version: '0.2.4', date: '2026-11-09', notes: { zh: '新增版本记录', en: 'Added version records' } },
            { version: '0.2.3', date: '2026-11-04', notes: { zh: '首个正式版本', en: 'First release' } },
          ],
          repository: 'https://github.com/shangyunqiang1/DSH_Eplan',
          releasesUrl: 'https://github.com/shangyunqiang1/DSH_Eplan/releases',
        },
})

new Function('window', source)(globalThis.window)

if (!exportsRef) throw new Error('bundle did not load')

// ── stub host context ────────────────────────────────────────────────────────
const registrations = []
const dicts = {}
let activeLang = 'zh'
const locale = {
  register(ns, dict) {
    // The host keeps one table per locale, not one per language key.
    dicts[ns] = dicts[ns] || {}
    for (const lang of Object.keys(dict)) dicts[ns][lang] = { ...(dicts[ns][lang] || {}), ...dict[lang] }
    return () => {}
  },
  bind(ns) {
    return (key, params) => {
      const table = (dicts[ns] && dicts[ns][activeLang]) || {}
      const raw = table[key]
      if (raw === undefined) {
        missingKeys.add(key)
        return key
      }
      return params
        ? String(raw).replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m))
        : raw
    }
  },
  subscribe: () => () => {},
}
const missingKeys = new Set()

const slots = {
  inject(key, callback) {
    // The real host runs the callback only once the slot is declared.
    const dispose = callback()
    return () => {
      if (typeof dispose === 'function') dispose()
    }
  },
  register(decl, component) {
    registrations.push({ decl, component })
    return () => {}
  },
}

const services = { locale, slots }
const ctx = {
  get: (name) => services[name],
  effect: (fn) => {
    const dispose = fn()
    return () => {
      if (typeof dispose === 'function') dispose()
    }
  },
}

exportsRef.apply(ctx)
console.log('exported name:', exportsRef.name, '| inject:', JSON.stringify(exportsRef.inject))
console.log('registrations:', registrations.map((r) => r.decl.name + (r.decl.id ? '#' + r.decl.id : r.decl.key ? '#' + r.decl.key : '')).join(', '))

// ── dictionaries: zh/en key parity ───────────────────────────────────────────
const zh = (dicts.eplan && dicts.eplan.zh) || {}
const en = (dicts.eplan && dicts.eplan.en) || {}
const zhKeys = Object.keys(zh)
const enKeys = Object.keys(en)
const onlyZh = zhKeys.filter((k) => !(k in en))
const onlyEn = enKeys.filter((k) => !(k in zh))
console.log('dict keys zh:', zhKeys.length, 'en:', enKeys.length)
if (onlyZh.length) console.log('!! keys missing from en:', onlyZh.join(', '))
if (onlyEn.length) console.log('!! keys missing from zh:', onlyEn.join(', '))

// ── render every registration with several subjects ──────────────────────────
const ours = { kind: 'bundle', pkg: { name: 'dsh-eplan', version: '0.2.3', installed: true, availability: 'profile', official: false, enabled: true, rows: [] } }
const other = { kind: 'bundle', pkg: { name: 'dsh-market', version: '1.69.0', installed: true, availability: 'profile', official: false, enabled: true, rows: [] } }
const noSubject = undefined

let failures = 0
for (const { decl, component } of registrations) {
  const id = String(decl.name) + '#' + String(decl.id || decl.key || '')
  const counts = []
  for (const [label, subject] of [['ours', ours], ['other', other], ['none', noSubject], ['ours-again', ours]]) {
    let rendered
    try {
      rendered = render(id, component, subject ? { subject } : {})
    } catch (err) {
      failures += 1
      console.log(`!! ${id} threw on ${label}: ${err && err.message}`)
      break
    }
    const out = rendered.out
    const shape = out === null || out === undefined ? 'null' : out.type || typeof out
    counts.push(`${label}=${shape}(${rendered.hookCount}h)`)
  }
  const hookCounts = counts.map((c) => c.match(/\((\d+)h\)/)?.[1]).filter(Boolean)
  const stable = new Set(hookCounts).size <= 1
  if (!stable) {
    failures += 1
    console.log(`!! ${id} hook count differs between subjects`)
  }
  console.log(`${stable ? 'ok ' : '!! '} ${id}: ${counts.join(' ')}`)
}

// ── second pass: after the shared store has its data ─────────────────────────
await new Promise((r) => setTimeout(r, 50))
console.log('--- after the version request settles ---')
for (const { decl, component } of registrations) {
  const id = String(decl.name) + '#' + String(decl.id || decl.key || '')
  const seen = []
  for (const [label, subject] of [['ours', ours], ['other', other], ['ours-again', ours]]) {
    let rendered
    try {
      rendered = render(id, component, subject ? { subject } : {})
    } catch (err) {
      failures += 1
      console.log(`!! ${id} threw on ${label}: ${err && err.message}`)
      break
    }
    const out = rendered.out
    const shape = out === null || out === undefined ? 'null' : out.type || typeof out
    seen.push(`${label}=${shape}(${rendered.hookCount}h)`)
  }
  const hookCounts = seen.map((c) => c.match(/\((\d+)h\)/)?.[1]).filter(Boolean)
  const stable = new Set(hookCounts).size <= 1
  if (!stable) {
    failures += 1
    console.log(`!! ${id} hook count differs between subjects after settle`)
  }
  console.log(`${stable ? 'ok ' : '!! '} ${id}: ${seen.join(' ')}`)
}

console.log(missingKeys.size === 0 ? 'ok  every t() key resolves' : '!! missing keys: ' + [...missingKeys].join(', '))

// ── read back what the detail-page section actually says ─────────────────────
function textOf(node) {
  if (node === null || node === undefined || node === false) return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join(' ')
  if (typeof node === 'object') return textOf(node.props && node.props.children)
  return ''
}

const sectionReg = registrations.find((r) => r.decl.name === 'plugins.detail.section')
if (sectionReg) {
  console.log('--- 版本记录 section text (zh) ---')
  const { out } = render('dump-zh', sectionReg.component, { subject: ours })
  console.log(
    textOf(out)
      .replace(/\s+/g, ' ')
      .trim(),
  )
  activeLang = 'en'
  const enOut = render('dump-en', sectionReg.component, { subject: ours }).out
  console.log('--- version section text (en) ---')
  console.log(
    textOf(enOut)
      .replace(/\s+/g, ' ')
      .trim(),
  )
}

console.log(failures === 0 ? 'RESULT: PASS' : `RESULT: ${failures} failure(s)`)
process.exitCode = failures === 0 ? 0 : 1
