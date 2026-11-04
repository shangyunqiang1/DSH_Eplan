/**
 * EPLAN installation discovery for the dsh-eplan plugin.
 *
 * EPLAN puts every installed Platform version side by side under one platform
 * root, for example:
 *
 *   C:\\Program Files\\EPLAN\\Platform\\2025.0.3\\Bin\\Eplan.EplApi.RemoteClientu.dll
 *
 * The bundled MCP server already honours EPLAN_PLATFORM_ROOT for a
 * non-standard location (vendor/eplan-mcp/.../eplan_connection.py reads it at
 * import time), so everything this module does is decide which root to hand it.
 *
 * Sources, in priority order: the path the user saved in the plugin UI, the
 * inherited EPLAN_PLATFORM_ROOT environment variable, the EPLAN setup registry,
 * and the usual Program Files locations. A candidate only counts when at least
 * one of its child folders really is a Platform version (Bin/Eplan.EplApi.
 * RemoteClientu.dll), so a stale registry entry cannot produce a phantom.
 */
import fs from 'node:fs'
import path from 'node:path'
import { execFile } from 'node:child_process'

const REMOTE_CLIENT_DLL = 'Eplan.EplApi.RemoteClientu.dll'
const GRPC_DLL = 'Grpc.Net.Client.dll'

export const ROOT_FILE_NAME = 'eplan-platform-root.txt'
export const DEFAULT_PLATFORM_ROOT = 'C:\\Program Files\\EPLAN\\Platform'

const REGISTRY_KEYS = [
  'HKLM\\SOFTWARE\\EPLAN\\EPLAN W3\\Platform',
  'HKLM\\SOFTWARE\\WOW6432Node\\EPLAN\\EPLAN W3\\Platform',
]

function isDir(target) {
  try {
    return fs.statSync(target).isDirectory()
  } catch {
    return false
  }
}

function readdirSafe(target) {
  try {
    return fs.readdirSync(target, { withFileTypes: true })
  } catch {
    return []
  }
}

/** Numeric dotted-version key, so 2025.0.10 sorts above 2025.0.9. */
export function versionKey(name) {
  const parts = String(name === undefined || name === null ? '' : name).split('.')
  const out = []
  for (const part of parts) {
    const value = Number.parseInt(part, 10)
    if (Number.isFinite(value)) out.push(value)
  }
  return out
}

function compareVersion(left, right) {
  const a = versionKey(left)
  const b = versionKey(right)
  const length = Math.max(a.length, b.length)
  for (let index = 0; index < length; index += 1) {
    const x = index < a.length ? a[index] : 0
    const y = index < b.length ? b[index] : 0
    if (x !== y) return x < y ? -1 : 1
  }
  return 0
}

/**
 * Accept what a user is likely to paste: a platform root, a Platform version
 * folder, or either of those with quotes and trailing separators. A version
 * folder (one that already holds Bin/Eplan.EplApi.RemoteClientu.dll) resolves
 * to its parent, because that is the folder the MCP server scans.
 */
export function normalizeRoot(input) {
  if (typeof input !== 'string') return null
  let candidate = input.trim().replace(/^["']+|["']+$/g, '')
  if (candidate.length === 0) return null
  candidate = candidate.replace(/[\\/]+$/, '')
  if (candidate.length === 0) return null
  const drive = /^[A-Za-z]:$/.test(candidate)
  const absolute = /^[A-Za-z]:[\\/]/.test(candidate) || candidate.startsWith('\\\\')
  if (!absolute && !drive) return null
  if (drive) return candidate + '\\'
  try {
    if (fs.existsSync(path.join(candidate, 'Bin', REMOTE_CLIENT_DLL))) {
      const parent = path.dirname(candidate)
      if (parent && parent !== candidate) return parent
    }
  } catch {
    /* fall through with the candidate as given */
  }
  return candidate
}

/**
 * The Platform versions installed directly under one root, newest first and
 * collapsed to one entry per major version, mirroring the bundled MCP server's
 * own detection so the UI cannot promise a version it will not use.
 */
export function readVersions(root) {
  if (!root) return []
  const byMajor = new Map()
  for (const entry of readdirSafe(root)) {
    if (!entry.isDirectory()) continue
    const name = entry.name
    const binDir = path.join(root, name, 'Bin')
    let hasRemoteClient = false
    try {
      hasRemoteClient = fs.existsSync(path.join(binDir, REMOTE_CLIENT_DLL))
    } catch {
      hasRemoteClient = false
    }
    if (!hasRemoteClient) continue
    const version = /^2\.9(?:\.|$)/.test(name) ? '2.9' : name.split('.')[0]
    let runtime = 'netfx'
    try {
      if (fs.existsSync(path.join(binDir, GRPC_DLL))) runtime = 'coreclr'
    } catch {
      runtime = 'netfx'
    }
    const record = { name, full_version: name, version, runtime, bin: binDir }
    const current = byMajor.get(version)
    if (!current || compareVersion(name, current.full_version) > 0) byMajor.set(version, record)
  }
  return Array.from(byMajor.values()).sort((left, right) =>
    compareVersion(right.full_version, left.full_version),
  )
}

export function inspectRoot(root) {
  const normalized = normalizeRoot(root)
  const exists = Boolean(normalized) && isDir(normalized)
  const versions = exists ? readVersions(normalized) : []
  return {
    root: normalized || (typeof root === 'string' ? root : ''),
    exists,
    valid: versions.length > 0,
    versions,
  }
}

function runRegistryQuery(key) {
  return new Promise((resolve) => {
    try {
      execFile(
        'reg',
        ['query', key, '/s'],
        { windowsHide: true, maxBuffer: 8 * 1024 * 1024, timeout: 8000 },
        (error, stdout) => resolve(error ? '' : String(stdout || '')),
      )
    } catch {
      resolve('')
    }
  })
}

/** Platform roots named by the EPLAN setup registry, derived from each BIN path. */
function rootsFromRegistryText(text) {
  const roots = []
  const lines = String(text || '').split(/\r?\n/)
  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (line.length === 0) continue
    const marker = line.indexOf('BIN=')
    if (marker < 0) continue
    const value = line.slice(marker + 4).trim()
    if (value.length === 0) continue
    const binAt = value.search(/[\\/]Bin(?:[\\/]|$)/i)
    const versionDir = binAt > 0 ? value.slice(0, binAt) : path.dirname(value)
    const root = path.dirname(versionDir)
    if (root && root !== versionDir) roots.push(root)
  }
  return roots
}

async function registryRoots() {
  const found = []
  for (const key of REGISTRY_KEYS) {
    const text = await runRegistryQuery(key)
    if (text.length === 0) continue
    for (const root of rootsFromRegistryText(text)) found.push(root)
  }
  return found
}

function commonRoots() {
  const roots = []
  const programFiles = [process.env.ProgramFiles, 'C:\\Program Files', process.env['ProgramFiles(x86)']]
  for (const base of programFiles) {
    if (!base) continue
    roots.push(path.join(base, 'EPLAN', 'Platform'))
  }
  // EPLAN occasionally installs a platform folder beside the usual one
  // (Platform 2025, Platform-2026, ...), so list those siblings too — but only
  // when they really hold a Platform version, which also filters out the
  // companion "Platform Data" folder.
  for (const base of programFiles) {
    if (!base) continue
    const eplanDir = path.join(base, 'EPLAN')
    for (const entry of readdirSafe(eplanDir)) {
      if (!entry.isDirectory()) continue
      if (!/^platform/i.test(entry.name)) continue
      const candidate = path.join(eplanDir, entry.name)
      if (readVersions(candidate).length === 0) continue
      roots.push(candidate)
    }
  }
  return roots
}

function dedupe(candidates) {
  const seen = new Set()
  const out = []
  for (const candidate of candidates) {
    if (!candidate || !candidate.root) continue
    const key = candidate.root.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(candidate)
  }
  return out
}

/**
 * Every root worth offering the user, best first. Each candidate carries the
 * source that produced it so the UI can explain where it came from, and its
 * inspection result so the UI never shows an empty install as selectable.
 */
export async function detectRoots(options) {
  const settings = options && typeof options === 'object' ? options : {}
  const candidates = []
  const saved = typeof settings.saved === 'string' ? settings.saved : null
  const environment = typeof process.env.EPLAN_PLATFORM_ROOT === 'string'
    ? process.env.EPLAN_PLATFORM_ROOT
    : null

  if (saved) candidates.push({ root: normalizeRoot(saved), source: 'saved' })
  if (environment) candidates.push({ root: normalizeRoot(environment), source: 'env' })
  for (const root of await registryRoots()) candidates.push({ root: normalizeRoot(root), source: 'registry' })
  for (const root of commonRoots()) candidates.push({ root: normalizeRoot(root), source: 'common' })
  if (!saved && !environment) candidates.push({ root: normalizeRoot(DEFAULT_PLATFORM_ROOT), source: 'common' })

  const defaultRoot = normalizeRoot(DEFAULT_PLATFORM_ROOT)
  const inspected = dedupe(candidates).map((candidate) => {
    const result = inspectRoot(candidate.root)
    return {
      root: result.root,
      source: candidate.source,
      exists: result.exists,
      valid: result.valid,
      versions: result.versions,
    }
  })
  const useful = inspected.filter((entry) => {
    if (entry.valid) return true
    // Keep an explicitly chosen/environment root and the canonical default even
    // when they are empty: the UI must be able to say "installed nowhere" for
    // them instead of silently showing nothing.
    if (entry.source === 'saved' || entry.source === 'env') return true
    return entry.root.toLowerCase() === String(defaultRoot).toLowerCase()
  })
  return useful.sort((left, right) => {
    if (left.valid !== right.valid) return left.valid ? -1 : 1
    return 0
  })
}

/** Drive roots on Windows, so the folder browser can start somewhere useful. */
export function listDrives() {
  const drives = []
  for (const letter of 'CDEFGHIJKLMNOPQRSTUVWXYZ') {
    const candidate = letter + ':\\'
    if (isDir(candidate)) drives.push(candidate)
  }
  return drives
}

/** Trim the quoting and trailing separators a pasted path arrives with. */
export function resolveDirPath(input) {
  if (typeof input !== 'string') return ''
  return input.trim().replace(/^["']+|["']+$/g, '').replace(/[\\/]+$/, '') || ''
}

/**
 * One level of the folder browser: the folder itself, its parent, and the
 * subfolders, each flagged with whether it is a usable platform root.
 */
export function browse(target) {
  const requested = resolveDirPath(target)
  if (requested.length === 0) {
    return { path: '', parent: null, drives: listDrives(), entries: [], valid: false, versions: [] }
  }
  if (!isDir(requested)) {
    return { path: requested, parent: null, drives: [], entries: [], missing: true, valid: false, versions: [] }
  }
  const parentPath = path.dirname(requested)
  const entries = []
  for (const entry of readdirSafe(requested)) {
    if (!entry.isDirectory()) continue
    const full = path.join(requested, entry.name)
    let versions = []
    try {
      versions = readVersions(full)
    } catch {
      versions = []
    }
    entries.push({ name: entry.name, path: full, valid: versions.length > 0, versions })
  }
  entries.sort((left, right) => {
    if (left.valid !== right.valid) return left.valid ? -1 : 1
    return left.name.localeCompare(right.name)
  })
  const own = readVersions(requested)
  return {
    path: requested,
    parent: parentPath && parentPath !== requested ? parentPath : null,
    drives: [],
    entries,
    valid: own.length > 0,
    versions: own,
  }
}

export function readSavedRoot(file) {
  try {
    const text = fs.readFileSync(file, 'utf8')
    const line = String(text).split(/\r?\n/).map((entry) => entry.trim()).find((entry) => entry.length > 0)
    return line ? line : null
  } catch {
    return null
  }
}

export function writeSavedRoot(file, root) {
  const directory = path.dirname(file)
  fs.mkdirSync(directory, { recursive: true })
  // LF only: the launcher reads the first line through cmd's for /f, which
  // trims line endings, but a stray CR would still reach Python.
  fs.writeFileSync(file, String(root).replace(/\r?\n/g, '') + '\n', { encoding: 'utf8' })
}

export function clearSavedRoot(file) {
  try {
    fs.rmSync(file, { force: true })
    return true
  } catch {
    return false
  }
}
