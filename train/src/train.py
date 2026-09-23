import json
import random
import time
from typing import Dict

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
    DATA_ROOT,
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
from dataset import CarClassificationDataset, write_model_type_report
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
    if not len(train_dataset) or not len(valid_dataset):
        raise ValueError("Train and valid datasets must contain valid labeled images.")
    train_filters = train_dataset.get_filter_counts()
    valid_filters = valid_dataset.get_filter_counts()
    print(
        "Dataset sizes  "
        f"train={len(train_dataset)} filtered_invalid={train_filters['invalid_labels']} "
        f"filtered_model_type={train_filters['model_type_mismatch']}  "
        f"valid={len(valid_dataset)} filtered_invalid={valid_filters['invalid_labels']} "
        f"filtered_model_type={valid_filters['model_type_mismatch']}"
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

#loss for each label group, ignoring labels with IGNORE_INDEX
def compute_group_losses(
    outputs: Dict[str, torch.Tensor],
    targets: Dict[str, torch.Tensor],
    class_weights: Dict[str, torch.Tensor] | None = None,
) -> Dict[str, torch.Tensor]:
    losses = {}
    class_weights = class_weights or {}
    for group_name, logits in outputs.items():
        group_targets = targets[group_name]
        valid_mask = group_targets != IGNORE_INDEX
        if valid_mask.any():
            losses[group_name] = nn.functional.cross_entropy(
                logits[valid_mask],
                group_targets[valid_mask],
                weight=class_weights.get(group_name),
            )
    return losses


#move targets to the specified device (CPU or GPU)
def move_targets_to_device(targets: Dict[str, torch.Tensor], device: torch.device) -> Dict[str, torch.Tensor]:
    return {group_name: value.to(device) for group_name, value in targets.items()}

def format_metrics(metrics: Dict[str, float], prefix: str) -> str:
    parts = [f"{prefix}_loss={metrics['loss']:.4f}"]
    for name, value in metrics.items():
        if name.endswith(("_loss", "_acc", "_macro_f1")) or name == "macro_f1":
            parts.append(f"{prefix}_{name}={value:.4f}")
    return "  ".join(parts)


def format_epoch_metrics(metrics: Dict[str, float]) -> str:
    parts = [f"loss {metrics['loss']:.4f}"]
    for name, value in metrics.items():
        if name.endswith("_loss"):
            parts.append(f"{name} {value:.4f}")
        elif name.endswith("_acc"):
            group_name = name.removesuffix("_acc")
            parts.append(f"{group_name} {value:.3f}")
        elif name.endswith("_macro_f1") or name == "macro_f1":
            parts.append(f"{name} {value:.4f}")
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
    f1_checkpoint_saved: bool,
    loss_checkpoint_saved: bool,
    best_valid_score: float,
    best_epoch: int,
    epochs_without_improvement: int,
    learning_rate: float,
) -> None:
    print(f"\nEpoch {epoch:02d}/{EPOCHS}")
    print(f"  train | {format_epoch_metrics(train_metrics)}")
    print(f"  valid | {format_epoch_metrics(valid_metrics)} | score {valid_score:.3f} | lr {learning_rate:.2e}")
    if f1_checkpoint_saved:
        print(f"  checkpoint | best_model_v3.pt saved, macro-F1 {best_valid_score:.4f} at epoch {best_epoch:02d}")
    if loss_checkpoint_saved:
        print("  checkpoint | best_loss_model_v3.pt saved, "
              f"validation loss {valid_metrics['loss']:.4f} at epoch {epoch:02d}")
    if not f1_checkpoint_saved:
        if epoch <= FREEZE_BACKBONE_EPOCHS:
            print("  early_stop | paused while backbone is frozen")
        else:
            print(f"  early_stop | no improvement {epochs_without_improvement}/{EARLY_STOP_PATIENCE}")


def set_backbone_trainable(model, trainable: bool) -> None:
    for param in model.backbone.parameters():
        param.requires_grad = trainable
    model.backbone.train(trainable)

def macro_f1_from_confusion(matrix):
    matrix = matrix.float()

    tp = matrix.diag()
    fp = matrix.sum(dim=0) - tp
    fn = matrix.sum(dim=1) - tp

    denominator = 2 * tp + fp + fn
    f1 = torch.where(
        denominator > 0,
        2 * tp / denominator.clamp_min(1),
        torch.zeros_like(tp),
    )
    return f1.mean().item()

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
    on_batch=None,
):
    epoch_start_time = time.perf_counter()
    training = optimizer is not None
    model.train(training)
    if training and freeze_backbone:
        model.backbone.eval()
    total_loss = 0.0
    group_loss_totals = {group_name: 0.0 for group_name in label_groups}
    seen_images = 0
    batch_times = []
    confusions = {
        name: torch.zeros(
            (len(labels), len(labels)),
            dtype=torch.long,
            device=device,
        )
        for name, labels in label_groups.items()
    }
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
            group_losses = compute_group_losses(outputs, targets, class_weights)
            loss = sum(group_losses.values()) if group_losses else next(iter(outputs.values())).sum() * 0

            if training:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()

            batch_size = images.size(0)
            total_loss += loss.item() * batch_size
            for group_name, group_loss in group_losses.items():
                group_loss_totals[group_name] += group_loss.item() * batch_size
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

            for name, labels in label_groups.items():
                valid_mask = targets[name] != IGNORE_INDEX
                true_labels = targets[name][valid_mask]
                predictions = outputs[name].detach().argmax(dim=1)[valid_mask]

                num_classes = len(labels)
                indices = true_labels * num_classes + predictions

                confusions[name] += torch.bincount(
                    indices,
                    minlength=num_classes * num_classes,
                ).reshape(num_classes, num_classes)
            if on_batch is not None:
                on_batch(batch, outputs)

    elapsed_seconds = time.perf_counter() - epoch_start_time
    metrics = {
        "loss": total_loss / len(loader.dataset),
        "elapsed_seconds": elapsed_seconds,
        "avg_batch_seconds": sum(batch_times) / len(batch_times) if batch_times else 0.0,
    }
    for group_name, group_total in group_loss_totals.items():
        metrics[f"{group_name}_loss"] = group_total / len(loader.dataset)
    for name, matrix in confusions.items():
        correct = int(matrix.diag().sum().item())
        total = int(matrix.sum().item())
        metrics[f"{name}_acc"] = correct / total if total else 0.0
    for name, matrix in confusions.items():
        metrics[f"{name}_macro_f1"] = macro_f1_from_confusion(matrix)

    metrics["macro_f1"] = sum(
        metrics[f"{name}_macro_f1"]
        for name in label_groups
    ) / len(label_groups)

    return metrics

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


def save_checkpoint(path, model, label_groups, epoch, valid_metrics, learning_rate, monitor):
    checkpoint = {
        "model_state": model.state_dict(),
        "data_root": str(DATA_ROOT),
        "label_groups": dict(label_groups),
        "epoch": epoch,
        "backbone_name": BACKBONE_NAME,
        "head_dropout": HEAD_DROPOUT,
        "image_size": IMAGE_SIZE[0],
        "freeze_backbone_epochs": FREEZE_BACKBONE_EPOCHS,
        "monitor": monitor,
        "valid_metrics": valid_metrics,
        "valid_score": valid_metrics["macro_f1"],
        "learning_rate": learning_rate,
    }
    if monitor == "valid_macro_f1":
        checkpoint["best_valid_score"] = valid_metrics["macro_f1"]
    else:
        checkpoint["best_valid_loss"] = valid_metrics["loss"]
    torch.save(checkpoint, path)


def save_history(history, best_epoch, best_valid_score, best_loss_epoch, best_valid_loss, stopped_epoch):
    payload = {
        "data_root": str(DATA_ROOT),
        "history": history,
        "early_stopping": {
            "monitor": "valid_macro_f1",
            "mode": "max",
            "patience": EARLY_STOP_PATIENCE,
            "min_delta": EARLY_STOP_MIN_DELTA,
            "best_epoch": best_epoch,
            "best_valid_score": best_valid_score,
            "stopped_epoch": stopped_epoch,
        },
        "best_validation_loss": {
            "epoch": best_loss_epoch,
            "loss": best_valid_loss,
        },
    }
    history_path = LOG_DIR / "history.json"
    temporary_path = LOG_DIR / "history.json.tmp"
    with temporary_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    temporary_path.replace(history_path)

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
def validate(model, loader, device, label_groups, epoch=0, phase="valid", on_batch=None):
    return run_epoch(model, loader, device, label_groups, epoch=epoch, phase=phase, on_batch=on_batch)


def main():
    set_seed(SEED)
    #if GPU is available, use it; otherwise, use CPU
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    #build data loaders for train and validation datasets
    loaders = build_data_loaders()
    label_groups = loaders["train"].dataset.get_label_groups()
    model = build_model(
        label_groups=label_groups,
        backbone_name=BACKBONE_NAME,
        head_dropout=HEAD_DROPOUT,
        pretrained=True,
    ).to(device)

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
    report_path = LOG_DIR / "filtered_model_type_rows.csv"
    write_model_type_report([loaders["train"].dataset, loaders["valid"].dataset], report_path)
    print(f"Model/type mismatches excluded: {report_path}")

    best_valid_score = float("-inf")
    best_valid_loss = float("inf")
    best_epoch = 0
    best_loss_epoch = 0
    epochs_without_improvement = 0
    stopped_epoch = None
    history = []
    for epoch in range(1, EPOCHS + 1):
        if FREEZE_BACKBONE_EPOCHS > 0 and epoch == FREEZE_BACKBONE_EPOCHS + 1:
            set_backbone_trainable(model, True)
            epochs_without_improvement = 0
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
        valid_score = valid_metrics["macro_f1"]
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

        f1_checkpoint_saved = False
        if valid_score > best_valid_score + EARLY_STOP_MIN_DELTA:
            best_valid_score = valid_score
            best_epoch = epoch
            epochs_without_improvement = 0
            f1_checkpoint_saved = True
            save_checkpoint(
                CHECKPOINT_DIR / "best_model_v3.pt", model, label_groups, epoch,
                valid_metrics, epoch_learning_rate, "valid_macro_f1",
            )
        elif epoch > FREEZE_BACKBONE_EPOCHS:
            epochs_without_improvement += 1

        loss_checkpoint_saved = valid_loss < best_valid_loss
        if loss_checkpoint_saved:
            best_valid_loss = valid_loss
            best_loss_epoch = epoch
            save_checkpoint(
                CHECKPOINT_DIR / "best_loss_model_v3.pt", model, label_groups, epoch,
                valid_metrics, epoch_learning_rate, "valid_loss",
            )
        print_epoch_summary(
            epoch=epoch,
            train_metrics=train_metrics,
            valid_metrics=valid_metrics,
            valid_score=valid_score,
            f1_checkpoint_saved=f1_checkpoint_saved,
            loss_checkpoint_saved=loss_checkpoint_saved,
            best_valid_score=best_valid_score,
            best_epoch=best_epoch,
            epochs_without_improvement=epochs_without_improvement,
            learning_rate=epoch_learning_rate,
        )
        if scheduler is not None:
            scheduler.step(valid_loss)
        if epoch > FREEZE_BACKBONE_EPOCHS and epochs_without_improvement >= EARLY_STOP_PATIENCE:
            stopped_epoch = epoch
            print(f"Early stopping at epoch {epoch}. Best epoch: {best_epoch}")
        save_history(
            history, best_epoch, best_valid_score, best_loss_epoch, best_valid_loss, stopped_epoch,
        )
        if stopped_epoch is not None:
            break

    print(f"Best macro-F1 checkpoint: {CHECKPOINT_DIR / 'best_model_v3.pt'}")
    print(f"Best validation-loss checkpoint: {CHECKPOINT_DIR / 'best_loss_model_v3.pt'}")


if __name__ == "__main__":
    main()
