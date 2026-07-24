from collections.abc import Mapping, Sequence
from pathlib import Path

import cv2
import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms


IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


class MultiTaskCarClassifier(nn.Module):
    """The same network structure used by train/src/model.py."""

    def __init__(
        self,
        label_groups: Mapping[str, Sequence[str]],
        backbone_name: str,
        head_dropout: float,
    ):
        super().__init__()
        self.label_groups = {
            group_name: list(labels)
            for group_name, labels in label_groups.items()
        }
        self.head_names = {
            group_name: f"{group_name}_head"
            for group_name in self.label_groups
        }
        self.backbone, feature_dim = self._build_backbone(backbone_name)
        self.dropouts = nn.ModuleDict(
            {
                self.head_names[group_name]: nn.Dropout(p=head_dropout)
                for group_name in self.label_groups
            }
        )
        self.heads = nn.ModuleDict(
            {
                self.head_names[group_name]: nn.Linear(
                    feature_dim,
                    len(group_labels),
                )
                for group_name, group_labels in self.label_groups.items()
            }
        )

    @staticmethod
    def _build_backbone(name: str):
        if name == "efficientnet_b0":
            model = models.efficientnet_b0(weights=None)
            feature_dim = model.classifier[1].in_features
            model.classifier = nn.Identity()
        elif name == "resnet50":
            model = models.resnet50(weights=None)
            feature_dim = model.fc.in_features
            model.fc = nn.Identity()
        else:
            raise ValueError(f"Unsupported classifier backbone: {name}")
        return model, feature_dim

    def forward(self, value: torch.Tensor) -> dict[str, torch.Tensor]:
        features = self.backbone(value)
        return {
            group_name: self.heads[self.head_names[group_name]](
                self.dropouts[self.head_names[group_name]](features)
            )
            for group_name in self.label_groups
        }


class VehicleClassifier:
    def __init__(self, model_path: Path, device: str):
        if not model_path.exists():
            raise FileNotFoundError(f"Classifier model олдсонгүй: {model_path}")

        self.device = self._resolve_device(device)
        checkpoint = self._load_checkpoint(model_path)

        label_groups = checkpoint.get("label_groups")
        state_dict = checkpoint.get("model_state")
        if not label_groups or state_dict is None:
            raise ValueError(
                "Classifier checkpoint нь label_groups болон model_state "
                "талбаруудтай байх ёстой."
            )

        self.label_groups = {
            group_name: list(labels)
            for group_name, labels in label_groups.items()
        }
        backbone_name = checkpoint.get("backbone_name", "efficientnet_b0")
        head_dropout = float(checkpoint.get("head_dropout", 0.2))
        image_size = int(checkpoint.get("image_size", 224))

        self.model = MultiTaskCarClassifier(
            label_groups=self.label_groups,
            backbone_name=backbone_name,
            head_dropout=head_dropout,
        ).to(self.device)
        self.model.load_state_dict(state_dict)
        self.model.eval()

        # This exactly matches train/src/dataset.py for non-augmented inference.
        self.transform = transforms.Compose(
            [
                transforms.Resize((image_size, image_size)),
                transforms.ToTensor(),
                transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
            ]
        )

    @staticmethod
    def _resolve_device(value: str) -> torch.device:
        if value == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if value.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("CUDA сонгосон боловч CUDA ашиглах боломжгүй байна.")
        return torch.device(value)

    def _load_checkpoint(self, path: Path) -> dict:
        try:
            return torch.load(
                path,
                map_location=self.device,
                weights_only=False,
            )
        except TypeError:
            return torch.load(path, map_location=self.device)

    @torch.inference_mode()
    def classify(self, crop_bgr) -> dict[str, dict[str, str | float]]:
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(crop_rgb)
        value = self.transform(image).unsqueeze(0).to(self.device)
        outputs = self.model(value)

        predictions: dict[str, dict[str, str | float]] = {}
        for group_name, logits in outputs.items():
            probabilities = torch.softmax(logits, dim=1)[0]
            index = int(probabilities.argmax().item())
            predictions[group_name] = {
                "label": self.label_groups[group_name][index],
                "confidence": float(probabilities[index].item()),
            }

        return predictions
