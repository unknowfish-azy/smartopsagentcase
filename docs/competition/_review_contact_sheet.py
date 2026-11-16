from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(r"D:\SmartOpsAgent\docs\competition\assets\ui")
files = [
    "cover-insights.png", "login.png", "dashboard.png", "chat.png",
    "agent-trace.png", "agent-studio.png", "vrm-persona.png", "knowledge-wall.png",
    "knowledge-detail.png", "insight-nebula.png", "forecast.png", "sentinel.png",
]
thumb_w, thumb_h = 520, 315
label_h = 36
sheet = Image.new("RGB", (thumb_w * 3, (thumb_h + label_h) * 4), "#dfe5eb")
draw = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 20)
except OSError:
    font = ImageFont.load_default()
for index, name in enumerate(files):
    image = Image.open(root / name).convert("RGB")
    print(f"{name}: {image.width}x{image.height}")
    image.thumbnail((thumb_w - 12, thumb_h - 12), Image.Resampling.LANCZOS)
    tile = Image.new("RGB", (thumb_w, thumb_h), "#0b1118")
    tile.paste(image, ((thumb_w - image.width) // 2, (thumb_h - image.height) // 2))
    x = (index % 3) * thumb_w
    y = (index // 3) * (thumb_h + label_h)
    sheet.paste(tile, (x, y))
    draw.text((x + 10, y + thumb_h + 7), name, fill="#0b3d63", font=font)
out = root.parent / "ui-contact-sheet.jpg"
sheet.save(out, quality=90)
print(out)
