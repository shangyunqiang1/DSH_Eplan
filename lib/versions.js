/**
 * Host-side version records and self-update for the dsh-eplan bundle.
 *
 * This plugin is installed with pnpm's `link:` protocol (a local git checkout),
 * so the built-in plugin manager deliberately offers it no "update" button —
 * there is no npm `installTarget` and the market refuses `link:` specs. We
 * therefore ship our own version ledger and update check instead, contributed
 * through the host's `plugins.detail.{actions,badge,section}` slots.
 *
 *   * `versions.json` is the release ledger (newest first). It is also the
 *     remote manifest served from the GitHub `main` branch.
 *   * `package.json#version` is the version currently activated on disk.
 *   * `latest` is the newest version advertised by either the local ledger or
 *     the remote manifest; `updateAvailable` is simply `latest > current`. The
 *     local ledger is authoritative for a release already present in this
 *     checkout (it also keeps the UI useful when GitHub is unreachable), while
 *     the remote manifest covers releases we still need to pull.
 *
 * Applying an update fast-forwards from origin when the remote is ahead and the
 * tree is clean; otherwise it finalises the release already present in the
 * working tree by aligning `package.json#version`. Either way DSH needs a
 * disable/re-enable to re-read the bundle, which the client explains.
 */
import fs from 'node:fs'
import path from 'node:path'
import { execFile } from 'node:child_process'

const JSON_HEADERS = { 'content-type': 'application/json' }
const errText = (err) => String((err && err.message) || err)

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

/** Register `/api-eplan/version` and `/api-eplan/version/update` on the web server. */
export function registerVersionRoutes(webServer, root) {
  const jsonRoute = (routePath, handle) => ({
    kind: 'exact',
    path: routePath,
    handler: async (req, res) => {
      let status = 200
      let payload
      try {
        payload = await handle(req)
      } catch (err) {
        status = 500
        payload = { ok: false, error: errText(err) }
      }
      res.writeHead(status, JSON_HEADERS)
      res.end(JSON.stringify(payload))
    },
  })

  const disposers = []
  try {
    disposers.push(
      webServer.register(
        jsonRoute('/api-eplan/version', async (req) => {
          const body = await readBody(req)
          return await versionStatus(root, { force: Boolean(body.force) })
        }),
      ),
    )
    disposers.push(
      webServer.register(
        jsonRoute('/api-eplan/version/update', async () => {
          return await applyUpdate(root)
        }),
      ),
    )
  } catch (err) {
    for (const d of disposers) {
      if (typeof d === 'function') {
        try {
          d()
        } catch {
          /* ignore */
        }
      }
    }
    throw err
  }
  return () => {
    while (disposers.length) {
      const d = disposers.pop()
      if (typeof d === 'function') {
        try {
          d()
        } catch {
          /* ignore */
        }
      }
    }
  }
}

export const RECORDS_FILE = 'versions.json'
export const REMOTE_MANIFEST =
  'https://raw.githubusercontent.com/shangyunqiang1/DSH_Eplan/main/versions.json'
export const RELEASES_URL = 'https://github.com/shangyunqiang1/DSH_Eplan/releases'
export const REPOSITORY = 'https://github.com/shangyunqiang1/DSH_Eplan'

const REMOTE_TTL_MS = 5 * 60 * 1000
const FETCH_TIMEOUT_MS = 6000

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return null
  }
}

/** Numeric semver-ish compare so 0.2.10 sorts after 0.2.9. */
export function compareVersions(a, b) {
  const parts = (v) => {
    const m = String(v || '').match(/^v?(\d+)\.(\d+)\.(\d+)/)
    return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : [0, 0, 0]
  }
  const A = parts(a)
  const B = parts(b)
  for (let i = 0; i < 3; i += 1) {
    if (A[i] !== B[i]) return A[i] > B[i] ? 1 : -1
  }
  return 0
}

export function currentVersion(root) {
  const pkg = readJson(path.join(root, 'package.json'))
  return (pkg && pkg.version) || '0.0.0'
}

export function readRecords(root) {
  const data = readJson(path.join(root, RECORDS_FILE))
  if (!data || !Array.isArray(data.releases)) return null
  return data
}

let remoteCache = { at: 0, value: null, error: null }

async function fetchRemote(force) {
  const now = Date.now()
  if (!force && remoteCache.value && now - remoteCache.at < REMOTE_TTL_MS) return remoteCache.value
  // After a failure, back off briefly before hammering the network again.
  if (!force && remoteCache.error && now - remoteCache.at < 30000) return null
  try {
    const url = force ? `${REMOTE_MANIFEST}?t=${now}` : REMOTE_MANIFEST
    const resp = await fetch(url, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      headers: { 'cache-control': 'no-cache' },
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json()
    if (!data || !Array.isArray(data.releases) || !data.releases[0]?.version) {
      throw new Error('manifest has no releases')
    }
    remoteCache = {
      at: now,
      value: { latest: data.releases[0].version, releases: data.releases, repository: data.repository, releasesUrl: data.releasesUrl },
      error: null,
    }
  } catch (err) {
    remoteCache = { at: now, value: null, error: String((err && err.message) || err) }
  }
  return remoteCache.value
}

/** Full status the client renders. Never throws: an offline host still shows local records. */
export async function versionStatus(root, options) {
  const force = Boolean(options && options.force)
  const current = currentVersion(root)
  const ledger = readRecords(root)
  const releases = ledger ? ledger.releases : []
  const localLatest = releases[0]?.version || current

  const remote = await fetchRemote(force)
  const remoteLatest = remote ? remote.latest : null
  // Newest version advertised by either source. The local ledger covers a
  // release already checked out but not yet activated; the remote manifest
  // covers a release published on GitHub that we still need to pull.
  const candidates = [localLatest, remoteLatest].filter(Boolean)
  const latest = candidates.sort((a, b) => compareVersions(b, a))[0] || current

  // Prefer the richer (remote) changelog when it has more entries.
  const shownReleases =
    remote && remote.releases && remote.releases.length > releases.length ? remote.releases : releases

  return {
    ok: true,
    current,
    latest,
    localLatest,
    updateAvailable: compareVersions(latest, current) > 0,
    source: remote ? 'remote' : remoteCache.error ? 'offline' : 'local',
    remoteError: remoteCache.error || null,
    checkedAt: new Date().toISOString(),
    releases: shownReleases,
    repository: (ledger && ledger.repository) || (remote && remote.repository) || REPOSITORY,
    releasesUrl: (ledger && ledger.releasesUrl) || (remote && remote.releasesUrl) || RELEASES_URL,
  }
}

function git(root, args, timeout) {
  return new Promise((resolve) => {
    execFile('git', args, { cwd: root, windowsHide: true, timeout: timeout || 15000 }, (err, stdout, stderr) => {
      resolve({
        ok: !err,
        stdout: String(stdout || '').trim(),
        stderr: String(stderr || (err && err.message) || '').trim(),
      })
    })
  })
}

/** Write only the "version" value, preserving key order and formatting. */
function bumpPackageVersion(root, version) {
  const file = path.join(root, 'package.json')
  try {
    const text = fs.readFileSync(file, 'utf8')
    const next = text.replace(/("version"\s*:\s*")[^"]+(")/, (m, a, b) => a + version + b)
    if (next === text) return { ok: false, error: 'package.json has no version field' }
    fs.writeFileSync(file, next, 'utf8')
    return { ok: true }
  } catch (err) {
    return { ok: false, error: String((err && err.message) || err) }
  }
}

/**
 * Apply the pending release. Git operations are best-effort and never fatal:
 * a `link:` install already points at the working tree, so even an offline or
 * dirty checkout can still activate a release whose files are present.
 *
 *   1. Try `git fetch` + `git pull --ff-only` when origin/main is ahead and the
 *      tree is clean (the normal path for a real published release).
 *   2. Align `package.json#version` to the target when it still lags (the path
 *      for a release already present in this checkout).
 *
 * DSH must re-read the bundle (disable/re-enable) afterwards; the client says so.
 */
export async function applyUpdate(root) {
  const before = await versionStatus(root, { force: true })
  const from = before.current
  const to = before.latest
  if (!before.updateAvailable) {
    return { ok: true, unchanged: true, from, to, needsReload: false, message: `Already on ${from}` }
  }

  const steps = []
  if (fs.existsSync(path.join(root, '.git'))) {
    const fetched = await git(root, ['fetch', 'origin', '--quiet'], 10000)
    if (fetched.ok) {
      const ahead = await git(root, ['rev-list', '--count', 'HEAD..origin/main'])
      const behind = ahead.ok ? Number(ahead.stdout) || 0 : 0
      if (behind > 0) {
        const dirty = await git(root, ['status', '--porcelain'])
        if (!dirty.stdout) {
          const pull = await git(root, ['pull', '--ff-only', 'origin', 'main'], 30000)
          if (pull.ok) steps.push('git pull --ff-only origin main')
          else steps.push(`pull skipped: ${pull.stderr || pull.stdout}`)
        } else {
          steps.push('pull skipped: working tree has local changes')
        }
      }
    } else {
      steps.push('fetch unavailable (offline)')
    }
  }

  const after = await versionStatus(root, { force: true })
  let version = after.current
  if (compareVersions(version, to) < 0) {
    const bumped = bumpPackageVersion(root, to)
    if (!bumped.ok) {
      return { ok: false, from, to, needsReload: false, steps, error: `写入版本号失败：${bumped.error}` }
    }
    version = to
    steps.push(`package.json version -> ${to}`)
  }

  return {
    ok: true,
    unchanged: false,
    from,
    to,
    version,
    method: steps.length ? steps.join(' + ') : 'none',
    steps,
    needsReload: true,
    message: `已更新到 ${version}。请在「插件」页停用再启用 dsh-eplan（或重新加载）使新版本生效。`,
  }
}
