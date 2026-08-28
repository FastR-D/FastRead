import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
import logo from '@/assets/icon.png'

export default function AboutPage() {
  return (
    <ScrollArea className={'h-full overflow-y-auto bg-white'}>
      <div className="container mx-auto px-4 py-12">
        {/* Hero Section */}
        <div className="mb-16 flex flex-col items-center justify-center text-center">
          <div className="mb-4 flex items-center gap-4">
            <img
              src={logo}
              alt="FastRead Logo"
              width={50}
              height={50}
              className="rounded-lg"
            />
            <h1 className="text-4xl font-bold">FastRead</h1>
          </div>
          <p className="text-muted-foreground mb-6 text-xl">
            从论文原文出发，把“读过”变成可回到页码核对的理解
          </p>

          <div className="mb-8 flex flex-wrap justify-center gap-2">
            <Badge variant="secondary">PDF / Paper URL</Badge>
            <Badge variant="secondary">Page-aware Citations</Badge>
            <Badge variant="secondary">React</Badge>
            <Badge variant="secondary">FastAPI</Badge>
            <Badge variant="secondary">Local-first</Badge>
          </div>
        </div>

        {/* Project Introduction */}
        <section className="mb-16">
          <h2 className="mb-6 text-center text-3xl font-bold">✨ 项目简介</h2>
          <div className="mx-auto max-w-3xl text-center">
            <p className="text-lg">
              FastRead 是一个面向论文深度阅读的本地应用。导入 PDF 或论文 URL 后，
              它会保留分页原文，生成关键问题报告，分开呈现方法、贡献、实验依据与局限，
              并将实质结论连回可核对的论文页码。
            </p>
          </div>
        </section>

        {/* Features Section */}
        <section className="mb-16">
          <h2 className="mb-8 text-center text-3xl font-bold">🔧 核心能力</h2>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {[
              { title: '分页原文', desc: '按页保存并展示论文正文，让报告、引用与问答共用同一份原文基础。' },
              { title: '关键问题报告', desc: '集中回答研究问题、方法过程、评估证据和局限，避免只生成零散摘要。' },
              { title: '方法与贡献', desc: '将“论文怎么做”与“它新增了什么”分开呈现，并保留证据边界。' },
              { title: '可追溯引用', desc: '引文必须在标注页面的原文中匹配；无法核对的引文不会进入报告。' },
              { title: '个人总结', desc: '将你自己的理解与 AI 报告分开保存；既可写成短摘要，也可展开为完整阅读笔记。' },
              { title: '带页码持续追问', desc: '围绕同一篇论文连续提问，实质结论回到分页原文；证据不足时直接说明。' },
            ].map((feature, index) => (
              <Card key={index} className="h-full">
                <CardContent className="pt-2">
                  <h3 className="mb-2 text-xl font-semibold">{feature.title}</h3>
                  <p className="text-muted-foreground">{feature.desc}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <section className="mb-16">
          <h2 className="mb-8 text-center text-3xl font-bold">🧭 证据边界</h2>
          <div className="mx-auto grid max-w-4xl grid-cols-1 gap-6 md:grid-cols-2">
            <Card>
              <CardContent className="pt-6">
                <h3 className="mb-3 text-xl font-semibold">论文内部证据</h3>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li>“原文已定位”只表示结论能回到具体页码与引文</li>
                  <li>单篇论文只能说明该研究报告了什么</li>
                  <li>无法解析或没有有效正文的 PDF 不会伪装成导入成功</li>
                </ul>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <h3 className="mb-3 text-xl font-semibold">不自动扩大的结论</h3>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li>论文身份确认不等于论文中所有结论已被外部证实</li>
                  <li>作者报告的实验结果不等于 FastRead 已完成实验复现</li>
                  <li>近邻论文只说明相似之处，不判断主张真假，也不会取代论文原文</li>
                </ul>
              </CardContent>
            </Card>
          </div>
        </section>

        {/* Quick Start Section */}
        <section className="mb-16">
          <h2 className="mb-8 text-center text-3xl font-bold">🚀 开始阅读</h2>
          <div className="mx-auto max-w-3xl space-y-6">
            <Card>
              <CardContent className="pt-6">
                <h3 className="mb-3 text-xl font-semibold">导入一篇论文</h3>
                <p className="mt-3 text-sm text-muted-foreground">
                  在资料库中点击“导入论文”，选择本地 PDF 或粘贴论文 URL。
                  导入后先检查分页原文和来源信息，再生成阅读报告。
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <h3 className="mb-3 text-xl font-semibold">形成自己的结论</h3>
                <p className="text-sm text-muted-foreground">
                  逐页核对关键问题、方法与贡献的证据，写下可长可短的个人总结，
                  然后在同一篇论文上持续追问。对任何实质结论，都建议点击引用回到对应页面核对。
                </p>
              </CardContent>
            </Card>
          </div>
        </section>

        {/* License Section */}
        <section className="mb-8 text-center">
          <h2 className="mb-4 text-3xl font-bold">📜 License</h2>
          <p>MIT License</p>
        </section>

        {/* Footer */}
        <footer className="border-t pt-8 text-center">
          <p className="mb-4">FastRead 帮你更快理解论文，也保留回到原文复核的路径。</p>
        </footer>
      </div>
    </ScrollArea>
  )
}
