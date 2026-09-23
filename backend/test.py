from ultralytics import YOLO

model = YOLO("yolo26s.pt")

model.predict(
    source="video.mp4",
    show=True,
    conf=0.4,
    classes=[1, 3]   # 1=bicycle, 3=motorcycle
)