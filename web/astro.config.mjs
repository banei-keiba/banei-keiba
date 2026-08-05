// @ts-check
import mdx from '@astrojs/mdx';
import { defineConfig } from 'astro/config';

// 独自ドメインを取得したら site を差し替える。
// それまでは noindex（src/layouts/Base.astro と public/robots.txt）で検索避けする。
export default defineConfig({
  site: 'https://banei-keiba.pages.dev',
  integrations: [mdx()],
  build: { format: 'directory' },
});
