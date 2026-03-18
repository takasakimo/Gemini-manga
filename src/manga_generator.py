"""
Gemini 3.1 Flash Image (Nano Banana 2) を使った漫画画像生成

- キャラクター一貫性：ワークフロー内で最大5キャラ対応
- 固定プロンプトでタッチ・色調を統一
- project.yaml: 作成枚数・各コマのセリフ・構図
- characters.yaml: キャラ設定
"""

from pathlib import Path

from dotenv import load_dotenv
import yaml

load_dotenv()


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
    """セリフをプロンプト用に整形。本物漫画風のフキダシ・縦書き指示を付ける"""
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
        lines.append(f"- Oval speech bubble with tail pointing to {name_en}, VERTICAL Japanese text (tategaki): \"{text}\"")
    if not lines:
        return ""
    return (
        "DIALOGUE (authentic Japanese manga style):\n"
        "- Oval speech bubbles with tails pointing to the speaker.\n"
        "- Draw ALL dialogue text in VERTICAL orientation (tategaki, right-to-left columns) as in real manga.\n"
        "- Clear gutters (white space) between panels. Clean black panel borders.\n"
        "- Add onomatopoeia if appropriate (e.g. コツ for footsteps, ザッ for steps, ドキ for heartbeat).\n"
        + "\n".join(lines)
    )


def load_prompt_hints(config_dir: Path) -> dict:
    """config/prompt_hints.yaml から画風・コマ割り用のプロンプトヒントを読み込む"""
    path = config_dir / "prompt_hints.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _get_manga_production_block() -> str:
    """本物漫画風の描画指示ブロック。プロンプト先頭で強く指定"""
    return (
        "MANGA PRODUCTION (authentic Japanese manga): "
        "Black-and-white, screentone (halftone dots) for shading. "
        "Oval speech bubbles with tails, VERTICAL Japanese text (tategaki). "
        "Onomatopoeia as graphic elements. Gutters between panels. "
        "Focus lines, action lines for drama."
    )


def _get_emotional_storytelling_block() -> str:
    """セリフ・感情に応じた効果・コマサイズの判断指示"""
    return (
        "EMOTIONAL STORYTELLING (analyze dialogue & action per panel): "
        "Strong emotion (anger, determination, surprise, climax) → add focus lines (集中線), make that panel LARGER. "
        "Nervousness, embarrassment → sweat drop (汗), blush lines (照れ). "
        "Movement, action → speed lines, action lines (効果線). "
        "Punchline, key revelation → give that panel more space (larger). "
        "Vary panel sizes to emphasize emotional beats and guide reader focus."
    )


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
        design_structure = proj.get("design_structure", "auto")
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

    manga_techniques = (
        "MANGA TECHNIQUES: Use screentone (halftone dot patterns) for shading. "
        "Add focus lines or speed lines for emphasis when appropriate. "
        "Action lines for movement. Subtle effects: blush lines, sweat drops for emotion."
    )
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
        manga_techniques,
        "",
        dialogue_section,
        "",
        f"Base art style: {art_style}",
        f"{style_neg}",
    ]
    return "\n".join(p for p in parts if p).strip()


def build_page_prompt(
    panel: dict,
    chars_config: dict,
    chars_in_panel: list[dict],
    project_config: dict | None = None,
) -> str:
    """
    1枚目（複数コマ）を1枚の画像用にまとめたプロンプトを構築。
    各コマの場面・構図・セリフを1つの manga page として記述する。
    """
    char_prompts = build_character_prompts(chars_in_panel)
    art_style = chars_config.get("series", {}).get("art_style", "").strip()
    style_neg = chars_config.get("series", {}).get("style_negative", "").strip()
    char_map = {c["id"]: c for c in chars_config.get("characters", [])}
    title = panel.get("title", "")

    koma_list = _get_koma_list(panel)
    num_panels = len(koma_list)
    proj = (project_config or {}).get("project", {})
    design_structure = proj.get("design_structure", "auto")

    # project hints
    project_hints = []
    if project_config:
        config_dir = Path(__file__).resolve().parent.parent / "config"
        hints_data = load_prompt_hints(config_dir)
        proj = project_config.get("project", {})
        usage = proj.get("usage", "standard_manga")
        art_taste = proj.get("art_taste", "standard")
        design_structure = proj.get("design_structure", "auto")
        genre = proj.get("genre", "none")
        if hints_data:
            if usage in hints_data.get("usage", {}):
                project_hints.append(f"Format: {hints_data['usage'][usage]}")
            if art_taste in hints_data.get("art_taste", {}):
                project_hints.append(f"Art style: {hints_data['art_taste'][art_taste]}")
            if design_structure in hints_data.get("design_structure", {}):
                project_hints.append(f"Panel/composition: {hints_data['design_structure'][design_structure]}")
            if genre in hints_data.get("genre", {}) and genre != "none":
                project_hints.append(f"Mood/worldview: {hints_data['genre'][genre]}")

    style_header = ""
    if project_hints:
        style_header = "STYLE REQUIREMENTS (must follow): " + " | ".join(project_hints) + "\n\n"

    # design_structure が auto のときは AI にコマ割りを判断させる
    layout_mode_auto = design_structure == "auto"

    if layout_mode_auto:
        # コマ数はユーザー指定を厳守。AI が判断するのは配置・サイズ・レイアウトのみ
        panel_descs = []
        for ki, koma in enumerate(koma_list):
            scene = koma.get("scene", "")
            shot = koma.get("shot", "")
            action = koma.get("action", "")
            dialogues = koma.get("dialogue") or []
            dial_lines = []
            for d in dialogues:
                text = d.get("text", "").strip()
                if not text:
                    continue
                char = char_map.get(d.get("character", ""), {})
                name_en = char.get("name_en", d.get("character", ""))
                dial_lines.append(f'  - {name_en}: "{text}"')
            dial_str = "\n".join(dial_lines) if dial_lines else "  (none)"
            panel_descs.append(
                f"**Panel {ki + 1}:**\n"
                f"  Setting: {scene or '(as appropriate)'}\n"
                f"  Camera/shot: {shot or '(as appropriate)'}\n"
                f"  Action: {action or '(as appropriate)'}\n"
                f"  Dialogue: oval bubbles with tails, VERTICAL Japanese text (tategaki):\n{dial_str}"
            )
        panel_section = "\n\n".join(panel_descs)
        content_label = f"PANEL CONTENT (draw EXACTLY {num_panels} panels - do NOT merge or reduce. Each panel below must appear):"
        layout = (
            f"LAYOUT: You MUST draw exactly {num_panels} panels. Do NOT merge panels or reduce the count.\n"
            f"YOU decide: where to place each panel (placement), panel sizes (make emotionally intense panels LARGER - climax, punchline, revelation), "
            "arrangement (2x2 grid, vertical stack, or mixed). Use gutters and clear borders. "
            "Draw ALL panels in ONE single image. Output MUST be one combined image, never separate."
        )
    else:
        # 固定レイアウト
        panel_descs = []
        for ki, koma in enumerate(koma_list):
            scene = koma.get("scene", "")
            shot = koma.get("shot", "")
            action = koma.get("action", "")
            dialogues = koma.get("dialogue") or []
            dial_lines = []
            for d in dialogues:
                text = d.get("text", "").strip()
                if not text:
                    continue
                char = char_map.get(d.get("character", ""), {})
                name_en = char.get("name_en", d.get("character", ""))
                dial_lines.append(f'  - {name_en}: "{text}"')
            dial_str = "\n".join(dial_lines) if dial_lines else "  (none)"
            panel_descs.append(
                f"**Panel {ki + 1}:**\n"
                f"  Setting: {scene or '(as appropriate)'}\n"
                f"  Camera/shot: {shot or '(as appropriate)'}\n"
                f"  Action: {action or '(as appropriate)'}\n"
                f"  Dialogue: oval bubbles with tails, VERTICAL Japanese text (tategaki):\n{dial_str}"
            )
        panel_section = "\n\n".join(panel_descs)
        content_label = "PANEL CONTENT (draw each panel as described, all within the same image):"
        if num_panels == 4:
            layout = (
                "LAYOUT: Draw ALL 4 panels in ONE single image. "
                "Use a 2x2 grid (four equal panels in 2 rows × 2 columns) "
                "with clear panel borders. This is a FOUR-PANEL MANGA format (yonkoma). "
                "Output MUST be a single combined image, never separate images."
            )
        elif num_panels >= 2:
            layout = (
                f"LAYOUT: Draw ALL {num_panels} panels in ONE single image. "
                "Arrange panels vertically (top to bottom) with clear borders between each. "
                "Output MUST be a single combined image containing all panels, never separate images."
            )
        else:
            layout = f"LAYOUT: Single panel. Output as one image."

    manga_page_style = (
        "MANGA PAGE STYLE: Clean white gutters between panels. Black panel borders. "
        "Screentone (halftone dots) for shading. Oval speech bubbles with tails, vertical Japanese text. "
        "Add onomatopoeia as graphic elements when fitting (e.g. コツ ザッ ドキ). "
        "Focus lines and action lines for emotional/action scenes."
    )
    manga_production = _get_manga_production_block()
    emotional_storytelling = _get_emotional_storytelling_block()
    parts = [
        "CRITICAL: Produce ONE single image containing multiple manga panels. Do NOT generate separate images.",
        "Draw a SINGLE manga page where ALL panels share the same canvas/frame.",
        "MOST IMPORTANT: Character consistency across ALL panels on this page.",
        manga_production,
        emotional_storytelling,
        style_header.strip() if style_header else "",
        f"Page title/heading (draw prominently if present): {title}" if title else "",
        "CHARACTER DESCRIPTIONS (maintain exact appearance in every panel):",
        char_prompts,
        "",
        manga_page_style,
        "",
        layout,
        "",
        content_label if layout_mode_auto else "PANEL CONTENT (draw each panel as described, all within the same image):",
        "",
        panel_section,
        "",
        f"Base art style: {art_style}",
        style_neg,
    ]
    return "\n".join(p for p in parts if p).strip()


def _get_koma_list(panel: dict) -> list[dict]:
    """枚目からコマリストを取得。旧形式(scene/shot/action)の場合は1コマに変換"""
    koma = panel.get("koma") or []
    if not koma and (panel.get("scene") or panel.get("shot") or panel.get("action")):
        ex_d = panel.get("dialogue") or []
        koma = [{"scene": panel.get("scene", ""), "shot": panel.get("shot", ""), "action": panel.get("action", ""), "dialogue": ex_d}]
    if not koma:
        koma = [{"scene": "（未設定）", "shot": "（適切な構図）", "action": "（未設定）", "dialogue": []}]
    for k in koma:
        if "dialogue" not in k:
            k["dialogue"] = []
    return koma


def build_panel_prompt_with_koma(
    panel: dict,
    koma: dict,
    chars_config: dict,
    chars_in_panel: list[dict],
    project_config: dict | None,
) -> str:
    """コマ単位でプロンプトを構築。koma.dialogue を使用（コマに紐づいたセリフ）"""
    panel_for_prompt = {
        **panel,
        "scene": koma.get("scene", ""),
        "shot": koma.get("shot", ""),
        "action": koma.get("action", ""),
        "dialogue": koma.get("dialogue") or [],
    }
    return build_panel_prompt(panel_for_prompt, chars_config, chars_in_panel, project_config)


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


def _flatten_panels(panels: list[dict]) -> list[tuple[str, dict, dict]]:
    """枚目・コマをフラット化。(label, panel_merged, koma) のリストを返す"""
    result = []
    for p in panels:
        koma_list = p.get("koma") or []
        if not koma_list and (p.get("scene") or p.get("shot") or p.get("action")):
            ex_d = p.get("dialogue") or []
            koma_list = [{"scene": p.get("scene", ""), "shot": p.get("shot", ""), "action": p.get("action", ""), "dialogue": ex_d}]
        if not koma_list:
            koma_list = [{"scene": "（未設定）", "shot": "（適切な構図）", "action": "（未設定）", "dialogue": []}]
        for ki, koma in enumerate(koma_list):
            if "dialogue" not in koma:
                koma["dialogue"] = []
            label = f"{p['number']}枚目・{ki + 1}コマ目"
            merged = {**p, "scene": koma.get("scene", ""), "shot": koma.get("shot", ""), "action": koma.get("action", ""), "dialogue": koma.get("dialogue") or []}
            result.append((label, merged, koma))
    return result


def get_all_prompts_flat(config_dir: Path, output_mode: str = "per_page") -> list[tuple[str, str]]:
    """
    プロンプトを取得。
    - per_koma: 各コマごとに1プロンプト（コマ数分）
    - per_page: 1枚目ごとに1プロンプト（複数コマを1枚の画像用にまとめる）
    """
    chars_config, project_config = load_config(config_dir)
    panels = project_config.get("panels", [])
    all_chars = chars_config.get("characters", [])
    proj = project_config.get("project", {})
    mode = proj.get("output_mode", output_mode)

    if mode == "per_page":
        result = []
        for p in panels:
            char_ids = p.get("characters", [])
            chars_in = get_characters_for_panel(char_ids, all_chars)
            prompt = build_page_prompt(p, chars_config, chars_in, project_config)
            label = f"{p.get('number', 0)}枚目（全コマ1枚）"
            result.append((label, prompt))
        return result

    # per_koma
    result = []
    for label, merged, _ in _flatten_panels(panels):
        char_ids = merged.get("characters", [])
        chars_in = get_characters_for_panel(char_ids, all_chars)
        prompt = build_panel_prompt(merged, chars_config, chars_in, project_config)
        result.append((label, prompt))
    return result


def main():
    """CLI: プロンプト表示のみ（API画像生成は削除済み）"""
    base = Path(__file__).resolve().parent.parent
    config_dir = base / "config"
    prompts = get_all_prompts_flat(config_dir)
    for label, prompt_text in prompts:
        print(f"\n{'='*50}\n【{label}】\n{'='*50}\n{prompt_text}")


if __name__ == "__main__":
    main()
