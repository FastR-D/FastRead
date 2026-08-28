import {
  BotMessageSquare,
  Info,
  Activity,
  Cable,
  Search,
} from 'lucide-react'
import MenuBar, { IMenuProps } from '@/pages/SettingPage/components/menuBar.tsx'

const Menu = () => {
  const menuList: IMenuProps[] = [
    {
      id: 'model',
      name: 'AI 模型设置',
      icon: <BotMessageSquare />,
      path: '/settings/model',
    },
    // //其他配置
    // {
    //   id: 'prompt',
    //   name: '提示词设置',
    //   icon: <SquareChevronRight />,
    //   path: '/settings/prompt',
    // },
    {
      id: 'search-connections',
      name: '学术检索连接',
      icon: <Search />,
      path: '/settings/search-connections',
    },
    {
      id: 'integrations',
      name: '外部连接',
      icon: <Cable />,
      path: '/settings/integrations',
    },
    {
      id: 'monitor',
      name: '部署监控',
      icon: <Activity />,
      path: '/settings/monitor',
    },
    {
      id: 'about',
      name: '关于',
      icon: <Info />,
      path: '/settings/about',
    },
    // {
    //   id: 'other',
    //   name: '其他配置',
    //   icon: <Wrench />,
    //   path: '/settings/other',
    // },
  ]
  return (
    <div className="flex h-full flex-col">
      <div className={'flex w-full flex-col gap-2'}>
        <div className="text-2xl font-medium">设置</div>
        <div className="text-sm font-light text-gray-800">全局配置与模型设置</div>
      </div>
      <div className="mt-6 flex-1">
        {menuList &&
          menuList.map(item => {
            return <MenuBar key={item.id} menuItem={item} />
          })}
      </div>
    </div>
  )
}
export default Menu
