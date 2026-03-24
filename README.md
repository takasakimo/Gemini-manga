# Gemini 3.1 漫画作成

Gemini 3.1 Flash Image（Nano Banana 2）で、**登場人物の一貫性**と**タッチ・色調の統一**を保った漫画を生成します。

## 機能

- **🤖 フルオート生成**: テーマからプロンプトを表示 → Gemini に貼り付け → 返答 JSON をアプリに貼り付けて反映（**API キー不要**・Cloud 対応）
- **作成枚数の指定**: `project.yaml` の `total_panels` で枚数を設定
- **各コマごとのセリフ・構図**: 1コマずつ場面・アクション・セリフを入力
- **キャラクター固定**: `characters.yaml` で外見を固定し、一貫性を維持

## セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env   # GEMINI_API_KEY を設定
```

## 設定ファイル

### `config/characters.yaml`
キャラクターの外見（髪・目・服装・区別できる特徴）を定義。最大5人推奨。

### `config/character_template.yaml`
キャラクター作成用テンプレート。項目（髪・目・体型・服装など）を埋めるだけで `description` が自動生成されます。UI の「キャラクター設定」タブからテンプレートを使って追加可能。

### `config/project.yaml`
- **project.total_panels**: 作成するコマ枚数
- **panels**: 各コマの定義
  - `number`: コマ番号
  - `characters`: 登場キャラIDのリスト
  - `scene`: 場面・背景
  - `shot`: 構図・カメラアングル
  - `action`: アクション・表情
  - `dialogue`: セリフ（character + text）

## 使い方

### 方法1: Web UI（推奨）

スクリーンショット参考アプリ風の3ステップ項目選択UIを起動：

```bash
streamlit run src/app.py
```

- **🤖 フルオート**: テーマを入力 → 「フルオート用プロンプトを表示」でコピー → Gemini に貼り付け → 返答 JSON を「設定に反映」→ 「漫画生成」タブで画像用プロンプトをコピー
- **📄 漫画生成（手動）**:
  1. 作りたい画像の設定: 用途・キャンバス比率・出力枚数・ターゲットジャンル
  2. 伝える内容と被写体: 各コマのタイトル・テキスト・メインの被写体・場面・アクション
  3. デザインの方向性: 図解・構図の構造、メインテイスト（画風）

「設定を保存」で project.yaml に反映、「プロンプトをコピー」で Gemini に貼り付けて画像生成します。

### 方法2: コマンドライン

```bash
# 全コマを生成
python -m src.manga_generator

# 特定コマのみ（例: 3コマ目）
python -m src.manga_generator 3
```

生成画像は `output/` に `panel_001.png` のように保存されます。

## デプロイ（Streamlit Community Cloud）

GitHub 連携でブラウザからアクセス可能な URL を発行できます。

### 1. GitHub にリポジトリを作成

1. [GitHub](https://github.com/new) で新規リポジトリ作成
2. リポジトリ名（例: `gemini-manga`）

### 2. コードをプッシュ

```bash
cd "Gemini漫画作成"
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 3. Streamlit Community Cloud でデプロイ

1. [share.streamlit.io](https://share.streamlit.io) にアクセス
2. GitHub でログイン
3. **Deploy an app** → リポジトリを選択
4. **Main file path**: `app.py`
5. **Advanced settings** → **Secrets** に以下を追加：

```
GEMINI_API_KEY = "あなたのAPIキー"
```

6. **Deploy** をクリック

数分後に公開URLが発行されます。プッシュするたびに自動デプロイされます。
