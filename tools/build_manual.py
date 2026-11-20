"""Build docs/PanelWorks-Manual.pdf (A4) from the Markdown chapters in docs/manual.

    python tools/build_manual.py

Needs pandoc and Google Chrome / Chromium on the PATH (build-time only).
Markdown -> one HTML file (pandoc, with a print stylesheet) -> PDF (headless Chrome).
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAN = os.path.join(ROOT, "docs", "manual")
OUT = os.path.join(ROOT, "docs", "PanelWorks-Manual.pdf")
sys.path.insert(0, ROOT)
from panelworks import __version__  # noqa: E402

CSS = r"""
@page { size: A4; margin: 18mm 16mm 20mm 16mm;
        @bottom-center { content: counter(page); font: 9pt sans-serif; color: #666; } }
html { font-family: "DejaVu Sans", "Segoe UI", Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1a1a1a; }
body { margin: 0; }
h1 { font-size: 21pt; color: #1f3d6b; border-bottom: 2px solid #1f3d6b; padding-bottom: 4px;
     margin: 0 0 12px; break-before: page; }
h2 { font-size: 14pt; color: #1f3d6b; margin: 18px 0 6px; break-after: avoid; }
h3 { font-size: 11.5pt; margin: 14px 0 4px; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
code { font-family: "DejaVu Sans Mono", Consolas, monospace; font-size: 9pt; background: #f2f4f7;
       padding: 0 2px; border-radius: 2px; }
pre { background: #f5f7fa; border: 1px solid #dde3ea; border-left: 3px solid #1f3d6b;
      padding: 7px 9px; font-size: 8.6pt; line-height: 1.35; white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 10px; font-size: 9.2pt; break-inside: auto; }
tr { break-inside: avoid; }
th, td { border: 1px solid #cfd6de; padding: 3px 6px; vertical-align: top; text-align: left; }
th { background: #e8eef5; }
blockquote { margin: 8px 0; padding: 6px 10px; background: #fff8e1; border-left: 3px solid #e0a800; }
blockquote p { margin: 2px 0; }
img { max-width: 100%; max-height: 120mm; display: block; margin: 8px auto; border: 1px solid #ccc; break-inside: avoid; }
a { color: #1f3d6b; text-decoration: none; }
.cover { break-after: page; text-align: center; padding-top: 55mm; }
.cover h1 { break-before: avoid; border: none; font-size: 40pt; margin: 0; }
.cover .sub { font-size: 15pt; color: #444; margin: 10px 0 40mm; }
.cover img { border: none; width: 46mm; margin: 0 auto 14mm; }
.cover .who { font-size: 11pt; color: #333; line-height: 1.7; }
nav#TOC { break-after: page; }
nav#TOC::before { content: "Contents"; display: block; font-size: 21pt; color: #1f3d6b;
                  border-bottom: 2px solid #1f3d6b; margin-bottom: 10px; }
nav#TOC ul { list-style: none; padding-left: 0; margin: 0; }
nav#TOC > ul > li { margin: 5px 0 2px; font-weight: bold; }
nav#TOC ul ul { padding-left: 16px; font-weight: normal; font-size: 9.5pt; columns: 2; }
"""


def main():
    pandoc = shutil.which("pandoc")
    chrome = next((shutil.which(c) for c in ("google-chrome", "chromium", "chromium-browser", "chrome")
                   if shutil.which(c)), None)
    if not pandoc or not chrome:
        sys.exit("Needs pandoc and Chrome/Chromium on the PATH.")
    chapters = sorted(p for p in glob.glob(os.path.join(MAN, "[0-9][0-9]-*.md")))
    work = tempfile.mkdtemp(prefix="pwman-")
    parts = []
    for p in chapters:
        text = open(p, encoding="utf-8").read()
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        # chapter cross-links (01-introduction.md) are pages in the PDF, not files
        text = re.sub(r"\]\((\d\d-[\w-]+)\.md\)", r"](#)", text)
        parts.append(text)
    md = os.path.join(work, "manual.md")
    with open(md, "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(parts))
    css = os.path.join(work, "manual.css")
    with open(css, "w", encoding="utf-8") as fh:
        fh.write(CSS)
    icon = os.path.join(ROOT, "panelworks", "assets", "panelworks.png")
    cover = os.path.join(work, "cover.html")
    with open(cover, "w", encoding="utf-8") as fh:
        fh.write(f"""<div class="cover"><img src="file://{icon}">
<h1>PanelWorks</h1><div class="sub">Installation and Programming Manual<br>Version {__version__}</div>
<div class="who">Steve Spence (KK4HFJ)<br>kk4hfj.com<br><br>github.com/KK4HFJ/panelworks<br>MIT licence</div></div>""")
    html = os.path.join(work, "manual.html")
    subprocess.run([pandoc, md, "-f", "gfm", "-t", "html5", "-s", "--toc", "--toc-depth=2",
                    "--metadata", "title=PanelWorks Manual", "--css", css,
                    "--include-before-body", cover, "--resource-path", MAN,
                    "--embed-resources", "-o", html], check=True, cwd=MAN)
    # pandoc's default page title block duplicates the cover
    page = open(html, encoding="utf-8").read()
    page = re.sub(r'<header id="title-block-header">.*?</header>', "", page, flags=re.S)
    open(html, "w", encoding="utf-8").write(page)
    subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={OUT}", "file://" + html], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("wrote", OUT, f"({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
