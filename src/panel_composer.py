"""
コマ割り：複数のパネル画像を1枚の漫画ページにまとめる
"""

from pathlib import Path
from PIL import Image

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
BORDER_WIDTH = 4  # コマ間の線の太さ（px）
BG_COLOR = (255, 255, 255)


def get_panel_paths(output_dir: Path | None = None) -> list[Path]:
    """output/ 内の panel_*.png を番号順で取得"""
    base = output_dir or OUTPUT_DIR
    if not base.exists():
        return []
    return sorted(base.glob("panel_*.png"), key=lambda p: int(p.stem.split("_")[1] or 0))


def compose_panels(
    panel_paths: list[Path],
    layout: str = "vertical",
    output_path: Path | None = None,
    border_width: int = BORDER_WIDTH,
    max_width: int = 800,
) -> Path | None:
    """
    複数パネルを1枚の漫画ページに結合する。

    layout:
      - "vertical": 縦並び（Webtoon風）
      - "horizontal": 横並び
      - "2x2": 2x2グリッド（4コマ）
      - "grid": 自動（2,3,4枚は2列、5枚以上は2列で折り返し）
    """
    if not panel_paths:
        return None

    images = []
    for p in panel_paths:
        try:
            img = Image.open(p).convert("RGB")
            images.append(img)
        except Exception:
            continue

    if not images:
        return None

    # リサイズ（幅を揃える）
    resized = []
    for img in images:
        w, h = img.size
        ratio = max_width / w
        new_w = max_width
        new_h = int(h * ratio)
        resized.append(img.resize((new_w, new_h), Image.Resampling.LANCZOS))

    border = border_width
    out_dir = panel_paths[0].parent
    out_path = output_path or out_dir / "manga_page.png"

    if layout == "vertical":
        total_h = sum(im.size[1] for im in resized) + border * (len(resized) - 1)
        result = Image.new("RGB", (max_width, total_h), BG_COLOR)
        y = 0
        for im in resized:
            result.paste(im, (0, y))
            y += im.size[1] + border

    elif layout == "horizontal":
        total_w = sum(im.size[0] for im in resized) + border * (len(resized) - 1)
        max_h = max(im.size[1] for im in resized)
        result = Image.new("RGB", (total_w, max_h), BG_COLOR)
        x = 0
        for im in resized:
            result.paste(im, (x, 0))
            x += im.size[0] + border

    elif layout == "2x2" and len(resized) <= 4:
        # 4コマまたは少ない枚数を2x2に
        cols, rows = 2, 2
        cell_w = max_width
        cell_h = max(im.size[1] for im in resized)
        total_w = cell_w * cols + border * (cols - 1)
        total_h = cell_h * rows + border * (rows - 1)
        result = Image.new("RGB", (total_w, total_h), BG_COLOR)
        for i, im in enumerate(resized):
            col, row = i % cols, i // cols
            x = col * (cell_w + border)
            y = row * (cell_h + border)
            # 中央寄せでペースト
            px = x + (cell_w - im.size[0]) // 2
            py = y + (cell_h - im.size[1]) // 2
            result.paste(im, (px, py))

    else:
        # grid: 2列で縦に並べる
        cols = 2
        rows = (len(resized) + cols - 1) // cols
        cell_w = max_width
        cell_h = max(im.size[1] for im in resized)
        total_w = cell_w * cols + border * (cols - 1)
        total_h = cell_h * rows + border * (rows - 1)
        result = Image.new("RGB", (total_w, total_h), BG_COLOR)
        for i, im in enumerate(resized):
            col, row = i % cols, i // cols
            x = col * (cell_w + border)
            y = row * (cell_h + border)
            px = x + (cell_w - im.size[0]) // 2
            py = y + (cell_h - im.size[1]) // 2
            result.paste(im, (px, py))

    result.save(str(out_path))
    return out_path
