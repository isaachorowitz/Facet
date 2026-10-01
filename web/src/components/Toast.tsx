import { useEffect, useState } from 'react';
export type ToastMessage = { id: number; text: string };
export function Toast({ message }: { message: ToastMessage | null }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!message) return;
    setVisible(true);
    const timer = setTimeout(() => setVisible(false), 7000);
    return () => clearTimeout(timer);
  }, [message]);
  return <div className={`toast${visible ? ' show' : ''}`} role="status" aria-live="polite">{message?.text}</div>;
}
