import { defineConfig, presetWind3 } from 'unocss'
import { fastUIContent, presetFastUI } from '@fastrd/ui-foundation/uno'

// FastUI owns appearance; standard utilities only arrange the application panels.
export default defineConfig({
  content: fastUIContent,
  presets: [presetWind3(), presetFastUI()],
})
