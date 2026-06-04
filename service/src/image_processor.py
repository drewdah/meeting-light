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
    font_size_override: int = 0,  # 0 = auto
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

    if emoji or text.strip():
        _draw_centered_group(img, draw, emoji or None, text, fg, bg,
                             font_size_override=font_size_override)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    data = buf.getvalue()
    logger.debug(f"Rendered screen: {len(data)} bytes JPEG")
    return data


def _draw_centered_group(img: Image.Image, draw: ImageDraw.Draw,
                          emoji: Optional[str], text: str, fg: tuple, bg: tuple,
                          font_size_override: int = 0):
    """
    Render emoji + text as a vertically centered group on the screen.
    Measures each element, stacks them with a gap, and centers the whole block.
    """
    EMOJI_SIZE = int(SCREEN_H * 0.38)    # ~170px font size
    EMOJI_PAD  = int(SCREEN_H * 0.025)  # ~11px extra canvas above/below emoji
    GAP = int(SCREEN_H * 0.06)          # ~27px between emoji and text
    PADDING = int(SCREEN_H * 0.04)      # ~18px top/bottom padding

    # --- Measure text block with word-wrap ---
    MIN_FONT = 36   # minimum readable from a few feet away
    MAX_FONT = 72
    text_font = None
    text_size = MAX_FONT
    lines = []

    raw_lines = (text.strip().split("\n") if text.strip() else [])

    def wrap_lines(font, raw, max_w):
        """Word-wrap raw lines to fit max_w pixels."""
        result = []
        for raw_line in raw:
            words = raw_line.split()
            if not words:
                result.append("")
                continue
            current = ""
            for word in words:
                test = (current + " " + word).strip()
                bbox = draw.textbbox((0, 0), test, font=font)
                if bbox[2] - bbox[0] <= max_w:
                    current = test
                else:
                    if current:
                        result.append(current)
                    current = word
            if current:
                result.append(current)
        return result

    MAX_TEXT_W = SCREEN_W - 32
    # Available height for the text block (screen minus emoji, gap, padding)
    emoji_h_budget = EMOJI_SIZE if emoji else 0
    gap_budget = GAP if (emoji and raw_lines) else 0
    max_text_h = SCREEN_H - emoji_h_budget - gap_budget - 2 * PADDING

    if raw_lines:
        if font_size_override > 0:
            # Use the requested size directly, just wrap to fit width
            text_size = max(MIN_FONT, font_size_override)
            f = _load_font(TEXT_FONT_CANDIDATES, text_size)
            if f:
                text_font = f
                lines = wrap_lines(f, raw_lines, MAX_TEXT_W)
            else:
                lines = raw_lines
        else:
            while text_size >= MIN_FONT:
                f = _load_font(TEXT_FONT_CANDIDATES, text_size)
                if f:
                    wrapped = wrap_lines(f, raw_lines, MAX_TEXT_W)
                    lh = int(text_size * 1.3)
                    ls = int(text_size * 0.2)
                    tbh = len(wrapped) * lh + max(0, len(wrapped) - 1) * ls
                    width_ok = all(
                        draw.textbbox((0, 0), l, font=f)[2] - draw.textbbox((0, 0), l, font=f)[0] <= MAX_TEXT_W
                        for l in wrapped if l
                    )
                    if width_ok and tbh <= max_text_h:
                        text_font = f
                        lines = wrapped
                        break
                text_size -= 4
            if not text_font:
                text_font = _load_font(TEXT_FONT_CANDIDATES, MIN_FONT)
                if text_font:
                    lines = wrap_lines(text_font, raw_lines, MAX_TEXT_W)
                else:
                    lines = raw_lines

    line_bboxes = []
    line_h = int(text_size * 1.3) if text_font else 0
    line_spacing = int(text_size * 0.2) if text_font else 0
    if text_font and lines:
        line_bboxes = [draw.textbbox((0, 0), l, font=text_font) for l in lines]
    text_block_h = len(lines) * line_h + max(0, len(lines)-1) * line_spacing if lines else 0

    # --- Calculate total group height ---
    emoji_block_h = (EMOJI_SIZE + EMOJI_PAD * 2) if emoji else 0
    gap = GAP if (emoji and lines) else 0
    total_h = emoji_block_h + gap + text_block_h

    # --- Center vertically ---
    top = max(PADDING, (SCREEN_H - total_h) // 2)

    # --- Draw emoji ---
    if emoji:
        font = _load_font(EMOJI_FONT_CANDIDATES, EMOJI_SIZE)
        if font:
            try:
                canvas = Image.new("RGBA", (SCREEN_W, emoji_block_h), (0, 0, 0, 0))  # includes EMOJI_PAD
                cdraw = ImageDraw.Draw(canvas)
                # Try measuring with and without variation selectors
                # Some multi-codepoint emoji (e.g. ✈️) return unusual bboxes
                bbox = cdraw.textbbox((0, 0), emoji, font=font)
                ew, eh = bbox[2] - bbox[0], bbox[3] - bbox[1]

                # If bbox looks unreasonable, try stripping variation selectors
                if ew <= 0 or ew > SCREEN_W or eh <= 0:
                    clean = emoji.replace('️', '').replace('︎', '')
                    bbox = cdraw.textbbox((0, 0), clean, font=font)
                    ew, eh = bbox[2] - bbox[0], bbox[3] - bbox[1]

                # Center emoji within canvas, with EMOJI_PAD headroom at top
                x = max(0, min(SCREEN_W - ew, (SCREEN_W - ew) // 2 - bbox[0]))
                y = EMOJI_PAD + max(0, (EMOJI_SIZE - eh) // 2 - bbox[1])
                cdraw.text((x, y), emoji, font=font, embedded_color=True)
                bg_layer = Image.new("RGBA", (SCREEN_W, emoji_block_h), (*bg, 255))
                composited = Image.alpha_composite(bg_layer, canvas)
                img.paste(composited.convert("RGB"), (0, top))
            except Exception as e:
                logger.warning(f"Emoji draw failed: {e}")

    # --- Draw text with consistent line height ---
    if text_font and lines:
        y = top + emoji_block_h + gap
        for line, bbox in zip(lines, line_bboxes):
            lw = bbox[2] - bbox[0]
            x = max(0, (SCREEN_W - lw) // 2 - bbox[0])
            # Vertically center text within the line_h slot
            y_offset = max(0, (line_h - (bbox[3] - bbox[1])) // 2 - bbox[1])
            draw.text((x, y + y_offset), line, font=text_font, fill=fg)
            y += line_h + line_spacing


def _draw_emoji(img: Image.Image, draw: ImageDraw.Draw, emoji: str, bg: tuple):
    """Draw emoji centered in the upper portion of the screen with padding."""
    emoji_size = int(SCREEN_H * 0.46)  # ~206px — large and prominent
    area_h = int(SCREEN_H * 0.58)      # emoji lives in top 58%

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
    # Text area: lower portion if there's an emoji, full screen if not
    # Leave a gap between emoji bottom and text top
    text_area_top = int(SCREEN_H * 0.62) if has_emoji else 0
    text_area_h = SCREEN_H - text_area_top - 20  # 20px bottom padding
    padding = 16

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
