#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_pdf.py — 把 README.md 编译成打印级 PDF

流程: Markdown -> HTML(打印样式) -> Edge headless --print-to-pdf

用法:
    python build_pdf.py <input.md> <output.pdf>
"""
import sys, os, re, subprocess, tempfile, pathlib

import mistune

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

CSS = r"""
@page { size: A4; margin: 17mm 15mm 18mm 15mm; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  font-size: 10.2pt; line-height: 1.78; color: #1c1c1c; background: #fff;
  -webkit-font-smoothing: antialiased;
}
h1 {
  font-size: 25pt; line-height: 1.25; margin: 0 0 4pt; font-weight: 800;
  letter-spacing: -0.4pt;
}
h1 + p { font-size: 12.5pt; color: #555; margin: 0 0 2pt; font-weight: 600; }
h1 + p + p { font-size: 10pt; color: #8a8178; font-style: italic; margin: 0 0 18pt; }
h2 {
  font-size: 13.5pt; margin: 22pt 0 8pt; padding-left: 9pt; font-weight: 700;
  border-left: 4pt solid #D96522; page-break-after: avoid;
}
h3 { font-size: 11.2pt; margin: 14pt 0 6pt; font-weight: 700; color: #2a2a2a; page-break-after: avoid; }
p { margin: 0 0 8pt; text-align: justify; }
strong { font-weight: 700; color: #111; }
em { font-style: italic; color: #6b6259; }
hr { border: none; border-top: 0.6pt solid #e2ddd4; margin: 16pt 0; }
blockquote {
  margin: 12pt 0; padding: 9pt 12pt; background: #FBF7F1;
  border-left: 3pt solid #E0A277; color: #3a3a3a; font-size: 10pt;
}
blockquote p { margin: 0; }
ul, ol { margin: 0 0 9pt 0; padding-left: 18pt; }
li { margin: 3pt 0; }
code {
  font-family: Consolas, "Courier New", monospace; font-size: 8.9pt;
  background: #F4F1EB; padding: 1pt 4pt; border-radius: 2pt; color: #7a3b16;
}
pre {
  background: #F8F6F1; border: 0.6pt solid #e4dfd6; border-radius: 4pt;
  padding: 10pt 12pt; overflow-x: auto; page-break-inside: avoid; margin: 10pt 0;
}
pre code { background: none; padding: 0; color: #2b2b2b; font-size: 8.4pt; line-height: 1.6; }
img {
  display: block; max-width: 100%; height: auto; margin: 12pt auto 4pt;
  border-radius: 3pt; page-break-inside: avoid;
}
table {
  width: 100%; border-collapse: collapse; margin: 10pt 0 12pt;
  font-size: 8.7pt; page-break-inside: avoid;
}
th {
  background: #F5F1EA; font-weight: 700; text-align: left;
  border: 0.5pt solid #ddd6c9; padding: 5pt 6pt; color: #333;
}
td { border: 0.5pt solid #e5dfd4; padding: 4.5pt 6pt; vertical-align: top; }
tr:nth-child(even) td { background: #FCFAF7; }
a { color: #B0521A; text-decoration: none; }
.paper-footer{position:fixed;bottom:-2mm;left:0;right:0;font-size:7.2pt;color:#a89f94;border-top:0.5pt solid #ece7de;padding-top:3pt;text-align:center;letter-spacing:.02em}.paper-meta {
  font-size: 8.6pt; color: #8a8178; border-top: 0.6pt solid #e2ddd4;
  padding-top: 6pt; margin-top: 4pt;
}
"""

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>约束的审美</title>
<base href="{base}">
<style>{css}</style>
</head>
<body>{body}<div class="paper-footer">约束的审美 · Aesthetic of Constraints　|　由 README.md 自动编译</div></body>
</html>
"""


def find_edge():
    for p in EDGE_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("Edge not found")


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: build_pdf.py <input.md> <output.pdf>")
    md_path = os.path.abspath(sys.argv[1])
    pdf_path = os.path.abspath(sys.argv[2])
    root = os.path.dirname(md_path)

    text = open(md_path, encoding="utf-8").read()
    text = text.lstrip("\ufeff")  # 兼容带 BOM 的文件，否则首行标题会失效

    # 去掉 Markdown 里的图片语法前的空行问题：直接交给 mistune
    renderer = mistune.create_markdown(
        plugins=["table", "strikethrough", "url"],
        escape=False,
    )
    body = renderer(text)

    base = pathlib.Path(root).as_uri() + "/"
    html = HTML.format(base=base, css=CSS, body=body)

    tmp_html = os.path.join(tempfile.gettempdir(), "aoc_print.html")
    open(tmp_html, "w", encoding="utf-8").write(html)

    edge = find_edge()
    args = [
        edge,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-pdf-header-footer",
        "--virtual-time-budget=12000",
        f"--print-to-pdf={pdf_path}",
        pathlib.Path(tmp_html).as_uri(),
    ]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=180)
    if not os.path.exists(pdf_path):
        # 旧版 Edge 不支持 --headless=new，退回 --headless
        args[1] = "--headless"
        proc = subprocess.run(args, capture_output=True, text=True, timeout=180)

    if os.path.exists(pdf_path):
        size = os.path.getsize(pdf_path) / 1024
        print(f"OK  {pdf_path}  ({size:.0f} KB)")
    else:
        print("FAILED")
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:])
        sys.exit(1)


if __name__ == "__main__":
    main()
