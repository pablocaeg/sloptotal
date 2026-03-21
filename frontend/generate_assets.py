"""Generate SlopTotal social/SEO assets: OG image + apple-touch-icon."""

from PIL import Image, ImageDraw, ImageFont
import os

OUT = os.path.join(os.path.dirname(__file__), "public")

INK = "#1a1a18"
PAPER = "#f5f0e8"
RED = "#b5282e"
DIM = "#7a756b"


def _font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/{name}", size)
    except OSError:
        return ImageFont.load_default()


def generate_og_image():
    """1200x630 Open Graph image for link previews."""
    w, h = 1200, 630
    img = Image.new("RGB", (w, h), PAPER)
    draw = ImageDraw.Draw(img)

    # Top accent stripe
    draw.rectangle([0, 0, w, 6], fill=RED)

    # Brand: SLOP (serif-bold) + TOTAL (regular)
    brand_font = _font(72, bold=True)
    slop = "SLOP"
    total = "TOTAL"

    slop_bbox = draw.textbbox((0, 0), slop, font=brand_font)
    slop_w = slop_bbox[2] - slop_bbox[0]

    total_font = _font(72, bold=False)
    total_bbox = draw.textbbox((0, 0), total, font=total_font)
    total_w = total_bbox[2] - total_bbox[0]

    brand_w = slop_w + total_w + 4
    brand_x = (w - brand_w) // 2
    brand_y = 180

    draw.text((brand_x, brand_y), slop, fill=INK, font=brand_font)
    draw.text((brand_x + slop_w + 4, brand_y), total, fill=INK, font=total_font)

    # Red underline beneath brand
    underline_y = brand_y + 80
    draw.rectangle([brand_x, underline_y, brand_x + brand_w, underline_y + 3], fill=RED)

    # Tagline
    tag_font = _font(28, bold=False)
    tagline = "Free AI Content Detector  |  23 Detection Engines"
    tag_bbox = draw.textbbox((0, 0), tagline, font=tag_font)
    tag_w = tag_bbox[2] - tag_bbox[0]
    draw.text(((w - tag_w) // 2, underline_y + 30), tagline, fill=DIM, font=tag_font)

    # Subtitle
    sub_font = _font(20, bold=False)
    subtitle = "Paste a URL or text. Get a forensic report from 23 independent AI detectors."
    sub_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
    sub_w = sub_bbox[2] - sub_bbox[0]
    draw.text(((w - sub_w) // 2, underline_y + 80), subtitle, fill=DIM, font=sub_font)

    # Domain at bottom
    domain_font = _font(22, bold=True)
    domain = "sloptotal.com"
    dom_bbox = draw.textbbox((0, 0), domain, font=domain_font)
    dom_w = dom_bbox[2] - dom_bbox[0]
    draw.text(((w - dom_w) // 2, h - 70), domain, fill=RED, font=domain_font)

    path = os.path.join(OUT, "og-image.png")
    img.save(path, optimize=True)
    print(f"  {path} ({w}x{h})")


def generate_apple_touch_icon():
    """180x180 apple-touch-icon."""
    size = 180
    img = Image.new("RGB", (size, size), INK)
    draw = ImageDraw.Draw(img)

    # Red "S" in center, italic-style
    font = _font(110, bold=True)
    text = "S"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1]
    draw.text((x, y), text, fill=RED, font=font)

    path = os.path.join(OUT, "apple-touch-icon.png")
    img.save(path, optimize=True)
    print(f"  {path} ({size}x{size})")


if __name__ == "__main__":
    generate_og_image()
    generate_apple_touch_icon()
    print("Done.")
