import { copyFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const packageRoot = path.join(appRoot, "node_modules", "pdfjs-dist");
const publicRoot = path.join(appRoot, "public");
const licenseRoot = path.join(publicRoot, "licenses");

await mkdir(licenseRoot, { recursive: true });
await copyFile(path.join(packageRoot, "build", "pdf.worker.min.mjs"), path.join(publicRoot, "pdf.worker.min.mjs"));
await copyFile(path.join(packageRoot, "LICENSE"), path.join(licenseRoot, "PDFJS-LICENSE.txt"));
console.log("Prepared the local PDF.js worker and license for the web app.");
