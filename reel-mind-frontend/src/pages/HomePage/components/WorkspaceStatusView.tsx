import { FC } from 'react'
import { Link2, Sparkles } from 'lucide-react'
import Idle from '@/components/Lottie/Idle.tsx'
import Loading from '@/components/Lottie/Loading.tsx'
import StepBar from '@/pages/HomePage/components/StepBar.tsx'

interface Step {
  label: string
  key: string
}

interface WorkspaceStatusViewProps {
  mode: 'idle' | 'loading' | 'empty'
  steps?: Step[]
  currentStep?: string
}

const platformHints = ['B 站', '抖音精选', '快手']

const WorkspaceStatusView: FC<WorkspaceStatusViewProps> = ({
  mode,
  steps = [],
  currentStep = '',
}) => {
  if (mode === 'loading') {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center px-6">
        <div className="w-full max-w-2xl">
          <StepBar steps={steps} currentStep={currentStep} />
        </div>

        <div className="mt-12 flex flex-col items-center gap-3 text-neutral-600">
          <Loading className="h-6 w-6" />
          <p className="text-base font-semibold text-neutral-800">正在生成笔记，请稍候…</p>
          <p className="text-xs text-neutral-500">
            处理时间取决于视频长度，通常需要几秒到几分钟
          </p>
        </div>
      </div>
    )
  }

  if (mode === 'empty') {
    return (
      <div className="flex h-full w-full items-center justify-center px-6">
        <div className="flex max-w-md flex-col items-center text-center">
          <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-full border border-neutral-200 bg-white text-neutral-500">
            <Link2 className="h-5 w-5" />
          </div>
          <p className="text-base font-semibold text-neutral-800">
            输入视频链接并点击"生成笔记"
          </p>
          <p className="mt-2 text-xs leading-5 text-neutral-500">
            支持抖音精选、B站和快手视频
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-full w-full flex-col items-center justify-center px-6">
      <div className="flex flex-col items-center">
        <Idle />
        <div className="mt-2 flex flex-col items-center text-center">
          <p className="text-lg font-semibold text-neutral-800">
            输入视频链接并点击"生成笔记"
          </p>
          <p className="mt-2 text-xs leading-5 text-neutral-500">
            粘贴链接，自动下载、转写并整理为结构化笔记
          </p>
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          {platformHints.map(name => (
            <span
              key={name}
              className="inline-flex items-center rounded-full border border-neutral-200 bg-white px-2.5 py-0.5 text-xs text-neutral-600"
            >
              {name}
            </span>
          ))}
        </div>

        <div className="mt-6 inline-flex items-center gap-1.5 text-xs text-neutral-500">
          <Sparkles className="h-3.5 w-3.5" />
          <span>工作区已就绪</span>
        </div>
      </div>
    </div>
  )
}

export default WorkspaceStatusView
