from __future__ import annotations

import argparse
import io
import textwrap
import zipfile
from pathlib import Path

from lxml import etree
from PIL import Image, ImageDraw, ImageFont


TALL_SIZE = (1000, 1850)
FINAL_SIZE = (1111, 350)
CAPTION = (
    "Figure S2. Case Study 2 Debate Progression from Round 1 to Final Synthesis. "
    "Condensed excerpts from the canonical Case Study 2 run (repository case_01) are shown for "
    "Rounds 1–3 and the final synthesis. The exchange moves from the surface-contact versus "
    "interstitial-transport trade-off, through competing mild-pressing, liquid-assisted, and "
    "dry-assembly proposals, to an allocation rule that remains within the fixed polycrystalline "
    "NCM811/LPSCl/existing-conductive-additive and mechanofusion design space. The final synthesis "
    "selects a minority nano-LPSCl fraction for partial surface coverage, a majority micron-scale "
    "LPSCl fraction for interstitial filling, and sequential low-energy mechanofusion. The complete "
    "unabridged transcript is provided in the public data release."
)

ROUNDS = [
    (
        "Round 1",
        "A: At >85 wt% active material, limited LPSCl must serve both local surface contact and bulk ionic transport. I propose a minority fine fraction for partial NCM811 coverage, a majority micron fraction for interstitial filling, and sequential controlled-energy mechanofusion.",
        "B: Fine-particle milling can lower sulfide conductivity, and mechanofusion can fracture NCM811. A simpler unimodal LPSCl blend followed by mild-temperature pressing may create contact and densification with less pre-processing risk.",
    ),
    (
        "Round 2",
        "A: Mild-temperature pressing and slurry processing can accelerate NCM811–sulfide reactions and introduce solvent/binder risks. A liquid-phase route could instead construct a low-tortuosity electrolyte network around intact particles.",
        "B: In-situ electrolyte formation adds uncontrolled chemistry. A dry architecture using a small nano-LPSCl coating fraction and larger interstitial LPSCl particles separates short-range contact from long-range ionic transport.",
    ),
    (
        "Round 3",
        "A: Dry powders may agglomerate and leave voids. Compatible liquid-assisted assembly with fine LPSCl can improve dispersion and contact, although it changes the processing route and adds solvent/binder constraints.",
        "B: The fixed mechanofusion design space is better served by explicit geometric allocation: nano-LPSCl for partial surface coverage, micron LPSCl for the interstices, and low-energy staged processing that limits particle damage.",
    ),
]

FINAL_TEXT = (
    "The moderator selected the geometric allocation principle that matches the fixed experimental constraints: "
    "use a minority nano-LPSCl fraction for partial NCM811 surface coverage, reserve the majority micron-scale "
    "LPSCl fraction for interstitial filling, and apply sequential low-energy mechanofusion to preserve ionic "
    "continuity, electronic accessibility, packing density, and particle integrity."
)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "timesbd.ttf" if bold else "times.ttf"
    path = Path("[LOCAL_PATH_REDACTED]
    return ImageFont.truetype(str(path), size=size)


def wrapped_lines(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=face) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_bubble(
    image: Image.Image,
    box: tuple[int, int, int, int],
    text: str,
    side: str,
    face: ImageFont.FreeTypeFont,
) -> None:
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=24, fill="white")
    if side == "left":
        draw.polygon([(x1 + 155, y2 - 2), (x1 + 75, y2 + 55), (x1 + 220, y2 - 2)], fill="white")
        icon_x = x1 + 22
    else:
        draw.polygon([(x2 - 155, y2 - 2), (x2 - 75, y2 + 55), (x2 - 220, y2 - 2)], fill="white")
        icon_x = x2 - 52
    draw.ellipse((icon_x, y2 + 58, icon_x + 30, y2 + 88), fill="white")
    draw.rounded_rectangle((icon_x - 7, y2 + 95, icon_x + 37, y2 + 142), radius=6, fill="white")
    lines = wrapped_lines(draw, text, face, x2 - x1 - 44)
    line_height = face.size + 7
    total_height = line_height * len(lines)
    cursor_y = y1 + max(14, (y2 - y1 - total_height) // 2)
    for line in lines:
        draw.text((x1 + 22, cursor_y), line, font=face, fill="black")
        cursor_y += line_height


def build_tall(path: Path) -> None:
    image = Image.new("RGB", TALL_SIZE, "black")
    draw = ImageDraw.Draw(image)
    body = font(25)
    heading = font(29, bold=True)
    y = 25
    for title, left_text, right_text in ROUNDS:
        draw.text((44, y), title, font=heading, fill="white")
        y += 45
        draw_bubble(image, (82, y, 965, y + 210), left_text, "left", body)
        y += 285
        draw_bubble(image, (82, y, 965, y + 210), right_text, "right", body)
        y += 285
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def build_final(path: Path) -> None:
    image = Image.new("RGB", FINAL_SIZE, "black")
    draw = ImageDraw.Draw(image)
    face = font(27)
    box = (108, 8, 1098, 215)
    draw.rounded_rectangle(box, radius=28, fill="white")
    draw.polygon([(270, 213), (205, 292), (520, 213)], fill="white")
    lines = wrapped_lines(draw, FINAL_TEXT, face, box[2] - box[0] - 42)
    y = 27
    for line in lines:
        draw.text((box[0] + 21, y), line, font=face, fill="black")
        y += face.size + 7
    draw.line((35, 292, 170, 292), fill="white", width=3)
    draw.line((85, 260, 83, 332), fill="white", width=3)
    draw.arc((20, 285, 85, 342), 0, 180, fill="white", width=3)
    draw.arc((110, 285, 175, 342), 0, 180, fill="white", width=3)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def patch_docx(source: Path, output: Path, tall_png: Path, final_png: Path) -> None:
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(source, "r") as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    document = etree.fromstring(parts["word/document.xml"])
    replaced = 0
    for paragraph in document.xpath(".//w:p", namespaces=namespace):
        nodes = paragraph.xpath(".//w:t", namespaces=namespace)
        existing = "".join(node.text or "" for node in nodes)
        if existing.startswith("Figure S2."):
            normal_nodes = [
                node
                for node in nodes
                if node.getparent().find("w:rPr/w:b", namespaces=namespace) is None
            ]
            if not normal_nodes:
                raise RuntimeError("Figure S2 caption has no non-bold body run")
            for node in nodes:
                node.text = ""
            nodes[0].text = "Figure S2. "
            normal_nodes[0].text = CAPTION.removeprefix("Figure S2. ")
            replaced += 1
    if replaced != 1:
        raise RuntimeError(f"Expected one Figure S2 caption, replaced {replaced}")
    parts["word/document.xml"] = etree.tostring(document, xml_declaration=True, encoding="UTF-8", standalone="yes")
    parts["word/media/image3.png"] = tall_png.read_bytes()
    parts["word/media/image4.png"] = final_png.read_bytes()

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)


def main() -> None:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--source",
        type=Path,
        default=root.parent / "AM 투고본" / "MPDS_Adv_Mater_Supprting information.docx",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "documents" / "MPDS_AS_revision_Supporting_Information_draft.docx",
    )
    args = parser.parse_args()
    figure_dir = root / "figures" / "figure_s2_corrected"
    tall_png = figure_dir / "figure_s2_rounds1_to_3.png"
    final_png = figure_dir / "figure_s2_final_synthesis.png"
    build_tall(tall_png)
    build_final(final_png)
    patch_docx(args.source.resolve(), args.output.resolve(), tall_png, final_png)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
