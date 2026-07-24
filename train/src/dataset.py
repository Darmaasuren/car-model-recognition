import csv
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, OrderedDict as OrderedDictType, Tuple

import torch
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms

from config import (
    DATA_SPLITS,
    FILTER_INVALID_LABEL_ROWS,
    IGNORE_INDEX,
    IMAGE_SIZE,
    LABEL_GROUPS,
    TRAIN_ROTATION_DEGREES,
)


LabelGroups = OrderedDictType[str, List[str]]


def normalize_label_name(label: str) -> str:
    return " ".join(label.split())


def get_label_groups() -> LabelGroups:
    return OrderedDict((group_name, list(labels)) for group_name, labels in LABEL_GROUPS.items())

#check config and csv labels match
def validate_csv_labels(csv_path: Path, label_groups: LabelGroups) -> None:
    if not csv_path.exists():
        raise FileNotFoundError(f"Label CSV not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Empty label CSV: {csv_path}")
        csv_labels = {
            normalize_label_name(name)
            for name in reader.fieldnames
            if name != "filename"
        }

    configured_labels = {
        normalize_label_name(label)
        for labels in label_groups.values()
        for label in labels
    }
    missing_in_csv = sorted(configured_labels - csv_labels)
    unknown_in_csv = sorted(csv_labels - configured_labels)

    if missing_in_csv:
        raise ValueError(f"Labels configured but not found in {csv_path}: {missing_in_csv}")
    if unknown_in_csv:
        raise ValueError(f"Labels found in {csv_path} but not configured in LABEL_GROUPS: {unknown_in_csv}")

#read class csv and return image paths and labels
def _label_name_map(label_groups: LabelGroups) -> Dict[str, str]:
    return {
        normalize_label_name(label): label
        for labels in label_groups.values()
        for label in labels
    }


def _read_label_csv(split_path: Path, label_groups: LabelGroups) -> Tuple[List[Path], List[Dict[str, int]]]:
    csv_path = split_path / "_classes.csv"
    label_name_map = _label_name_map(label_groups)
    image_paths: List[Path] = []
    labels: List[Dict[str, int]] = []

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            image_paths.append(split_path / row["filename"])
            normalized_row = {}
            for key, value in row.items():
                if key == "filename":
                    continue
                configured_name = label_name_map[normalize_label_name(key)]
                normalized_row[configured_name] = int(value)
            labels.append(normalized_row)

    return image_paths, labels


def _is_valid_multitask_label(raw_labels: Dict[str, int], label_groups: LabelGroups) -> bool:
    for labels in label_groups.values():
        active_count = sum(raw_labels.get(label, 0) for label in labels)
        if active_count != 1:
            return False
    return True

#get dataset class for car classification
class CarClassificationDataset(Dataset):
    def __init__(self, split: str, augment: bool = False, label_groups: LabelGroups | None = None):
        self.split = split
        self.split_path = DATA_SPLITS[split]
        self.label_groups = label_groups or get_label_groups()
        validate_csv_labels(self.split_path / "_classes.csv", self.label_groups)
        self.image_paths, self.raw_labels = _read_label_csv(self.split_path, self.label_groups)
        self.filtered_rows = 0
        if FILTER_INVALID_LABEL_ROWS:
            valid_items = [
                (image_path, raw_labels)
                for image_path, raw_labels in zip(self.image_paths, self.raw_labels)
                if _is_valid_multitask_label(raw_labels, self.label_groups)
            ]
            self.filtered_rows = len(self.image_paths) - len(valid_items)
            self.image_paths = [image_path for image_path, _ in valid_items]
            self.raw_labels = [raw_labels for _, raw_labels in valid_items]

        self.transform = self._build_transform(augment)

    #processing in image
    def _build_transform(self, augment: bool) -> transforms.Compose:
        transform_list = [transforms.Resize(IMAGE_SIZE)]
        if augment:
            transform_list.extend(
                [
                    transforms.RandomHorizontalFlip(p=0.5),
                    transforms.RandomRotation(degrees=TRAIN_ROTATION_DEGREES),
                ]
            )
        transform_list.extend(
            [
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )
        return transforms.Compose(transform_list)

    #how many images in dataset
    def __len__(self) -> int:
        return len(self.image_paths)

    #every image is processed and returned with its label
    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        #read image and apply transformations
        image = Image.open(self.image_paths[idx]).convert("RGB")
        image = self.transform(image)

        raw = self.raw_labels[idx]
        #target every label group, if multiple labels are active, set to IGNORE_INDEX
        targets = {}
        for group_name, labels in self.label_groups.items():
            active = [label_idx for label_idx, label in enumerate(labels) if raw.get(label, 0) == 1]
            target = active[0] if len(active) == 1 else IGNORE_INDEX
            targets[group_name] = torch.tensor(target, dtype=torch.long)

        return {
            "image": image,
            "targets": targets,
            "filename": self.image_paths[idx].name,
        }

    def get_label_groups(self) -> LabelGroups:
        return self.label_groups

    def get_filtered_rows(self) -> int:
        return self.filtered_rows
