/** @type {import('next').NextConfig} */
const nextConfig = {
  // Supabase is read server-side only; nothing here needs the client bundle.
  reactStrictMode: true,
};

export default nextConfig;
