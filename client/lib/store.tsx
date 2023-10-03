import React, { useCallback } from 'react';
import { configureStore, createSlice } from '@reduxjs/toolkit';
import { Provider as ReduxProvider, useDispatch, useSelector } from 'react-redux';

type Message = any; // TODO
type Event = any; // TODO

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

      if (idx < 0) {
        state.messages.push({ ...ev, createdAt: ev.created_at * 1000 });
      } else if (ev.delta) {
        state.messages[idx].content += ev.content;
      } else {
        state.messages[idx] = { ...ev, createdAt: ev.created_at * 1000 };
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
