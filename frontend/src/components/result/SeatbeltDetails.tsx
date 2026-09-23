import type { SeatbeltResult } from "../../models/live";
import "./SeatbeltDetails.css";

export function SeatbeltDetails({ result }: { result?: SeatbeltResult | null }) {
  if (!result) return null;
  const people = result.detections.filter(item =>
    item.className === "person-seatbelt" || item.className === "person-noseatbelt");
  return <section className="seatbelt-details" aria-label="Суудлын бүс">
    <h3>Суудлын бүс</h3>
    {people.length === 0
      ? <p className={result.status === "error" ? "seatbelt-details__error" : "seatbelt-details__reason"}>{result.reason}</p>
      : <div className="seatbelt-details__results">{people.map((item, index) =>
        <span key={index} className={`seatbelt-details__badge seatbelt-details__badge--${item.className === "person-seatbelt" ? "success" : "danger"}`}>
          {item.className === "person-seatbelt" ? "Бүс зүүсэн хүн" : "Бүс зүүгээгүй хүн"}
          {" · "}{(item.confidence * 100).toFixed(1)}%
        </span>)}</div>}
  </section>;
}

