import {useSyncExternalStore} from 'react';
import english from './locales/en.json';

export type Language = 'zh-CN' | 'en-US';
let language: Language = 'zh-CN';
const listeners = new Set<() => void>();
export const getLanguage = () => language;
export function setLanguage(value: Language) {
  language = value;
  document.documentElement.lang = value;
  document.title = value === 'zh-CN' ? '知数 · Data Agent' : 'Zhishu · Data Agent';
  listeners.forEach(listener => listener());
}
export function useLanguage() {
  return useSyncExternalStore(listener => {listeners.add(listener); return () => {listeners.delete(listener);};}, getLanguage);
}
export function t(key: string, ...values: unknown[]): string {
  const template = language === 'en-US' ? (english as Record<string, string>)[key] ?? key : key;
  return template.replace(/\{(\d+)\}/g, (_, index) => String(values[Number(index)]));
}
