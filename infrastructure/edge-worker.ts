/**
 * ─────────────────────────────────────────────────────────────
 * AuraGen — Cloudflare Worker for Edge-Cached Media Delivery
 * ─────────────────────────────────────────────────────────────
 *
 * Deployed as a Cloudflare Worker (or compatible edge runtime)
 * that intercepts requests to /outputs/* and serves cached,
 * compressed variants based on the client's network tier.
 *
 * Features:
 *   1. Reads X-Network-Tier header from the client
 *   2. Falls back to Client Hints (Downlink, ECT, Save-Data)
 *   3. Serves tier-appropriate variant (thumb/preview/full)
 *   4. Uses Cloudflare Cache API with tier-specific TTLs
 *   5. Adds Vary headers for correct cache partitioning
 *
 * Deployment:
 *   wrangler publish infrastructure/edge-worker.ts
 *
 * Configuration (wrangler.toml):
 *   [vars]
 *   ORIGIN = "https://api.auragen.app"
 *   CACHE_TTL_FULL = "86400"
 *   CACHE_TTL_PREVIEW = "604800"
 *   CACHE_TTL_THUMBNAIL = "2592000"
 */

interface Env {
  ORIGIN: string;
  CACHE_TTL_FULL: string;
  CACHE_TTL_PREVIEW: string;
  CACHE_TTL_THUMBNAIL: string;
}

type NetworkTier = "low" | "medium" | "high";

/**
 * Detect the client's network tier from headers.
 * Priority: X-Network-Tier > Save-Data > ECT > Downlink > default high
 */
function detectTier(request: Request): NetworkTier {
  // 1. Explicit tier header (set by our frontend)
  const explicit = request.headers.get("X-Network-Tier");
  if (explicit && ["low", "medium", "high"].includes(explicit.toLowerCase())) {
    return explicit.toLowerCase() as NetworkTier;
  }

  // 2. Save-Data hint (Chrome, Edge)
  if (request.headers.get("Save-Data") === "on") {
    return "low";
  }

  // 3. ECT (Effective Connection Type)
  const ect = request.headers.get("ECT");
  if (ect) {
    if (ect === "slow-2g" || ect === "2g") return "low";
    if (ect === "3g") return "medium";
    return "high";
  }

  // 4. Downlink header (Mbps)
  const downlink = parseFloat(request.headers.get("Downlink") ?? "");
  if (!isNaN(downlink)) {
    if (downlink < 1.5) return "low";
    if (downlink < 7) return "medium";
    return "high";
  }

  return "high";
}

/**
 * Map a filename to its tier-appropriate variant.
 *
 * Given "abc123.png" and tier "low", returns "abc123_thumb.jpg".
 * Given "abc123.mp4" and tier "medium", returns "abc123_preview.mp4".
 */
function resolveVariant(filename: string, tier: NetworkTier): string {
  if (tier === "high") return filename;

  const dotIdx = filename.lastIndexOf(".");
  if (dotIdx === -1) return filename;

  const stem = filename.substring(0, dotIdx);
  const ext = filename.substring(dotIdx).toLowerCase();
  const isVideo = [".mp4", ".webm", ".avi", ".mov"].includes(ext);

  if (tier === "low") {
    // Thumbnail: always JPEG for images, JPEG poster for video
    return `${stem}_thumb.jpg`;
  }

  // Medium tier: compressed preview
  if (isVideo) {
    return `${stem}_preview.mp4`;
  }
  return `${stem}_preview.jpg`;
}

/**
 * Get the TTL (in seconds) for the given tier.
 */
function getTTL(tier: NetworkTier, env: Env): number {
  switch (tier) {
    case "low":
      return parseInt(env.CACHE_TTL_THUMBNAIL, 10) || 2592000;
    case "medium":
      return parseInt(env.CACHE_TTL_PREVIEW, 10) || 604800;
    case "high":
      return parseInt(env.CACHE_TTL_FULL, 10) || 86400;
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Only intercept /outputs/* requests
    if (!url.pathname.startsWith("/outputs/")) {
      // Pass through to origin
      return fetch(new Request(env.ORIGIN + url.pathname + url.search, request));
    }

    const tier = detectTier(request);
    const originalFilename = url.pathname.split("/").pop() ?? "";
    const variantFilename = resolveVariant(originalFilename, tier);

    // Build the cache key including tier for correct partitioning
    const cacheKey = new URL(url);
    cacheKey.pathname = `/outputs/${variantFilename}`;
    cacheKey.searchParams.set("_tier", tier);

    // Check Cloudflare Cache
    const cache = caches.default;
    let response = await cache.match(new Request(cacheKey.toString()));

    if (!response) {
      // Fetch from origin
      const originUrl = `${env.ORIGIN}/outputs/${variantFilename}`;
      const originResponse = await fetch(originUrl, {
        headers: {
          "X-Network-Tier": tier,
        },
      });

      if (!originResponse.ok) {
        // Variant doesn't exist — fall back to original
        if (variantFilename !== originalFilename) {
          const fallbackUrl = `${env.ORIGIN}/outputs/${originalFilename}`;
          const fallback = await fetch(fallbackUrl);
          if (fallback.ok) {
            response = new Response(fallback.body, {
              status: fallback.status,
              headers: new Headers(fallback.headers),
            });
            response.headers.set("X-Served-Tier", "full");
            response.headers.set("X-Fallback", "true");
          } else {
            return new Response("Not Found", { status: 404 });
          }
        } else {
          return new Response("Not Found", { status: 404 });
        }
      } else {
        response = new Response(originResponse.body, {
          status: originResponse.status,
          headers: new Headers(originResponse.headers),
        });
      }

      // Set cache control and custom headers
      const ttl = getTTL(tier, env);
      response.headers.set("Cache-Control", `public, max-age=${ttl}, s-maxage=${ttl}`);
      response.headers.set("X-Served-Tier", tier);
      response.headers.set("X-Network-Tier-Detected", tier);
      response.headers.set("Vary", "X-Network-Tier, ECT, Save-Data, Downlink");

      // Store in edge cache
      const cacheResponse = response.clone();
      await cache.put(new Request(cacheKey.toString()), cacheResponse);
    }

    return response;
  },
};
