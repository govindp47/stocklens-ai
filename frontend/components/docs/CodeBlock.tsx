/**
 * CodeBlock — server component that renders a syntax-highlighted code block.
 *
 * Uses inline CSS class styling only — no client-side syntax highlighter dependency.
 * This is a React Server Component (no 'use client' directive).
 */

interface CodeBlockProps {
  code: string;
  language?: string;
}

export function CodeBlock({ code, language = 'bash' }: CodeBlockProps) {
  return (
    <div className="rounded-md bg-neutral-900 overflow-x-auto">
      {language && (
        <div className="px-4 pt-2 pb-0 text-xs text-neutral-500 font-mono">
          {language}
        </div>
      )}
      <pre className="px-4 py-3 text-xs text-neutral-100 font-mono leading-relaxed whitespace-pre">
        <code>{code}</code>
      </pre>
    </div>
  );
}
