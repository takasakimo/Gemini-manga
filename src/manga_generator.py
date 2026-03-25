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

# 1回の画像生成に載せるコマの上限（ユーザー方針: 最大4コマ／1画像）
KOMA_PER_IMAGE_MAX = 4


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
        "- English names below are for you to match speakers visually only—do NOT letter those English names on the page.\n"
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


def _get_forbidden_lettering_block() -> str:
    """
    画像にプロンプト由来の文字が出ないよう、本文の先頭で強く指定。
    英日混在（Gemini 画像向け）。
    """
    return (
        "【最優先・禁止】この指示文に出てくる英単語や見出しを、漫画の絵の中に文字として描かないこと。\n"
        "CRITICAL — NEVER draw on the artwork: page/panel numbers; fractions like 1/3, 2/3, 3/3; "
        "'Panel 1', '1枚目', 'コマ1'; progress counters; corner stamps; margin notes; chapter numbers that are only metadata; "
        "watermarks; the words Setting, Camera, Action, Dialogue, LAYOUT, PANEL, CRITICAL, FORBIDDEN; "
        "dashes used as section dividers from this prompt; XML/tag brackets or tag names; "
        "any label that looks like a prompt or editor UI.\n"
        "Below: technical descriptions for YOU only — interpret visually, do NOT letter them onto the page.\n"
        "描いてよい文字: 吹き出し・思考のふきだしのセリフ、画面内の看板・スクリーンの文言（物語の一部として自然なもの）、"
        "擬音（ザワザワ、ドキッ 等の漫画表現としての文字）。それ以外の説明文は絵に書かない。"
    )


def _get_bounded_multi_panel_block(num_panels: int) -> str:
    """1画像あたり最大 KOMA_PER_IMAGE_MAX コマであることを明示（1〜4コマ）"""
    n = min(KOMA_PER_IMAGE_MAX, max(1, num_panels))
    return (
        f"PANEL BUDGET: ONE image with exactly {n} manga panel(s). "
        f"Never more than {KOMA_PER_IMAGE_MAX} bordered panels in this output. "
        "Do not add empty filler panels or extra cells beyond the descriptions below. "
        f"日本語: この1枚に描くコマは{n}コマ（同一画像・上限{KOMA_PER_IMAGE_MAX}コマ）。余計なコマを増やさない。"
    )


def _get_forbidden_lettering_footer() -> str:
    return (
        "FINAL: The image must look like a finished manga page with NO instructional text, NO panel counters, "
        "NO '1/3' style markers, and NO English prompt fragments visible anywhere."
    )


def _append_style_negative_no_meta(style_neg: str) -> str:
    extra = (
        " No page numbers, no panel index numbers, no 1/3-style fractions, no prompt labels or metadata as visible text."
    )
    return (style_neg + extra).strip() if style_neg else extra.strip()


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

    pacing = ""
    if project_config:
        pacing = (project_config.get("project") or {}).get("story_pacing_hint", "").strip()

    manga_techniques = (
        "MANGA TECHNIQUES: Use screentone (halftone dot patterns) for shading. "
        "Add focus lines or speed lines for emphasis when appropriate. "
        "Action lines for movement. Subtle effects: blush lines, sweat drops for emotion."
    )
    parts = [
        _get_forbidden_lettering_block(),
        "MOST IMPORTANT: Character consistency across the entire manga panel.",
        pacing,
        style_header.strip() if style_header else "",
        f"In-world title or heading (only if clearly a sign/poster in the scene): {title}" if title else "",
        "CHARACTER DESCRIPTIONS (for appearance only; do not paste this block as visible text):",
        char_prompts,
        "",
        "SINGLE PANEL — draw the following as art, not as captions or labels on the page:",
        f"Background and place: {scene}",
        f"Camera and framing: {shot}" if shot else "",
        f"Action, poses, expressions: {action}",
        "",
        manga_techniques,
        "",
        dialogue_section,
        "",
        _get_forbidden_lettering_footer(),
        f"Base art style: {art_style}",
        _append_style_negative_no_meta(style_neg),
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
    if num_panels > KOMA_PER_IMAGE_MAX:
        koma_list = koma_list[:KOMA_PER_IMAGE_MAX]
        num_panels = KOMA_PER_IMAGE_MAX
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
                "<scene_instruction>\n"
                f"{scene or 'Appropriate setting for this beat'}\n"
                f"Framing: {shot or 'appropriate'}\n"
                f"Action: {action or 'appropriate'}\n"
                f"Speech in oval bubbles only, VERTICAL Japanese (tategaki):\n{dial_str}\n"
                "</scene_instruction>"
            )
        panel_section = "\n\n".join(panel_descs)
        content_label = (
            f"PANEL CONTENT: draw exactly {num_panels} separate comic panels (this number is for you only—do NOT write it on the page). "
            "Each block below is one panel; do NOT merge or reduce count."
        )
        layout = (
            f"LAYOUT: Exactly {num_panels} panels in ONE image. Do NOT merge or reduce.\n"
            "YOU decide placement, relative sizes (larger for climax/punchline), grid vs vertical stack. Gutters and black borders. "
            "One combined image only. Do NOT write the panel count or the word LAYOUT on the artwork.\n"
            "The <scene_instruction>...</scene_instruction> wrappers are invisible metadata—never draw angle brackets, tag names, or English field labels."
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
                "<scene_instruction>\n"
                f"{scene or 'Appropriate setting for this beat'}\n"
                f"Framing: {shot or 'appropriate'}\n"
                f"Action: {action or 'appropriate'}\n"
                f"Speech in oval bubbles only, VERTICAL Japanese (tategaki):\n{dial_str}\n"
                "</scene_instruction>"
            )
        panel_section = "\n\n".join(panel_descs)
        content_label = (
            "PANEL CONTENT: draw each segment below as one comic cell in the same image. "
            "Do NOT render tag names, brackets, or English structural words on the canvas."
        )
        if num_panels == 4:
            layout = (
                "LAYOUT: Four panels in ONE image, 2×2 yonkoma grid, clear borders. Single combined image only. "
                "Do NOT write panel counts, LAYOUT, or instruction words on the art. "
                "<scene_instruction> blocks are metadata only—never draw tags or labels from them."
            )
        elif num_panels >= 2:
            layout = (
                f"LAYOUT: {num_panels} panels in ONE image, vertical stack top-to-bottom, clear borders. "
                "Single combined image. Do NOT write numbers, fractions, or English UI words on the page. "
                "<scene_instruction> blocks are metadata only—never draw tags or labels from them."
            )
        else:
            layout = "LAYOUT: Single panel, one image. Do not add instructional text to the artwork."

    manga_page_style = (
        "MANGA PAGE STYLE: Clean white gutters between panels. Black panel borders. "
        "Screentone (halftone dots) for shading. Oval speech bubbles with tails, vertical Japanese text. "
        "Add onomatopoeia as graphic elements when fitting (e.g. コツ ザッ ドキ). "
        "Focus lines and action lines for emotional/action scenes. "
        "No corner boxes with technical titles unless clearly in-world (e.g. a diegetic screen)."
    )
    manga_production = _get_manga_production_block()
    emotional_storytelling = _get_emotional_storytelling_block()
    pacing = (project_config.get("project") or {}).get("story_pacing_hint", "").strip() if project_config else ""
    parts = [
        _get_forbidden_lettering_block(),
        _get_bounded_multi_panel_block(num_panels),
        "CRITICAL: Produce exactly ONE image file. All described manga panels must appear in that single image—never split into separate image files.",
        "Draw a SINGLE manga page where ALL panels share the same canvas/frame.",
        "MOST IMPORTANT: Character consistency across ALL panels on this page.",
        pacing,
        manga_production,
        emotional_storytelling,
        style_header.strip() if style_header else "",
        f"In-world page title (only as a diegetic sign, poster, or chapter art—never as a bare fraction or counter): {title}" if title else "",
        "CHARACTER DESCRIPTIONS (appearance reference only; do not paste as floating captions):",
        char_prompts,
        "",
        manga_page_style,
        "",
        layout,
        "",
        content_label,
        "",
        panel_section,
        "",
        _get_forbidden_lettering_footer(),
        f"Base art style: {art_style}",
        _append_style_negative_no_meta(style_neg),
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


def _merge_ordered_char_ids(parent_panels: list[dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for p in parent_panels:
        for cid in p.get("characters") or []:
            if cid not in seen:
                seen.add(cid)
                out.append(cid)
    return out


def _build_koma_chunks_global(
    panels: list[dict],
    max_koma: int = KOMA_PER_IMAGE_MAX,
) -> list[tuple[str, dict]]:
    """
    全「枚」をまたいでコマを時系列順に並べ、max_koma 件ごとに1画像用の仮想パネルを返す。
    （旧 per_koma 相当：プロンプト本数は ceil(総コマ数 / max_koma)）
    """
    ordered: list[tuple[dict, dict]] = []
    for p in sorted(panels, key=lambda x: x.get("number", 0)):
        for k in _get_koma_list(p):
            ordered.append((p, k))

    out: list[tuple[str, dict]] = []
    for start in range(0, len(ordered), max_koma):
        chunk = ordered[start : start + max_koma]
        komas = [t[1] for t in chunk]
        parents = [t[0] for t in chunk]
        syn = {
            "number": parents[0].get("number", 1),
            "title": "",
            "text": parents[0].get("text", ""),
            "characters": _merge_ordered_char_ids(parents),
            "koma": komas,
        }
        i1 = start + 1
        i2 = start + len(chunk)
        label = f"コマ{i1}〜{i2}（1画像・{len(chunk)}コマ）"
        out.append((label, syn))
    return out


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


def get_all_prompts_from_data(
    chars_config: dict,
    project_config: dict,
    output_mode: str | None = None,
) -> list[tuple[str, str]]:
    """
    メモリ上の project / characters から画像用プロンプト一覧を構築。
    output_mode が None のときは project.project.output_mode を使用。
    """
    panels = project_config.get("panels", [])
    all_chars = chars_config.get("characters", [])
    proj = project_config.get("project", {})
    mode = output_mode if output_mode is not None else proj.get("output_mode", "per_koma")

    if mode == "per_page":
        result = []
        for p in sorted(panels, key=lambda x: x.get("number", 0)):
            klist = _get_koma_list(p)
            if not klist:
                continue
            char_ids = p.get("characters", [])
            chars_in = get_characters_for_panel(char_ids, all_chars)
            for start in range(0, len(klist), KOMA_PER_IMAGE_MAX):
                chunk = klist[start : start + KOMA_PER_IMAGE_MAX]
                syn = {**p, "koma": chunk}
                label = (
                    f"{p.get('number', 0)}枚目 コマ{start + 1}〜{start + len(chunk)} "
                    f"（1画像・最大{KOMA_PER_IMAGE_MAX}コマ）"
                )
                prompt = build_page_prompt(syn, chars_config, chars_in, project_config)
                result.append((label, prompt))
        return result

    # per_koma: 連続コマを最大4コマずつ1画像にまとめる（1コマ1画像ではない）
    result = []
    for label, syn in _build_koma_chunks_global(panels, KOMA_PER_IMAGE_MAX):
        char_ids = syn.get("characters", [])
        chars_in = get_characters_for_panel(char_ids, all_chars)
        prompt = build_page_prompt(syn, chars_config, chars_in, project_config)
        result.append((label, prompt))
    return result


def get_all_prompts_flat(config_dir: Path, output_mode: str = "per_koma") -> list[tuple[str, str]]:
    """
    プロンプトを取得。
    - per_koma: 連続コマを最大4コマまで1画像にまとめたプロンプト（長いときは複数プロンプト）
    - per_page: project の各「枚」内のコマを、最大4コマ単位で1画像プロンプトに分割
    """
    chars_config, project_config = load_config(config_dir)
    proj = project_config.get("project", {})
    mode = proj.get("output_mode", output_mode)
    return get_all_prompts_from_data(chars_config, project_config, mode)


def _effective_theme_panel_count(theme: str, base: int, *, max_panels: int = 10) -> tuple[int, bool]:
    """
    テーマの文字数に応じて枚数を増やす。base はユーザー指定の最小枚数（上限 max_panels）。
    戻り値: (実際の枚数, ユーザー指定より増えたか)
    """
    base = max(1, min(max_panels, int(base)))
    n = len(theme.strip())
    # おおよそ 55 文字超過分ごとに +1 枚（長い説明ほどコマを分割しやすくする）
    extra = max(0, (n - 35) // 55)
    eff = min(max_panels, base + extra)
    eff = max(base, eff)
    return eff, eff > base


def _build_story_pacing_hint(theme: str, *, panel_expanded: bool, four_panel: bool) -> str:
    """長文テーマ・枚数拡張時にプロンプトへ織り込む読みやすさ指示（英日混在）"""
    parts: list[str] = []
    n = len(theme.strip())
    if four_panel and n >= 60:
        parts.append(
            "FOUR-PANEL READABILITY: Theme text is long—each cell ONE clear idea; short vertical Japanese in bubbles; "
            "no tiny crowded text. 4コマそれぞれに詰め込みすぎない／セリフは短めの縦書きで。"
        )
    elif n >= 80:
        parts.append(
            "READABILITY: Story brief is long—THIS image is ONE beat only; keep dialogue concise and legible (vertical tategaki); "
            "never crowd the whole synopsis into one panel. 1コマ1要点／セリフは読みやすい量だけ。"
        )
    if panel_expanded and not four_panel:
        parts.append(
            "MULTI-IMAGE PACING: Extra panels were allocated for this long summary—spread beats across images; "
            "one main moment per generated image so text stays readable."
        )
    return " ".join(parts)


def _load_chars_config(config_dir: Path) -> dict:
    path = config_dir / "characters.yaml"
    if not path.exists():
        return {"series": {}, "characters": []}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {"series": {}, "characters": []}


def build_theme_image_prompts(
    theme: str,
    config_dir: Path,
    *,
    genre: str = "none",
    usage: str = "standard_manga",
    total_panels: int = 3,
    art_taste: str = "standard",
    design_structure: str = "auto",
    canvas_ratio: str = "9:16",
    output_mode: str = "per_koma",
    four_panel: bool = False,
    selected_character_ids: list[str] | None = None,
    expand_panels_by_text: bool = True,
) -> tuple[list[tuple[str, str]], dict]:
    """
    テーマと選択項目だけから、Gemini 画像生成にそのまま貼るプロンプトを組み立てる。
    JSON や中間ファイルは不要。既存の characters.yaml があれば一貫性のため利用する。

    selected_character_ids: 登場させるキャラの id を順に最大5人。None または空リストのときは
      YAML にいるキャラを全員（最大5人）。YAML に1人もいないときだけ仮の主人公を補う。
    expand_panels_by_text: True のとき、テーマが長いほど枚数を自動で増やす（最大10枚）。

    戻り値: (プロンプトのリスト, メタ情報 dict)
    """
    theme = (theme or "").strip()
    if not theme:
        raise ValueError("テーマが空です")

    chars_config = _load_chars_config(config_dir)
    all_from_file = list(chars_config.get("characters") or [])

    if all_from_file:
        if selected_character_ids:
            by_id = {c["id"]: c for c in all_from_file}
            characters = [by_id[i] for i in selected_character_ids if i in by_id][:5]
            if not characters:
                characters = all_from_file[:5]
        else:
            characters = all_from_file[:5]
    else:
        characters = []

    if not characters:
        characters = [{
            "id": "lead",
            "name": "主人公",
            "name_en": "Protagonist",
            "description": (
                f"Main character(s) appropriate for this story: {theme}. "
                "Distinct, memorable design; same hair, face, outfit, and body proportions in every panel."
            ),
            "personality_hints": "Expressions and poses that fit the story beats",
            "voice_style": "Natural Japanese dialogue in speech bubbles",
        }]
        series = chars_config.get("series") or {}
        if not series.get("art_style"):
            series = {
                **series,
                "title": series.get("title") or "Theme manga",
                "art_style": (
                    "Professional Japanese manga: black-and-white, screentone halftone shading, "
                    "clean ink lines, oval speech bubbles with VERTICAL Japanese (tategaki), "
                    "onomatopoeia as graphic elements, publication quality."
                ),
                "style_negative": (
                    "Avoid: photorealistic, 3D render, Western comic layout, horizontal text in bubbles."
                ),
            }
        chars_config = {"series": series, "characters": characters}

    char_ids = [c["id"] for c in characters[:5]]

    user_base_panels = max(1, min(10, int(total_panels)))
    panel_expanded = False
    effective_panels = user_base_panels
    if not four_panel:
        if expand_panels_by_text:
            effective_panels, panel_expanded = _effective_theme_panel_count(
                theme, user_base_panels, max_panels=10
            )
        else:
            effective_panels = user_base_panels

    story_pacing_hint = _build_story_pacing_hint(
        theme, panel_expanded=panel_expanded, four_panel=four_panel
    )

    if four_panel:
        koma4 = [
            ("起", "Introduce the situation and characters clearly."),
            ("承", "Develop the story along the theme; tension or comedy builds."),
            ("転", "Twist, surprise, or turning point."),
            ("結", "Punchline, resolution, or warm closing beat."),
        ]
        koma_list = []
        for idx, (label, desc) in enumerate(koma4, start=1):
            koma_list.append({
                "scene": f"Story theme: {theme}\n4-koma beat [{label}]: {desc}",
                "shot": "One cell in a vertical four-panel yonkoma strip; clear gutters; no cell numbers on the art",
                "action": (
                    f"Show 「{label}」 moment vividly. Add vertical Japanese dialogue in speech bubbles where natural."
                ),
                "dialogue": [],
            })
        panels = [{
            "number": 1,
            "title": "",
            "text": theme,
            "characters": char_ids,
            "koma": koma_list,
        }]
        n_pages = 1
        effective_panels = 1
    else:
        beat_labels = [
            "Opening: establish setting and mood",
            "Rising action: story moves forward",
            "Turn or climax: emotion or stakes peak",
            "Falling action or punchline setup",
            "Resolution or afterglow",
            "Extra story beat",
            "Further development",
            "Continuation",
            "Near ending",
            "Final beat",
        ]
        shots = [
            "Wide establishing shot",
            "Medium shot on character(s)",
            "Close-up on face or hands",
            "Dynamic angle (low or dutch)",
            "Two-shot or interaction framing",
        ]
        panels = []
        for i in range(effective_panels):
            beat = beat_labels[min(i, len(beat_labels) - 1)]
            shot = shots[i % len(shots)]
            panels.append({
                "number": i + 1,
                "title": "",
                "text": theme,
                "characters": char_ids,
                "koma": [{
                    "scene": (
                        f"STORY THEME (must read clearly in the art): {theme}\n"
                        f"Narrative beat for this image: {beat}. "
                        f"(Sequential story; do not draw page numbers, fractions, or step counters on the art.)"
                    ),
                    "shot": shot,
                    "action": (
                        "Characters and props consistent with the theme; natural acting. "
                        "Use oval speech bubbles with VERTICAL Japanese (tategaki) where dialogue helps the scene."
                    ),
                    "dialogue": [],
                }],
            })
        n_pages = effective_panels

    project_config = {
        "project": {
            "title": theme[:60] + ("…" if len(theme) > 60 else ""),
            "total_panels": n_pages,
            "usage": usage,
            "canvas_ratio": canvas_ratio,
            "aspect_ratio": canvas_ratio,
            "genre": genre,
            "design_structure": design_structure,
            "art_taste": art_taste,
            "output_mode": output_mode,
            "story_pacing_hint": story_pacing_hint,
        },
        "panels": panels,
    }

    prompts = get_all_prompts_from_data(chars_config, project_config, output_mode)
    meta = {
        "effective_panels": n_pages,
        "base_panels": user_base_panels,
        "expanded": bool(panel_expanded and not four_panel),
        "theme_chars": len(theme),
        "expand_enabled": bool(expand_panels_by_text and not four_panel),
    }
    return prompts, meta


def main():
    """CLI: プロンプト表示のみ（API画像生成は削除済み）"""
    base = Path(__file__).resolve().parent.parent
    config_dir = base / "config"
    prompts = get_all_prompts_flat(config_dir)
    for label, prompt_text in prompts:
        print(f"\n{'='*50}\n【{label}】\n{'='*50}\n{prompt_text}")


if __name__ == "__main__":
    main()
