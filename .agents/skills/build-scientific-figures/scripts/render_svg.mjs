#!/usr/bin/env node
/** Optional cross-platform SVG renderer backed by Sharp and PDFKit. */

import fs from "node:fs/promises";
import fsSync from "node:fs";
import path from "node:path";
import process from "node:process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function parseArgs(argv) {
  const args = { input: null, output: null, format: null, dpi: 180 };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (!args.input && !value.startsWith("-")) args.input = value;
    else if (value === "--output" || value === "-o") args.output = argv[++index];
    else if (value === "--format") args.format = argv[++index];
    else if (value === "--dpi") args.dpi = Number(argv[++index]);
    else if (value === "--help" || value === "-h") args.help = true;
    else throw new Error(`Unknown argument: ${value}`);
  }
  return args;
}

function usage() {
  return "Usage: node render_svg.mjs input.svg --output output.png|pdf --format png|pdf [--dpi 180]";
}

async function writePdf(PDFDocument, pngBuffer, output, dpi) {
  const sharp = require("sharp");
  const metadata = await sharp(pngBuffer).metadata();
  if (!metadata.width || !metadata.height) throw new Error("Rendered PNG has no dimensions.");
  const pageWidth = (metadata.width * 72) / dpi;
  const pageHeight = (metadata.height * 72) / dpi;
  await new Promise((resolve, reject) => {
    const document = new PDFDocument({ autoFirstPage: false, margin: 0, compress: true });
    const stream = fsSync.createWriteStream(output);
    stream.on("finish", resolve);
    stream.on("error", reject);
    document.on("error", reject);
    document.pipe(stream);
    document.addPage({ size: [pageWidth, pageHeight], margin: 0 });
    document.image(pngBuffer, 0, 0, { width: pageWidth, height: pageHeight });
    document.end();
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    process.stdout.write(`${usage()}\n`);
    return;
  }
  if (!args.input || !args.output || !["png", "pdf"].includes(args.format)) throw new Error(usage());
  if (!(args.dpi >= 36 && args.dpi <= 1200)) throw new Error("--dpi must be between 36 and 1200.");
  const sharp = require("sharp");
  const input = path.resolve(args.input);
  const output = path.resolve(args.output);
  await fs.mkdir(path.dirname(output), { recursive: true });
  const pngBuffer = await sharp(input, { density: args.dpi }).png().toBuffer();
  if (args.format === "png") {
    await fs.writeFile(output, pngBuffer);
  } else {
    const PDFDocument = require("pdfkit");
    await writePdf(PDFDocument, pngBuffer, output, args.dpi);
  }
  process.stdout.write(`${JSON.stringify({ input, output, format: args.format, dpi: args.dpi })}\n`);
}

main().catch((error) => {
  process.stderr.write(`ERROR: ${error?.stack || error}\n`);
  process.exitCode = 1;
});
