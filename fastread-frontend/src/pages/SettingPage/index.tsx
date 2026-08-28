import SettingLayout from '@/layouts/SettingLayout.tsx'
import Menu from '@/pages/SettingPage/Menu'
import { useProviderStore } from '@/store/providerStore'
import { useEffect } from 'react'

const SettingPage = () => {
  const fetchProviderList = useProviderStore(state => state.fetchProviderList)
  useEffect(() => {
    fetchProviderList()
  }, [fetchProviderList])
  return (
    <div className="h-dvh min-h-0 w-full overflow-hidden">
      <SettingLayout Menu={<Menu />} />
    </div>
  )
}
export default SettingPage
