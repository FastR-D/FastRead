import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area.tsx'
import logo from '@/assets/icon.png'

export default function AboutPage() {
  const images = [
    'https://common-1304618721.cos.ap-chengdu.myqcloud.com/20250504102850.png',
    'https://common-1304618721.cos.ap-chengdu.myqcloud.com/20250504103028.png',
    'https://common-1304618721.cos.ap-chengdu.myqcloud.com/20250504103304.png',
    'https://common-1304618721.cos.ap-chengdu.myqcloud.com/20250504103625.png',
  ]
  return (
    <ScrollArea className={'h-full overflow-y-auto bg-white'}>
      <div className="container mx-auto px-4 py-12">
        {/* Hero Section */}
        <div className="mb-16 flex flex-col items-center justify-center text-center">
          <div className="mb-4 flex items-center gap-4">
            <img
              src={logo}
              alt="Reel Mind Logo"
              width={50}
              height={50}
              className="rounded-lg"
            />
            <h1 className="text-4xl font-bold">Reel Mind</h1>
          </div>
          <p className="text-muted-foreground mb-6 text-xl">
            把短视频变成可沉淀的知识
          </p>

          <div className="mb-8 flex flex-wrap justify-center gap-2">
            <Badge variant="secondary">Douyin Jingxuan</Badge>
            <Badge variant="secondary">React</Badge>
            <Badge variant="secondary">FastAPI</Badge>
            <Badge variant="secondary">Docker Compose</Badge>
            <Badge variant="secondary">MVP</Badge>
          </div>
        </div>

        {/* Project Introduction */}
        <section className="mb-16">
          <h2 className="mb-6 text-center text-3xl font-bold">✨ 项目简介</h2>
          <div className="mx-auto max-w-3xl text-center">
            <p className="text-lg">
              这是一个基于现有视频笔记工程整理出的独立产品骨架，当前阶段不再追求通用多平台能力，
              而是优先收敛到抖音精选知识视频场景。目标是把“收藏视频、提取知识、输出总结、生成思维导图”做成一条可落地的最短路径。
            </p>
          </div>
        </section>

        {/* Features Section */}
        <section className="mb-16">
          <h2 className="mb-8 text-center text-3xl font-bold">🔧 当前 MVP</h2>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {[
              { title: '视频收藏管理', desc: '围绕知识视频建立可回看、可整理的基础收藏入口。' },
              { title: 'AI 知识提取', desc: '从视频字幕与画面中提取结构化知识点，减少人工摘录。' },
              { title: 'AI 知识总结', desc: '输出适合复习与二次编辑的 Markdown 总结。' },
              { title: '思维导图生成', desc: '基于笔记内容直接生成导图，方便梳理主题与层级。' },
              { title: '中文模型优先', desc: '产品配置与文案默认面向中文模型供应商，如 Qwen / DeepSeek。' },
              { title: '浏览器插件联动', desc: '保留插件入口，便于后续接入抖音精选页面的一键提取流程。' },
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
                  <li>抖音精选知识视频场景</li>
                  <li>浏览器插件 + 独立 Web 应用</li>
                  <li>知识提取、知识总结、思维导图</li>
                </ul>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <h3 className="mb-3 text-xl font-semibold">暂不纳入当前 MVP</h3>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  <li>讲解动画、学习计划、知识图谱</li>
                  <li>知识关联推荐、多平台统一适配</li>
                  <li>视频下载 / 离线播放 / 社交能力</li>
                </ul>
              </CardContent>
            </Card>
          </div>
        </section>

        {/* Screenshots Section */}
        <section className="mb-16">
          <h2 className="mb-8 text-center text-3xl font-bold">📸 当前界面预览</h2>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {images.map(num => (
              <div key={num} className="overflow-hidden rounded-lg border shadow-sm">
                <img
                  src={num}
                  alt={`Reel Mind 截图 ${num}`}
                  width={600}
                  height={400}
                  className="w-full object-cover transition-transform hover:scale-105"
                />
              </div>
            ))}
          </div>
        </section>

        {/* Quick Start Section */}
        <section className="mb-16">
          <h2 className="mb-8 text-center text-3xl font-bold">🚀 本地运行</h2>
          <div className="mx-auto max-w-3xl space-y-6">
            <Card>
              <CardContent className="pt-6">
                <h3 className="mb-3 text-xl font-semibold">Docker Compose</h3>
                <div className="bg-muted rounded-md p-4 font-mono text-sm">
                  docker compose up -d --build
                </div>
                <p className="mt-3 text-sm text-muted-foreground">
                  前端通过 Nginx 对外暴露，端口以当前仓库的 <code>.env</code> 为准。
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <h3 className="mb-3 text-xl font-semibold">当前阶段说明</h3>
                <p className="text-sm text-muted-foreground">
                  这一版先完成品牌收口、运行打通和基础信息架构整理。底层仍保留部分原工程的多平台实现，后续阶段再继续收缩到抖音精选主流程。
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
          <p className="mb-4">当前页面用于说明这套独立改造项目的阶段目标与运行状态。</p>
        </footer>
      </div>
    </ScrollArea>
  )
}
