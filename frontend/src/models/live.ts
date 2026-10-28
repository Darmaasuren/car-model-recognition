export type ConnectionState =
  | "connecting"
  | "connected"
  | "disconnected"
  | "error";

export interface Prediction {
  label: string;
  confidence: number;
}

export interface LiveRecognitionResult {
  seatbelt?: SeatbeltResult | null;
  eventId: string;
  trackId?: number;
  detectedAt: string;
  cropUrl: string;

  model?: Prediction;
  color?: Prediction;
  vehicleType?: Prediction;
  view?: Prediction;
}

export interface RecognitionEvent {
  type: "recognition";
  cameraId: string;
  result: LiveRecognitionResult;
}

export interface SeatbeltResult {
  schemaVersion: number;
  status: string;
  detections: Array<{
    label: string;
    confidence: number;
    role: "driver" | "passenger" | "unknown" | null;
    bbox: number[];
    windshieldIndex: number;
    cropUrl?: string | null;
    cropError?: string;
    personConfidence?: number | null;
    roleConfidence?: number | null;
    phoneUsage?: boolean | null;
    phoneConfidence?: number | null;
  }>;
  error?: { code: string; message: string } | null;
}
