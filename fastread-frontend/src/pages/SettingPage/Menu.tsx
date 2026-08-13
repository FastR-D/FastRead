import {
  BotMessageSquare,
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
