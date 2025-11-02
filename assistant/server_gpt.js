require('dotenv').config();

const express = require('express');
const axios = require('axios');
const { createClient } = require('@supabase/supabase-js');
const path = require('path');

const {
  LINE_CHANNEL_ACCESS_TOKEN,
  OPENAI_API_KEY,
  SUPABASE_URL,
  SUPABASE_ANON_KEY,
  ADMIN_USER_ID,
  BOT_USER_ID,
} = process.env;

const supabase = (SUPABASE_URL && SUPABASE_ANON_KEY) ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;

const app = express();
app.use(express.json());

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

async function pushMessage(userId, messages) {
  if (!LINE_CHANNEL_ACCESS_TOKEN) {
    console.error('Missing LINE channel access token');
    return;
  }
  try {
    await axios.post('https://api.line.me/v2/bot/message/push', {
      to: userId,
      messages: Array.isArray(messages) ? messages : [messages],
    }, {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${LINE_CHANNEL_ACCESS_TOKEN}`,
      },
    });
  } catch (err) {
    console.error('LINE push error:', err.response?.data || err.message);
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
  if (!supabase) throw new Error('Supabase not configured');
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

// Call OpenAI ChatGPT to get response
async function callChatGPT(text) {
  if (!OPENAI_API_KEY) {
    console.error('Missing OpenAI API key');
    return '抱歉，目前無法回覆';
  }
  try {
    const res = await axios.post(
      'https://api.openai.com/v1/chat/completions',
      {
        model: 'gpt-3.5-turbo',
        messages: [
          { role: 'system', content: 'You are a helpful assistant that responds in Traditional Chinese.' },
          { role: 'user', content: text },
        ],
        max_tokens: 512,
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
    console.error('OpenAI error:', err.response?.data || err.message);
    return '抱歉，暫時無法回覆';
  }
}

// Handle incoming message event
async function handleMessage(event) {
  const { message, replyToken, source } = event;
  const mentionees = message?.mention?.mentionees || [];
  const isMentionBot = mentionees.some((m) => m.userId === BOT_USER_ID);
  const isMentionOthers = mentionees.some((m) => m.userId !== BOT_USER_ID);
  const userId = source?.userId || null;

  // Insert message into Supabase messages table (text only)
  let insertedMessage = null;
  if (supabase && message.type === 'text') {
    try {
      const { data, error } = await supabase
        .from('messages')
        .insert({
          user_id: userId,
          type: message.type,
          message_text: message.text,
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

  // If someone mentioned the bot
  if (isMentionBot) {
    const gptReply = await callChatGPT(message.text);
    await replyToLine(replyToken, { type: 'text', text: gptReply });
    if (supabase && insertedMessage) {
      try {
        await supabase.from('messages').update({ gpt_reply: gptReply }).eq('id', insertedMessage.id);
      } catch (err) {
        console.error('Save gpt reply error:', err);
      }
    }
    return;
  }

  // If someone mentioned others in a group (notify admin)
  if (isMentionOthers) {
    const mentionIds = mentionees.map((m) => m.userId).join(', ');
    const notifyText = `${userId} \u63d0\u5230 ${mentionIds}`;
    await pushMessage(ADMIN_USER_ID, { type: 'text', text: notifyText });
    return;
  }

  // Private chat or group chat without mentions
  if (source.type === 'user' && message.type === 'text') {
    const gptReply = await callChatGPT(message.text);
    await replyToLine(replyToken, { type: 'text', text: gptReply });
    if (supabase && insertedMessage) {
      try {
        await supabase.from('messages').update({ gpt_reply: gptReply }).eq('id', insertedMessage.id);
      } catch (err) {
        console.error('Save gpt reply error:', err);
      }
    }
    return;
  }

  // Handle attachments
  if (['image','video','audio','file'].includes(message.type)) {
    try {
      const buffer = await downloadContent(message.id);
      const fileName = `${message.id}-${(message.fileName || message.type)}`.replace(/[^\w.\\-]/g, '_');
      const contentType =
        message.type === 'image' ? 'image/jpeg' :
        message.type === 'video' ? 'video/mp4' :
        message.type === 'audio' ? 'audio/mpeg' :
        'application/octet-stream';
      if (supabase && insertedMessage) {
        const publicUrl = await uploadToSupabase(buffer, fileName, contentType);
        await supabase.from('attachments').insert({
          message_id: insertedMessage.id,
          object_storage_url: publicUrl,
          content_type: contentType,
        });
      }
      await replyToLine(replyToken, { type: 'text', text: `已收到並保存您的${message.type}` });
    } catch (err) {
      console.error('Attachment handling error:', err);
      await replyToLine(replyToken, { type: 'text', text: '抱歉，檔案處理失敗' });
    }
    return;
  }

  // Default reply
  await replyToLine(replyToken, { type: 'text', text: '收到您的訊息！' });
}

app.post('/webhook', async (req, res) => {
  const events = req.body.events || [];
  for (const event of events) {
    if (event.type === 'message') {
      await handleMessage(event);
    }
  }
  res.status(200).send('OK');
});

app.use('/admin', express.static(path.join(__dirname, 'admin')));

app.get('/', (req, res) => {
  res.send('LINE GPT assistant server with GPT replies is running');
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log(`Server is running on port ${port}`);
});
