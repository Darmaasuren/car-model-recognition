# Vehicle Recognition Service

Бие даасан FastAPI service: YOLO detection, plate-to-vehicle matching,
машины model/color/type/view classification, видео/камерын tracking.
Backend-ийн Python код, PostgreSQL, хэрэглэгчийн session-оос хамаарахгүй.

## Бүтэц

```text
recognition_service/
  main.py                 # FastAPI, router бүртгэл, алдааны хариу
  lifespan.py             # Model ачаалах, session manager эхлүүлэх/хаах
  config.py               # Environment болон model/runtime замууд
  media.py                # Зураг decode, хэмжээ шалгах, crop encode
  api/
    security.py           # Дотоод API key шалгалт
    health.py             # Readiness, model metadata
    recognition.py        # Бүтэн зураг, vehicle bbox, plate хүсэлтүүд
    video.py              # Видео upload, session, events, stream
    live.py               # Камерын events, stream, stop
  schemas/
    common.py             # CamelCase API суурь model
    recognition.py        # Bbox, prediction, inference оролт/гаралт
  inference/
    detector.py           # YOLO detect/track
    classifier.py         # Model/color/type/view ангилалт
    pipeline.py           # Crop, ROI, plate matching, track deduplication
  tracking/
    sessions.py           # Frame loop, session, buffer, TTL cleanup
checkpoints/              # Model weights (Git-д орохгүй)
runtime/                  # Түр видео; ажиллах үед үүснэ
tests/                   # API болон tracking session тестүүд
```

Python package нь `recognition_service`: backend-ийн `app` package-тай import
давхцахгүй. `__init__.py` шаардлагагүй namespace package ашиглана.
API → inference/tracking; tracking → inference гэсэн хамааралтай.
Backend-тэй зөвхөн HTTP-ээр холбогдоно. Model weights энд байрлана.

## Ажиллуулах

Root `docker-compose.yaml` backend, worker, recognition, PostgreSQL-ийг хамт асаана.
Зөвхөн recognition service-ийг ажиллуулах бол энэ хавтсанд:

```bash
export API_KEY='replace-with-a-long-random-key'
docker compose -f docker-compose.yaml up -d --build
```

Standalone Compose-ийн service: `http://localhost:8009/api`; OpenAPI: `http://localhost:8009/docs`.
Docker image нь model файлуудаа агуулна. CPU default; CUDA ашиглах бол тохирох
PyTorch build, NVIDIA container runtime болон Compose GPU allocation-ийг тохируулна.
Зөвхөн `MODEL_DEVICE=cuda` тавих нь GPU төхөөрөмжийг container-т дамжуулахгүй.

Docker-гүй, dependencies суусан Python орчинд:

```bash
API_KEY=your-key MODEL_DEVICE=cpu uvicorn recognition_service.main:app --host 127.0.0.1 --port 8009 --workers 1
```

## HTTP API

Health-ээс бусад API хүсэлт бүр `API-Key` header шаарддаг.
Доорх замууд `API_PREFIX`-ийн дараа орно: root Compose болон default нь `/api/v1`, standalone Compose нь `/api`.

| Method / path | Оролт, үр дүн |
|---|---|
| `GET /health` | Model бэлэн бол 200, бэлэн биш бол 503 |
| `GET /metadata` | `modelVersion`, `labelGroups` |
| `POST /inference/image` | Multipart `file`; бүх машины `results`, model metadata |
| `POST /inference/vehicle` | `imageBase64`, `vehicleBbox`, optional `eventId`; зөвхөн classifier |
| `POST /inference/vehicle/upload` | `file`, `vehicle_x1/y1/x2/y2`, optional `event_id` |
| `POST /inference/plate` | `imageBase64`, `plateBbox`, optional `eventId`; detect + match + classify |
| `POST /inference/plate/upload` | `file`, `plate_x1/y1/x2/y2`, optional `event_id` |
| `POST /video/sessions` | Multipart `file`; 201, `sessionId` |
| `GET /video/sessions/{id}/events?after=0` | `events: [{sequence, result}]`, `status`, `error` |
| `GET /video/sessions/{id}/stream` | MJPEG, boundary `frame` |
| `DELETE /video/sessions/{id}` | Зогсоох, түр файл/санах ойг цэвэрлэх |
| `GET /live/cameras/{camera_id}/events?after=0` | Камерын session-ийг эхлүүлж event авна |
| `GET /live/cameras/{camera_id}/stream` | Камерын MJPEG stream |
| `DELETE /live/cameras/{camera_id}` | Камерын session зогсоох |

Bbox нь илгээсэн бүтэн зургийн pixel `x1,y1,x2,y2` координат.
`/vehicle` нь **машины**, `/plate` нь **дугаарын** bbox авдаг.
Хуучин standalone service-ийн `/api` prefix хэрэгтэй бол `API_PREFIX=/api` тохируулна.

```bash
curl http://localhost:8009/api/v1/inference/image \
  -H "API-Key: $API_KEY" -F file=@car.jpg
curl http://localhost:8009/api/v1/video/sessions \
  -H "API-Key: $API_KEY" -F file=@traffic.mp4
```

Зураг 15 MiB / 12 сая pixel, видео 200 MiB / 360 секунд хүртэл.
Service нь зураг танилтын crop-ийг дискэнд хадгалахгүй. Видео/камерын event нь
lossless PNG `cropBase64` агуулна; backend crop хадгална.
Видео түр файлыг recognition service өөрийн runtime-д хадгалж, дуусахад устгана.

## Tracking ба нөөцийн удирдлага

- Session үүсэхэд `pending`; event эсвэл stream уншихад `running` болно.
- Видео/камер бүр өөрийн detector/predictor/tracker-тай; classifier нийтлэг.
- Model inference-ийг lock-оор сериалчилна. Default нь throughput-оос илүү
  isolation, санах ойн хязгаарыг чухалчилсан эхний deployment.
- `MAX_TRACKING_SESSIONS=2`: нийт хадгалж буй session-ийн хязгаар.
  Дууссан session-ээ DELETE хийж slot чөлөөлнө. Дүүрвэл 429; автомат queue байхгүй.
- `SESSION_TTL_SECONDS=600`: event/stream хүсэлтгүй session-ийг зогсоож цэвэрлэнэ.
- Event buffer: хамгийн ихдээ 100 event, 64 MiB. Хэрэглэгчийн cursor хоцорч
  event устсан бол 409 өгнө; үр дүнг чимээгүй алгасахгүй.
- `TRACKING_ROI=0.20,0.60,1.00,0.97`: normalized ROI; бүхэл bbox ROI-д орсон үед ангилна.
- `CAMERA_1_SOURCE`: service-ээс хүрэх боломжтой RTSP/HTTP URL эсвэл camera index.
  Камерын URL-ийг frontend-ээс дур мэдэн хүлээн авахгүй.
- `MODEL_VERSION`: хариу болон backend-ийн түүхэнд хадгалах model release ID.

**Нэг process (`--workers 1`), нэг instance** ашиглана. Session төлөв RAM-д байгаа
учраас restart хийвэл хуучин session алга болно; backend шинэ session үүсгэнэ.
Олон replica болгохоос өмнө session routing/shared job registry шаардлагатай.
Model шинэчилсний дараа service-ийг restart хийнэ.

## Шалгах

Тестийн dependencies: `pip install -r requirements.txt httpx`.
Repository root-оос:

```bash
.venv/bin/python -m unittest discover -s vehicle_recognition_service/tests -v
```

Тестүүд fake detector/classifier ашигладаг тул checkpoint/GPU/гаднын сүлжээ шаардахгүй.

Service startup нь өөрийн runtime дахь өмнөх process-оос үлдсэн UUID нэртэй
түр видео файлуудыг цэвэрлэнэ. Энэ runtime хавтсыг бусад instance-тэй хуваалцахгүй.

### Duplicate vehicle detections

Image detection and tracking restrict YOLO to car/bus/truck and use
class-agnostic NMS with IoU 0.5. Converted vehicle boxes also receive a
confidence-ordered overlap check before classification; invalid boxes are discarded.
This removes highly overlapping detections across classes, not vehicles with
the same model name. Distinct vehicles with IoU above 0.5 may also be suppressed;
check crowded scenes when changing this threshold (`VehicleDetector.duplicate_iou`).

Rebuild the inference service to apply detector changes:

```sh
docker compose -f backend/docker-compose.yaml up -d --build vehicle-bbox-api
```

Run that command from the car_model_recognition repository root.
