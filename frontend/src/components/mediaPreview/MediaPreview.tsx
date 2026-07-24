import { useEffect, useState } from "react";
import "./MediaPreview.css";

interface MediaPreviewProps {
  file: File | null;
  processedStreamUrl?: string;
}

export function MediaPreview({
  file,
  processedStreamUrl,
}: MediaPreviewProps) {
  const [previewUrl, setPreviewUrl] = useState("");

  useEffect(() => {
    if (!file) {
      setPreviewUrl("");
      return;
    }

    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);

    return () => {
      URL.revokeObjectURL(objectUrl);
    };
  }, [file]);

  if (!file || !previewUrl) {
    return (
      <div className="media-preview media-preview--empty">
        <strong>Файл сонгоогүй байна</strong>
        {/* <span>
          Зураг эсвэл бичлэг сонгоход энд харагдана.
        </span> */}
      </div>
    );
  }

  if (file.type.startsWith("video/")) {
    if (processedStreamUrl) {
      return (
        <div className="media-preview">
          <img
            className="media-preview__content"
            src={processedStreamUrl}
            alt={`${file.name} танилт хийж буй дүрс`}
          />

          <div className="media-preview__processing">
            <span />
            REALTIME
          </div>
        </div>
      );
    }

    return (
      <div className="media-preview">
        <video
          className="media-preview__content"
          src={previewUrl}
          controls
        />
      </div>
    );
  }

  return (
    <div className="media-preview">
      <img
        className="media-preview__content"
        src={previewUrl}
        alt={file.name}
      />
    </div>
  );
}
