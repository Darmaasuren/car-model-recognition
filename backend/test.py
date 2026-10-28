"""Manual recognition-client smoke check: python test.py path/to/car.jpg."""
import argparse
from pathlib import Path

from app.core.config import settings
from app.services.media import MediaService
from app.services.recognition.client import RecognitionClient
from app.services.recognition.results import RecognitionResults


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    media = MediaService(settings.upload_dir, settings.crop_dir, settings.output_dir)
    client = RecognitionResults(media, RecognitionClient())
    for result in client.process_image(media.read_image(args.image)):
        print(result.model_dump_json(by_alias=True))


if __name__ == "__main__":
    main()
