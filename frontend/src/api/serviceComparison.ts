import { apiFetch, buildApiUrl } from "./client";
import type { LiveRecognitionResult, SeatbeltResult } from "../models/live";

export interface ServiceComparison {
  recordId: string;
  plate: string;
  eventDate: string;
  sourceMark: string;
  sourceModel: string;
  sourceColor: string;
  sourceType: string;
  imageUrl?: string;
  imageStatus: string;
  modelStatus: string;
  colorStatus: string;
  typeStatus: string;
  viewStatus: string;
  prediction: LiveRecognitionResult | null;
  error?: string;
  seatbelt?: SeatbeltResult;
}

export interface ServiceComparisonBatch {
  items: ServiceComparison[];
  count: number;
}

export async function compareBatch(): Promise<ServiceComparisonBatch> {
  const response = await apiFetch(buildApiUrl("/service/compare-batch"), {
    method: "POST",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : "Service-ийн машиныг харьцуулж чадсангүй.");
  }
  return response.json() as Promise<ServiceComparisonBatch>;
}


export interface ServiceComparisonHistory extends ServiceComparisonBatch {
  total: number;
  offset: number;
  limit: number;
}

export async function getComparisons(offset = 0, signal?: AbortSignal, limit = 20): Promise<ServiceComparisonHistory> {
  const response = await apiFetch(buildApiUrl(`/service/comparisons?offset=${offset}&limit=${limit}`), { signal });
  if (!response.ok) {
    throw new Error("Хадгалсан харьцуулалтыг уншиж чадсангүй.");
  }
  return response.json() as Promise<ServiceComparisonHistory>;
}
