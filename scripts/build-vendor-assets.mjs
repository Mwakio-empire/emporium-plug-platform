import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const destination = resolve(projectRoot, "static", "vendor", "htmx.min.js");
const source = resolve(projectRoot, "node_modules", "htmx.org", "dist", "htmx.min.js");

await mkdir(dirname(destination), { recursive: true });
await copyFile(source, destination);
