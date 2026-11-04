/**
 * Host routes behind the EPLAN install-path setting.
 *
 * The browser half cannot read the filesystem, so every read and write of the
 * platform root goes through these four JSON endpoints. The prefix is unique to
 * this plugin: webServer.register() does not follow the plugin scope and throws
 * on a duplicate path, so namespacing is the only thing keeping another plugin
 * from colliding with us.
 */
import path from 'node:path'
import {
  ROOT_FILE_NAME,
  browse,
  clearSavedRoot,
  detectRoots,
  inspectRoot,
  normalizeRoot,
  readSavedRoot,
  writeSavedRoot,
} from './platform.js'

const JSON_HEADERS = { 'content-type': 'application/json' }
const errorText = (err) => String((err && err.message) || err)

function jsonRoute(routePath, handle) {
  return {
    kind: 'exact',
    path: routePath,
    handler: async (req, res) => {
      let status = 200
      let payload
      try {
        const out = await handle(req)
        if (Array.isArray(out)) {
          status = out[0]
          payload = out[1]
        } else {
          payload = out
        }
      } catch (err) {
        status = 500
        payload = { ok: false, error: errorText(err) }
      }
      res.writeHead(status, JSON_HEADERS)
      res.end(JSON.stringify(payload))
    },
  }
}

async function readBody(req) {
  const chunks = []
  for await (const chunk of req) chunks.push(String(chunk))
  const text = chunks.join('')
  if (text.trim().length === 0) return {}
  try {
    return JSON.parse(text)
  } catch {
    return {}
  }
}

const badRequest = (error) => [400, { ok: false, error }]

/**
 * @param {string} root  bundle root (the folder holding cordis.patch.yml)
 */
export function createRootStore(root) {
  const runtimeDir = path.join(root, 'runtime')
  const file = path.join(runtimeDir, ROOT_FILE_NAME)
  const launcher = path.join(root, 'scripts', 'launch-eplan-mcp.cmd')
  return {
    root,
    runtimeDir,
    file,
    launcher,
    read: () => readSavedRoot(file),
    write: (value) => writeSavedRoot(file, value),
    clear: () => clearSavedRoot(file),
  }
}

async function buildState(store) {
  const saved = store.read()
  const candidates = await detectRoots({ saved })
  const effective = candidates.find((entry) => entry.valid) || null
  return {
    ok: true,
    saved: saved || null,
    effective: effective ? effective.root : null,
    effectiveSource: effective ? effective.source : null,
    effectiveVersions: effective ? effective.versions : [],
    candidates,
    rootFile: store.file,
    launcher: store.launcher,
  }
}

export function registerRoutes(webServer, store) {
  const disposers = []
  const register = (route) => {
    const dispose = webServer.register(route)
    if (dispose) disposers.push(dispose)
    return dispose
  }
  const disposeAll = () => {
    while (disposers.length > 0) {
      const dispose = disposers.pop()
      try {
        if (typeof dispose === 'function') dispose()
      } catch {
        /* keep tearing the rest down */
      }
    }
  }

  try {
    register(
      jsonRoute('/api-eplan/state', async () => {
        const state = await buildState(store)
        return [200, state]
      }),
    )

    register(
      jsonRoute('/api-eplan/probe', async (req) => {
        const body = await readBody(req)
        const requested = normalizeRoot(body.root)
        if (!requested) return badRequest('请输入 EPLAN Platform 目录的绝对路径。')
        const result = inspectRoot(requested)
        return [200, { ok: true, probe: result }]
      }),
    )

    // One level of the server-side folder browser. Doing this on the host keeps
    // the browser half free of any filesystem assumption (it may be a remote
    // browser) and matches how the native directory pickers work.
    register(
      jsonRoute('/api-eplan/browse', async (req) => {
        const body = await readBody(req)
        return [200, { ok: true, listing: browse(body.path) }]
      }),
    )

    register(
      jsonRoute('/api-eplan/save', async (req) => {
        const body = await readBody(req)
        const requested = normalizeRoot(body.root)
        if (!requested) return badRequest('请输入 EPLAN Platform 目录的绝对路径。')
        const result = inspectRoot(requested)
        // A valid folder is one that really holds a Platform version. Refusing
        // anything else keeps a typo from silently disabling EPLAN detection.
        if (!result.valid) {
          return [
            400,
            {
              ok: false,
              error: result.exists
                ? '该目录下没有找到 EPLAN Platform 版本（需要包含 Bin/Eplan.EplApi.RemoteClientu.dll）。'
                : '该目录不存在。',
              probe: result,
            },
          ]
        }
        store.write(requested)
        const state = await buildState(store)
        return [200, { ...state, ok: true, saved: requested, probe: result }]
      }),
    )

    register(
      jsonRoute('/api-eplan/reset', async () => {
        store.clear()
        const state = await buildState(store)
        return [200, { ...state, ok: true, saved: null }]
      }),
    )
  } catch (err) {
    disposeAll()
    throw err
  }

  return disposeAll
}
