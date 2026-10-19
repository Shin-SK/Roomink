import type { Device, WorkCall } from './roomink';

/** The two read endpoints can briefly overlap while a call changes state. */
export function callList(device: Device, current: WorkCall[], history: WorkCall[], storeId: number | null, missedOnly: boolean): WorkCall[] {
  const receiving = new Set(device.status === 'active' ? device.stores.filter((store) => store.is_receiving).map((store) => store.id) : []);
  const entitled = new Set(device.stores.filter((store) => store.is_entitled !== false).map((store) => store.id));
  const byId = new Map<number, WorkCall>();
  for (const call of current) if (receiving.has(call.store_id) && entitled.has(call.store_id)) byId.set(call.id, call);
  // History is read after current calls and wins if a call transitioned during refresh.
  for (const call of history) if (entitled.has(call.store_id)) byId.set(call.id, call);
  return [...byId.values()]
    .filter((call) => (storeId === null || call.store_id === storeId) && (!missedOnly || call.status === 'MISSED'))
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id - a.id);
}
