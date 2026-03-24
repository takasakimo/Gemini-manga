"""
テーマから漫画の構成（キャラ・コマ割り・セリフ）をプロンプト経由で生成
- プロンプトを Gemini（ブラウザ等）に貼り付け → JSON を返答させる
- 返答を貼り付けて project.yaml / characters.yaml に反映（API 不要・Cloud 対応）
"""

from pathlib import Path
import json
import re

import yaml

# プロンプトで生成させる JSON スキーマの説明
SCHEMA_INSTRUCTION = """
あなたはプロの漫画家・シナリオライターです。テーマに基づき、漫画の全構成を生成してください。

出力は必ず次のJSON形式のみを返してください。説明文やマークダウンは一切含めないでください。

{
  "title": "漫画のタイトル（日本語）",
  "characters": [
    {
      "id": "英数字のID（例: sakura）",
      "name": "日本語名",
      "name_en": "英語名（プロンプト用）",
      "description": "外見の詳細説明（英語で、髪・目・体型・服装・特徴を含む。画像生成AI用なので具体的に）",
      "personality_hints": "性格・表情の傾向（簡潔に）",
      "voice_style": "セリフの口調（例: ですます調、タメ口）"
    }
  ],
  "panels": [
    {
      "number": 1,
      "title": "この枚の見出し・タイトル",
      "characters": ["登場キャラのidリスト"],
      "koma": [
        {
          "scene": "場面・背景（例: 教室の窓際。朝の光が差し込む）",
          "shot": "構図・カメラアングル（例: 全身が入る、上半身）",
          "action": "アクション・表情（例: 手を挙げて笑顔で挨拶）",
          "dialogue": [
            {"character": "キャラid", "text": "セリフ"}
          ]
        }
      ]
    }
  ]
}

ルール:
- characters は最大5人まで（Nano Banana 2 の仕様）
- 各 panel の koma は1〜4コマ程度。ストーリーの流れに合わせて適切に分割
- セリフは自然な日本語で、キャラの口調を反映
- description は画像生成用なので、髪色・目の色・服装・身長感などを具体的に
- 4コマ漫画の場合は panel 1つに koma 4つ。普通の漫画なら複数枚で展開
"""


def _extract_json_from_text(text: str) -> str | None:
    """テキストから JSON ブロックを抽出。```json ... ``` または { ... } を探す"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        return m.group(1).strip()
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i, c in enumerate(text[start:], start):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def build_full_auto_prompt(
    theme: str,
    *,
    genre: str = "none",
    usage: str = "standard_manga",
    total_panels: int = 3,
    art_taste: str = "standard",
    design_structure: str = "auto",
) -> str:
    """Gemini に貼り付ける用の完全プロンプト（API 呼び出しなし）"""
    genre_hint = ""
    if genre and genre != "none":
        genre_hint = f"\nジャンル・世界観: {genre}"

    user_prompt = f"""
【テーマ】
{theme.strip()}
{genre_hint}

【指定】
- 用途: {usage}
- 枚数: {total_panels}枚
- 画風: {art_taste}
- コマ割り: {design_structure}
- 4コマの場合は1枚に4コマ。それ以外は1枚あたり1〜3コマ程度でストーリーを展開

上記の形式のJSONのみを出力してください。
"""
    return SCHEMA_INSTRUCTION.strip() + "\n\n" + user_prompt.strip()


def manga_dict_to_project_chars(
    data: dict,
    *,
    genre: str = "none",
    usage: str = "standard_manga",
    canvas_ratio: str = "9:16",
    design_structure: str = "auto",
    art_taste: str = "standard",
    output_mode: str = "per_koma",
) -> tuple[dict, dict]:
    """パース済み JSON オブジェクトから project_data / chars_data を構築"""
    project = {
        "title": data.get("title", "自動生成漫画"),
        "total_panels": len(data.get("panels", [])),
        "usage": usage,
        "canvas_ratio": canvas_ratio,
        "aspect_ratio": canvas_ratio,
        "genre": genre,
        "design_structure": design_structure,
        "art_taste": art_taste,
        "output_mode": output_mode,
    }

    panels = []
    for p in data.get("panels", []):
        koma_list = p.get("koma", [])
        if not koma_list:
            continue
        first_dialogue = []
        for k in koma_list:
            first_dialogue.extend(k.get("dialogue", []))
        first_text = first_dialogue[0]["text"] if first_dialogue else ""
        panels.append({
            "number": p.get("number", len(panels) + 1),
            "title": p.get("title", ""),
            "text": first_text,
            "characters": p.get("characters", []),
            "koma": koma_list,
        })

    project_data = {"project": project, "panels": panels}

    chars_data = {
        "series": {
            "title": project["title"],
            "art_style": (
                "Professional Japanese manga style: Black-and-white, screentone shading, "
                "oval speech bubbles with vertical Japanese text (tategaki), "
                "clean line art, publication quality."
            ),
            "style_negative": "Avoid: photorealistic, 3D, Western comic, horizontal text in bubbles.",
        },
        "characters": data.get("characters", []),
    }

    return project_data, chars_data


def parse_manga_json_response(raw_text: str) -> dict:
    """貼り付けた応答から JSON を取り出して dict に"""
    json_block = _extract_json_from_text(raw_text.strip()) or raw_text.strip()
    return json.loads(json_block)


def apply_pasted_json(
    raw_text: str,
    config_dir: Path,
    *,
    genre: str = "none",
    usage: str = "standard_manga",
    canvas_ratio: str = "9:16",
    design_structure: str = "auto",
    art_taste: str = "standard",
    output_mode: str = "per_koma",
) -> tuple[dict, dict]:
    """貼り付けテキストを解析し、project.yaml / characters.yaml に保存"""
    data = parse_manga_json_response(raw_text)
    project_data, chars_data = manga_dict_to_project_chars(
        data,
        genre=genre,
        usage=usage,
        canvas_ratio=canvas_ratio,
        design_structure=design_structure,
        art_taste=art_taste,
        output_mode=output_mode,
    )

    config_dir.mkdir(parents=True, exist_ok=True)
    with open(config_dir / "project.yaml", "w", encoding="utf-8") as f:
        yaml.dump(project_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    with open(config_dir / "characters.yaml", "w", encoding="utf-8") as f:
        yaml.dump(chars_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return project_data, chars_data
