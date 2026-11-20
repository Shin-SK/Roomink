// Display lanes never become saved therapist or room assignments.
export function freePendingTimeline(orders) {
  const pending = orders.filter(order => order.is_free_pending && order.status !== 'CANCELLED')
    .slice().sort((a, b) => new Date(a.start) - new Date(b.start) || a.id - b.id)
  const ends = []
  const blocks = pending.map(order => {
    const start = new Date(order.start).getTime()
    let lane = ends.findIndex(end => end <= start)
    if (lane < 0) lane = ends.length
    ends[lane] = new Date(order.end).getTime()
    return { ...order, cast_id: `free-pending-${lane}`, is_off_shift: false }
  })
  return {
    casts: ends.map((_, lane) => ({ id: `free-pending-${lane}`, name: lane ? `フリー・担当未定 ${lane + 1}` : 'フリー・担当未定', is_pending_lane: true, shifts: [], interval_minutes: 0 })),
    orders: blocks,
    queueIds: new Set(pending.map(order => order.cast_id)),
  }
}
