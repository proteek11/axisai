/** @type {import('next').NextConfig} */
const nextConfig = {
  // Image domains
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '**.edzlms.com' },
      { protocol: 'https', hostname: 'img.youtube.com' },
      { protocol: 'https', hostname: 'i.vimeocdn.com' },
    ],
  },

  // Increase body size limit for large file uploads (videos up to 500 MB)
  // This applies to all API routes in App Router.
  experimental: {
    serverActions: {
      bodySizeLimit: '500mb',
    },
  },

  // Redirect legacy admin routes to their current equivalents
  async redirects() {
    return [
      {
        source: '/admin/token-budgets',
        destination: '/admin/tokens',
        permanent: true,
      },
      {
        source: '/admin/knowledge-base',
        destination: '/admin/kb',
        permanent: true,
      },
      {
        source: '/admin/catalogue',
        destination: '/admin/content',
        permanent: true,
      },
      {
        source: '/admin/departments',
        destination: '/admin/teams',
        permanent: true,
      },
    ];
  },

  // Security headers
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-XSS-Protection', value: '1; mode=block' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=()',
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
