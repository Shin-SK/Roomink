// Explicit confirmation is requested only after the server detects room overlap.
export function confirmRoomOverlap(messages) {
  return new Promise(resolve => {
    const dialog = document.createElement('dialog')
    dialog.setAttribute('aria-label', 'ルームの重複を確認')
    dialog.style.cssText = 'width:min(480px,calc(100% - 32px));border:1px solid #e2e8f0;border-radius:16px;padding:24px;color:#334155;box-shadow:0 24px 80px #0003'
    const heading = document.createElement('h2')
    heading.textContent = 'ルームの時間が重なっています'
    heading.style.fontSize = '1.15rem'
    const text = document.createElement('p')
    text.textContent = messages.join('\n')
    text.style.cssText = 'white-space:pre-wrap;line-height:1.7'
    const note = document.createElement('p')
    note.textContent = '内容に間違いがなければ、重なったままシフトを登録できます。'
    const actions = document.createElement('div')
    actions.style.cssText = 'display:flex;flex-wrap:wrap;gap:10px;justify-content:flex-end'
    const back = document.createElement('button')
    back.textContent = '戻って修正'
    back.className = 'btn btn-outline-secondary'
    back.style.cssText = 'color:#334155;background:#fff;border:1px solid #94a3b8'
    const proceed = document.createElement('button')
    proceed.textContent = '重複を確認して登録'
    proceed.className = 'btn btn-warning'
    let accepted = false
    proceed.onclick = () => { accepted = true; dialog.close() }
    back.onclick = () => dialog.close()
    dialog.addEventListener('close', () => { dialog.remove(); resolve(accepted) }, { once: true })
    actions.append(back, proceed)
    dialog.append(heading, text, note, actions)
    document.body.append(dialog)
    dialog.showModal()
    back.focus()
  })
}

export function roomOverlapMessages(data) {
  return [...(Array.isArray(data?.room_overlap) ? data.room_overlap : []),
    ...(Array.isArray(data?.errors) ? data.errors : []).flatMap(row => row.room_overlap || [])]
}

export async function withRoomOverlapConfirmation(send, body) {
  try { return await send(body) } catch (error) {
    const messages = roomOverlapMessages(error.data)
    if (!messages.length || !(await confirmRoomOverlap(messages))) throw error
    return send({ ...body, allow_room_overlap: true })
  }
}
