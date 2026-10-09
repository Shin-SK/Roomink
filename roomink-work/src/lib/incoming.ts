/** Local call-state model. OS delivery and server-side answer arbitration are separate. */
export type IncomingCall = {
  id: string;
  storeId: number;
  storeName: string;
  caller: string;
  phone: string;
  attention?: string;
  revision: number;
  status: 'ringing' | 'answered' | 'ended' | 'missed';
  answeredBy?: string;
};

export type CallSignal =
  | { kind: 'ring'; call: Omit<IncomingCall, 'status' | 'answeredBy'> }
  | { kind: 'answered'; callId: string; storeId: number; revision: number; deviceId: string }
  | { kind: 'ended' | 'missed'; callId: string; storeId: number; revision: number };

export type CallBook = Record<string, IncomingCall>;

function tombstone(callId: string, storeId: number, revision: number): IncomingCall {
  return { id: callId, storeId, storeName: '', caller: '', phone: '', revision, status: 'ended' };
}

export function applyCallSignal(book: CallBook, signal: CallSignal): CallBook {
  const callId = signal.kind === 'ring' ? signal.call.id : signal.callId;
  const previous = book[callId];
  const revision = signal.kind === 'ring' ? signal.call.revision : signal.revision;
  if (previous && (revision <= previous.revision || previous.storeId !== (signal.kind === 'ring' ? signal.call.storeId : signal.storeId))) return book;

  if (signal.kind === 'ring') {
    // A delayed ring must never revive a call already answered or closed.
    if (previous && previous.status !== 'ringing') return book;
    return { ...book, [callId]: { ...signal.call, status: 'ringing' } };
  }

  const base = previous ?? tombstone(callId, signal.storeId, revision);
  if (signal.kind === 'answered') {
    // The first accepted answer owns the call. A later answer cannot steal it.
    if (previous && previous.status !== 'ringing') return book;
    return { ...book, [callId]: { ...base, revision, status: 'answered', answeredBy: signal.deviceId } };
  }
  if (previous?.status === 'ended' || previous?.status === 'missed') return book;
  if (signal.kind === 'missed' && previous?.status === 'answered') return book;
  return { ...book, [callId]: { ...base, revision, status: signal.kind } };
}

export function ringableCalls(book: CallBook, storeIds: readonly number[], deviceActive: boolean): IncomingCall[] {
  if (!deviceActive) return [];
  const allowed = new Set(storeIds);
  return Object.values(book).filter((call) => call.status === 'ringing' && allowed.has(call.storeId));
}

/** Used only by the local simulator; production answers require server confirmation. */
export function mockAnswer(book: CallBook, callId: string, deviceId: string): { book: CallBook; accepted: boolean } {
  const call = book[callId];
  if (!call || call.status !== 'ringing') return { book, accepted: false };
  return {
    book: applyCallSignal(book, { kind: 'answered', callId, storeId: call.storeId, revision: call.revision + 1, deviceId }),
    accepted: true,
  };
}
