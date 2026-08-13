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
            学术论文阅读报告与可审计证据层
          </p>

          <div className="mb-8 flex flex-wrap justify-center gap-2">
            <Badge variant="secondary">Paper Reading</Badge>
            <Badge variant="secondary">React</Badge>
            <Badge variant="secondary">FastAPI</Badge>
            <Badge variant="secondary">PPT Export</Badge>
            <Badge variant="secondary">Venue Search</Badge>
          </div>
        </div>

        {/* Project Introduction */}
        <section className="mb-16">
          <h2 className="mb-6 text-center text-3xl font-bold">✨ 项目简介</h2>
          <div className="mx-auto max-w-3xl text-center">
            <p className="text-lg">
              FastRead 用来读懂一篇论文：导入 PDF 或论文 URL，围绕关键问题生成可审计阅读报告，
              保留页码引用，支持个人总结、持续追问，以及一键导出 PPT。
            </p>
          </div>
        </section>

        {/* Features Section */}
        <section className="mb-16">
          <h2 className="mb-8 text-center text-3xl font-bold">🔧 当前 MVP</h2>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {[
              { title: '论文导入与分页解析', desc: '从 PDF 或论文 URL 抽出分页原文，作为后续报告和追问的唯一原文依据。' },
              { title: '关键问题阅读报告', desc: '固定覆盖研究问题、方法过程、主要贡献、实验证据和局限。' },
              { title: '页码可审计引用', desc: '报告引文只有在分页原文或核验证据中匹配成功才会保留。' },
              { title: '顶会限定检索', desc: '只搜安全四大与系统顶会论文，命中后可一键导入阅读。' },
              { title: '一键导出 PPT', desc: '把阅读报告投影成带页码引用的幻灯片。' },
              { title: '浏览器插件导入', desc: '从当前论文页面把链接送到 FastRead，生成阅读报告。' },
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
          <h2 className="mb-8 text-center text-3xl font-bold">🧭 当前边界</h2>
          <div className="mx-auto grid max-w-4xl grid-cols-1 gap-6 md:grid-cols-2">
            <Card>
              <CardContent className="pt-6">
                <h3 className="mb-3 text-xl font-semibold">当前优先处理</h3>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li>单篇论文阅读报告与页码追问</li>
                  <li>四大安全顶会 + 系统顶会检索</li>
                  <li>阅读报告导出 PPT</li>
                </ul>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <h3 className="mb-3 text-xl font-semibold">暂不纳入当前 MVP</h3>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li>实验复现与代码执行</li>
                  <li>通用全网论文搜索（仅限指定顶会）</li>
                  <li>视频下载、转写或思维导图</li>
                </ul>
              </CardContent>
            </Card>
          </div>
        </section>

        {/* Screenshots Section */}
        <section className="mb-16">
          <h2 className="mb-8 text-center text-3xl font-bold">📸 当前界面预览</h2>
          <div className="mx-auto max-w-3xl overflow-hidden rounded-lg border shadow-sm">
            <img
              src="/preview_1.png"
              alt="FastRead 界面预览"
              width={600}
              height={400}
              className="w-full object-cover"
            />
          </div>
        </section>

        {/* Quick Start Section */}
        <section className="mb-16">
          <h2 className="mb-8 text-center text-3xl font-bold">🚀 本地运行</h2>
          <div className="mx-auto max-w-3xl space-y-6">
            <Card>
              <CardContent className="pt-6">
                <h3 className="mb-3 text-xl font-semibold">唯一启动入口</h3>
                <div className="bg-muted rounded-md p-4 font-mono text-sm">
                  run.bat
                </div>
                <p className="mt-3 text-sm text-muted-foreground">
                  从仓库根目录启动本地后端和前端；状态检查和停止服务分别使用 <code>run.bat --status</code> 与 <code>run.bat --stop</code>。
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <h3 className="mb-3 text-xl font-semibold">当前阶段说明</h3>
                <p className="text-sm text-muted-foreground">
                  当前默认走本地启动：配置模型供应商后即可导入论文、生成阅读报告、追问和导出 PPT。
                </p>
              </CardContent>
            </Card>
          </div>
        </section>

        {/* Footer */}
        <footer className="border-t pt-8 text-center">
          <p className="mb-4">FastRead · 论文阅读与笔记</p>
        </footer>
      </div>
    </ScrollArea>
  )
}
