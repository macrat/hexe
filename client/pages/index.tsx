import React, { useState, useEffect } from 'react';
import { useChat } from '../lib/store';

export default function Index() {
  const { messages, generating, pushEvent } = useChat();
  const [input, setInput] = useState('');

  useEffect(() => {
    const source = new EventSource('/api/events?stream=true');
    source.onmessage = (ev) => {
      pushEvent(JSON.parse(ev.data));
    };

    return () => {
      source.close();
    };
  }, [pushEvent]);

  return (
    <>
      <ul>
        {messages.map((message) => (
          <li key={message.id}>
            <b>{message.type}</b> - <span>{new Date(message.createdAt).toLocaleString()}</span>
            {message.type === 'function_call' ? (
              <>
                <pre>function <b>{message.name}</b> {message.arguments}</pre>
                <ol>
                  {message.outputs.map((output) => (
                    <li key={output.id}><pre>{output.content}</pre></li>
                  ))}
                </ol>
              </>
            ) : (
              <pre>{message.content}</pre>
            )}
          </li>
        ))}
      </ul>

      <form onSubmit={(ev) => {
        ev.preventDefault();
        setInput('');
        fetch('/api/messages', {
          method: 'POST',
          headers: { 'Content-Type': 'text/plain' },
          body: input,
        });
      }}>
        <input value={input} onChange={(ev) => setInput(ev.target.value)} />
        <button disabled={generating}>送信</button>
      </form>

      <style jsx>{`
        pre {
          font-family: inherit;
          white-space: pre-wrap;
        }
      `}</style>
    </>
  );
}
