# CLAUDE.md

このファイルは Claude Code がこのプロジェクトで作業する際のガイドラインです。

## プロジェクト概要

Claude API を使って eラーニング教材（Markdown）を自動生成するツール。
`init.py` でコース設定をヒアリングし、`generate.py` で教材を一括生成する。

## 主要コマンド

```bash
python3 init.py                                    # セットアップウィザード（初回のみ）
python3 generate.py                                # 教材生成パイプライン実行
python3 scripts/validate_content.py               # 品質検証
python3 scripts/summarize_cost.py [cost.csv]      # コスト集計
```

## ディレクトリ構成

```
init.py                    # セットアップウィザード
scripts/
  generate_md.py           # メイン生成スクリプト（Claude API 呼び出し）
  build_master_csv.py      # chapters.csv + lessons.csv → curriculum_master.csv
  build_index.py           # README.md と _index.json 生成
  validate_content.py      # 生成済み教材の品質検証
  summarize_cost.py        # API コスト集計
curriculum/                # 教材出力先（.gitignore 対象）
output/                    # 実行ログ（.gitignore 対象）
```

## コミットルール

- **機能単位でコミットを作る（1機能 = 1コミット）**
- コミットメッセージは `<type>: <内容>` 形式（日本語可）

| type | 用途 |
|------|------|
| `feat:` | 新機能 |
| `fix:` | バグ修正 |
| `refactor:` | リファクタリング |
| `docs:` | ドキュメント |
| `chore:` | その他 |

## コーディング規約

- インデント: スペース4つ（Python標準）
- 命名規則: 関数・変数は `snake_case`、定数は `UPPER_SNAKE_CASE`
- 型ヒント: 新規関数には付ける
- 1ファイル1責務（既存の構成を維持）
- マジックナンバーは定数化する

## 注意事項

- `config.json`, `generate.py`, `curriculum/`, `output/` は `.gitignore` 対象のため commit しない
- 依存パッケージ: `anthropic>=0.39.0`（`requirements.txt` 参照）
