/* global window, document, fetch */
// lib/client.js — DSH Web half of the EPLAN plugin: the install-path setting.
//
// The browser cannot read the filesystem, so every read/write goes through the
// host routes registered by index.js (/api-eplan/*). Two seats are registered
// because the settings UI moved between DSH generations:
//   * DSH 0.2 — "设置 → 插件 → dsh-eplan" renders the plugins.bundle.config slot
//                (key = package name);
//   * older hosts — no plugins.bundle.config slot and no configForms service, so
//                the settings.section page keeps working.
window.__ModuleLoader__.load({
  id: "dsh-eplan",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    const React = require("react");
    const { useState, useEffect, useRef } = React;
    const h = React.createElement;

    const LOCALE_NS = "eplan";

    const DICT = {
      zh: {
        "settings.title": "EPLAN 安装路径",
        "settings.description":
          "EPLAN MCP 服务器从这里查找已安装的 Platform 版本。默认位置是 C:\\Program Files\\EPLAN\\Platform；装在别处时在下面指定。",
        "settings.label": "EPLAN Platform 目录",
        "settings.placeholder": "例如 D:\\EPLAN\\Platform",
        "settings.probe": "检测",
        "settings.browse": "浏览…",
        "settings.save": "保存",
        "settings.reset": "恢复自动识别",
        "settings.use": "使用",
        "settings.pick": "使用此目录",
        "settings.up": "上级目录",
        "settings.close": "收起",
        "settings.reload":
          "保存后需要重新加载 eplan MCP 客户端（或在「插件」页停用再启用 dsh-eplan）才会生效，因为服务器在启动时只读取一次该路径。",
        "settings.file": "记录文件",
        "settings.none": "未检测到 EPLAN Platform，请手动指定。",
        "settings.empty": "该目录下没有子文件夹。",
        "settings.loading": "正在读取…",
        "settings.versions": "版本",
        "settings.noVersions": "无可用版本",
        "status.saved": "已保存。重新加载 eplan MCP 客户端后生效。",
        "status.reset": "已恢复自动识别。重新加载 eplan MCP 客户端后生效。",
        "status.valid": "有效：找到 {n} 个版本。",
        "status.invalid": "该目录不是 EPLAN Platform 根目录（需要包含 Bin/Eplan.EplApi.RemoteClientu.dll 的子文件夹）。",
        "status.missing": "目录不存在。",
        "error.state": "无法读取设置：{msg}",
        "error.save": "保存失败：{msg}",
        "error.route": "宿主路由不可用：{msg}",
        "source.saved": "手动指定",
        "source.env": "环境变量 EPLAN_PLATFORM_ROOT",
        "source.registry": "注册表",
        "source.common": "默认位置",
      },
      en: {
        "settings.title": "EPLAN install path",
        "settings.description":
          "The EPLAN MCP server looks for installed Platform versions here. The default is C:\\Program Files\\EPLAN\\Platform; set another folder when EPLAN lives elsewhere.",
        "settings.label": "EPLAN Platform folder",
        "settings.placeholder": "e.g. D:\\EPLAN\\Platform",
        "settings.probe": "Check",
        "settings.browse": "Browse…",
        "settings.save": "Save",
        "settings.reset": "Back to auto-detect",
        "settings.use": "Use",
        "settings.pick": "Use this folder",
        "settings.up": "Parent",
        "settings.close": "Collapse",
        "settings.reload":
          "Reload the eplan MCP client afterwards (or disable and re-enable dsh-eplan on the Plugins page): the server reads this path once at start-up.",
        "settings.file": "Recorded in",
        "settings.none": "No EPLAN Platform found — set the folder manually.",
        "settings.empty": "No subfolders here.",
        "settings.loading": "Loading…",
        "settings.versions": "Versions",
        "settings.noVersions": "No usable version",
        "status.saved": "Saved. Reload the eplan MCP client to apply it.",
        "status.reset": "Auto-detection restored. Reload the eplan MCP client to apply it.",
        "status.valid": "Valid: {n} version(s) found.",
        "status.invalid": "Not an EPLAN Platform root (it needs a subfolder with Bin/Eplan.EplApi.RemoteClientu.dll).",
        "status.missing": "That folder does not exist.",
        "error.state": "Cannot read the setting: {msg}",
        "error.save": "Save failed: {msg}",
        "error.route": "Host route unavailable: {msg}",
        "source.saved": "set manually",
        "source.env": "EPLAN_PLATFORM_ROOT",
        "source.registry": "registry",
        "source.common": "default location",
      },
    };

    let localeSvc = null;

    function fill(text, params) {
      if (!params) return text;
      return String(text).replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m));
    }

    function useTranslate() {
      const [, force] = useState(0);
      useEffect(() => {
        if (!localeSvc) return undefined;
        try {
          return localeSvc.subscribe(() => force((x) => x + 1));
        } catch (_) {
          return undefined;
        }
      }, []);
      return (key, params) => {
        if (!localeSvc) return fill(DICT.zh[key] || key, params);
        try {
          return localeSvc.bind(LOCALE_NS)(key, params);
        } catch (_) {
          return fill(DICT.zh[key] || key, params);
        }
      };
    }

    // Same semantic tokens the other plugin pages use, so light/dark themes and
    // skins work without any per-theme code here.
    const COLORS = Object.freeze({
      surface: "var(--dsw-alias-bg-layer-3)",
      border: "var(--dsw-alias-border-l2)",
      field: "var(--dsw-alias-bg-layer-1)",
      text: "var(--dsw-alias-label-primary)",
      dim: "var(--dsw-alias-label-secondary)",
      dimmer: "var(--dsw-alias-label-tertiary)",
      accent: "var(--dsw-alias-brand-primary)",
      accentForeground: "var(--dsw-alias-label-primary-foreground)",
      hover: "var(--dsw-alias-interactive-bg-hover)",
      success: "var(--dsw-alias-state-success-primary)",
      error: "var(--dsw-alias-state-error-primary)",
    });

    const MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

    async function postJson(routePath, body) {
      const resp = await fetch(routePath, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      let data = null;
      try {
        data = await resp.json();
      } catch (_) {
        data = null;
      }
      return { ok: resp.ok && !!(data && data.ok), status: resp.status, data };
    }

    const errorText = (err) => String((err && err.message) || err);

    function chip(text, tone) {
      const color = tone === "ok" ? COLORS.success : tone === "bad" ? COLORS.error : COLORS.dim;
      return h(
        "span",
        {
          key: text,
          style: {
            display: "inline-block",
            padding: "1px 8px",
            margin: "0 6px 6px 0",
            borderRadius: "999px",
            border: "1px solid " + COLORS.border,
            background: COLORS.field,
            color: color,
            fontSize: "12px",
            whiteSpace: "nowrap",
          },
        },
        text,
      );
    }

    function button(label, onClick, options) {
      const opts = options || {};
      return h(
        "button",
        {
          type: "button",
          onClick: opts.disabled ? undefined : onClick,
          disabled: !!opts.disabled,
          style: {
            padding: "6px 14px",
            fontSize: "13px",
            borderRadius: "8px",
            cursor: opts.disabled ? "default" : "pointer",
            opacity: opts.disabled ? 0.5 : 1,
            border: opts.primary ? "none" : "1px solid " + COLORS.border,
            background: opts.primary ? COLORS.accent : COLORS.field,
            color: opts.primary ? COLORS.accentForeground : COLORS.text,
            fontWeight: opts.primary ? 600 : 400,
            flex: "none",
          },
        },
        label,
      );
    }

    function versionsOf(list) {
      return Array.isArray(list) ? list : [];
    }

    /** Small row used for both the candidate list and the folder browser. */
    function row(key, title, note, trailing, onClick, highlighted) {
      return h(
        "div",
        {
          key: key,
          onClick,
          style: {
            display: "flex",
            alignItems: "center",
            gap: "10px",
            padding: "8px 10px",
            borderRadius: "10px",
            border: "1px solid " + (highlighted ? COLORS.accent : COLORS.border),
            background: COLORS.field,
            cursor: onClick ? "pointer" : "default",
          },
        },
        h(
          "div",
          { style: { flex: "1", minWidth: "0" } },
          h(
            "div",
            {
              style: {
                fontSize: "12.5px",
                fontFamily: MONO,
                color: COLORS.text,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              },
            },
            title,
          ),
          note
            ? h("div", { style: { fontSize: "11.5px", color: COLORS.dimmer, marginTop: "2px" } }, note)
            : null,
        ),
        trailing || null,
      );
    }

    function InstallPathSection() {
      const t = useTranslate();
      const [state, setState] = useState(null);
      const [draft, setDraft] = useState("");
      const [listing, setListing] = useState(null);
      const [busy, setBusy] = useState(false);
      const [error, setError] = useState(null);
      const [notice, setNotice] = useState(null);
      const [probeNote, setProbeNote] = useState(null);
      const alive = useRef(true);

      useEffect(() => {
        alive.current = true;
        return () => {
          alive.current = false;
        };
      }, []);

      const adopt = (data) => {
        if (!alive.current) return;
        setState(data);
        setDraft((current) => (current === "" && data.effective ? data.effective : current));
      };

      const load = () => {
        setError(null);
        postJson("/api-eplan/state", {})
          .then((res) => {
            if (!alive.current) return;
            if (res.ok) adopt(res.data);
            else setError(t("error.state", { msg: (res.data && res.data.error) || res.status }));
          })
          .catch((err) => {
            if (alive.current) setError(t("error.route", { msg: errorText(err) }));
          });
      };

      useEffect(() => {
        load();
      }, []);

      const run = (promise) => {
        setBusy(true);
        setNotice(null);
        setError(null);
        return promise
          .then((res) => {
            if (!alive.current) return res;
            setBusy(false);
            if (!res.ok) {
              setError((res.data && res.data.error) || t("error.save", { msg: res.status }));
            } else if (res.data && res.data.candidates) {
              adopt(res.data);
            }
            return res;
          })
          .catch((err) => {
            if (!alive.current) return null;
            setBusy(false);
            setError(t("error.route", { msg: errorText(err) }));
            return null;
          });
      };

      const save = (value) =>
        run(postJson("/api-eplan/save", { root: value })).then((res) => {
          if (res && res.ok) {
            setNotice(t("status.saved"));
            setProbeNote(null);
            setListing(null);
          }
          return res;
        });

      const probe = (value) =>
        run(postJson("/api-eplan/probe", { root: value })).then((res) => {
          if (!res || !res.ok) return res;
          const info = (res.data && res.data.probe) || {};
          if (info.valid) setProbeNote(t("status.valid", { n: versionsOf(info.versions).length }));
          else if (info.exists === false) setProbeNote(t("status.missing"));
          else setProbeNote(t("status.invalid"));
          return res;
        });

      const openBrowser = (value) => {
        const start = String(value || "").trim();
        return run(postJson("/api-eplan/browse", start ? { path: start } : {})).then((res) => {
          if (res && res.ok && res.data && res.data.listing) {
            setListing(res.data.listing);
            if (res.data.listing.path) setDraft(res.data.listing.path);
          }
          return res;
        });
      };

      const clear = () =>
        run(postJson("/api-eplan/reset", {})).then((res) => {
          if (res && res.ok) {
            setNotice(t("status.reset"));
            setProbeNote(null);
            setListing(null);
            setDraft("");
          }
          return res;
        });

      const sourceLabel = (source) => {
        const key = "source." + String(source || "");
        const text = t(key);
        return text === key ? String(source || "") : text;
      };

      const effective = state && state.effective ? state.effective : null;
      const versions = versionsOf(state && state.effectiveVersions);

      const browser = listing
        ? h(
            "div",
            {
              style: {
                border: "1px solid " + COLORS.border,
                borderRadius: "12px",
                padding: "10px",
                display: "flex",
                flexDirection: "column",
                gap: "8px",
                background: COLORS.surface,
              },
            },
            h(
              "div",
              { style: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" } },
              listing.parent ? button(t("settings.up"), () => openBrowser(listing.parent), { disabled: busy }) : null,
              h(
                "div",
                {
                  style: {
                    flex: "1",
                    minWidth: "120px",
                    fontSize: "12px",
                    fontFamily: MONO,
                    color: COLORS.dim,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  },
                },
                listing.path || "",
              ),
              button(t("settings.pick"), () => draft && save(draft), { primary: true, disabled: busy || !(listing.valid || draft) }),
              button(t("settings.close"), () => setListing(null)),
            ),
            listing.drives && listing.drives.length
              ? h(
                  "div",
                  { style: { display: "flex", gap: "6px", flexWrap: "wrap" } },
                  listing.drives.map((drive) => button(drive, () => openBrowser(drive))),
                )
              : null,
            listing.entries && listing.entries.length
              ? h(
                  "div",
                  { style: { display: "flex", flexDirection: "column", gap: "6px", maxHeight: "260px", overflowY: "auto" } },
                  listing.entries.map((entry) =>
                    row(
                      entry.path,
                      entry.name,
                      entry.valid
                        ? t("settings.versions") + ": " + versionsOf(entry.versions).map((v) => v.full_version || v.name).join(", ")
                        : null,
                      entry.valid ? chip(t("settings.use"), "ok") : null,
                      () => openBrowser(entry.path),
                      entry.valid,
                    ),
                  ),
                )
              : h("div", { style: { fontSize: "12px", color: COLORS.dimmer } }, t("settings.empty")),
          )
        : null;

      return h(
        "div",
        {
          style: {
            padding: "20px 24px",
            display: "flex",
            flexDirection: "column",
            gap: "14px",
            maxWidth: "720px",
          },
        },
        h("div", { style: { fontSize: "15px", fontWeight: 600, color: COLORS.text } }, t("settings.title")),
        h("div", { style: { fontSize: "12.5px", color: COLORS.dim, lineHeight: "1.6" } }, t("settings.description")),

        // ── the one path control ────────────────────────────────────────────
        // A single box: the path in use, the field to change it, and the
        // detected versions underneath. Everything the old design split over
        // three blocks (in use / detected / manual) is now one input, because
        // all three described the same value.
        h(
          "div",
          {
            style: {
              border: "1px solid " + COLORS.border,
              borderRadius: "12px",
              padding: "12px 14px",
              background: COLORS.field,
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            },
          },
          h("div", { style: { fontSize: "12.5px", color: COLORS.dim } }, t("settings.label")),
          h(
            "div",
            { style: { display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" } },
            h("input", {
              type: "text",
              value: draft,
              placeholder: t("settings.placeholder"),
              spellCheck: false,
              onChange: (event) => setDraft(event.target.value),
              onKeyDown: (event) => {
                if (event.key === "Enter" && draft && !busy) save(draft);
              },
              style: {
                flex: "1 1 260px",
                minWidth: "180px",
                padding: "7px 10px",
                fontSize: "12.5px",
                fontFamily: MONO,
                color: COLORS.text,
                background: COLORS.field,
                border: "1px solid " + COLORS.border,
                borderRadius: "8px",
                outline: "none",
              },
            }),
            button(t("settings.probe"), () => probe(draft), { disabled: busy || !draft }),
            button(t("settings.browse"), () => openBrowser(draft), { disabled: busy }),
            button(t("settings.save"), () => save(draft), { primary: true, disabled: busy || !draft }),
            state && state.saved ? button(t("settings.reset"), clear, { disabled: busy }) : null,
          ),
          effective || state
            ? h(
                "div",
                { style: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" } },
                versions.length
                  ? versions.map((v) => chip((v.full_version || v.name) + " · " + (v.runtime || "?"), "ok"))
                  : h("span", { style: { fontSize: "11.5px", color: COLORS.error } }, t("settings.none")),
                effective && state && state.effectiveSource
                  ? h("span", { style: { fontSize: "11.5px", color: COLORS.dimmer } }, sourceLabel(state.effectiveSource))
                  : null,
              )
            : null,
          probeNote ? h("div", { style: { fontSize: "12px", color: COLORS.dim } }, probeNote) : null,
        ),

        browser,

        notice ? h("div", { style: { fontSize: "12px", color: COLORS.success } }, notice) : null,
        error ? h("div", { style: { fontSize: "12px", color: COLORS.error } }, error) : null,
        h("div", { style: { fontSize: "11.5px", color: COLORS.dimmer, lineHeight: "1.6" } }, t("settings.reload")),
      );
    }

    const name = "dsh-eplan";
    const inject = ["slots", "locale"];

    function apply(ctx) {
      const locale = ctx.get ? ctx.get("locale") : undefined;
      if (locale && typeof locale.register === "function" && typeof locale.bind === "function") {
        localeSvc = locale;
        // ctx.effect owns the disposer: an unload must not leave the dictionaries
        // registered (a second apply would then collide on the namespace).
        ctx.effect(() => locale.register(LOCALE_NS, { zh: DICT.zh, en: DICT.en }), "dsh-eplan: locale");
      }

      const label = () => (localeSvc ? localeSvc.bind(LOCALE_NS)("settings.title") : DICT.zh["settings.title"]);
      const slots = ctx.get ? ctx.get("slots") : undefined;
      if (!slots || typeof slots.inject !== "function" || typeof slots.register !== "function") return;

      // Every slot registration goes through slots.inject: registering into a
      // slot the host did not declare at apply time throws, and a throw here
      // fails renderer boot (white screen).
      slots.inject("plugins.bundle.config", () =>
        slots.register({ name: "plugins.bundle.config", key: name, label }, InstallPathSection),
      );

      // Older hosts (no configForms service): the setting lives on its own page
      // in the settings sidebar instead. On 0.2 this self-disables, because the
      // plugin page above already shows the same form.
      slots.inject("settings.section", () => {
        const forms = ctx.get ? ctx.get("configForms") : undefined;
        if (forms) return undefined;
        return slots.register(
          { name: "settings.section", id: "eplan", order: 23, label, locale: LOCALE_NS, inject: () => ({}) },
          InstallPathSection,
        );
      });
    }

    exports.name = name;
    exports.inject = inject;
    exports.apply = apply;
    return module.exports;
  },
});
