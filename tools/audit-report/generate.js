const fs = require("fs");

const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  AlignmentType,
  HeadingLevel,
  BorderStyle,
  WidthType,
  ShadingType,
  LevelFormat,
} = require("docx");

function readText(p) {
  return fs.readFileSync(p, "utf-8");
}

function loadJson(p) {
  return JSON.parse(readText(p));
}

function safeString(v) {
  if (v === null || v === undefined) return "";
  return String(v);
}

function text(t, opts = {}) {
  return new TextRun({ text: safeString(t), ...opts });
}

function para(textRuns, opts = {}) {
  const children = Array.isArray(textRuns) ? textRuns : [text(textRuns)];
  return new Paragraph({ children, ...opts });
}

function h1(title) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [text(title)] });
}

function h2(title) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [text(title)] });
}

function kvLine(k, v) {
  return para([text(`${k}：`, { bold: true }), text(v)]);
}

function bullet(line) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [text(line)],
  });
}

function makeTable({ rows, columnWidths }) {
  const borderOuter = { style: BorderStyle.DOUBLE, size: 2, color: "666666" };
  const borderInner = { style: BorderStyle.SINGLE, size: 1, color: "AAAAAA" };
  const borders = {
    top: borderOuter,
    bottom: borderOuter,
    left: borderOuter,
    right: borderOuter,
    insideHorizontal: borderInner,
    insideVertical: borderInner,
  };

  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    columnWidths,
    borders,
    rows,
  });
}

function headerCell(label, width) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: { fill: "D5E8F0", type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [para([text(label, { bold: true })])],
  });
}

function bodyCell(value, width) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [para(safeString(value))],
  });
}

function latestChangelogSection(markdown) {
  const lines = markdown.split(/\r?\n/);
  const idx = [];
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].startsWith("### ")) idx.push(i);
  }
  if (idx.length === 0) return "（暂无）";
  const start = idx[idx.length - 1];
  const end = lines.length;
  const section = lines.slice(start, end).join("\n").trim();
  return section || "（暂无）";
}

async function main() {
  const root = "/sessions/69df99acf22671cacf117ebb/workspace";
  const args = process.argv.slice(2);
  const getArg = (name, fallback) => {
    const idx = args.indexOf(name);
    if (idx >= 0 && idx + 1 < args.length) return args[idx + 1];
    return fallback;
  };

  const findingsPath = getArg("--in", `${root}/reports/audit_findings.json`);
  const changelogPath = getArg("--changelog", `${root}/reports/audit_changelog.md`);
  const outPath = getArg("--out", `${root}/reports/aiPlat_设计文档与实现一致性审查报告.docx`);

  const data = loadJson(findingsPath);
  const items = data.items || [];

  const changelog = fs.existsSync(changelogPath) ? readText(changelogPath) : "";
  const latestChange = changelog ? latestChangelogSection(changelog) : "（暂无）";

  // A4 with 1-inch margins (DXA)
  const pageWidth = 11906;
  const pageHeight = 16838;
  const margin = 1440;
  const contentWidth = pageWidth - margin * 2; // 9026

  const numbering = {
    config: [
      {
        reference: "bullets",
        levels: [
          {
            level: 0,
            format: LevelFormat.BULLET,
            text: "•",
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } },
          },
        ],
      },
    ],
  };

  const children = [];

  // Title
  children.push(h1("aiPlat 设计文档与实现一致性审查报告"));
  children.push(para([text("范围：", { bold: true }), text((data.meta?.scope || []).join(" / "))]));
  children.push(para([text("重点：", { bold: true }), text((data.meta?.focus || []).join(" / "))]));
  children.push(para(" "));

  // Summary
  children.push(h1("结论摘要"));
  const riskCount = {};
  const statusCount = {};
  for (const it of items) {
    const r = it.risk || "未知";
    riskCount[r] = (riskCount[r] || 0) + 1;
    const s = it.status || "open";
    statusCount[s] = (statusCount[s] || 0) + 1;
  }
  children.push(
    para([
      text("总审查项：", { bold: true }),
      text(String(items.length)),
      text("；风险分布：", { bold: true }),
      text(Object.entries(riskCount).map(([k, v]) => `${k} ${v}`).join("，") || "（无）"),
    ])
  );
  children.push(
    para([
      text("修复状态分布：", { bold: true }),
      text(Object.entries(statusCount).map(([k, v]) => `${k} ${v}`).join("，") || "（无）"),
    ])
  );
  children.push(
    para("说明：本报告以“设计文档原文 + 代码证据”为最终判定依据；每次修复必须同步更新 JSON 与本报告。")
  );
  children.push(para(" "));

  // Latest change summary
  children.push(h1("本次迭代变更摘要"));
  children.push(para("以下内容来自 reports/audit_changelog.md 的最新条目："));
  for (const line of latestChange.split(/\r?\n/)) {
    if (!line.trim()) continue;
    if (line.startsWith("### ")) {
      children.push(para(line.replace(/^###\s+/, ""), { bold: true }));
    } else if (line.trim().startsWith("-")) {
      children.push(bullet(line.trim().replace(/^-+\s*/, "")));
    } else {
      children.push(para(line));
    }
  }
  children.push(para(" "));

  // Progress overview table
  children.push(h1("修复进度总览"));
  const colP = [
    Math.floor(contentWidth * 0.11), // ID
    Math.floor(contentWidth * 0.07), // 风险
    Math.floor(contentWidth * 0.11), // 判定
    Math.floor(contentWidth * 0.12), // 状态
    Math.floor(contentWidth * 0.14), // 更新时间
    contentWidth -
      (Math.floor(contentWidth * 0.11) +
        Math.floor(contentWidth * 0.07) +
        Math.floor(contentWidth * 0.11) +
        Math.floor(contentWidth * 0.12) +
        Math.floor(contentWidth * 0.14)), // 来源
  ];
  const headerRowP = new TableRow({
    cantSplit: true,
    children: [
      headerCell("ID", colP[0]),
      headerCell("风险", colP[1]),
      headerCell("判定", colP[2]),
      headerCell("状态", colP[3]),
      headerCell("更新时间", colP[4]),
      headerCell("来源文档", colP[5]),
    ],
  });
  const bodyRowsP = items.map((it) => {
    return new TableRow({
      cantSplit: true,
      children: [
        bodyCell(it.id, colP[0]),
        bodyCell(it.risk, colP[1]),
        bodyCell(it.verdict, colP[2]),
        bodyCell(it.status || "open", colP[3]),
        bodyCell(it.updated_at || "", colP[4]),
        bodyCell(it.source_doc, colP[5]),
      ],
    });
  });
  children.push(makeTable({ rows: [headerRowP, ...bodyRowsP], columnWidths: colP }));
  children.push(para(" "));

  // Issue list table (legacy, short)
  children.push(h1("问题清单（总览）"));
  const col = [
    Math.floor(contentWidth * 0.12), // ID
    Math.floor(contentWidth * 0.08), // 风险
    Math.floor(contentWidth * 0.12), // 判定
    Math.floor(contentWidth * 0.28), // 类型
    contentWidth -
      (Math.floor(contentWidth * 0.12) +
        Math.floor(contentWidth * 0.08) +
        Math.floor(contentWidth * 0.12) +
        Math.floor(contentWidth * 0.28)), // 来源
  ];
  const headerRow = new TableRow({
    cantSplit: true,
    children: [
      headerCell("ID", col[0]),
      headerCell("风险", col[1]),
      headerCell("判定", col[2]),
      headerCell("问题类型", col[3]),
      headerCell("来源文档", col[4]),
    ],
  });
  const bodyRows = items.map((it) => {
    return new TableRow({
      cantSplit: true,
      children: [
        bodyCell(it.id, col[0]),
        bodyCell(it.risk, col[1]),
        bodyCell(it.verdict, col[2]),
        bodyCell(it.issue_type, col[3]),
        bodyCell(it.source_doc, col[4]),
      ],
    });
  });
  children.push(makeTable({ rows: [headerRow, ...bodyRows], columnWidths: col }));
  children.push(para(" "));

  // Detailed items
  children.push(h1("逐条审查明细"));
  for (const it of items) {
    const title = `${it.id}（${it.risk || "未知"} | ${it.status || "open"}）`;
    children.push(h2(title));
    children.push(kvLine("来源文档", it.source_doc));
    children.push(kvLine("设计声明", it.design_statement));
    children.push(kvLine("判定", it.verdict));
    children.push(kvLine("问题类型", it.issue_type));
    children.push(kvLine("状态", it.status || "open"));
    if (it.updated_at) children.push(kvLine("更新时间", it.updated_at));

    // Evidence
    children.push(para([text("代码/文档证据：", { bold: true })]));
    for (const ev of it.code_evidence || []) {
      const line = `${ev.type || "evidence"} | ${ev.path || ""} | ${ev.evidence || ""}`;
      children.push(bullet(line));
    }

    // Recommendation
    if (it.recommendation) children.push(kvLine("修正建议", it.recommendation));
    if (it.verification) children.push(kvLine("验证方法", it.verification));

    // Fix info (continuous delivery fields)
    if (it.fix_summary) children.push(kvLine("修复摘要", it.fix_summary));
    if (Array.isArray(it.fix_refs) && it.fix_refs.length > 0) {
      children.push(para([text("修复涉及文件：", { bold: true })]));
      for (const ref of it.fix_refs) {
        const symbols = Array.isArray(ref.symbols) && ref.symbols.length > 0 ? ` (${ref.symbols.join(", ")})` : "";
        const note = ref.note ? ` - ${ref.note}` : "";
        children.push(bullet(`${ref.path}${symbols}${note}`));
      }
    }
    if (it.verification_result && (it.verification_result.tests || it.verification_result.commands || it.verification_result.evidence)) {
      children.push(para([text("验证结果：", { bold: true })]));
      if (Array.isArray(it.verification_result.tests)) {
        for (const t of it.verification_result.tests) children.push(bullet(`tests: ${t}`));
      }
      if (Array.isArray(it.verification_result.commands)) {
        for (const c of it.verification_result.commands) children.push(bullet(`cmd: ${c}`));
      }
      if (it.verification_result.evidence) children.push(bullet(`evidence: ${it.verification_result.evidence}`));
    }

    children.push(para(" "));
  }

  const doc = new Document({
    numbering,
    styles: {
      default: {
        document: {
          run: {
            font: { ascii: "Arial", hAnsi: "Arial", eastAsia: "Microsoft YaHei" },
            size: 24,
          },
        },
      },
      paragraphStyles: [
        {
          id: "Heading1",
          name: "Heading 1",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: {
            size: 34,
            bold: true,
            font: { ascii: "Arial", hAnsi: "Arial", eastAsia: "Microsoft YaHei" },
          },
          paragraph: {
            spacing: { before: 240, after: 240 },
            outlineLevel: 0,
            keepNext: false,
            keepLines: false,
          },
        },
        {
          id: "Heading2",
          name: "Heading 2",
          basedOn: "Normal",
          next: "Normal",
          quickFormat: true,
          run: {
            size: 28,
            bold: true,
            font: { ascii: "Arial", hAnsi: "Arial", eastAsia: "Microsoft YaHei" },
          },
          paragraph: {
            spacing: { before: 180, after: 180 },
            outlineLevel: 1,
            keepNext: false,
            keepLines: false,
          },
        },
      ],
    },
    sections: [
      {
        properties: {
          page: {
            size: { width: pageWidth, height: pageHeight },
            margin: { top: margin, right: margin, bottom: margin, left: margin },
          },
        },
        children,
      },
    ],
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outPath, buffer);
  console.log(`Wrote ${outPath}`);
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
