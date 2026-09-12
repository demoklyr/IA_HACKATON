import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

function usage() {
  console.error(
    "Usage: npm run inspect -- <instagram-post-url> [--headed] [--out <html-file>] [--wait <ms>]",
  );
  process.exit(1);
}

function parseArgs(argv) {
  const options = {
    url: undefined,
    headed: false,
    out: path.resolve("work/instagram-dom.html"),
    waitMs: 5_000,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];

    if (arg === "--headed") {
      options.headed = true;
    } else if (arg === "--out") {
      options.out = path.resolve(argv[++index] ?? usage());
    } else if (arg === "--wait") {
      options.waitMs = Number(argv[++index]);
    } else if (!options.url) {
      options.url = arg;
    } else {
      usage();
    }
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
  const isPost = /^\/(p|reel|reels|tv)\/[^/]+\/?/.test(url.pathname);

  if (url.protocol !== "https:" || !isInstagram || !isPost) {
    throw new Error(
      "Expected a public https://www.instagram.com/p|reel|reels|tv/... URL",
    );
  }

  // Remove tracking parameters while preserving the post shortcode.
  return `${url.origin}${url.pathname}`;
}

const options = parseArgs(process.argv.slice(2));
const instagramUrl = validateInstagramUrl(options.url);
const shortcode = new URL(instagramUrl).pathname.split("/").filter(Boolean).at(-1);

const browser = await chromium.launch({ headless: !options.headed });

try {
  const context = await browser.newContext({
    locale: "en-US",
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage();

  const mainResponse = await page.goto(instagramUrl, {
    waitUntil: "domcontentloaded",
    timeout: 45_000,
  });

  // Give Instagram's React application time to hydrate and add media elements.
  await page.waitForTimeout(options.waitMs);

  const result = await page.evaluate((shortcode) => {
    const meta = (selector) =>
      document.querySelector(selector)?.getAttribute("content")?.trim() || null;

    // Instagram includes the selected reel and suggested reels in JSON scripts.
    // Match by shortcode so we do not accidentally return a suggested video.
    const findStructuredPost = () => {
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

          if (
            (value.code === shortcode || value.shortcode === shortcode) &&
            Array.isArray(value.video_versions)
          ) {
            return value;
          }

          if (Array.isArray(value)) {
            stack.push(...value);
          } else {
            stack.push(...Object.values(value));
          }
        }
      }

      return null;
    };

    const structuredPost = findStructuredPost();
    const cleanUrl = (value) =>
      typeof value === "string" ? value.replaceAll("&amp;", "&") : null;

    const descriptionCandidates = [
      {
        source: `script JSON node[code="${shortcode}"].caption.text`,
        value: structuredPost?.caption?.text?.trim() || null,
      },
      {
        source: 'meta[name="description"]',
        value: meta('meta[name="description"]'),
      },
      {
        source: 'meta[property="og:description"]',
        value: meta('meta[property="og:description"]'),
      },
      {
        source: 'meta[name="twitter:description"]',
        value: meta('meta[name="twitter:description"]'),
      },
    ].filter(({ value }) => value);

    const videoCandidates = [];
    const addVideo = (source, value) => {
      const url = cleanUrl(value);
      if (url && !videoCandidates.some((item) => item.value === url)) {
        videoCandidates.push({ source, value: url });
      }
    };

    structuredPost?.video_versions?.forEach((version, index) => {
      addVideo(
        `script JSON node[code="${shortcode}"].video_versions[${index}].url`,
        version.url,
      );
    });

    document.querySelectorAll("video").forEach((video, index) => {
      addVideo(`video[${index}].currentSrc`, video.currentSrc);
      addVideo(`video[${index}].src`, video.src);
      video.querySelectorAll("source").forEach((source, sourceIndex) => {
        addVideo(`video[${index}] source[${sourceIndex}].src`, source.src);
      });
    });
    addVideo('meta[property="og:video:secure_url"]', meta('meta[property="og:video:secure_url"]'));
    addVideo('meta[property="og:video"]', meta('meta[property="og:video"]'));
    addVideo('meta[name="twitter:player:stream"]', meta('meta[name="twitter:player:stream"]'));

    const thumbnailCandidates = [];
    const addThumbnail = (source, value) => {
      const url = cleanUrl(value);
      if (url && !thumbnailCandidates.some((item) => item.value === url)) {
        thumbnailCandidates.push({ source, value: url });
      }
    };

    structuredPost?.image_versions2?.candidates?.forEach((candidate, index) => {
      addThumbnail(
        `script JSON node[code="${shortcode}"].image_versions2.candidates[${index}].url`,
        candidate.url,
      );
    });

    document.querySelectorAll("video[poster]").forEach((video, index) => {
      addThumbnail(`video[${index}].poster`, video.poster);
    });
    addThumbnail('meta[property="og:image"]', meta('meta[property="og:image"]'));
    addThumbnail('meta[name="twitter:image"]', meta('meta[name="twitter:image"]'));

    return {
      finalUrl: location.href,
      title: document.title,
      shortcode,
      description: descriptionCandidates[0]?.value ?? null,
      videoUrl: videoCandidates[0]?.value ?? null,
      thumbnailUrl: thumbnailCandidates[0]?.value ?? null,
      candidates: {
        descriptions: descriptionCandidates,
        videos: videoCandidates,
        thumbnails: thumbnailCandidates,
      },
      elementCounts: {
        videos: document.querySelectorAll("video").length,
        images: document.querySelectorAll("img").length,
        scripts: document.querySelectorAll("script").length,
      },
    };
  }, shortcode);

  const html = await page.content();
  await mkdir(path.dirname(options.out), { recursive: true });
  await writeFile(options.out, html, "utf8");

  console.log(
    JSON.stringify(
      {
        httpStatus: mainResponse?.status() ?? null,
        savedDom: options.out,
        ...result,
      },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
}
