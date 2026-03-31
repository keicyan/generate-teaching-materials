import argparse
import csv
import json
import os
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from anthropic import Anthropic

MASTER_CSV    = "curriculum/curriculum_master.csv"
CHAPTERS_CSV  = "curriculum/chapters.csv"
CHAPTERS_CONTEXT_DIR = Path("docs/chapters")

# 公式Pricing（USD / MTok）をベースに「よく使うモデル」を内蔵
MODEL_PRICING_USD_PER_MTOK = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-3-7-sonnet-latest": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-3-5": (0.8, 4.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-opus-4-5": (5.0, 25.0),
}

SYSTEM_PROMPT = """あなたは教材の編集者です。
必ずLMS投入用のMarkdownで出力してください。
コードブロックは必要なときだけ最小限にしてください。"""

# デフォルトの対象読者・教材方針（--config 未使用時のフォールバック）
DEFAULT_AUDIENCE_BLOCK = """対象読者：
・18〜30歳の若年層
・完全未経験
・副業で収入を得ることを目指す学習者"""

DEFAULT_POLICY_BLOCK = """教材方針：
・専門用語は必ずかみ砕いて説明
・スマホ世代でも理解できる表現を使う
・難しい言葉は使わない
・短めの段落で読みやすくする
・初心者がつまずくポイントを先回りして解説する
・実務イメージが湧く具体例を入れる
・よくある失敗例も必ず記載する
・各セクションの最後にミニ課題を入れる
・「ここまでできればOK」の到達ラインを記載する"""

# 章の最初のレッスン用テンプレート（章イントロ + 本章の目的 あり）
USER_TEMPLATE_FIRST = """
{audience_block}

{policy_block}

出力条件：
・Markdown形式（LMSにそのまま投入できる）
・見出し構造を明確にする
・図解が必要な箇所には「（画像）」とだけ記載（画像生成はしない）
・本文は"このセクション単体で理解できる"ように完結させる
・Frontmatter（YAML）を必ず含める
・estimated_time_minはセクションの内容量・手順数に基づき5〜20の整数で設定すること（手順5ステップ以下→5〜10分、10ステップ以上→15〜20分）
・レッスン本文は必ず「# {topic}」から始めること。「# {chapter_jp}」の見出しは絶対に出力しないこと

今回作る教材：
カテゴリ：{category}
章：{chapter_jp}
章キー：{chapter_key}
トピック：{topic}
章概要動画URL：{chapter_video_url}

章の方針（概要動画の文字起こしに基づく。この方針・ゴールを必ず守って教材を作成すること）：
{chapter_context}

ページ相当：
8〜12ページ相当（ただし冗長にしない、読みやすさ優先）

必ず次の構造で出力（順序固定）：

---
title: "{topic}"
chapter: "{chapter_jp}"
section: "{chapter_jp}"
level: "beginner"
goal_income: "5-10"
chapter_video_url: "{chapter_video_url}"
estimated_time_min: XX  ←★ 5〜20の整数で設定。手順・セクション数から判断すること（例：手順5つ以下=5〜10、10以上=15〜20）
---

# {topic}

## このセクションでできるようになること
- （3つ）

## 概要
（わかりやすく）

## 手順
1.
2.
3.

## よくある失敗
- （3つ）

## ミニ課題（5〜15分）
- 課題：
- 提出物：
- チェックポイント：

## ここまでできればOK
- （3つ）

（必要なら）## 図解
（画像）
"""

# 章の2番目以降のレッスン用テンプレート（章概要動画なし）
USER_TEMPLATE_REST = """
{audience_block}

{policy_block}

出力条件：
・Markdown形式（LMSにそのまま投入できる）
・見出し構造を明確にする
・図解が必要な箇所には「（画像）」とだけ記載（画像生成はしない）
・本文は"このセクション単体で理解できる"ように完結させる
・Frontmatter（YAML）を必ず含める
・estimated_time_minはセクションの内容量・手順数に基づき5〜20の整数で設定すること（手順5ステップ以下→5〜10分、10ステップ以上→15〜20分）
・レッスン本文は必ず「# {topic}」から始めること。「# {chapter_jp}」の見出しは絶対に出力しないこと

今回作る教材：
カテゴリ：{category}
章：{chapter_jp}
章キー：{chapter_key}
トピック：{topic}
章概要動画URL：{chapter_video_url}

章の方針（概要動画の文字起こしに基づく。この方針・ゴールを必ず守って教材を作成すること）：
{chapter_context}

ページ相当：
8〜12ページ相当（ただし冗長にしない、読みやすさ優先）

必ず次の構造で出力（順序固定）：

---
title: "{topic}"
chapter: "{chapter_jp}"
section: "{chapter_jp}"
level: "beginner"
goal_income: "5-10"
chapter_video_url: "{chapter_video_url}"
estimated_time_min: XX  ←★ 5〜20の整数で設定。手順・セクション数から判断すること（例：手順5つ以下=5〜10、10以上=15〜20）
---

# {topic}

## このセクションでできるようになること
- （3つ）

## 概要
（わかりやすく）

## 手順
1.
2.
3.

## よくある失敗
- （3つ）

## ミニ課題（5〜15分）
- 課題：
- 提出物：
- チェックポイント：

## ここまでできればOK
- （3つ）

（必要なら）## 図解
（画像）
"""

@dataclass
class RunPaths:
    run_dir: Path
    progress_csv: Path
    errors_log: Path
    cost_log: Path

def load_config(path: str) -> dict:
    """config.json を読み込む。パスが空または存在しない場合は空 dict を返す。"""
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        print(f"⚠️  Config file not found: {path} — using defaults")
        return {}
    with p.open(encoding="utf-8") as f:
        return json.load(f)

def ensure_api_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY を環境変数に設定してください")
    return key

def make_run_paths() -> RunPaths:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path("output/_runs") / f"run_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunPaths(
        run_dir=run_dir,
        progress_csv=run_dir / "progress.csv",
        errors_log=run_dir / "errors.log",
        cost_log=run_dir / "cost.csv",
    )

def write_error(paths: RunPaths, msg: str):
    with paths.errors_log.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

def read_master_rows() -> list[Dict[str, str]]:
    with open(MASTER_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_chapter_overview() -> Dict[Tuple[str, str], Dict[str, str]]:
    """
    curriculum/chapters.csv と docs/chapters/{category}/{chapter_key}.md を読み、
    (category, chapter_jp) をキーに {"context": ..., "movie": ...} の辞書を返す。
    """
    chapters_path = Path(CHAPTERS_CSV)
    if not chapters_path.exists():
        return {}

    result: Dict[Tuple[str, str], Dict[str, str]] = {}
    with chapters_path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cat       = (r.get("category") or "").strip()
            ch_jp     = (r.get("chapter_jp") or "").strip()
            ch_key    = (r.get("chapter_key") or "").strip()
            movie     = (r.get("chapter_video_url") or "").strip()
            if not ch_jp:
                continue

            ctx_path = CHAPTERS_CONTEXT_DIR / cat / f"{ch_key}.md"
            ctx = ctx_path.read_text(encoding="utf-8").strip() if ctx_path.exists() else ""

            result[(cat, ch_jp)] = {"context": ctx, "movie": movie}
    return result

def normalize_text(md: str) -> str:
    """コードフェンスによる二重ラップを除去し末尾改行を正規化する。"""
    text = md.strip()
    lines = text.split("\n")

    if lines and lines[0].startswith("```"):
        if len(lines) > 1 and lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
            dash_count = 0
            for i, line in enumerate(lines):
                if line.strip() == "---":
                    dash_count += 1
                    if dash_count == 2:
                        if i + 1 < len(lines) and lines[i + 1].startswith("```"):
                            lines.pop(i + 1)
                        break
        text = "\n".join(lines).strip()

    return text + "\n"

def get_pricing_for_model(model: str, override_in: Optional[float], override_out: Optional[float]) -> Tuple[float, float]:
    if override_in is not None and override_out is not None:
        return float(override_in), float(override_out)

    for k, v in MODEL_PRICING_USD_PER_MTOK.items():
        if model.startswith(k):
            return v

    return (3.0, 15.0)

def extract_usage_tokens(res) -> Tuple[int, int]:
    usage = getattr(res, "usage", None)
    if usage is None:
        return (0, 0)

    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

    cache_creation = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    input_total = input_tokens + cache_creation + cache_read

    return (input_total, output_tokens)

def estimate_cost_usd(input_tokens: int, output_tokens: int, price_in_per_mtok: float, price_out_per_mtok: float) -> float:
    return (input_tokens / 1_000_000.0) * price_in_per_mtok + (output_tokens / 1_000_000.0) * price_out_per_mtok

def call_claude(client: Anthropic, model: str, max_tokens: int, system_prompt: str, prompt: str):
    return client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )

def resolve_model_id(client: Anthropic, requested_model: str) -> str:
    try:
        res = client.models.list()
        data = getattr(res, "data", None) or []
        model_ids = [m.id for m in data if getattr(m, "id", None)]
        if not model_ids:
            return requested_model

        if requested_model in model_ids:
            return requested_model

        def score(mid: str) -> int:
            s = 0
            m = mid.lower()
            if "sonnet" in m:
                s += 30
            if "haiku" in m:
                s += 20
            if "opus" in m:
                s += 10
            if "latest" in m:
                s += 5
            return s

        fallback = sorted(model_ids, key=score, reverse=True)[0]
        print(f"⚠️  Model not found: {requested_model} -> fallback to: {fallback}")
        preview = ", ".join(model_ids[:20])
        if len(model_ids) > 20:
            preview += " ..."
        print(f"ℹ️  Available models: {preview}")
        return fallback
    except Exception as e:
        print(f"⚠️  Could not validate model '{requested_model}' via models.list ({type(e).__name__}: {e}). Proceeding as-is.")
        return requested_model

def should_process_row(row: Dict[str, str], only_chapter: Optional[str], only_folder: Optional[str]) -> bool:
    if only_chapter and row.get("chapter_key") != only_chapter:
        return False
    if only_folder and row.get("chapter_folder") != only_folder:
        return False
    return True

def main():
    parser = argparse.ArgumentParser(description="Generate curriculum markdowns via Claude API.")
    parser.add_argument("--config", default="", help="Path to config.json written by init.py")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Claude model id")
    parser.add_argument("--max-tokens", type=int, default=4500, help="max_tokens for each generation")
    parser.add_argument("--retries", type=int, default=4, help="retries per item on error")
    parser.add_argument("--sleep", type=float, default=0.0, help="sleep seconds between requests")
    parser.add_argument("--start-row", type=int, default=1, help="1-based row index to start from")
    parser.add_argument("--limit", type=int, default=0, help="max number of rows to process (0 = all)")
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--no-skip-existing", dest="skip_existing", action="store_false")
    parser.add_argument("--overwrite", action="store_true", help="overwrite even if md exists")
    parser.add_argument("--dry-run", action="store_true", help="do not call API")
    parser.add_argument("--only-chapter", default="", help="process only this chapter_key")
    parser.add_argument("--only-folder", default="", help="process only this chapter_folder")
    parser.add_argument("--budget-usd", type=float, default=0.0, help="Stop when spend reaches this USD (0 = unlimited)")
    parser.add_argument("--price-input", type=float, default=None, help="Override input price ($/MTok)")
    parser.add_argument("--price-output", type=float, default=None, help="Override output price ($/MTok)")

    args = parser.parse_args()

    # config.json から設定を読み込み（なければデフォルト値を使用）
    cfg = load_config(args.config)
    system_prompt_effective = cfg.get("prompts", {}).get("system_prompt", SYSTEM_PROMPT)
    audience_block = cfg.get("prompts", {}).get("audience_block", DEFAULT_AUDIENCE_BLOCK)
    policy_block   = cfg.get("prompts", {}).get("policy_block",   DEFAULT_POLICY_BLOCK)

    # config の model 設定を CLI 引数で上書き可能
    if cfg.get("model", {}).get("model_id") and args.model == "claude-sonnet-4-6":
        args.model = cfg["model"]["model_id"]
    if cfg.get("model", {}).get("max_tokens") and args.max_tokens == 4500:
        args.max_tokens = cfg["model"]["max_tokens"]
    if cfg.get("model", {}).get("budget_usd") and args.budget_usd == 0.0:
        args.budget_usd = cfg["model"]["budget_usd"]

    only_chapter = args.only_chapter.strip() or None
    only_folder = args.only_folder.strip() or None

    paths = make_run_paths()

    # progress CSV header
    with paths.progress_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["row_no", "chapter_key", "chapter_jp", "topic", "output_path", "status", "attempts", "error"],
        )
        writer.writeheader()

    # cost CSV header
    with paths.cost_log.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["row_no", "topic", "input_tokens", "output_tokens", "cost_usd", "cumulative_usd", "price_in_per_mtok", "price_out_per_mtok", "model"],
        )
        writer.writeheader()

    rows = read_master_rows()
    total = len(rows)

    start = max(args.start_row, 1)
    end = total if args.limit == 0 else min(total, start - 1 + args.limit)

    client = None
    if not args.dry_run:
        ensure_api_key()
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        args.model = resolve_model_id(client, args.model)

    price_in, price_out = get_pricing_for_model(args.model, args.price_input, args.price_output)

    chapter_overview = read_chapter_overview()
    if chapter_overview:
        print(f"📋 Chapter overview: {len(chapter_overview)} entries loaded from {CHAPTERS_CSV}")
    else:
        print(f"⚠️  No chapter overview found at {CHAPTERS_CSV}")

    print(f"🧾 Master rows: {total}")
    print(f"🚀 Processing rows: {start}..{end} (filters: chapter={only_chapter}, folder={only_folder})")
    print(f"💵 Pricing assumed: input ${price_in}/MTok, output ${price_out}/MTok (model={args.model})")
    if args.budget_usd and args.budget_usd > 0:
        print(f"🧯 Budget cap: ${args.budget_usd} USD")
    print(f"📝 Run logs: {paths.run_dir}")

    cumulative_usd = 0.0
    processed = 0

    for i in range(start, end + 1):
        row = rows[i - 1]

        if not should_process_row(row, only_chapter, only_folder):
            continue

        chapter_key = row.get("chapter_key", "").strip()
        chapter_jp = row.get("chapter_jp", "").strip()
        topic = row.get("topic", "").strip()
        out_path = Path(row.get("output_path", "")).resolve()

        if args.budget_usd and args.budget_usd > 0 and cumulative_usd >= args.budget_usd:
            print(f"🛑 Budget reached. cumulative=${cumulative_usd:.4f} >= cap=${args.budget_usd:.4f}")
            break

        category = (row.get("category") or "").strip()
        overview = chapter_overview.get((category, chapter_jp), {}) if chapter_overview else {}
        chapter_video_url = (overview.get("movie") or "").strip()
        chapter_context = (overview.get("context") or "").strip()
        if not chapter_context:
            chapter_context = "（この章の概要動画の文字起こしは未登録です。共通の教材方針に従って作成してください。）"

        if args.overwrite:
            skip_existing = False
        else:
            skip_existing = args.skip_existing

        if skip_existing and out_path.exists():
            print(f"⏭️  Skip existing: {out_path.name}")
            with paths.progress_csv.open("a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["row_no","chapter_key","chapter_jp","topic","output_path","status","attempts","error"])
                writer.writerow({"row_no": i, "chapter_key": chapter_key, "chapter_jp": chapter_jp, "topic": topic, "output_path": str(out_path), "status": "skipped", "attempts": 0, "error": ""})
            continue

        index_in_chapter = int(row.get("index_in_chapter", 0) or 0)
        template = USER_TEMPLATE_FIRST if index_in_chapter == 1 else USER_TEMPLATE_REST
        prompt = template.format(
            audience_block=audience_block,
            policy_block=policy_block,
            category=category,
            chapter_jp=chapter_jp,
            chapter_key=chapter_key,
            topic=topic,
            chapter_video_url=chapter_video_url,
            chapter_context=chapter_context,
        )

        if args.dry_run:
            print(f"[DRY] Would generate: row={i} -> {out_path}")
            processed += 1
            continue

        out_path.parent.mkdir(parents=True, exist_ok=True)

        attempts = 0
        ok = False
        last_err = ""

        while attempts <= args.retries and not ok:
            attempts += 1
            try:
                if args.sleep > 0:
                    time.sleep(args.sleep)

                res = call_claude(
                    client=client,
                    model=args.model,
                    max_tokens=args.max_tokens,
                    system_prompt=system_prompt_effective,
                    prompt=prompt,
                )

                text = "".join([c.text for c in res.content if getattr(c, "text", None)])
                md = normalize_text(text)
                out_path.write_text(md, encoding="utf-8")

                in_tok, out_tok = extract_usage_tokens(res)
                cost = estimate_cost_usd(in_tok, out_tok, price_in, price_out)
                cumulative_usd += cost

                with paths.cost_log.open("a", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=["row_no","topic","input_tokens","output_tokens","cost_usd","cumulative_usd","price_in_per_mtok","price_out_per_mtok","model"])
                    writer.writerow({"row_no": i, "topic": topic, "input_tokens": in_tok, "output_tokens": out_tok, "cost_usd": f"{cost:.6f}", "cumulative_usd": f"{cumulative_usd:.6f}", "price_in_per_mtok": price_in, "price_out_per_mtok": price_out, "model": args.model})

                ok = True
                print(f"✅ Generated ({attempts}): {out_path.name} | cost=${cost:.4f} cum=${cumulative_usd:.4f}")

                with paths.progress_csv.open("a", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=["row_no","chapter_key","chapter_jp","topic","output_path","status","attempts","error"])
                    writer.writerow({"row_no": i, "chapter_key": chapter_key, "chapter_jp": chapter_jp, "topic": topic, "output_path": str(out_path), "status": "ok", "attempts": attempts, "error": ""})

                if args.budget_usd and args.budget_usd > 0 and cumulative_usd >= args.budget_usd:
                    print(f"🛑 Budget reached after row {i}. cumulative=${cumulative_usd:.4f} >= cap=${args.budget_usd:.4f}")
                    return

            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                print(f"⚠️  Error row={i} attempt={attempts}/{args.retries+1}: {last_err}")

                write_error(paths, f"[row {i}] {chapter_key} / {topic} / {out_path}")
                write_error(paths, last_err)
                write_error(paths, traceback.format_exc())
                write_error(paths, "-" * 80)

                backoff = min(60, 2 ** (attempts - 1))
                time.sleep(backoff)

        if not ok:
            with paths.progress_csv.open("a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["row_no","chapter_key","chapter_jp","topic","output_path","status","attempts","error"])
                writer.writerow({"row_no": i, "chapter_key": chapter_key, "chapter_jp": chapter_jp, "topic": topic, "output_path": str(out_path), "status": "failed", "attempts": attempts, "error": last_err})
            print(f"❌ Failed: row={i} -> {out_path.name}")

        processed += 1

    print(f"\n🏁 Done. processed={processed}")
    print(f"📄 Progress: {paths.progress_csv}")
    print(f"💸 Cost log:  {paths.cost_log}")
    print(f"🪵 Errors:    {paths.errors_log}")

if __name__ == "__main__":
    main()
