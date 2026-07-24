import base64
import binascii
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from fastapi import HTTPException, UploadFile


class MediaTooLargeError(ValueError):
    pass


class MediaService:
    def __init__(
        self,
        upload_dir: Path,
        crop_dir: Path,
        output_dir: Path,
    ):
        self.upload_dir = upload_dir
        self.crop_dir = crop_dir
        self.output_dir = output_dir

        self.upload_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.crop_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    async def save_upload(
        self,
        file: UploadFile,
        allowed_suffixes: set[str],
        max_bytes: int,
    ) -> Path:
        suffix = Path(file.filename or "").suffix.lower()

        if suffix not in allowed_suffixes:
            raise HTTPException(
                status_code=400,
                detail="Дэмжигдэхгүй файл байна.",
            )

        path = self.upload_dir / f"{uuid4().hex}{suffix}"
        total_bytes = 0
        chunk_size = 1024 * 1024

        try:
            with path.open("wb") as output:
                while chunk := await file.read(chunk_size):
                    total_bytes += len(chunk)

                    if total_bytes > max_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail="Файлын хэмжээ хэтэрсэн.",
                        )

                    output.write(chunk)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

        if total_bytes == 0:
            path.unlink(missing_ok=True)

            raise HTTPException(
                status_code=400,
                detail="Хоосон файл байна.",
            )

        return path

    def read_image(self, path: Path):
        frame = cv2.imread(str(path))

        if frame is None:
            raise ValueError("Зургийг уншиж чадсангүй.")

        return frame

    def decode_base64_image(
        self,
        encoded_image: str,
        max_bytes: int,
        max_pixels: int,
    ):
        value = encoded_image.strip()

        if value.lower().startswith("data:"):
            try:
                header, value = value.split(",", maxsplit=1)
            except ValueError as error:
                raise ValueError(
                    "Base64 image формат буруу байна."
                ) from error

            allowed_headers = {
                "data:image/jpeg;base64",
                "data:image/png;base64",
                "data:image/webp;base64",
            }

            if header.lower() not in allowed_headers:
                raise ValueError(
                    "Дэмжигдээгүй зургийн төрөл байна."
                )

        max_encoded_length = ((max_bytes + 2) // 3) * 4

        if len(value) > max_encoded_length:
            raise MediaTooLargeError(
                "Зургийн хэмжээ хэтэрсэн."
            )

        try:
            image_bytes = base64.b64decode(
                value,
                validate=True,
            )
        except (binascii.Error, ValueError) as error:
            raise ValueError(
                "Base64 өгөгдөл буруу байна."
            ) from error

        if not image_bytes:
            raise ValueError("Зураг хоосон байна.")

        if len(image_bytes) > max_bytes:
            raise MediaTooLargeError(
                "Зургийн хэмжээ хэтэрсэн."
            )

        image_array = np.frombuffer(
            image_bytes,
            dtype=np.uint8,
        )
        frame = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR,
        )

        if frame is None:
            raise ValueError(
                "Base64 өгөгдлийг зураг болгон уншиж чадсангүй."
            )

        height, width = frame.shape[:2]

        if width * height > max_pixels:
            raise MediaTooLargeError(
                "Зургийн нягтаршил хэт өндөр байна."
            )

        return frame

    def encode_image_data_url(
        self,
        image,
        jpeg_quality: int = 85,
    ) -> str:
        if image.size == 0:
            raise ValueError("Encode хийх зураг хоосон байна.")

        success, encoded = cv2.imencode(
            ".jpg",
            image,
            [
                cv2.IMWRITE_JPEG_QUALITY,
                jpeg_quality,
            ],
        )

        if not success:
            raise RuntimeError(
                "Vehicle crop encode хийж чадсангүй."
            )

        value = base64.b64encode(
            encoded.tobytes()
        ).decode("ascii")

        return f"data:image/jpeg;base64,{value}"

    def save_crop(
        self,
        crop,
        event_id: str,
    ) -> str:
        filename = f"{event_id}.jpg"
        path = self.crop_dir / filename

        if not cv2.imwrite(str(path), crop):
            raise RuntimeError(
                "Crop зураг хадгалж чадсангүй."
            )

        return f"/media/crops/{filename}"

    def remove_file(self, path: Path) -> None:
        path.unlink(missing_ok=True)

    def remove_crop(self, crop_url: str) -> None:
        filename = Path(crop_url).name

        if filename:
            (self.crop_dir / filename).unlink(missing_ok=True)
