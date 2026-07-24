import csv
from collections import OrderedDict

from src.config import DATA_SPLITS, LABEL_GROUPS


def normalize_label_name(label: str) -> str:
    return " ".join(label.split())


def count_split(split: str):
    csv_path = DATA_SPLITS[split] / "_classes.csv"
    groups = OrderedDict((group_name, list(labels)) for group_name, labels in LABEL_GROUPS.items())
    all_labels = [label for labels in groups.values() for label in labels]
    label_name_map = {normalize_label_name(label): label for label in all_labels}
    counts = {label: 0 for label in all_labels}
    missing = {group_name: 0 for group_name in groups}
    multi = {group_name: 0 for group_name in groups}
    rows = 0

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            normalized_row = {
                label_name_map[normalize_label_name(label)]: int(value)
                for label, value in row.items()
                if label != "filename"
            }
            rows += 1
            for label in all_labels:
                counts[label] += normalized_row.get(label, 0)

            for group_name, labels in groups.items():
                active_count = sum(normalized_row.get(label, 0) for label in labels)
                if active_count == 0:
                    missing[group_name] += 1
                elif active_count > 1:
                    multi[group_name] += 1

    print(f"\n=== {split.upper()} ===")
    print(f"images: {rows}")
    print(f"missing labels: {missing}")
    print(f"multiple labels: {multi}")

    for group_name, labels in groups.items():
        print(f"\n[{group_name}]")
        for label in labels:
            percent = counts[label] / rows * 100 if rows else 0
            print(f"{label}: {counts[label]} ({percent:.2f}%)")


def main():
    for split in ["train", "valid", "test"]:
        count_split(split)


if __name__ == "__main__":
    main()
