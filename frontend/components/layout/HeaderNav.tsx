"use client";

/**
 * HeaderNav — client component for the header's right side:
 * navigation links + theme toggle.
 * Needs to be a client component for usePathname (active link detection).
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, History, Zap } from "lucide-react";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

const NAV_LINKS = [
  { href: "/", label: "Analyze", icon: Zap },
  { href: "/history", label: "History", icon: History },
  { href: "/docs", label: "API Docs", icon: BookOpen },
];

export function HeaderNav() {
  const pathname = usePathname();

  return (
    <div className="flex items-center gap-1">
      <nav className="flex items-center gap-2" aria-label="Main navigation">
        {NAV_LINKS.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`relative inline-flex items-center gap-1.5 rounded-lg px-3 py-1 text-xs font-medium transition-all duration-150
                ${
                  isActive
                    ? "bg-brand-50 text-brand-600 ring-1 ring-brand-200/60"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              aria-current={isActive ? "page" : undefined}
            >
              <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span className="hidden sm:inline">{label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="ml-2 mr-2 h-4 w-px bg-border" aria-hidden="true" />
      <ThemeToggle />
    </div>
  );
}
