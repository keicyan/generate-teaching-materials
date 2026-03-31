"""
curriculum/chapters.csv + curriculum/lessons.csv を読み込み、
curriculum/curriculum_master.csv を生成する。

build_master_csv_from_csv.py（raw_topics.csv + CHAPTER_MAP定数に依存）の後継。
出力カラムは既存の curriculum_master.csv と同じ形式を保つ。

category → course フォルダのマッピング:
  Pr → premiere-pro
  Ps → photoshop
  Ae → after-effects
"""
import csv
from pathlib import Path

CHAPTERS_CSV = Path("curriculum/chapters.csv")
LESSONS_CSV  = Path("curriculum/lessons.csv")
OUT_CSV      = Path("curriculum/curriculum_master.csv")

# カテゴリ略称 → コースフォルダ名
CATEGORY_FOLDER = {
    "Pr": "premiere-pro",
    "Ps": "photoshop",
    "Ae": "after-effects",
}

# デフォルトの type 値（将来的に lessons.csv に列追加で上書き可能）
DEFAULT_TYPE = "操作解説"


def load_chapters() -> dict[tuple[str, str], dict]:
    """(category, chapter_key) → chapter row の辞書を返す。"""
    mapping = {}
    with open(CHAPTERS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["category"].strip(), row["chapter_key"].strip())
            mapping[key] = {k: v.strip() for k, v in row.items()}
    return mapping


def main() -> None:
    chapters = load_chapters()

    fieldnames = [
        "category", "type", "chapter_jp", "chapter_key", "chapter_folder",
        "index_in_chapter", "topic", "md_file", "output_path",
    ]

    rows = []
    skipped = []

    with open(LESSONS_CSV, newline="", encoding="utf-8") as f:
        for lesson in csv.DictReader(f):
            category    = lesson["category"].strip()
            chapter_key = lesson["chapter_key"].strip()
            order       = int(lesson["order"])
            topic       = lesson["topic"].strip()
            md_file     = lesson["md_file"].strip()

            ch = chapters.get((category, chapter_key))
            if ch is None:
                skipped.append(f"[{category}] {chapter_key}")
                continue

            chapter_jp     = ch["chapter_jp"]
            chapter_folder = ch["chapter_folder"]
            course_folder  = CATEGORY_FOLDER.get(category, category.lower())
            output_path    = f"curriculum/{course_folder}/{chapter_folder}/{md_file}"

            rows.append({
                "category":          category,
                "type":              DEFAULT_TYPE,
                "chapter_jp":        chapter_jp,
                "chapter_key":       chapter_key,
                "chapter_folder":    chapter_folder,
                "index_in_chapter":  order,
                "topic":             topic,
                "md_file":           md_file,
                "output_path":       output_path,
            })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ {OUT_CSV} — {len(rows)} 行を書き出しました")
    if skipped:
        for s in sorted(set(skipped)):
            print(f"⚠️  chapters.csv に未登録: {s}")


if __name__ == "__main__":
    main()
