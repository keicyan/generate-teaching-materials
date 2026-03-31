import csv
import sys
from collections import defaultdict
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/summarize_cost.py output/_runs/run_YYYYMMDD_HHMMSS/cost.csv")
        sys.exit(1)

    cost_path = Path(sys.argv[1])
    if not cost_path.exists():
        raise FileNotFoundError(cost_path)

    total_cost = 0.0
    total_in = 0
    total_out = 0

    by_model = defaultdict(lambda: {"cost": 0.0, "in": 0, "out": 0, "count": 0})
    # 章キーを topic だけからは取れないので、将来必要ならcost.csvにchapter_key列を足す設計にできる
    # 今回はまずモデル別/合計のサマリを提供（十分有用）

    with cost_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            c = float(r["cost_usd"])
            it = int(r["input_tokens"])
            ot = int(r["output_tokens"])
            m = r.get("model", "unknown")

            total_cost += c
            total_in += it
            total_out += ot

            by_model[m]["cost"] += c
            by_model[m]["in"] += it
            by_model[m]["out"] += ot
            by_model[m]["count"] += 1

    print("\n=== COST SUMMARY ===")
    print(f"Files: {sum(v['count'] for v in by_model.values())}")
    print(f"Total input tokens : {total_in}")
    print(f"Total output tokens: {total_out}")
    print(f"Total cost (USD)   : ${total_cost:.4f}")

    print("\n--- By model ---")
    for m, v in sorted(by_model.items(), key=lambda x: x[1]["cost"], reverse=True):
        print(f"{m}: files={v['count']} cost=${v['cost']:.4f} in={v['in']} out={v['out']}")

if __name__ == "__main__":
    main()
