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

// Check if Supabase credentials exist
const hasSupabase = SUPABASE_URL && SUPABASE_ANON_KEY;
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
          { role: 'user', content: `請用繁體中文總結這段訊息的重點，限於80字以內:\n${text}` }
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

  // Insert message into messages table only if Supabase credentials exist
  let insertedMessage = null;
  if (hasSupabase) {
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
  }

  // handle different message types
  if (['image','video','audio','file'].includes(message.type)) {
    try {
      // Download attachment content
      const buffer = await downloadContent(message.id);
      const fileName = `${message.id}-${(message.fileName || message.type)}`.replace(/[^\w.\-]/g, '_');
      const contentType =
        message.type === 'image' ? 'image/jpeg' :
        message.type === 'video' ? 'video/mp4' :
        message.type === 'audio' ? 'audio/mpeg' :
        'application/octet-stream';
      // Only upload and save attachment if Supabase is configured and message inserted
      if (hasSupabase && insertedMessage) {
        const publicUrl = await uploadToSupabase(buffer, fileName, contentType);
        await supabase.from('attachments').insert({
          message_id: insertedMessage.id,
          object_storage_url: publicUrl,
          content_type: contentType,
        });
      }
      // Reply to user that file is received (always)
      await replyToLine(replyToken, { type: 'text', text: `已收到並保存您的${message.type}` });
    } catch (err) {
      console.error('Attachment handling error:', err);
      await replyToLine(replyToken, { type: 'text', text: '抱歉，檔案處理失敗' });
    }
  } else if (message.type === 'text') {
    // Summarize text
    const summary = await summarizeText(message.text);
    // Save summary to database only if Supabase is configured and summary exists and message inserted
    if (hasSupabase && summary && insertedMessage) {
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
    // reply with summary or confirm
    const replyText = summary ? `摘要：${summary}` : '已收到訊息';
    await replyToLine(replyToken, { type: 'text', text: replyText });
  } else {
    await replyToLine(replyToken, { type: 'text', text: '收到您的訊息！' });
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
  if (!hasSupabase) {
    res.json([]);
    return;
  }

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
