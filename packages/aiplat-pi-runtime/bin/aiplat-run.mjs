#!/usr/bin/env node
/**
 * Thin launcher: prefer `pi` CLI with this package as a local extension source.
 *
 * Usage:
 *   AIPLAT_APP_HOME=/path/to/app aiplat-run
 *   aiplat-run -- --print "hello"
 */
import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PKG = resolve(__dirname, "..");
const extra = process.argv.slice(2);

const args = ["-e", PKG, ...extra];
const child = spawn("pi", args, {
  stdio: "inherit",
  env: process.env,
  shell: false,
});

child.on("error", (err) => {
  console.error(
    "aiplat-run: failed to spawn `pi`. Install with:\n" +
      "  npm install -g --ignore-scripts @earendil-works/pi-coding-agent\n" +
      "or: curl -fsSL https://pi.dev/install.sh | sh\n",
    err.message,
  );
  process.exit(127);
});

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 1);
});
