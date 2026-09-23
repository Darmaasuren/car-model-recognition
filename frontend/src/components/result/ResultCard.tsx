import { resolveMediaUrl } from "../../api/client";
import type {
  LiveRecognitionResult,
  Prediction,
} from "../../models/live";
import "./ResultCard.css";
import { SeatbeltDetails } from "./SeatbeltDetails";

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
  return (
    <article className="result-card">
      <img
        className="result-card__image"
        src={resolveMediaUrl(result.cropUrl)}
        alt={result.model?.label ?? "Танигдсан машин"}
      />

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
        <SeatbeltDetails result={result.seatbelt} />
      </div>
    </article>
  );
}
