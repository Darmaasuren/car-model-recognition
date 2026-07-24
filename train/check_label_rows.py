import csv
from collections import OrderedDict

from src.config import DATA_SPLITS, LABEL_GROUPS


def normalize_label_name(label: str) -> str:
    return " ".join(label.split())


def active_labels(row, labels):
    return [label for label in labels if int(row.get(label, 0)) == 1]


def check_split(split: str):
    csv_path = DATA_SPLITS[split] / "_classes.csv"
    groups = OrderedDict((group_name, list(labels)) for group_name, labels in LABEL_GROUPS.items())
    all_labels = [label for labels in groups.values() for label in labels]
    label_name_map = {normalize_label_name(label): label for label in all_labels}
    bad_rows = []

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for line_number, row in enumerate(reader, start=2):
            normalized_row = {
                label_name_map[normalize_label_name(label)]: int(value)
                for label, value in row.items()
                if label != "filename"
            }
            problems = []
            total_active = 0

            for group_name, labels in groups.items():
                active = active_labels(normalized_row, labels)
                total_active += len(active)
                if len(active) == 0:
                    problems.append(f"{group_name}: missing")
                elif len(active) > 1:
                    problems.append(f"{group_name}: multiple={active}")

            if total_active != 4:
                problems.append(f"total_active={total_active}, expected=4")

            if problems:
                bad_rows.append(
                    {
                        "line": line_number,
                        "filename": row["filename"],
                        "problems": problems,
                    }
                )

    print(f"\n=== {split.upper()} ===")
    print(f"bad rows: {len(bad_rows)}")
    for item in bad_rows:
        print(f"line {item['line']} | {item['filename']} | {'; '.join(item['problems'])}")


def main():
    for split in ["train", "valid", "test"]:
        check_split(split)


if __name__ == "__main__":
    main()
