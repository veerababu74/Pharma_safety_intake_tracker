import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/** Renders assistant/user chat text with light markdown (bold, lists, headings, code, tables). */
export function ChatMarkdown({ text }: { text: string }) {
  return (
    <div className="chat-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="chat-md-table-wrap">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {text || ''}
      </ReactMarkdown>
    </div>
  );
}
