// SiBi LINE-GPT Assistant - server_gpt.js
// Version: v1.5 (memory + recall + 10s dedup + admin notify + optional attachment upload)
// Runtime: Node 18+, Express on Render. Webhook: POST /webhook

require('dotenv').config();
const express = require('express');
const axios = require('axios');
const { createClient } = require('@supabase/supabase-js');

const {
  LINE_CHANNEL_ACCESS_TOKEN,
  OPENAI_API_KEY,
  SUPABASE_URL,
  SUPABASE_ANON_KEY,
  ADMIN_USER_ID,              // 可選：有人在群組 @ 其他人時推播通知的對象
} = process.env;

// ---- Feature flags ----
const FF_MEMORIES   = process.env.FF_MEMORIES === 'on';  // 記憶功能（/remember、/recall）
const FF_RESPONSES  = process.env.FF_RESPONSES === 'on'; // 先關閉（未使用）
const FF_WEB_SEARCH = process.env.FF_WEB_SEARCH === 'on';// 先關閉（未使用）

// ---- Clients ----
const app = express();
app.use(express.json());

const supabase = (SUPABASE_URL && SUPABASE_ANON_KEY)
  ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  : null;

// ---- Helpers: LINE ----
async function replyToLine(replyToken, message) {
  const messages = Array.isArray(message) ? message : [message];
  const payload = {
    replyToken,
    messages: messages.map(m => (typeof m === 'string' ? { type: 'text', text: m } : m)),
  };
  await axios.post('https://api.line.me/v2/bot/message/reply', payload, {
    headers: {
      Authorization: `Bearer ${LINE_CHANNEL_ACCESS_TOKEN}`,
      'Content-Type': 'application/json',
    },
  });
}

async function pushMessage(toUserId, message) {
  const messages = Array.isArray(message) ? message : [message];
  const payload = {
    to: toUserId,
    messages: messages.map(m => (typeof m === 'string' ? { type: 'text', text: m } : m)),
  };
  await axios.post('https://api.line.me/v2/bot/message/push', payload, {
    headers: {
      Authorization: `Bearer ${LINE_CHANNEL_ACCESS_TOKEN}`,
      'Content-Type': 'application/json',
    },
  });
}

async function downloadLineContent(messageId) {
  const url = `https://api-data.line.me/v2/bot/message/${messageId}/content`;
  const res = await axios.get(url, {
    responseType: 'arraybuffer',
    headers: { Authorization: `Bearer ${LINE_CHANNEL_ACCESS_TOKEN}` },
  });
  return Buffer.from(res.data);
}

async function uploadToSupabase(buffer, path, contentType) {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase.storage
      .from('attachments')                       // 需先在 Supabase 建 bucket: attachments
      .upload(path, buffer, { contentType, upsert: true });
    if (error) throw error;
    const { publicURL } = supabase.storage.from('attachments').getPublicUrl(path).data;
    return publicURL || null;
  } catch (err) {
    console.error('Upload to Supabase failed:', err.response?.data || err.message);
    return null;
  }
}

// ---- Helper: OpenAI Chat ----
async function callChatGPT(userText, systemPrompt = '你是一位使用繁體中文回覆的助理。回覆要精簡、直接。') {
  const payload = {
    model: 'gpt-4o-mini',
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userText }
    ],
    temperature: 0.7,
    max_tokens: 512,
  };
  const res = await axios.post('https://api.openai.com/v1/chat/completions', payload, {
    headers: {
      Authorization: `Bearer ${OPENAI_API_KEY}`,
      'Content-Type': 'application/json',
    },
    timeout: 30000,
  });
  return res.data.choices?.[0]?.message?.content?.trim() || '（沒有內容）';
}

// ---- Helpers: Memory (DB: group_memories) ----
async function saveMemory(groupId, userId, content) {
  if (!supabase) return;
  try {
    await supabase.from('group_memories').insert({ group_id: groupId, user_id: userId, content });
  } catch (err) {
    console.error('Save memory error:', err.message || err);
  }
}
async function getLastMemory(groupId) {
  if (!supabase) return null;
  try {
    const { data, error } = await supabase
      .from('group_memories')
      .select('content, created_at')
      .eq('group_id', groupId)
      .order('created_at', { ascending: false })
      .limit(1);
    if (error) throw error;
    return (data && data[0]) ? data[0].content : null;
  } catch (err) {
    console.error('Get memory error:', err.message || err);
    return null;
  }
}

// ---- State: 10s dedup for default reply ----
let lastDefaultMessage = '';
let lastDefaultTimestamp = 0;

// ---- Health check ----
app.get('/', (_, res) => {
  res.status(200).send('LINE GPT assistant server with GPT replies is running');
});

// ---- Webhook ----
app.post('/webhook', async (req, res) => {
  try {
    const events = req.body?.events || [];
    for (const event of events) {
      if (event.type === 'message') {
        await handleMessage(event);
      }
    }
    res.sendStatus(200);
  } catch (err) {
    console.error('Webhook error:', err.message || err);
    res.sendStatus(500);
  }
});

async function handleMessage(event) {
  const { replyToken, source, message } = event;
  const mentionees = message?.mention?.mentionees || [];
  const isMentionBot = mentionees.some(m => m.isSelf);                 // @機器人
  const isMentionOthers = mentionees.some(m => !m.isSelf && m.userId); // @其他人
  const groupId = source.groupId || source.roomId || source.userId;
  const userId = source.userId;

  // ---- 附件處理（可選）----
  if (['image', 'video', 'audio', 'file'].includes(message?.type)) {
    try {
      const buffer = await downloadLineContent(message.id);
      const ts = Date.now();
      const ext = message.type === 'image' ? 'jpg'
        : message.type === 'video' ? 'mp4'
        : message.type === 'audio' ? 'm4a'
        : 'bin';
      const path = `uploads/${groupId || 'na'}/${message.id}-${ts}.${ext}`;
      const url = await uploadToSupabase(buffer, path, message.contentProvider?.type || `application/octet-stream`);
      await replyToLine(replyToken, {
        type: 'text',
        text: url ? `已收到並保存您的 ${message.type}。\n${url}` : `已收到您的 ${message.type}。`,
      });
    } catch (err) {
      console.error('Attachment handling error:', err.message || err);
      await replyToLine(replyToken, '已收到您的檔案。');
    }
    return;
  }

  // ---- 文字訊息處理 ----
  if (message?.type === 'text') {
    const text = (message.text || '').trim();

    // 1) 記憶：@機器人 + 「記住…」或 /remember
    if (FF_MEMORIES && isMentionBot && (text.includes('記住') || text.startsWith('/remember'))) {
      const memoryContent = text.replace(/(記住|\/remember)\s*/i, '').trim();
      if (memoryContent) {
        await saveMemory(groupId, userId, memoryContent);
        await replyToLine(replyToken, '我會記住。');
        return;
      }
    }

    // 2) 召回：@機器人 + 「上次…」或 /recall
    if (FF_MEMORIES && isMentionBot && (text.includes('上次') || text.startsWith('/recall'))) {
      const last = await getLastMemory(groupId);
      await replyToLine(replyToken, last ? `你之前提過：${last}` : '目前沒有記錄。');
      return;
    }

    // 3) 群組 @ 其他人 → 通知管理者（可選）
    if (isMentionOthers && ADMIN_USER_ID) {
      const ids = mentionees.filter(m => !m.isSelf && m.userId).map(m => m.userId).join(', ');
      const notify = `【群組通知】${source.userId || '某位成員'} 提及了：${ids}\n內容：${text}`;
      try { await pushMessage(ADMIN_USER_ID, notify); } catch (_) {}
      // 預設對話可繼續往下走（不攔截）
    }

    // 4) 若 @ 機器人 → 走 GPT 回覆
    if (isMentionBot) {
      try {
        const gpt = await callChatGPT(text);
        await replyToLine(replyToken, gpt);
      } catch (err) {
        console.error('GPT error:', err.message || err);
        await replyToLine(replyToken, '稍等一下，我這邊有點忙線。');
      }
      return;
    }

    // 5) 預設簡短回覆（含 10 秒內相同文字不重覆回覆）
    const now = Date.now();
    if (text === lastDefaultMessage && (now - lastDefaultTimestamp) < 10000) {
      // 靜默：避免刷頻
      return;
    }
    lastDefaultMessage = text;
    lastDefaultTimestamp = now;
    await replyToLine(replyToken, '收到');
    return;
  }

  // 不是文字也不是附件：給個簡短確認
  await replyToLine(replyToken, '收到');
}

// ---- Start server ----
const PORT = process.env.PORT || 10000;
app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});
// 召回條件：@機器人 + 「上次」或 /recall；或未 @ 但明確提到「上次」/ /recall
const recallIntent = /上次|\/recall/i.test(text);
if (FF_MEMORIES && (isMentionBot || recallIntent)) {
  const last = await getLastMemory(groupId);
  await replyToLine(replyToken, last ? `你之前提過：${last}` : '目前沒有記錄。');
  return;
}
async function saveMemory(groupId, userId, content) {
  console.log('[MEMO] save groupId=', groupId, 'userId=', userId, 'content=', content);
  if (!supabase) throw new Error('Supabase client not initialized');

  const { error } = await supabase
    .from('group_memories')
    .insert({ group_id: groupId, user_id: userId, content });

  if (error) throw error;
}
if (FF_MEMORIES && isMentionBot && (text.includes('記住') || text.startsWith('/remember'))) {
  const memoryContent = text.replace(/(記住|\/remember)\s*/i, '').trim();
  if (memoryContent) {
    try {
      await saveMemory(groupId, userId, memoryContent);
      await replyToLine(replyToken, '我會記住。');
    } catch (err) {
      console.error('Save memory error:', err.message || err);
      await replyToLine(replyToken, '記錄暫時失敗，我再試一次。');
    }
    return;
  }
}

