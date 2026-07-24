import json
import random
import time
from typing import Dict, Mapping, Sequence

import numpy as np
import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torch.utils.data import DataLoader
from tqdm.auto import tqdm

from config import (
    BATCH_SIZE,
    BACKBONE_NAME,
    CHECKPOINT_DIR,
    CLASS_WEIGHT_GROUPS,
    CLASS_WEIGHT_MAX,
    EARLY_STOP_MIN_DELTA,
    EARLY_STOP_PATIENCE,
    EPOCHS,
    FREEZE_BACKBONE_EPOCHS,
    HEAD_DROPOUT,
    IMAGE_SIZE,
    IGNORE_INDEX,
    LEARNING_RATE,
    LOG_DIR,
    LR_SCHEDULER_FACTOR,
    LR_SCHEDULER_MIN_LR,
    LR_SCHEDULER_PATIENCE,
    NUM_WORKERS,
    SEED,
    TRAIN_AUGMENT,
    USE_CLASS_WEIGHTS,
    USE_LR_SCHEDULER,
    WEIGHT_DECAY,
)
from dataset import CarClassificationDataset
from model import build_model


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

#build data loaders for train and validation datasets
def build_data_loaders() -> Dict[str, DataLoader]:
    train_dataset = CarClassificationDataset("train", augment=TRAIN_AUGMENT)
    #read train dataset to get label groups
    label_groups = train_dataset.get_label_groups()
    #get validation dataset with the same label groups
    valid_dataset = CarClassificationDataset("valid", augment=False, label_groups=label_groups)
    print(
        "Dataset sizes  "
        f"train={len(train_dataset)} filtered={train_dataset.get_filtered_rows()}  "
        f"valid={len(valid_dataset)} filtered={valid_dataset.get_filtered_rows()}"
    )

    return {
        "train": DataLoader(
            train_dataset,
            batch_size=BATCH_SIZE,
            shuffle=True,
            num_workers=NUM_WORKERS,
            pin_memory=True,
        ),
        "valid": DataLoader(
            valid_dataset,
            batch_size=BATCH_SIZE,
            shuffle=False,
            num_workers=NUM_WORKERS,
            pin_memory=True,
        ),
    }

#loss function for multi-task classification, ignoring labels with IGNORE_INDEX
def compute_loss(
    outputs: Dict[str, torch.Tensor],
    targets: Dict[str, torch.Tensor],
    class_weights: Dict[str, torch.Tensor] | None = None,
) -> torch.Tensor:
    losses = []
    class_weights = class_weights or {}
    for group_name, logits in outputs.items():
        group_targets = targets[group_name]
        valid_mask = group_targets != IGNORE_INDEX
        if valid_mask.any():
            losses.append(
                nn.functional.cross_entropy(
                    logits[valid_mask],
                    group_targets[valid_mask],
                    weight=class_weights.get(group_name),
                )
            )
    if not losses:
        first_output = next(iter(outputs.values()))
        return first_output.sum() * 0
    return sum(losses)

#accuracy metrics for each label group
def compute_metrics(
    outputs: Dict[str, torch.Tensor],
    targets: Dict[str, torch.Tensor],
    label_groups: Mapping[str, Sequence[str]],
) -> Dict[str, int]:
    metrics = {}
    for group_name in label_groups:
        group_targets = targets[group_name]
        valid_mask = group_targets != IGNORE_INDEX
        total = int(valid_mask.sum().item())
        correct = 0
        if total:
            predictions = outputs[group_name].argmax(dim=1)
            correct = int((predictions[valid_mask] == group_targets[valid_mask]).sum().item())
        metrics[f"{group_name}_correct"] = correct
        metrics[f"{group_name}_total"] = total
    return metrics

#move targets to the specified device (CPU or GPU)
def move_targets_to_device(targets: Dict[str, torch.Tensor], device: torch.device) -> Dict[str, torch.Tensor]:
    return {group_name: value.to(device) for group_name, value in targets.items()}

def format_metrics(metrics: Dict[str, float], prefix: str) -> str:
    parts = [f"{prefix}_loss={metrics['loss']:.4f}"]
    for name, value in metrics.items():
        if name.endswith("_acc"):
            parts.append(f"{prefix}_{name}={value:.4f}")
    return "  ".join(parts)


def format_epoch_metrics(metrics: Dict[str, float]) -> str:
    parts = [f"loss {metrics['loss']:.4f}"]
    for name, value in metrics.items():
        if name.endswith("_acc"):
            group_name = name.removesuffix("_acc")
            parts.append(f"{group_name} {value:.3f}")
    if "elapsed_seconds" in metrics:
        parts.append(f"time {metrics['elapsed_seconds']:.1f}s")
    if "avg_batch_seconds" in metrics:
        parts.append(f"avg_batch {metrics['avg_batch_seconds']:.2f}s")
    return " | ".join(parts)


def print_epoch_summary(
    epoch: int,
    train_metrics: Dict[str, float],
    valid_metrics: Dict[str, float],
    valid_score: float,
    checkpoint_saved: bool,
    best_val_loss: float,
    best_epoch: int,
    epochs_without_improvement: int,
    learning_rate: float,
) -> None:
    print(f"\nEpoch {epoch:02d}/{EPOCHS}")
    print(f"  train | {format_epoch_metrics(train_metrics)}")
    print(f"  valid | {format_epoch_metrics(valid_metrics)} | score {valid_score:.3f} | lr {learning_rate:.2e}")
    if checkpoint_saved:
        print(f"  checkpoint | saved, best valid_loss {best_val_loss:.4f} at epoch {best_epoch:02d}")
    else:
        print(f"  early_stop | no improvement {epochs_without_improvement}/{EARLY_STOP_PATIENCE}")


def set_backbone_trainable(model, trainable: bool) -> None:
    for param in model.backbone.parameters():
        param.requires_grad = trainable
    model.backbone.train(trainable)


#train or validate the model for one epoch, returning metrics
def run_epoch(
    model,
    loader,
    device,
    label_groups,
    optimizer=None,
    epoch=0,
    phase="train",
    class_weights=None,
    freeze_backbone=False,
):
    epoch_start_time = time.perf_counter()
    training = optimizer is not None
    model.train(training)
    if training and freeze_backbone:
        model.backbone.eval()
    total_loss = 0.0
    seen_images = 0
    batch_times = []
    totals = {group_name: {"correct": 0, "total": 0} for group_name in label_groups}
    progress = tqdm(
        loader,
        desc=f"{phase} {epoch:02d}/{EPOCHS}",
        leave=False,
        dynamic_ncols=True,
    )

    with torch.set_grad_enabled(training):
        for batch in progress:
            batch_start_time = time.perf_counter()
            images = batch["image"].to(device)
            targets = move_targets_to_device(batch["targets"], device)
            outputs = model(images)
            loss = compute_loss(outputs, targets, class_weights=class_weights)

            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()

            batch_size = images.size(0)
            total_loss += loss.item() * batch_size
            seen_images += batch_size
            avg_loss = total_loss / max(seen_images, 1)
            batch_time = time.perf_counter() - batch_start_time
            elapsed_time = time.perf_counter() - epoch_start_time
            batch_times.append(batch_time)
            progress.set_postfix(
                loss=f"{avg_loss:.4f}",
                backbone="frozen" if freeze_backbone else "train",
                batch_s=f"{batch_time:.2f}",
                elapsed=f"{elapsed_time:.0f}s",
            )
            batch_metrics = compute_metrics(outputs, targets, label_groups)
            for group_name in label_groups:
                totals[group_name]["correct"] += batch_metrics[f"{group_name}_correct"]
                totals[group_name]["total"] += batch_metrics[f"{group_name}_total"]

    elapsed_seconds = time.perf_counter() - epoch_start_time
    metrics = {
        "loss": total_loss / len(loader.dataset),
        "elapsed_seconds": elapsed_seconds,
        "avg_batch_seconds": sum(batch_times) / len(batch_times) if batch_times else 0.0,
    }
    for group_name, counts in totals.items():
        metrics[f"{group_name}_acc"] = (
            counts["correct"] / counts["total"] if counts["total"] else 0.0
        )
    return metrics

#average accuracy across all label groups for validation scoring
def average_accuracy(metrics: Dict[str, float], label_groups: Mapping[str, Sequence[str]]) -> float:
    accuracies = [metrics[f"{group_name}_acc"] for group_name in label_groups]
    return sum(accuracies) / len(accuracies)


def build_class_weights(train_dataset, label_groups, device) -> Dict[str, torch.Tensor]:
    if not USE_CLASS_WEIGHTS:
        return {}

    weights = {}
    weighted_groups = set(CLASS_WEIGHT_GROUPS)
    for group_name, labels in label_groups.items():
        if group_name not in weighted_groups:
            continue

        counts = torch.zeros(len(labels), dtype=torch.float)
        for raw_labels in train_dataset.raw_labels:
            active = [idx for idx, label in enumerate(labels) if raw_labels.get(label, 0) == 1]
            if len(active) == 1:
                counts[active[0]] += 1

        safe_counts = counts.clamp_min(1.0)
        group_weights = torch.sqrt(safe_counts.sum() / (len(labels) * safe_counts))
        group_weights = group_weights / group_weights.mean()
        group_weights = group_weights.clamp(max=CLASS_WEIGHT_MAX)
        weights[group_name] = group_weights.to(device)

        formatted = ", ".join(
            f"{label}={weight:.2f}"
            for label, weight in zip(labels, group_weights.tolist())
        )
        print(f"{group_name} class weights: {formatted}")

    return weights


def current_learning_rate(optimizer) -> float:
    return optimizer.param_groups[0]["lr"]

#use the train_one_epoch 
def train_one_epoch(model, loader, optimizer, device, label_groups, epoch, class_weights=None):
    return run_epoch(
        model,
        loader,
        device,
        label_groups,
        optimizer=optimizer,
        epoch=epoch,
        phase="train",
        class_weights=class_weights,
        freeze_backbone=epoch <= FREEZE_BACKBONE_EPOCHS,
    )

#use the validate function to evaluate the model on validation or test datasets
def validate(model, loader, device, label_groups, epoch=0, phase="valid"):
    return run_epoch(model, loader, device, label_groups, epoch=epoch, phase=phase)


def main():
    set_seed(SEED)
    #if GPU is available, use it; otherwise, use CPU
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    #build data loaders for train and validation datasets
    loaders = build_data_loaders()
    label_groups = loaders["train"].dataset.get_label_groups()
    #build the multi-task classification
    model = build_model(label_groups=label_groups).to(device)
    if FREEZE_BACKBONE_EPOCHS > 0:
        set_backbone_trainable(model, False)
        print(f"Backbone frozen for first {FREEZE_BACKBONE_EPOCHS} epochs")
    #create an AdamW optimizer
    optimizer = AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
    scheduler = (
        ReduceLROnPlateau(
            optimizer,
            mode="min",
            factor=LR_SCHEDULER_FACTOR,
            patience=LR_SCHEDULER_PATIENCE,
            min_lr=LR_SCHEDULER_MIN_LR,
        )
        if USE_LR_SCHEDULER
        else None
    )
    class_weights = build_class_weights(loaders["train"].dataset, label_groups, device)

    CHECKPOINT_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

    best_val_loss = float("inf")
    best_epoch = 0
    epochs_without_improvement = 0
    stopped_epoch = None
    history = []
    for epoch in range(1, EPOCHS + 1):
        if FREEZE_BACKBONE_EPOCHS > 0 and epoch == FREEZE_BACKBONE_EPOCHS + 1:
            set_backbone_trainable(model, True)
            print(f"Backbone unfrozen after {FREEZE_BACKBONE_EPOCHS} epochs")

        train_metrics = train_one_epoch(
            model,
            loaders["train"],
            optimizer,
            device,
            label_groups,
            epoch,
            class_weights=class_weights,
        )
        valid_metrics = validate(model, loaders["valid"], device, label_groups, epoch=epoch, phase="valid")
        valid_score = average_accuracy(valid_metrics, label_groups)
        valid_loss = valid_metrics["loss"]
        epoch_learning_rate = current_learning_rate(optimizer)
        history.append(
            {
                "epoch": epoch,
                "train": train_metrics,
                "valid": valid_metrics,
                "valid_score": valid_score,
                "learning_rate": epoch_learning_rate,
            }
        )

        checkpoint_saved = False
        if valid_loss < best_val_loss - EARLY_STOP_MIN_DELTA:
            best_val_loss = valid_loss
            best_epoch = epoch
            epochs_without_improvement = 0
            checkpoint_saved = True
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "label_groups": dict(label_groups),
                    "epoch": epoch,
                    "backbone_name": BACKBONE_NAME,
                    "head_dropout": HEAD_DROPOUT,
                    "image_size": IMAGE_SIZE[0],
                    "freeze_backbone_epochs": FREEZE_BACKBONE_EPOCHS,
                    "monitor": "valid_loss",
                    "best_valid_loss": best_val_loss,
                    "valid_metrics": valid_metrics,
                    "valid_score": valid_score,
                    "learning_rate": epoch_learning_rate,
                },
                CHECKPOINT_DIR / "best_model.pt",
            )
        else:
            epochs_without_improvement += 1
        print_epoch_summary(
            epoch=epoch,
            train_metrics=train_metrics,
            valid_metrics=valid_metrics,
            valid_score=valid_score,
            checkpoint_saved=checkpoint_saved,
            best_val_loss=best_val_loss,
            best_epoch=best_epoch,
            epochs_without_improvement=epochs_without_improvement,
            learning_rate=epoch_learning_rate,
        )
        if scheduler is not None:
            scheduler.step(valid_loss)
        if not checkpoint_saved:
            if epochs_without_improvement >= EARLY_STOP_PATIENCE:
                stopped_epoch = epoch
                print(f"Early stopping at epoch {epoch}. Best epoch: {best_epoch}")
                break

    with (LOG_DIR / "history.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "history": history,
                "early_stopping": {
                    "monitor": "valid_loss",
                    "mode": "min",
                    "patience": EARLY_STOP_PATIENCE,
                    "min_delta": EARLY_STOP_MIN_DELTA,
                    "best_epoch": best_epoch,
                    "best_valid_loss": best_val_loss,
                    "stopped_epoch": stopped_epoch,
                },
            },
            f,
            indent=2,
        )

    print(f"Best checkpoint: {CHECKPOINT_DIR / 'best_model.pt'}")


if __name__ == "__main__":
    main()
