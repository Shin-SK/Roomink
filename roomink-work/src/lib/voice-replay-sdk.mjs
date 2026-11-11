class Emitter {
  listeners = new Map();
  on(name, callback) {
    const callbacks = this.listeners.get(name) ?? [];
    callbacks.push(callback);
    this.listeners.set(name, callbacks);
  }
  emit(name, ...args) {
    for (const callback of this.listeners.get(name) ?? []) callback(...args);
  }
}

/** An isolated SDK transport for the same voice session used by live reception. */
export function createReplaySdk() {
  let voice;
  let invite;
  let call;
  class ReplayCall extends Emitter {
    state = 'connecting';
    getSid() { return 'replay'; }
    getFrom() { return ''; }
    getState() { return this.state; }
    async disconnect() { this.emit('disconnected'); }
    static Event = {
      Connected: 'connected', Reconnected: 'reconnected', Reconnecting: 'reconnecting',
      Disconnected: 'disconnected', ConnectFailure: 'connectFailure',
    };
    static State = { Connected: 'connected' };
  }
  class ReplayInvite extends Emitter {
    getCallSid() { return 'replay'; }
    getFrom() { return ''; }
    async accept() {
      call ??= new ReplayCall();
      this.emit('accepted', call);
      return call;
    }
    async reject() { this.emit('rejected'); }
    static Event = { Accepted: 'accepted', Cancelled: 'cancelled', Rejected: 'rejected' };
  }
  class ReplayVoice extends Emitter {
    constructor() { super(); voice = this; }
    async register() {}
    async unregister() {}
    async getCalls() { return new Map(); }
    async getCallInvites() { return new Map(); }
    static Event = { CallInvite: 'invite', Error: 'error' };
  }
  return {
    sdk: { Voice: ReplayVoice, Call: ReplayCall, CallInvite: ReplayInvite },
    async deliver(event) {
      if (!voice) throw new Error('Replay session is not initialized');
      switch (event.stage) {
        case 'invite':
          invite = new ReplayInvite();
          voice.emit('invite', invite);
          break;
        case 'accepted':
          if (invite) await invite.accept();
          break;
        case 'connecting':
          if (invite && !call) await invite.accept();
          break;
        case 'connected':
          if (invite && !call) await invite.accept();
          if (call) { call.state = 'connected'; call.emit('connected'); }
          break;
        case 'reconnecting': call?.emit('reconnecting'); break;
        case 'cancelled': invite?.emit('cancelled'); break;
        case 'rejected': invite?.emit('rejected'); break;
        case 'ended': call?.emit('disconnected'); break;
        case 'registration_failed':
        case 'error':
          voice.emit('error', Object.assign(new Error('Recorded voice error'), { code: event.snapshot?.error_code }));
          break;
      }
    },
  };
}
