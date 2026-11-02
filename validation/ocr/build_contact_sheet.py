"""Construit une planche des images réelles et des zones OCR comparées."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).parent
FILES = sorted(ROOT.glob("*.webp"))
FONT = ImageFont.load_default(size=20)
SMALL = ImageFont.load_default(size=16)
THUMB = (360, 500)
MARGIN = 20
LABEL = 42
ROWS = 3
sheet = Image.new("RGB", (MARGIN + 3 * (THUMB[0] + MARGIN), MARGIN + ROWS * (THUMB[1] + LABEL + MARGIN)), "#eef2f7")
draw = ImageDraw.Draw(sheet)
for column, path in enumerate(FILES):
    with Image.open(path) as source:
        image = source.convert("RGB")
        width, height = image.size
        variants = (
            ("Image complète", image),
            ("Nom : bande haute 20 %", ImageOps.autocontrast(image.crop((0, 0, width, height * 20 // 100)).convert("L")).convert("RGB")),
            ("Numéro : bande basse 15 %", ImageOps.autocontrast(image.crop((0, height * 85 // 100, width, height)).convert("L")).convert("RGB")),
        )
        for row, (label, variant) in enumerate(variants):
            variant.thumbnail(THUMB)
            x = MARGIN + column * (THUMB[0] + MARGIN)
            y = MARGIN + row * (THUMB[1] + LABEL + MARGIN)
            draw.text((x, y), f"{path.stem} — {label}", fill="#172033", font=SMALL)
            sheet.paste(variant, (x + (THUMB[0] - variant.width) // 2, y + LABEL))
output = ROOT / "planche-recadrages.jpg"
sheet.save(output, quality=88, optimize=True)
print(output.resolve())
