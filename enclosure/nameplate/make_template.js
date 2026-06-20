const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, PageOrientation, BorderStyle, WidthType, ShadingType,
  VerticalAlign, HeightRule, LevelFormat,
} = require("docx");

// ---- mm -> DXA (1 mm = 56.6929 DXA, 1440 DXA = 1 inch) ----
const mm = (v) => Math.round(v * 56.6929);

// Measured from FrontLid.stl (current v11 print geometry):
//   Cut size  : 193 mm (length, X) x 46 mm (height, Y)
//   Visible   : ~194 x 42.6 mm  -> ~1.7 mm top & bottom slips under the lips
const CUT_W = mm(194);      // full usable channel X55->X249 (butts both ends)
const CUT_H = mm(46);       // 2609
const LIP   = mm(1.7);      // 96  (hidden strip top & bottom)
const VIS_H = CUT_H - 2 * LIP;   // visible band height
const CAL_W = mm(50);       // 50 mm calibration bar

const GRAY = "9A9A9A";
const LIGHT = "BBBBBB";

const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder,
                    insideHorizontal: noBorder, insideVertical: noBorder };

const cutBorder = { style: BorderStyle.SINGLE, size: 6, color: "000000" }; // solid CUT line (~0.75pt)
const visBorder = { style: BorderStyle.DASHED, size: 4, color: LIGHT };    // dashed visible-area guide

// ---- CUT box: solid border = the only printed line. Text sits directly inside,
//      with top/bottom margins = LIP so it stays in the visible band (no dashed guide). ----
const cutTable = new Table({
  width: { size: CUT_W, type: WidthType.DXA },
  columnWidths: [CUT_W],
  borders: { top: cutBorder, bottom: cutBorder, left: cutBorder, right: cutBorder,
             insideHorizontal: noBorder, insideVertical: noBorder },
  rows: [ new TableRow({
    height: { value: CUT_H, rule: HeightRule.EXACT },
    children: [ new TableCell({
      width: { size: CUT_W, type: WidthType.DXA },
      verticalAlign: VerticalAlign.CENTER,
      margins: { top: LIP, bottom: LIP, left: mm(3), right: mm(3) },
      children: [
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 0, after: 40, line: 240, lineRule: "auto" },
          children: [ new TextRun({ text: "Drew Lawton",
            font: "Arial", size: 48, bold: false, color: "000000" }) ],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 0, after: 0, line: 240, lineRule: "auto" },
          children: [ new TextRun({ text: "Director of Data & Tech Operations",
            font: "Arial", size: 24, bold: true, color: "000000" }) ],
        }),
      ],
    }) ],
  }) ],
});

// ---- 50 mm calibration bar ----
const calTable = new Table({
  width: { size: CAL_W, type: WidthType.DXA },
  columnWidths: [CAL_W],
  borders: { top: cutBorder, bottom: cutBorder, left: cutBorder, right: cutBorder,
             insideHorizontal: noBorder, insideVertical: noBorder },
  rows: [ new TableRow({
    height: { value: mm(6), rule: HeightRule.EXACT },
    children: [ new TableCell({
      width: { size: CAL_W, type: WidthType.DXA },
      verticalAlign: VerticalAlign.CENTER,
      children: [ new Paragraph({ alignment: AlignmentType.CENTER,
        children: [ new TextRun({ text: "50 mm", font: "Arial", size: 16, color: GRAY }) ] }) ],
    }) ],
  }) ],
});

const H = (t) => new Paragraph({ spacing: { before: 120, after: 60 },
  children: [ new TextRun({ text: t, font: "Arial", size: 26, bold: true, color: "222222" }) ] });
const P = (t, opts = {}) => new Paragraph({ spacing: { after: 40 }, ...opts,
  children: [ new TextRun({ text: t, font: "Arial", size: 20, color: "333333" }) ] });
const step = (n, t) => new Paragraph({ numbering: { reference: "steps", level: 0 }, spacing: { after: 30 },
  children: [ new TextRun({ text: t, font: "Arial", size: 20, color: "333333" }) ] });

const doc = new Document({
  numbering: { config: [ { reference: "steps",
    levels: [ { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 460, hanging: 280 } } } } ] } ] },
  sections: [ {
    properties: { page: {
      size: { width: mm(216), height: mm(279), orientation: PageOrientation.LANDSCAPE },
      margin: { top: mm(12), right: mm(12), bottom: mm(12), left: mm(12) },
    } },
    children: [
      new Paragraph({ spacing: { after: 40 }, children: [
        new TextRun({ text: "Meeting Light — Nameplate Insert", font: "Arial", size: 30, bold: true, color: "111111" }) ] }),
      P("Final cut size: 194 × 46 mm (≈ 7‑ 5/8″ × 1‑ 13/16″). Slides into the right-hand channel of the front lid."),

      new Paragraph({ spacing: { before: 200, after: 80 }, children: [
        new TextRun({ text: "▼  Edit the text, then cut along the solid line  ▼", font: "Arial", size: 20, bold: true, color: GRAY }) ] }),

      cutTable,

      new Paragraph({ spacing: { before: 60, after: 200 }, children: [
        new TextRun({ text: "Solid line = cut here (194 × 46 mm). The top & bottom ~1.7 mm tucks under the retaining lips, so keep important text vertically centered (it already is).",
          font: "Arial", size: 16, italics: true, color: GRAY }) ] }),

      H("How to use"),
      step(1, "Click inside the box and replace the placeholder with your name / status. Keep it vertically centered so nothing important hides under the lips."),
      step(2, "Print at 100% / “Actual size.” Turn OFF “Fit to page” / “Shrink oversized pages.”"),
      step(3, "Check scale: the bar below should measure exactly 50 mm. If not, fix the print-scaling setting and reprint."),
      step(4, "Cut along the solid outer rectangle — final piece is 194 × 46 mm."),
      step(5, "Slide it into the right-hand channel of the front lid, entering from the screen end, until it stops at the far wall."),

      new Paragraph({ spacing: { before: 140, after: 40 }, children: [
        new TextRun({ text: "Print-scale check bar:", font: "Arial", size: 18, bold: true, color: "333333" }) ] }),
      calTable,
    ],
  } ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync("MeetingLight-Nameplate-Drew.docx", buf);
  console.log("wrote MeetingLight-Nameplate-Drew.docx");
});
