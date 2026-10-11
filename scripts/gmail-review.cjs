#!/usr/bin/env node
// Human-only send gate. Never register this program as a DSH/MCP tool.
const fs = require('fs');
const path = require('path');
const readline = require('readline/promises');
const { google } = require('googleapis');
const outbox = require('./gmail-outbox.cjs');

const stateDir = process.env.GMAIL_MCP_STATE_DIR || path.join(__dirname, '../.local/google-gmail');
const tokenPath = path.join(stateDir, 'send-tokens.json');
const readTokenPath = path.join(stateDir, 'tokens.json');
const clientPath = fs.existsSync(path.join(stateDir, 'oauth-client.json'))
  ? path.join(stateDir, 'oauth-client.json') : path.join(__dirname, '../.local/google-calendar/oauth-client.json');

function encodedSubject(subject) {
  const chunks = [];
  let chunk = '';
  for (const char of subject) {
    if (Buffer.byteLength(chunk + char) > 45) {
      chunks.push(`=?UTF-8?B?${Buffer.from(chunk).toString('base64')}?=`);
      chunk = '';
    }
    chunk += char;
  }
  if (chunk) chunks.push(`=?UTF-8?B?${Buffer.from(chunk).toString('base64')}?=`);
  return chunks.join('\r\n ');
}

function replyContext(message) {
  if (!message?.threadId || !Array.isArray(message.payload?.headers)) throw new Error('Original email lacks thread metadata');
  const header = (name) => message.payload.headers.find((h) => h.name?.toLowerCase() === name.toLowerCase())?.value || '';
  const messageId = header('Message-ID').trim();
  if (!/^<[^<>\s\0]+>$/.test(messageId)) throw new Error('Original email lacks a safe Message-ID header');
  const refs = (header('References').match(/<[^<>\s\0]+>/g) || []).slice(-15);
  const references = [...refs, messageId].join(' ');
  if (references.length > 900) throw new Error('Reply references are too long');
  return { threadId: message.threadId, messageId, references,
    originalFrom: header('From').replace(/[\x00-\x1f\x7f]/g, ' '),
    originalSubject: header('Subject').replace(/[\x00-\x1f\x7f]/g, ' ') };
}

function decodeSubjectHeader(value) {
  return value.replace(/\?=\s+=\?/g, '?==?').replace(/=\?UTF-8\?([BQ])\?([^?]+)\?=/gi, (_, encoding, data) => {
    if (encoding.toUpperCase() === 'B') return Buffer.from(data, 'base64').toString('utf8');
    const bytes = data.replace(/_/g, ' ').replace(/=([A-F0-9]{2})/gi, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
    return Buffer.from(bytes, 'binary').toString('utf8');
  });
}

function validateReply(email, reply) {
  const from = reply.originalFrom.trim();
  const match = from.match(/<([^<>\s]+@[^<>\s]+)>$/) || from.match(/^([^<>\s]+@[^<>\s]+)$/);
  if (!match || email.to.length !== 1 || email.to[0].toLowerCase() !== match[1].toLowerCase()
      || email.cc.length || email.bcc.length) {
    throw new Error('Reply must address only the original sender; prepare a new email for other recipients');
  }
  const normalize = (value) => decodeSubjectHeader(value).normalize('NFC').replace(/^(?:re:\s*)+/i, '').trim();
  if (!reply.originalSubject || normalize(email.subject) !== normalize(reply.originalSubject)) {
    throw new Error('Reply subject differs from original subject; prepare a new email or correct the subject');
  }
}

function rawMessage(email, senderAddress, reply) {
  const headers = [
    ...(senderAddress ? [`From: ${senderAddress}`] : []),
    `To: ${email.to.join(', ')}`,
    ...(email.cc.length ? [`Cc: ${email.cc.join(', ')}`] : []),
    ...(email.bcc.length ? [`Bcc: ${email.bcc.join(', ')}`] : []),
    `Subject: ${encodedSubject(email.subject)}`,
    ...(reply ? [`In-Reply-To: ${reply.messageId}`, `References: ${reply.references}`] : []),
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=UTF-8',
    'Content-Transfer-Encoding: base64',
  ];
  const body = Buffer.from(email.body, 'utf8').toString('base64').match(/.{1,76}/g).join('\r\n');
  return Buffer.from(`${headers.join('\r\n')}\r\n\r\n${body}\r\n`).toString('base64url');
}

function gmailClientFor(tokenFile, requiredScope) {
  const stat = fs.statSync(tokenFile);
  if (stat.mode & 0o077) throw new Error('OAuth token file has unsafe permissions');
  const saved = JSON.parse(fs.readFileSync(tokenFile, 'utf8'));
  const scopes = saved.scopes ?? [];
  const tokenScope = (saved.tokens?.scope ?? '').split(' ');
  if (!scopes.includes(requiredScope) || !tokenScope.includes(`https://www.googleapis.com/auth/${requiredScope}`)) {
    throw new Error(`OAuth token lacks ${requiredScope}`);
  }
  const client = JSON.parse(fs.readFileSync(clientPath, 'utf8'));
  const keys = client.installed || client.web;
  if (!keys?.client_id || !keys?.client_secret) throw new Error('OAuth desktop client is missing');
  const auth = new google.auth.OAuth2(keys.client_id, keys.client_secret);
  auth.setCredentials(saved.tokens);
  return google.gmail({ version: 'v1', auth });
}
function gmailClient() { return gmailClientFor(tokenPath, 'gmail.send'); }

async function loadReview(id) {
  const record = outbox.read(id);
  if (record.status !== 'prepared') throw new Error(`Draft status is ${record.status}; cannot send it again`);
  const gmail = gmailClient();
  const profile = await gmailClientFor(readTokenPath, 'gmail.readonly').users.getProfile({ userId: 'me' });
  const senderAddress = profile.data.emailAddress;
  if (typeof senderAddress !== 'string' || /[\r\n\0<> ]/.test(senderAddress)) throw new Error('Could not verify sender address');
  let reply;
  if (record.email.replyToMessageId) {
    const source = await gmailClientFor(readTokenPath, 'gmail.readonly').users.messages.get({
      userId: senderAddress, id: record.email.replyToMessageId, format: 'metadata',
      metadataHeaders: ['Message-ID', 'References', 'From', 'Subject'],
    });
    reply = replyContext(source.data);
    validateReply(record.email, reply);
  }
  return { record, gmail, senderAddress, reply };
}

async function sendReviewed({ record, gmail, senderAddress, reply }) {
  const id = record.id;
  const lockPath = `${outbox.fileFor(id)}.lock`;
  const lock = fs.openSync(lockPath, 'wx', 0o600);
  try {
    const fresh = outbox.read(id);
    if (fresh.status !== 'prepared' || fresh.sha256 !== record.sha256) throw new Error('Draft changed during review');
    fresh.status = 'sending';
    fresh.attemptedAt = new Date().toISOString();
    outbox.write(fresh);
    try {
      // Explicit userId makes Google reject a send token for another mailbox.
      const result = await gmail.users.messages.send({
        userId: senderAddress,
        requestBody: { raw: rawMessage(fresh.email, senderAddress, reply), ...(reply ? { threadId: reply.threadId } : {}) },
      });
      fresh.status = 'sent';
      fresh.sentAt = new Date().toISOString();
      fresh.gmailMessageId = result.data.id;
      fresh.gmailThreadId = result.data.threadId;
      outbox.write(fresh);
      return result.data;
    } catch (error) {
      fresh.status = 'uncertain';
      outbox.write(fresh);
      throw new Error(`Send outcome is uncertain; check Gmail Sent before doing anything else. ${error.message}`);
    }
  } finally {
    fs.closeSync(lock);
    fs.unlinkSync(lockPath);
  }
}

async function review(id) {
  if (!process.stdin.isTTY || !process.stdout.isTTY) throw new Error('Sending requires an interactive terminal');
  const context = await loadReview(id);
  const { record, senderAddress, reply } = context;
  process.stdout.write(`\nReview ID: ${id}\nSHA-256: ${record.sha256}\n`);
  process.stdout.write(`From: ${senderAddress}\nTo: ${record.email.to.join(', ')}\n`);
  if (record.email.cc.length) process.stdout.write(`Cc: ${record.email.cc.join(', ')}\n`);
  if (record.email.bcc.length) process.stdout.write(`Bcc: ${record.email.bcc.join(', ')}\n`);
  process.stdout.write(`Subject: ${record.email.subject}\n\n${record.email.body}\n\n`);
  if (reply) process.stdout.write(`Replying to Gmail message: ${record.email.replyToMessageId}\nOriginal From: ${reply.originalFrom}\nOriginal Subject: ${reply.originalSubject}\n`);
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  let answer;
  try { answer = await rl.question(`To send exactly this email, type SEND ${id}: `); }
  finally { rl.close(); }
  if (answer !== `SEND ${id}`) { process.stdout.write('Cancelled; draft remains prepared.\n'); return; }
  const result = await sendReviewed(context);
  process.stdout.write(`Sent. Gmail message ID: ${result.id}\n`);
}

async function main() {
  const arg = process.argv[2];
  if (arg === 'list' || !arg) {
    for (const item of outbox.list()) process.stdout.write(`${item.id}  ${item.status}  ${item.to.join(', ')}  ${item.subject}\n`);
    return;
  }
  await review(arg);
}

if (require.main === module) main().catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
module.exports = { encodedSubject, rawMessage, replyContext, validateReply, gmailClient, loadReview, sendReviewed, review };
