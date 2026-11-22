import fs from "node:fs";
import path from "node:path";
import type { NextConfig } from "next";

const BUILD_ID = Date.now().toString(36);

try {
  const publicDir = path.join(__dirname, "public");
  fs.mkdirSync(publicDir, { recursive: true });
  fs.writeFileSync(path.join(publicDir, "build-id.txt"), BUILD_ID, "utf8");
} catch {
  // ignore write error in read-only environments
}

const nextConfig: NextConfig = {
  output: "export",
  images: {
    unoptimized: true,
  },
  env: {
    NEXT_PUBLIC_BUILD_ID: BUILD_ID,
  },
};

export default nextConfig;
