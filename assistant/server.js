require('dotenv').config();
const express = require('express');
const axios = require('axios');
const { Client } = require('@line/bot-sdk');
const { createClient } = require('@supabase/supabase-js');

// LINE and Supabase configuration
const config = {
  channelAccessToken: process.env.LINE_CHANNEL_ACCESS_TOKEN,
  channelSecret: process.env.LINE_CHANNEL_SECRET,
};

const lineClient = new Client(config);
const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_ANON_KEY);

const app = express();
app.use(express.json());

// helper: download message content from LINE
async function downloadContent(messageId) {
  const res = await axios.get(`https://api.line.me/v2/bot/message/${messageId}/content`, {
    responseType: 'arraybuffer',
    headers: {
      Authorization: `Bearer ${config.channelAccessToken}`,
    },
  });
  return res.data;
}

// helper: call OpenAI API to summarize text
async function summarizeText(text) {
  try {
    const res = await axios.post(
      'https://api.openai.com/v1/chat/completions',
      {
        model: 'gpt-3.5-turbo',
        messages: [
          { role: 'system', content: '\u4f60\u662f\u4e00\u500b\u7528\u4e2d\u6587\u56de\u7b54\u7684\u6458\u8981\u52a9\u624b\uff0c\u8acb\u7c21\u77ed\u6458\u8981\u4ee5\u4e0b\u6587\u5b57\u5167\u5bb9\u3002' },
          { role: 'user', content: text },
        ],
      },
      {
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
        },
      }
    );
    return res.data.choices?.[0]?.message?.content?.trim() || '';
  } catch (err) {
    console.error('OpenAI summarization error:', err.message);
    return '';
  }
}

// handle each event from webhook
async function handleEvent(event) {
  if (event.type !== 'message') {
    return Promise.resolve(null);
  }

  const message = event.message;

  // save raw event to messages table
  try {
    await supabase.from('messages').insert([
      {
        line_message_id: message.id,
        type: message.type,
        raw_event: event,
      },
    ]);
  } catch (e) {
    console.error('Failed to insert message:', e.message);
  }

  // process text messages
  if (message.type === 'text') {
    const summary = await summarizeText(message.text || '');
    // save extraction
    try {
      await supabase.from('extractions').insert([
        {
          line_message_id: message.id,
          schema: 'summary',
          data: { summary },
          confidence: 1.0,
        },
      ]);
    } catch (e) {
      console.error('Failed to insert extraction:', e.message);
    }
    // reply to user
    return lineClient.replyMessage(event.replyToken, {
      type: 'text',
      text: summary || `\u6536\u5230\uff1a${message.text}`,
    });
  }

  // process images, videos, audio or files
  if (['image', 'video', 'audio', 'file'].includes(message.type)) {
    try {
      const buffer = await downloadContent(message.id);
      const timestamp = Date.now();
      const ext = message.type === 'image' ? 'jpg' : message.type === 'video' ? 'mp4' : message.type === 'audio' ? 'm4a' : 'bin';
      const fileName = `${message.id}-${timestamp}.${ext}`;
      const contentType =
        message.type === 'image'
          ? 'image/jpeg'
          : message.type === 'video'
          ? 'video/mp4'
          : message.type === 'audio'
          ? 'audio/m4a'
          : 'application/octet-stream';

      // upload to Supabase Storage bucket 'attachments'
      const { error: uploadError } = await supabase.storage
        .from('attachments')
        .upload(fileName, buffer, { contentType });

      if (uploadError) {
        console.error('Upload error:', uploadError);
      }

      // get public URL
      const { data: publicData } = supabase.storage.from('attachments').getPublicUrl(fileName);
      const publicUrl = publicData?.publicUrl || null;

      // insert attachment record
      await supabase.from('attachments').insert([
        {
          line_message_id: message.id,
          name: message.fileName || fileName,
          content_type: contentType,
          size: buffer.length,
          storage_path: fileName,
          public_url: publicUrl,
        },
      ]);

      // reply to user
      return lineClient.replyMessage(event.replyToken, {
        type: 'text',
        text: '\u6536\u5230\u60a8\u7684\u6a94\u6848\uff0c\u6211\u5011\u5df2\u4fdd\u5b58\u3002',
      });
    } catch (err) {
      console.error('Attachment processing error:', err);
      return lineClient.replyMessage(event.replyToken, {
        type: 'text',
        text: '\u62b1\u6b49\uff0c\u8655\u7406\u6a94\u6848\u6642\u767c\u751f\u932f\u8aa4\u3002',
      });
    }
  }

  // for other message types
  return lineClient.replyMessage(event.replyToken, {
    type: 'text',
    text: '\u6536\u5230\u60a8\u7684\u8a0a\u606f\uff01',
  });
}

// webhook route
app.post('/webhook', async (req, res) => {
  const events = req.body.events;
  if (!events || events.length === 0) {
    return res.status(200).send('No events');
  }
  // handle all events concurrently
  await Promise.all(events.map((e) => handleEvent(e)));
  res.status(200).send('OK');
});

// health check
app.get('/', (req, res) => {
  res.send('LINE GPT assistant server is running');
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log(`Server is running on port ${port}`);
});
