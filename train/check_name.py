import csv, re
from pathlib import Path

def base_name(fname: str) -> str:
    # "Aqua_389_jpg.rf.xxxxx.jpg" -> "Aqua_389"
    return re.split(r"_jpg\.rf\.", fname)[0]

def load_bases(csv_path: Path) -> set:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {base_name(row["filename"]) for row in reader}

train_bases = load_bases(Path("car_model_recognition-1/train/_classes.csv"))
valid_bases = load_bases(Path("car_model_recognition-1/valid/_classes.csv"))
test_bases  = load_bases(Path("car_model_recognition-1/test/_classes.csv"))

print("train∩valid:", len(train_bases & valid_bases))
print("train∩test :", len(train_bases & test_bases))
print("valid∩test :", len(valid_bases & test_bases))