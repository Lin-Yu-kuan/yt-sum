"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownContentProps {
  content: string;
  className?: string;
}

export default function MarkdownContent({
  content,
  className = "",
}: MarkdownContentProps) {
  if (!content) return null;

  return (
    <div
      className={`text-sm leading-relaxed text-[var(--text-main)] space-y-2.5 break-words ${className}`}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-base font-bold text-[var(--text-main)] mt-4 mb-2 first:mt-0 pb-1 border-b border-[var(--border-subtle)]">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-[15px] font-bold text-[var(--text-main)] mt-4 mb-2 first:mt-0 pb-1 border-b border-[var(--border-subtle)]">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-semibold text-[var(--accent-blue)] mt-3.5 mb-1.5 first:mt-0">
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-sm font-semibold text-[var(--text-main)] mt-3 mb-1 first:mt-0">
              {children}
            </h4>
          ),
          p: ({ children }) => (
            <p className="leading-relaxed text-[var(--text-main)] my-1.5 first:mt-0 last:mb-0">
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul className="list-disc pl-5 space-y-1.5 my-2">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-5 space-y-1.5 my-2">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="leading-relaxed [&>p]:my-0.5">{children}</li>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-[var(--text-main)]">
              {children}
            </strong>
          ),
          em: ({ children }) => (
            <em className="italic text-[var(--text-muted)]">{children}</em>
          ),
          blockquote: ({ children }) => (
            <blockquote className="my-2.5 pl-3 pr-2 py-1.5 border-l-2 border-blue-500/60 bg-blue-500/5 rounded-r-md text-[var(--text-main)]">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-3 border-[var(--border-subtle)]" />,
          code: ({ className: codeClassName, children }) => {
            const isBlock = Boolean(codeClassName?.includes("language-"));
            if (isBlock) {
              return (
                <code className="block p-3 rounded-lg bg-[var(--bg-elevated)] border border-[var(--border-subtle)] font-mono text-xs overflow-x-auto my-2">
                  {children}
                </code>
              );
            }
            return (
              <code className="px-1.5 py-0.5 rounded bg-[var(--bg-elevated)] border border-[var(--border-subtle)]/60 font-mono text-[0.88em] text-[var(--accent-blue)]">
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="my-2 overflow-x-auto">{children}</pre>
          ),
          table: ({ children }) => (
            <div className="my-3 overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
              <table className="w-full text-xs border-collapse text-left">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-[var(--bg-elevated)] text-[var(--text-main)]">
              {children}
            </thead>
          ),
          th: ({ children }) => (
            <th className="px-3 py-2 font-semibold border-b border-[var(--border-subtle)] whitespace-nowrap">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2 border-b border-[var(--border-subtle)]/60 align-top">
              {children}
            </td>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--accent-blue)] underline underline-offset-2 hover:opacity-80"
            >
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
