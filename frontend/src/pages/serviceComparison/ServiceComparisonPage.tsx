import { useEffect, useState } from "react";
import { resolveMediaUrl } from "../../api/client";
import { getWorkerStatus, getComparisons } from "../../api/serviceComparison";
import type { ServiceComparison, ServiceWorkerStatus } from "../../api/serviceComparison";
import "./ServiceComparisonPage.css";
import { SeatbeltDetails } from "../../components/result/SeatbeltDetails";
import { ImageViewer } from "../../components/mediaPreview/ImageViewer";

const STATUS: Record<string, string> = {
  pending: "Хүлээгдэж буй",
  processing: "Боловсруулж буй",
  completed: "Дууссан",
  failed: "Алдаатай",
  OK: "Зураг танигдсан",
  MATCH: "Тохирсон",
  MISMATCH: "Зөрсөн",
  LOW_CONFIDENCE: "Итгэлцэл 90%-иас бага",
  UNSUPPORTED_CLASS: "Сургасан ангилалд байхгүй",
  MISSING_REFERENCE: "Service-ийн өгөгдөл дутуу",
  UNMAPPED_REFERENCE: "Нэршлийг тааруулах шаардлагатай",
  NO_PREDICTION: "Танилтын үр дүн байхгүй",
  NO_VEHICLE_DETECTED: "Машин илрээгүй",
  AMBIGUOUS_VEHICLE: "Нэгээс олон машин илэрсэн",
};

function formatEventDate(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Ulaanbaatar", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).format(date);
}

function predictionText(value?: { label: string; confidence: number } | null) {
  return value ? `${value.label} (${(value.confidence * 100).toFixed(1)}%)` : "—";
}

function StatusBadge({ status }: { status: string }) {
  const tone = status === "OK" || status === "MATCH"
    ? "success"
    : status === "MISMATCH"
      ? "danger"
      : status === "LOW_CONFIDENCE" || status === "UNMAPPED_REFERENCE"
        ? "warning"
        : "neutral";

  return <span className={`service-page__status service-page__status--${tone}`}>{STATUS[status] ?? status}</span>;
}

export function ServiceComparisonPage() {
  const [results, setResults] = useState<ServiceComparison[]>([]);
  const [worker, setWorker] = useState<ServiceWorkerStatus | null>(null);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<{ src: string; alt: string } | null>(null);

  const [offset, setOffset] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [pageInput, setPageInput] = useState("1");
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setLoading(true);
    async function refresh() {
      try {
        if (document.hidden) return;
        const [history, status] = await Promise.all([
          getComparisons(offset, controller.signal, pageSize),
          getWorkerStatus(controller.signal),
        ]);
        if (controller.signal.aborted) return;
        const lastOffset = Math.max(0, Math.ceil(history.total / pageSize) - 1) * pageSize;
        if (offset > lastOffset) { setOffset(lastOffset); return; }
        setResults(history.items);
        setTotal(history.total);
        setWorker(status);
        setError("");
      } catch (caught) {
        if (!controller.signal.aborted) {
          setError(caught instanceof Error ? caught.message : "Мэдээлэл уншиж чадсангүй.");
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          timer = setTimeout(() => void refresh(), 5000);
        }
      }
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [offset, pageSize]);

  const currentPage = Math.floor(offset / pageSize) + 1;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    setPageInput(String(currentPage));
  }, [currentPage]);

  function submitPage() {
    const value = Number(pageInput);
    const page = Number.isFinite(value) && pageInput.trim()
      ? Math.max(1, Math.min(pageCount, Math.trunc(value))) : currentPage;
    setPageInput(String(page));
    changePage((page - 1) * pageSize);
  }

  function changePage(nextOffset: number) {
    setError("");
    setOffset(nextOffset);
  }

  return (
    <main className="service-page">
      <header className="service-page__header">
        <div><h1>Service-ийн машин харьцуулах</h1><p>Service-ийн мэдээллийг танилтын үр дүнтэй харьцуулна.</p></div>
        <span className="service-page__status service-page__status--neutral">Автомат · 20 минут / 20 бичлэг</span>
      </header>
      <p className="service-page__count" role="status">
        {worker ? ({ waiting: "Дараагийн ажлыг хүлээж байна", fetching: "Service-ээс мэдээлэл авч байна",
          processing: "Зураг боловсруулж байна", blocked: "Автомат ажиллагаа зогссон",
          cooldown: "Дахин оролдох хугацааг хүлээж байна", not_started: "Worker асаагүй байна",
          unresponsive: "Worker-ийн төлөв шинэчлэгдээгүй байна", starting: "Worker эхэлж байна",
        }[worker.status] ?? worker.status) : "Worker-ийн төлөвийг уншиж байна…"}
        {worker && ` · Хүлээгдэж буй: ${worker.counts.pending ?? 0} · Алдаатай: ${worker.counts.failed ?? 0}`}
        {worker?.nextRequestAt && ` · Дараагийн хүсэлт: ${new Date(worker.nextRequestAt).toLocaleString()}`}
      </p>
      {worker?.error && <p role="alert" className="service-page__error">{worker.error}</p>}
      {error && <p role="alert" className="service-page__error">{error}</p>}
      {loading && <p role="status">Хадгалсан мэдээллийг уншиж байна…</p>}
      {!loading && !error && results.length === 0 && <p>Хадгалсан харьцуулалт байхгүй байна.</p>}
      {results.map((result, index) => <article className="service-page__card" key={`${result.recordId}-${index}`}>
        {result.imageUrl ? <button
          type="button"
          className="service-page__image-button"
          aria-label={`${result.plate || "Машины"} зургийг томруулж харах`}
          onClick={() => setPreview({ src: resolveMediaUrl(result.imageUrl!), alt: `Машины зураг ${result.plate}` })}
        ><img src={resolveMediaUrl(result.imageUrl)} alt={`Машины зураг ${result.plate}`} /></button> : <div className="service-page__missing-image">Зураг байхгүй</div>}
        <div className="service-page__details">
          <div className="service-page__card-heading">
            <h2><span>#{offset + index + 1}</span> {result.plate || "Дугаар байхгүй"}</h2>
            <StatusBadge status={result.imageStatus} />
          </div>
          <p className="service-page__meta"><span>Record ID:</span> {result.recordId}</p>
          {result.error ? <p className="service-page__error" role="alert">{result.error}</p> : <>
          <p className="service-page__meta"><span>Үйл явдлын огноо (УБ):</span> <time dateTime={result.eventDate || undefined} title={result.eventDate}>{formatEventDate(result.eventDate)}</time></p>
          <div className="service-page__table-scroll" tabIndex={0} role="region" aria-label="Танилтын харьцуулалт">
          <table>
            <thead><tr><th scope="col">Мэдээлэл</th><th scope="col">Service</th><th scope="col">Танилт</th><th scope="col">Харьцуулалт</th></tr></thead>
            <tbody>
              <tr><th scope="row">Марк, модель</th><td>{`${result.sourceMark} ${result.sourceModel}`.trim() || "—"}</td><td>{predictionText(result.prediction?.model)}</td><td><StatusBadge status={result.modelStatus} /></td></tr>
              <tr><th scope="row">Өнгө</th><td>{result.sourceColor || "—"}</td><td>{predictionText(result.prediction?.color)}</td><td><StatusBadge status={result.colorStatus} /></td></tr>
              <tr><th scope="row">Төрөл</th><td>{result.sourceType || "—"}</td><td>{predictionText(result.prediction?.vehicleType)}</td><td><StatusBadge status={result.typeStatus} /></td></tr>
              <tr><th scope="row">Харагдац</th><td>—</td><td>{predictionText(result.prediction?.view)}</td><td><StatusBadge status={result.viewStatus} /></td></tr>
            </tbody>
          </table>
          </div>
          <SeatbeltDetails result={result.seatbelt} />
          </>}
        </div>
      </article>)}
      <nav className="service-page__pagination" aria-label="Харьцуулалтын хуудас">
        <span className="service-page__total">Нийт : {total}</span>
        <button type="button" className="service-page__page-arrow" aria-label="Өмнөх хуудас"
          disabled={loading || currentPage === 1}
          onClick={() => changePage(offset - pageSize)}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 7-5 5 5 5" /></svg>
        </button>
        <input className="service-page__page-input" aria-label="Хуудасны дугаар"
          type="text" inputMode="numeric" value={pageInput} disabled={loading}
          onChange={(event) => setPageInput(event.target.value)} onBlur={submitPage}
          onKeyDown={(event) => {
            if (event.key === "Enter") { event.preventDefault(); submitPage(); }
            if (event.key === "Escape") setPageInput(String(currentPage));
          }} />
        <span className="service-page__page-count">/ <span>{pageCount}</span></span>
        <button type="button" className="service-page__page-arrow" aria-label="Дараагийн хуудас"
          disabled={loading || currentPage >= pageCount}
          onClick={() => changePage(offset + pageSize)}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m10 7 5 5-5 5" /></svg>
        </button>
        <span className="service-page__page-size">
          <select aria-label="Нэг хуудсанд харуулах тоо" value={pageSize} disabled={loading}
            onChange={(event) => {
              setPageSize(Number(event.target.value));
              setPageInput("1");
              changePage(0);
            }}>
            {[10, 20, 50, 100].map((size) => <option key={size} value={size}>{size} - р харах</option>)}
          </select>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 10 5 5 5-5" /></svg>
        </span>
      </nav>
      {preview && <ImageViewer src={preview.src} alt={preview.alt} onClose={() => setPreview(null)} />}
    </main>
  );
}
