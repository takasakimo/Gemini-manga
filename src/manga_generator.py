"""
Gemini 3.1 Flash Image (Nano Banana 2) を使った漫画画像生成

- キャラクター一貫性：ワークフロー内で最大5キャラ対応
- 固定プロンプトでタッチ・色調を統一
- project.yaml: 作成枚数・各コマのセリフ・構図
- characters.yaml: キャラ設定
"""

import os
from pathlib import Path

from dotenv import load_dotenv
import yaml

load_dotenv()

MODEL_ID = "gemini-3.1-flash-image-preview"


def load_config(config_dir: Path) -> tuple[dict, dict, dict]:
    """config/ から characters, project を読み込む"""
    with open(config_dir / "characters.yaml", encoding="utf-8") as f:
        chars_config = yaml.safe_load(f)

    with open(config_dir / "project.yaml", encoding="utf-8") as f:
        project_config = yaml.safe_load(f)

    return chars_config, project_config


def get_characters_for_panel(char_ids: list[str], all_characters: list[dict]) -> list[dict]:
    """コマに登場するキャラのみを id でフィルタして返す"""
    id_set = set(char_ids)
    return [c for c in all_characters if c["id"] in id_set]


def build_character_prompts(characters: list[dict]) -> str:
    """指定キャラの説明を連結したプロンプト部分を生成"""
    return "\n\n---\n\n".join(c["description"].strip() for c in characters)


def build_dialogue_section(panel: dict, char_map: dict[str, dict]) -> str:
    """セリフをプロンプト用に整形。フキダシ描画の指示を付ける"""
    dialogues = panel.get("dialogue") or []
    if not dialogues:
        return ""
    lines = []
    for d in dialogues:
        char_id = d.get("character")
        text = d.get("text", "").strip()
        if not text:
            continue
        char = char_map.get(char_id, {})
        name_en = char.get("name_en", char_id)
        lines.append(f"- Speech bubble for {name_en}: \"{text}\"")
    if not lines:
        return ""
    return "Dialogue (draw as manga speech bubbles, Japanese text):\n" + "\n".join(lines)


def load_prompt_hints(config_dir: Path) -> dict:
    """config/prompt_hints.yaml から画風・コマ割り用のプロンプトヒントを読み込む"""
    path = config_dir / "prompt_hints.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_panel_prompt(
    panel: dict,
    chars_config: dict,
    chars_in_panel: list[dict],
    project_config: dict | None = None,
) -> str:
    """
    1コマ用の完全プロンプトを構築。
    project.yaml の panel から scene, shot, action, dialogue を使う。
    project の art_taste, design_structure, genre もプロンプトに反映する。
    """
    char_prompts = build_character_prompts(chars_in_panel)
    art_style = chars_config.get("series", {}).get("art_style", "").strip()
    style_neg = chars_config.get("series", {}).get("style_negative", "").strip()

    char_map = {c["id"]: c for c in chars_config.get("characters", [])}

    scene = panel.get("scene", "")
    shot = panel.get("shot", "")
    action = panel.get("action", "")
    title = panel.get("title", "")
    dialogue_section = build_dialogue_section(panel, char_map)

    # project の usage, art_taste, design_structure, genre をプロンプトに追加
    project_hints = []
    if project_config:
        config_dir = Path(__file__).resolve().parent.parent / "config"
        hints_data = load_prompt_hints(config_dir)
        proj = project_config.get("project", {})
        usage = proj.get("usage", "standard_manga")
        art_taste = proj.get("art_taste", "standard")
        design_structure = proj.get("design_structure", "standard")
        genre = proj.get("genre", "none")
        if hints_data:
            usage_hints = hints_data.get("usage", {})
            art_hints = hints_data.get("art_taste", {})
            design_hints = hints_data.get("design_structure", {})
            genre_hints = hints_data.get("genre", {})
            if usage in usage_hints:
                project_hints.append(f"Format: {usage_hints[usage]}")
            if art_taste in art_hints:
                project_hints.append(f"Art style: {art_hints[art_taste]}")
            if design_structure in design_hints:
                project_hints.append(f"Panel/composition: {design_hints[design_structure]}")
            if genre in genre_hints and genre != "none":
                project_hints.append(f"Mood/worldview: {genre_hints[genre]}")

    # 画風・コマ割り・ジャンルは先頭で強く指定（選択内容を確実に反映）
    style_header = ""
    if project_hints:
        style_header = "STYLE REQUIREMENTS (must follow): " + " | ".join(project_hints) + "\n\n"

    parts = [
        "MOST IMPORTANT: Character consistency across the entire manga panel.",
        style_header.strip() if style_header else "",
        f"Panel title/heading (draw prominently if present): {title}" if title else "",
        "CHARACTER DESCRIPTIONS (maintain exact appearance):",
        char_prompts,
        "",
        "SCENE & COMPOSITION:",
        f"Setting: {scene}",
        f"Camera/shot: {shot}" if shot else "",
        f"Action & expression: {action}",
        "",
        dialogue_section,
        "",
        f"Base art style: {art_style}",
        f"{style_neg}",
    ]
    return "\n".join(p for p in parts if p).strip()


def generate_image(
    prompt: str,
    output_path: Path,
    api_key: str | None = None,
    aspect_ratio: str = "3:4",
) -> bool:
    """
    Gemini 3.1 Flash Image (Nano Banana 2) で画像生成

    google-genai の GenerateContentConfig + response_modalities を使用
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY を .env または環境変数で設定してください")

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise ImportError("pip install google-genai を実行してください")

    client = genai.Client(api_key=api_key)

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
    )

    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=config,
    )

    # レスポンスから画像を抽出して保存
    parts = getattr(response, "parts", None)
    if not parts and response.candidates:
        parts = response.candidates[0].content.parts
    parts = parts or []

    for part in parts:
        inline = getattr(part, "inline_data", None)
        if not inline:
            continue
        # part.as_image() で PIL Image 相当を取得
        if hasattr(part, "as_image"):
            img = part.as_image()
            if img is not None:
                out_file = output_path.with_suffix(".png")
                out_file.parent.mkdir(parents=True, exist_ok=True)
                img.save(str(out_file))
                print(f"  Saved: {out_file}")
                return True
        # fallback: inline_data.data から bytes で保存
        data = getattr(inline, "data", None)
        if data:
            out_file = output_path.with_suffix(".png")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(data)
            print(f"  Saved: {out_file}")
            return True

    print("  Warning: No image in response. Check model availability (gemini-3.1-flash-image-preview).")
    return False


def get_prompt_for_panel(panel_number: int, config_dir: Path) -> str | None:
    """
    指定コマのプロンプト文字列を取得する（APIは呼ばない）。
    コピー用・Geminiに貼り付け用。
    """
    chars_config, project_config = load_config(config_dir)
    panels = project_config.get("panels", [])
    all_chars = chars_config.get("characters", [])

    panel = next((p for p in panels if p.get("number") == panel_number), None)
    if not panel:
        return None

    char_ids = panel.get("characters", [])
    chars_in_panel = get_characters_for_panel(char_ids, all_chars)
    return build_panel_prompt(panel, chars_config, chars_in_panel, project_config)


def get_prompt_for_panel(panel_number: int, config_dir: Path) -> str:
    """
    指定コマのプロンプト文字列のみ取得（API呼び出しなし）。
    project.yaml と characters.yaml から構築する。
    """
    chars_config, project_config = load_config(config_dir)
    panels = project_config.get("panels", [])
    all_chars = chars_config.get("characters", [])

    panel = next((p for p in panels if p.get("number") == panel_number), None)
    if not panel:
        return ""

    char_ids = panel.get("characters", [])
    chars_in_panel = get_characters_for_panel(char_ids, all_chars)
    return build_panel_prompt(panel, chars_config, chars_in_panel, project_config)


def get_prompt_for_panel(
    panel_number: int,
    config_dir: Path,
) -> str:
    """
    指定コマのプロンプト文字列を返す（API呼び出しなし）。
    Gemini ブラウザ等に貼り付けて手動で画像生成する際に利用。
    """
    chars_config, project_config = load_config(config_dir)
    panels = project_config.get("panels", [])
    all_chars = chars_config.get("characters", [])

    panel = next((p for p in panels if p.get("number") == panel_number), None)
    if not panel:
        return ""

    char_ids = panel.get("characters", [])
    chars_in_panel = get_characters_for_panel(char_ids, all_chars)
    return build_panel_prompt(panel, chars_config, chars_in_panel, project_config)


def run_panel(
    panel_number: int,
    config_dir: Path,
    output_dir: Path,
) -> bool:
    """指定コマ番号の画像を1枚生成"""
    chars_config, project_config = load_config(config_dir)
    panels = project_config.get("panels", [])
    all_chars = chars_config.get("characters", [])

    panel = next((p for p in panels if p.get("number") == panel_number), None)
    if not panel:
        print(f"Panel {panel_number} not found.")
        return False

    char_ids = panel.get("characters", [])
    chars_in_panel = get_characters_for_panel(char_ids, all_chars)

    prompt = build_panel_prompt(panel, chars_config, chars_in_panel, project_config)
    output_path = output_dir / f"panel_{panel_number:03d}"

    proj = project_config.get("project", {})
    aspect = proj.get("aspect_ratio") or proj.get("canvas_ratio") or "3:4"

    print(f"Generating panel {panel_number}...")
    return generate_image(prompt, output_path, aspect_ratio=aspect)


def get_prompt_for_panel(panel_number: int, config_dir: Path) -> str | None:
    """
    指定コマのプロンプトを取得する（API呼び出しなし）。
    Gemini に貼り付けて手動で画像生成する際に使用。
    """
    chars_config, project_config = load_config(config_dir)
    panels = project_config.get("panels", [])
    all_chars = chars_config.get("characters", [])

    panel = next((p for p in panels if p.get("number") == panel_number), None)
    if not panel:
        return None

    char_ids = panel.get("characters", [])
    chars_in_panel = get_characters_for_panel(char_ids, all_chars)

    return build_panel_prompt(panel, chars_config, chars_in_panel, project_config)


def run_all(config_dir: Path, output_dir: Path) -> None:
    """全コマの画像を生成（project.yaml の panels に定義された分）"""
    _, project_config = load_config(config_dir)
    panels = project_config.get("panels", [])
    total = project_config.get("project", {}).get("total_panels")

    if total is not None and len(panels) != total:
        print(f"Note: total_panels={total} but {len(panels)} panels defined. Using defined panels.")

    for panel in panels:
        run_panel(panel["number"], config_dir, output_dir)


def main():
    base = Path(__file__).resolve().parent.parent
    config_dir = base / "config"
    output_dir = base / "output"

    import sys
    if len(sys.argv) > 1:
        try:
            num = int(sys.argv[1])
            run_panel(num, config_dir, output_dir)
        except ValueError:
            print("Usage: python -m src.manga_generator [panel_number]")
            print("  panel_number: 1-based. Omit to generate all panels.")
    else:
        run_all(config_dir, output_dir)


if __name__ == "__main__":
    main()
