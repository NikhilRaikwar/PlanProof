/** @type {import('next').NextConfig} */
const nextConfig = {
  // Cloud Run containers use the minimal standalone server output. Build-time
  // type errors intentionally fail the build; production must not mask them.
  output: 'standalone',
  images: {
    unoptimized: true,
  },
}

export default nextConfig
