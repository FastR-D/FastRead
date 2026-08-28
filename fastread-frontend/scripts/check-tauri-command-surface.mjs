import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const source = readFileSync(resolve(root, 'src-tauri/src/lib.rs'), 'utf8')

for (const forbidden of [
  'get_system_env_vars',
  'run_command_with_env',
  'update_sidecar_environment',
]) {
  if (source.includes(forbidden)) {
    throw new Error(`Unsafe generic Tauri command surface is present: ${forbidden}`)
  }
}

const handler = source.match(/\.invoke_handler\(tauri::generate_handler!\[([\s\S]*?)\]\)/)?.[1] || ''
const exposed = handler
  .split(',')
  .map((item) => item.trim())
  .filter(Boolean)
const allowed = new Set([
  'get_install_path_diagnostics',
  'restart_backend_sidecar',
])

for (const command of exposed) {
  if (!allowed.has(command)) {
    throw new Error(`Unexpected Tauri command exposed to the renderer: ${command}`)
  }
}

if (exposed.length !== allowed.size) {
  throw new Error(`Expected ${allowed.size} fixed Tauri commands, found ${exposed.length}`)
}

console.log(`Tauri command surface OK: ${exposed.join(', ')}`)
