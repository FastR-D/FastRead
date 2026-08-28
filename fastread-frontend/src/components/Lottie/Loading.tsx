import { type HTMLAttributes } from 'react'
import Lottie from 'lottie-react'
import loadingJson from '@/assets/Lottie/loading.json'
import { cn } from '@/lib/utils'

const Loading = ({ className, ...props }: HTMLAttributes<HTMLDivElement>) => {
  return (
    <div className={cn('flex items-center justify-center', className)} {...props}>
      <Lottie animationData={loadingJson} loop autoplay style={{ width: 150, height: 150 }} />
    </div>
  )
}

export default Loading
