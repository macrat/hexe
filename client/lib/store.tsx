import React, { useCallback } from 'react';
import { configureStore, createSlice } from '@reduxjs/toolkit';
import { Provider as ReduxProvider, useDispatch, useSelector } from 'react-redux';

export type FunctionOutput = {
  id: string;
  content: string;
};

export type Message = {
  id: string;
  createdAt: number;
  errors: string[];
} & ({
  type: 'user' | 'assistant';
  content: string;
} | {
  type: 'function_call';
  name: string;
  arguments: string;
  outputs: FunctionOutput[];
});

export type Event = {
  id: string;
  created_at: number;
} & ({
  type: 'user';
  content: string;
  delta?: boolean;
} | {
  source: string;
  type: 'assistant';
  content: string;
  delta?: boolean;
} | {
  source: string;
  type: 'function_call';
  name: string;
  arguments: string;
  delta?: boolean;
} | {
  source: string;
  type: 'function_output';
  name: string;
  content: string;
  delta?: boolean;
} | {
  source: string;
  type: 'status';
  generating: boolean;
} | {
  source: string;
  type: 'error';
  content: string;
});

type ChatSlice = {
  messages: Message[];
  generating: boolean;
};

const chatSlice = createSlice({
  name: 'chat',
  initialState: {
    messages: [],
    generating: false,
  } as ChatSlice,
  reducers: {
    pushEvent: (state, action) => {
      const ev = action.payload;
      if (ev.type === 'status') {
        state.generating = ev.generating;
      }

      const idx = state.messages.findLastIndex((message) => message.id === ev.id);

      const sourceIdx = 'source' in ev ? state.messages.findIndex((message) => message.id === ev.source) : -1;

      if (idx < 0) {
        state.messages.push({ ...ev, createdAt: ev.created_at * 1000 });
      } else if (ev.delta) {
        const msg = state.messages[idx];

        if (msg.type === 'function_call') {
          msg.arguments = ev.arguments;
        } else {
          msg.content += ev.content;
        }
      } else {
        switch (ev.type) {
          case 'user':
          case 'assistant':
            state.messages[idx] = {
              id: ev.id,
              type: ev.type,
              content: ev.content,
              createdAt: ev.created_at * 1000,
              errors: [],
            };
            break;
          case 'function_call':
            state.messages[idx] = {
              id: ev.id,
              type: 'function_call',
              name: ev.name,
              arguments: ev.arguments,
              outputs: [],
              createdAt: ev.created_at * 1000,
              errors: [],
            };
            break;
          case 'function_output':
            if (sourceIdx >= 0) {
              const msg = state.messages[sourceIdx];
              if (msg.type === 'function_call') {
                const outputIdx = msg.outputs.findIndex((output) => output.id === ev.id);
                if (outputIdx >= 0) {
                  if (ev.delta) {
                    msg.outputs[outputIdx].content += ev.content;
                  } else {
                    msg.outputs[outputIdx].content = ev.content;
                  }
                } else {
                  msg.outputs.push({
                    id: ev.id,
                    content: ev.content,
                  });
                }
              }
            }
            break;
          case 'error':
            if (sourceIdx >= 0) {
              state.messages[sourceIdx].errors.push(ev.content);
            }
            break;
        }
      }
    },
  },
});

const store = configureStore({
  reducer: {
    chat: chatSlice.reducer,
  },
});

type State = ReturnType<typeof store.getState>;

export const Provider = ({ children }) => <ReduxProvider store={store}>{children}</ReduxProvider>;

export const useChat = () => {
  const dispatch = useDispatch();
  const messages = useSelector((state: State) => state.chat.messages);
  const generating = useSelector((state: State) => state.chat.generating);

  const pushEvent = useCallback((ev: Event) => dispatch(chatSlice.actions.pushEvent(ev)), [dispatch]);

  return { messages, generating, pushEvent };
}
