import type { LiveRecognitionResult } from "../../models/live";
import { ResultCard } from "./ResultCard";
import "./ResultList.css";

interface ResultListProps {
  results: LiveRecognitionResult[];
  emptyTitle?: string;
  emptyDescription?: string;
}

export function ResultList({
  results,
  emptyTitle = "Танилтын үр дүн одоогоор байхгүй.",
}: ResultListProps) {
  if (results.length === 0) {
    return (
      <div className="result-list__empty">
        <p>{emptyTitle}</p>
      </div>
    );
  }

  return (
    <div className="result-list">
      {results.map((result) => (
        <ResultCard
          key={result.eventId}
          result={result}
        />
      ))}
    </div>
  );
}
