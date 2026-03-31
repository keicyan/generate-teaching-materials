"""
generate-teaching-materials — セットアップウィザード

使い方:
  python3 init.py

実行すると:
  1. ANTHROPIC_API_KEY の確認・設定
  2. curriculum/ の CSV ファイル確認
  3. Claude との対話でコース設定をヒアリング
  4. config.json と generate.py を生成
"""

import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ────────────────────────────────────────────────
# ウィザード用システムプロンプト（Haiku で実行）
# ────────────────────────────────────────────────
WIZARD_SYSTEM_PROMPT = """あなたは教材自動生成ツールのセットアップアシスタントです。
ユーザーから以下の情報を**自然な会話形式**で聞き出してください。
一度に全部聞かず、1〜2項目ずつ進めてください。

必要な情報:
1. コーストピック（例: Premiere Pro動画編集、Python入門、Webデザイン基礎 など）
2. 対象読者（年齢層・経験レベル・学習目的）
3. 学習目標・到達ゴール（このコースを終えたら何ができるか）
4. 教え方のスタイル（口調・難易度・具体例の多さ・重視したいこと）
5. 出力言語（デフォルト: 日本語。英語など他言語も可）
6. 使用する AI モデル（以下から選択）:
   - claude-sonnet-4-6（推奨: バランスが良い）
   - claude-haiku-4-5（高速・低コスト）
   - claude-opus-4-6（最高品質・高コスト）
7. 予算上限（USD。例: 10。0 で無制限）

すべての情報が集まったら、以下のフォーマットで JSON を出力して終了してください:

<CONFIG_JSON>
{
  "topic": "コーストピック",
  "language": "ja",
  "category_key": "カテゴリの英略称（例: Pr, Py, Wd など）",
  "audience_description": "対象読者の説明",
  "learning_goal": "学習目標",
  "teaching_style": "教え方の方針",
  "model_id": "claude-sonnet-4-6",
  "budget_usd": 10.0
}
</CONFIG_JSON>"""

# ────────────────────────────────────────────────
# プロンプト生成用（Sonnet で実行）
# ────────────────────────────────────────────────
PROMPT_GEN_TEMPLATE = """以下のコース設定をもとに、教材生成AIへの指示文を日本語で作成してください。

設定:
{config_json}

以下の3つをそれぞれタグで囲んで出力してください:

<SYSTEM_PROMPT>
AIが教材編集者として振る舞うためのシステムプロンプト（2〜3文）。
コーストピックと学習目標を踏まえること。
</SYSTEM_PROMPT>

<AUDIENCE_BLOCK>
対象読者のリスト（箇条書き3〜4項目）。
フォーマット:
対象読者：
・（年齢層・属性）
・（経験レベル）
・（学習目的・ゴール）
</AUDIENCE_BLOCK>

<POLICY_BLOCK>
教材方針のリスト（箇条書き7〜9項目）。
フォーマット:
教材方針：
・（方針1）
・（方針2）
...
</POLICY_BLOCK>"""

# ────────────────────────────────────────────────
# generate.py のテンプレート（init.py が書き出す）
# ────────────────────────────────────────────────
GENERATE_PY_TEMPLATE = '''"""
{topic} 教材生成スクリプト
生成日時: {created_at}

使い方:
  python3 generate.py                        # 引数なし → 対話式で範囲選択
  python3 generate.py --only-chapter setup   # 特定章のみ
  python3 generate.py --limit 3             # 先頭3件（テスト用）
  python3 generate.py --overwrite           # 既存ファイルを上書き
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path

# このファイルは init.py によって自動生成されました
# 設定を変更したい場合は config.json を編集してから、
# python3 init.py を再実行してください

CONFIG_PATH = "config.json"
LESSONS_CSV = "curriculum/lessons.csv"
CATEGORY_KEY = {category_key!r}

PRICING = {{
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5":  (1.0,  5.0),
    "claude-opus-4-6":   (5.0, 25.0),
}}
# トークン数の概算（実際のコストは多少前後します）
AVG_INPUT_TOKENS  = 1200
AVG_OUTPUT_TOKENS = 3500


def load_config():
    import json
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def count_lessons(only_chapter=None, limit=None):
    """lessons.csv から対象レッスン数をカウントする（API 呼び出しなし）"""
    if not Path(LESSONS_CSV).exists():
        print(f"エラー: {{LESSONS_CSV}} が見つかりません。")
        print("curriculum/ フォルダに chapters.csv と lessons.csv を配置してください。")
        sys.exit(1)

    with open(LESSONS_CSV, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("category") == CATEGORY_KEY]

    if only_chapter:
        rows = [r for r in rows if r.get("chapter_key") == only_chapter]
    if limit:
        rows = rows[:limit]
    return len(rows)


def estimate_cost(lesson_count, model_id):
    price_in, price_out = PRICING.get(model_id, (3.0, 15.0))
    return lesson_count * (
        (AVG_INPUT_TOKENS  / 1_000_000) * price_in +
        (AVG_OUTPUT_TOKENS / 1_000_000) * price_out
    )


def ask_scope(args):
    """CLI 引数がない場合、対話形式で実行範囲を選択する"""
    if args.only_chapter or args.limit:
        return args

    print()
    print("実行範囲を選んでください:")
    print("  [1] 全章生成")
    print("  [2] 特定の章のみ（章キーを入力）")
    print("  [3] 先頭N件だけ（テスト用）")
    choice = input("選択 [1]: ").strip() or "1"

    if choice == "2":
        args.only_chapter = input("章キーを入力（例: setup, chapter1 など）: ").strip()
    elif choice == "3":
        try:
            args.limit = int(input("件数を入力（例: 3）: ").strip())
        except ValueError:
            print("無効な値です。全件生成に切り替えます。")

    return args


def run_pipeline(args, config):
    """3ステップのパイプラインを順番に実行する"""
    model_id = config["model"]["model_id"]
    budget_usd = config["model"]["budget_usd"]
    max_tokens = config["model"]["max_tokens"]

    # ステップ1: マスタ CSV 再生成
    print()
    print("▶ ステップ 1/3: curriculum_master.csv を再生成中...")
    result = subprocess.run(
        [sys.executable, "scripts/build_master_csv.py"],
        check=False
    )
    if result.returncode != 0:
        print("エラー: build_master_csv.py が失敗しました。")
        sys.exit(1)

    # ステップ2: Markdown 生成
    print()
    print("▶ ステップ 2/3: 教材 Markdown を生成中...")
    cmd = [
        sys.executable, "scripts/generate_md.py",
        "--config", CONFIG_PATH,
        "--model", model_id,
        "--budget-usd", str(budget_usd),
        "--max-tokens", str(max_tokens),
    ]
    if args.only_chapter:
        cmd += ["--only-chapter", args.only_chapter]
    if args.limit:
        cmd += ["--limit", str(args.limit)]
    if args.overwrite:
        cmd += ["--overwrite"]

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print("エラー: generate_md.py が失敗しました。")
        sys.exit(1)

    # ステップ3: インデックス生成
    print()
    print("▶ ステップ 3/3: _index.json と README を生成中...")
    result = subprocess.run(
        [sys.executable, "scripts/build_index.py"],
        check=False
    )
    if result.returncode != 0:
        print("エラー: build_index.py が失敗しました。")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="{topic} 教材生成スクリプト")
    parser.add_argument("--only-chapter", default="", help="特定の章キーのみ生成（例: setup）")
    parser.add_argument("--limit", type=int, default=0, help="生成する最大レッスン数（0=全件）")
    parser.add_argument("--overwrite", action="store_true", help="既存ファイルを上書き")
    args = parser.parse_args()

    # None/0 を falsy に統一
    args.only_chapter = args.only_chapter.strip() or ""
    args.limit = args.limit or 0

    config = load_config()
    model_id = config["model"]["model_id"]
    budget_usd = config["model"]["budget_usd"]

    # 引数なしの場合は対話式で範囲を選択
    args = ask_scope(args)

    # レッスン数とコストを見積もり
    lesson_count = count_lessons(
        only_chapter=args.only_chapter or None,
        limit=args.limit or None,
    )
    cost = estimate_cost(lesson_count, model_id)

    # 実行確認メッセージ
    scope_label = ""
    if args.only_chapter:
        scope_label = f"（章: {{args.only_chapter}}）"
    elif args.limit:
        scope_label = f"（先頭{{args.limit}}件）"

    print()
    print("================================")
    print("  教材生成")
    print("================================")
    print(f"  コース     : {topic}")
    print(f"  モデル     : {{model_id}}")
    print(f"  予算上限   : ${{budget_usd:.2f}}")
    print(f"  対象レッスン: {{lesson_count}} 件{{scope_label}}")
    print(f"  推定コスト  : ${{cost:.2f}}（概算）")
    print("================================")

    answer = input("実行しますか？ [Y/n]: ").strip().lower()
    if answer not in ("", "y", "yes"):
        print("キャンセルしました。")
        sys.exit(0)

    run_pipeline(args, config)

    print()
    print("✅ 完了しました！")
    print("生成されたファイルは curriculum/ フォルダをご確認ください。")


if __name__ == "__main__":
    main()
'''


# ────────────────────────────────────────────────
# ユーティリティ関数
# ────────────────────────────────────────────────

def extract_tag(text: str, tag: str) -> str:
    """<TAG>...</TAG> の内容を抽出する"""
    pattern = rf"<{tag}>(.*?)</{tag}>"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def setup_api_key() -> str:
    """ANTHROPIC_API_KEY を確認し、なければ入力を求める"""
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if key:
        print(f"✅ ANTHROPIC_API_KEY が設定されています。")
        return key

    print()
    print("ANTHROPIC_API_KEY が環境変数に見つかりません。")
    print("Anthropic Console ( https://console.anthropic.com/ ) でAPIキーを取得してください。")
    print()
    key = input("APIキーを入力してください (sk-ant-...): ").strip()
    if not key:
        print("エラー: APIキーが入力されませんでした。")
        sys.exit(1)

    save = input(".env ファイルに保存しますか？ [Y/n]: ").strip().lower()
    if save in ("", "y", "yes"):
        env_path = Path(".env")
        with env_path.open("a", encoding="utf-8") as f:
            f.write(f"\nANTHROPIC_API_KEY={key}\n")
        print(f"✅ .env に保存しました。次回は自動で読み込まれます。")
        print("   （起動前に: export $(cat .env | xargs) を実行するか、python-dotenv を使用してください）")

    os.environ["ANTHROPIC_API_KEY"] = key
    return key


def check_csv_files():
    """必要な CSV ファイルの存在を確認する"""
    chapters_csv = Path("curriculum/chapters.csv")
    lessons_csv  = Path("curriculum/lessons.csv")

    missing = []
    if not chapters_csv.exists():
        missing.append("curriculum/chapters.csv")
    if not lessons_csv.exists():
        missing.append("curriculum/lessons.csv")

    if missing:
        print()
        print("⚠️  以下の CSV ファイルが見つかりません:")
        for f in missing:
            print(f"   - {f}")
        print()
        print("chapters.csv のカラム: category, chapter_key, chapter_folder, chapter_jp, order, chapter_video_url, is_published, description_short")
        print("lessons.csv のカラム:  category, chapter_key, order, topic, md_file")
        print()
        answer = input("CSV なしで続けますか？（後で配置することもできます） [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            print("CSV を配置してから再実行してください。")
            sys.exit(0)
    else:
        # CSV が存在する場合はカテゴリキーを確認
        with chapters_csv.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            categories = list({row.get("category", "").strip() for row in reader if row.get("category")})
        print(f"✅ CSV ファイルを検出しました。カテゴリ: {', '.join(sorted(categories))}")
        return categories

    return []


def run_conversation(client, detected_categories: list) -> dict:
    """Claude Haiku と多ターン会話を行い、設定 JSON を収集する"""
    from anthropic import Anthropic

    hint = ""
    if detected_categories:
        hint = f"\n（検出されたカテゴリキー: {', '.join(detected_categories)}）"

    messages = [
        {"role": "user", "content": f"よろしくお願いします。教材生成ツールのセットアップを始めてください。{hint}"}
    ]

    print()
    print("━" * 50)
    print("  セットアップウィザード")
    print("━" * 50)
    print("Claude があなたのコースについてヒアリングします。")
    print("（終了するには Ctrl+C）")
    print()

    while True:
        res = client.messages.create(
            model="claude-haiku-4-5",
            system=WIZARD_SYSTEM_PROMPT,
            messages=messages,
            max_tokens=800,
        )
        assistant_text = res.content[0].text
        messages.append({"role": "assistant", "content": assistant_text})

        # CONFIG_JSON タグが含まれていれば完了
        if "<CONFIG_JSON>" in assistant_text:
            print(assistant_text)
            raw_json = extract_tag(assistant_text, "CONFIG_JSON")
            try:
                return json.loads(raw_json)
            except json.JSONDecodeError as e:
                print(f"\n⚠️  JSON パースエラー: {e}")
                print("もう一度設定を確認します...")
                messages.append({"role": "user", "content": "JSON の形式が正しくないようです。修正して再出力してください。"})
                continue

        print(assistant_text)
        print()

        user_input = input("> ").strip()
        if not user_input:
            user_input = "続けてください。"
        messages.append({"role": "user", "content": user_input})


def generate_prompts(client, raw_config: dict) -> dict:
    """Sonnet を使って system_prompt / audience_block / policy_block を生成する"""
    print()
    print("⏳ カスタムプロンプトを生成中...")

    prompt = PROMPT_GEN_TEMPLATE.format(config_json=json.dumps(raw_config, ensure_ascii=False, indent=2))

    res = client.messages.create(
        model="claude-sonnet-4-6",
        system="あなたはeラーニング教材の専門家です。指示に従って正確にテキストを出力してください。",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
    )
    text = res.content[0].text

    system_prompt  = extract_tag(text, "SYSTEM_PROMPT")
    audience_block = extract_tag(text, "AUDIENCE_BLOCK")
    policy_block   = extract_tag(text, "POLICY_BLOCK")

    if not system_prompt:
        system_prompt = f"あなたは{raw_config.get('topic', 'このコース')}の教材編集者です。必ずLMS投入用のMarkdownで出力してください。コードブロックは必要なときだけ最小限にしてください。"
    if not audience_block:
        audience_block = f"対象読者：\n・{raw_config.get('audience_description', '学習者')}"
    if not policy_block:
        policy_block = f"教材方針：\n・わかりやすく丁寧に説明する\n・具体例を交えて解説する"

    return {
        "system_prompt": system_prompt,
        "audience_block": audience_block,
        "policy_block": policy_block,
    }


def write_config(raw_config: dict, prompts: dict) -> dict:
    """config.json を書き出す"""
    model_map = {
        "sonnet": "claude-sonnet-4-6",
        "haiku": "claude-haiku-4-5",
        "opus": "claude-opus-4-6",
    }
    model_id = raw_config.get("model_id", "claude-sonnet-4-6")
    # 短縮名（sonnet など）が入ってきた場合に正式名に変換
    model_id = model_map.get(model_id.lower(), model_id)

    config = {
        "course": {
            "topic": raw_config.get("topic", ""),
            "language": raw_config.get("language", "ja"),
            "category_key": raw_config.get("category_key", ""),
        },
        "audience": {
            "description": raw_config.get("audience_description", ""),
        },
        "model": {
            "model_id": model_id,
            "budget_usd": float(raw_config.get("budget_usd", 10.0)),
            "max_tokens": 4500,
        },
        "prompts": prompts,
        "_meta": {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "init_version": "1.0",
        },
    }

    config_path = Path("config.json")
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"✅ config.json を生成しました。")
    return config


def write_generate_py(config: dict):
    """generate.py を書き出す"""
    topic = config["course"]["topic"]
    category_key = config["course"]["category_key"]
    created_at = config["_meta"]["created_at"]

    content = GENERATE_PY_TEMPLATE.format(
        topic=topic,
        category_key=category_key,
        created_at=created_at,
    )

    generate_path = Path("generate.py")
    with generate_path.open("w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ generate.py を生成しました。")


# ────────────────────────────────────────────────
# メイン
# ────────────────────────────────────────────────

def main():
    print()
    print("=" * 50)
    print("  generate-teaching-materials")
    print("  セットアップウィザード")
    print("=" * 50)

    # Step 1: API キー確認
    api_key = setup_api_key()

    # Step 2: CSV ファイル確認
    detected_categories = check_csv_files()

    # Anthropic クライアント初期化
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
    except ImportError:
        print()
        print("エラー: anthropic ライブラリがインストールされていません。")
        print("  pip install -r requirements.txt")
        sys.exit(1)

    # Step 3: 対話ヒアリング（Haiku）
    try:
        raw_config = run_conversation(client, detected_categories)
    except KeyboardInterrupt:
        print("\n\nキャンセルしました。")
        sys.exit(0)

    # Step 4: プロンプト生成（Sonnet）
    prompts = generate_prompts(client, raw_config)

    # Step 5: config.json 書き出し
    config = write_config(raw_config, prompts)

    # Step 6: generate.py 書き出し
    write_generate_py(config)

    # 完了メッセージ
    print()
    print("━" * 50)
    print("  セットアップ完了！")
    print("━" * 50)
    print()
    print("次のステップ:")
    print()
    print("  1. curriculum/ に chapters.csv と lessons.csv を配置")
    print("     （まだ配置していない場合）")
    print()
    print("  2. 教材を生成:")
    print("     python3 generate.py")
    print()
    print("  ※ 設定を変更したい場合は python3 init.py を再実行してください。")
    print()


if __name__ == "__main__":
    main()
