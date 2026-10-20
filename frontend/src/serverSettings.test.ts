// The owner's server settings on Settings (B26): what the form starts from, what Save sends, the words. `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { ServerStatus } from './api.ts'
import {
  baselineOf, blockOf, fieldsNamedIn, reachableFromPhone, secretLine, serverChanges, setupState, sourceLine, tapLine,
} from './serverSettings.ts'

const status = (over: Partial<ServerStatus['fields']> = {}): ServerStatus => ({
  fields: {
    data_mode: { value: 'snapshot', source: 'default' },
    alert_tz: { value: 'UTC', source: 'default' },
    app_url: { value: 'http://localhost:5173', source: 'default' },
    ntfy_url: { value: 'https://ntfy.sh', source: 'default' },
    smtp_port: { value: 587, source: 'default' },
    smtp_starttls: { value: true, source: 'default' },
    telegram_chat_id: { value: '', source: 'default' },
    ...over,
  },
  secrets: {
    ntfy_topic: { set: true, source: 'env' },
    ntfy_token: { set: false, source: 'default' },
    smtp_host: { set: true, source: 'saved' },
    smtp_user: { set: false, source: 'default' },
    smtp_password: { set: false, source: 'default' },
    alert_email_from: { set: false, source: 'default' },
    alert_email_to: { set: false, source: 'default' },
    nvd_api_key: { set: false, source: 'default' },
    telegram_bot_token: { set: false, source: 'default' },
  },
  env_names: {
    data_mode: 'DATA_MODE', alert_tz: 'ALERT_TZ', app_url: 'APP_URL', ntfy_url: 'NTFY_URL', smtp_port: 'SMTP_PORT',
    smtp_starttls: 'SMTP_STARTTLS', ntfy_topic: 'NTFY_TOPIC', ntfy_token: 'NTFY_TOKEN', smtp_host: 'SMTP_HOST',
    smtp_user: 'SMTP_USER', smtp_password: 'SMTP_PASSWORD', alert_email_from: 'ALERT_EMAIL_FROM',
    alert_email_to: 'ALERT_EMAIL_TO', nvd_api_key: 'NVD_API_KEY', telegram_chat_id: 'TELEGRAM_CHAT_ID',
    telegram_bot_token: 'TELEGRAM_BOT_TOKEN',
  },
  app_url_reachable: false,
  feeds: 'real',
})

test('B26.8 an address on this machine is unreachable from a phone; a LAN, Tailscale or Cloud Run one is', () => {
  for (const url of ['http://localhost:5173', 'http://127.0.0.1:5173', 'http://127.4.5.6', 'http://[::1]:5173',
    'http://0.0.0.0:8000', 'http://app.localhost', '', 'not a url']) {
    assert.equal(reachableFromPhone(url), false, url)
  }
  for (const url of ['https://patch-abc.a.run.app', 'http://192.168.1.20:5173', 'http://desk.tail1234.ts.net']) {
    assert.equal(reachableFromPhone(url), true, url)
  }
})

test('B26.8 the tap line says what tapping an alert does', () => {
  assert.match(tapLine('http://localhost:5173'), /opens the message in the ntfy app/)
  assert.match(tapLine('https://patch-abc.a.run.app'), /opens Patch at the CVE/)
})

test("B26.8 the time zone starts as the browser's while nothing is saved and no quiet hours depend on UTC", () => {
  assert.equal(baselineOf(status(), 'Europe/Vilnius', false).alert_tz, 'Europe/Vilnius')
  assert.equal(baselineOf(status(), 'Europe/Vilnius', true).alert_tz, 'UTC') // saved quiet hours keep working
  const saved = status({ alert_tz: { value: 'Asia/Tokyo', source: 'saved' } })
  assert.equal(baselineOf(saved, 'Europe/Vilnius', false).alert_tz, 'Asia/Tokyo')
  const env = status({ alert_tz: { value: 'UTC', source: 'env' } })
  assert.equal(baselineOf(env, 'Europe/Vilnius', false).alert_tz, 'UTC')
})

test('B26.8 Save sends only what changed, the secrets typed or removed, and the zone with new quiet hours', () => {
  const s = status()
  const base = baselineOf(s, 'Europe/Vilnius', false)
  assert.deepEqual(serverChanges(s, base, base, {}, false), {})
  assert.deepEqual(serverChanges(s, base, { ...base, data_mode: 'live' }, {}, false), { data_mode: 'live' })
  assert.deepEqual(serverChanges(s, base, base, { ntfy_token: 'tk_new', smtp_host: null }, false),
    { ntfy_token: 'tk_new', smtp_host: null })
  assert.deepEqual(serverChanges(s, base, base, { ntfy_token: '' }, false), {}) // an empty box changes nothing
  // the browser's zone is saved with the first quiet hours, so they mean what the owner sees
  assert.deepEqual(serverChanges(s, base, base, {}, true), { alert_tz: 'Europe/Vilnius' })
  assert.deepEqual(serverChanges(s, base, { ...base, app_url: 'http://192.168.1.20:5173/' }, {}, false),
    { app_url: 'http://192.168.1.20:5173' })
})

test('B26.8 a setting from the environment says so, and a secret says only whether it is set', () => {
  const s = status()
  assert.equal(sourceLine(s, 'data_mode'), null)
  assert.equal(sourceLine(status({ data_mode: { value: 'live', source: 'env' } }), 'data_mode'),
    "Set in the server's environment, which wins.")
  assert.equal(secretLine(s, 'ntfy_topic', undefined), "Set in the server's environment, which wins.")
  assert.equal(secretLine(s, 'smtp_host', undefined), 'Saved. Type a new one to replace it.')
  assert.equal(secretLine(s, 'smtp_host', null), 'Removed when you save.')
  assert.equal(secretLine(s, 'ntfy_token', undefined), 'Not set.')
  assert.equal(secretLine(s, 'ntfy_token', 'x'), 'Saved when you save.')
})

test("SL.4 a folded setup block's summary says its state: set up, not set up, or the environment's", () => {
  const s = status() // ntfy_topic from the environment, smtp_host saved
  assert.equal(setupState(s, 'ntfy', true), "set in the server's environment")
  assert.equal(setupState(s, 'email', true), 'set up')
  assert.equal(setupState(s, 'email', false), 'not set up')
  assert.equal(setupState(s, 'links', false), 'this computer only')
  assert.equal(setupState({ ...s, app_url_reachable: true }, 'links', false), 'phones can open it')
  assert.equal(setupState(status({ app_url: { value: 'https://x.run.app', source: 'env' } }), 'links', false),
    "set in the server's environment")
})

test('SL.6 a failed save names the fields it refused; each belongs to its setup block', () => {
  const msg = "The request isn't in the expected shape. ntfy_topic: String should match pattern '^[-_A-Za-z0-9]{1,64}$'"
  assert.deepEqual(fieldsNamedIn(msg), ['ntfy_topic'])
  assert.deepEqual(fieldsNamedIn('… smtp_port: too big; alert_email_to: not an email'), ['smtp_port', 'alert_email_to'])
  assert.deepEqual(fieldsNamedIn("Can't reach the backend at /api. Is it running?"), [])
  assert.deepEqual(fieldsNamedIn('data_mode: wrong'), []) // not in a setup block
  assert.equal(blockOf('ntfy_token'), 'ntfy')
  assert.equal(blockOf('smtp_starttls'), 'email')
  assert.equal(blockOf('app_url'), 'links')
})

test('B57.13 Telegram has its own setup block: the token and the chat id, with its state', () => {
  assert.equal(blockOf('telegram_bot_token'), 'telegram')
  assert.equal(blockOf('telegram_chat_id'), 'telegram')
  const msg = "The request isn't in the expected shape. telegram_chat_id: String should match pattern '…'"
  assert.deepEqual(fieldsNamedIn(msg), ['telegram_chat_id'])
  assert.equal(setupState(status(), 'telegram', false), 'not set up')
  assert.equal(setupState(status(), 'telegram', true), 'set up')
  const env = { ...status(), secrets: { ...status().secrets, telegram_bot_token: { set: true, source: 'env' as const } } }
  assert.equal(setupState(env, 'telegram', true), "set in the server's environment")
})

test('B57.13 the chat id starts as the server says and is sent trimmed when changed', () => {
  const s = status({ telegram_chat_id: { value: '42', source: 'saved' } })
  const base = baselineOf(s, 'UTC', false)
  assert.equal(base.telegram_chat_id, '42')
  assert.deepEqual(serverChanges(s, base, { ...base, telegram_chat_id: ' 987654321 ' }, {}, false),
    { telegram_chat_id: '987654321' })
  assert.deepEqual(serverChanges(s, base, { ...base, telegram_chat_id: ' 42' }, {}, false), {})
  assert.deepEqual(serverChanges(s, base, base, { telegram_bot_token: ' 1:abc ' }, false), { telegram_bot_token: '1:abc' })
})
