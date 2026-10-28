import { SeatbeltResult } from "./SeatbeltResult";
import { resolveMediaUrl } from "../../api/client";
import type {
  LiveRecognitionResult,
  Prediction,
} from "../../models/live";
import "./ResultCard.css";
import { useState } from "react";
import { ImageViewer } from "../mediaPreview/ImageViewer";

interface ResultCardProps {
  result: LiveRecognitionResult;
}

interface PredictionItemProps {
  title: string;
  prediction?: Prediction;
}

function formatConfidence(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function formatTime(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("mn-MN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function PredictionItem({
  title,
  prediction,
}: PredictionItemProps) {
  if (!prediction) {
    return null;
  }

  return (
    <div className="prediction-item">
      <span className="prediction-item__title">{title}</span>

      <strong className="prediction-item__label">
        {prediction.label}
      </strong>

      <strong className="prediction-item__confidence">
        {formatConfidence(prediction.confidence)}
      </strong>
    </div>
  );
}

export function ResultCard({ result }: ResultCardProps) {
  const [preview, setPreview] = useState(false);
  const imageSrc = resolveMediaUrl(result.cropUrl);
  const imageAlt = result.model?.label ?? "Танигдсан машин";
  return (
    <article className="result-card">
      <button
        type="button"
        className="result-card__image-button"
        onClick={() => setPreview(true)}
        aria-label={`${imageAlt} — зураг томруулах`}
      >
        <img
          className="result-card__image"
          src={imageSrc}
          alt={imageAlt}
        />
      </button>

      <div className="result-card__body">
        <time
          className="result-card__time"
          dateTime={result.detectedAt}
        >
          {formatTime(result.detectedAt)}
        </time>

        <div className="result-card__predictions">
          <PredictionItem
            title="Model"
            prediction={result.model}
          />

          <PredictionItem
            title="Color"
            prediction={result.color}
          />

          <PredictionItem
            title="Type"
            prediction={result.vehicleType}
          />

          <PredictionItem
            title="View"
            prediction={result.view}
          />
        </div>
      </div>
      <div className="result-card__occupants">
        <SeatbeltResult result={result.seatbelt} />
      </div>
      {preview && (
      <ImageViewer
        src={imageSrc}
        alt={imageAlt}
        onClose={() => setPreview(false)}
      />
    )}
    </article>
  );
}
