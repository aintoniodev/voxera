/**
 * Stock Assets Agent Plugin (Pixabay · Freesound · Jamendo) — pi extension
 *
 * Registers a /pixabay command (setup/status) and provisions the MCP server
 * entry in ~/.pi/agent/mcp.json. The stock-assets skill ships from
 * ~/.agents/skills/stock-assets (shared by all agent harnesses on this machine).
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { homedir } from "node:os";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Resolve extension directory: __dirname in CJS, import.meta.url in ESM
declare const __dirname: string | undefined;
const EXT_DIR =
  typeof __dirname !== "undefined"
    ? __dirname
    : path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1"));

// os.homedir() is C:\Users\<user> on Windows regardless of the shell (Git Bash
// sets HOME=/c/Users/<user>, which Node path-joins to a wrong drive-relative
// location). Never use process.env.HOME for config paths.
const HOME_DIR = homedir() || process.env.USERPROFILE || process.env.HOME;

const MCP_CONFIG_PATH = path.join(HOME_DIR, ".pi", "agent", "mcp.json");

const PIXABAY_CONFIG_PATH = path.join(HOME_DIR, ".pi", "agent", "pixabay-config.json");

// ── Helpers ──────────────────────────────────────────────────────────────────

function ensureMcpEntry(): void {
  try {
    const dir = path.dirname(MCP_CONFIG_PATH);
    fs.mkdirSync(dir, { recursive: true });

    let config: Record<string, any> = {};
    if (fs.existsSync(MCP_CONFIG_PATH)) {
      try {
        const raw = fs.readFileSync(MCP_CONFIG_PATH, "utf-8");
        config = JSON.parse(raw);
      } catch {
        console.error("[pixabay] Warning: could not parse mcp.json, will overwrite");
        config = {};
      }
    }

    if (!config.mcpServers) config.mcpServers = {};

    config.mcpServers["pixabay"] = {
      command: "python",
      args: [path.join(EXT_DIR, "mcp-server", "pixabay_server.py")],
      directTools: true,
      lifecycle: "lazy",
    };

    fs.writeFileSync(MCP_CONFIG_PATH, JSON.stringify(config, null, 2) + "\n", "utf-8");
  } catch (err) {
    console.error("[pixabay] Failed to ensure MCP entry:", err);
  }
}

// ── Extension factory ────────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  // 1. Ensure MCP entry on session start
  pi.on("session_start", async () => {
    ensureMcpEntry();
  });

  // 2. Motivate automatic asset fetching: every turn's system prompt reminds
  //    the agent to use the pixabay_* tools for stock media instead of asking.
  pi.on("before_agent_start", async (event) => {
    const guidance =
      "\n- Stock media: when the user needs ANY visual or audio asset (photos, illustrations, vectors, videos/b-roll, thumbnails, cover art, backgrounds, placeholders, sound effects, ambient audio, or music tracks), do NOT ask where to get it — use the pixabay_* MCP tools (pixabay_search_images, pixabay_search_videos, pixabay_search_sfx, pixabay_search_music to find candidates, then pixabay_download_image/video/sfx/music to save them into the project media directory). Follow the stock-assets skill workflow.";
    return { systemPrompt: event.systemPrompt + guidance };
  });

  // 3. Register /pixabay command
  pi.registerCommand("pixabay", {
    description: "Pixabay/Freesound/Jamendo MCP + skill setup and status",
    handler: async (args, ctx) => {
      const sub = (args || "").trim().toLowerCase();

      if (sub === "setup") {
        // Read existing config to preserve current values
        let existing: Record<string, string> = {};
        try {
          if (fs.existsSync(PIXABAY_CONFIG_PATH)) {
            existing = JSON.parse(fs.readFileSync(PIXABAY_CONFIG_PATH, "utf-8"));
          }
        } catch { /* ignore */ }

        // --- Pixabay key ---
        let pixabayKey = process.env.PIXABAY_API_KEY?.trim() || "";
        if (!pixabayKey && ctx.hasUI) {
          pixabayKey =
            (await ctx.ui.input("Pixabay API key (https://pixabay.com/api/docs/):", existing.apiKey || "")) || "";
        }
        // If still empty and existing has a value, keep existing
        if (!pixabayKey && existing.apiKey) {
          pixabayKey = existing.apiKey;
        }

        if (!pixabayKey) {
          ctx.ui.notify(
            "Error: No Pixabay API key provided. Set PIXABAY_API_KEY env var or run /pixabay setup with UI.",
            "error",
          );
          return;
        }

        // --- Freesound token ---
        let freesoundToken = process.env.FREESOUND_TOKEN?.trim() || "";
        if (!freesoundToken && ctx.hasUI) {
          freesoundToken =
            (await ctx.ui.input("Freesound API token (https://freesound.org/apiv2/apply/, optional):", existing.freesoundToken || "")) || "";
        }
        if (!freesoundToken && existing.freesoundToken) {
          freesoundToken = existing.freesoundToken;
        }

        // --- Jamendo client_id ---
        let jamendoClientId = process.env.JAMENDO_CLIENT_ID?.trim() || "";
        if (!jamendoClientId && ctx.hasUI) {
          jamendoClientId =
            (await ctx.ui.input("Jamendo client_id (https://developer.jamendo.com, optional):", existing.jamendoClientId || "")) || "";
        }
        if (!jamendoClientId && existing.jamendoClientId) {
          jamendoClientId = existing.jamendoClientId;
        }

        // Write merged config
        try {
          const dir = path.dirname(PIXABAY_CONFIG_PATH);
          fs.mkdirSync(dir, { recursive: true });
          fs.writeFileSync(
            PIXABAY_CONFIG_PATH,
            JSON.stringify(
              {
                apiKey: pixabayKey,
                freesoundToken: freesoundToken || "",
                jamendoClientId: jamendoClientId || "",
              },
              null,
              2,
            ) + "\n",
            "utf-8",
          );
        } catch (err) {
          ctx.ui.notify(`Error writing config: ${err}`, "error");
          return;
        }

        // Ensure MCP entry
        ensureMcpEntry();

        ctx.ui.notify(
          "Pixabay/Freesound/Jamendo keys guardados. Reinicia pi o /reload si los tools MCP aún no aparecen.",
          "info",
        );
        return;
      }

      if (sub === "status") {
        const lines: string[] = [];

        // Read config once
        let config: Record<string, string> = {};
        try {
          if (fs.existsSync(PIXABAY_CONFIG_PATH)) {
            config = JSON.parse(fs.readFileSync(PIXABAY_CONFIG_PATH, "utf-8"));
          }
        } catch { /* ignore */ }

        // --- Pixabay ---
        let pixabayKey = process.env.PIXABAY_API_KEY?.trim() || config.apiKey || "";
        if (pixabayKey) {
          const masked = "****" + pixabayKey.slice(-4);
          lines.push(`Pixabay API key: configured (${masked})`);
        } else {
          lines.push("Pixabay API key: NOT configured (run /pixabay setup)");
        }

        // --- Freesound ---
        let freesoundToken = process.env.FREESOUND_TOKEN?.trim() || config.freesoundToken || "";
        if (freesoundToken) {
          const masked = "****" + freesoundToken.slice(-4);
          lines.push(`Freesound token: configured (${masked})`);
        } else {
          lines.push("Freesound token: NOT configured (optional — /pixabay setup)");
        }

        // --- Jamendo ---
        let jamendoClientId = process.env.JAMENDO_CLIENT_ID?.trim() || config.jamendoClientId || "";
        if (jamendoClientId) {
          const masked = "****" + jamendoClientId.slice(-4);
          lines.push(`Jamendo client_id: configured (${masked})`);
        } else {
          lines.push("Jamendo client_id: NOT configured (optional — /pixabay setup)");
        }

        // Check mcp.json
        let hasMcpEntry = false;
        try {
          if (fs.existsSync(MCP_CONFIG_PATH)) {
            const data = JSON.parse(fs.readFileSync(MCP_CONFIG_PATH, "utf-8"));
            hasMcpEntry = !!data.mcpServers?.["pixabay"];
          }
        } catch { /* ignore */ }
        lines.push(`mcp.json entry: ${hasMcpEntry ? "present" : "MISSING"}`);

        // Skill location (shared ~/.agents/skills)
        lines.push(`Skill: ${path.join(HOME_DIR, ".agents", "skills", "stock-assets")}`);

        ctx.ui.notify(lines.join("\n"), "info");
        return;
      }

      // Default: show usage
      ctx.ui.notify("Uso: /pixabay setup | status", "info");
    },
  });
}
