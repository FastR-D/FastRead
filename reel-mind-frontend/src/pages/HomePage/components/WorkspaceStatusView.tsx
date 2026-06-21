import { FC } from 'react'
import { Link2, SearchCheck } from 'lucide-react'
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

const FLOW_STEPS = [
  { n: '01', title: '解析输入 · 提取主张', desc: '识别可核实的事实性陈述与数值型证据' },
  { n: '02', title: '联网检索 · 抓取信源', desc: '检索权威来源并抓取正文，分级 A/B/C/D 信源' },
  { n: '03', title: '交叉判定 · 生成报告', desc: '比对正文证据，给出支持/反证/不足的可审计结论' },
]

const WorkspaceStatusView: FC<WorkspaceStatusViewProps> = ({
  mode,
  steps = [],
  currentStep = '',
}) => {
  if (mode === 'loading') {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center bg-slate-50/40 px-6">
        <div className="w-full max-w-2xl rounded-md border border-slate-200 bg-white px-6 py-5">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <SearchCheck className="h-4 w-4 text-slate-700" />
              <span className="text-sm font-semibold text-slate-900">正在执行联网核实</span>
            </div>
            <span className="font-mono text-[11px] uppercase tracking-wide text-slate-400">
              {currentStep || 'RUNNING'}
            </span>
          </div>
          <StepBar steps={steps} currentStep={currentStep} />
        </div>

        <div className="mt-6 flex items-center gap-2 text-xs text-slate-500">
          <Loading className="h-4 w-4" />
          <span>深度核验会检索、抓取原文并交叉判定，可能需要更长时间。</span>
        </div>
      </div>
    )
  }

  if (mode === 'empty') {
    return (
      <div className="flex h-full w-full items-center justify-center bg-slate-50/40 px-6">
        <div className="flex max-w-sm flex-col items-center text-center">
          <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-sm border border-slate-200 bg-white text-slate-400">
            <Link2 className="h-4 w-4" />
          </div>
          <p className="text-sm font-semibold text-slate-800">等待核实输入</p>
          <p className="mt-1.5 text-xs leading-5 text-slate-500">
            在左侧粘贴网页 URL 或待核实文本，点击"开始联网核实"。
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-full w-full items-center justify-center bg-slate-50/40 px-6 py-10">
      <div className="w-full max-w-lg rounded-md border border-slate-200 bg-white">
        {/* 头部 */}
        <div className="flex items-center gap-3 border-b border-slate-200 px-5 py-4">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm bg-slate-900 text-white">
            <SearchCheck className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-900">核实工作台已就绪</div>
            <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-slate-400">
              Awaiting Verification Input
            </div>
          </div>
        </div>

        {/* 说明 */}
        <div className="px-5 py-4">
          <p className="text-xs leading-5 text-slate-600">
            在左侧粘贴网页 URL 或待核实文本并点击"开始联网核实"，系统会提取主张、联网检索、抓取正文并生成可审计的证据报告。
          </p>
        </div>

        {/* 流程 */}
        <ol className="divide-y divide-slate-100 border-t border-slate-200">
          {FLOW_STEPS.map(step => (
            <li key={step.n} className="flex items-start gap-3 px-5 py-3">
              <span className="mt-0.5 font-mono text-[11px] font-semibold tabular-nums text-slate-400">
                {step.n}
              </span>
              <div className="min-w-0">
                <div className="text-xs font-semibold text-slate-800">{step.title}</div>
                <div className="mt-0.5 text-[11px] leading-5 text-slate-500">{step.desc}</div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  )
}

export default WorkspaceStatusView
