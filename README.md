# Тээврийн хэрэгсэл таних систем

Recognition service нь бүх detect, classification, видео/камерын tracking-ийг
хийдэг. Backend болон worker model ачаалахгүй, HTTP API-аар service-ийг дуудна.
Frontend-ийн одоогийн endpoint болон event формат хэвээр.

```text
frontend → backend → vehicle_recognition_service
              ↓               ↓
          PostgreSQL     YOLO + classifier + tracker
              ↑
            worker → vehicle_recognition_service
```

## Кодын бүтэц

```text
backend/app/
  main.py                      # FastAPI router/middleware бүртгэл
  lifespan.py                  # DB, client, service lifecycle
  worker.py                    # Автомат worker-ийн эхлэх цэг
  api/
    auth.py                    # Login, logout, me
    health.py                  # Recognition readiness
    recognition.py             # Зураг, vehicle bbox, plate bbox
    video.py                   # Видео session, stream, WebSocket
    live.py                    # Камерын stream, WebSocket
    comparison.py              # Харьцуулалт, түүх, worker төлөв
  core/                        # Config, database, passwords, API-key security
  middleware/auth.py           # Session, Basic Auth, Origin хамгаалалт
  commands/init_db.py           # DB/admin бэлтгэх команд
  models/
    user.py                    # User, login session
    video_session.py           # Видео session-ийн эзэмшигч
    recognition.py             # Харьцуулалтын үр дүнгийн хүснэгт
    source_token.py             # Гаднын service token
    sync_state.py               # Worker-ийн явц
  schemas/
    common.py                  # ApiModel, camelCase JSON
    auth.py                    # Хэрэглэгчийн хариу
    recognition.py             # Bbox, prediction, recognition response
    video.py                   # Video session/event/status
    comparison.py              # Comparison/history/worker response
  services/
    auth.py                    # Login logic, анхны admin
    media.py                   # Upload, decode/encode, crop хадгалалт
    recognition/
      client.py                # Зөвхөн HTTP transport
      results.py               # Prediction validation, crop, result cache
      video.py                 # Remote session + DB ownership
    comparison/
      auth.py                  # Гаднын service-ийн token lifecycle
      source.py                # Бүртгэл болон зураг татах
      compare.py               # Бүртгэлтэй харьцуулах дүрэм
      store.py                 # DB хадгалалт, түүх, worker status
      poller.py                # Давтамж, retry, pending records
vehicle_recognition_service/    # YOLO, classifier, tracking — тусдаа service
frontend/                      # React интерфейс
train/                         # Model сургах код
```

Зураг таних урсгал: `api/recognition.py` → `services/recognition/results.py`
→ `services/recognition/client.py` → recognition service. `results.py` нь хариуг
шалгаж `media.py`-гаар crop хадгална; HTTP client нь файл хадгалах/DB логикгүй.

Харьцуулалтын урсгал: `comparison/source.py` → `comparison/compare.py`
→ recognition results → `comparison/store.py`. `comparison/auth.py` нь гаднын
системийн token-ийг, `services/auth.py` нь хэрэглэгчийн нэвтрэлтийг удирдана.

Файлын байрлал өөрчлөгдсөн ч public URL, хүсэлтийн бүтэц болон DB хүснэгтийн нэрүүд
хэвээр. `schemas/comparison.py` хариуг баримтжуулж, өгөөгүй optional талбарыг JSON-д
нэмэхгүй. `live_manager.py` зэрэг дан дамжуулах wrapper байхгүй.

Backend дээр OpenCV нь зураг decode/encode, crop хадгалахад үлдсэн. YOLO, PyTorch, classifier, frame tracking энд байхгүй.
`__init__.py` нэмээгүй; existing namespace-package бүтэц ашиглана.

## Хамт ажиллуулах

Root `.env` дотор дор хаяж:

```dotenv
API_PREFIX=/api/v1
API_KEY=replace-with-a-long-random-key
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
DB_HOST=postgres
DB_PORT=5432
DB_USER=vehicle_app
DB_PASSWORD=replace-with-a-database-password
DB_NAME=vehicle_recognition
POSTGRES_USER=vehicle_app
POSTGRES_PASSWORD=replace-with-a-database-password
POSTGRES_DB=vehicle_recognition
# Local HTTP development only; HTTPS production-д true.
COOKIE_SECURE=false
ADMIN_USERNAME=admin
ADMIN_PASSWORD=replace-with-an-admin-password
```

DB болон POSTGRES нэр/нууц үгүүд таарах ёстой. Байгаа PostgreSQL volume-ийн
нууц үгийг `.env` засах төдийд өөрчлөхгүй. Нууцуудаа Git-д оруулахгүй.

Optional тохиргоо:

```dotenv
RECOGNITION_API_KEY=separate-internal-key
MODEL_DEVICE=cpu
MODEL_VERSION=best_loss_model_v3
MAX_TRACKING_SESSIONS=2
MEDIA_ROOT=/mnt/data/car_model_img
CAMERA_1_SOURCE=
```

`RECOGNITION_API_KEY` байхгүй бол Compose нь `API_KEY`-г ашиглана.
Model weights: `vehicle_recognition_service/checkpoints/best_loss_model_v3.pt`,
`vehicle_recognition_service/checkpoints/yolo11s.pt`.

```bash
docker compose up -d --build
cd frontend
npm ci
npm run dev
```

Backend: `http://localhost:8008`; recognition service нь root Compose-д дотоод
сүлжээнд `http://recognition:8000/api/v1` хаягаар ажиллана.
Backend, worker ижил `MEDIA_ROOT` mount ашиглана. Recognition service өөрийн
түр storage-тай; backend-ийн локал замыг уншихгүй.

Тусад нь recognition service гаргах, API contract, tracking-ийн хязгаарууд:
[vehicle_recognition_service/README.md](vehicle_recognition_service/README.md).
Backend-ийг Docker-гүй ажиллуулах бол `RECOGNITION_URL=http://localhost:8009/api/v1`,
`RECOGNITION_API_KEY`, DB болон API тохиргоонуудаа environment-д экспортлоод
`backend/` дотроос `uvicorn app.main:app --port 8008` ажиллуулна.
`.env` файлыг Python өөрөө автоматаар уншихгүй.

## Шилжилтийн тэмдэглэл

- `vehicle_bbox_api/` → `vehicle_recognition_service/` болсон.
- Backend-ийн public `/inference/vehicle` нь plate bbox хэвээр;
  standalone service-ийн `/inference/plate` руу дамжуулна.
- Backend-ийн `/inference/vehicle-bbox` нь standalone `/inference/vehicle` руу дамжуулна.
- Координатгүй бүтэн зураг: standalone `/inference/image` шинээр нэмэгдсэн.
- Видео файлыг service рүү нэг удаа дамжуулна. Frame loop, YOLO tracking, ROI,
  classifier бүгд service дотор. Backend event-ийг авч crop хадгална.
- `recognition_sessions` шинэ хүснэгт видео session-ийг үүсгэсэн хэрэглэгчтэй холбоно.
  Startup дээр хүснэгт үүснэ; хуучин хүснэгтүүдийг устгахгүй.
- Видео session-ийг эзэмшигч нь унших/зогсоох боломжтой. Камер нь өмнөх шиг
  нэвтэрсэн хэрэглэгчдийн хамтын stream байна.
- Session-үүд restart хооронд сэргээгдэхгүй. Нэг recognition instance, нэг worker
  process ашиглана; concurrency/TTL/429/409-ийн тайлбарыг service README-ээс үзнэ үү.
- Worker/API хоёр model ачаалахгүй. Хуучин `backend/checkpoints/` файлуудыг
  автоматаар устгаагүй, backend Docker build-д оруулахгүй.
- Worker өмнө өөр `/mnt/data/car_model_imgs` хавтаст зураг хадгалсан бол түүхийн
  зургуудыг сонгосон `MEDIA_ROOT` руу нүүлгэх шаардлагатай; энэ өөрчлөлт өөрөө нүүлгэхгүй.

## Шалгалт

Backend болон тестийн dependency-уудыг `backend/requirements.txt`-аар суулгана.

```bash
.venv/bin/python -m unittest discover -s backend/tests -v
.venv/bin/python -m unittest discover -s vehicle_recognition_service/tests -v
cd frontend
npm run build
npm run lint
node --test tests/*.test.cjs
```

## Username/password нэвтрэлт, PostgreSQL

`POST /auth/login` (API prefix-ийн дор) нь `Authorization: Basic <base64(username:password)>`
header-аар UTF-8 нэвтрэх мэдээлэл авна; JSON body ашиглахгүй. Амжилттай нэвтэрсний
дараа HttpOnly session cookie үүсгэж, дараагийн хүсэлтүүд cookie ашиглана.
Basic мэдээлэл байхгүй эсвэл буруу бол `401` болон `WWW-Authenticate: Basic` буцаана.
Production орчинд HTTPS ашиглана.

Скриптээс зураг болон хамгаалагдсан HTTP API татахад login эсвэл session cookie
шаардлагагүй: хүсэлт бүрд `Authorization: Basic <base64(username:password)>` илгээнэ.
Жишээ: `curl -u USERNAME http://localhost:5173/media/crop/IMAGE.jpg -o IMAGE.jpg`
(`curl` нууц үгийг асууна). Origin header шаардлагагүй. Вебийн session нэвтрэлт
мөн ажиллана; `API-Key` ашигладаг service endpoint-уудын хамгаалалт хэвээр.

Auth нь SQLAlchemy `User`, `Session` model, Argon2id password hash болон
HttpOnly session cookie ашиглана. Alembic байхгүй. Backend эхлэхэд байхгүй
хүснэгтүүдийг үүсгэнэ. `ADMIN_USERNAME`, `ADMIN_PASSWORD` тохируулсан бол
backend анх асахдаа admin хэрэглэгч автоматаар үүсгэнэ. Хоёуланг нь
тохируулаагүй бол хэрэглэгч үүсгэхгүй; зөвхөн нэгийг өгвөл startup алдаа гарна.
Байгаа хэрэглэгчийн password болон role-ийг өөрчлөхгүй.
Compose-ийн backend.environment хэсэгт эдгээр утгыг шууд өгч болно, эсвэл
одоогийн compose-ийн хувьсагчаар `.env`-ээс өгнө. Нууц үгийг repository-д commit хийхгүй.
`app/commands/init_db.py` командаар мөн admin хэрэглэгч үүсгэж болно. Аль аль нь
байгаа хүснэгтийн багануудыг өөрчлөхгүй.

### Эхний тохиргоо

Backend, auth болон PostgreSQL-ийн тохиргоонууд төслийн үндсэн `.env`
файлд байрлана. Compose-ийн хоёр service `env_file: [.env]` ашиглаж уншина.
Шинээр суулгахад үндсэн `.env` файлд тохиргоонуудаа оруулна.
`DB_USER`, `DB_PASSWORD`, `DB_NAME`-ийг нэг удаа заана; `POSTGRES_*` утгууд
тэдгээрийг ашиглана. Service token мөн үндсэн `.env` файлд хадгалагдана. `frontend/.env`
нь frontend тохиргоонд зориулагдсан.

```bash
sudo docker compose up -d postgres
sudo docker compose build backend
sudo docker compose up -d backend
sudo docker compose run --rm backend python -m app.commands.init_db
```

`app/commands/init_db.py` username, password асууж admin үүсгэнэ. Password оруулах үед
terminal дээр энгийн текстээр харагдана, database-д Argon2id hash хэлбэрээр
хадгалагдана. Username болон password-д тэмдэгтийн төрлийн эсвэл уртын хатуу
хязгаар тавиагүй, хоосон байж болохгүй. Байгаа хэрэглэгчийг
дарж өөрчлөхгүй. Шинэ admin үүсгэхэд command-ийг дахин ажиллуулж болно.
DB schema өөрчлөгдвөл өгөгдөлтэй хүснэгтүүдийг устгалгүй SQL өөрчлөлт хийнэ.

Frontend-ийн `frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8008/api/
VITE_WS_BASE_URL=ws://localhost:8008/api/
VITE_CAMERA_ID=camera-1
```

```bash
cd frontend
npm install
npm run dev
```

Browser-оор `http://localhost:5173/login` нээнэ. Frontend болон backend дээр
`localhost`/`127.0.0.1`-ийг хольж ашиглахгүй. Login нь backend model
ачаалагдаагүй байсан ч ажиллана; inference тэр үед 503 буцаана.

### Cookie ба хандалт

- Локал HTTP-д `COOKIE_SECURE=false`; HTTPS орчинд `true`.
- SameSite=Lax cookie тул нэг site-ийн frontend/backend ашиглана. Хоёр
  хамааралгүй домэйны cross-site cookie deployment энэ тохиргоонд дэмжигдэхгүй.
- `CORS_ORIGINS` нь frontend-ийн яг origin-ууд байна. Browser-ийн өөрчлөлт
  хийх хүсэлт, login/logout болон WebSocket-д итгэмжлэгдсэн Origin шаарддаг.
- Зураг, видео, live, `/media/crops` нь session-оор хамгаалагдана. Эдгээр нь
  нэвтэрсэн багийн хэрэглэгчдэд хамт нээлттэй; хэрэглэгч тус бүрийн media
  ownership энэ эхний хувилбарт байхгүй.
- `/vehicle`, `/vehicle/upload` service endpoint-ууд `API-Key` хамгаалалтаа
  хадгална. Service token-ийг frontend-д дамжуулахгүй.
- Role хадгалагдана, одоогийн танилтын дэлгэц бүх идэвхтэй хэрэглэгчид нээлттэй.
- Login оролдлого IP бүрд 5 минутанд 10; limiter нэг процессын RAM-д байна.
  Одоогийн 1 worker deployment-д зориулсан. Олон replica-д shared limiter хэрэгтэй.
- Stream илгээх үед session-ийг 5 секунд тутам дахин шалгана; frontend idle
  session-ийг минут тутам шалгана. Logout нь database session-ийг устгана.
- Одоогийн `compare_service.py`-ийн `/inference/image` хүсэлт одоо session
  шаарддаг. Автомат service polling integration дараагийн шатны ажил.

PostgreSQL container-ийн `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
нь зөвхөн хоосон volume дээр database анх үүсэхдээ хэрэглэгдэнэ. Password-ийг
`.env` дотор солих нь байгаа database
хэрэглэгчийн password-ийг өөрчлөхгүй. `docker compose down -v` нь хадгалсан
өгөгдлийг устгана.
Backend шинэчлэхдээ `docker compose up -d --build backend` ашиглана.

### Шалгалт

```bash
.venv/bin/python -m unittest discover -s backend/tests -v
cd frontend
npm run build
npm run lint
```

Auth тестүүд SQLite fixture дээр ажиллана; PostgreSQL deployment-ийн
холболт, initialization-ийг дээрх Compose урсгалаар тусад нь шалгана.

### Backend кодын бүтэц

- `app/main.py`: FastAPI, router болон middleware бүртгэл.
- `app/lifespan.py`: database болон recognition HTTP client эхлүүлэх, холболт хаах.
- `app/core/`: тохиргоо, database холболт, password hash, API key шалгалт.
- `app/models/`: SQLAlchemy User, Session хүснэгтүүд.
- `app/schemas/`: нийтлэг, нэвтрэлт, танилтын request/response бүтэц.
- `app/middleware/`: session болон Origin шалгалт.
- `app/api/`: HTTP, WebSocket endpoint-ууд.
- `app/services/`: танилт болон нэвтрэлтийн үндсэн логик.
- `app/commands/`: admin үүсгэх команд.

`__init__.py` ашиглахгүй. Импортууд `app.`-аар эхэлнэ.
Docker-гүй ажиллуулахдаа шаардлагатай environment утгуудыг өгөөд `backend/`
хавтаснаас `uvicorn app.main:app --host 0.0.0.0 --port 8000` ажиллуулна.

### Service-ийн 20 машиныг харьцуулах

Үндсэн `.env` файлд `SERVICE_URL`, `SERVICE_METHOD`,
`IMAGE_BASE_URL` болон дараах нэвтрэх тохиргоог өгнө:

```dotenv
SERVICE_LOGIN_URL=https://traffic-police.odt.mn/api/user/login
SERVICE_USERNAME=
SERVICE_PASSWORD=
SERVICE_PASSWORD_SHA256=
```

Нэвтрэх утгуудыг өөрөө оруулна. `SERVICE_PASSWORD` нь login JSON-ийн
`password` талбарт, `SERVICE_PASSWORD_SHA256` нь `sha256` талбарт тус тус
дамжина. Эдгээр нь тусдаа утгууд бөгөөд код дахин хэшлэхгүй.
Backend API нь хуучин `SERVICE_TOKEN` тохиргооны оронд автоматаар login хийнэ.
Эхний Service хүсэлт дээр token авч, PostgreSQL-ийн `service_tokens` хүснэгтэд
token болон дуусах хугацааг хадгална. Энэ token нь дахин ашиглах шаардлагатай
тул хэрэглэгчийн session шиг нэг чиглэлийн хэш биш, буцааж унших утга байна;
database болон backup-д хандах эрхийг хязгаарлана. Token frontend болон логт гарахгүй.

Дараагийн хүсэлтүүд token-ийг database-аас уншина; JWT-ийн `exp` хүртэл
60 секундээс бага үлдвэл дахин login хийнэ. `exp` байхгүй зөв бүтэцтэй JWT-д
нэг өдрийн хугацаа хэрэглэнэ. Энэ нь хүсэлт ирэхэд шалгах ажиллагаа бөгөөд
Service дуудахгүй үед login хийхгүй. `401` үед нэг удаа шинэчлээд хүсэлтийг
давтана. Зэрэг хүсэлтүүдийн шинэчлэлтийг PostgreSQL transaction lock-оор
нэгтгэнэ. Backend дахин ассан ч хадгалсан хүчинтэй token-оо ашиглана.
Хүснэгт backend асахад автоматаар үүснэ. Тохиргоо өөрчилсний дараа Docker
контейнерийг дахин үүсгэнэ: `docker compose up -d --build backend`.
Тусдаа `compare_service.py` скриптийн гараар token авах ажиллагаа хэвээр.

Service-ийн query эсвэл body шаардлагатай бол
`SERVICE_PARAMS_JSON`, `SERVICE_BODY_JSON`-ийг JSON объект хэлбэрээр өгнө.

Нэвтэрсний дараа **Service харьцуулах** хуудасны **20 машин шалгах** товчийг
дарна. Backend `POST /api/service/compare-batch` хүсэлтээр service-ийн
`items` жагсаалтын эхний 20 record-ийг авч, тус бүрийн `full_photo` зургийг
recognition service рүү өгнө. Frontend дөрвөн танилт (model, color,
type, view) болон confidence-ийг машин бүр дээр харуулна. Service-тэй
нэршил нь таарсан model, color, type-ийг 90%-ийн confidence босгоор
харьцуулна. Type-ийн нэршил таарахгүй эсвэл view-ийн эх утга байхгүй бол
таамгаар тохирсон гэж үзэхгүй. Нэг зурагт олон машин илэрвэл model танилтын
confidence хамгийн өндөр машиныг сонгож, тэр машины model, color, type, view
үр дүнг ашиглана. Машин илрээгүй бол `NO_VEHICLE_DETECTED` гэж харуулна.
Нэг record-ийн зураг алдаатай байсан ч
бусад record-ийг үргэлжлүүлэн боловсруулна. Бүтэн зургийн хуулбар `runtime/full_photo`-д, crop нь `runtime/crops`-д
хадгалагдана; харьцуулалтын metadata-г PostgreSQL-д бичнэ.

### Service харьцуулалтын database хадгалалт

`POST /api/service/compare-batch` (20 бичлэг), мөн `compare-next` нь
`vehicle_recognitions` хүснэгтэд мэдээлэл хадгална. Backend болон worker эхлэхэд
Alembic migration-уудыг PostgreSQL lock ашиглан дарааллаар ажиллуулна. Эхний
migration нь нийцтэй хуучин schema-г өгөгдөл устгахгүйгээр хувилбаржуулж, дараагийн
migration нь `seatbelt_result` багана байхгүй бол нэмнэ. Дэлгэрэнгүй: [Migration заавар](backend/migrations/README.md),
[төвлөрсөн тохиргоо](backend/CONFIGURATION.md).

- Бүх зөв форматтай эх бичлэгийг зураг татахаас өмнө `pending` төлөвөөр хадгална.
- Service-ийн `_id` нь `source_record_id` гэсэн давтагдахгүй түлхүүр болно.
  Ижил бичлэгийг дахин шалгахад нэг мөрөнд хамгийн сүүлийн үр дүнг шинэчилнэ.
  Улсын дугаар, огноо, марк, модель, өнгө, төрөл, `full_photo` замыг тусдаа
  баганад хадгална; давхар `source_payload` хадгалахгүй.
- `processing` → `completed` / `failed` төлөв, оролдлогын тоо, алдаа, эхэлсэн
  болон дууссан хугацааг хадгална. Танилтын алдаа нь дараагийн бичлэгийг зогсоохгүй.
  Database алдаа гарвал API 503 буцаана; хадгалаагүй үр дүнг амжилттай гэж буцаахгүй.
- `prediction`, `comparison`, `vehicle_bbox` нь PostgreSQL JSONB.
  Машины bbox эх зургийн pixel xyxy координаттай.
- Seatbelt integration хасагдсан. Шинэ хүсэлтээр бүс шалгахгүй, API/UI-д талбар
  гаргахгүй. Өмнөх DB-ийн `seatbelt_result` багана, түүхэн өгөгдлийг хадгалсан.
- Бүтэн зураг runtime/full_photo дотор файл хэлбэрээр, харьцангуй зам болон эх зургийн хэмжээ
  database-д хадгалагдана. `model_version` нь recognition service-ийн `MODEL_VERSION` утга
  бөгөөд агуулгын hash биш; ижил нэртэй checkpoint соливол хувилбарыг ялгахгүй.

Хадгалалтын тестүүд SQLite дээр transaction, давхардал, алдаа, bbox-ийг шалгана;
бодит PostgreSQL болон гаднын service-ийн integration шалгалтыг орлохгүй.


Service харьцуулалтын хуудас нээгдэхэд `GET /api/service/comparisons?offset=0&limit=20`
API-аас хадгалсан бичлэгүүдийг уншина. Энэ API-ийн offset нь алгасах **мөрийн тоо**
(0, 20, 40), гаднын service-ийн хуудасны index-ээс ялгаатай. Limit нь 1–100.
Сүүлийн боловсруулж эхэлсэн (эхлээгүй бол татсан) хугацаагаар буурахаар эрэмбэлнэ.
API нь session хамгаалалттай, танилтын моделийг дуудахгүй. Frontend дээр өмнөх/дараах хуудас, хуудасны хэмжээ сонгох боломжтой.
Хадгалсан үр дүнг автоматаар шинэчилнэ.
Өмнөх зургийн файл байхгүй бол imageUrl хоосон буцааж, текстэн үр дүнг харуулна.

### Автомат service worker

`worker` container нь `python -m app.worker` командаар ажиллана. Browser хаалттай
байсан ч үргэлжилнэ. Frontend үр дүн, worker-ийн төлөвийг 5 секунд тутам манай
backend-ээс уншина; энэ нь гаднын service рүү хүсэлт явуулахгүй.

```bash
sudo docker compose up -d --build backend worker
sudo docker compose logs --tail=100 worker
```

- Service-ийн жагсаалт руу **20 минут тутам хамгийн ихдээ нэг хүсэлт** явуулна:
  `offset: 0, limit: 20`. Огноогоор шүүхгүй; request body болон query params дахь
  `startDate`/`endDate`-ийг автоматаар хасна. Бусад filter хэвээр үлдэнэ.
- Мөчлөг бүр эхний хуудсыг авна; offset ахиулахгүй. Хамгийн шинэ бичлэгүүд ирэх
  эсэх нь service-ийн эрэмбэлэлтээс хамаарна. Завсрын бүх бичлэгийг нөхөж авахгүй.
- Хүсэлтийн дараагийн хугацааг network I/O-оос өмнө database-д хадгална. Restart
  хийсэн ч хүсэлтийн зайг барина. Өмнөх боловсруулалт дуусаагүй бол давхар эхлэхгүй.
- Хуучин огноо/offset-той worker-оос шинэ хувилбарт анх шилжихэд cursor-ийг цэвэрлэж,
  эхний хүсэлтийг дор хаяж 20 минутын дараа товлоно. Хадгалсан үр дүнг устгахгүй.
  Цоо шинэ database дээр эхний хүсэлт worker бэлэн болмогц явна.
- Давхардсан `_id` шинээр нэмэгдэхгүй, `completed` бичлэгийг дахин танихгүй.
  Зургийг нэг нэгээр татаж таньж, бичлэгүүдийн хооронд 2 секунд хүлээнэ. Зураг
  таталт, token login/refresh нь жагсаалтын хүсэлтээс тусдаа HTTP хүсэлтүүд.
- Алдаатай зурагт нийт 3 хүртэл оролдлого, оролдлого хооронд дор хаяж 30 минут.
  Timeout/5xx үед 20, дараа нь 40 минут хүлээнэ. Retry-After урт бол түүнийг дагана.
  Зургийн 429/503 үед түр хүлээлгэнэ. 403 үед blocked төлөвөөр зогсоож харуулна.
  401 үед token шинэчилж, жагсаалтын хүсэлтийг дараагийн мөчлөгт давтана.
- PostgreSQL advisory lock нь нэг worker ажиллуулна. Тасарсан processing ажлыг
  restart дээр сэргээнэ. Database/моделийн ноцтой алдаагаар процесс зогсвол Docker
  дахин асаана. Локал inference-д хатуу хугацааны хязгаар энэ шатанд байхгүй.
- Compose backend-ийн `SERVICE_WORKER_ENABLED=true` нь гар ажиллагааны compare
  endpoint-уудыг 409 хариугаар хаана. Docker-гүй ажиллуулахад мөн тохируулна.
- Зургууд `backend/runtime` bind mount-д хадгалагдана. Автомат цэвэрлэгээ нэмээгүй.

Blocked шалтгааныг зассаны дараа `docker compose restart worker` хийнэ. Эх үүсвэрийн
URL/method/filter өөрчлөгдвөл хадгалсан config fingerprint-ийг шалгаж удирдана.

### Vehicle bbox-оор шууд classifier дуудах API

Өөр project-оос **бүтэн зураг + нэг машины bbox** илгээнэ. Энэ урсгал detector,
автомат worker дуудахгүй; database болон runtime хавтаст зураг,
үр дүн хадгалахгүй. Backend энэ хүсэлтийг recognition service-ийн
`/inference/vehicle` endpoint рүү дамжуулна; service ажиллаж байх шаардлагатай.

Хоёр endpoint нь `API-Key` header шаарддаг. Cookie/session login, Origin header
шаардахгүй. Доорх `/api`-г өөрийн `API_PREFIX`-тэй тааруулна.

`POST /api/inference/vehicle-bbox` — application/json:

```json
{
  "eventId": "event-123",
  "imageBase64": "<base64 эсвэл data:image/png;base64,...>",
  "vehicleBbox": {"x1": 100, "y1": 80, "x2": 700, "y2": 500}
}
```

`POST /api/inference/vehicle-bbox/upload` — multipart/form-data:

```bash
curl -X POST http://localhost:8008/api/inference/vehicle-bbox/upload \
  -H "API-Key: <your-api-key>" \
  -F "file=@car.jpg" \
  -F "event_id=event-123" \
  -F "vehicle_x1=100" -F "vehicle_y1=80" \
  -F "vehicle_x2=700" -F "vehicle_y2=500"
```

Bbox нь ирүүлсэн зураг дээрх бүхэл пиксел координат; x2/y2 нь тайралтын орохгүй
баруун/доод хил (`frame[y1:y2, x1:x2]`). Bbox-ийг тэлэхгүй, зураг гадна гарсан
координатыг чимээгүй засахгүй. Нэг машинаас модель, өнгө, төрөл, харагдац болон
анхны confidence утгуудыг буцаана. Confidence бага байсан ч Unknown гэж дарж бичихгүй.

```json
{
  "eventId": "event-123",
  "vehicleBbox": {"x1": 100, "y1": 80, "x2": 700, "y2": 500},
  "result": {
    "model": {"label": "Toyota Prius", "confidence": 0.96},
    "color": {"label": "white", "confidence": 0.94},
    "vehicleType": {"label": "car", "confidence": 0.98},
    "view": {"label": "front_side", "confidence": 0.95}
  }
}
```

`eventId` өгөөгүй бол сервер үүсгэнэ. Танилтын бүх талбар хоосон бол 200 хариунд
`reasonCode: CLASSIFICATION_FAILED` буцаана. API key буруу/байхгүй: 401;
буруу зураг/bbox: 422; зургийн хэмжээ хэтэрсэн: 413; classifier бэлэн биш: 503;
recognition service-ийн дотоод алдаа: 503. Одоогийн image byte/pixel хязгаарууд үйлчилнэ.
Postman collection: `postman/Vehicle Bbox API.postman_collection.json`.
