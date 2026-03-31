"""
curriculum/premiere-pro/ 配下を走査し、
・コース全体 README.md
・各章 README.md
・機械可読 _index.json
を自動生成する。
Frontmatter の title, estimated_time_min, chapter_video_url を優先使用。
"""
import csv
import json
import re
from pathlib import Path
from typing import List, Optional

CHAPTERS_CSV = Path("curriculum/chapters.csv")

# カテゴリ略称 → コースフォルダ名（build_master_csv.py と同じマッピング）
CATEGORY_FOLDER = {
    "Pr": "premiere-pro",
    "Ps": "photoshop",
    "Ae": "after-effects",
}

DEFAULT_CATEGORY = "Pr"


def load_chapter_order(category: str = DEFAULT_CATEGORY) -> List[str]:
    """
    chapters.csv から指定カテゴリの chapter_folder を order 順で返す。
    CHAPTER_ORDER 定数の代替。
    """
    rows = []
    with CHAPTERS_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["category"].strip() == category:
                rows.append((int(r["order"]), r["chapter_folder"].strip()))
    return [folder for _, folder in sorted(rows)]


def get_course_root(category: str = DEFAULT_CATEGORY) -> Path:
    folder = CATEGORY_FOLDER.get(category, category.lower())
    return Path("curriculum") / folder


def parse_frontmatter(md_path: Path) -> dict:
    """Markdown の Frontmatter（YAML）を簡易パース。title, estimated_time_min, chapter_video_url を返す。"""
    text = md_path.read_text(encoding="utf-8")
    match = re.match(r"^(?:```yaml\s*\n)?---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    block = match.group(1)
    result = {}
    for line in block.splitlines():
        m = re.match(r"^(\w+):\s*(.+)$", line.strip())
        if m:
            key, value = m.group(1), m.group(2).strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace('\\"', '"')
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1].replace("\\'", "'")
            if key == "estimated_time_min":
                try:
                    value = int(value)
                except ValueError:
                    value = None
            result[key] = value
    return result


def collect_lessons(chapter_folder: Path, course_root: Path) -> List[dict]:
    """章フォルダ内の .md ファイル（README 除く）を収集し、Frontmatter を付けて返す。"""
    lessons = []
    for p in sorted(chapter_folder.glob("*.md")):
        if p.name == "README.md":
            continue
        fm = parse_frontmatter(p)
        lessons.append({
            "file": p.name,
            "title": fm.get("title") or p.stem,
            "estimated_time_min": fm.get("estimated_time_min"),
            "path": str(p.relative_to(course_root)),
        })
    return lessons


def collect_chapters(course_root: Path, chapter_order: List[str]) -> List[dict]:
    """全章フォルダを ORDER に従い収集。各章に lessons と chapter_video_url（章内先頭レッスンから）を付与。"""
    chapters = []
    for folder_name in chapter_order:
        chapter_path = course_root / folder_name
        if not chapter_path.is_dir():
            continue
        lessons = collect_lessons(chapter_path, course_root)
        chapter_video_url = None
        if lessons:
            first_md = chapter_path / lessons[0]["file"]
            fm = parse_frontmatter(first_md)
            chapter_video_url = fm.get("chapter_video_url") or None
        chapters.append({
            "folder": folder_name,
            "lessons": lessons,
            "chapter_video_url": chapter_video_url,
        })
    return chapters


def build_course_readme(chapters: List[dict]) -> str:
    """コース全体の README（目次）を生成。"""
    lines = [
        "# Premiere Pro 教材",
        "",
        "## 目次",
        "",
    ]
    for ch in chapters:
        folder = ch["folder"]
        readme_link = f"{folder}/README.md"
        lines.append(f"- [{folder}]({readme_link})")
        for les in ch["lessons"]:
            lines.append(f"  - [{les['title']}]({folder}/{les['file']})")
        lines.append("")
    return "\n".join(lines)


def build_chapter_readme(chapter_folder: str, lessons: List[dict], chapter_video_url: Optional[str]) -> str:
    """章ごとの README（目次）を生成。"""
    lines = [
        f"# {chapter_folder}",
        "",
    ]
    if chapter_video_url:
        lines.append(f"## 章概要動画\n")
        lines.append(f"{chapter_video_url}\n")
    lines.append("## レッスン一覧\n")
    for les in lessons:
        title = les["title"]
        if les.get("estimated_time_min") is not None:
            title = f"{title}（約{les['estimated_time_min']}分）"
        lines.append(f"- [{title}]({les['file']})")
    lines.append("")
    return "\n".join(lines)


def build_index_json(chapters: List[dict]) -> dict:
    """機械可読インデックス用の辞書を生成。"""
    return {
        "course": "Premiere Pro",
        "chapters": [
            {
                "folder": ch["folder"],
                "chapter_video_url": ch["chapter_video_url"],
                "lessons": [
                    {
                        "file": les["file"],
                        "title": les["title"],
                        "estimated_time_min": les.get("estimated_time_min"),
                        "path": les["path"],
                    }
                    for les in ch["lessons"]
                ],
            }
            for ch in chapters
        ],
    }


def main():
    course_root   = get_course_root()
    course_readme = course_root / "README.md"
    index_json    = course_root / "_index.json"
    chapter_order = load_chapter_order()

    course_root.mkdir(parents=True, exist_ok=True)

    chapters = collect_chapters(course_root, chapter_order)

    # コース全体 README
    course_readme.write_text(build_course_readme(chapters), encoding="utf-8")
    print(f"✅ Wrote {course_readme}")

    # 各章 README
    for ch in chapters:
        readme_path = course_root / ch["folder"] / "README.md"
        readme_path.parent.mkdir(parents=True, exist_ok=True)
        body = build_chapter_readme(
            ch["folder"],
            ch["lessons"],
            ch["chapter_video_url"],
        )
        readme_path.write_text(body, encoding="utf-8")
        print(f"✅ Wrote {readme_path}")

    # _index.json
    index_data = build_index_json(chapters)
    index_json.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Wrote {index_json}")


if __name__ == "__main__":
    main()
