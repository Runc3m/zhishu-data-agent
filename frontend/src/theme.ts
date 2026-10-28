import {useSyncExternalStore} from 'react';

export type ThemeChoice = 'system' | 'light' | 'dark';
const KEY = 'zhishu-theme';
const listeners = new Set<() => void>();
// Chart helpers are also bundled for Node tests, where there is no window.
const browser = typeof window !== 'undefined';
const media = browser ? window.matchMedia('(prefers-color-scheme: dark)') : null;

function stored(): ThemeChoice {
  try {
    const value = browser ? localStorage.getItem(KEY) : null;
    return value === 'light' || value === 'dark' ? value : 'system';
  } catch {
    return 'system';
  }
}

let choice: ThemeChoice = stored();
const resolve = (): 'light' | 'dark' => choice === 'system' ? (media?.matches ? 'dark' : 'light') : choice;
let resolved = resolve();

function apply() {
  resolved = resolve();
  if (browser) {
    document.documentElement.dataset.theme = resolved;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', resolved === 'dark' ? '#0e1413' : '#f6f7f5');
  }
  listeners.forEach(listener => listener());
}

apply();
media?.addEventListener('change', () => { if (choice === 'system') apply(); });

export function setTheme(value: ThemeChoice) {
  choice = value;
  try { localStorage.setItem(KEY, value); } catch { /* Private mode keeps the choice for this session only. */ }
  apply();
}

const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export const useThemeChoice = () => useSyncExternalStore(subscribe, () => choice);
export const useResolvedTheme = () => useSyncExternalStore(subscribe, () => resolved);
