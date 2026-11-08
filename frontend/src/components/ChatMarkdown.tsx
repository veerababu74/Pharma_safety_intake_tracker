import ReactMarkdown from 'react-markdown';

/** Renders assistant/user chat text with light markdown (bold, lists, headings, code). */
export function ChatMarkdown({ text }: { text: string }) {
  return (
    <div className="chat-md">
      <ReactMarkdown
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
        }}
      >
        {text || ''}
      </ReactMarkdown>
    </div>
  );
}
