import { useState } from "react";
import { resolveMediaUrl } from "../../api/client";
import { ImageViewer } from "../mediaPreview/ImageViewer";
import "./SeatbeltResult.css";
import type { SeatbeltResult as Result } from "../../models/live";

const statuses: Record<string, string> = {
  DISABLED: "Шалгалт идэвхгүй",
  SKIPPED_NOT_FRONT: "Машин урдаас хараагүй тул шалгах боломжгүй",
  SKIPPED_UNCERTAIN_VIEW: "Харагдац тодорхойгүй тул шалгаагүй",
  NO_WINDSHIELD: "Урд шил илрээгүй",
  NO_OCCUPANT_DETECTED: "Хүн илрээгүй",
  COMPLETED: "Шалгалт амжилттай",
  ERROR: "Шалгалт амжилтгүй",
};

function confidence(value?: number | null) {
  return value == null ? null : <span className="seatbelt-person__confidence">{(value * 100).toFixed(2)}%</span>;
}

function PersonResult({ person, index }: { person: Result["detections"][number]; index: number }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const role = person.role === "driver" ? "Жолооч" : person.role === "passenger" ? "Зорчигч" : "Байрлал тодорхойгүй";
  const belt = person.label === "person_seatbelt" ? "Бүстэй" : person.label === "person_no_seatbelt" ? "Бүсгүй" : "Тодорхойгүй";
  const phone = person.phoneUsage === true ? "Ашиглаж байна" : person.phoneUsage === false ? "Ашиглаагүй" : "Тодорхойгүй";
  const src = person.cropUrl ? resolveMediaUrl(person.cropUrl) : null;
  const alt = `Хүн ${index + 1} — ${role}`;
  return <article className="seatbelt-person" aria-label={alt}>
    {src && failedUrl !== src ? <button type="button" className="seatbelt-person__image" onClick={() => setPreview(true)} aria-label={`${alt}, зураг томруулах`}>
      <img src={src} alt={alt} loading="lazy" onError={() => setFailedUrl(src)} />
    </button> : <div className="seatbelt-person__missing">Хүний зураг байхгүй</div>}
    <div className="seatbelt-person__details">
      {/* <strong>Хүн {index + 1}</strong> */}
      <dl>
        <div><dt>Байрлал:</dt><dd>{role}{confidence(person.roleConfidence)}</dd></div>
        <div><dt>Суудлын бүс:</dt><dd>{belt}{person.label !== "person_unknown" && confidence(person.confidence)}</dd></div>
        <div><dt>Утас:</dt><dd>{phone}{person.phoneUsage != null && confidence(person.phoneConfidence)}</dd></div>
        {person.personConfidence != null && <div><dt>Хүн илрүүлэлт:</dt><dd>{confidence(person.personConfidence)}</dd></div>}
      </dl>
    </div>
    {preview && src && <ImageViewer src={src} alt={alt} onClose={() => setPreview(false)} />}
  </article>;
}

export function SeatbeltResult({ result }: { result?: Result | null }) {
  if (!result) return <p>Суудлын бүс: шалгаагүй</p>;
  const people = result.detections.filter(d => ["person_seatbelt", "person_no_seatbelt", "person_unknown"].includes(d.label));
  return <section className="seatbelt-result" aria-label="Суудлын бүсний танилт">
    <p><strong>Суудлын бүс:</strong> {statuses[result.status] ?? result.status}</p>
    <div className="seatbelt-result__people">
      {people.map((person, index) => <PersonResult key={person.cropUrl ?? index} person={person} index={index} />)}
    </div>
    {result.error && <p>{result.error.message}</p>}
  </section>;
}
