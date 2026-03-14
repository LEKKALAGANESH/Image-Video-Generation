# frontend/public/ -- Static Assets Directory

This directory should contain static assets served by Next.js at the site root.

## Required files

- **favicon.ico** -- Browser tab icon for AuraGen.
- **og-image.png** -- Open Graph image for social sharing (recommended 1200x630px).
- Any other static assets (logos, fonts, manifest files) that need to be served
  from the root URL path.

## Notes

- Files placed here are accessible at `/filename` in the browser (e.g., `/favicon.ico`).
- Do not place large media files here; use the backend outputs directory instead.
- Consider adding `robots.txt` and `site.webmanifest` for production deployments.
