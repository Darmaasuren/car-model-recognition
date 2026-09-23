# Тээврийн хэрэгсэл таних систем

Энэ төсөл нь React frontend болон FastAPI backend ашиглан зураг, бичлэг,
камерын дүрсээс тээврийн хэрэгслийг илрүүлж, ангилан таних зориулалттай.

Танилтын үндсэн дараалал:

1. YOLO object detection model зураг эсвэл бичлэг дээрээс тээврийн хэрэгслийг илрүүлнэ.
2. Тухайн илэрсэн тээврийн хэрэгслийн хэсгийг crop хийнэ.
3. Тээврийн хэрэгслийн төрлийг ангилах classifier нь model, color, tyope болон view гэсэн 4 төрлийг ангилна.
4. Машины дугаар танилтын системтэй холбох боломжтой API .

## Backend тохиргоо

Backend ажиллах үед дараах environment variable-уудыг заавал өгнө:

```text
API_PREFIX=/api/v1
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
API_KEY=<api-key>
```

## Docker image үүсгэх

Root directory-оос:

```bash
sudo docker build \
  -t vehicle-recognition-backend:v1 \
  ./backend
```

## Docker Compose ашиглахгүйгээр ажиллуулах

API key-г terminal-аас үүсгэж container ажиллуулна:

```bash
read -rsp "API key: " API_KEY
echo
export API_KEY

sudo --preserve-env=API_KEY docker run -d \
  --name vehicle-recognition-backend \
  --restart unless-stopped \
  -p 8008:8000 \
  -e API_KEY \
  -e API_PREFIX="/api/v1" \
  -e CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173" \
  vehicle-recognition-backend:v1

unset API_KEY
```

## Docker Compose ашиглах

```bash
sudo docker compose up -d
```
docker-compose.yaml Жишээ:

```yaml
services:
  backend:
    image: vehicle-recognition-backend:v1
    container_name: vehicle-recognition-backend
    environment:
      API_PREFIX: "/api/v1"
      CORS_ORIGINS: "http://localhost:5173,http://127.0.0.1:5173"
      API_KEY: "api-key"
    ports:
      - "8008:8000"
    restart: unless-stopped
```

---

# Vehicle Recognition System

This project uses a React frontend and FastAPI backend to detect and classify
vehicles from images, videos, and camera streams.

The main recognition workflow:

1. The YOLO object detection model detects vehicles from images or videos.
2. The detected vehicle region is cropped.
3. The vehicle classifier predicts four attributes: model, color, type, and
   view.
4. An API is provided for integration with a license plate recognition system.

## Backend Configuration

The following environment variables are required when running the backend:

```text
API_PREFIX=/api/v1
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
API_KEY=<api-key>
```

## Building the Docker Image

Run the following command from the root directory:

```bash
sudo docker build \
  -t vehicle-recognition-backend:v1 \
  ./backend
```

## Running Without Docker Compose

Enter the API key from the terminal and start the container:

```bash
read -rsp "API key: " API_KEY
echo
export API_KEY

sudo --preserve-env=API_KEY docker run -d \
  --name vehicle-recognition-backend \
  --restart unless-stopped \
  -p 8008:8000 \
  -e API_KEY \
  -e API_PREFIX="/api/v1" \
  -e CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173" \
  vehicle-recognition-backend:v1

unset API_KEY
```

## Running with Docker Compose

```bash
sudo docker compose up -d
```

Example `docker-compose.yaml`:

```yaml
services:
  backend:
    image: vehicle-recognition-backend:v1
    container_name: vehicle-recognition-backend
    environment:
      API_PREFIX: "/api/v1"
      CORS_ORIGINS: "http://localhost:5173,http://127.0.0.1:5173"
      API_KEY: "api-key"
    ports:
      - "8008:8000"
    restart: unless-stopped
```

## Username/password нэвтрэлт, PostgreSQL

Auth нь SQLAlchemy `User`, `Session` model, Argon2id password hash болон
HttpOnly session cookie ашиглана. Alembic байхгүй. Backend эхлэхэд байхгүй
хүснэгтүүдийг үүсгэнэ; `app/commands/init_db.py` нь admin хэрэглэгч үүсгэнэ. Аль аль нь
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
- `app/lifespan.py`: database, танилтын model эхлүүлэх болон хаах.
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
одоогийн танилтын pipeline-д өгнө. Frontend дөрвөн танилт (model, color,
type, view) болон confidence-ийг машин бүр дээр харуулна. Service-тэй
нэршил нь таарсан model, color, type-ийг 90%-ийн confidence босгоор
харьцуулна. Type-ийн нэршил таарахгүй эсвэл view-ийн эх утга байхгүй бол
таамгаар тохирсон гэж үзэхгүй. Нэг зурагт олон машин илэрвэл model танилтын
confidence хамгийн өндөр машиныг сонгож, тэр машины model, color, type, view
үр дүнг ашиглана. Машин илрээгүй бол `NO_VEHICLE_DETECTED` гэж харуулна.
Нэг record-ийн зураг алдаатай байсан ч
бусад record-ийг үргэлжлүүлэн боловсруулна. Зургийн хуулбар `runtime/crops`-д
хадгалагдана; харьцуулалтын metadata-г PostgreSQL-д хараахан бичихгүй.

### Урд талаас харагдсан машины суудлын бүс шалгах

Service харьцуулалтын үед сонгосон машины
`view.label=front_side`, confidence нь тохируулсан босгоос багагүй байвал
seatbelt service-ийг дуудна. Бусад зурагт шалгаагүй шалтгааныг харуулна.
Файл таних хуудасны зураг болон бичлэгт мөн энэ шалгалт хийгдэнэ:
`POST /inference/image`, `POST /inference/video` болон video session-ийн
шинэ танилтын event бүрд машины өөрийн crop ашиглана. Бичлэгийн tracking
нь өмнө таньсан track-ийг дахин танихгүй тул frame бүрд seatbelt дуудахгүй.
Анх таних үед урд талаас харагдаагүй track-ийг дараа нь дахин бүс шалгахгүй.
Seatbelt хариу хүлээхэд тухайн бичлэгийн боловсруулалт түр удааширч болно.
Live камер болон `/inference/vehicle` integration endpoint өөрчлөгдөөгүй.

```dotenv
SEATBELT_URL=http://host.docker.internal:8000/predict
SEATBELT_VIEW_MIN_CONFIDENCE=0.90
```

Одоогийн seatbelt Compose нь host-ийн 8000 портыг нээдэг.
Машин таних backend-ийн Compose-д `host.docker.internal:host-gateway`
нэмсэн тул тусдаа ажиллаж буй seatbelt контейнерийн тэр портоор холбогдоно.
Хоёр service ижил host дээр ажиллана гэж үзсэн. Backend-ийг Docker-гүй
ажиллуулбал URL-ийг `http://localhost:8000/predict` болгоно. Өөр сервер
ашиглавал хүрч болох хаягаар солино. Seatbelt project-ийн код өөрчлөгдөөгүй.

Pipeline машины тайрсан хэсгийн координатыг `vehicleBbox` талбарт нэмнэ.
Тэр координатаар RAM дахь эх зургаас crop авч, хэмжээг жижигрүүлэхгүй,
PNG байт болгон `Content-Type: image/png`-тай raw body илгээнэ.
Classifier-ийн жижигрүүлсэн tensor ашиглахгүй. Дамжуулалтад түр файл,
тусдаа annotated зураг үүсгэхгүй; одоогийн машины зураг хадгалалт хэвээр.

Seatbelt service нэг зураг зэрэг боловсруулдаг тул backend дотор
дуудлагуудыг lock-оор дарааллуулна. `503` үед 1 секунд хүлээгээд нэг удаа
давтана. Холболтын timeout 3 секунд, response унших timeout 30 секунд.
Timeout, service алдаа, буруу response нь машины үндсэн танилтыг устгахгүй:
`seatbelt.status=error` болж UI дээр тайлбар харагдана.

Response-ийн шинэ `seatbelt` хэсэг:
- `status`: `completed`, `unknown`, `skipped`, `error`.
- `reason`: төлөвийн тайлбар.
- `detections`: `className`, `confidence`, `bbox` бүхий илрүүлэлтүүд.
- `image`: амжилттай response-ийн crop хэмжээ.

`bbox` нь илгээсэн машины crop-ийн пиксел координат.
UI нь `person-seatbelt`, `person-noseatbelt` илрүүлэлт бүрийг confidence-той
харуулна; жолооч/зорчигч гэж ялгахгүй. Зөвхөн `seatbelt`, `windshield`
эсвэл хоосон илрүүлэлт ирвэл `unknown`; бүсгүй гэж дүгнэхгүй.
Илрүүлэлтүүд нь model-ийн үр дүн бөгөөд давхар box байж болох тул
баталгаатай хүний тоо гэж нэгтгэхгүй. Үр дүн database-д хараахан хадгалагдахгүй.

Seatbelt контейнер ажиллаж байгаа үед backend-ийн өөрчлөлтийг:
```bash
docker compose up -d --build backend
```
командаар оруулаад Service харьцуулалтын хуудсаар шалгана.

Файл таних үр дүнгийн `seatbelt` талбар нь REST response болон video
WebSocket event-д хамт ирнэ. Frontend-ийн `SeatbeltDetails` компонентыг
файл болон Service харьцуулалтын картууд хамт ашиглана.

### Service харьцуулалтын database хадгалалт

`POST /api/service/compare-batch` (20 бичлэг), мөн `compare-next` нь
`vehicle_recognitions` хүснэгтэд мэдээлэл хадгална. Backend эхлэхэд одоогийн
`create_all` механизмаар шинэ хүснэгтийг үүсгэнэ; backend-ийг шинэ кодоор дахин
асаах шаардлагатай. Одоо байгаа хүснэгтүүдийг өөрчлөхгүй.

- Бүх зөв форматтай эх бичлэгийг зураг татахаас өмнө `pending` төлөвөөр хадгална.
- Service-ийн `_id` нь `source_record_id` гэсэн давтагдахгүй түлхүүр болно.
  Ижил бичлэгийг дахин шалгахад нэг мөрөнд хамгийн сүүлийн үр дүнг шинэчилнэ.
  Улсын дугаар, огноо, марк, модель, өнгө, төрөл, `full_photo` замыг тусдаа
  баганад хадгална; давхар `source_payload` хадгалахгүй.
- `processing` → `completed` / `failed` төлөв, оролдлогын тоо, алдаа, эхэлсэн
  болон дууссан хугацааг хадгална. Танилтын алдаа нь дараагийн бичлэгийг зогсоохгүй.
  Database алдаа гарвал API 503 буцаана; хадгалаагүй үр дүнг амжилттай гэж буцаахгүй.
- `prediction`, `comparison`, `vehicle_bbox`, `seatbelt_result` нь PostgreSQL JSONB.
  Машины bbox эх зураг дээрх пиксел координаттай. Seatbelt bbox нь **машины
  тайралтын** пиксел координаттай хэвээр хадгалагдана: `coordinateSpace`, `units`,
  `bboxFormat`, `cropOrigin` болон service-ийн буцаасан `image` хэмжээтэй.
  Эх зурагт байрлуулахдаа cropOrigin-ийн x1/y1-ийг seatbelt координатад нэмнэ.
- Зураг runtime/crops дотор файл хэлбэрээр, харьцангуй зам болон эх зургийн хэмжээ
  database-д хадгалагдана. `model_version` нь classifier checkpoint-ийн файлын нэр
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
