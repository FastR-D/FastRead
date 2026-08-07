import fs from 'fs-extra'
import type { Manifest } from 'webextension-polyfill'
import type PkgType from '../package.json'
import { isDev, port, r } from '../scripts/utils'

type ManifestWithBrowserSettings = Manifest.WebExtensionManifest & {
  browser_specific_settings?: {
    gecko?: {
      id: string
    }
  }
}

export async function getManifest() {
  const pkg = await fs.readJSON(r('package.json')) as typeof PkgType

  // update this file to update this manifest.json
  // can also be conditional based on your need
  const manifest: ManifestWithBrowserSettings = {
    manifest_version: 3,
    name: 'FastRead Verification',
    version: pkg.version,
    description: 'Start FastRead online verification tasks from the current page or selected text.',
    action: {
      default_icon: {
        16: 'assets/icon-16.png',
        48: 'assets/icon-48.png',
        128: 'assets/icon-128.png',
      },
      default_popup: 'dist/popup/index.html',
    },
    icons: {
      16: 'assets/icon-16.png',
      48: 'assets/icon-48.png',
      128: 'assets/icon-128.png',
    },
    permissions: [
      'tabs',
      'storage',
      'cookies',
    ],
    host_permissions: [
      '*://*.douyin.com/*',
      'http://localhost/*',
      'http://127.0.0.1/*',
    ],
    content_security_policy: {
      extension_pages: isDev
        // this is required on dev for Vite script to load
        ? `script-src \'self\' http://localhost:${port}; object-src \'self\'`
        : 'script-src \'self\'; object-src \'self\'',
    },
    browser_specific_settings: {
      gecko: {
        id: 'fastread-verification@local',
      },
    },
  }

  return manifest
}
