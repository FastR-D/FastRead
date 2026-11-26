import { assetUrl } from './urls'
let engine: Promise<any> | undefined
export function pdfEngine() {
  const url = new URL(assetUrl('/vendor/pdfjs/pdf.js?v=4.10.38'), window.location.origin).href
  return (engine ||= import(/* @vite-ignore */ url)
    .then(pdf => {
      pdf.GlobalWorkerOptions.workerSrc = assetUrl('/vendor/pdfjs/pdf.worker.js?v=4.10.38')
      return pdf
    })
    .catch(error => {
      engine = undefined
      throw error
    }))
}
