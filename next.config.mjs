/** @type {import('next').NextConfig} */
const nextConfig = {
  // Strict mode enabled: TypeScript and ESLint failures will fail the build.
  // If you ever need to skip a check during a migration, do it for one
  // build with `NEXT_DISABLE_ESLINT=1 npm run build`, then fix the underlying
  // problem and remove the override. Do not add ignoreBuildErrors /
  // ignoreDuringBuilds back here.
  images: {
    unoptimized: true,
  },
}

export default nextConfig
