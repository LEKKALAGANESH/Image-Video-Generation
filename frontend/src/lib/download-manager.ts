/* ─────────────────────────────────────────────
 * AuraGen — DownloadManager
 * Streams file chunks from the backend into
 * OPFS (Origin-Private File System) with
 * IndexedDB metadata for persistent gallery.
 * ───────────────────────────────────────────── */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

/** Database name for gallery metadata. */
const DB_NAME = "auragen-gallery";
const DB_VERSION = 1;
const STORE_NAME = "assets";

/** OPFS directory name. */
const OPFS_DIR = "auragen-outputs";

/* ── Types ─────────────────────────────────── */

export interface GalleryAsset {
  /** Job ID used as the primary key. */
  id: string;
  /** Original filename on the server. */
  filename: string;
  /** MIME type. */
  mimeType: string;
  /** File size in bytes. */
  size: number;
  /** Prompt used for generation. */
  prompt: string;
  /** When the asset was saved locally. */
  savedAt: number;
  /** Whether the file exists in OPFS. */
  persisted: boolean;
}

export type DownloadPhase = "idle" | "streaming" | "saving" | "ready";

export interface DownloadProgress {
  phase: DownloadPhase;
  bytesReceived: number;
  totalBytes: number;
  percent: number;
}

/* ── IndexedDB helpers ─────────────────────── */

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function putAsset(asset: GalleryAsset): Promise<void> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).put(asset);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getAllAssets(): Promise<GalleryAsset[]> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const req = tx.objectStore(STORE_NAME).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function getAsset(id: string): Promise<GalleryAsset | undefined> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const req = tx.objectStore(STORE_NAME).get(id);
    req.onsuccess = () => resolve(req.result ?? undefined);
    req.onerror = () => reject(req.error);
  });
}

/* ── OPFS helpers ──────────────────────────── */

async function getOpfsDir(): Promise<FileSystemDirectoryHandle | null> {
  try {
    const root = await navigator.storage.getDirectory();
    return await root.getDirectoryHandle(OPFS_DIR, { create: true });
  } catch {
    return null;
  }
}

/** Read a file from OPFS and return an object URL. */
export async function getLocalFileURL(filename: string): Promise<string | null> {
  try {
    const dir = await getOpfsDir();
    if (!dir) return null;
    const fileHandle = await dir.getFileHandle(filename);
    const file = await fileHandle.getFile();
    return URL.createObjectURL(file);
  } catch {
    return null;
  }
}

/* ── Parallel Chunk Download ───────────────── */

/** Minimum file size (1 MB) to trigger parallel chunked download. */
const PARALLEL_CHUNK_THRESHOLD = 1024 * 1024;

/** Number of concurrent download chunks. */
const PARALLEL_CHUNK_COUNT = 4;

/**
 * Download a file using parallel Range-request chunks.
 *
 * 1. HEAD request to discover Content-Length and Accept-Ranges support.
 * 2. If the file is > 1 MB and the server supports Range requests,
 *    split into 4 concurrent fetches with Range headers.
 * 3. Combine all chunks in order into a single Blob.
 * 4. Falls back to a single-stream fetch if conditions are not met.
 *
 * @returns A Blob containing the complete file, plus its MIME type.
 */
async function downloadWithParallelChunks(
  url: string,
  onProgress?: (bytesReceived: number, totalBytes: number) => void,
): Promise<{ blob: Blob; totalBytes: number; mimeType: string }> {
  // ── 1. Probe the server ──────────────────────────────────────────
  let totalBytes = 0;
  let supportsRange = false;
  let mimeType = "application/octet-stream";

  try {
    const head = await fetch(url, { method: "HEAD" });
    if (head.ok) {
      totalBytes = parseInt(head.headers.get("Content-Length") || "0", 10);
      supportsRange = (head.headers.get("Accept-Ranges") || "").toLowerCase() === "bytes";
      mimeType = head.headers.get("Content-Type") || mimeType;
    }
  } catch {
    // HEAD failed — fall through to single-stream
  }

  // ── 2. Decide strategy ───────────────────────────────────────────
  if (supportsRange && totalBytes > PARALLEL_CHUNK_THRESHOLD) {
    // Parallel chunked download
    const chunkSize = Math.ceil(totalBytes / PARALLEL_CHUNK_COUNT);
    const received = new Array<number>(PARALLEL_CHUNK_COUNT).fill(0);

    const reportAggregate = () => {
      const total = received.reduce((a, b) => a + b, 0);
      onProgress?.(total, totalBytes);
    };

    const fetchChunk = async (index: number): Promise<Uint8Array> => {
      const start = index * chunkSize;
      const end = Math.min(start + chunkSize - 1, totalBytes - 1);

      const res = await fetch(url, {
        headers: { Range: `bytes=${start}-${end}` },
      });

      if (!res.ok && res.status !== 206) {
        throw new Error(`Chunk ${index} failed: ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) {
        const buf = await res.arrayBuffer();
        received[index] = buf.byteLength;
        reportAggregate();
        return new Uint8Array(buf);
      }

      const parts: Uint8Array[] = [];
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        parts.push(value);
        received[index] += value.byteLength;
        reportAggregate();
      }

      // Merge parts for this chunk
      const merged = new Uint8Array(received[index]);
      let offset = 0;
      for (const part of parts) {
        merged.set(part, offset);
        offset += part.byteLength;
      }
      return merged;
    };

    const chunks = await Promise.all(
      Array.from({ length: PARALLEL_CHUNK_COUNT }, (_, i) => fetchChunk(i)),
    );

    const blob = new Blob(chunks as BlobPart[], { type: mimeType });
    return { blob, totalBytes, mimeType };
  }

  // ── 3. Fallback: single-stream download ──────────────────────────
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Download failed: ${res.status} ${res.statusText}`);
  }

  if (!totalBytes) {
    totalBytes = parseInt(res.headers.get("Content-Length") || res.headers.get("X-File-Size") || "0", 10);
  }
  mimeType = res.headers.get("Content-Type") || mimeType;

  const reader = res.body?.getReader();
  if (!reader) {
    const buf = await res.arrayBuffer();
    onProgress?.(buf.byteLength, buf.byteLength);
    return { blob: new Blob([buf], { type: mimeType }), totalBytes: buf.byteLength, mimeType };
  }

  const parts: Uint8Array[] = [];
  let got = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    parts.push(value);
    got += value.byteLength;
    onProgress?.(got, totalBytes);
  }

  const blob = new Blob(parts as BlobPart[], { type: mimeType });
  return { blob, totalBytes: got, mimeType };
}

/* ── Download Manager ──────────────────────── */

/**
 * Stream a file from the backend's chunked endpoint into OPFS and
 * register it in IndexedDB for the persistent gallery.
 *
 * Uses parallel chunk downloading when the file is large enough and
 * the server supports Range requests, otherwise falls back to
 * single-stream download.
 *
 * @param jobId - The generation job ID (used as gallery key).
 * @param filename - Server-side filename (e.g. "abc123.png").
 * @param prompt - The prompt used (stored for gallery display).
 * @param onProgress - Called with download progress updates.
 * @returns Object URL to the locally-saved file.
 */
export async function downloadToLocal(
  jobId: string,
  filename: string,
  prompt: string,
  onProgress?: (progress: DownloadProgress) => void,
): Promise<string> {
  const report = (
    phase: DownloadPhase,
    bytesReceived: number,
    totalBytes: number,
  ) => {
    onProgress?.({
      phase,
      bytesReceived,
      totalBytes,
      percent: totalBytes > 0 ? Math.round((bytesReceived / totalBytes) * 100) : 0,
    });
  };

  // ── 1. Download using parallel chunks when possible ───────────────
  report("streaming", 0, 0);

  const url = `${API_BASE}/stream/${encodeURIComponent(filename)}`;
  const { blob, totalBytes, mimeType } = await downloadWithParallelChunks(
    url,
    (received, total) => report("streaming", received, total),
  );

  // ── 2. Persist to OPFS (or keep as object URL) ────────────────────
  const opfsDir = await getOpfsDir();
  let objectUrl: string;
  let fileSize = blob.size;

  if (opfsDir) {
    report("saving", fileSize, totalBytes);
    const fileHandle = await opfsDir.getFileHandle(filename, { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(blob);
    await writable.close();

    const file = await fileHandle.getFile();
    objectUrl = URL.createObjectURL(file);
  } else {
    report("saving", fileSize, totalBytes);
    objectUrl = URL.createObjectURL(blob);
  }

  // ── 3. Register in IndexedDB ──────────────────────────────────────
  const asset: GalleryAsset = {
    id: jobId,
    filename,
    mimeType,
    size: fileSize,
    prompt,
    savedAt: Date.now(),
    persisted: opfsDir !== null,
  };

  await putAsset(asset);
  report("ready", fileSize, totalBytes);

  return objectUrl;
}

/* ── Deletion & Cleanup ───────────────────── */

/** Delete a single asset from IndexedDB and its file from OPFS. */
export async function deleteAsset(id: string): Promise<void> {
  // Remove metadata from IndexedDB
  const db = await openDB();
  const asset = await getAsset(id);
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });

  // Remove file from OPFS
  if (asset?.filename) {
    try {
      const dir = await getOpfsDir();
      if (dir) await dir.removeEntry(asset.filename);
    } catch { /* file may already be gone */ }
  }
}

/**
 * Purge OPFS files + IDB metadata older than `maxAgeMs`.
 * Default: 24 hours. Returns the number of items removed.
 */
export async function purgeOldAssets(maxAgeMs = 24 * 60 * 60 * 1000): Promise<number> {
  const assets = await getAllAssets();
  const cutoff = Date.now() - maxAgeMs;
  const stale = assets.filter((a) => a.savedAt < cutoff);

  for (const asset of stale) {
    await deleteAsset(asset.id);
  }

  return stale.length;
}

/**
 * Check if OPFS is supported in this browser.
 */
export function isOPFSSupported(): boolean {
  return typeof navigator !== "undefined" && "storage" in navigator && "getDirectory" in navigator.storage;
}
