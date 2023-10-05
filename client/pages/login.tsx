import React, { useState, useEffect } from 'react';
import useSWR from 'swr';

export default function Login() {
  const [id, setID] = useState('');
  const [password, setPassword] = useState('');
  const { data: user, error: userError } = useSWR('/api/user', fetch);

  useEffect(() => {
    if (user && user.ok) {
      window.location.href = '/';
    }
  }, [userError, user]);

  if (!user) return <div>読み込み中</div>;

  if (userError) return <div>エラーが発生しました</div>;

  if (user.ok) {
    return <div>ログイン済みです</div>;
  }

  function login() {
    fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, password }),
    }).then(() => {
      window.location.href = '/';
    });
  }

  return (
    <form onSubmit={(ev) => {
      ev.preventDefault();
      login();
    }}>
      <label>ID <input type="text" value={id} onChange={(ev) => setID(ev.target.value)} /></label>
      <label>password <input type="password" value={password} onChange={(ev) => setPassword(ev.target.value)} /></label>
      <button type="submit">ログイン</button>
    </form>
  );
}
