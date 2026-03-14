/* AuraGen — Media URL Resolver */

/**
 * Backend origin (without /api suffix).
 * Strips trailing /api from NEXT_PUBLIC_API_URL if present.
 */
const BACKEND_ORIGIN =
  (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    .replace(/\/api\/?$/, "");

/**
 * Resolve a backend-relative URL to an absolute URL loadable by the browser.
 * - "/api/outputs/abc.png" → "http://localhost:8000/api/outputs/abc.png"
 * - "/outputs/abc.png" → "http://localhost:8000/outputs/abc.png"
 * - "http://..." → returned as-is (already absolute)
 * - "blob:..." → returned as-is (local object URL)
 * - null/undefined → null
 */
export function resolveMediaUrl(url: string | undefined | null): string | null {
  if (!url) return null;
  // Already absolute or blob URL
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("blob:") || url.startsWith("data:")) {
    return url;
  }
  // Relative path from backend
  return `${BACKEND_ORIGIN}${url.startsWith("/") ? "" : "/"}${url}`;
}

/**
 * Given a result_url, determine the media type.
 */
export function getMediaType(url: string | undefined | null): "image" | "video" | "unknown" {
  if (!url) return "unknown";
  const lower = url.toLowerCase();
  if (lower.endsWith(".mp4") || lower.endsWith(".webm") || lower.endsWith(".mov") || lower.endsWith(".avi")) return "video";
  if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".webp") || lower.endsWith(".gif")) return "image";
  return "unknown";
}
