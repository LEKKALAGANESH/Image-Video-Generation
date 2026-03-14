/**
 * ─────────────────────────────────────────────────────────────
 * AuraGen — CDN & Edge Configuration
 * ─────────────────────────────────────────────────────────────
 *
 * Defines the TTL strategy, cache key rules, and edge
 * configuration for network-aware asset delivery.
 *
 * This file serves as the source of truth for:
 *   1. Cloudflare Workers / AWS CloudFront Function config
 *   2. Cache-Control header generation
 *   3. Origin shield / purge strategy
 */

/* ── TTL Strategy ──────────────────────────────────────────── */

/**
 * Time-to-Live strategy balances storage cost vs delivery speed.
 *
 * Rationale:
 *   - Thumbnails are tiny (2–5 KB) and rarely change → cache 30 days
 *   - Previews are moderate (30–100 KB) and never change → cache 7 days
 *   - Full-res assets are large (0.5–5 MB) and immutable → cache 24h
 *     (shorter TTL since they cost more to store at edge nodes)
 *   - All generated assets are immutable (UUID-based filenames), so
 *     there is no cache invalidation concern for content changes.
 */
export const TTL_STRATEGY = {
  /** Thumbnails: 128px JPEG, ~3 KB — cache aggressively. */
  thumbnail: {
    maxAge: 2_592_000,    // 30 days
    sMaxAge: 2_592_000,   // 30 days at edge
    staleWhileRevalidate: 86_400,
    comment: "Tiny, immutable, cheap to store — max cache",
  },

  /** Previews: 480px JPEG, ~50 KB — cache for a week. */
  preview: {
    maxAge: 604_800,      // 7 days
    sMaxAge: 604_800,
    staleWhileRevalidate: 43_200,
    comment: "Moderate size, immutable — week-long cache",
  },

  /** Full-resolution: original PNG/MP4, 0.5–5 MB — cache 24h at edge. */
  full: {
    maxAge: 86_400,       // 24 hours
    sMaxAge: 86_400,
    staleWhileRevalidate: 3_600,
    comment: "Large files, expensive at edge — daily cache",
  },

  /** API responses: health check, negotiate, job status. */
  api: {
    maxAge: 0,
    sMaxAge: 0,
    comment: "Dynamic — never cache",
  },
} as const;

export type TierKey = keyof typeof TTL_STRATEGY;

/**
 * Generate a Cache-Control header string for the given tier.
 */
export function buildCacheControl(tier: TierKey): string {
  const config = TTL_STRATEGY[tier];
  if (config.maxAge === 0) return "no-store, no-cache";
  return [
    "public",
    `max-age=${config.maxAge}`,
    `s-maxage=${config.sMaxAge}`,
    `stale-while-revalidate=${config.staleWhileRevalidate}`,
  ].join(", ");
}

/* ── Cache Key Strategy ────────────────────────────────────── */

/**
 * Cache keys must be partitioned by network tier so that a "low"
 * request never gets a cached "high" response.
 *
 * Key format:  /outputs/{filename}?_tier={low|medium|high}
 *
 * Vary headers: X-Network-Tier, ECT, Save-Data, Downlink
 */
export const CACHE_KEY_CONFIG = {
  /** Headers to include in the Vary header for cache partitioning. */
  varyHeaders: ["X-Network-Tier", "ECT", "Save-Data", "Downlink"],

  /** Query param appended to cache keys for tier separation. */
  tierParam: "_tier",
} as const;

/* ── Edge Locations & Origin Shield ────────────────────────── */

/**
 * Recommended edge configuration for different providers.
 */
export const EDGE_CONFIG = {
  cloudflare: {
    /** Wrangler toml vars */
    vars: {
      ORIGIN: "https://api.auragen.app",
      CACHE_TTL_FULL: String(TTL_STRATEGY.full.maxAge),
      CACHE_TTL_PREVIEW: String(TTL_STRATEGY.preview.maxAge),
      CACHE_TTL_THUMBNAIL: String(TTL_STRATEGY.thumbnail.maxAge),
    },
    /** Routes to match */
    routes: [
      "auragen.app/outputs/*",
      "auragen.app/api/network/stream/*",
    ],
    /** Enable Cloudflare Polish for automatic WebP conversion. */
    polish: "lossy",
    /** Enable Argo Smart Routing for optimal origin fetches. */
    argo: true,
  },

  aws: {
    /** CloudFront distribution settings */
    distribution: {
      originDomain: "api.auragen.app",
      originShield: {
        enabled: true,
        region: "us-east-1",
      },
      behaviors: [
        {
          pathPattern: "/outputs/*",
          cachePolicyId: "custom-network-aware",
          viewerProtocolPolicy: "redirect-to-https",
          compress: true,
          headerWhitelist: ["X-Network-Tier", "Save-Data", "ECT", "Downlink"],
        },
      ],
    },
    /** S3 bucket policy for origin storage */
    s3: {
      bucket: "auragen-outputs",
      lifecycleRules: [
        { prefix: "*_thumb*", expirationDays: 90 },
        { prefix: "*_preview*", expirationDays: 30 },
        { prefix: "", expirationDays: 7, noncurrentVersionExpiration: 3 },
      ],
    },
  },
} as const;

/* ── Purge Strategy ────────────────────────────────────────── */

/**
 * Since all generated assets use UUID-based filenames, cache
 * invalidation is only needed when:
 *   1. A job is deleted by the user
 *   2. Storage cleanup runs (old assets beyond retention window)
 *
 * For both cases, purge by exact URL prefix:
 *   PURGE /outputs/{job_id}*
 *
 * This removes the full-res, preview, and thumbnail variants
 * in a single wildcard purge.
 */
export const PURGE_STRATEGY = {
  /** Purge all variants for a given job ID stem. */
  purgePattern: (jobId: string) => `/outputs/${jobId}*`,
  /** Maximum purge requests per minute (Cloudflare free plan: 1000). */
  rateLimitPerMinute: 500,
} as const;
