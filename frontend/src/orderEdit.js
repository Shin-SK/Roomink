const nullableId = value => value === '' || value == null ? null : Number(value)
const sortedIds = value => [...(value || [])].map(Number).sort((a, b) => a - b)

export function changedOrderFields(order, proposed) {
  const original = {
    ...order,
    options: order.option_ids || [],
    payment_method: order.payment_method || 'UNSET',
    card_include_options: Boolean(order.card_include_options),
    memo: order.memo || '',
    service_recipient_name: order.service_recipient_name || '',
  }
  const patch = {}
  for (const [key, value] of Object.entries(proposed)) {
    let before = original[key]
    let after = value
    if (['cast', 'course', 'medium', 'nomination_fee', 'discount', 'extension', 'reception_staff'].includes(key)) {
      before = nullableId(before)
      after = nullableId(after)
    } else if (key === 'options') {
      before = sortedIds(before)
      after = sortedIds(after)
    }
    if (JSON.stringify(before) !== JSON.stringify(after)) patch[key] = value
  }
  // The API accepts the reservation date/time as one group (including 24+ hours).
  const timeFields = ['business_date', 'start_time_extended', 'end_time_extended']
  if (timeFields.some(key => key in patch)) {
    for (const key of timeFields) patch[key] = proposed[key] ?? original[key]
  }
  if (Object.keys(patch).length) patch.expected_updated_at = order.updated_at
  return patch
}
