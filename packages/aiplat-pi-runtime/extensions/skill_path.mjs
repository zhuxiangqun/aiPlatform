/**
 * Skill directory names used to locate skills/<name>/handler.py.
 * Rejects empty, absolute, and traversal names before any path join.
 */
import { existsSync, realpathSync } from "node:fs";
import { join, sep } from "node:path";

export function safeSkillDirName(skill) {
  const name = String(skill || "").trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$/.test(name)) return "";
  return name;
}

/** Phase 0 fixture only, unless AIPLAT_HANDLER_ECHO=1. */
export function allowHandlerEcho(skill) {
  const raw = (process.env.AIPLAT_HANDLER_ECHO || "").trim().toLowerCase();
  if (raw === "1" || raw === "true" || raw === "yes" || raw === "on") return true;
  const name = safeSkillDirName(skill);
  return name === "fixture" || name === "fixture-skill";
}

/**
 * Absolute handler.py under root/skills-style root, or "" if missing / escaped.
 * `root` is the skills directory, not the app home.
 */
export function handlerPyUnderRoot(root, skill) {
  const name = safeSkillDirName(skill);
  if (!name || !root) return "";
  const rootAbs = String(root);
  if (!existsSync(rootAbs)) return "";
  const candidate = join(rootAbs, name, "handler.py");
  if (!existsSync(candidate)) return "";
  const rootReal = realpathSync(rootAbs);
  const fileReal = realpathSync(candidate);
  const prefix = rootReal.endsWith(sep) ? rootReal : `${rootReal}${sep}`;
  if (!fileReal.startsWith(prefix)) return "";
  return fileReal;
}
