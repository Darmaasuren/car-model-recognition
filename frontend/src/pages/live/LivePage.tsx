import { useEffect, useMemo, useState } from "react";
import {
  connectLiveEvents,
  getLiveStreamUrl,
} from "../../api/live";
import { ConnectionStatus } from "../../components/connection/ConnectionStatus";
import { LiveVideo } from "../../components/live/LiveVideo";
import { ResultList } from "../../components/result/ResultList";
import type {
  ConnectionState,
  LiveRecognitionResult,
} from "../../models/live";
import { environment } from "../../config";
import "./LivePage.css";

const MAX_VISIBLE_RESULTS = 50;

export function LivePage() {
  const cameraId = environment.cameraId;

  const [connectionState, setConnectionState] =
    useState<ConnectionState>("connecting");

  const [results, setResults] =
    useState<LiveRecognitionResult[]>([]);

  const streamUrl = useMemo(
    () => getLiveStreamUrl(cameraId),
    [cameraId],
  );

  useEffect(() => {
    setConnectionState("connecting");

    const disconnect = connectLiveEvents({
      cameraId,

      onConnected: () => {
        setConnectionState("connected");
      },

      onDisconnected: () => {
        setConnectionState("disconnected");
      },

      onError: () => {
        setConnectionState("error");
      },

      onRecognition: (event) => {
        setResults((currentResults) => {
          const alreadyExists = currentResults.some(
            (result) =>
              result.eventId === event.result.eventId,
          );

          if (alreadyExists) {
            return currentResults;
          }

          return [
            event.result,
            ...currentResults,
          ].slice(0, MAX_VISIBLE_RESULTS);
        });
      },
    });

    return disconnect;
  }, [cameraId]);

  return (
    <main className="live-page">
      <header className="live-page__heading">
        <div>
          <h1>Хянах самбар</h1>
        </div>

        <ConnectionStatus status={connectionState} />
      </header>

      <div className="live-page__content">
        <section className="live-panel">
          <header className="live-panel__header">
            <div>
              <h2>Камерын шууд дүрс</h2>
              <p>{cameraId}</p>
            </div>

            <span className="live-panel__camera-state">
              Live
            </span>
          </header>

          <div className="live-panel__body">
            <LiveVideo
              streamUrl={streamUrl}
              cameraName={cameraId}
            />
          </div>
        </section>

        <section className="live-panel">
          <header className="live-panel__header">
            <div>
              <h2>Танилтын үр дүн</h2>
            </div>

            <div className="live-panel__count">
              {results.length}
            </div>
          </header>

          <div className="live-panel__results">
            <ResultList results={results} />
          </div>
        </section>
      </div>
    </main>
  );
}
