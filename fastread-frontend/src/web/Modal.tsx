import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { useRef, type ReactNode } from 'react'

export default function Modal({
  title,
  description,
  children,
  onClose,
  wide = false,
}: {
  title: string
  description: string
  children: ReactNode
  onClose: () => void
  wide?: boolean
}) {
  const opener = useRef(document.activeElement as HTMLElement | null)
  return (
    <Dialog.Root
      open
      onOpenChange={open => {
        if (!open) onClose()
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="product-overlay" />
        <Dialog.Content
          className={`product-dialog ${wide ? 'wide' : ''}`}
          onCloseAutoFocus={event => {
            event.preventDefault()
            opener.current?.focus()
          }}
        >
          <div className="dialog-heading">
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close className="icon-button quiet" aria-label="关闭对话框">
              <X size={18} />
            </Dialog.Close>
          </div>
          <Dialog.Description>{description}</Dialog.Description>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
