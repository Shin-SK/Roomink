const form = document.querySelector('#login');
const target = document.querySelector('#target');
const devices = document.querySelector('#device');
const message = document.querySelector('#message');
const lookup = document.querySelector('#lookup');
const send = document.querySelector('#send');
let credentials = null;

async function request(path, data) {
  const response = await fetch(`/api/work/demo/${path}/`, {
    method: 'POST', credentials: 'omit', cache: 'no-store',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(data),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || '接続できませんでした。 / Unable to connect.');
  return body;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  lookup.disabled = true;
  send.disabled = true;
  target.hidden = true;
  credentials = null;
  message.textContent = '端末を確認しています… / Finding your devices…';
  const input = { username: form.username.value.trim(), password: form.password.value };
  try {
    const result = await request('devices', input);
    devices.replaceChildren(...result.devices.map((device) => {
      const option = document.createElement('option');
      option.value = device.id;
      option.textContent = device.label;
      return option;
    }));
    if (!result.devices.length) throw new Error('受電端末がありません。先に同じアカウントでアプリにログインし、着信をONにしてください。 / Sign in to the app with the same account and enable receiving first.');
    credentials = input;
    target.hidden = false;
    send.disabled = false;
    message.textContent = '端末を選び、テスト着信を送ってください。 / Select your device and send a test call.';
  } catch (error) { message.textContent = error.message; }
  finally { lookup.disabled = false; }
});

send.addEventListener('click', async () => {
  if (!credentials) return;
  send.disabled = true;
  lookup.disabled = true;
  message.textContent = 'テスト着信を送っています… / Sending a test call…';
  try {
    await request('call', { ...credentials, device_id: devices.value });
    message.textContent = '着信を送りました。iPhoneで応答してください。通話後はアプリの「更新」で履歴を確認できます。 / Answer the call on your iPhone, then refresh the app to see the call history.';
  } catch (error) { message.textContent = error.message; }
  finally { send.disabled = false; lookup.disabled = false; }
});

form.addEventListener('input', () => { credentials = null; target.hidden = true; });
window.addEventListener('pagehide', () => { credentials = null; form.password.value = ''; });
