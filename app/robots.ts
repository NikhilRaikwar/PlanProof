import type { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
  const baseUrl =
    process.env.NEXT_PUBLIC_SITE_URL || 'https://planproof-web-lfrrer4z6q-el.a.run.app'

  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/workspace/', '/internal/', '/api/', '/v1/'],
      },
    ],
    sitemap: `${baseUrl}/sitemap.xml`,
  }
}
