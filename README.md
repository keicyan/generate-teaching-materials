# generate-teaching-materials

Claude API を使って eラーニング教材（Markdown）を自動生成するツール。

コース設定をウィザード形式でヒアリングし、章・レッスン構成に基づいて教材を一括生成します。

## 必要環境

- Python 3.9+
- Anthropic API キー

## セットアップ

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# セットアップウィザードの実行（初回のみ）
python3 init.py
```

ウィザードでは以下を設定します：

- `ANTHROPIC_API_KEY` の確認・保存
- コーストピック、対象読者、学習目標、教え方スタイル
- 使用モデルと予算上限
- `config.json` と `generate.py` の自動生成

## 使い方

### 1. カリキュラムの定義

`curriculum/chapters.csv` と `curriculum/lessons.csv` を作成します。

### 2. 教材の生成

```bash
python3 generate.py
```

内部で以下を順に実行します：

1. `scripts/build_master_csv.py` — chapters.csv + lessons.csv → curriculum_master.csv
2. `scripts/generate_md.py` — Claude API で各レッスンの Markdown を生成
3. `scripts/build_index.py` — README.md と _index.json を生成

生成された教材は `curriculum/<コース名>/` に出力されます。

### 3. 品質検証

```bash
python3 scripts/validate_content.py
```

Frontmatter の完全性、必須セクションの存在、文字数などをチェックします。

### 4. コスト確認

```bash
python3 scripts/summarize_cost.py output/_runs/<run_id>/cost.csv
```

## ディレクトリ構成

```
.
├── init.py                    # セットアップウィザード
├── requirements.txt
├── curriculum/                # 教材出力先（.gitignore 対象）
│   ├── chapters.csv           # 章定義
│   └── lessons.csv            # レッスン定義
├── scripts/
│   ├── generate_md.py         # 教材生成（Claude API）
│   ├── build_master_csv.py    # マスタ CSV 生成
│   ├── build_index.py         # インデックス生成
│   ├── validate_content.py    # 品質検証
│   └── summarize_cost.py      # コスト集計
├── docs/
│   └── chapters/              # 章概要・文字起こし置き場
└── output/
    └── _runs/                 # 実行ログ（.gitignore 対象）
```

## 注意事項

- `config.json` と `generate.py` は `init.py` が自動生成します（.gitignore 対象）
- `curriculum/` と `output/` 配下は .gitignore 対象です
