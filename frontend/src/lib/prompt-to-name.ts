/* ─────────────────────────────────────────────
 * AuraGen — Prompt-to-Name
 * Generates meaningful, filesystem-safe names
 * from generation prompts for downloads & display.
 * ───────────────────────────────────────────── */

/** Words to skip when building the name (articles, prepositions, etc.) */
const STOP_WORDS = new Set([
  "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
  "but", "is", "are", "was", "were", "be", "been", "being", "with",
  "from", "by", "as", "into", "this", "that", "it", "its",
]);

/**
 * Convert a generation prompt into a clean, readable display name.
 * Example: "A beautiful sunset over snowy mountains" → "Beautiful Sunset Over Snowy Mountains"
 */
export function promptToDisplayName(prompt: string): string {
  if (!prompt || !prompt.trim()) return "Untitled";

  // Clean up: remove special chars, extra spaces
  const cleaned = prompt
    .replace(/[^\w\s-]/g, " ")   // strip non-word chars except hyphens
    .replace(/\s+/g, " ")         // collapse whitespace
    .trim();

  // Split into words, remove stop words from the beginning
  const words = cleaned.split(" ").filter(Boolean);
  if (words.length === 0) return "Untitled";

  // Title-case the words, skip leading stop words
  const titled = words
    .filter((w, i) => i === 0 || !STOP_WORDS.has(w.toLowerCase()))
    .slice(0, 6) // max 6 words for readability
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase());

  return titled.join(" ") || "Untitled";
}

/**
 * Convert a generation prompt into a filesystem-safe filename.
 * Example: "A beautiful sunset over mountains" → "beautiful-sunset-over-mountains-a3b2c1d4.png"
 *
 * @param prompt - The generation prompt
 * @param mode - "image" | "video" | "pose"
 * @param jobId - Job ID (first 8 chars used as suffix for uniqueness)
 */
export function promptToFilename(
  prompt: string,
  mode: "image" | "video" | "pose" | string,
  jobId: string,
): string {
  const ext = mode === "video" ? "mp4" : "png";
  const idSuffix = jobId.slice(0, 8);

  if (!prompt || !prompt.trim()) {
    return `auragen-${idSuffix}.${ext}`;
  }

  // Clean: lowercase, replace non-alphanumeric with hyphens
  const slug = prompt
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")    // strip special chars
    .replace(/\s+/g, "-")        // spaces to hyphens
    .replace(/-+/g, "-")         // collapse multiple hyphens
    .replace(/^-|-$/g, "");      // trim leading/trailing hyphens

  // Take first ~50 chars worth of the slug for the filename
  const words = slug.split("-").filter(Boolean);
  let name = "";
  for (const word of words) {
    if (name.length + word.length + 1 > 50) break;
    name += (name ? "-" : "") + word;
  }

  if (!name) {
    return `auragen-${idSuffix}.${ext}`;
  }

  return `${name}-${idSuffix}.${ext}`;
}
