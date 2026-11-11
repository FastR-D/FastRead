import { initColorMode } from '@fastrd/ui-foundation'

// Settings/account surfaces opt in; PDF and reading surfaces retain their own styles.
export const colorMode = initColorMode({ storageKey: 'fastread.theme' })
