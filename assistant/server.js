require('dotenv').config();

const express = require('express');
const axios = require('axios');
const { createClient } = require('@supabase/supabase-js');
const path = require('path');

const {
  LINE_CHANNEL_ACCESS_TOKEN,
  LINE_CHANNEL_SECRET,
  OPENAI_API_KEY,
  SUPABASE_URL,
  SUPABASE_ANON_KEY
} = process.env;

const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

const app = express();
app.use(express.json());

// Helper to send reply messages without using LINE SDK
async function replyToLine(replyToken, messages) {
  if (!LINE_CHANNEL_ACCESS_TOKEN) {
    console.error('Missing LINE channel access token');
    return;
  }
  try {
    await axios.post('https://api.line.me/v2/bot/message/reply', {
      replyToken,
      messages: Array.isArray(messages) ? messages : [messages],
    }, {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${LINE_CHANNEL_ACCESS_TOKEN}`,
      },
    });
  } catch (err) {
    console.error('LINE reply error:', err.response?.data || err.message);
  }
}

// Download message content from LINE (images, videos, files)
async function downloadContent(messageId) {
  const url = `https://api-data.line.me/v2/bot/message/${messageId}/content`;
  const response = await axios.get(url, {
    responseType: 'arraybuffer',
    headers: {
      Authorization: `Bearer ${LINE_CHANNEL_ACCESS_TOKEN}`,
    },
  });
  return response.data;
}

// Upload file buffer to Supabase Storage and return public URL
async function uploadToSupabase(buffer, fileName, contentType) {
  const { data, error } = await supabase
    .storage
    .from('attachments')
    .upload(`uploads/${fileName}`, buffer, {
      contentType,
      upsert: true,
    });
  if (error) throw error;
  const { data: publicUrlData } = supabase
    .storage
    .from('attachments')
    .getPublicUrl(`uploads/${fileName}`);
  return publicUrlData.publicUrl;
}

// Summarize text using OpenAI
async function summarizeText(text) {
  if (!OPENAI_API_KEY) return null;
  try {
    const res = await axios.post(
      'https://api.openai.com/v1/chat/completions',
      {
        model: 'gpt-3.5-turbo',
        messages: [
          { role: 'system', content: 'You are a helpful assistant that summarizes messages.' },
          { role: 'user', content: `\u8acb\u7528\u7e41\u9ad4\u4e2d\u6587\u7e3d\u7d50\u9019\u6bb5\u8a0a\u606f\u7684\u91cd\u9ede\uff0c\u9650\u523080\u5b57\u4ee5\u5167:\n${text}` }
        ],
        max_tokens: 80,
      },
      {
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${OPENAI_API_KEY}`,
        },
      }
    );
    return res.data.choices[0].message.content.trim();
  } catch (err) {
    console.error('OpenAI summarize error:', err.response?.data || err.message);
    return null;
  }
}

// Handle incoming message event
async function handleMessage(event) {
  const { message, replyToken, source } = event;
  const userId = source?.userId || null;

  // Insert message into messages table
  let insertedMessage;
  try {
    const { data, error } = await supabase
      .from('messages')
      .insert({
        user_id: userId,
        type: message.type,
        message_text: message.text || message.title || null,
        raw_event: event,
      })
      .select()
      .single();
    if (error) throw error;
    insertedMessage = data;
  } catch (err) {
    console.error('Insert message error:', err);
  }

  // handle different message types
  if (['image','video','audio','file'].includes(message.type)) {
    try {
      const buffer = await downloadContent(message.id);
      const fileName = `${message.id}-${(message.fileName || message.type)}`
        .replace(/[^\w.\-]/g, '_');
      const contentType =
        message.type === 'image' ? 'image/jpeg' :
        message.type === 'video' ? 'video/mp4' :
        message.type === 'audio' ? 'audio/mpeg' :
        'application/octet-stream';
      const publicUrl = await uploadToSupabase(buffer, fileName, contentType);
      await supabase.from('attachments').insert({
        message_id: insertedMessage?.id,
        object_storage_url: publicUrl,
        content_type: contentType,
      });
      await replyToLine(replyToken, { type: 'text', text: `\u5df2\u6536\u5230\u4e26\u4fdd\u5b58\u60a8\u7684${message.type}` });
    } catch (err) {
      console.error('Attachment handling error:', err);
      await replyToLine(replyToken, { type: 'text', text: '\u62b1\u6b49\uff0c\u6a94\u6848\u8655\u7406\u5931\u6557' });
    }
  } else if (message.type === 'text') {
    const summary = await summarizeText(message.text);
    if (summary && insertedMessage) {
      try {
        await supabase.from('extractions').insert({
          message_id: insertedMessage.id,
          schema: 'summary',
          data: summary,
          confidence: 1.0,
        });
      } catch (err) {
        console.error('Insert summary error:', err);
      }
    }
    const replyText = summary ? `\u6458\u8981\uff1a${summary}` : '\u5df2\u6536\u5230\u8a0a\u606f';
    await replyToLine(replyToken, { type: 'text', text: replyText });
  } else {
    await replyToLine(replyToken, { type: 'text', text: '\u6536\u5230\u60a8\u7684\u8a0a\u606f\uff01' });
  }
}

// Webhook endpoint
app.post('/webhook', async (req, res) => {
  const events = req.body.events || [];
  for (const event of events) {
    if (event.type === 'message') {
      await handleMessage(event);
    }
  }
  res.status(200).send('OK');
});

// Serve admin static interface
app.use('/admin', express.static(path.join(__dirname, 'admin')));

// API endpoint to fetch messages with attachments and extractions
app.get('/admin/messages', async (req, res) => {
  try {
    const { data, error } = await supabase
      .from('messages')
      .select('id,user_id,type,message_text,created_at,attachments(object_storage_url),extractions(data)')
      .order('created_at', { ascending: false });
    if (error) throw error;
    res.json(data);
  } catch (err) {
    console.error('Fetch admin messages error:', err);
    res.status(500).json({ error: 'failed to fetch messages' });
  }
});

// Health check route
app.get('/', (req, res) => {
  res.send('LINE GPT assistant is running');
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log(`Server is running on port ${port}`);
});
