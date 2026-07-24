import csv
import json
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib
import torch
from torch.utils.data import DataLoader

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import BACKBONE_NAME, BATCH_SIZE, CHECKPOINT_DIR, IGNORE_INDEX, LOG_DIR, NUM_WORKERS
from dataset import CarClassificationDataset, get_label_groups
from model import build_model
from train import format_metrics, validate


def collect_predictions(model, loader, device, label_groups):
    model.eval()
    rows = []
    wrong_rows = []
    confusion = {
        group_name: [[0 for _ in labels] for _ in labels]
        for group_name, labels in label_groups.items()
    }

    with torch.no_grad():
        for batch in loader:
            images = batch["image"].to(device)
            targets = {name: value.to(device) for name, value in batch["targets"].items()}
            outputs = model(images)
            filenames = batch["filename"]

            probabilities = {
                group_name: torch.softmax(logits, dim=1)
                for group_name, logits in outputs.items()
            }
            predictions = {
                group_name: probs.argmax(dim=1)
                for group_name, probs in probabilities.items()
            }
            confidences = {
                group_name: probs.max(dim=1).values
                for group_name, probs in probabilities.items()
            }

            for idx, filename in enumerate(filenames):
                row = {"filename": filename}
                for group_name, labels in label_groups.items():
                    true_idx = int(targets[group_name][idx].item())
                    pred_idx = int(predictions[group_name][idx].item())
                    confidence = float(confidences[group_name][idx].item())
                    pred_label = labels[pred_idx]

                    row[f"pred_{group_name}"] = pred_label
                    row[f"{group_name}_confidence"] = f"{confidence:.6f}"

                    if true_idx == IGNORE_INDEX:
                        row[f"true_{group_name}"] = ""
                        row[f"{group_name}_correct"] = ""
                        continue

                    true_label = labels[true_idx]
                    correct = true_idx == pred_idx
                    row[f"true_{group_name}"] = true_label
                    row[f"{group_name}_correct"] = int(correct)
                    confusion[group_name][true_idx][pred_idx] += 1

                    if not correct:
                        wrong_rows.append(
                            {
                                "filename": filename,
                                "group": group_name,
                                "true_label": true_label,
                                "pred_label": pred_label,
                                "confidence": f"{confidence:.6f}",
                            }
                        )
                rows.append(row)

    return rows, wrong_rows, confusion


def compute_class_metrics(confusion, label_groups):
    all_metrics = {}
    for group_name, matrix in confusion.items():
        labels = label_groups[group_name]
        total = sum(sum(row) for row in matrix)
        group_metrics = {}
        for idx, label in enumerate(labels):
            tp = matrix[idx][idx]
            fp = sum(matrix[row_idx][idx] for row_idx in range(len(labels))) - tp
            fn = sum(matrix[idx]) - tp
            tn = total - tp - fp - fn

            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            accuracy = (tp + tn) / total if total else 0.0

            group_metrics[label] = {
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "accuracy": accuracy,
                "support": sum(matrix[idx]),
            }
        all_metrics[group_name] = group_metrics
    return all_metrics


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_prediction_csv(rows, label_groups):
    fieldnames = ["filename"]
    for group_name in label_groups:
        fieldnames.extend(
            [
                f"true_{group_name}",
                f"pred_{group_name}",
                f"{group_name}_confidence",
                f"{group_name}_correct",
            ]
        )
    write_csv(LOG_DIR / "predictions.csv", rows, fieldnames)


def save_wrong_prediction_csv(rows):
    fieldnames = ["filename", "group", "true_label", "pred_label", "confidence"]
    write_csv(LOG_DIR / "wrong_predictions.csv", rows, fieldnames)


def save_confusion_json(confusion, label_groups):
    payload = {
        group_name: {
            "labels": list(label_groups[group_name]),
            "matrix": matrix,
        }
        for group_name, matrix in confusion.items()
    }
    with (LOG_DIR / "confusion_matrices.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def plot_confusion_matrix(group_name, labels, matrix):
    size = max(6, min(18, len(labels) * 0.7))
    fig, ax = plt.subplots(figsize=(size, size))
    image = ax.imshow(matrix, cmap="Blues")
    ax.set_title(f"{group_name} confusion matrix")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_yticklabels(labels)
    fig.colorbar(image, ax=ax)

    if len(labels) <= 16:
        max_value = max((max(row) for row in matrix), default=0)
        threshold = max_value / 2 if max_value else 0
        for row_idx, row in enumerate(matrix):
            for col_idx, value in enumerate(row):
                if value:
                    color = "white" if value > threshold else "black"
                    ax.text(col_idx, row_idx, str(value), ha="center", va="center", color=color, fontsize=8)

    fig.tight_layout()
    fig.savefig(LOG_DIR / f"confusion_{group_name}.png", dpi=160)
    plt.close(fig)


def plot_class_metrics(group_name, group_metrics):
    labels = list(group_metrics)
    metrics = ["precision", "recall", "f1"]
    x = list(range(len(labels)))
    width = 0.25

    fig_width = max(8, min(18, len(labels) * 0.8))
    fig, ax = plt.subplots(figsize=(fig_width, 6))
    for metric_idx, metric_name in enumerate(metrics):
        offset = (metric_idx - 1) * width
        values = [group_metrics[label][metric_name] for label in labels]
        ax.bar([value + offset for value in x], values, width=width, label=metric_name)

    ax.set_title(f"{group_name} class metrics")
    ax.set_ylabel("Score")
    ax.set_ylim(0, 1)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.legend()
    fig.tight_layout()
    fig.savefig(LOG_DIR / f"class_metrics_{group_name}.png", dpi=160)
    plt.close(fig)


def save_analysis_outputs(rows, wrong_rows, confusion, class_metrics, label_groups):
    save_prediction_csv(rows, label_groups)
    save_wrong_prediction_csv(wrong_rows)
    save_confusion_json(confusion, label_groups)

    with (LOG_DIR / "class_metrics.json").open("w", encoding="utf-8") as f:
        json.dump(class_metrics, f, indent=2)

    for group_name, labels in label_groups.items():
        plot_confusion_matrix(group_name, labels, confusion[group_name])
        plot_class_metrics(group_name, class_metrics[group_name])


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint_path = CHECKPOINT_DIR / "best_model.pt"
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    checkpoint = torch.load(checkpoint_path, map_location=device)
    label_groups = checkpoint.get("label_groups") or get_label_groups()
    backbone_name = checkpoint.get("backbone_name", BACKBONE_NAME)
    head_dropout = checkpoint.get("head_dropout", 0.0)

    test_dataset = CarClassificationDataset("test", augment=False, label_groups=label_groups)
    test_loader = DataLoader(
        test_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=True,
    )

    model = build_model(
        label_groups=label_groups,
        backbone_name=backbone_name,
        head_dropout=head_dropout,
    ).to(device)
    model.load_state_dict(checkpoint["model_state"])

    test_metrics = validate(model, test_loader, device, label_groups)
    rows, wrong_rows, confusion = collect_predictions(model, test_loader, device, label_groups)
    class_metrics = compute_class_metrics(confusion, label_groups)

    LOG_DIR.mkdir(exist_ok=True)
    with (LOG_DIR / "test_metrics.json").open("w", encoding="utf-8") as f:
        json.dump(test_metrics, f, indent=2)
    save_analysis_outputs(rows, wrong_rows, confusion, class_metrics, label_groups)

    print(f"Checkpoint: {checkpoint_path}")
    print(f"Test  {format_metrics(test_metrics, 'test')}")
    print(f"Predictions: {LOG_DIR / 'predictions.csv'}")
    print(f"Wrong predictions: {LOG_DIR / 'wrong_predictions.csv'}")
    print(f"Confusion matrices: {LOG_DIR / 'confusion_matrices.json'}")
    print(f"Class metrics: {LOG_DIR / 'class_metrics.json'}")


if __name__ == "__main__":
    main()
