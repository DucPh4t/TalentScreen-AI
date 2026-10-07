'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, UserAccount, RequisitionItem } from '../../lib/api';
import DashboardHome from '../../components/DashboardHome';

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const [requisitions, setRequisitions] = useState<RequisitionItem[]>([]);
  const [dashboardError, setDashboardError] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      const u = await api.getMe();
      setUser(u);
      try {
        const list = await api.listRequisitions();
        setRequisitions(list);
      } catch (err: any) {
        setDashboardError(err.message || 'Không tải được danh sách tuyển dụng.');
      }
    } catch {
      router.push('/');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '6rem 2rem' }}>
        <div className="env-status-dot" style={{ width: '12px', height: '12px', margin: '0 auto 1rem auto' }} />
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>Đang nạp không gian làm việc…</p>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <DashboardHome
      user={user}
      requisitions={requisitions}
      error={dashboardError}
      onReload={loadData}
    />
  );
}
