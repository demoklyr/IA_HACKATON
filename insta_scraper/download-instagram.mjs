import { createWriteStream } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const MAX_DOWNLOAD_BYTES = 250 * 1024 * 1024;

function usage() {
  console.error(
    "Usage: npm run download -- <instagram-post-url> [--out <directory>] [--headed] [--wait <ms>]",
  );
  process.exit(1);
}

function parseArgs(argv) {
  const options = { url: null, out: null, headed: false, waitMs: 5_000 };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--headed") options.headed = true;
    else if (arg === "--out") options.out = argv[++index] ?? usage();
    else if (arg === "--wait") options.waitMs = Number(argv[++index]);
    else if (!options.url) options.url = arg;
    else usage();
  }

  if (!options.url || !Number.isFinite(options.waitMs) || options.waitMs < 0) {
    usage();
  }
  return options;
}

function validateInstagramUrl(value) {
  const url = new URL(value);
  const hostname = url.hostname.toLowerCase();
  const isInstagram =
    hostname === "instagram.com" || hostname.endsWith(".instagram.com");
  const match = url.pathname.match(/^\/(?:p|reel|reels|tv)\/([^/]+)/);

  if (url.protocol !== "https:" || !isInstagram || !match) {
    throw new Error("Expected a public Instagram post or reel URL");
  }

  return {
    url: `${url.origin}${url.pathname}`,
    shortcode: match[1],
  };
}

async function extractPost(instagramUrl, shortcode, options) {
  const browser = await chromium.launch({ headless: !options.headed });

  try {
    const context = await browser.newContext({
      locale: "en-US",
      viewport: { width: 1440, height: 1000 },
    });
    const page = await context.newPage();
    const response = await page.goto(instagramUrl, {
      waitUntil: "domcontentloaded",
      timeout: 45_000,
    });

    if (!response?.ok()) {
      throw new Error(`Instagram returned HTTP ${response?.status() ?? "unknown"}`);
    }

    await page.waitForTimeout(options.waitMs);

    return await page.evaluate((expectedShortcode) => {
      for (const script of document.querySelectorAll('script[type="application/json"]')) {
        let root;
        try {
          root = JSON.parse(script.textContent);
        } catch {
          continue;
        }

        const stack = [root];
        while (stack.length > 0) {
          const value = stack.pop();
          if (!value || typeof value !== "object") continue;

          const isRequestedPost =
            value.code === expectedShortcode || value.shortcode === expectedShortcode;
          if (isRequestedPost && Array.isArray(value.video_versions)) {
            const video = value.video_versions.find(({ url }) => url);
            const thumbnail = value.image_versions2?.candidates?.find(({ url }) => url);
            const dashStreams = [];

            if (value.video_dash_manifest) {
              const xml = new DOMParser().parseFromString(
                value.video_dash_manifest,
                "application/xml",
              );

              for (const representation of xml.querySelectorAll("Representation")) {
                const adaptationSet = representation.parentElement;
                const mimeType =
                  representation.getAttribute("mimeType") ??
                  adaptationSet?.getAttribute("mimeType") ??
                  "";
                const contentType =
                  representation.getAttribute("contentType") ??
                  adaptationSet?.getAttribute("contentType") ??
                  mimeType.split("/")[0];
                const url = representation.querySelector("BaseURL")?.textContent;

                if (url && (contentType === "video" || contentType === "audio")) {
                  dashStreams.push({
                    contentType,
                    mimeType,
                    bandwidth: Number(representation.getAttribute("bandwidth")) || 0,
                    width: Number(representation.getAttribute("width")) || null,
                    height: Number(representation.getAttribute("height")) || null,
                    url: url.replaceAll("&amp;", "&"),
                  });
                }
              }
            }

            const bestDashStream = (contentType) =>
              dashStreams
                .filter((stream) => stream.contentType === contentType)
                .sort((left, right) => right.bandwidth - left.bandwidth)[0] ?? null;

            return {
              shortcode: expectedShortcode,
              username: value.user?.username ?? null,
              caption: value.caption?.text ?? "",
              takenAt: value.taken_at ?? null,
              width: value.original_width ?? video?.width ?? null,
              height: value.original_height ?? video?.height ?? null,
              durationSeconds: value.video_duration ?? null,
              videoUrl: video?.url?.replaceAll("&amp;", "&") ?? null,
              thumbnailUrl: thumbnail?.url?.replaceAll("&amp;", "&") ?? null,
              separateStreams: {
                video: bestDashStream("video"),
                audio: bestDashStream("audio"),
              },
            };
          }

          if (Array.isArray(value)) stack.push(...value);
          else stack.push(...Object.values(value));
        }
      }

      return null;
    }, shortcode);
  } finally {
    await browser.close();
  }
}

async function downloadFile(url, destination, instagramUrl) {
  if (!url) return null;

  const response = await fetch(url, {
    redirect: "follow",
    headers: { referer: instagramUrl },
  });
  if (!response.ok || !response.body) {
    throw new Error(`Download failed with HTTP ${response.status}: ${url}`);
  }

  const contentLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(contentLength) && contentLength > MAX_DOWNLOAD_BYTES) {
    throw new Error(`Refusing a download larger than ${MAX_DOWNLOAD_BYTES} bytes`);
  }

  await pipeline(Readable.fromWeb(response.body), createWriteStream(destination));
  return {
    path: destination,
    contentType: response.headers.get("content-type"),
    bytes: Number.isFinite(contentLength) ? contentLength : null,
  };
}

const options = parseArgs(process.argv.slice(2));
const post = validateInstagramUrl(options.url);
const outputDirectory = path.resolve(options.out ?? `downloads/${post.shortcode}`);
await mkdir(outputDirectory, { recursive: true });

const metadata = await extractPost(post.url, post.shortcode, options);
if (!metadata?.videoUrl) {
  throw new Error(
    "No direct video URL was found. The post may be private, unavailable, or Instagram may have changed its page data.",
  );
}

const video = await downloadFile(
  metadata.videoUrl,
  path.join(outputDirectory, "video.mp4"),
  post.url,
);
const videoOnly = await downloadFile(
  metadata.separateStreams?.video?.url,
  path.join(outputDirectory, "video-only.mp4"),
  post.url,
);
const audioOnly = await downloadFile(
  metadata.separateStreams?.audio?.url,
  path.join(outputDirectory, "audio-only.m4a"),
  post.url,
);
const thumbnail = await downloadFile(
  metadata.thumbnailUrl,
  path.join(outputDirectory, "thumbnail.jpg"),
  post.url,
);

await writeFile(path.join(outputDirectory, "caption.txt"), metadata.caption, "utf8");
await writeFile(
  path.join(outputDirectory, "metadata.json"),
  `${JSON.stringify({ sourceUrl: post.url, ...metadata }, null, 2)}\n`,
  "utf8",
);

console.log(
  JSON.stringify(
    {
      outputDirectory,
      shortcode: metadata.shortcode,
      username: metadata.username,
      video,
      videoOnly,
      audioOnly,
      thumbnail,
      caption: path.join(outputDirectory, "caption.txt"),
      metadata: path.join(outputDirectory, "metadata.json"),
    },
    null,
    2,
  ),
);
