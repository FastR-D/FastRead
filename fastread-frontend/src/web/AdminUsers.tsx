import { UserManagement } from './Admin'

type Api = (path: string, method?: string, body?: unknown) => Promise<any>

export default function AdminUsers({ api, currentId }: { api: Api; currentId: string }) {
  return <UserManagement api={api} currentUser={{ id: currentId }} />
}
