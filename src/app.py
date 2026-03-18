"""
漫画生成 Web UI（Streamlit）
スクリーンショット参考アプリ風の3ステップ項目選択インターフェース
"""

import yaml
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Gemini 漫画生成",
    page_icon="📖",
    layout="wide",
)

BASE = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE / "config"
OUTPUT_DIR = BASE / "output"


def load_options():
    """config/options.yaml から選択肢を読み込む"""
    path = CONFIG_DIR / "options.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_characters():
    """config/characters.yaml からキャラ一覧を読み込む"""
    path = CONFIG_DIR / "characters.yaml"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("characters", [])


def load_characters_full():
    """characters.yaml を丸ごと読み込む"""
    path = CONFIG_DIR / "characters.yaml"
    if not path.exists():
        return {"series": {}, "characters": []}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_characters(data: dict):
    """characters.yaml に保存"""
    path = CONFIG_DIR / "characters.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def load_character_template():
    """キャラクター作成用テンプレートを読み込む"""
    path = CONFIG_DIR / "character_template.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_description_from_template(template_str: str, values: dict) -> str:
    """テンプレート文字列に値を当てはめて description を生成"""
    result = template_str
    for key, val in values.items():
        if val is None:
            val = ""
        result = result.replace(f"{{{key}}}", str(val).strip())
    return result.strip()


def load_project():
    """config/project.yaml からプロジェクト設定を読み込む"""
    path = CONFIG_DIR / "project.yaml"
    if not path.exists():
        return {"project": {}, "panels": []}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_project(project_data: dict):
    """project.yaml に保存"""
    path = CONFIG_DIR / "project.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(project_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def get_output_images():
    """output/ 内のPNG画像をパス順で取得"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = sorted(OUTPUT_DIR.glob("panel_*.png"))
    return paths


def render_gallery_section(key_prefix: str = "gallery"):
    """
    生成済み画像をプレビュー表示し、ダウンロードボタンを表示する。
    漫画生成タブ・生成済み画像タブ両方で利用。
    """
    paths = get_output_images()
    if not paths:
        st.info("まだ画像がありません。「画像を生成」ボタンで作成するか、既存画像を output/ フォルダに配置してください。")
        return False

    cols = st.columns(min(3, len(paths)))
    for idx, img_path in enumerate(paths):
        col = cols[idx % len(cols)]
        with col:
            st.markdown(f"**{img_path.name}**")
            try:
                st.image(str(img_path))
                with open(img_path, "rb") as f:
                    data = f.read()
                st.download_button(
                    f"💾 保存",
                    data=data,
                    file_name=img_path.name,
                    mime="image/png",
                    key=f"{key_prefix}_dl_{img_path.stem}",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"読み込みエラー: {e}")

    # コマ割りセクション
    st.divider()
    st.subheader("📐 コマ割り")
    st.caption("複数のコマを1枚の漫画ページにまとめます。")
    layout_opts = [
        ("vertical", "縦並び（Webtoon風）"),
        ("horizontal", "横並び"),
        ("2x2", "2×2（4コマ）"),
        ("grid", "グリッド（2列）"),
    ]
    layout_key = st.selectbox(
        "レイアウト",
        range(len(layout_opts)),
        format_func=lambda i: layout_opts[i][1],
        key=f"{key_prefix}_layout",
    )
    layout = layout_opts[layout_key][0]
    if st.button("📐 コマ割りで1枚にまとめる", key=f"{key_prefix}_compose"):
        try:
            from src.panel_composer import get_panel_paths, compose_panels
        except ImportError:
            from panel_composer import get_panel_paths, compose_panels
        panel_paths = get_panel_paths(OUTPUT_DIR)
        if panel_paths:
            out_path = compose_panels(panel_paths, layout=layout, output_path=OUTPUT_DIR / "manga_page.png")
            if out_path:
                st.success("manga_page.png を生成しました")
                st.rerun()
        else:
            st.warning("結合するパネル画像がありません")

    manga_page = OUTPUT_DIR / "manga_page.png"
    if manga_page.exists():
        st.markdown("**manga_page.png**")
        try:
            st.image(str(manga_page))
            with open(manga_page, "rb") as f:
                data = f.read()
            st.download_button(
                "💾 コマ割り画像を保存",
                data=data,
                file_name="manga_page.png",
                mime="image/png",
                key=f"{key_prefix}_dl_manga_page",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"読み込みエラー: {e}")

    return True


def render_gallery_tab():
    """生成済み画像のプレビュー・ダウンロードタブ"""
    st.subheader("生成済み画像")
    st.caption("output/ フォルダ内の画像をプレビューし、保存（ダウンロード）できます。")
    render_gallery_section(key_prefix="tab_gallery")


def render_character_tab():
    """キャラクター設定タブ"""
    chars_data = load_characters_full()
    characters = chars_data.get("characters", [])
    template = load_character_template()
    fields = template.get("fields", [])
    desc_tpl = template.get("description_template", "")

    st.subheader("登録キャラクター一覧")
    if not characters:
        st.info("まだキャラクターがありません。下のテンプレートから新規作成してください。")
    else:
        for i, c in enumerate(characters):
            with st.expander(f"**{c.get('name', c['id'])}** ({c['id']})", expanded=False):
                st.text(f"英語名: {c.get('name_en', '-')}")
                st.text(f"口調: {c.get('voice_style', '-')}")
                if st.button(f"🗑 削除", key=f"del_char_{i}"):
                    characters.pop(i)
                    chars_data["characters"] = characters
                    save_characters(chars_data)
                    st.rerun()

    st.divider()
    st.subheader("テンプレートから新規作成")
    st.caption("項目を埋めるだけでキャラクターが作成できます。必須項目以外は省略可。")

    with st.form("new_character_form"):
        values = {}
        col_a, col_b = st.columns(2)

        with col_a:
            for f in fields[:9]:
                fid = f["id"]
                default = f.get("default", "")
                if "options" in f:
                    opts = f["options"]
                    labels = f.get("labels", opts)
                    idx = opts.index(default) if default in opts else 0
                    values[fid] = st.selectbox(f["label"], opts, index=idx, format_func=lambda x, ls=labels, os=opts: ls[os.index(x)] if x in os else x, key=f"new_{fid}")
                else:
                    values[fid] = st.text_input(f["label"], value=default, placeholder=f.get("placeholder", ""), key=f"new_{fid}")

        with col_b:
            for f in fields[9:]:
                fid = f["id"]
                default = f.get("default", "")
                if "options" in f:
                    opts = f["options"]
                    labels = f.get("labels", opts)
                    idx = opts.index(default) if default in opts else 0
                    values[fid] = st.selectbox(f["label"], opts, index=idx, format_func=lambda x, ls=labels, os=opts: ls[os.index(x)] if x in os else x, key=f"new_{fid}")
                else:
                    values[fid] = st.text_input(f["label"], value=default, placeholder=f.get("placeholder", ""), key=f"new_{fid}")

        submitted = st.form_submit_button("キャラクターを追加")
        if submitted:
            id_val = (values.get("id") or "").strip().lower().replace(" ", "_")
            name_val = (values.get("name") or "").strip()
            name_en_val = (values.get("name_en") or "").strip()
            if not id_val or not name_val or not name_en_val:
                st.error("ID・名前（日本語）・名前（英語）は必須です")
            elif any(c["id"] == id_val for c in characters):
                st.error(f"ID「{id_val}」は既に使われています")
            elif len(characters) >= 5:
                st.error("キャラクターは最大5人までです（Nano Banana 2 の仕様）")
            else:
                hair_acc = values.get("hair_accessory", "")
                if hair_acc and not hair_acc.startswith(",") and not hair_acc.startswith(" "):
                    hair_acc = ", " + hair_acc
                values["hair_accessory"] = hair_acc

                description = build_description_from_template(desc_tpl, values)
                new_char = {
                    "id": id_val,
                    "name": name_val,
                    "name_en": name_en_val,
                    "description": description,
                    "personality_hints": values.get("personality_hints", ""),
                    "voice_style": values.get("voice_style", ""),
                }
                characters.append(new_char)
                chars_data["characters"] = characters
                save_characters(chars_data)
                st.success(f"「{name_val}」を追加しました！")
                st.rerun()


def main():
    options = load_options()
    project_data = load_project()
    characters = load_characters()

    st.title("📖 Gemini 漫画生成")
    st.caption("Nano Banana 2 (Gemini 3.1 Flash Image) で一貫性のある漫画を生成")

    tab_manga, tab_chars, tab_gallery = st.tabs([
        "📄 漫画生成",
        "👤 キャラクター設定",
        "🖼 生成済み画像",
    ])

    with tab_manga:
        render_manga_tab(options, characters, project_data)

    with tab_chars:
        render_character_tab()

    with tab_gallery:
        render_gallery_tab()


def render_manga_tab(options, characters, project_data):
    """漫画生成タブ"""
    # --- Step 1: 作りたい画像の設定 ---
    st.header("1. 作りたい画像の設定")

    col1, col2, col3, col4 = st.columns(4)

    usage_opts = options.get("usage", [["standard", "標準漫画"]])
    usage_key_idx = {opts[0]: i for i, opts in enumerate(usage_opts)}
    proj = project_data.get("project", {})
    with col1:
        usage_labels = [opts[1] for opts in usage_opts]
        usage_sel = st.selectbox(
            "用途",
            range(len(usage_labels)),
            format_func=lambda i: usage_labels[i],
            index=usage_key_idx.get(proj.get("usage", "standard_manga"), 0),
        )
        usage_key = usage_opts[usage_sel][0]

    canvas_opts = options.get("canvas_ratio", [["3:4", "3:4 (縦長)"]])
    canvas_key_idx = {opts[0]: i for i, opts in enumerate(canvas_opts)}
    with col2:
        canvas_labels = [opts[1] for opts in canvas_opts]
        canvas_sel = st.selectbox(
            "キャンバス比率",
            range(len(canvas_labels)),
            format_func=lambda i: canvas_labels[i],
            index=canvas_key_idx.get(proj.get("canvas_ratio", "3:4") or proj.get("aspect_ratio", "3:4"), 1),
        )
        canvas_key = canvas_opts[canvas_sel][0]
        canvas_label = canvas_opts[canvas_sel][1]

    with col3:
        total_panels = st.number_input("出力枚数", min_value=1, max_value=20, value=proj.get("total_panels", 5))

    genre_opts = options.get("genre", [["none", "指定なし (標準)"]])
    genre_key_idx = {opts[0]: i for i, opts in enumerate(genre_opts)}
    with col4:
        genre_labels = [opts[1] for opts in genre_opts]
        genre_sel = st.selectbox(
            "ターゲットジャンル・世界観",
            range(len(genre_labels)),
            format_func=lambda i: genre_labels[i],
            index=min(genre_key_idx.get(proj.get("genre", "none"), 0), len(genre_labels) - 1),
        )
        genre_key = genre_opts[genre_sel][0]
        genre_label = genre_opts[genre_sel][1]

    st.divider()

    # --- Step 2: 伝える内容と被写体（コマ割り・セリフ） ---
    st.header("2. 伝える内容と被写体（コマ割り）")
    st.caption("各コマにセリフを複数行で入力できます。1枚目、2枚目…の順でコマ割りされます。")

    panels_data = project_data.get("panels", [])
    char_choices = ["入れない(背景・世界観のみ)"] + [f"{c.get('name', c['id'])} ({c['id']})" for c in characters]

    panels = []
    for i in range(total_panels):
        with st.expander(f"■ {i + 1}枚目", expanded=(i == 0)):
            existing = next((p for p in panels_data if p.get("number") == i + 1), {})
            existing_dialogue = existing.get("dialogue") or []

            title = st.text_input(
                f"{i + 1}枚目のタイトル・見出し",
                value=existing.get("title", ""),
                key=f"title_{i}",
            )

            # メインの被写体（このコマに登場するキャラの代表）
            main_char_index = 0
            if existing.get("characters"):
                cid = existing["characters"][0]
                for j, c in enumerate(characters):
                    if c["id"] == cid:
                        main_char_index = j + 1
                        break
            main_char_raw = st.selectbox(
                "メインの被写体 (キャラクター)",
                char_choices,
                index=main_char_index,
                key=f"main_char_{i}",
            )
            main_chars = []
            if main_char_raw and main_char_raw != "入れない(背景・世界観のみ)":
                char_id = main_char_raw.split("(")[-1].rstrip(")")
                main_chars = [char_id]

            st.markdown("**セリフ（複数可）**")
            dialogue_rows = []
            # session_state で「追加」した行数を持ち越す。保存後は existing から再初期化
            base_count = max(len(existing_dialogue), 1)
            num_dialogue = st.session_state.get(f"dialogue_count_{i}", base_count)
            for d_idx in range(num_dialogue):
                ex = existing_dialogue[d_idx] if d_idx < len(existing_dialogue) else {}
                ex_char = ex.get("character", "")
                ex_text = ex.get("text", "")
                d_char_idx = 0
                if ex_char:
                    for j, c in enumerate(characters):
                        if c["id"] == ex_char:
                            d_char_idx = j + 1
                            break
                col_c, col_t = st.columns([1, 3])
                with col_c:
                    d_char = st.selectbox(
                        f"セリフ{d_idx + 1} キャラ",
                        char_choices,
                        index=d_char_idx,
                        key=f"d_char_{i}_{d_idx}",
                    )
                with col_t:
                    d_text = st.text_input(
                        f"セリフ{d_idx + 1} 内容",
                        value=ex_text,
                        placeholder="例: おはよう！今日も頑張ろうね",
                        key=f"d_text_{i}_{d_idx}",
                    )
                dialogue_rows.append({"char_sel": d_char, "text": d_text})

            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button(f"➕ セリフを追加", key=f"add_dialogue_{i}"):
                    st.session_state[f"dialogue_count_{i}"] = num_dialogue + 1
                    st.rerun()
            with btn_col2:
                if num_dialogue > 1 and st.button(f"➖ 最後のセリフを削除", key=f"rem_dialogue_{i}"):
                    st.session_state[f"dialogue_count_{i}"] = num_dialogue - 1
                    st.rerun()

            # セリフから登場キャラを収集
            char_ids_in_dialogue = set()
            dialogue_list = []
            for dr in dialogue_rows:
                if dr["char_sel"] and dr["char_sel"] != "入れない(背景・世界観のみ)":
                    cid = dr["char_sel"].split("(")[-1].rstrip(")")
                    char_ids_in_dialogue.add(cid)
                if dr["text"]:
                    cid = dr["char_sel"].split("(")[-1].rstrip(")") if dr["char_sel"] != "入れない(背景・世界観のみ)" else None
                    if cid:
                        dialogue_list.append({"character": cid, "text": dr["text"]})
            if not main_chars and char_ids_in_dialogue:
                main_chars = list(char_ids_in_dialogue)
            elif main_chars and char_ids_in_dialogue:
                main_chars = list(set(main_chars) | char_ids_in_dialogue)
            if not dialogue_list and main_chars and dialogue_rows and dialogue_rows[0]["text"]:
                cid = dialogue_rows[0]["char_sel"].split("(")[-1].rstrip(")") if dialogue_rows[0]["char_sel"] != "入れない(背景・世界観のみ)" else main_chars[0]
                dialogue_list = [{"character": cid, "text": dialogue_rows[0]["text"]}]

            # コマ（一コマ目・二コマ目…）の入れ子構造
            existing_koma = existing.get("koma") or []
            if not existing_koma and (existing.get("scene") or existing.get("shot") or existing.get("action")):
                existing_koma = [{"scene": existing.get("scene", ""), "shot": existing.get("shot", ""), "action": existing.get("action", "")}]
            if not existing_koma:
                existing_koma = [{"scene": "", "shot": "", "action": ""}]

            num_koma = st.session_state.get(f"koma_count_{i}", len(existing_koma))
            koma_list = []
            for k in range(num_koma):
                ex_k = existing_koma[k] if k < len(existing_koma) else {"scene": "", "shot": "", "action": ""}
                with st.expander(f"□ {k + 1}コマ目", expanded=(num_koma <= 2)):
                    scene_k = st.text_input(
                        f"{k + 1}コマ目 場面・背景",
                        value=ex_k.get("scene", ""),
                        placeholder="例: 教室の窓際。朝の光が差し込む。",
                        key=f"scene_{i}_{k}",
                    )
                    shot_k = st.text_input(
                        f"{k + 1}コマ目 構図・カメラアングル",
                        value=ex_k.get("shot", ""),
                        placeholder="例: 全身が入る、上半身、手元クローズアップ",
                        key=f"shot_{i}_{k}",
                    )
                    action_k = st.text_input(
                        f"{k + 1}コマ目 構図・アクション",
                        value=ex_k.get("action", ""),
                        placeholder="例: 手を挙げて笑顔で挨拶。",
                        key=f"action_{i}_{k}",
                    )
                    koma_list.append({
                        "scene": scene_k or "（未設定）",
                        "shot": shot_k or "（適切な構図）",
                        "action": action_k or (dialogue_list[k]["text"] if k < len(dialogue_list) else "（未設定）"),
                    })

            btn_k1, btn_k2 = st.columns(2)
            with btn_k1:
                if st.button(f"➕ コマを追加", key=f"add_koma_{i}"):
                    st.session_state[f"koma_count_{i}"] = num_koma + 1
                    st.rerun()
            with btn_k2:
                if num_koma > 1 and st.button(f"➖ コマを削除", key=f"rem_koma_{i}"):
                    st.session_state[f"koma_count_{i}"] = num_koma - 1
                    st.rerun()

            first_text = dialogue_list[0]["text"] if dialogue_list else ""
            panels.append({
                "number": i + 1,
                "title": title,
                "text": first_text,
                "characters": main_chars,
                "koma": koma_list,
                "dialogue": dialogue_list,
            })

    st.divider()

    # --- Step 3: デザインの方向性 ---
    st.header("3. デザインの方向性")

    design_col, taste_col = st.columns(2)

    design_opts = options.get("design_structure", [["standard", "スタンダードなコマ割り漫画"]])
    design_key_idx = {opts[0]: i for i, opts in enumerate(design_opts)}
    with design_col:
        design_labels = [opts[1] for opts in design_opts]
        design_sel = st.selectbox(
            "図解・構図の構造",
            range(len(design_labels)),
            format_func=lambda i: design_labels[i],
            index=min(design_key_idx.get(proj.get("design_structure", "standard"), 0), len(design_labels) - 1),
        )
        design_key = design_opts[design_sel][0]
        design_label = design_opts[design_sel][1]

    taste_opts = options.get("art_taste", [["standard", "スタンダード (少年漫画)"]])
    taste_key_idx = {opts[0]: i for i, opts in enumerate(taste_opts)}
    with taste_col:
        taste_labels = [opts[1] for opts in taste_opts]
        taste_sel = st.selectbox(
            "メインテイスト (画風)",
            range(len(taste_labels)),
            format_func=lambda i: taste_labels[i],
            index=min(taste_key_idx.get(proj.get("art_taste", "standard"), 0), len(taste_labels) - 1),
        )
        taste_key = taste_opts[taste_sel][0]
        taste_label = taste_opts[taste_sel][1]

    st.divider()

    # --- 保存 & 生成 ---
    st.subheader("操作を選んでください")
    # API不要（おすすめ）を先に大きく表示
    col_prompt_lead, _ = st.columns([1, 2])
    with col_prompt_lead:
        if st.button("📋 プロンプトをコピー（API不要）", type="primary", use_container_width=True, key="prompt_btn"):
            project = project_data.get("project", {})
            project["usage"] = usage_key
            project["canvas_ratio"] = canvas_key
            project["aspect_ratio"] = canvas_key
            project["canvas_ratio_label"] = canvas_label
            project["total_panels"] = total_panels
            project["genre"] = genre_key
            project["genre_label"] = genre_label
            project["design_structure"] = design_key
            project["design_structure_label"] = design_label
            project["art_taste"] = taste_key
            project["art_taste_label"] = taste_label
            new_panels = []
            for p in panels:
                d = {"number": p["number"], "characters": p["characters"], "dialogue": p.get("dialogue", [])}
                if p["title"]:
                    d["title"] = p["title"]
                if p["text"]:
                    d["text"] = p["text"]
                koma_list = p.get("koma") or []
                if not koma_list and (p.get("scene") or p.get("shot") or p.get("action")):
                    koma_list = [{"scene": p.get("scene",""), "shot": p.get("shot",""), "action": p.get("action","")}]
                if not koma_list:
                    koma_list = [{"scene": "（未設定）", "shot": "（適切な構図）", "action": "（未設定）"}]
                d["koma"] = koma_list
                new_panels.append(d)
            save_project({"project": project, "panels": new_panels})
            try:
                from src.manga_generator import get_all_prompts_flat
            except ImportError:
                from manga_generator import get_all_prompts_flat
            prompts = get_all_prompts_flat(CONFIG_DIR)
            st.session_state["panel_prompts"] = [(label, txt) for label, txt in prompts]
            st.rerun()
    st.caption("↑ おすすめ：Geminiに貼り付けて手動で画像生成（API費用なし）")

    col_save, col_gen = st.columns(2)

    with col_save:
        if st.button("💾 設定を保存", use_container_width=True):
            project = project_data.get("project", {})
            project["usage"] = usage_key
            project["canvas_ratio"] = canvas_key
            project["aspect_ratio"] = canvas_key
            project["canvas_ratio_label"] = canvas_label
            project["total_panels"] = total_panels
            project["genre"] = genre_key
            project["genre_label"] = genre_label
            project["design_structure"] = design_key
            project["design_structure_label"] = design_label
            project["art_taste"] = taste_key
            project["art_taste_label"] = taste_label

            new_panels = []
            for p in panels:
                d = {"number": p["number"], "characters": p["characters"], "dialogue": p.get("dialogue", [])}
                if p["title"]:
                    d["title"] = p["title"]
                if p["text"]:
                    d["text"] = p["text"]
                koma_list = p.get("koma") or []
                if not koma_list:
                    koma_list = [{"scene": "（未設定）", "shot": "（適切な構図）", "action": "（未設定）"}]
                d["koma"] = koma_list
                new_panels.append(d)

            save_project({"project": project, "panels": new_panels})
            st.success("project.yaml に保存しました")

    with col_gen:
        if st.button("🎨 画像を生成（API使用・有料）", use_container_width=True):
            # 保存してから生成（UI の全設定を project に反映）
            project = project_data.get("project", {})
            project["usage"] = usage_key
            project["canvas_ratio"] = canvas_key
            project["aspect_ratio"] = canvas_key
            project["total_panels"] = total_panels
            project["genre"] = genre_key
            project["genre_label"] = genre_label
            project["design_structure"] = design_key
            project["design_structure_label"] = design_label
            project["art_taste"] = taste_key
            project["art_taste_label"] = taste_label

            new_panels = []
            for p in panels:
                d = {"number": p["number"], "characters": p["characters"], "dialogue": p.get("dialogue", [])}
                if p["title"]:
                    d["title"] = p["title"]
                if p["text"]:
                    d["text"] = p["text"]
                koma_list = p.get("koma") or []
                if not koma_list:
                    koma_list = [{"scene": "（未設定）", "shot": "（適切な構図）", "action": "（未設定）"}]
                d["koma"] = koma_list
                new_panels.append(d)

            save_project({"project": project, "panels": new_panels})

            progress = st.progress(0)
            status = st.empty()

            try:
                from src.manga_generator import run_all_flat
            except ImportError:
                from manga_generator import run_all_flat

            config_dir = CONFIG_DIR
            output_dir = OUTPUT_DIR

            results = run_all_flat(config_dir, output_dir)
            total = len(results)
            for idx, ok in enumerate(results):
                progress.progress((idx + 1) / total)
                status.text(f"生成中: {idx + 1}/{total}コマ目...")
                if ok:
                    st.success(f"panel_{idx + 1:03d}.png 保存完了")
                else:
                    st.error(f"panel_{idx + 1:03d} エラー")

            progress.progress(1.0)
            status.text("完了")
            st.balloons()

    # プロンプト表示エリア（コピー用）
    if st.session_state.get("panel_prompts"):
        st.divider()
        st.subheader("📋 プロンプト（Geminiに貼り付けてください）")
        st.caption("各コマのプロンプトをコピーして、Gemini（Web/アプリ）に貼り付け、画像を生成してください。API費用はかかりません。")
        for idx, (label, prompt_text) in enumerate(st.session_state["panel_prompts"]):
            safe_name = label.replace("・", "_").replace("枚", "").replace("コマ", "k")
            with st.expander(f"■ {label} のプロンプト", expanded=True):
                st.caption("下の枠内を選択してコピー (Cmd+C / Ctrl+C)、またはダウンロードしてください")
                st.code(prompt_text, language=None, line_numbers=False)
                st.download_button(
                    f"{label}_prompt.txt をダウンロード",
                    data=prompt_text,
                    file_name=f"{safe_name}_prompt.txt",
                    mime="text/plain",
                    key=f"prompt_dl_{idx}",
                )

    # --- 生成済み画像のプレビュー & 保存（同じ画面で表示） ---
    st.divider()
    st.subheader("🖼 生成済み画像（プレビュー & 保存）")
    st.caption("output/ フォルダ内の画像をプレビューし、ダウンロードボタンでPCに保存できます。")
    render_gallery_section(key_prefix="manga_tab")


if __name__ == "__main__":
    main()
