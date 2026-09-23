import json
import os
from config import LOG_DIR

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt

history_path = LOG_DIR / "history.json"

with history_path.open("r", encoding="utf-8") as f:
    data = json.load(f)

history = data["history"]
epochs = [item["epoch"] for item in history]

train_loss = [item["train"]["loss"] for item in history]
valid_loss = [item["valid"]["loss"] for item in history]

plt.figure(figsize=(8, 5))
plt.plot(epochs, train_loss, label="train_loss")
plt.plot(epochs, valid_loss, label="valid_loss")
plt.xlabel("Epoch")
plt.ylabel("Loss")
plt.title("Train / Valid Loss")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig(LOG_DIR / "loss_curve.png", dpi=200)
plt.close()

groups = ["model", "color", "type", "view"]

for group in groups:
    metric = f"{group}_loss"
    if not all(metric in item[phase] for item in history for phase in ("train", "valid")):
        continue
    plt.figure(figsize=(8, 5))
    for phase in ("train", "valid"):
        plt.plot(epochs, [item[phase][metric] for item in history], label=phase)
    plt.xlabel("Epoch")
    plt.ylabel("Cross-entropy loss")
    plt.title(f"{group} loss")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(LOG_DIR / f"{group}_loss_curve.png", dpi=200)
    plt.close()

for group in groups:
    train_acc = [item["train"][f"{group}_acc"] for item in history]
    valid_acc = [item["valid"][f"{group}_acc"] for item in history]

    plt.figure(figsize=(8, 5))
    plt.plot(epochs, train_acc, label=f"train_{group}_acc")
    plt.plot(epochs, valid_acc, label=f"valid_{group}_acc")
    plt.xlabel("Epoch")
    plt.ylabel("Accuracy")
    plt.title(f"{group} Accuracy")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(LOG_DIR / f"{group}_accuracy_curve.png", dpi=200)
    plt.close()

# New histories include group and overall macro-F1.
for metric in ["macro_f1"] + [f"{group}_macro_f1" for group in groups]:
    if not all(metric in item[phase] for item in history for phase in ("train", "valid")):
        continue
    plt.figure(figsize=(8, 5))
    for phase in ("train", "valid"):
        plt.plot(epochs, [item[phase][metric] for item in history], label=phase)
    plt.xlabel("Epoch")
    plt.ylabel("Macro-F1")
    plt.ylim(0, 1)
    plt.title(metric)
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(LOG_DIR / f"{metric}_curve.png", dpi=200)
    plt.close()
