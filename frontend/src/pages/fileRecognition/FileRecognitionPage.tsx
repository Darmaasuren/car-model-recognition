import { useEffect, useMemo, useState } from "react";
import {
  connectVideoSessionEvents,
  createVideoSession,
  getVideoSessionStreamUrl,
  recognizeFile,
  stopVideoSession,
} from "../../api/inference";
import { FileUploader } from "../../components/fileUploader/FileUploader";
import { MediaPreview } from "../../components/mediaPreview/MediaPreview";
import { ResultList } from "../../components/result/ResultList";
import type { LiveRecognitionResult } from "../../models/live";
import "./FileRecognitionPage.css";

const MAX_VISIBLE_RESULTS = 50;

export function FileRecognitionPage() {
  const [selectedFile, setSelectedFile] =
    useState<File | null>(null);
  const [results, setResults] =
    useState<LiveRecognitionResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [videoSessionId, setVideoSessionId] = useState("");

  const processedStreamUrl = useMemo(
    () =>
      videoSessionId
        ? getVideoSessionStreamUrl(videoSessionId)
        : "",
    [videoSessionId],
  );

  useEffect(() => {
    if (!videoSessionId) {
      return;
    }

    const disconnect = connectVideoSessionEvents({
      sessionId: videoSessionId,

      onRecognition: (result) => {
        setResults((currentResults) => {
          if (
            currentResults.some(
              (current) => current.eventId === result.eventId,
            )
          ) {
            return currentResults;
          }

          return [result, ...currentResults].slice(
            0,
            MAX_VISIBLE_RESULTS,
          );
        });
      },

      onStatus: (status, sessionError) => {
        if (status === "completed") {
          setIsLoading(false);
        }

        if (status === "error" || status === "stopped") {
          setIsLoading(false);
          if (sessionError) {
            setError(sessionError);
          }
        }
      },

      onError: () => {
        setIsLoading(false);
        setError("Бичлэгийн realtime холболт тасарлаа.");
      },
    });

    return () => {
      disconnect();
      void stopVideoSession(videoSessionId);
    };
  }, [videoSessionId]);

  function handleFileChange(file: File | null) {
    setVideoSessionId("");
    setSelectedFile(file);
    setResults([]);
    setError("");
  }

  function handleClear() {
    setVideoSessionId("");
    setSelectedFile(null);
    setResults([]);
    setError("");
  }

  async function handleRecognize() {
    if (!selectedFile || isLoading) {
      return;
    }

    try {
      setIsLoading(true);
      setError("");
      setResults([]);

      if (selectedFile.type.startsWith("video/")) {
        const response = await createVideoSession(selectedFile);
        setVideoSessionId(response.sessionId);
        return;
      }

      const response = await recognizeFile(selectedFile);
      setResults(response.results);
      setIsLoading(false);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Танилт хийхэд алдаа гарлаа.",
      );
      setIsLoading(false);
    }
  }

  return (
    <main className="file-page">
      <header className="file-page__heading">
        <div>
          <h1>Файл таних</h1>
        </div>
      </header>

      <div className="file-page__content">
        <section className="file-panel">
          <header className="file-panel__header">
            <div>
              <h2>Зураг эсвэл бичлэг оруулах</h2>
              <p>Зураг 15 MB · Бичлэг 200 MB хүртэл</p>
            </div>

            {selectedFile && (
              <button
                type="button"
                className="file-panel__clear"
                onClick={handleClear}
              >
                Цэвэрлэх
              </button>
            )}
          </header>

          <div className="file-panel__body">
            <MediaPreview
              file={selectedFile}
              processedStreamUrl={processedStreamUrl}
            />

            {error && (
              <p className="file-panel__error" role="alert">
                {error}
              </p>
            )}

            <FileUploader
              selectedFile={selectedFile}
              disabled={isLoading}
              onFileChange={handleFileChange}
              onRecognize={handleRecognize}
            />
          </div>
        </section>

        <section className="file-panel">
          <header className="file-panel__header">
            <div>
              <h2>Танилтын үр дүн</h2>
            </div>

            <div className="file-panel__count">
              {results.length}
            </div>
          </header>

          <div className="file-panel__results">
            <ResultList
              results={results}
              emptyDescription={
                isLoading
                  ? "ROI дотор машин орж ирэхэд үр дүн шууд харагдана."
                  : "Файл сонгож танилт хийхэд үр дүн энд харагдана."
              }
            />
          </div>
        </section>
      </div>
    </main>
  );
}
