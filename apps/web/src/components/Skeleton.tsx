'use client';

import React from 'react';

interface SkeletonProps {
  className?: string;
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  style?: React.CSSProperties;
}

export function Skeleton({ className = '', width, height = '1rem', borderRadius = '8px', style = {} }: SkeletonProps) {
  return (
    <div
      className={`skeleton-shimmer ${className}`}
      style={{
        width: width ?? '100%',
        height,
        borderRadius,
        ...style
      }}
    />
  );
}

export function SkeletonCard({ height = '180px' }: { height?: string }) {
  return (
    <div className="card" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem', height }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Skeleton width="40%" height="22px" borderRadius="6px" />
        <Skeleton width="60px" height="20px" borderRadius="12px" />
      </div>
      <Skeleton width="85%" height="14px" borderRadius="4px" />
      <Skeleton width="70%" height="14px" borderRadius="4px" />
      <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '0.75rem' }}>
        <Skeleton width="30%" height="16px" borderRadius="4px" />
        <Skeleton width="90px" height="32px" borderRadius="10px" />
      </div>
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div className="card" style={{ padding: '1.25rem' }}>
      {/* Table Header */}
      <div style={{ display: 'flex', gap: '1rem', paddingBottom: '0.85rem', borderBottom: '1px solid rgba(24, 24, 27, 0.08)' }}>
        {Array.from({ length: cols }).map((_, i) => (
          <div key={i} style={{ flex: i === 0 ? 1.5 : 1 }}>
            <Skeleton height="14px" borderRadius="4px" />
          </div>
        ))}
      </div>
      {/* Table Rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', paddingTop: '1rem' }}>
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
            {Array.from({ length: cols }).map((_, c) => (
              <div key={c} style={{ flex: c === 0 ? 1.5 : 1 }}>
                <Skeleton height={c === 0 ? '18px' : '14px'} borderRadius="6px" />
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function SkeletonDossier() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      {/* Top Header Shimmer */}
      <div className="card" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', flex: 1, minWidth: '280px' }}>
            <Skeleton width="180px" height="14px" borderRadius="4px" />
            <Skeleton width="320px" height="28px" borderRadius="8px" />
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem' }}>
              <Skeleton width="100px" height="22px" borderRadius="12px" />
              <Skeleton width="140px" height="22px" borderRadius="12px" />
              <Skeleton width="120px" height="22px" borderRadius="12px" />
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <Skeleton width="130px" height="38px" borderRadius="10px" />
            <Skeleton width="150px" height="38px" borderRadius="10px" />
          </div>
        </div>
      </div>

      {/* Tabs placeholder */}
      <div style={{ display: 'flex', gap: '0.75rem' }}>
        <Skeleton width="160px" height="40px" borderRadius="12px" />
        <Skeleton width="180px" height="40px" borderRadius="12px" />
        <Skeleton width="150px" height="40px" borderRadius="12px" />
        <Skeleton width="140px" height="40px" borderRadius="12px" />
      </div>

      {/* 3-Column Rubric & Evidence Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.25rem' }}>
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="card" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Skeleton width="60%" height="20px" borderRadius="6px" />
              <Skeleton width="45px" height="20px" borderRadius="10px" />
            </div>
            <Skeleton width="90%" height="14px" borderRadius="4px" />
            <Skeleton width="80%" height="14px" borderRadius="4px" />
            <div style={{ marginTop: '0.75rem', padding: '1rem', background: 'rgba(255, 255, 255, 0.6)', borderRadius: '10px', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <Skeleton width="40%" height="12px" borderRadius="4px" />
              <Skeleton width="100%" height="36px" borderRadius="6px" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
