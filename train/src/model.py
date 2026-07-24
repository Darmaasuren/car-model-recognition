from typing import Dict, Mapping, Sequence

import torch
import torch.nn as nn
from torchvision import models

from config import BACKBONE_NAME, HEAD_DROPOUT

#base model for multi-task class
class MultiTaskCarClassifier(nn.Module):
    #
    def __init__(
        self,
        label_groups: Mapping[str, Sequence[str]],
        backbone_name: str = BACKBONE_NAME,
        head_dropout: float = HEAD_DROPOUT,
        pretrained: bool = True,
    ):
        super().__init__()
        self.backbone_name = backbone_name
        self.head_dropout = head_dropout
        self.label_groups = {group_name: list(labels) for group_name, labels in label_groups.items()}
        self.head_names = {group_name: f"{group_name}_head" for group_name in self.label_groups}
        self.backbone, feature_dim = self._build_backbone(backbone_name, pretrained)
        self.dropouts = nn.ModuleDict(
            {
                self.head_names[group_name]: nn.Dropout(p=head_dropout)
                for group_name in self.label_groups
            }
        )

        #create a linear head for each label group
        self.heads = nn.ModuleDict(
            {
                self.head_names[group_name]: nn.Linear(feature_dim, len(group_labels))
                for group_name, group_labels in self.label_groups.items()
            }
        )

    #build backbone model based on the name provided, either EfficientNet or ResNet
    @staticmethod
    def _build_backbone(name: str, pretrained: bool):
        if name == "efficientnet_b0":
            model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None)
            feature_dim = model.classifier[1].in_features
            #remove the classifier layer to use the backbone as a feature extractor
            model.classifier = nn.Identity()
        elif name == "resnet50":
            model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2 if pretrained else None)
            feature_dim = model.fc.in_features
            model.fc = nn.Identity()
        else:
            raise ValueError(f"Unsupported backbone: {name}")
        return model, feature_dim

    #model prediction
    def forward(self, x):
        features = self.backbone(x)
        return {
            group_name: self.heads[self.head_names[group_name]](
                self.dropouts[self.head_names[group_name]](features)
            )
            for group_name in self.label_groups
        }

#helper function to build the model with specified label groups and backbone
def build_model(
    label_groups: Mapping[str, Sequence[str]],
    backbone_name: str = BACKBONE_NAME,
    head_dropout: float = HEAD_DROPOUT,
    pretrained: bool = True,
) -> MultiTaskCarClassifier:
    return MultiTaskCarClassifier(
        label_groups=label_groups,
        backbone_name=backbone_name,
        head_dropout=head_dropout,
        pretrained=pretrained,
    )
