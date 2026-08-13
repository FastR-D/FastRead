import type { ReactNode, FC } from 'react'
// import "@/global.css"
import { Toaster } from 'react-hot-toast'

interface RootLayoutProps {
  children: ReactNode
}

export const metadata = {
  title: 'FastRead',
  description: '学术论文阅读报告与可审计证据层',
}

const RootLayout: FC<RootLayoutProps> = ({ children }) => {
  return (
    <div className="min-h-screen bg-neutral-100 font-sans text-neutral-900">
      <Toaster
        position="top-center" // 顶部居中显示
        toastOptions={{
          style: {
            borderRadius: '8px',
            background: '#333',
            color: '#fff',
          },
        }}
      />
      {children}
    </div>
  )
}

export default RootLayout
