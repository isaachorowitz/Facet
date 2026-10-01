import { useEffect } from 'react';
export function useSpotlight() {
  useEffect(() => {
    const move = (event: MouseEvent) => {
      for (const card of document.querySelectorAll<HTMLElement>('.card')) {
        const rect = card.getBoundingClientRect();
        card.style.setProperty('--mx', `${event.clientX - rect.left}px`);
        card.style.setProperty('--my', `${event.clientY - rect.top}px`);
      }
    };
    document.addEventListener('mousemove', move);
    return () => document.removeEventListener('mousemove', move);
  }, []);
}
