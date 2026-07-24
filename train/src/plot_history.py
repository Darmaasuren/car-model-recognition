import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
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
plt.show()

groups = ["model", "color", "type", "view"]

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
    plt.show()
