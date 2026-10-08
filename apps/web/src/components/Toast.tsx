'use client';

import { IconCheckCircle, IconAlertTriangle, IconShield, IconX } from './Icons';
import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface ToastItem {
  id: string;
  type: ToastType;
  title?: string;
  message: string;
  duration?: number;
}

interface ToastContextValue {
  showToast: (options: { type: ToastType; message: string; title?: string; duration?: number }) => void;
  removeToast: (id: string) => void;
  success: (message: string, title?: string) => void;
  error: (message: string, title?: string) => void;
  info: (message: string, title?: string) => void;
  warning: (message: string, title?: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

// Standalone event bus so toast can also be called outside React hooks if needed
type ToastListener = (toast: ToastItem) => void;
const listeners = new Set<ToastListener>();

export const toast = {
  success: (message: string, title: string = 'Thao tác thành công') => {
    emitToast({ type: 'success', title, message });
  },
  error: (message: string, title: string = 'Đã có lỗi xảy ra') => {
    emitToast({ type: 'error', title, message });
  },
  info: (message: string, title: string = 'Thông báo hệ thống') => {
    emitToast({ type: 'info', title, message });
  },
  warning: (message: string, title: string = 'Cảnh báo') => {
    emitToast({ type: 'warning', title, message });
  }
};

function emitToast(item: Omit<ToastItem, 'id'>) {
  const id = 'toast_' + Math.random().toString(36).substring(2, 9);
  const fullItem: ToastItem = { ...item, id, duration: item.duration ?? 4500 };
  listeners.forEach(fn => fn(fullItem));
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    ({ type, message, title, duration = 4500 }: { type: ToastType; message: string; title?: string; duration?: number }) => {
      const id = 'toast_' + Math.random().toString(36).substring(2, 9);
      setToasts((prev) => [...prev, { id, type, title, message, duration }]);
    },
    []
  );

  const success = useCallback((message: string, title?: string) => {
    showToast({ type: 'success', message, title: title || 'Thao tác thành công' });
  }, [showToast]);

  const error = useCallback((message: string, title?: string) => {
    showToast({ type: 'error', message, title: title || 'Đã có lỗi xảy ra' });
  }, [showToast]);

  const info = useCallback((message: string, title?: string) => {
    showToast({ type: 'info', message, title: title || 'Thông báo hệ thống' });
  }, [showToast]);

  const warning = useCallback((message: string, title?: string) => {
    showToast({ type: 'warning', message, title: title || 'Cảnh báo' });
  }, [showToast]);

  useEffect(() => {
    const handleEmit: ToastListener = (newToast) => {
      setToasts((prev) => [...prev, newToast]);
    };
    listeners.add(handleEmit);
    return () => {
      listeners.delete(handleEmit);
    };
  }, []);

  return (
    <ToastContext.Provider value={{ showToast, removeToast, success, error, info, warning }}>
      {children}
      {/* Liquid Glass Toast Floating Portal */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="toast-container"
        style={{
          position: 'fixed',
          top: '20px',
          right: '20px',
          zIndex: 999999,
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          maxWidth: '420px',
          width: 'calc(100vw - 40px)',
          pointerEvents: 'none'
        }}
      >
        {toasts.map((item) => (
          <ToastCard key={item.id} item={item} onDismiss={() => removeToast(item.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    // Graceful fallback to static emitter if outside provider
    return {
      showToast: (opts: any) => emitToast(opts),
      removeToast: () => {},
      success: toast.success,
      error: toast.error,
      info: toast.info,
      warning: toast.warning
    };
  }
  return context;
}

function ToastCard({ item, onDismiss }: { item: ToastItem; onDismiss: () => void }) {
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    if (!item.duration) return;
    const timer = setTimeout(() => {
      setExiting(true);
      setTimeout(onDismiss, 240);
    }, item.duration);
    return () => clearTimeout(timer);
  }, [item.duration, onDismiss]);

  const handleClose = () => {
    setExiting(true);
    setTimeout(onDismiss, 240);
  };

  const getTheme = () => {
    switch (item.type) {
      case 'success':
        return {
          icon: IconCheckCircle,
          border: 'var(--emerald-border)',
          glow: 'transparent',
          badgeColor: 'var(--emerald-text)',
          badgeBg: 'var(--emerald-bg)',
          barBg: 'var(--emerald-text)'
        };
      case 'error':
        return {
          icon: IconAlertTriangle,
          border: 'var(--rose-border)',
          glow: 'transparent',
          badgeColor: 'var(--rose-text)',
          badgeBg: 'var(--rose-bg)',
          barBg: 'var(--rose-text)'
        };
      case 'warning':
        return {
          icon: IconAlertTriangle,
          border: 'var(--amber-border)',
          glow: 'transparent',
          badgeColor: 'var(--amber-text)',
          badgeBg: 'var(--amber-bg)',
          barBg: 'var(--amber-text)'
        };
      case 'info':
      default:
        return {
          icon: IconShield,
          border: 'var(--border-glow)',
          glow: 'transparent',
          badgeColor: 'var(--accent-olive)',
          badgeBg: 'var(--accent-soft)',
          barBg: 'var(--accent-olive)'
        };
    }
  };

  const theme = getTheme();
  const TypeIcon = theme.icon;

  return (
    <div
      role="alert"
      className="toast-card"
      style={{
        pointerEvents: 'auto',
        background: '#ffffff',
        backdropFilter: 'none',
        WebkitBackdropFilter: 'none',
        border: `1px solid ${theme.border}`,
        borderRadius: '16px',
        padding: '0.9rem 1rem',
        boxShadow: `0 16px 36px -8px rgba(24, 24, 27, 0.14), 0 4px 12px ${theme.glow}, inset 0 1px 1px rgba(255, 255, 255, 1)`,
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        overflow: 'hidden',
        transition: 'all 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
        opacity: exiting ? 0 : 1,
        transform: exiting ? 'translateX(30px) scale(0.96)' : 'translateX(0) scale(1)',
        animation: 'toast-slide-in 0.3s cubic-bezier(0.16, 1, 0.3, 1)'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
        {/* Type Icon */}
        <div
          style={{
            width: '32px',
            height: '32px',
            borderRadius: '10px',
            backgroundColor: theme.badgeBg,
            color: theme.badgeColor,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            marginTop: '1px'
          }}
        >
          <TypeIcon size={19} />
        </div>

        {/* Content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {item.title && (
            <div style={{ fontSize: '13px', fontWeight: 700, color: '#18181b', lineHeight: 1.3, marginBottom: '2px' }}>
              {item.title}
            </div>
          )}
          <div style={{ fontSize: '12.5px', color: '#3f3f46', lineHeight: 1.45, wordBreak: 'break-word' }}>
            {item.message}
          </div>
        </div>

        {/* Close Button */}
        <button
          type="button"
          onClick={handleClose}
          aria-label="Đóng thông báo"
          style={{
            background: 'transparent',
            border: 'none',
            color: '#71717a',
            cursor: 'pointer',
            padding: '2px',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'color 0.15s ease'
          }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.color = '#18181b')}
          onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.color = '#71717a')}
        >
          <IconX size={17} />
        </button>
      </div>

      {/* Countdown Progress Bar */}
      {item.duration && (
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            height: '2.5px',
            backgroundColor: theme.barBg,
            borderRadius: '0 0 16px 16px',
            animation: `toast-progress ${item.duration}ms linear forwards`
          }}
        />
      )}
    </div>
  );
}
