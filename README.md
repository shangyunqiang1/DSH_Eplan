# DSH_Eplan

把 [Bochica](https://github.com/Canary-ECAD/bochica) 的 EPLAN 能力移植成 **DeepSeek Harness 插件（bundle）**：
在本机直接操控 EPLAN Electric P8 2025，并离线查阅 2025 / 2026 / 2027 / EEC Pro 文档，附带 5 个技能。

相对 Bochica 的两个关键差异：

1. **新增 EPLAN P8 2025 的版本精确离线文档索引（API 参考 + 平台帮助两部分）。** Bochica 的托管文档只覆盖
   2026 / 2027 / EEC Pro（`rag2025.covaga.xyz` 不存在），EPLAN_Skills 也写明「P8 2025 的接口应结合本机核对」。
   本插件一方面解析本机安装的 `Eplan.EplApi.*u.xml`（12 个程序集、36,493 个成员）生成 API 索引，另一方面
   一次性爬取官方帮助站的 `Plattform/2025` 用户手册（2,691 页：对话框、设置、命令、概念、提示信息）——两者
   都是版本精确、全程离线、每条结果带官方帮助页 URL。
2. **全部文档本地化（五套索引）。** 2026 / 2027 / EEC Pro 原本依赖 Canary E-cad 的云托管 RAG 服务（查询会离开
   本机）；本插件改为一次性爬取官方帮助站 `www.eplan.help`，写入本地 SQLite（`data\eplan2026-help.sqlite` 等），
   之后所有检索都在本机完成，不再联网。同时补上了原方案完全没有的 **2025 平台用户手册**（2,691 页）。

> API 参考 ≠ 用户手册：`eplan2025` 只有 .NET 类型/成员（写脚本、做插件用），`eplan2025guide` 才是「这个对话框
> 在哪、这个选项什么意思、这个流程怎么走」的手册内容。提问时先分清是哪一类；查不到通常说明用错了服务，而不是
> 文档缺失。

## 提供的能力

| MCP 服务器 | 工具前缀 | 说明 |
| --- | --- | --- |
| `eplan` | `mcp__eplan__*` | 本地 EPLAN 自动化。eplan-mcp v1.3.0（上游 tag，commit `77a78f63`；与 Bochica 同源），discovery 模式发布 15 个工具（12 个连接/动作目录核心 + 3 个发现元工具，含 `eplan_list_dialogs` / `eplan_click_dialog_button` 用于 EPLAN 被弹窗卡住时）；约 236 个隐藏类型化工具（full 模式共 248 个）通过 `eplan_tools_call` 调用，约 1150 个原始 action 通过 `eplan_action_run` 调用。每个工具带 MCP 注解与 `canary-ecad/eplan` 安全事实。通过 Remote Client 驱动正在运行的 EPLAN。 |
| `eplan2025` | `mcp__eplan2025__*` | EPLAN P8 2025.0.3 的 .NET **API 离线参考**（36,493 个成员，全文检索 + 按成员/类型查看，带 Source URL）。**纯本地**。 |
| `eplan2025guide` | `mcp__eplan2025guide__*` | P8 2025 **平台用户手册**离线索引（2,691 页：对话框/Settings、命令调用路径、工艺流程、提示信息；`_search` / `_get` / `_stats`）。**纯本地**。 |
| `eplan2026` | `mcp__eplan2026__*` | 本地爬取的 P8 2026 API 参考 + 平台帮助（SQLite FTS5，`category` 区分 API/User Guide）。**纯本地**。 |
| `eplan2027` | `mcp__eplan2027__*` | 本地爬取的 P8 2027 API 参考 + 平台帮助，支持按页读取。**纯本地**。 |
| `eecpro` | `mcp__eecpro__*` | 本地爬取的 EEC Pro 2026 帮助（参考公式、EEC CAD/PLC/脚本、管理、参考命令）。**纯本地**。 |

本机装的是 P8 2025，所以 `eplan2026`、`eplan2027` 两行**默认关闭**（`disabled: true`），装好后只有 2025 在运行；
需要时到 **设置 → 插件** 打开。六行 MCP 在插件列表里各自显示真实名称（EPLAN 远程连接 / P8 2025 · API 参考 /
P8 2025 · 平台帮助 / P8 2026 · 文档 / P8 2027 · 文档 / EEC Pro · 文档），不再是一串同名
`@deepseek-ai/dsh-mcp-client`——实现见下文「为什么插件列表里能分开显示」。

技能（`skills/`）：`eplan`（路由 + 连接/安全）、`eplan-scripting`（C# 脚本与 API，来自 Canary 上游）、
`eplan-docs`（五套文档的版本纪律、API vs 手册分流与引用规则）、`eec-pro-development`（EEC Pro，来自 Canary
上游）、`eplan-setup`（安装/验证/修复/重建索引与爬取）。五个技能的 `description` 都按「触发分支」重写：
任务是冲着正在运行的程序来的就进 `eplan`，写代码进 `eplan-scripting`，问名字/菜单/选项进 `eplan-docs`，
EEC Pro 进 `eec-pro-development`，插件本身坏了进 `eplan-setup`。正文按「步骤在前、参考资料靠指针」组织，
细节（动作清单、API 陷阱、Job Server 等 15 篇）留在 `references/` 里，由正文按任务指向。

此外主插件（`index.js`）会向系统提示注入 `eplan:integration` 一节：说明本机版本、工具发现流程、
安全规则和文档路由，使新会话无需先加载技能也知道插件存在。

## 与 Bochica 的对应关系

| Bochica | 本插件 |
| --- | --- |
| `eplan`（stdio，`EPLAN_MCP_MODE=full`，248 工具） | `eplan`（stdio，默认 `discovery`，15 工具 = 12 核心 + 3 元工具），需要时可切回 full |
| `eplan-docs-2027`（https://rag2027.covaga.xyz/mcp，必选） | `eplan2027`（**改为本地爬取**，同一套 2027 帮助页） |
| `eplan-docs-2026`（https://rag2026.covaga.xyz/mcp，可选） | `eplan2026`（**改为本地爬取**，同一套 2026 帮助页） |
| `eec-pro-docs`（https://rageecpro.covaga.xyz/mcp，可选） | `eecpro`（**改为本地爬取**，EEC Pro 2026 官方帮助） |
| —（无 2025） | `eplan2025` + `eplan2025guide`（**新增**，本地离线：API 索引 + 平台用户手册） |
| `eplan-scripting-skill` / `eec-pro-skill` | `skills/eplan-scripting` / `skills/eec-pro-development`（MIT，保留许可证与出处） |
| Consult / Tasks / Draw 三种系统提示 | `index.js` 的 `eplan:integration` 区块 + `eplan` / `eplan-docs` / `eplan-setup` 技能 |

## 安装

前置条件：

1. 已安装 EPLAN Electric P8 2025（本机为 `C:\Program Files\EPLAN\Platform\2025.0.3`），并在
   **文件 → 设置 → 工作站 → 接口 → 远程访问** 勾选「允许通过 Remote Client 远程访问」。
2. Python 3.12+（本机为 3.13），具备 `mcp`（>=1.19,<2，v1.3.0 的 tool annotations 需要）与 `pythonnet`。
   默认复用 EPLAN_Skills 环境（实际解释器路径由 `setup.ps1` 探测并写入 `runtime\python-path.txt`），
   也可用 `-Python <路径>` 指定；setup 还会回退到 Bochica 内置解释器、`py` 启动器和 PATH。
   **vendor 已随插件入库，不依赖 Bochica 安装目录。**
3. DeepSeek Harness（desktop profile）。
4. 只在首次构建/更新 2025 平台手册与 2026、2027、EEC Pro 本地索引时需要能访问 `www.eplan.help`；
   2025 的 API 索引完全来自本机安装的 XML。

```powershell
# 1) 初始化：解析 Python、探测 EPLAN 安装路径、构建 2025 API 索引
#    先进入插件根目录（解压出来的那个目录，换盘符不影响后续任何步骤）
Set-Location "C:\path\to\DSH_Eplan"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1

# 2) 在 DSH 里安装这个目录：插件 → 安装 → 选上面的插件根目录
#    （也可以用 git 地址安装，见下）
```

`setup.ps1` 会：校验并写入 `runtime\python-path.txt`；定位 EPLAN 安装路径并写入
`runtime\eplan-platform-root.txt`（已经选过就保留用户的选择）；把 `.cmd` 启动器规范为 CRLF；
校验 `vendor/eplan-mcp` 完整性与六个启动器是否齐全；构建 `data\eplan2025.sqlite`
（约 35 MB / 4 秒）。可选参数：`-Python <路径>`、`-PlatformRoot <路径>`、`-RebuildIndex`、`-SkipIndex`。

`cordis.patch.yml` 里**没有任何绝对路径**：每个 MCP 行都用 `cmd.exe` 加一个相对启动器名
（`scripts\launch-*.cmd`）启动，`cwd` 由 `!!js` 在加载时按已安装包的位置算出来。所以插件装在哪个盘、
哪个目录都不用改文件；换机器、升级、重新解压都不会把路径写错。

装好后**默认挂 4 个** MCP 服务器：`mcp__eplan__*`（本地 EPLAN 自动化）、`mcp__eplan2025__*`（2025 API）、
`mcp__eplan2025guide__*`（2025 手册）、`mcp__eecpro__*`（EEC Pro 2026 帮助）。`mcp__eplan2026__*` 与
`mcp__eplan2027__*` 在 `cordis.patch.yml` 里是 `disabled: true`：它们的索引来自 Release 资源，没解压到
`data\` 之前打开也只会报缺库，需要时到 **设置 → 插件** 打开即可。**技能目录在会话开始时构建**，5 个技能
（eplan / eplan-scripting / eplan-docs / eec-pro-development / eplan-setup）需要新开一个会话
（或重启 DSH）后才会出现在技能列表里。系统提示中的 `eplan:integration` 区块同样随即生效。

验证：

| 检查 | 期望 |
| --- | --- |
| `mcp__eplan__eplan_versions` | `2025` / `2025.0.3`，runtime `netfx` |
| `mcp__eplan__eplan_status` | `connected: false` 直到 `eplan_connect`；连接后 `api_loaded: true` |
| `mcp__eplan__eplan_tools_search({query:"pdf"})` | 返回 `eplan_export_pdf_project` 等类型化工具 |
| `mcp__eplan2025__eplan2025_stats` | EPLAN 2025.0.3，36,493 个成员，库大小约 35 MB |
| `mcp__eplan2025__eplan2025_get({name:"Eplan.EplApi.DataModel.ProjectManager.OpenProject"})` | 3 个重载，含参数/返回/异常/备注 |
| `mcp__eplan2025guide__eplan2025_guide_stats` | 2,691 页平台手册，库大小约 11 MB |
| `mcp__eplan2025guide__eplan2025_guide_search({query:"connection numbering"})` | 返回对话框/流程页，带 `/Plattform/2025/Content/htm/` Source URL |
| `mcp__eplan2026__eplan_stats` / `mcp__eplan2027__eplan2027_stats` / `mcp__eecpro__eecpro_stats` | 各自报告本地页数与库大小 |

### EPLAN 安装路径（自动识别 / 手动选择）

装到非默认位置（默认 `C:\Program Files\EPLAN\Platform`）时不必改代码，也不用手工编辑 YAML：

**设置 → 插件 → dsh-eplan → EPLAN Platform 目录**

整个页面只有一个路径框：

- 打开即自动识别并填入当前生效的路径，优先级为「已保存的选择 → 环境变量 `EPLAN_PLATFORM_ROOT` → 注册表
  `HKLM\SOFTWARE\EPLAN\EPLAN W3\Platform`（含 WOW6432Node）→ `Program Files` / `Program Files (x86)`
  下的 `EPLAN\Platform` 与 `Platform*` 兄弟目录」。识别到的版本与 runtime 以标签显示在框下方。
- 换路径就用同一个框：直接粘贴绝对路径（粘错到版本目录如 `…\Platform\2025.0.3` 会自动提升到父目录
  `…\Platform`），或点「浏览…」用内置目录浏览器逐级点选（盘符、上级目录、子目录，含
  `Bin\Eplan.EplApi.RemoteClientu.dll` 的目录高亮），再点「保存」。回车等于「保存」，「检测」只校验不写入。
- 选择结果写入 `runtime\eplan-platform-root.txt`（无 BOM 单行）。`scripts\launch-eplan-mcp.cmd` 启动时读它并
  `set EPLAN_PLATFORM_ROOT`，vendor 的 `eplan_connection.py:58` 就用这个值扫版本 —— **不改 vendor 代码**。
  文件缺失或路径失效时启动器打印一条 stderr 提示并回落到默认路径，不会让服务器起不来。
- **改完要重新加载 `eplan` MCP 客户端**（插件页停用/启用该条目，或重启 DSH）：`PLATFORM_ROOT` 是模块级常量，
  服务器只在进程启动时读一次。设置页底部也写了这句提示。
- 「恢复自动识别」删除该文件，回到默认探测顺序。`setup.ps1` 同样会写这个文件，但**不会覆盖你已经选好的有效路径**；
  命令行指定用 `-PlatformRoot <路径>` 或环境变量 `EPLAN_PLATFORM_ROOT`。

宿主侧实现：`lib/platform.js`（探测/校验/目录浏览）、`lib/routes.js`（`POST /api-eplan/state|probe|browse|save|reset`）、
`index.js` 注册路由与 `GET /api-eplan/health`、`client.js`（设置页两个 seat：`plugins.bundle.config` 与旧宿主的
`settings.section`）。`client.js` 由 `package.json` 的 `exports["./client"]` + `dsh.client` 声明，宿主按
`/plugins/…` 组合下发。

### 连接状态指示（已连接 / 未连接）

插件详情页标题右侧有一个彩色状态灯，每 5 秒自动刷新，页面打开时也能一眼看出 EPLAN 是否真的连上：

| 显示 | 含义 | 怎么处理 |
| --- | --- | --- |
| 🟢 **EPLAN 已连接** | EPLAN 进程在跑，且宿主里 `mcp__eplan__*` 工具已注册 | 可以直接出图 |
| ⚪ **EPLAN 已启动 · MCP 未连上** | EPLAN 进程在跑，但 MCP 工具已注销（重连预算耗尽） | 重启 DSH，或在插件页停用/启用 `eplan` |
| ⚪ **EPLAN 已启动** | 进程在跑；宿主工具注册表读不到（非 Web 宿主） | 只需确认 EPLAN 已打开 |
| ⚪ **MCP 已就绪 · EPLAN 未运行** | 工具在，但 EPLAN.exe 没启动 | 打开 EPLAN Electric P8 |
| 🔴 **EPLAN 未运行** | 两者都没有 | 启动 EPLAN |
| ⚪ **连接状态未知** | 非 Windows 宿主或探测失败 | 不影响其它功能 |

探测由宿主完成（浏览器看不到进程）：`lib/connection.js` 先用 `tasklist` 拿到 `EPLAN.exe` 的 PID，
再用 `netstat -ano -p TCP` 找 **该 PID** 正在监听的端口（remoting 端口是动态的，49152 只是常见首选），
同时读宿主工具注册表判断 `mcp__eplan__*` 是否还在。结果经 `GET /api-eplan/connection` 下发，
宿主侧缓存约 1.2 秒，前端轮询不会把机器压满（一次探测约 300 ms）。

> **不要用「TCP 能连 127.0.0.1:49152」判断已连接**：EPLAN 只把 remoting 端口绑在网卡地址上
> （本机实测是 192.168.x.x / 169.254.x.x），回环探测必然 `ECONNREFUSED`，但 `eplan_connect` 依然成功。
> 这也是 `lib/connection.js` 从 PID 反查端口、而不是假定端口的原因。

### 开着代理时的连接问题（必须清代理变量）

EPLAN 的 Remote Client 走 gRPC，底层是 **原生 C-core 通道**——它读进程环境里的 `HTTP_PROXY` /
`HTTPS_PROXY` / `ALL_PROXY`，并且**对局域网和回环目标也一样走代理**。代理隧道在 EPLAN 的 remoting
端口上被丢弃后，`eplan_connect` 就报 gRPC `failed to connect to all addresses`（`grpc_status 14`）；
同一时刻用裸 TCP/h2c 直连同一个 `host:port` 却是通的，很容易误判成「EPLAN 没开远程访问」。

- `NO_PROXY=*` **不管用**（C-core 不透传该变量），必须把变量本身清空。
- 清理必须发生在 **python 启动之前**：`scripts\launch-eplan-mcp.cmd` 在 `set` `EPLAN_PLATFORM_ROOT`
  之后、调用解释器之前，清掉 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`（含小写）、`GRPC_PROXY`（含小写）
  与 `NODE_USE_ENV_PROXY` 共 9 个变量。在服务器进程里 `del os.environ` 太晚——gRPC 在客户端初始化时已读走。
- `C:\Users\<用户>\.dsh\.env` 里的代理变量只在 `launch-*` 这类 `.cmd` 之前生效；它不含
  `EPLAN_PLATFORM_ROOT`，影响的是整个 DSH 进程的环境，与 EPLAN 安装在哪个目录无关。
- **升级插件会覆盖启动器**，重新打补丁前先确认这段 `rem --- Strip HTTP proxy variables` 还在。

### 版本记录与插件内更新

插件详情页（**设置 → 插件 → dsh-eplan**）自带版本记录，不依赖插件市场：

- 标题旁的 `v0.2.5` 由宿主本身绘制；检测到更新的版本时后面再跟一个 **「可更新到 x.y.z」** 徽标，
  顶部操作区同时出现 **「更新到 x.y.z」** 按钮（在「卸载」左边）。
- 页面底部的 **版本记录** 一节列出当前版本、最新版本、检查来源和发布记录（取自 `versions.json`），
  并提供「检查更新」按钮和 GitHub Release 链接。

为什么不用宿主自带的更新按钮：本插件是 `link:` 协议安装的本地目录，没有 npm `installTarget`，
宿主 `updateAvailable()` 因此恒为 false，插件市场也明确不给 `link:` 来源提供更新。缺口由本插件自己补：

| 文件 | 作用 |
| --- | --- |
| `versions.json` | 发布台账，最新在前；同时就是 GitHub `main` 上的远端清单 |
| `lib/versions.js` | `POST /api-eplan/version`（状态）、`POST /api-eplan/version/update`（更新）；`compareVersions`、`versionStatus`、`applyUpdate` |
| `client.js` | 通过 `plugins.detail.{badge,actions,section}` 三个宿主插槽注入徽标、按钮、版本记录节 |

判定与更新行为：

- `latest` 取「本地 `versions.json` 首条」与「远端清单首条」中较大者，`updateAvailable = latest > current`。
  远端取不到（离线/404）时回落本地台账，`source` 显示 `offline`，界面照常可用。
- 更新时先尽力 `git fetch` + `git pull --ff-only origin main`（仅在远端领先且工作区干净时），
  否则把 `package.json#version` 对齐到目标版本——`link:` 安装本来就指向工作树，文件已就位即可生效。
- 更新完成后需要**在插件页停用再启用 dsh-eplan**（或重启 DSH）让宿主重新读取 bundle，页面会提示这一点。

要发布新版本：改 `package.json#version` → 在 `versions.json` 顶部加一条记录（`version` / `date` / `notes.zh` / `notes.en`）
→ 提交并推到 `main`。用户在插件页点「检查更新」就能看到，再点「更新到 …」由 `applyUpdate` 落地。

宿主侧实现补充：版本逻辑在 `lib/versions.js`，`index.js` 用 `webCtx.effect(() => registerVersionRoutes(webCtx.webServer, root), …)`
注册路由；三个插槽组件对其它插件页返回 `null`，只在 `subject.pkg.name === "dsh-eplan"` 时渲染。

## 离线文档

五套文档索引都只读本地 SQLite，查询不联网。

> **不想自己重建？** 五套已构建好的索引（约 199 MB）不进 git 历史，而是作为
> [GitHub Release 附件](https://github.com/shangyunqiang1/DSH_Eplan/releases/tag/offline-indexes-v0.2.3)
> 提供：下载 `DSH_Eplan-offline-indexes.zip`，解压到插件根目录，让五个 `.sqlite` 落在 `data\` 下，
> 重新加载 MCP 客户端即可开箱即用。下面的命令用于在别的机器上从头重建。

### 2025：API 参考来自本机 XML，用户手册来自官方帮助站

**（a）API 参考，版本精确，无需联网也不需要下载**

- 数据源：`C:\Program Files\EPLAN\Platform\2025.0.3\Bin\Eplan.EplApi.{AF,Base,CommandLineActions,DataModel,EServices,Gui,HEServices,MasterData,RemoteClient,Remoting,Starter,System}u.xml`
  （12 个文件；`assembly` 名从文件名推断，因为 XML 内的 `<assembly><name>` 通常为空）。
- 规模：**36,493** 个成员 — type 1,246 / method 8,064 / property 15,287 / field 11,895 / event 1；
  其中 36,478 个有文档文本。按程序集：DataModel 22,823、AF 3,666、MasterData 3,327、Base 1,527 等。
- 重建（先 `cd` 到插件根目录；`--xml-dir` 换成本机 EPLAN 的 `Bin` 目录）：
  ```powershell
  $bundle = (Get-Location).Path
  python "$bundle\scripts\build-eplan2025-index.py" `
    --xml-dir "C:\Program Files\EPLAN\Platform\2025.0.3\Bin" `
    --out "$bundle\data\eplan2025.sqlite"
  ```
- 索引结构：`member(id, assembly, kind, name, ns, type_name, member_name, signature, summary, remarks, params, returns, exceptions, url, has_doc)`、
  `meta(key, value)`、FTS5 虚表 `fts(name, member_name, summary, params)`（external content，`bm25` 加权
  name 8 / member_name 6 / summary 1 / params 0.5）。
- 工具：
  - `eplan2025_search({query, topK, kind, assembly})` — FTS5 前缀检索；短词、点号全名、中文走 LIKE 回退。
  - `eplan2025_get({name})` — 按全名/签名头/短成员名/类型名解析，一次返回所有重载（参数、返回、异常、备注、Source URL）。
  - `eplan2025_type({type})` — 类型摘要 + 方法/属性/字段/事件分组列表。
  - `eplan2025_stats()` — 版本、构建时间、来源目录、计数、库大小。
- URL 规则与官方帮助一致：
  `https://www.eplan.help/en-us/Infoportal/Content/api/2025/<Assembly>u~<Type>[~<Member>(<Args>)].html`
  （`{}` 显示为 `<>`，参数用短类型名，如 `OpenProject(String,OpenMode)`）。
- 限制：只有 .NET API 参考，没有界面说明、操作流程和图片——这些在下面的（b）。

**（b）平台用户手册（Plattform/2025），一次性爬取，2,691 页**

- 数据源：`https://www.eplan.help/en-us/Infoportal/Content/Plattform/2025/Content/htm/`，
  页名清单取自同目录的 `sitemap.xml`（2,693 个 HTML 条目）。
- 覆盖内容：对话框与 Settings 说明、命令的「Dialog call:」调用路径、操作流程、概念章节、提示/报错信息条目——
  也就是「这个按钮在哪、这个选项什么意思」这类问题。
- 与 API 索引互补：把界面里看到的名字（如 `Connection numbering`）丢给 `eplan2025_guide_search`，
  把代码里的类型/成员（如 `PathMap.ReSubstitutePath`）丢给 `eplan2025_search`。
- 工具：`eplan2025_guide_search({query, topK, category})`、`eplan2025_guide_get({path, offset})`、
  `eplan2025_guide_stats()`；Source URL 形如
  `https://www.eplan.help/en-us/Infoportal/Content/Plattform/2025/Content/htm/<page>.htm`。
- 只抓正文文本：不保存图片、截图和 JS 目录树，所以「请给我看这张图」这类需求本地无法满足。
- 注意 sitemap 陷阱：官方各版本 sitemap 在发布之间被整包复制，2025 的 sitemap 里写的其实还是
  `Plattform/2023/...` 路径。因此 `guide` 模式只取页名、再按本版本目录重拼 URL
  （`load_sitemap(..., flatten_prefix=…)`），这也是它需要 `--version` 的原因。

### 2025 手册 / 2026 / 2027 / EEC Pro：一次性爬取官方帮助站

`scripts/build-help-index.py` 是唯一需要联网的环节：它把 `www.eplan.help` 的公开帮助页抓下来，写入本地
SQLite + FTS5，之后 MCP 服务器只读本地库。

```powershell
# 先 cd 到插件根目录（见「安装」一节），下面所有路径都由 $bundle 派生
$bundle = (Get-Location).Path
$py = Get-Content "$bundle\runtime\python-path.txt"

# 手册页名清单来自官方各版本 sitemap.xml。robots.txt 禁止自动抓 *.xml，
# 所以每个版本手工下载一次、缓存到本地（该目录已被 .gitignore 忽略）：
$sitemaps = Join-Path $bundle "_recon\sitemaps"
New-Item -ItemType Directory -Force -Path $sitemaps | Out-Null
Invoke-WebRequest -UseBasicParsing -OutFile (Join-Path $sitemaps "plattform2025.xml") `
  "https://www.eplan.help/en-us/Infoportal/Content/Plattform/2025/sitemap.xml"
Invoke-WebRequest -UseBasicParsing -OutFile (Join-Path $sitemaps "plattform2026.xml") `
  "https://www.eplan.help/en-us/Infoportal/Content/Plattform/2026/sitemap.xml"
Invoke-WebRequest -UseBasicParsing -OutFile (Join-Path $sitemaps "plattform2027.xml") `
  "https://www.eplan.help/en-us/Infoportal/Content/Plattform/2027/sitemap.xml"
Invoke-WebRequest -UseBasicParsing -OutFile (Join-Path $sitemaps "eecpro2026.xml") `
  "https://www.eplan.help/en-us/infoportal/content/eecpro/2026/sitemap.xml"

# 2025 平台用户手册（独立库）
& $py "$bundle\scripts\build-help-index.py" guide --version 2025 `
  --sitemap (Join-Path $sitemaps "plattform2025.xml") `
  --out "$bundle\data\eplan2025-guide.sqlite" --workers 10

# 2026 API 参考：从 webindex.html 取种子，顺着每个类型的 "_members" 页找全部成员页
& $py "$bundle\scripts\build-help-index.py" api --version 2026 `
  --out "$bundle\data\eplan2026-help.sqlite" --workers 12
# 2026 平台用户手册：并入同一个库（topic 页与 API 页共存，靠 category 区分）
& $py "$bundle\scripts\build-help-index.py" guide --version 2026 `
  --sitemap (Join-Path $sitemaps "plattform2026.xml") `
  --out "$bundle\data\eplan2026-help.sqlite" --workers 10

# 2027 API 参考 + 平台用户手册
& $py "$bundle\scripts\build-help-index.py" api --version 2027 `
  --out "$bundle\data\eplan2027-help.sqlite" --workers 12
& $py "$bundle\scripts\build-help-index.py" guide --version 2027 `
  --sitemap (Join-Path $sitemaps "plattform2027.xml") `
  --out "$bundle\data\eplan2027-help.sqlite" --workers 10

# EEC Pro 2026：sitemap.xml 里列出的全部 HTML 页
& $py "$bundle\scripts\build-help-index.py" sitemap `
  --sitemap (Join-Path $sitemaps "eecpro2026.xml") `
  --prefix  https://eplan.help/en-US/infoportal/Content/EECPro/2026/Content/htm/ `
  --out "$bundle\data\eecpro-help.sqlite" --workers 8
```

sitemap 缓存到 `_recon\sitemaps\`（robots.txt 禁止自动抓 `*.xml`，所以每个版本手工下载一次；上面的
命令已包含下载步骤，新克隆的仓库整段执行即可）。若不想手工下载，也可省略 `guide` 命令的
`--sitemap`，脚本会自行读取该版本的官方 `sitemap.xml`；2025 API 索引的重建命令见本节（a）。

- 断点续爬：已成功（HTTP 200）的页面不会重复请求，404 也会记住；中断后重跑同一条命令即可补齐。
- 页表：`page(id, path, url, title, breadcrumb, kind, assembly, type_name, member_name, body, status, fetched_at)`，
  FTS5 虚表 `fts(title, body)`（external content），`meta` 存版本/来源/构建时间/计数；
  `page` 上的 AFTER INSERT/UPDATE/DELETE 触发器和 FTS 同步，爬完还会统一 `rebuild` 一次。
- 只重建全文索引（不联网，排查「页数正常但搜不到」时用；沿用上一命令块里的 `$bundle` / `$py`）：
  ```powershell
  & $py "$bundle\scripts\build-help-index.py" reindex `
    --out "$bundle\data\eplan2026-help.sqlite"
  ```
- 页面正文取自帮助页的正文容器（Innovasys 的 `#i-body-content`、MadCap 的 `#mainbody`），
  每页保留原始 Source URL，回答可精确引用。
- 已构建完成的实际规模（本机 2026-11-04）：

  | 文档集 | 规模 | 构成 | 正文字符 | 库大小 |
  | --- | --- | --- | --- | --- |
  | 2025 API（XML） | 36,493 个成员 | type 1,246 / method 8,064 / property 15,287 / field 11,895 / event 1 | — | 35.5 MB |
  | 2025 平台手册 | 2,691 页 | topic 2,691（sitemap 全量） | 6.3 M | 11.6 MB |
  | 2026 | 25,024 页 | member 20,281 / topic 2,981 / type 1,018 / members 714 / namespace 30 | 33.5 M | 72.2 MB |
  | 2027 | 26,360 页 | member 21,391 / topic 3,037 / type 1,115 / members 781 / namespace 36 | 34.9 M | 75.2 MB |
  | EEC Pro 2026 | 1,971 页 | topic 1,971（sitemap 全量） | 2.1 M | 4.3 MB |

  2026 API 爬取约 34 分钟（22,346 页，10.8 页/秒，12 线程），2027 约 37 分钟（23,647 页，10.7 页/秒），
  EEC Pro 约 5 分钟（1,971 页，7.2 页/秒，8 线程）；2025/2026/2027 平台手册各约 6 分钟
  （2,691 / 2,705 / 2,748 页，7.9 页/秒，10 线程）。2026/2027 的手册页并入同一个库
  （topic 页从 278 → 2,981、291 → 3,037），靠 `category` 区分 API 与 User Guide。
- 已知限制：不含 PDF 手册与图片；2027 帮助站内容本身比 2026 少；官方站改版后需要重跑爬取。

## 使用示例

```text
连接并查看当前项目
  eplan_versions → eplan_connect → eplan_status → eplan_tools_call({name:"eplan_get_current_project"})

把项目导出为 PDF
  eplan_tools_search({query:"export pdf"}) → eplan_tools_describe({names:"eplan_export_pdf_project"})
  → eplan_tools_call({name:"eplan_export_pdf_project", arguments:{project_path:"…", export_path:"…"}})

按 GUI 名字找动作
  eplan_action_catalog({search:"Page macro"}) → eplan_action_describe({name:"…"})
  → eplan_action_run({name:"…", params:{…}, dry_run:true}) → 去掉 dry_run 执行

查 2025 API（写脚本用）
  eplan2025_get({name:"Eplan.EplApi.DataModel.ProjectManager.OpenProject"})
  eplan2025_type({type:"Eplan.EplApi.Base.PathMap"})

查 2025 界面/流程（操作 EPLAN 用）
  eplan2025_guide_search({query:"connection numbering"})
  eplan2025_guide_get({path:"…/Plattform/2025/Content/htm/wirenumberinggui_k_start.htm"})

查 2026 / 2027 / EEC Pro（本地）
  eplan_search({query:"ProjectManager OpenProject", category:"API Reference"})
  eplan_search({query:"schematic generation settings", category:"User Guide"})
  eplan2027_search({query:"InsertSymbol"}) → eplan2027_get({path:"…"})
  eecpro_search({query:"refformulas"})
```

## 配置

`cordis.patch.yml` 中的七行：

- `dsh-eplan` — 主插件，注入系统提示。
- `eplan-mcp`（`dsh-eplan/mcp/eplan`，显示为 **EPLAN 远程连接**）— stdio，经 `scripts\launch-eplan-mcp.cmd` 启动，
  `cwd` 为 `vendor\eplan-mcp\eplan-p8-mcp-server\mcp_server`。默认 `EPLAN_MCP_MODE=discovery`；
  改成 `full` 可获得 248 个独立工具（每个请求都要携带全部 schema，token 成本高）。
- `eplan-docs-2025`（`dsh-eplan/mcp/eplan2025`，**P8 2025 · API 参考**）— stdio，经 `scripts\launch-docs2025.cmd`。
- `eplan-guide-2025`（`dsh-eplan/mcp/eplan2025guide`，**P8 2025 · 平台帮助**）— stdio，经 `scripts\launch-docs2025guide.cmd`。
- `eplan-docs-2026` / `eplan-docs-2027`（**P8 2026 · 文档** / **P8 2027 · 文档**）— stdio，分别经 `scripts\launch-docs2026.cmd`、
  `launch-docs2027.cmd` 启动 `server\docs\server.py --docset …`，只读本地库。**默认关闭**（见下）。
- `eec-pro-docs`（`dsh-eplan/mcp/eecpro`，**EEC Pro · 文档**）— stdio，经 `scripts\launch-docseecpro.cmd`。

### 为什么插件列表里能分开显示

`cordis.patch.yml` 的每一行 `name:` 都是插件包内自带的小包 `dsh-eplan/mcp/<row>`（`mcp\<row>\index.js`
只做 `export * from "@deepseek-ai/dsh-mcp-client"`，`mcp\<row>\locale\{en,zh}.json` 提供标题与说明），
而不是六行同名 `@deepseek-ai/dsh-mcp-client`。DSH 的插件列表按包名读取 `locale` 里的 `meta.title`，
所以现在每行显示各自的名称（EPLAN 远程连接 / P8 2025 · API 参考 / …）。
根 `package.json` 为此导出了 `./mcp/*`、`./mcp/*/locale/en.json`、`./mcp/*/locale/zh.json` 三个入口
（Node 的单星号导出规则所限，必须逐文件列出，不能写成 `./mcp/*/locale/*.json`）。

### 2025 / 2026 / 2027 的默认开关

本机装的是 P8 2025，所以 `eplan2026`、`eplan2027` 两行在 `cordis.patch.yml` 里带 `disabled: true`，
装好后**只有 2025 在运行**（2025 API + 2025 平台帮助 + EEC Pro 文档 + 远程连接）。需要时到
**设置 → 插件** 打开对应开关即可，开关状态写在 profile 的 `cordis.patch.yml` 里，不会改回插件包。

相关环境变量/文件：`runtime\python-path.txt`（setup 写入）、`EPLAN_DATA_DIR`（统一指定五套索引所在目录）、
`EPLAN2025_DB` / `EPLAN2025_GUIDE_DB` / `EPLAN2026_DB` / `EPLAN2027_DB` / `EECPRO_DB`（逐个覆盖）、
`EPLAN_DSH_PYTHON`（setup 优先解释器）、`EPLAN_MCP_MODE`、`EPLAN_PLATFORM_ROOT`（EPLAN 安装根目录，见上一节；
通常由设置页写入 `runtime\eplan-platform-root.txt` 后自动注入）。动作调用超时为 600 秒（EPLAN 动作可能很慢）。

### 索引放在哪里

默认**跟随插件目录**，即 `<插件目录>\data\*.sqlite`（例如 `C:\path\to\DSH_Eplan\data\`，五个库共约
199 MB）。插件目录被 DSH 以 Junction 链接进 profile（`…\profiles\desktop\node_modules\dsh-eplan`），
所以只要原目录存在，索引就跟着走；整包拷贝到别处同样可用。

想让索引不跟着插件走（例如插件目录只读、或多人共用一个缓存），设置环境变量 `EPLAN_DATA_DIR` 指向任意目录，
再把五个 `.sqlite` 放进去即可；逐个覆盖用 `EPLAN2025_DB` 等。解析顺序：

```text
EPLAN2025_DB / … / EECPRO_DB   （单库覆盖，最高）
EPLAN_DATA_DIR\eplan2025.sqlite …（统一目录）
<插件目录>\data\eplan2025.sqlite …（默认）
```

`cordis.patch.yml` 里没有任何绝对路径：每行只写 `cmd.exe` 和一个相对启动器名（如 `scripts\launch-docs2025.cmd`），
`cwd` 由 `!!js` 表达式在加载时解析成当前插件目录，所以换机器/换盘符不用改 YAML，也不用先跑 `setup.ps1` 才能搬。
换机器真正要做的是机器本地的东西：重跑一次 `setup.ps1` 重写 `runtime\python-path.txt`、把五个 `.sqlite` 解压进 `data\`。

## 安全

- 只读优先：先 `eplan_status` / `eplan_get_current_project` / 搜索 / 导出到临时目录，不要为了「看看」打开或关闭用户的项目。
- 第一次修改类操作前先 `eplan_backup_project`，或确认用户已有备份；压缩、还原、升级同样按修改处理。
- 删除/清理类动作（delete、remove、purge、reorganize、discard、erase、destroy、wipe）必须在对话中明确批准并点名项目。v1.3.0 起工具自带 `canary-ecad/eplan` 注解（`destructive` / `changesProject` / `changesEplan`）；对 `eplan_live_batch`、`eplan_live_remove_placement`、`eplan_live_copy_pages_to_structure`、`eplan_remove_unused_user_properties`、`eplan_set_parts_data_source`、`eplan_restore_masterdata`、`eplan_partsmanagement_import`（mode 3 会替换主数据）、`eplan_dataportal_*` 一律先备份并获批。
- 动作在 `QuietModes.ShowNoDialogs` 下执行：返回 `{"success": false}` 是正常返回值而非异常，改完用只读查询复核。
- 文档检索全部本地：客户名、项目路径、物料号都可以放心作为检索词，不会离开本机。

## 目录结构

```text
<插件目录>   （即 $bundle 指向的位置）
├─ package.json / cordis.patch.yml / index.js / icon.svg / locale/
├─ client.js                        设置页（单个路径框）+ 连接状态灯 + 版本记录
├─ lib\platform.js · lib\routes.js  安装路径探测 / 宿主路由
├─ lib\connection.js                连接状态探测（EPLAN.exe PID → remoting 端口 → MCP 工具）
├─ mcp\<row>\                       行标题小包（eplan · eplan2025 · eplan2025guide · eplan2026 · eplan2027 · eecpro）
│            index.js 转发 @deepseek-ai/dsh-mcp-client，locale\{en,zh}.json 提供标题与说明
├─ scripts\  setup.ps1 · launch-eplan-mcp.cmd · launch-docs2025.cmd · launch-docs2025guide.cmd
│            launch-docs2026.cmd · launch-docs2027.cmd · launch-docseecpro.cmd
│            build-eplan2025-index.py · build-help-index.py
│            clean-dsh-auth-cookies.cmd / .ps1
│            （清 DSH 累积的 dsh-auth-* cookie；.cmd 兼作启动包装器）
├─ server\docs2025\server.py        离线 2025 API 文档 MCP（仅标准库）
├─ server\docs\server.py            离线 2025 手册 / 2026 / 2027 / EEC Pro 文档 MCP（仅标准库，--docset）
├─ data\eplan2025.sqlite            2025 API 索引（35.5 MB / 36,493 成员）
├─ data\eplan2025-guide.sqlite      2025 平台手册（11.6 MB / 2,691 页）
├─ data\eplan2026-help.sqlite       2026 API + 平台帮助（72.2 MB / 25,024 页）
├─ data\eplan2027-help.sqlite       2027 API + 平台帮助（75.2 MB / 26,360 页）
├─ data\eecpro-help.sqlite          EEC Pro 2026 帮助爬取索引（4.3 MB / 1,971 页）
│   （data\*.sqlite 与 _recon\ 均被 .gitignore 排除：数据库随 Release 附件 offline-indexes 分发，
│    新克隆的仓库需按「安装 / 重建索引」一节生成，不随源码提交）
├─ runtime\python-path.txt          setup 解析出的 Python 路径
├─ runtime\eplan-platform-root.txt  用户选的 EPLAN 安装根目录（设置页写入；可选，缺失则自动识别）
├─ versions.json                    版本台账（最新在前），同时也是 GitHub main 上的远端清单
├─ lib\versions.js                  版本状态 / 更新实现（/api-eplan/version*）
├─ vendor\eplan-mcp\                eplan-mcp v1.3.0 @ 77a78f63（MIT；来源见 vendor\eplan-mcp\PROVENANCE.md）
├─ skills\                          eplan · eplan-scripting · eplan-docs · eec-pro-development · eplan-setup
├─ licenses\                        MIT 许可证副本
├─ README.md / THIRD_PARTY_NOTICES.md
└─ _recon\                          开发期探针/爬取日志（.gitignore 排除，不随插件包分发，可删除）
```

## 排错

| 现象 | 处理 |
| --- | --- |
| 会话里没有 EPLAN 工具 | 服务器没起来。在终端运行 `scripts\launch-eplan-mcp.cmd` 看 stderr；确认 `runtime\python-path.txt` 指向真实解释器。 |
| EPLAN 装在非默认目录，`eplan_versions` 报 `No EPLAN installation found under …` | 在 设置 → 插件 → dsh-eplan 里选对根目录（要选到 `…\EPLAN\Platform` 这一层，含 `2025.0.3` 子目录），然后**重新加载 `eplan` MCP 客户端**。 |
| 设置页改了路径但报错还在 | `PLATFORM_ROOT` 在服务器进程启动时读一次。到插件页把 `eplan` 条目停用再启用，或重启 DSH；用 `GET /api-eplan/health` 可确认宿主侧插件已加载。 |
| 设置 → 插件 → dsh-eplan 里没有「EPLAN Platform 目录」 | 插件没重新加载：改动 `client.js`/`index.js` 后需要重启 DSH（或触发 profile 重组合）才会下发新 bundle。 |
| 插件列表里六行又变成同一个 `@deepseek-ai/dsh-mcp-client` | `mcp\<row>\` 小包丢了，或 `package.json` 少了 `./mcp/*` 三个导出（`./mcp/*`、`./mcp/*/locale/en.json`、`./mcp/*/locale/zh.json`）；注意不能写成 `./mcp/*/locale/*.json`，Node 只替换一个 `*`。 |
| 在插件页打开了 2026/2027，重启后又关了 | 开关写在 profile 的 `cordis.patch.yml`；如果那里没有、只有插件包里的 `disabled: true`，就说明插件包被重装覆盖了。重新在插件页打开即可，插件包的默认值不会被改成 2025 以外。 |
| 设置页显示「未检测到」但 EPLAN 确实装了 | 手动粘贴路径，或用浏览器按钮从盘符逐级进去；也确认安装目录下确实有 `<版本>\Bin\Eplan.EplApi.RemoteClientu.dll`。 |
| 详情页没有「更新到 …」按钮和版本记录 | 三点依次排查：`client.js` 是否含 `plugins.detail.section`（旧 bundle 没有）；`POST /api-eplan/version` 是否 200（`lib/versions.js` 没注册说明 `index.js` 版本旧）；`versions.json` 首条是否高于 `package.json#version`——没有更高版本时按钮按设计不显示。 |
| `ModuleNotFoundError: mcp` / `clr` | 解释器不对。`setup.ps1 -Python <带 mcp 和 pythonnet 的 python>`。 |
| `eplan_connect` 报 gRPC "failed to connect to all addresses" | 先排除代理：`HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY`（含 `GRPC_PROXY`、`NODE_USE_ENV_PROXY`）会让 gRPC 的 C-core 栈把局域网/回环目标也塞进代理隧道，隧道在 remoting 端口被断开就报 status 14 —— 此时 `NO_PROXY=*` 无效，必须清空变量；`scripts\launch-eplan-mcp.cmd` 已在 python 启动前清掉这 9 个变量。其次才是：未开远程访问 / EPLAN 没启动 / 端口不是 49152。用 `netstat -ano | findstr LISTENING` 对照 EPLAN.exe 的 PID 查真实端口。 |
| DSH 启动即退出，日志有 `desktop welcome: Web authentication failed` | 随机端口导致 `dsh-auth-*` cookie 每启动一次新增一个、旧的只叠加不覆盖，Cookie 头涨过 Node 默认 16 KB 上限后被 431 拒掉。退出 DSH 后运行 `scripts\clean-dsh-auth-cookies.cmd`（或把开始菜单快捷方式指向它，启动前自动清理，并附带 `NODE_OPTIONS=--max-http-header-size=1048576` 兜底）。 |
| 详情页没有连接状态灯 | 三点依次排查：`client.js` 是否含 `plugins.detail.badge#dsh-eplan-connection`（旧 bundle 没有）；`GET /api-eplan/connection` 是否 200（`lib/connection.js` 没注册说明 `index.js` 版本旧）；返回的 `state` 是否为 `unknown`（非 Windows 宿主）。 |
| 连到了错误的 EPLAN 版本 / `eplan_connect` 回报 2026 | 只装 2025 时自动检测仍可能报 2026：显式 `eplan_connect({version:"2025"})` 再让服务器加载 DLL；一个进程只能加载一个大版本，换版本要重启 DSH。v1.3.0 的 2027 专用工具仅对 2027 生效。 |
| EPLAN 突然不响应、两分钟后断连 | 2025 的 `eplan_dataportal_add_to_download_list` 会弹出 Data Portal 模态窗口且脚本不返回：让用户在该窗口下载并关闭后再继续；期间不要重复排队。 |
| `eplan2025_search` 没结果 / stats 找不到库 | 重建索引；确认 `--xml-dir` 指向已安装平台的 `Bin`。 |
| 查界面/流程找不到，但 API 能查到 | 用错了服务：改用 `eplan2025_guide_search`（2025 手册）或 2026/2027 的 `category:"User Guide"`。 |
| 2025 手册搜不到，但 `eplan2025_guide_stats` 页数正常 | 全文索引与页表不同步：`build-help-index.py reindex --out data\eplan2025-guide.sqlite`。 |
| 2026/2027/EEC Pro 工具消失或 stats 页数极少 | 对应本地库缺失或爬取未完成。重跑 `build-help-index.py`（会断点续爬）；或运行对应 `launch-docs*.cmd` 看 stderr。 |
| 2025、2026 都查不到某个名字 | 它可能是 EPLAN 动作或界面选项而非 .NET 成员，改用 `eplan_action_catalog` / 手册检索。 |
| 工具已出现但技能列表里没有 | 技能目录按会话构建：新开会话或重启 DSH 即可，无需重装。 |
| 中文输出乱码 | 两端均已强制 UTF-8；若仍乱码，检查是否绕过了 `.cmd` 启动器直接运行 `.py`。 |

## 许可

本插件 MIT。第三方组件与文档版权见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)；上游均为 MIT
（eplan-mcp、eplan-scripting-skill、eec-pro-skill、Bochica），EPLAN 帮助页内容版权归 EPLAN GmbH，
本地爬取仅作个人/内部离线检索使用，不再分发。eplan-cloudflare-rags 只是早期托管方案的参考，本插件运行时不依赖它。