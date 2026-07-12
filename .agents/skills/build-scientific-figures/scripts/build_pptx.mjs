#!/usr/bin/env node
/** Build an optional editable PPTX view of a v1 figure specification.
 *
 * The canonical source remains the JSON spec plus SVG. This backend uses public
 * PptxGenJS when installed and intentionally fails with exit code 3 when the
 * optional package is unavailable.
 */

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);

async function readJsonFile(filePath) {
  const raw = await fs.readFile(filePath, "utf8");
  return JSON.parse(raw.replace(/^\uFEFF/, ""));
}

function parseArgs(argv) {
  const args = { spec: null, output: null };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (!args.spec && !value.startsWith("-")) args.spec = value;
    else if (value === "--output" || value === "-o") args.output = argv[++index];
    else if (value === "--help" || value === "-h") args.help = true;
    else throw new Error(`Unknown argument: ${value}`);
  }
  return args;
}

function usage() {
  return "Usage: node build_pptx.mjs figure-spec.json --output figure.pptx";
}

function resolveColor(value, theme, fallback = "000000") {
  if (typeof value !== "string" || !value) return fallback;
  const resolved = value.startsWith("@") ? theme?.palette?.[value.slice(1)] : value;
  return String(resolved || `#${fallback}`).replace(/^#/, "").slice(0, 6).toUpperCase();
}

function mergeTheme(base, override) {
  return {
    ...base,
    ...override,
    palette: { ...(base?.palette || {}), ...(override?.palette || {}) },
  };
}

function edgePoints(edge, ports) {
  if (Array.isArray(edge.points) && edge.points.length >= 2) return edge.points;
  const start = ports.get(edge.from);
  const end = ports.get(edge.to);
  if (!start || !end) throw new Error(`Edge ${edge.id} references an unknown port.`);
  if (edge.route === "orthogonal" && start.x !== end.x && start.y !== end.y) {
    const middleX = (start.x + end.x) / 2;
    return [start, { x: middleX, y: start.y }, { x: middleX, y: end.y }, end];
  }
  return [start, end];
}

function addLineSegment(slide, pptx, a, b, options) {
  const x = Math.min(a.x, b.x);
  const y = Math.min(a.y, b.y);
  const w = Math.abs(b.x - a.x);
  const h = Math.abs(b.y - a.y);
  slide.addShape(pptx.ShapeType.line, {
    x: options.px(x),
    y: options.px(y),
    w: options.px(w),
    h: options.px(h),
    flipH: a.x > b.x,
    flipV: a.y > b.y,
    objectName: options.objectName,
    line: options.line,
  });
}

function addEdge(slide, pptx, edge, ports, theme, px) {
  const points = edgePoints(edge, ports).map((point) => ({ x: Number(point.x), y: Number(point.y) }));
  const color = resolveColor(edge.color || "@connector", theme, "1769E8");
  const dashType = edge.dash === "dashed" ? "dash" : edge.dash === "dotted" ? "sysDot" : "solid";
  for (let index = 0; index < points.length - 1; index += 1) {
    const isFirst = index === 0;
    const isLast = index === points.length - 2;
    const line = {
      color,
      width: Number(edge.width || theme.connector_width || 2.5) * 0.75,
      dashType,
      beginArrowType: isFirst && ["start", "both"].includes(edge.arrowhead) ? "triangle" : "none",
      endArrowType: isLast && ["end", "both"].includes(edge.arrowhead) ? "triangle" : "none",
    };
    addLineSegment(slide, pptx, points[index], points[index + 1], {
      px,
      line,
      objectName: `${edge.id}-segment-${index + 1}`,
    });
  }
}

async function loadDefaultTheme(scriptDir) {
  const themePath = path.resolve(scriptDir, "..", "assets", "default-theme.json");
  try {
    const parsed = await readJsonFile(themePath);
    return parsed.theme && typeof parsed.theme === "object" ? parsed.theme : parsed;
  } catch {
    return {};
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    process.stdout.write(`${usage()}\n`);
    return 0;
  }
  if (!args.spec || !args.output) throw new Error(usage());

  let PptxGenJS;
  try {
    PptxGenJS = require("pptxgenjs");
  } catch (error) {
    process.stderr.write(
      `${JSON.stringify({ status: "skipped", backend: "pptxgenjs", reason: "optional_dependency_missing", install: "npm install --prefix scripts" })}\n`,
    );
    return 3;
  }

  const specPath = path.resolve(args.spec);
  const outputPath = path.resolve(args.output);
  const spec = await readJsonFile(specPath);
  const defaultTheme = await loadDefaultTheme(path.dirname(fileURLToPath(import.meta.url)));
  const theme = mergeTheme(defaultTheme, spec.theme || {});
  const canvasWidth = Number(spec.canvas.width);
  const canvasHeight = Number(spec.canvas.height);
  if (!(canvasWidth > 0 && canvasHeight > 0)) throw new Error("Canvas dimensions must be positive.");

  const pptx = new PptxGenJS();
  const layoutName = "SCIENTIFIC_FIGURE_SPEC";
  pptx.defineLayout({ name: layoutName, width: canvasWidth / 96, height: canvasHeight / 96 });
  pptx.layout = layoutName;
  pptx.author = "build-scientific-figures";
  pptx.subject = "Editable projection of a canonical scientific figure specification";
  pptx.title = spec.title || "Scientific figure";
  pptx.company = "";
  pptx.lang = "en-US";
  pptx.theme = {
    headFontFace: theme.font_family || "Noto Sans",
    bodyFontFace: theme.font_family || "Noto Sans",
    lang: "en-US",
  };
  const slide = pptx.addSlide();
  slide.background = { color: resolveColor(spec.canvas.background || "@background", theme, "FFFFFF") };
  const px = (value) => Number(value) / 96;
  const ports = new Map((spec.ports || []).map((port) => [port.id, port]));

  for (const edge of (spec.edges || []).filter((entry) => entry.scope !== "internal")) {
    addEdge(slide, pptx, edge, ports, theme, px);
  }

  for (const panel of [...(spec.panels || [])].sort((a, b) => Number(a.z || 0) - Number(b.z || 0))) {
    const fill = resolveColor(panel.fill || "@panel_fill", theme, "FFFFFF");
    const stroke = resolveColor(panel.stroke || "@primary", theme, "1769E8");
    slide.addShape(pptx.ShapeType.roundRect, {
      x: px(panel.x), y: px(panel.y), w: px(panel.width), h: px(panel.height),
      objectName: panel.id,
      fill: { color: fill },
      line: { color: stroke, width: Number(panel.stroke_width || theme.panel_stroke_width || 2) * 0.75 },
    });
    const headerHeight = Number(panel.header_height || 0);
    if (headerHeight > 0) {
      const headerColor = resolveColor(panel.header_fill || panel.stroke || "@primary", theme, stroke);
      const headerInset = Math.max(1, Number(panel.stroke_width || theme.panel_stroke_width || 2) * 0.75);
      const headerWidth = Math.max(1, Number(panel.width) - headerInset * 2);
      const squareFrom = Math.min(headerHeight - headerInset, Math.max(headerInset + 4, headerHeight * 0.38));
      // PowerPoint shapes do not support SVG-style clipping. Build the header
      // from a rounded cap plus an inset rectangle so its top follows the
      // panel corners while its lower boundary stays straight.
      slide.addShape(pptx.ShapeType.roundRect, {
        x: px(Number(panel.x) + headerInset),
        y: px(Number(panel.y) + headerInset),
        w: px(headerWidth),
        h: px(Math.max(1, headerHeight - headerInset)),
        objectName: `${panel.id}-header`,
        fill: { color: headerColor },
        line: { color: headerColor, transparency: 100 },
      });
      if (squareFrom < headerHeight - headerInset) {
        slide.addShape(pptx.ShapeType.rect, {
          x: px(Number(panel.x) + headerInset),
          y: px(Number(panel.y) + squareFrom),
          w: px(headerWidth),
          h: px(headerHeight - squareFrom),
          objectName: `${panel.id}-header-square-base`,
          fill: { color: headerColor },
          line: { color: headerColor, transparency: 100 },
        });
      }
    }
    let titleSizePx = Number(panel.title_font_size || Math.max(16, Math.min(30, headerHeight ? headerHeight * 0.44 : 22)));
    if (Number(panel.width) < 360) {
      titleSizePx = Math.min(titleSizePx, Math.max(12, (Number(panel.width) - 36) / Math.max(String(panel.title || "").length * 0.58, 1)));
    }
    slide.addText(String(panel.title || ""), {
      x: px(Number(panel.x) + 18),
      y: px(Number(panel.y) + (headerHeight ? 2 : 8)),
      w: px(Number(panel.width) - 36),
      h: px(headerHeight || titleSizePx * 1.7),
      objectName: `${panel.id}-title`,
      fontFace: theme.font_family || "Noto Sans",
      fontSize: titleSizePx * 0.75,
      bold: true,
      color: resolveColor(headerHeight ? panel.header_text_color || "@on_primary" : "@text", theme, headerHeight ? "FFFFFF" : "17212B"),
      margin: 0,
      breakLine: false,
      valign: "mid",
      fit: "shrink",
    });
    if (panel.subtitle) {
      const compactSubtitle = Number(panel.width) < 360 || String(panel.subtitle).length > Math.max(18, Math.floor(Number(panel.width) / Math.max(titleSizePx * 0.55, 1)));
      slide.addText(String(panel.subtitle), {
        x: px(compactSubtitle ? Number(panel.x) + 14 : Number(panel.x) + Number(panel.width) * 0.5),
        y: px(compactSubtitle ? Number(panel.y) + headerHeight + 6 : Number(panel.y) + (headerHeight ? 2 : 8)),
        w: px(compactSubtitle ? Number(panel.width) - 28 : Number(panel.width) * 0.5 - 18),
        h: px(compactSubtitle ? Math.max(20, Number(panel.height) - headerHeight - 14) : headerHeight || titleSizePx * 1.7),
        objectName: `${panel.id}-subtitle`,
        fontFace: theme.font_family || "Noto Sans",
        fontSize: Math.max(9, Math.min(14, titleSizePx * 0.5)) * 0.75,
        bold: true,
        color: resolveColor(compactSubtitle ? "@muted_text" : headerHeight ? panel.header_text_color || "@on_primary" : "@muted_text", theme, compactSubtitle ? "5F7180" : headerHeight ? "FFFFFF" : "5F7180"),
        margin: 0,
        align: compactSubtitle ? "center" : "right",
        valign: compactSubtitle ? "top" : "mid",
        fit: "shrink",
      });
    }
  }

  for (const asset of spec.assets || []) {
    const assetPath = asset.path ? path.resolve(path.dirname(specPath), asset.path) : null;
    let exists = false;
    if (assetPath) {
      try { await fs.access(assetPath); exists = true; } catch { exists = false; }
    }
    if (!exists || asset.placeholder === true) {
      slide.addShape(pptx.ShapeType.roundRect, {
        x: px(asset.x), y: px(asset.y), w: px(asset.width), h: px(asset.height),
        objectName: asset.id,
        fill: { color: "F2F5F8" },
        line: { color: "A8B4BE", width: 1, dashType: "dash" },
      });
      slide.addText(String(asset.placeholder_label || "ASSET SLOT"), {
        x: px(asset.x), y: px(Number(asset.y) + Number(asset.height) * 0.38),
        w: px(asset.width), h: px(Number(asset.height) * 0.24),
        objectName: `${asset.id}-placeholder-label`,
        fontFace: theme.font_family || "Noto Sans", fontSize: 10, color: "667580",
        align: "center", valign: "mid", margin: 0, fit: "shrink",
      });
    } else {
      slide.addImage({
        path: assetPath,
        x: px(asset.x), y: px(asset.y), w: px(asset.width), h: px(asset.height),
        objectName: asset.id,
        altText: asset.alt || asset.id,
      });
    }
  }

  for (const edge of (spec.edges || []).filter((entry) => entry.scope === "internal")) {
    addEdge(slide, pptx, edge, ports, theme, px);
  }

  for (const text of spec.texts || []) {
    slide.addText(String(text.text || ""), {
      x: px(text.x), y: px(text.y), w: px(text.width), h: px(text.height),
      objectName: text.id,
      fontFace: theme.font_family || "Noto Sans",
      fontSize: Number(text.font_size || 18) * 0.75,
      bold: ["semibold", "bold"].includes(text.font_weight),
      color: resolveColor(text.color || "@text", theme, "17212B"),
      align: text.align || "left",
      valign: text.valign === "top" ? "top" : text.valign === "bottom" ? "bottom" : "mid",
      margin: 0,
      fit: "shrink",
    });
  }

  const provenanceSummary = JSON.stringify({
    spec: path.basename(specPath),
    mode: spec.mode,
    canonical: "SVG",
    provenance: spec.provenance || [],
    limitations: "PptxGenJS uses editable native panels, text, and segmented connectors; rounded SVG connector geometry may differ from the canonical SVG.",
  });
  slide.addNotes([provenanceSummary]);
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await pptx.writeFile({ fileName: outputPath, compression: true });
  process.stdout.write(`${JSON.stringify({ output: outputPath, backend: "pptxgenjs", canonical: false })}\n`);
  return 0;
}

main()
  .then((code) => { process.exitCode = code; })
  .catch((error) => {
    process.stderr.write(`ERROR: ${error?.stack || error}\n`);
    process.exitCode = 1;
  });
