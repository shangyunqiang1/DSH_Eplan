/**
 * Live "is EPLAN actually there?" probe behind the connection indicator.
 *
 * The browser half cannot see processes, so the settings page asks this module
 * over /api-eplan/connection. Two independent facts are collected, cheaply and
 * without ever touching the live project:
 *
 *   1. EPLAN itself — the process exists AND it owns a listening remoting
 *      socket. The port is dynamic (49152 is only the usual first choice, see
 *      vendor/eplan-mcp/.../eplan_connection.py), so it is discovered from the
 *      PID instead of assumed. netstat/tasklist cost ~90/330 ms on this machine;
 *      Get-CimInstance costs ~2 s and is deliberately avoided.
 *
 *   2. The MCP client — whether `mcp__eplan__*` tools are still registered in
 *      the host tool registry. The MCP client registers those names only after
 *      a successful initialize handshake and drops them once its reconnect
 *      budget is exhausted, so their presence is the closest thing the host
 *      exposes to "the MCP connection is up" (it publishes no status service).
 *
 * Note that "TCP connect to 127.0.0.1:49152" is NOT a valid check: EPLAN binds
 * the remoting socket to the physical/NIC addresses only, so the loopback probe
 * fails while eplan_connect still works.
 */
import { execFile } from 'node:child_process'

const PROCESS_NAME = 'EPLAN.exe'
const MCP_PREFIX = 'mcp__eplan__'
const EXEC_TIMEOUT_MS = 3000
const CACHE_TTL_MS = 1200

function run(file, args, timeoutMs) {
  return new Promise((resolve) => {
    try {
      execFile(file, args, { timeout: timeoutMs, windowsHide: true, maxBuffer: 8 * 1024 * 1024 }, (error, stdout) => {
        // A non-zero exit still carries usable output; only a hard failure
        // (ENOENT on a non-Windows host) resolves to nothing.
        resolve(error && !stdout ? '' : String(stdout || ''))
      })
    } catch {
      resolve('')
    }
  })
}

/** `tasklist /FO CSV` rows look like "EPLAN.exe","31480","Console","1","346,536 K". */
function parseTasklist(text) {
  const pids = []
  for (const raw of String(text || '').split(/\r?\n/)) {
    const line = raw.trim()
    if (!line.startsWith('"')) continue
    const cells = line.split('","').map((cell) => cell.replace(/^"|"$/g, ''))
    if (cells.length < 2) continue
    if (String(cells[0]).toLowerCase() !== PROCESS_NAME.toLowerCase()) continue
    const pid = Number(cells[1])
    if (Number.isInteger(pid) && pid > 0) pids.push(pid)
  }
  return pids
}

/** `netstat -ano -p TCP` LISTENING rows owned by the given PIDs, one entry per port. */
function parseNetstat(text, pids) {
  const wanted = new Set(pids.map(String))
  const byPort = new Map()
  for (const raw of String(text || '').split(/\r?\n/)) {
    const cols = raw.trim().split(/\s+/)
    if (cols.length < 5) continue
    if (cols[0].toUpperCase() !== 'TCP') continue
    if (cols[3].toUpperCase() !== 'LISTENING') continue
    if (!wanted.has(cols[4])) continue
    const local = cols[1]
    const cut = local.lastIndexOf(':')
    if (cut < 0) continue
    const port = Number(local.slice(cut + 1))
    if (!Number.isInteger(port) || port <= 0) continue
    const entry = byPort.get(port) || { port, addresses: [] }
    const address = local.slice(0, cut)
    if (address && !entry.addresses.includes(address)) entry.addresses.push(address)
    byPort.set(port, entry)
  }
  return [...byPort.values()].sort((a, b) => a.port - b.port)
}

export async function probeEplan() {
  if (process.platform !== 'win32') {
    return { supported: false, running: false, pids: [], ports: [], port: null }
  }
  const listing = await run('tasklist', ['/FI', `IMAGENAME eq ${PROCESS_NAME}`, '/NH', '/FO', 'CSV'], EXEC_TIMEOUT_MS)
  const pids = parseTasklist(listing)
  if (pids.length === 0) return { supported: true, running: false, pids: [], ports: [], port: null }
  const table = await run('netstat', ['-ano', '-p', 'TCP'], EXEC_TIMEOUT_MS)
  const ports = parseNetstat(table, pids)
  return { supported: true, running: true, pids, ports, port: ports.length ? ports[0].port : null }
}

/**
 * @param tools the host tool registry (`ctx.get('tools')`), or undefined when the
 *              service is not available in this profile.
 */
export function probeMcpTools(tools) {
  if (!tools || typeof tools.view !== 'function') return { available: false, count: 0, names: [] }
  try {
    const view = tools.view()
    const names = []
    const visible = view && view.visible
    if (visible && typeof visible.keys === 'function') {
      for (const key of visible.keys()) {
        const name = String(key)
        // "mcp__eplan__" never matches "mcp__eplan2025__": the prefix ends with
        // a double underscore, which the documentation servers do not follow.
        if (name.startsWith(MCP_PREFIX)) names.push(name)
      }
    }
    return { available: true, count: names.length, names }
  } catch {
    return { available: false, count: 0, names: [] }
  }
}

function decide(eplan, mcp) {
  const eplanUp = Boolean(eplan && eplan.running)
  const mcpUp = Boolean(mcp && mcp.count > 0)
  if (!eplan || !eplan.supported) return 'unknown'
  if (eplanUp && mcpUp) return 'connected'
  if (eplanUp) return mcp && mcp.available ? 'eplan-only' : 'eplan-started'
  if (mcpUp) return 'mcp-only'
  return 'disconnected'
}

/** `tools` is a getter on purpose: the service mounts after this plugin applies. */
function resolveTools(options) {
  const value = options.tools
  if (typeof value === 'function') {
    try {
      return value()
    } catch {
      return undefined
    }
  }
  return value
}

async function runProbe(options) {
  const [eplan, mcp] = await Promise.all([probeEplan(), Promise.resolve(probeMcpTools(resolveTools(options)))])
  return {
    ok: true,
    state: decide(eplan, mcp),
    eplan,
    mcp,
    checkedAt: new Date().toISOString(),
  }
}

let cache = null
let inflight = null

/** Never throws: every failure degrades to a state the UI can still render. */
export async function probeConnection(options = {}) {
  if (cache && Date.now() - cache.at < CACHE_TTL_MS) return cache.payload
  if (inflight) return inflight
  inflight = (async () => {
    try {
      return await runProbe(options)
    } finally {
      inflight = null
    }
  })()
  const payload = await inflight
  cache = { at: Date.now(), payload }
  return payload
}

/** Test/DI seam: drop the short-lived probe cache. */
export function resetConnectionCache() {
  cache = null
  inflight = null
}
