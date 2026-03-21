"""Generate SlopTotal extension icons — red "ST" monogram badge."""

from PIL import Image, ImageDraw, ImageFont

SIZES = [16, 48, 128]
BG_COLOR = "#b5282e"
TEXT_COLOR = "#ffffff"
OUTPUT_DIR = "icons"


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded rectangle background
    radius = max(2, size // 5)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BG_COLOR)

    # Font size scaled to icon
    font_size = int(size * 0.52)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except (OSError, IOError):
        font = ImageFont.load_default()

    # Center "ST" text
    text = "ST"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1]
    draw.text((x, y), text, fill=TEXT_COLOR, font=font)

    return img


if __name__ == "__main__":
    import os

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for s in SIZES:
        path = os.path.join(OUTPUT_DIR, f"icon{s}.png")
        icon = draw_icon(s)
        icon.save(path)
        print(f"  {path} ({s}x{s})")
    print("Done.")
