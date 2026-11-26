import { Button, Section } from '@fastrd/ui-react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'
export const pageSize = 20
const secondary = 'text-[var(--fastui-secondary)]'

export function PageHeading({ title, children }: { title: string; children: ReactNode }) {
  return (
    <header className="app-page-heading">
      <h1 className="fastui-heading m-0 text-2xl">{title}</h1>
      <div className="flex items-center gap-2">{children}</div>
    </header>
  )
}
export function ListTable({
  label,
  columns,
  children,
  rows,
}: {
  label: string
  columns: string[]
  children?: ReactNode
  rows?: { id: string; cells: ReactNode[] }[]
}) {
  return (
    <Section>
      <div className="fastui-table-scroll" role="region" aria-label={label} tabIndex={0}>
        <table className="fastui-table workbench-table w-full min-w-[48rem]">
          <thead>
            <tr>
              {columns.map(column => (
                <th scope="col" key={column} className="sticky top-0 whitespace-nowrap">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {children ||
              rows?.map(row => (
                <tr key={row.id} className="hover:bg-[var(--fastui-hover)]">
                  {row.cells.map((cell, index) => (
                    <td key={columns[index]}>{cell}</td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}
export function ListFooter({
  count,
  page,
  onPage,
  unit,
}: {
  count: number
  page: number
  onPage: (page: number) => void
  unit: string
}) {
  const pages = Math.max(1, Math.ceil(count / pageSize))
  return (
    <div className={`flex flex-wrap items-center justify-between gap-3 ${secondary}`}>
      <span>
        {count} {unit}
      </span>
      {pages > 1 && (
        <nav className="flex items-center gap-3" aria-label={`${unit}分页`}>
          <Button
            variant="quiet"
            aria-label="上一页"
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
          >
            <ChevronLeft size={15} />
          </Button>
          <span>
            {page} / {pages}
          </span>
          <Button
            variant="quiet"
            aria-label="下一页"
            disabled={page >= pages}
            onClick={() => onPage(page + 1)}
          >
            <ChevronRight size={15} />
          </Button>
        </nav>
      )}
    </div>
  )
}
