"""
Renders a full 368x448 screen image as JPEG using Pillow.
Used for icon+text custom states where full compositing flexibility is needed.
"""

import io
import os
import logging
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

SCREEN_W = 368
SCREEN_H = 448
JPEG_QUALITY = 82

# Font paths to try for text rendering
TEXT_FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf",   # Segoe UI Bold (Windows)
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",  # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]

EMOJI_FONT_CANDIDATES = [
    "C:/Windows/Fonts/seguiemj.ttf",   # Segoe UI Emoji (Windows)
    "/System/Library/Fonts/Apple Color Emoji.ttc",  # macOS
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
]


def _load_font(candidates: list[str], size: int) -> Optional[ImageFont.FreeTypeFont]:
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return None


def render_screen(
    emoji: Optional[str],
    text: str,
    bg_r: int, bg_g: int, bg_b: int,
    fg_r: int = -1, fg_g: int = -1, fg_b: int = -1,  # -1 = auto
) -> bytes:
    """
    Render a full 368x448 JPEG screen image.
    - emoji: emoji character(s) to draw large at top (None = skip)
    - text: text to draw below emoji
    - bg: background color
    - fg: foreground (text) color, -1 = auto (black/white based on bg luminance)
    Returns: JPEG bytes
    """
    bg = (bg_r, bg_g, bg_b)

    # Auto foreground color
    if fg_r < 0:
        lum = 0.299 * bg_r + 0.587 * bg_g + 0.114 * bg_b
        fg = (0, 0, 0) if lum > 140 else (255, 255, 255)
    else:
        fg = (fg_r, fg_g, fg_b)

    img = Image.new("RGB", (SCREEN_W, SCREEN_H), bg)
    draw = ImageDraw.Draw(img)

    if emoji:
        _draw_emoji(img, draw, emoji, bg)

    if text.strip():
        _draw_text(draw, text, fg, has_emoji=bool(emoji))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    data = buf.getvalue()
    logger.debug(f"Rendered screen: {len(data)} bytes JPEG")
    return data


def _draw_emoji(img: Image.Image, draw: ImageDraw.Draw, emoji: str, bg: tuple):
    """Draw emoji centered in the upper 55% of the screen."""
    emoji_size = int(SCREEN_H * 0.42)  # ~188px — about 42% of screen height
    area_h = int(SCREEN_H * 0.55)      # emoji lives in top 55%

    font = _load_font(EMOJI_FONT_CANDIDATES, emoji_size)
    if not font:
        logger.warning("No emoji font found, skipping icon")
        return

    try:
        # Render emoji onto transparent canvas first
        canvas = Image.new("RGBA", (SCREEN_W, area_h), (0, 0, 0, 0))
        cdraw = ImageDraw.Draw(canvas)

        bbox = cdraw.textbbox((0, 0), emoji, font=font)
        ew = bbox[2] - bbox[0]
        eh = bbox[3] - bbox[1]

        x = (SCREEN_W - ew) // 2 - bbox[0]
        y = (area_h - eh) // 2 - bbox[1]

        cdraw.text((x, y), emoji, font=font, embedded_color=True)

        # Composite emoji onto background (handles transparency correctly)
        bg_layer = Image.new("RGBA", (SCREEN_W, area_h), (*bg, 255))
        composited = Image.alpha_composite(bg_layer, canvas)

        img.paste(composited.convert("RGB"), (0, 0))

    except Exception as e:
        logger.warning(f"Emoji render failed: {e}")


def _draw_text(draw: ImageDraw.Draw, text: str, fg: tuple, has_emoji: bool):
    """Draw text centered in the lower portion of the screen."""
    # Text area: lower 45% if there's an emoji, full screen if not
    text_area_top = int(SCREEN_H * 0.57) if has_emoji else 0
    text_area_h = SCREEN_H - text_area_top
    padding = 12

    # Try to find a good font size that fits
    lines = text.split("\n") or [text]
    max_line = max(lines, key=len)

    font = None
    font_size = 72
    while font_size >= 18:
        f = _load_font(TEXT_FONT_CANDIDATES, font_size)
        if not f:
            # Fallback to default
            break
        bbox = draw.textbbox((0, 0), max_line, font=f)
        line_w = bbox[2] - bbox[0]
        if line_w <= SCREEN_W - padding * 2:
            font = f
            break
        font_size -= 6

    if not font:
        font = _load_font(TEXT_FONT_CANDIDATES, 36)
        if not font:
            return

    # Measure total text block height
    line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_h = max((b[3] - b[1]) for b in line_bboxes) if line_bboxes else 0
    line_spacing = int(line_h * 0.2)
    total_h = len(lines) * line_h + (len(lines) - 1) * line_spacing

    # Center text block in the text area
    y = text_area_top + (text_area_h - total_h) // 2

    for i, (line, bbox) in enumerate(zip(lines, line_bboxes)):
        line_w = bbox[2] - bbox[0]
        x = (SCREEN_W - line_w) // 2 - bbox[0]
        draw.text((x, y), line, font=font, fill=fg)
        y += line_h + line_spacing
