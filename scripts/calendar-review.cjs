// Human-only Calendar write gate. Do not expose createReviewed as an MCP tool.
const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');
const outbox = require('./calendar-outbox.cjs');

const stateDir = process.env.SSS_GOOGLE_CALENDAR_STATE || path.join(__dirname, '../.local/google-calendar');
const tokenPath = path.join(stateDir, 'tokens.json');
const clientPath = path.join(stateDir, 'oauth-client.json');

function calendarClient() {
  const stat = fs.statSync(tokenPath);
  if (stat.mode & 0o077) throw new Error('Calendar token file has unsafe permissions');
  const saved = JSON.parse(fs.readFileSync(tokenPath, 'utf8'));
  const tokens = saved.normal;
  if (!tokens?.scope?.split(' ').includes('https://www.googleapis.com/auth/calendar')) throw new Error('Calendar OAuth token lacks event write permission');
  const client = JSON.parse(fs.readFileSync(clientPath, 'utf8'));
  const keys = client.installed || client.web;
  if (!keys?.client_id || !keys?.client_secret) throw new Error('OAuth desktop client is missing');
  const auth = new google.auth.OAuth2(keys.client_id, keys.client_secret);
  auth.setCredentials(tokens);
  return google.calendar({ version: 'v3', auth });
}

async function createReviewed(id, calendar = calendarClient()) {
  const lockPath = `${outbox.fileFor(id)}.lock`;
  const lock = fs.openSync(lockPath, 'wx', 0o600);
  try {
    const record = outbox.read(id);
    if (record.status !== 'prepared') throw new Error(`Event status is ${record.status}; cannot create it again`);
    record.status = 'creating';
    record.attemptedAt = new Date().toISOString();
    outbox.write(record);
    const event = record.event;
    const requestBody = {
      id: record.id,
      summary: event.summary,
      description: event.description,
      start: { dateTime: event.start, ...(event.timeZone ? { timeZone: event.timeZone } : {}) },
      end: { dateTime: event.end, ...(event.timeZone ? { timeZone: event.timeZone } : {}) },
      ...(event.attendees.length ? { attendees: event.attendees.map((email) => ({ email })) } : {}),
    };
    try {
      const response = await calendar.events.insert({ calendarId: event.calendarId, requestBody,
        sendUpdates: event.attendees.length ? 'all' : 'none' });
      record.status = 'created';
      record.createdAtGoogle = new Date().toISOString();
      record.googleEventId = response.data.id;
      record.htmlLink = response.data.htmlLink;
      outbox.write(record);
      return { id: response.data.id, htmlLink: response.data.htmlLink };
    } catch (error) {
      record.status = 'uncertain';
      outbox.write(record);
      throw new Error(`Event outcome is uncertain; check the calendar before doing anything else. ${error.message}`);
    }
  } finally {
    fs.closeSync(lock);
    fs.unlinkSync(lockPath);
  }
}

module.exports = { calendarClient, createReviewed };
