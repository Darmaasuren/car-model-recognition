from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "car_model_recognition-3"

DATA_SPLITS = {
    "train": DATA_ROOT / "train",
    "valid": DATA_ROOT / "valid",
    "test": DATA_ROOT / "test",
}

# All CSV labels used for training are listed here explicitly.
# When a new class is added in Roboflow, add it to the correct group below.
LABEL_GROUPS = {
    "model": [
        "Hyundai Porter",
        "Hyundai Sonata",
        "KIA Bongo3",
        "Lexus HS250h",
        "Lexus RX",
        "Nissan X-Trail",
        "Toyota Harrier",
        "Toyota Alphard",
        "Toyota Aqua",
        "Toyota Camry",
        "Toyota Crown",
        "Toyota Land Cruiser",
        "Toyota Land Cruiser Prado",
        "Toyota Prius",
        "Toyota Prius Alpha",
        "Toyota Sai",
    ],
    "color": [
        "black",
        "blue",
        "brown",
        "gray",
        "red",
        "white",
    ],
    "type": [
        "car",
        "truck",
        "van",
    ],
    "view": [
        "front_side",
        "rear_side",
    ],
}

# Expected type for each model. Keep this rule shared by the label checker and dataset loader.
EXPECTED_TYPES = {
    "Hyundai Porter": "truck",
    "Hyundai Sonata": "car",
    "KIA Bongo3": "truck",
    "Lexus HS250h": "car",
    "Lexus RX": "car",
    "Nissan X-Trail": "car",
    "Toyota Harrier": "car",
    "Toyota Alphard": "van",
    "Toyota Aqua": "car",
    "Toyota Camry": "car",
    "Toyota Crown": "car",
    "Toyota Land Cruiser": "car",
    "Toyota Land Cruiser Prado": "car",
    "Toyota Prius": "car",
    "Toyota Prius Alpha": "car",
    "Toyota Sai": "car",
}

IMAGE_SIZE = (224, 224)
BATCH_SIZE = 16
NUM_WORKERS = 4
SEED = 42
IGNORE_INDEX = -100

BACKBONE_NAME = "resnet50"
LEARNING_RATE = 3e-5
WEIGHT_DECAY = 5e-4
EPOCHS = 100
TRAIN_AUGMENT = True
TRAIN_ROTATION_DEGREES = 5
FILTER_INVALID_LABEL_ROWS = True
FILTER_INCONSISTENT_MODEL_TYPE_ROWS = True

HEAD_DROPOUT = 0.2
FREEZE_BACKBONE_EPOCHS = 10

USE_CLASS_WEIGHTS = False
CLASS_WEIGHT_GROUPS = ["color"]
CLASS_WEIGHT_MAX = 5.0

USE_LR_SCHEDULER = True
LR_SCHEDULER_FACTOR = 0.5
LR_SCHEDULER_PATIENCE = 2
LR_SCHEDULER_MIN_LR = 1e-6

EARLY_STOP_PATIENCE = 5
EARLY_STOP_MIN_DELTA = 1e-4

CHECKPOINT_DIR = PROJECT_ROOT / "checkpoints_retrain_v3"
LOG_DIR = PROJECT_ROOT / "logs_retrain_v3"
