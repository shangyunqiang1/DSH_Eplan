// Row package for the EPLAN remote-client connection.
//
// Every MCP row needs its own package name so that 设置 → 插件 can show a real
// title instead of the shared "@deepseek-ai/dsh-mcp-client" for all of them.
// The plugin-manager reads display text from readPluginMeta(specifier, base):
// the package behind the row's `name` contributes package.json + locale/*.json.
// This package is only that name: it re-exports the MCP client unchanged, and
// the row's config in cordis.patch.yml still does all the work.
export * from "@deepseek-ai/dsh-mcp-client";
