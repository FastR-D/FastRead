import Provider from '@/components/Form/modelForm/Provider.tsx'
import { Outlet } from 'react-router-dom'

const Model = () => {
  return (
    <div className={'flex h-full min-h-0 bg-white'}>
      <div className={'w-60 shrink-0 min-h-0 overflow-y-auto border-r border-neutral-200 p-2'}>
        <Provider></Provider>
      </div>
      <div className={'min-w-0 flex-1 min-h-0 overflow-y-auto'}>
        <Outlet />
      </div>
    </div>
  )
}
export default Model
