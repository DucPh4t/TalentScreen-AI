"use client";

import { useEffect, useRef, useState } from "react";

interface RawPdfViewerProps {
  file: Blob;
}

/** Render a private PDF in app-owned canvas; this avoids browser plugin/iframe gaps. */
export default function RawPdfViewer({ file }: RawPdfViewerProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);
  const [pdf, setPdf] = useState<any>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [hostWidth, setHostWidth] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [rendering, setRendering] = useState(false);

  useEffect(() => {
    let active = true;
    let loadingTask: any;
    let loadedDocument: any;
    setPdf(null);
    setPageNumber(1);
    setLoadError(null);

    void (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
        loadingTask = pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) });
        loadedDocument = await loadingTask.promise;
        if (active) setPdf(loadedDocument);
        else await loadedDocument.destroy();
      } catch (error: any) {
        console.error("Raw PDF rendering failed", error);
        if (active) setLoadError(error?.message || "Không thể đọc tệp PDF này.");
      }
    })();

    return () => {
      active = false;
      renderTaskRef.current?.cancel();
      if (loadingTask) void loadingTask.destroy();
      else if (loadedDocument) void loadedDocument.destroy();
    };
  }, [file]);

  useEffect(() => {
    if (!hostRef.current) return;
    const host = hostRef.current;
    const observer = new ResizeObserver(() => setHostWidth(host.clientWidth));
    observer.observe(host);
    setHostWidth(host.clientWidth);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!pdf || !canvasRef.current || !hostWidth) return;
    let active = true;
    setRendering(true);
    renderTaskRef.current?.cancel();

    void (async () => {
      try {
        const page = await pdf.getPage(pageNumber);
        const baseViewport = page.getViewport({ scale: 1 });
        const scale = Math.min(1.5, Math.max(0.55, (hostWidth - 32) / baseViewport.width));
        const viewport = page.getViewport({ scale });
        const outputScale = Math.min(window.devicePixelRatio || 1, 2);
        const canvas = canvasRef.current;
        const context = canvas?.getContext("2d", { alpha: false });
        if (!canvas || !context || !active) return;
        canvas.width = Math.floor(viewport.width * outputScale);
        canvas.height = Math.floor(viewport.height * outputScale);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;
        const task = page.render({
          canvas,
          canvasContext: context,
          viewport,
          transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
        });
        renderTaskRef.current = task;
        await task.promise;
      } catch (error: any) {
        if (active && error?.name !== "RenderingCancelledException") {
          setLoadError(error?.message || "Không thể kết xuất trang PDF này.");
        }
      } finally {
        if (active) setRendering(false);
      }
    })();

    return () => {
      active = false;
      renderTaskRef.current?.cancel();
    };
  }, [pdf, pageNumber, hostWidth]);

  return (
    <div ref={hostRef}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem", padding: "0.65rem 0.85rem", borderBottom: "1px solid var(--border-subtle)" }}>
        <span role="status" style={{ color: "var(--text-secondary)", fontSize: "0.82rem" }}>
          {pdf ? `Trang ${pageNumber}/${pdf.numPages}` : "Đang đọc PDF…"}{rendering ? " · Đang kết xuất" : ""}
        </span>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPageNumber(page => Math.max(1, page - 1))} disabled={!pdf || pageNumber <= 1}>Trang trước</button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPageNumber(page => Math.min(pdf?.numPages || 1, page + 1))} disabled={!pdf || pageNumber >= (pdf?.numPages || 1)}>Trang sau</button>
        </div>
      </div>
      {loadError ? (
        <p role="alert" style={{ margin: "1rem", color: "var(--rose-text)" }}>Không thể hiển thị PDF. {loadError}</p>
      ) : (
        <div style={{ display: "flex", justifyContent: "center", padding: "1rem", minHeight: "18rem", background: "#e8ebef" }}>
          <canvas ref={canvasRef} aria-label={`Trang ${pageNumber} của CV gốc`} style={{ maxWidth: "100%", height: "auto", background: "white", boxShadow: "0 2px 14px rgba(0,0,0,.16)" }} />
        </div>
      )}
    </div>
  );
}
