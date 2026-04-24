"use client";

import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/cn";

// Paper-palette button system. `primary` is the default ink-on-paper pill;
// `accent` is the terracotta CTA used sparingly. `ghost` and `outline` keep
// the framed-button feel with different chrome. Hover swaps to the warm
// sand wash on non-primary variants.
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-terracotta/40 disabled:opacity-50 disabled:pointer-events-none border",
  {
    variants: {
      variant: {
        primary:
          "bg-ink text-paper border-ink hover:bg-terracotta hover:border-terracotta",
        accent:
          "bg-terracotta text-paper border-terracotta hover:bg-terracotta-2 hover:border-terracotta-2",
        ghost: "bg-transparent border-transparent text-ink hover:bg-sand",
        outline: "bg-paper border-rule text-ink hover:bg-sand",
      },
      size: {
        sm: "h-7 px-2.5 text-xs",
        md: "h-9 px-3.5 text-[13px]",
        lg: "h-11 px-5 text-[14px]",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  ),
);
Button.displayName = "Button";
