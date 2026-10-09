import { Redirect } from 'expo-router';
import { useState } from 'react';
import { CallListScreen } from '../components/CallListScreen';
import type { Device, Store, WorkCall } from '../lib/roomink';

const now = new Date().toISOString();
const sampleCalls: WorkCall[] = [
  { id: 1, contact_id: 'local-preview-1', store_id: 1, store_name: 'Work検証 A店', from_phone: '090-0000-0000', customer_name: '山田さま（架空）', customer_attention: { flag: 'CAUTION', ban_type: '', staff_memo: '受付時に確認' }, status: 'NEW', created_at: now },
  { id: 2, contact_id: 'local-preview-2', store_id: 2, store_name: 'Work検証 B店', from_phone: '080-0000-0000', customer_name: null, status: 'IN_PROGRESS', created_at: now },
];
const sampleHistory: WorkCall[] = [
  { id: 3, contact_id: 'local-preview-3', store_id: 1, store_name: 'Work検証 A店', from_phone: '070-0000-0000', customer_name: '鈴木さま（架空）', status: 'DONE', created_at: now },
  { id: 4, contact_id: 'local-preview-4', store_id: 3, store_name: 'Work検証 C店', from_phone: '050-0000-0000', customer_name: null, status: 'MISSED', created_at: now },
];

export default function ReceptionPreview() {
  const [device, setDevice] = useState<Device>({ label: '本部の受付端末（架空）', status: 'active', stores: [
    { id: 1, name: 'Work検証 A店', is_receiving: true },
    { id: 2, name: 'Work検証 B店', is_receiving: true },
    { id: 3, name: 'Work検証 C店', is_receiving: false },
  ] });
  if (!__DEV__) return <Redirect href="/" />;
  function toggleStore(store: Store) {
    setDevice((current) => ({ ...current, stores: current.stores.map((row) => row.id === store.id ? { ...row, is_receiving: !row.is_receiving } : row) }));
  }
  return <CallListScreen preview device={device} calls={sampleCalls} history={sampleHistory} busy={false} error={null} onRefresh={() => {}} onToggleStore={toggleStore} />;
}
