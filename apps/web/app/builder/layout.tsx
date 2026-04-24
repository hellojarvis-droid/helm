import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";

// Builder uses the standard Helm AppShell (nav + credits chip +
// notifications) but renders its content full-width. No Studio
// sidebar — each Builder screen owns its own layout.

export default function BuilderLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
