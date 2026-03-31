"""
Phase 2: 生成済みコンテンツの品質検証スクリプト

以下の項目をチェックし、問題のあるファイルを CSV でレポートする:
  - フロントマターの完全性（7つの必須キー）
  - estimated_time_min の型（5〜30の整数）
  - コードフェンスによる二重ラップ（バグ検出）
  - 必須セクションの存在確認
  - ファイルが文中で切れていないか（truncation）
  - 最小文字数（本文 1500 文字以上）

使い方:
  python scripts/validate_content.py                    # 全ファイル
  python scripts/validate_content.py curriculum/premiere-pro/04_cut/  # 特定フォルダ
"""
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

CURRICULUM_DIR = Path("curriculum/premiere-pro")
OUTPUT_DIR = Path("output")

REQUIRED_FM_KEYS = ["title", "chapter", "section", "level", "goal_income", "chapter_video_url", "estimated_time_min"]
REQUIRED_SECTIONS = ["## よくある失敗", "## ミニ課題", "## ここまでできればOK"]
MIN_BODY_CHARS = 1500

_FM_PATTERN = re.compile(r"^(?:```[a-z]*\s*\n)?---\s*\n(.*?)\n---", re.DOTALL)


def parse_frontmatter(content: str) -> Optional[dict]:
    m = _FM_PATTERN.match(content)
    if not m:
        return None
    result: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def get_body(content: str) -> str:
    """frontmatter 以降の本文を返す。"""
    m = _FM_PATTERN.match(content)
    if not m:
        return content
    return content[m.end():].strip()


def check_file(path: Path) -> list[dict]:
    """ファイルを検証し、問題リストを返す。各要素は {file, check, status, detail}"""
    issues = []
    content = path.read_text(encoding="utf-8")

    def issue(check: str, detail: str = ""):
        issues.append({"file": str(path), "check": check, "status": "FAIL", "detail": detail})

    def ok(check: str):
        issues.append({"file": str(path), "check": check, "status": "OK", "detail": ""})

    # コードフェンスバグ
    if content.lstrip().startswith("```"):
        issue("code_fence_bug", "ファイルが ``` で始まっている（二重フェンスバグ）")
    else:
        ok("code_fence_bug")

    # フロントマター解析
    fm = parse_frontmatter(content)
    if fm is None:
        issue("frontmatter_parse", "frontmatter を解析できない")
        return issues

    # 必須キーの存在確認
    missing_keys = [k for k in REQUIRED_FM_KEYS if k not in fm]
    if missing_keys:
        issue("frontmatter_keys", f"不足キー: {', '.join(missing_keys)}")
    else:
        ok("frontmatter_keys")

    # estimated_time_min の型チェック
    etm = fm.get("estimated_time_min", "")
    try:
        etm_val = int(etm)
        if 5 <= etm_val <= 30:
            ok("estimated_time_min")
        else:
            issue("estimated_time_min", f"範囲外 (5〜30): {etm_val}")
    except (ValueError, TypeError):
        issue("estimated_time_min", f"整数でない値: '{etm}'")

    # 本文取得
    body = get_body(content)

    # 必須セクションの存在確認
    for section in REQUIRED_SECTIONS:
        if section in body:
            ok(f"section_{section.strip('#').strip()}")
        else:
            issue(f"section_{section.strip('#').strip()}", f"'{section}' が見つからない")

    # 最小文字数
    if len(body) >= MIN_BODY_CHARS:
        ok("min_body_chars")
    else:
        issue("min_body_chars", f"本文 {len(body)} 文字（最低 {MIN_BODY_CHARS} 文字）")

    # truncation 検出（文中で切れていないか）
    # 最後の非空行を取得し、明らかに途中で切れているかを判定する
    non_empty_lines = [l for l in content.split("\n") if l.strip()]
    last_line = non_empty_lines[-1].strip() if non_empty_lines else ""

    # 明確に切れていない（OK）パターン
    _NOT_TRUNCATED = (
        # 行頭がリスト・見出し・引用符・コードフェンス
        re.match(r"^[-*#>]", last_line)
        # 番号リスト
        or re.match(r"^\d+\.", last_line)
        # URL のみの行
        or re.match(r"^https?://", last_line)
        # 末尾が句読点・括弧・感嘆疑問符
        or last_line.endswith(("。", ".", "！", "!", "？", "?", "）", ")", "」", "\"", "…", "✅"))
        # 末尾がコードフェンス
        or last_line.endswith("```")
        # 画像・図解プレースホルダーや図表キャプション
        or re.search(r"[（(]画像[）)]", last_line)
        or last_line.startswith(("※", "▲", "△", "図：", "図）"))
        or re.search(r"[図解画像例示比較]を挿入$", last_line)
        or re.search(r"(スクリーンショット|キャプチャ|画面|図解|状態|比較)$", last_line)
        # イタリック/太字マーカーで終わる（Markdown 装飾）
        or last_line.endswith("*")
        or last_line.endswith("_")
    )

    if _NOT_TRUNCATED:
        ok("truncation")
    else:
        # 最後の文字が日本語文字で、かつ一般的な文末でない → 切れている可能性が高い
        last_char = last_line[-1] if last_line else ""
        is_jp = re.match(r"[\u3040-\u9fff]", last_char)
        if is_jp:
            issue("truncation", f"文中で切れている可能性: '{last_line[:60]}'")
        else:
            ok("truncation")

    return issues


def main():
    target_arg = sys.argv[1] if len(sys.argv) > 1 else None
    if target_arg:
        target = Path(target_arg)
        files = sorted(target.glob("**/*.md")) if target.is_dir() else [target]
    else:
        files = sorted(CURRICULUM_DIR.glob("**/*.md"))

    files = [f for f in files if f.name != "README.md"]

    if not files:
        print("対象ファイルが見つかりません。")
        return

    all_issues: list[dict] = []
    fail_counts: dict[str, int] = {}

    for path in files:
        file_issues = check_file(path)
        all_issues.extend(file_issues)
        for item in file_issues:
            if item["status"] == "FAIL":
                fail_counts[item["check"]] = fail_counts.get(item["check"], 0) + 1

    # CSV 出力
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"validation_{ts}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "check", "status", "detail"])
        writer.writeheader()
        writer.writerows(all_issues)

    # サマリー表示
    total_files = len(files)
    fail_files = len({i["file"] for i in all_issues if i["status"] == "FAIL"})
    total_fails = sum(1 for i in all_issues if i["status"] == "FAIL")

    print(f"\n{'='*60}")
    print(f"検証結果: {total_files} ファイル / {fail_files} ファイルに問題あり / {total_fails} 件の FAIL")
    print(f"{'='*60}")
    if fail_counts:
        print("チェック別 FAIL 件数:")
        for check, count in sorted(fail_counts.items(), key=lambda x: -x[1]):
            print(f"  {check:40s}  {count:3d} 件")
    else:
        print("すべてのチェックが PASS しました！")
    print(f"\nレポート: {out_path}")


if __name__ == "__main__":
    main()
