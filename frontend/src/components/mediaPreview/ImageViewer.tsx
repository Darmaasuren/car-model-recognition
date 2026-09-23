import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./ImageViewer.css";

interface ImageViewerProps {
  src: string;
  alt: string;
  onClose: () => void;
}

export function ImageViewer({ src, alt, onClose }: ImageViewerProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    const dialog = dialogRef.current;
    const previousOverflow = document.body.style.overflow;
    dialog?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  function changeZoom(amount: number) {
    setZoom(current => Math.min(4, Math.max(1, current + amount)));
  }

  return createPortal(
    <dialog
      ref={dialogRef}
      className="image-viewer"
      aria-label={alt}
      onCancel={event => { event.preventDefault(); onClose(); }}
      onClick={event => { if (event.target === event.currentTarget) onClose(); }}
    >
      <button className="image-viewer__close" type="button" onClick={onClose} aria-label="Зураг хаах" autoFocus>×</button>
      <div className="image-viewer__stage" onClick={event => {
        if (event.target === event.currentTarget) onClose();
      }}>
        <div className="image-viewer__canvas" style={{ width: `${zoom * 100}%`, height: `${zoom * 100}%` }}
          onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
          <img src={src} alt={alt} draggable={false} />
        </div>
      </div>
      <div className="image-viewer__toolbar" role="group" aria-label="Зургийн хэмжээ">
        <button type="button" onClick={() => changeZoom(-0.25)} disabled={zoom <= 1} aria-label="Жижигрүүлэх">−</button>
        <output aria-live="polite">{Math.round(zoom * 100)}%</output>
        <button type="button" onClick={() => changeZoom(0.25)} disabled={zoom >= 4} aria-label="Томруулах">+</button>
        <button type="button" onClick={() => setZoom(1)}>Дэлгэцэд тааруулах</button>
      </div>
    </dialog>,
    document.body,
  );
}
