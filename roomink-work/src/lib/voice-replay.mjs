/**
 * Replay the observed ordering against an injected diagnostics consumer.
 * This never sends a VoIP notification or calls the production voice SDK.
 */
export async function replayVoiceEvents(replay, consume, wait) {
  if (replay?.version !== 1 || replay.clock !== 'server_observed' ||
      !Array.isArray(replay.events) || replay.events.length > 500) {
    throw new Error('Unsupported voice replay');
  }
  let previousTime = 0;
  for (const event of replay.events) {
    if (!Number.isSafeInteger(event.at_ms) || event.at_ms < previousTime ||
        typeof event.stage !== 'string' || typeof event.leg !== 'string') {
      throw new Error('Invalid voice replay event');
    }
    previousTime = event.at_ms;
  }
  previousTime = 0;
  for (const event of replay.events) {
    const elapsed = event.at_ms - previousTime;
    if (elapsed > 0) await wait(elapsed);
    await consume(event);
    previousTime = event.at_ms;
  }
}
