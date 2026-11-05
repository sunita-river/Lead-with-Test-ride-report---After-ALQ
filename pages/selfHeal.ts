import { errors, Locator, Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';

/**
 * Backup locators for when Salesforce changes a screen.
 *
 * healed() finds an element by its usual (primary) locator. Only if the
 * primary finds nothing does it try the backups, in order, and use the first
 * one that matches, so a renamed label or id doesn't stop the login. Each
 * backup used is logged as a "[HEAL]" line and appended to
 * output/healed-locators.json, so the primary can be fixed permanently.
 * Pure code: nothing is sent to any outside service.
 */
export const HEAL_FILE = path.resolve(__dirname, '..', 'output', 'healed-locators.json');

export type HealEvent = { label: string; primary: string; used_backup: number; backup: string; url: string; time: string };
export const healEvents: HealEvent[] = []; // backups used this run (each label/backup once)

/**
 * Wait until `primary` or any of `backups` is in the page (timeout in ms,
 * undefined = Playwright's default), then return `primary` unchanged if it
 * matches, else the first backup that does. Throws a TimeoutError naming
 * every locator tried if none turns up. Keep backups in the same frame as
 * the primary.
 */
export async function healed(page: Page, label: string, primary: Locator, backups: Locator[], timeout?: number): Promise<Locator> {
  let either = primary;
  for (const backup of backups) either = either.or(backup);
  try {
    await either.first().waitFor({ state: 'attached', timeout });
  } catch (err) {
    if (!(err instanceof errors.TimeoutError)) throw err;
    const tried = [primary, ...backups].map(String).join('; ');
    throw new errors.TimeoutError(`Timeout: "${label}" not found on the page - tried ${tried}`);
  }
  if (await primary.count()) return primary;
  for (const [i, backup] of backups.entries()) {
    if (await backup.count()) {
      record(page, label, primary, i + 1, backup);
      return backup;
    }
  }
  return primary; // the match vanished mid-refresh; the caller's own wait takes over
}

function record(page: Page, label: string, primary: Locator, n: number, backup: Locator) {
  if (healEvents.some(e => e.label === label && e.used_backup === n)) return; // already logged this run
  const event: HealEvent = { label, primary: String(primary), used_backup: n, backup: String(backup), url: page.url(), time: new Date().toISOString() };
  healEvents.push(event);
  console.log(`[HEAL] ${label}: primary ${event.primary} not found, used backup ${n} ${event.backup}`);
  try { // a problem writing the record must never stop the run
    let events: HealEvent[] = [];
    try {
      const saved = JSON.parse(fs.readFileSync(HEAL_FILE, 'utf-8'));
      if (Array.isArray(saved)) events = saved;
    } catch { /* no file yet, or unreadable: start a new list */ }
    events.push(event);
    fs.mkdirSync(path.dirname(HEAL_FILE), { recursive: true });
    fs.writeFileSync(HEAL_FILE, JSON.stringify(events, null, 2));
  } catch { /* ignore */ }
}
