const fs = require("fs");
const path = require("path");

const vendorDir = path.join(__dirname, "..", "static", "vendor");
fs.mkdirSync(vendorDir, { recursive: true });

const files = [
  ["node_modules/alpinejs/dist/cdn.min.js", "static/vendor/alpine.min.js"],
  ["node_modules/video.js/dist/video.min.js", "static/vendor/video.min.js"],
  ["node_modules/video.js/dist/video-js.css", "static/vendor/video-js.css"],
];

for (const [src, dest] of files) {
  const srcPath = path.join(__dirname, "..", src);
  const destPath = path.join(__dirname, "..", dest);
  fs.copyFileSync(srcPath, destPath);
  console.log(`Copied ${src} -> ${dest}`);
}
