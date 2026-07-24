import { useState } from "react";
import "./LiveVideo.css";

interface LiveVideoProps {
  streamUrl: string;
  cameraName: string;
}

export function LiveVideo({
  streamUrl,
  cameraName,
}: LiveVideoProps) {
  const [hasError, setHasError] = useState(false);

  if (hasError) {
    return (
      <div className="live-video live-video--empty">
        <strong>Камерын дүрс ачаалагдсангүй</strong>
      </div>
    );
  }

  return (
    <div className="live-video">
      <img
        className="live-video__stream"
        src={streamUrl}
        alt={`${cameraName} камерын шууд дүрс`}
        onError={() => setHasError(true)}
      />

      <div className="live-video__badge">
        <span className="live-video__badge-dot" />
        LIVE
      </div>
    </div>
  );
}