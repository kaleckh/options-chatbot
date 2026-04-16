"use client";

import { forwardRef } from "react";
import { Loader2 } from "lucide-react";

type ButtonVariant = "primary" | "secondary" | "ghost";
type ButtonSize = "sm" | "md";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: React.ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-gradient-to-r from-accent to-blue-600 text-white border-transparent hover:opacity-90 shadow-md shadow-accent/20",
  secondary:
    "bg-bg-3 text-text-1 border-border hover:bg-bg-4 hover:border-text-3 hover:text-text-0",
  ghost:
    "bg-transparent text-text-2 border-transparent hover:bg-bg-4 hover:text-text-1",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "px-2.5 py-1.5 text-xs gap-1.5",
  md: "px-4 py-2 text-sm gap-2",
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      type = "button",
      variant = "secondary",
      size = "md",
      loading = false,
      icon,
      children,
      disabled,
      className = "",
      ...props
    },
    ref
  ) => {
    return (
      <button
        ref={ref}
        type={type}
        disabled={disabled || loading}
        className={`
          inline-flex items-center justify-center font-medium rounded-md border
          transition-colors duration-150
          focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2
          disabled:opacity-50 disabled:cursor-not-allowed
          active:scale-[0.98]
          ${variantStyles[variant]}
          ${sizeStyles[size]}
          ${className}
        `}
        {...props}
      >
        {loading ? (
          <Loader2 size={size === "sm" ? 12 : 14} className="animate-spin" aria-hidden="true" />
        ) : icon ? (
          <span aria-hidden="true">{icon}</span>
        ) : null}
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";

export default Button;
