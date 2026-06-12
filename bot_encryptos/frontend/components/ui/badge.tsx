import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default: "bg-primary/20 text-primary",
        success: "bg-green-500/20 text-green-400",
        danger: "bg-red-500/20 text-red-400",
        warning: "bg-amber-500/20 text-amber-400",
        muted: "bg-gray-500/20 text-gray-400",
        blue: "bg-blue-500/20 text-blue-400",
        outline: "border border-[#2a2d3a] text-[#6b7280]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
