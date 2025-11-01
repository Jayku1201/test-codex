require('dotenv').config();
const express = require('express');
const axios = require('axios');
const { createClient } = require('@supabase/supabase-js');

const app = express();
app.use(express.json());

// Load environment variables
const LINE_CHANNEL_ACCESS_TOKEN = process.env.LINE_CHANNEL_ACCESS_TOKEN;
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.SUPABASE_ANON_KEY;

// Initialize Supabase client
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// Helper to send reply messages without using LINE SDK
async function replyToLine(replyToken, message) {
  if (!LINE_CHANNEL_ACCESS_TOKEN) {
    console.error('Missing LINE channel access token');
    return;
  }
  try {
    await axios.post(
      'https://api.line.me/v2/bot/message/reply',
      {
        replyToken,
        messages: Array.isArray(message) ? message : [message],
      },
      {
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${LINE_CHANNEL_ACCESS_TOKEN}`,
        },
      },
    );
  } catch (err) {
    console.error('LINE reply error:', err.response?.data || err.message);
  }
}

// Helper: download message content from LINE (image/video/audio/file)
async function downloadContent(messageId) {
  if (!LINE_CHANNEL_ACCESS_TOKEN) {
    throw new Error('Missing LINE channel access token');
  }
  const url = `https://api-data.line.me/v2/bot/message/${messageId}/content`;
  const res = await axios.get(url, {
    responseType: 'arraybuffer',
    headers: {
      Authorization: `Bearer ${LINE_CHANNEL_ACCESS_TOKEN}`,
    },
  });
  return res.data;
}

// Helper: summarize text using OpenAI
async function summarizeText(text) {
  if (!OPENAI_API_KEY) {
    return null;
  }
  try {
    const response = await axios.post(
      'https://api.openai.com/v1/chat/completions',
      {
        model: 'gpt-3.5-turbo',
        messages: [
          { role: 'system', content: 'You are a helpful assistant that summarizes Chinese text concisely.' },
          { role: 'user', content: text },
        ],
        max_tokens: 100,
        temperature: 0.5,
      },
      {
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${OPENAI_API_KEY}`,
        },
      },
    );
    return response.data.choices?.[0]?.message?.content?.trim();
  } catch (err) {
    console.error('OpenAI summarization error:', err.response?.data || err.message);
    return null;
  }
}

// Handle incoming LINE events
async function handleEvent(event) {
  // Save raw event
  try {
    await supabase.from('messages').insert([
      {
        event: event,
        message_id: event.message?.id || null,
        type: event.type,
        created_at: new Date().toISOString(),
      },
    ]);
  } catch (err) {
    console.error('Supabase insert message error:', err);
  }

  if (event.type !== 'message' || !event.message) return;

  const replyToken = event.replyToken;
  const message = event.message;

  if (message.type === 'text') {
    const summary = await summarizeText(message.text);
    try {
      await supabase.from('extractions').insert([
        {
          message_id: message.id,
          summary: summary,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      console.error('Supabase insert extraction error:', err);
    }
    const replyText = summary ? `\u6458\u8981\uff1a${summary}` : '已收到訊息';
    await replyToLine(replyToken, { type: 'text', text: replyText });
  } else if (['image', 'video', 'audio', 'file'].includes(message.type)) {
    try {
      const data = await downloadContent(message.id);
      // Determine file extension
      let fileExt = 'dat';
      if (message.type === 'image') fileExt = 'jpg';
      else if (message.type === 'audio') fileExt = 'm4a';
      else if (message.type === 'video') fileExt = 'mp4';
      else if (message.fileName) {
        const parts = message.fileName.split('.');
        fileExt = parts[parts.length - 1];
      }
      const filePath = `${message.id}-${Date.now()}.${fileExt}`;
      const { error: uploadError } = await supabase.storage.from('attachments').upload(filePath, data, {
        contentType: message.type === 'file' && message.fileName ? undefined : `${message.type}/${fileExt}`,
      });
      if (uploadError) {
        console.error('Supabase storage upload error:', uploadError);
      } else {
        const { data: publicData } = supabase.storage.from('attachments').getPublicUrl(filePath);
        await supabase.from('attachments').insert([
          {
            message_id: message.id,
            type: message.type,
            url: publicData?.publicUrl || '',
            created_at: new Date().toISOString(),
          },
        ]);
      }
      await replyToLine(replyToken, { type: 'text', text: '已收到您的檔案，我們已經儲存。' });
    } catch (err) {
      console.error('Attachment handling error:', err);
      await replyToLine(replyToken, { type: 'text', text: '抱歉，檔案處理發生錯誤。' });
    }
  } else {
    await replyToLine(replyToken, { type: 'text', text: '已收到訊息' });
  }
}

// Webhook endpoint
app.post('/webhook', async (req, res) => {
  const events = req.body.events || [];
  for (const event of events) {
    await handleEvent(event);
  }
  res.status(200).send('OK');
});

// Health check
app.get('/', (req, res) => {
  res.send('LINE GPT assistant is running');
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log(`Server is running on port ${port}`);
});
