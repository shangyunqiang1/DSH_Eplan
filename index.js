/**
 * DSH_Eplan host plugin.
 *
 * Two jobs:
 *
 * 1. Keep the EPLAN capability visible in the always-on system prompt: which
 *    MCP servers exist, the safety rules for driving a live EPLAN project, and
 *    the documentation routing that prefers the local, version-exact 2025
 *    reference. The MCP servers themselves are mounted by cordis.patch.yml.
 *
 * 2. Serve the install-path setting: the browser half (client.js) asks these
 *    routes where EPLAN lives, and the resolved root is persisted to
 *    runtime/eplan-platform-root.txt, which scripts/launch-eplan-mcp.cmd turns
 *    into EPLAN_PLATFORM_ROOT for the bundled MCP server.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRootStore, registerRoutes } from './lib/routes.js'
import { registerVersionRoutes } from './lib/versions.js'

export const name = 'dsh-eplan'

export const inject = ['systemPrompt']

const GUIDANCE = `## EPLAN Electric P8

The \`eplan\` MCP server drives the local EPLAN Electric P8 instance over the Remote Client interface — call \`eplan_versions\` for the versions actually installed instead of assuming one (\`mcp__eplan__*\`). It normally runs in discovery mode: start with \`eplan_status\` / \`eplan_versions\`, connect with \`eplan_connect\`, then use \`eplan_tools_search\` → \`eplan_tools_describe\` → \`eplan_tools_call\` for the ~236 typed tools (project, page, parts, exports, scripts); use \`eplan_action_catalog\` → \`eplan_action_run\` for any of the ~1150 raw EPLAN actions, and \`eplan_ribbon_catalog\` to map a GUI button back to an action. 15 tools are published directly (12 connection/action-catalog core — including \`eplan_list_dialogs\` / \`eplan_click_dialog_button\` for when EPLAN is blocked by a prompt — plus the 3 discovery meta-tools).

Safety: inspect read-only first; ask the user before changing their open project; back up the project before the first modifying action (\`eplan_backup_project\`); never run delete/purge/reorganize/wipe/discard/erase actions without explicit approval naming the project. The bundled server (eplan-mcp v1.3.0) tags every tool with MCP annotations and \`canary-ecad/eplan\` facts (changesProject / runsCode / changesEplan / destructive); treat destructive or parts/master-data tools — especially \`eplan_live_batch\`, \`eplan_live_remove_placement\`, \`eplan_live_copy_pages_to_structure\`, \`eplan_remove_unused_user_properties\`, \`eplan_set_parts_data_source\`, \`eplan_restore_masterdata\`, \`eplan_partsmanagement_import\` (import mode 3 replaces data) and \`eplan_dataportal_*\` — as requiring the same explicit approval and backup. When only 2025 is installed, pin the version with \`eplan_connect({version:"2025"})\` before the first DLL load (auto-detection can otherwise report 2026 and expose 2027-gated tools); Data Portal actions on 2025 open a modal window — the user must close it before EPLAN responds again.

Documentation is fully local after a one-time crawl — every documentation server answers from local SQLite indexes, so no query leaves the machine. Four are mounted by default; the 2026 and 2027 rows ship disabled and light up once their indexes are in \`data/\`:

- \`mcp__eplan2025__eplan2025_search\` / \`_get\` / \`_type\` / \`_stats\` — version-exact P8 2025 **.NET API reference** built from the installed XML docs (36,493 members: namespaces, types, methods, properties, fields, events).
- \`mcp__eplan2025guide__eplan2025_guide_search\` / \`_get\` / \`_stats\` — P8 2025 **platform help** (user guide, dialogs, commands, concepts), crawled from www.eplan.help. Use this when the question is about the program, not about the API.
- \`mcp__eplan2026__eplan_search\` / \`eplan2026_get\` / \`eplan_stats\` — P8 2026 API reference plus platform help.
- \`mcp__eplan2027__eplan2027_search\` / \`_get\` / \`_stats\` — P8 2027 API reference plus platform help (use for 2027-only behaviour).
- \`mcp__eecpro__eecpro_search\` / \`eecpro_get\` / \`eecpro_stats\` — EEC Pro 2026 help.

If EPLAN is installed somewhere other than C:\\Program Files\\EPLAN\\Platform, the user sets that folder in the plugin's settings page (设置 → 插件 → dsh-eplan): the value is saved and handed to the MCP server as EPLAN_PLATFORM_ROOT. Reload the \`eplan\` MCP client after changing it, because the server reads the root once at start-up.

For a 2025 question prefer the 2025 servers: the API reference for identifiers, the guide for procedures. Load the \`eplan\`, \`eplan-scripting\`, \`eplan-docs\`, \`eplan-setup\` or \`eec-pro-development\` skills for detailed workflows.`

/** Folder that holds this plugin's own files (index.js, client.js, runtime/). */
function bundleRoot() {
  try {
    return path.dirname(fileURLToPath(import.meta.url))
  } catch {
    return process.cwd()
  }
}

function readJsonVersion(root) {
  try {
    const text = fs.readFileSync(path.join(root, 'package.json'), 'utf8')
    return JSON.parse(text).version || 'unknown'
  } catch {
    return 'unknown'
  }
}

export function apply(ctx, config) {
  // Deliberately NOT in inject: settings/webServer are optional services, and
  // listing them here would stop the plugin from activating in a headless or
  // CLI profile that has no web server at all.
  let order = 500
  try {
    order = ctx.systemPrompt.getSectionOrder('MCP_SERVERS') - 1
  } catch {
    // Placement names are owned by the runtime; fall back to a neutral order.
  }
  ctx.systemPrompt.section({
    name: 'eplan:integration',
    order,
    interpolate: false,
    text: GUIDANCE,
  })

  const root = bundleRoot()
  const store = createRootStore(root)

  // webServer.register() only returns a disposer, so it has to be registered
  // inside webCtx.effect — otherwise every route outlives an unload and the
  // duplicate path throws on the next activation.
  ctx.inject(['webServer'], (webCtx) => {
    webCtx.effect(() => registerRoutes(webCtx.webServer, store), 'dsh-eplan: install path routes')
    webCtx.effect(() => registerVersionRoutes(webCtx.webServer, root), 'dsh-eplan: version routes')
  })

  // Keep the resolved Python path (written by setup.ps1) in the diagnostics the
  // settings page shows, so a broken runtime is visible where the path is set.
  ctx.inject(['webServer'], (webCtx) => {
    webCtx.effect(
      () =>
        webCtx.webServer.register({
          kind: 'exact',
          path: '/api-eplan/health',
          handler: async (req, res) => {
            let python = null
            try {
              python = fs
                .readFileSync(path.join(root, 'runtime', 'python-path.txt'), 'utf8')
                .split(/\r?\n/)[0]
                .trim()
            } catch {
              python = null
            }
            let pythonExists = false
            try {
              pythonExists = Boolean(python) && fs.existsSync(python)
            } catch {
              pythonExists = false
            }
            res.writeHead(200, { 'content-type': 'application/json' })
            res.end(
              JSON.stringify({
                ok: true,
                version: readJsonVersion(root),
                root,
                python: python || null,
                pythonExists,
                launcher: store.launcher,
              }),
            )
          },
        }),
      'dsh-eplan: health route',
    )
  })

  void config
}